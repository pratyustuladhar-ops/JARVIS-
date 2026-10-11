const { spawn, exec } = require('child_process');
const http = require('http');
const path = require('path');
const fs = require('fs');
const EventEmitter = require('events');

class ServiceManager extends EventEmitter {
  constructor(options = {}) {
    super();
    this.repoRoot = options.repoRoot || path.resolve(__dirname, '..');
    this.backendDir = path.join(this.repoRoot, 'jarvis-backend');
    this.backendUrl = options.backendUrl || 'http://127.0.0.1:8000';
    this.localAgentUrl = options.localAgentUrl || 'http://127.0.0.1:8001';

    this.backendProcess = null;
    this.localAgentProcess = null;
    this.backendPid = null;
    this.localAgentPid = null;

    this.status = {
      backend: 'offline', // 'offline' | 'starting' | 'online' | 'error'
      localAgent: 'offline',
      backendPid: null,
      localAgentPid: null,
      lastHealthCheck: null,
      details: ''
    };

    this.pollTimer = null;
    this.isShuttingDown = false;
  }

  /**
   * Locate the preferred Python interpreter
   */
  getPythonPath() {
    const venvPython = path.join(this.backendDir, 'venv', 'Scripts', 'python.exe');
    if (fs.existsSync(venvPython)) {
      return venvPython;
    }
    return process.platform === 'win32' ? 'python' : 'python3';
  }

  /**
   * Asynchronously perform an HTTP GET with timeout
   */
  async httpGetJson(urlStr, timeoutMs = 2500) {
    return new Promise((resolve, reject) => {
      try {
        const url = new URL(urlStr);
        const req = http.get(
          {
            hostname: url.hostname,
            port: url.port || 80,
            path: url.pathname + url.search,
            timeout: timeoutMs,
            headers: { 'User-Agent': 'JARVIS-Desktop/1.0' }
          },
          (res) => {
            let data = '';
            res.on('data', (chunk) => {
              data += chunk;
            });
            res.on('end', () => {
              if (res.statusCode && res.statusCode >= 200 && res.statusCode < 400) {
                try {
                  const json = JSON.parse(data);
                  resolve({ statusCode: res.statusCode, data: json });
                } catch {
                  resolve({ statusCode: res.statusCode, raw: data });
                }
              } else {
                reject(new Error(`HTTP status ${res.statusCode}`));
              }
            });
          }
        );

        req.on('timeout', () => {
          req.destroy(new Error('Request timed out'));
        });

        req.on('error', (err) => {
          reject(err);
        });
      } catch (err) {
        reject(err);
      }
    });
  }

  /**
   * Health check for JARVIS FastAPI Backend (/health)
   */
  async checkBackendHealth() {
    try {
      const res = await this.httpGetJson(`${this.backendUrl}/health`, 2000);
      if (res && res.data && res.data.status === 'online') {
        return { online: true, version: res.data.version || '1.0.0' };
      }
      return { online: false, reason: 'Invalid health payload' };
    } catch (err) {
      return { online: false, reason: err.message };
    }
  }

  /**
   * Health check for Local Agent (HTTP server on port 8001 or backend check)
   */
  async checkLocalAgentHealth() {
    try {
      const res = await this.httpGetJson(`${this.localAgentUrl}/status`, 1500);
      if (res && (res.statusCode === 200 || res.data)) {
        return { online: true };
      }
      return { online: false, reason: 'Inactive' };
    } catch (err) {
      // Local agent might not expose /status, or is inactive
      return { online: false, reason: err.message };
    }
  }

  /**
   * Comprehensive check of all services
   */
  async checkAll() {
    const prevBackend = this.status.backend;
    const prevAgent = this.status.localAgent;

    const [backendRes, agentRes] = await Promise.all([
      this.checkBackendHealth(),
      this.checkLocalAgentHealth()
    ]);

    const newBackend = backendRes.online ? 'online' : (this.backendProcess ? 'starting' : 'offline');
    const newAgent = agentRes.online ? 'online' : (this.localAgentProcess ? 'starting' : 'offline');

    this.status = {
      backend: newBackend,
      localAgent: newAgent,
      backendPid: this.backendPid,
      localAgentPid: this.localAgentPid,
      lastHealthCheck: new Date().toISOString(),
      details: backendRes.online ? 'Connected to JARVIS Core' : (backendRes.reason || 'Offline')
    };

    if (prevBackend !== newBackend || prevAgent !== newAgent) {
      this.emit('status-change', { ...this.status });
    }

    return { ...this.status };
  }

  /**
   * Launch backend if not already running
   */
  async startBackend() {
    const health = await this.checkBackendHealth();
    if (health.online) {
      this.status.backend = 'online';
      this.emit('status-change', { ...this.status });
      return { started: false, alreadyRunning: true };
    }

    if (this.backendProcess) {
      return { started: false, alreadyStarting: true };
    }

    const pythonBin = this.getPythonPath();
    const args = ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'];

    try {
      this.status.backend = 'starting';
      this.emit('status-change', { ...this.status });

      const child = spawn(pythonBin, args, {
        cwd: this.backendDir,
        env: { ...process.env, PYTHONUNBUFFERED: '1' },
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true
      });

      this.backendProcess = child;
      this.backendPid = child.pid;
      this.status.backendPid = child.pid;

      child.stdout.on('data', (d) => {
        const text = d.toString();
        if (text.includes('Application startup complete') || text.includes('Uvicorn running on')) {
          this.status.backend = 'online';
          this.emit('status-change', { ...this.status });
        }
      });

      child.stderr.on('data', (d) => {
        // Log or inspect
      });

      child.on('exit', (code, signal) => {
        this.backendProcess = null;
        this.backendPid = null;
        this.status.backendPid = null;
        if (!this.isShuttingDown) {
          this.status.backend = code === 0 ? 'offline' : 'error';
          this.emit('status-change', { ...this.status });
        }
      });

      return { started: true, pid: child.pid };
    } catch (err) {
      this.status.backend = 'error';
      this.emit('status-change', { ...this.status });
      throw err;
    }
  }

  /**
   * Launch local agent if not already running
   */
  async startLocalAgent() {
    const health = await this.checkLocalAgentHealth();
    if (health.online) {
      this.status.localAgent = 'online';
      this.emit('status-change', { ...this.status });
      return { started: false, alreadyRunning: true };
    }

    if (this.localAgentProcess) {
      return { started: false, alreadyStarting: true };
    }

    const pythonBin = this.getPythonPath();
    const args = ['-m', 'local_agent.agent'];

    try {
      this.status.localAgent = 'starting';
      this.emit('status-change', { ...this.status });

      const child = spawn(pythonBin, args, {
        cwd: this.repoRoot,
        env: { ...process.env, PYTHONUNBUFFERED: '1' },
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true
      });

      this.localAgentProcess = child;
      this.localAgentPid = child.pid;
      this.status.localAgentPid = child.pid;

      child.stdout.on('data', (d) => {
        const text = d.toString();
        if (text.includes('is ONLINE') || text.includes('Local agent')) {
          this.status.localAgent = 'online';
          this.emit('status-change', { ...this.status });
        }
      });

      child.on('exit', (code) => {
        this.localAgentProcess = null;
        this.localAgentPid = null;
        this.status.localAgentPid = null;
        if (!this.isShuttingDown) {
          this.status.localAgent = code === 0 ? 'offline' : 'error';
          this.emit('status-change', { ...this.status });
        }
      });

      return { started: true, pid: child.pid };
    } catch (err) {
      this.status.localAgent = 'error';
      this.emit('status-change', { ...this.status });
      throw err;
    }
  }

  /**
   * Start polling health loop
   */
  startPolling(intervalMs = 4000) {
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.pollTimer = setInterval(async () => {
      try {
        await this.checkAll();
      } catch {
        // ignore polling error
      }
    }, intervalMs);
  }

  stopPolling() {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  /**
   * Terminate only child processes launched by this manager
   */
  async shutdownAll() {
    this.isShuttingDown = true;
    this.stopPolling();

    const killPid = (pid) => {
      return new Promise((resolve) => {
        if (!pid) return resolve();
        if (process.platform === 'win32') {
          exec(`taskkill /pid ${pid} /T /F`, () => resolve());
        } else {
          try {
            process.kill(pid, 'SIGTERM');
          } catch {
            // ignore
          }
          resolve();
        }
      });
    };

    const promises = [];
    if (this.backendPid) {
      promises.push(killPid(this.backendPid));
    }
    if (this.localAgentPid) {
      promises.push(killPid(this.localAgentPid));
    }

    await Promise.all(promises);

    this.backendProcess = null;
    this.backendPid = null;
    this.localAgentProcess = null;
    this.localAgentPid = null;
    this.status.backend = 'offline';
    this.status.localAgent = 'offline';
  }
}

module.exports = { ServiceManager };
