const { spawn, spawnSync, exec } = require('child_process');
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

    this.backendStderrLog = [];
    this.localAgentStderrLog = [];
    this.cachedPythonConfig = null;

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
   * Verify if candidate Python command can run and import backend dependencies
   */
  verifyPythonCandidate(command, baseArgs = []) {
    try {
      const probeArgs = [
        ...baseArgs,
        '-c',
        'import sys, uvicorn, fastapi; print("JARVIS_PYTHON_VALID:" + sys.version.split()[0])'
      ];
      const res = spawnSync(command, probeArgs, {
        encoding: 'utf8',
        timeout: 4000,
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'pipe']
      });

      if (res.status === 0 && res.stdout && res.stdout.includes('JARVIS_PYTHON_VALID:')) {
        const match = res.stdout.match(/JARVIS_PYTHON_VALID:([^\s\r\n]+)/);
        const version = match ? match[1] : 'unknown';
        return { valid: true, version };
      }
      return {
        valid: false,
        error: (res.stderr || res.stdout || (res.error ? res.error.message : 'Unknown probe error')).trim()
      };
    } catch (err) {
      return { valid: false, error: err.message };
    }
  }

  /**
   * Discovers and verifies the preferred Python interpreter.
   * Checks virtualenv, then py -3.11, python3.11, python, python3.
   * Does NOT select an interpreter missing FastAPI or Uvicorn.
   */
  findPythonInterpreter(forceRefresh = false) {
    if (this.cachedPythonConfig && !forceRefresh) {
      return this.cachedPythonConfig;
    }

    const isWin = process.platform === 'win32';
    const candidates = [];

    // 1. Virtual environments (preferred only if dependencies are verified)
    const venvRelPaths = isWin
      ? [
          path.join('jarvis-backend', 'venv', 'Scripts', 'python.exe'),
          path.join('jarvis-backend', '.venv', 'Scripts', 'python.exe'),
          path.join('venv', 'Scripts', 'python.exe'),
          path.join('.venv', 'Scripts', 'python.exe')
        ]
      : [
          path.join('jarvis-backend', 'venv', 'bin', 'python'),
          path.join('jarvis-backend', '.venv', 'bin', 'python'),
          path.join('venv', 'bin', 'python'),
          path.join('.venv', 'bin', 'python')
        ];

    for (const rel of venvRelPaths) {
      const fullPath = path.resolve(this.repoRoot, rel);
      if (fs.existsSync(fullPath)) {
        candidates.push({
          command: fullPath,
          baseArgs: [],
          displayPath: fullPath,
          isVenv: true,
          label: `VirtualEnv (${rel})`
        });
      }
    }

    // 2. Python launcher on Windows (e.g. py -3.11, py -3)
    if (isWin) {
      candidates.push({
        command: 'py',
        baseArgs: ['-3.11'],
        displayPath: 'py -3.11',
        isVenv: false,
        label: 'Windows Python Launcher (py -3.11)'
      });
      candidates.push({
        command: 'py',
        baseArgs: ['-3'],
        displayPath: 'py -3',
        isVenv: false,
        label: 'Windows Python Launcher (py -3)'
      });
    }

    // 3. System Python candidates
    candidates.push(
      { command: 'python3.11', baseArgs: [], displayPath: 'python3.11', isVenv: false, label: 'System python3.11' },
      { command: 'python', baseArgs: [], displayPath: 'python', isVenv: false, label: 'System python' },
      { command: 'python3', baseArgs: [], displayPath: 'python3', isVenv: false, label: 'System python3' }
    );

    const probeErrors = [];

    for (const cand of candidates) {
      const probe = this.verifyPythonCandidate(cand.command, cand.baseArgs);
      if (probe.valid) {
        this.cachedPythonConfig = {
          command: cand.command,
          baseArgs: cand.baseArgs,
          displayPath: cand.displayPath,
          isVenv: cand.isVenv,
          label: cand.label,
          version: probe.version,
          verified: true
        };
        return this.cachedPythonConfig;
      } else {
        probeErrors.push(`${cand.displayPath}: ${probe.error || 'not runnable'}`);
      }
    }

    // Fallback if none passed probe
    const fallback = isWin ? 'python' : 'python3';
    this.cachedPythonConfig = {
      command: fallback,
      baseArgs: [],
      displayPath: fallback,
      isVenv: false,
      label: 'Unverified fallback',
      version: 'unverified',
      verified: false,
      probeErrors
    };
    return this.cachedPythonConfig;
  }

  getPythonCommand() {
    return this.findPythonInterpreter();
  }

  /**
   * Backwards-compatible string representation of Python command or path
   */
  getPythonPath() {
    const config = this.getPythonCommand();
    return config.command || config.displayPath;
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

    const newBackend = backendRes.online
      ? 'online'
      : (this.backendProcess ? 'starting' : (prevBackend === 'error' ? 'error' : 'offline'));
    const newAgent = agentRes.online
      ? 'online'
      : (this.localAgentProcess ? 'starting' : (prevAgent === 'error' ? 'error' : 'offline'));

    let details = 'Offline';
    if (backendRes.online && agentRes.online) {
      details = 'Connected to JARVIS Core';
    } else if (backendRes.online) {
      details = 'Connected to JARVIS Core (Local Agent offline)';
    } else if (this.status.details && this.status.details !== 'Offline' && this.status.details !== 'Connected to JARVIS Core') {
      details = this.status.details;
    } else if (backendRes.reason) {
      details = backendRes.reason;
    }

    this.status = {
      backend: newBackend,
      localAgent: newAgent,
      backendPid: this.backendPid,
      localAgentPid: this.localAgentPid,
      lastHealthCheck: new Date().toISOString(),
      details
    };

    if (prevBackend !== newBackend || prevAgent !== newAgent) {
      this.emit('status-change', { ...this.status });
    }

    return { ...this.status };
  }

  /**
   * Launch backend if not already running, with bounded readiness polling
   */
  async startBackend(options = {}) {
    const waitForReady = options.waitForReady !== false;
    const timeoutMs = options.timeoutMs || 15000;

    const health = await this.checkBackendHealth();
    if (health.online) {
      this.status.backend = 'online';
      this.status.details = 'Connected to JARVIS Core';
      this.emit('status-change', { ...this.status });
      return { started: false, alreadyRunning: true, ready: true };
    }

    if (this.backendProcess) {
      if (waitForReady) {
        return this.waitForBackendReady(timeoutMs);
      }
      return { started: false, alreadyStarting: true };
    }

    const pyConfig = this.getPythonCommand();
    const args = [...pyConfig.baseArgs, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'];

    this.backendStderrLog = [];

    try {
      this.status.backend = 'starting';
      this.status.details = `Starting FastAPI core using ${pyConfig.label || pyConfig.displayPath}...`;
      this.emit('status-change', { ...this.status });

      const child = spawn(pyConfig.command, args, {
        cwd: this.backendDir,
        env: {
          ...process.env,
          PYTHONUNBUFFERED: '1',
          PYTHONPATH: this.backendDir
        },
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
          this.status.details = 'Connected to JARVIS Core';
          this.emit('status-change', { ...this.status });
        }
      });

      child.stderr.on('data', (d) => {
        const text = d.toString();
        this.backendStderrLog.push(text);
        if (this.backendStderrLog.length > 25) {
          this.backendStderrLog.shift();
        }
      });

      child.on('exit', (code) => {
        this.backendProcess = null;
        this.backendPid = null;
        this.status.backendPid = null;
        if (!this.isShuttingDown) {
          const detail = this.backendStderrLog.join('').trim() || `Process exited with code ${code}`;
          this.status.backend = code === 0 ? 'offline' : 'error';
          this.status.details = detail;
          this.emit('status-change', { ...this.status });
        }
      });

      child.on('error', (err) => {
        this.status.backend = 'error';
        this.status.details = `Spawn failure: ${err.message}`;
        this.emit('status-change', { ...this.status });
      });

      if (waitForReady) {
        return await this.waitForBackendReady(timeoutMs);
      }

      return { started: true, pid: child.pid };
    } catch (err) {
      this.status.backend = 'error';
      this.status.details = err.message;
      this.emit('status-change', { ...this.status });
      throw err;
    }
  }

  async waitForBackendReady(timeoutMs = 15000) {
    const startTime = Date.now();
    const pollInterval = 300;

    while (Date.now() - startTime < timeoutMs) {
      if (!this.backendProcess && this.status.backend === 'error') {
        const detail = this.backendStderrLog.join('').trim() || this.status.details || 'Backend exited before becoming healthy';
        throw new Error(`FastAPI backend failed to start: ${detail}`);
      }

      const health = await this.checkBackendHealth();
      if (health.online) {
        this.status.backend = 'online';
        this.status.details = 'Connected to JARVIS Core';
        this.emit('status-change', { ...this.status });
        return { started: true, pid: this.backendPid, ready: true };
      }

      await new Promise((r) => setTimeout(r, pollInterval));
    }

    const detail = this.backendStderrLog.join('').trim() || 'Health check timed out';
    this.status.backend = 'error';
    this.status.details = `Readiness timeout (${timeoutMs}ms): ${detail}`;
    this.emit('status-change', { ...this.status });
    throw new Error(`FastAPI backend did not become ready within ${timeoutMs}ms. Details: ${detail}`);
  }

  /**
   * Launch local agent if not already running, with bounded readiness polling
   */
  async startLocalAgent(options = {}) {
    const waitForReady = options.waitForReady !== false;
    const timeoutMs = options.timeoutMs || 10000;

    const health = await this.checkLocalAgentHealth();
    if (health.online) {
      this.status.localAgent = 'online';
      this.emit('status-change', { ...this.status });
      return { started: false, alreadyRunning: true, ready: true };
    }

    if (this.localAgentProcess) {
      if (waitForReady) {
        return this.waitForLocalAgentReady(timeoutMs);
      }
      return { started: false, alreadyStarting: true };
    }

    const pyConfig = this.getPythonCommand();
    const args = [...pyConfig.baseArgs, '-m', 'local_agent.agent'];

    this.localAgentStderrLog = [];

    try {
      this.status.localAgent = 'starting';
      this.emit('status-change', { ...this.status });

      const child = spawn(pyConfig.command, args, {
        cwd: this.repoRoot,
        env: {
          ...process.env,
          PYTHONUNBUFFERED: '1',
          PYTHONPATH: this.repoRoot
        },
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true
      });

      this.localAgentProcess = child;
      this.localAgentPid = child.pid;
      this.status.localAgentPid = child.pid;

      child.stdout.on('data', (d) => {
        const text = d.toString();
        if (text.includes('is ONLINE') || text.includes('Local agent') || text.includes('Running on')) {
          this.status.localAgent = 'online';
          this.emit('status-change', { ...this.status });
        }
      });

      child.stderr.on('data', (d) => {
        const text = d.toString();
        this.localAgentStderrLog.push(text);
        if (this.localAgentStderrLog.length > 25) {
          this.localAgentStderrLog.shift();
        }
      });

      child.on('exit', (code) => {
        this.localAgentProcess = null;
        this.localAgentPid = null;
        this.status.localAgentPid = null;
        if (!this.isShuttingDown) {
          const detail = this.localAgentStderrLog.join('').trim() || `Process exited with code ${code}`;
          this.status.localAgent = code === 0 ? 'offline' : 'error';
          this.emit('status-change', { ...this.status });
        }
      });

      child.on('error', (err) => {
        this.status.localAgent = 'error';
        this.emit('status-change', { ...this.status });
      });

      if (waitForReady) {
        return await this.waitForLocalAgentReady(timeoutMs);
      }

      return { started: true, pid: child.pid };
    } catch (err) {
      this.status.localAgent = 'error';
      this.emit('status-change', { ...this.status });
      throw err;
    }
  }

  async waitForLocalAgentReady(timeoutMs = 10000) {
    const startTime = Date.now();
    const pollInterval = 300;

    while (Date.now() - startTime < timeoutMs) {
      if (!this.localAgentProcess && this.status.localAgent === 'error') {
        const detail = this.localAgentStderrLog.join('').trim() || 'Local agent exited before becoming healthy';
        throw new Error(`Windows Local Agent failed to start: ${detail}`);
      }

      const health = await this.checkLocalAgentHealth();
      if (health.online) {
        this.status.localAgent = 'online';
        this.emit('status-change', { ...this.status });
        return { started: true, pid: this.localAgentPid, ready: true };
      }

      await new Promise((r) => setTimeout(r, pollInterval));
    }

    const detail = this.localAgentStderrLog.join('').trim() || 'Health check timed out';
    this.status.localAgent = 'error';
    this.emit('status-change', { ...this.status });
    throw new Error(`Windows Local Agent did not become ready within ${timeoutMs}ms. Details: ${detail}`);
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
