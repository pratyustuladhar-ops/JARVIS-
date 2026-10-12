import { test, describe, before, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { SettingsStore, DEFAULT_SETTINGS } = require('../desktop/settings-store.cjs');
const { ServiceManager } = require('../desktop/service-manager.cjs');
const { WindowManager } = require('../desktop/window-manager.cjs');

describe('JARVIS Windows Desktop Application Architecture', () => {
  const testConfigPath = path.resolve('.test-desktop-settings.json');

  after(() => {
    if (fs.existsSync(testConfigPath)) {
      try { fs.unlinkSync(testConfigPath); } catch {}
    }
  });

  describe('Desktop Settings Store & Persistence', () => {
    test('SettingsStore initializes with default values', () => {
      const store = new SettingsStore(testConfigPath);
      const settings = store.getAll();

      assert.equal(settings.startMinimized, false);
      assert.equal(settings.minimizeToTrayOnClose, true);
      assert.equal(settings.launchOnStartup, false, 'Launch on Windows login must be disabled by default');
      assert.equal(settings.startBackgroundServices, true);
      assert.equal(settings.showDesktopNotifications, true);
      assert.equal(settings.globalShortcut, 'CommandOrControl+Shift+J');
      assert.ok(settings.backendUrl.includes('8000'));
      assert.ok(settings.localAgentUrl.includes('8001'));
      assert.ok(settings.webControlPanelUrl.includes('5173'));
    });

    test('SettingsStore saves and persists updates to local disk', () => {
      const store = new SettingsStore(testConfigPath);
      const updateResult = store.set({
        startMinimized: true,
        launchOnStartup: true,
        globalShortcut: 'CommandOrControl+Alt+J'
      });

      assert.equal(updateResult.success, true);
      assert.equal(updateResult.settings.startMinimized, true);
      assert.equal(updateResult.settings.launchOnStartup, true);
      assert.equal(updateResult.settings.globalShortcut, 'CommandOrControl+Alt+J');

      // Verify file on disk
      assert.ok(fs.existsSync(testConfigPath));
      const onDisk = JSON.parse(fs.readFileSync(testConfigPath, 'utf8'));
      assert.equal(onDisk.startMinimized, true);
      assert.equal(onDisk.launchOnStartup, true);
      assert.equal(onDisk.globalShortcut, 'CommandOrControl+Alt+J');
    });

    test('SettingsStore safely sanitizes unknown or invalid fields', () => {
      const store = new SettingsStore(testConfigPath);
      store.set({
        invalidField: 'malicious',
        globalShortcut: '   ',
        launchOnStartup: 'not-a-boolean'
      });

      const current = store.getAll();
      assert.equal(current.invalidField, undefined);
      assert.notEqual(current.globalShortcut.trim(), '');
    });

    test('SettingsStore resets back to defaults cleanly', () => {
      const store = new SettingsStore(testConfigPath);
      store.set({ startMinimized: true, launchOnStartup: true });
      const reset = store.reset();

      assert.equal(reset.startMinimized, false);
      assert.equal(reset.launchOnStartup, false);
    });
  });

  describe('Service Manager & Process Lifecycle', () => {
    test('ServiceManager discovers valid repo paths and Python environment', () => {
      const sm = new ServiceManager();
      assert.ok(fs.existsSync(sm.repoRoot), 'Repo root must exist');
      assert.ok(fs.existsSync(sm.backendDir), 'Backend directory must exist');

      const pythonPath = sm.getPythonPath();
      assert.ok(pythonPath, 'Python path must be resolved');
    });

    test('ServiceManager reports offline status before processes start', () => {
      const sm = new ServiceManager();
      assert.equal(sm.status.backend, 'offline');
      assert.equal(sm.status.localAgent, 'offline');
      assert.equal(sm.backendPid, null);
      assert.equal(sm.localAgentPid, null);
    });

    test('ServiceManager graceful shutdown does not terminate unrelated processes', async () => {
      const sm = new ServiceManager();
      // Without spawned child, shutdownAll should safely execute and resolve without killing anything
      await sm.shutdownAll();
      assert.equal(sm.status.backend, 'offline');
      assert.equal(sm.status.localAgent, 'offline');
      assert.equal(sm.backendPid, null);
    });

    test('ServiceManager rejects invalid virtual environment missing uvicorn and falls back safely', () => {
      const sm = new ServiceManager();
      const venvPy = path.join(sm.backendDir, 'venv', 'Scripts', 'python.exe');

      if (fs.existsSync(venvPy)) {
        // jarvis-backend/venv exists on disk but has only pip/setuptools (missing uvicorn)
        const probe = sm.verifyPythonCandidate(venvPy);
        assert.equal(probe.valid, false, 'venv lacking uvicorn must be rejected');
      }

      // Resolved interpreter must be verified and not select the unverified venv
      const resolved = sm.findPythonInterpreter(true);
      assert.equal(resolved.verified, true, 'Resolved interpreter must be verified');
      assert.notEqual(resolved.command, venvPy, 'Must not pick invalid venv');
      assert.ok(resolved.version, 'Must detect valid Python version');
    });

    test('ServiceManager prevents duplicate backend and local agent process spawning', async () => {
      const sm = new ServiceManager();

      // Simulate backend already running
      sm.checkBackendHealth = async () => ({ online: true, version: '1.0.0' });
      const backendResult = await sm.startBackend({ waitForReady: false });
      assert.equal(backendResult.started, false);
      assert.equal(backendResult.alreadyRunning, true);
      assert.equal(sm.backendProcess, null);

      // Simulate local agent already running
      sm.checkLocalAgentHealth = async () => ({ online: true });
      const agentResult = await sm.startLocalAgent({ waitForReady: false });
      assert.equal(agentResult.started, false);
      assert.equal(agentResult.alreadyRunning, true);
      assert.equal(sm.localAgentProcess, null);

      // Simulate process already starting
      sm.checkBackendHealth = async () => ({ online: false });
      sm.backendProcess = { pid: 99999 };
      const startingBackend = await sm.startBackend({ waitForReady: false });
      assert.equal(startingBackend.started, false);
      assert.equal(startingBackend.alreadyStarting, true);
    });

    test('ServiceManager readiness check captures errors and times out cleanly on failing processes', async () => {
      const sm = new ServiceManager();
      sm.checkBackendHealth = async () => ({ online: false, reason: 'Simulated connection refused' });
      sm.backendStderrLog = ['Error: Address already in use'];

      // Bounded timeout
      await assert.rejects(
        async () => {
          await sm.waitForBackendReady(350);
        },
        /did not become ready/
      );
      assert.equal(sm.status.backend, 'error');
      assert.ok(sm.status.details.includes('Readiness timeout'));
      assert.ok(sm.status.details.includes('Address already in use'));
    });
  });

  describe('Desktop Files and Packaging Structure', () => {
    test('desktop directory contains core files', () => {
      assert.ok(fs.existsSync(path.resolve('desktop/main.cjs')), 'main.cjs must exist');
      assert.ok(fs.existsSync(path.resolve('desktop/preload.cjs')), 'preload.cjs must exist');
      assert.ok(fs.existsSync(path.resolve('desktop/settings-store.cjs')), 'settings-store.cjs must exist');
      assert.ok(fs.existsSync(path.resolve('desktop/service-manager.cjs')), 'service-manager.cjs must exist');
      assert.ok(fs.existsSync(path.resolve('desktop/tray-manager.cjs')), 'tray-manager.cjs must exist');
      assert.ok(fs.existsSync(path.resolve('desktop/window-manager.cjs')), 'window-manager.cjs must exist');
    });

    test('desktop assets contain icon.ico, icon.png, and tray-icon.png', () => {
      assert.ok(fs.existsSync(path.resolve('desktop/assets/icon.ico')), 'icon.ico must exist');
      assert.ok(fs.existsSync(path.resolve('desktop/assets/icon.png')), 'icon.png must exist');
      assert.ok(fs.existsSync(path.resolve('desktop/assets/tray-icon.png')), 'tray-icon.png must exist');
    });

    test('package.json contains electron scripts and packaging commands', () => {
      const pkg = JSON.parse(fs.readFileSync(path.resolve('package.json'), 'utf8'));
      assert.equal(pkg.main, 'desktop/main.cjs');
      assert.ok(pkg.scripts['electron:start'], 'Must have electron:start script');
      assert.ok(pkg.scripts['electron:dev'], 'Must have electron:dev script');
      assert.ok(pkg.scripts['package:win'], 'Must have package:win script');
      assert.ok(pkg.scripts['desktop:build'], 'Must have desktop:build script');
    });

    test('preload.cjs exposes isolated jarvisDesktop API without raw ipcRenderer', () => {
      const preloadCode = fs.readFileSync(path.resolve('desktop/preload.cjs'), 'utf8');
      assert.ok(preloadCode.includes("contextBridge.exposeInMainWorld('jarvisDesktop'"), 'Must use contextBridge');
      assert.ok(!preloadCode.includes("window.ipcRenderer ="), 'Must not expose raw ipcRenderer');
      assert.ok(preloadCode.includes('getSettings'), 'Must expose getSettings');
      assert.ok(preloadCode.includes('updateSettings'), 'Must expose updateSettings');
      assert.ok(preloadCode.includes('getServiceStatus'), 'Must expose getServiceStatus');
      assert.ok(preloadCode.includes('checkHealth'), 'Must expose checkHealth');
      assert.ok(preloadCode.includes('minimizeToTray'), 'Must expose minimizeToTray');
    });

    test('window-manager.cjs enforces security best practices', () => {
      const wmCode = fs.readFileSync(path.resolve('desktop/window-manager.cjs'), 'utf8');
      assert.ok(wmCode.includes('contextIsolation: true'), 'Must enable contextIsolation');
      assert.ok(wmCode.includes('nodeIntegration: false'), 'Must disable nodeIntegration');
      assert.ok(wmCode.includes('setWindowOpenHandler'), 'Must intercept window open');
      assert.ok(wmCode.includes('shell.openExternal'), 'Must open external links safely');
      assert.ok(wmCode.includes('minimizeToTrayOnClose'), 'Must handle minimize to tray on close');
    });

    test('tray-manager.cjs provides all required Windows tray context menu actions', () => {
      const tmCode = fs.readFileSync(path.resolve('desktop/tray-manager.cjs'), 'utf8');
      assert.ok(tmCode.includes('JARVIS Assistant'), 'Must include JARVIS Assistant');
      assert.ok(tmCode.includes('Open Web Control Panel'), 'Must include Web Control Panel link');
      assert.ok(tmCode.includes('Desktop Settings'), 'Must include Desktop Settings link');
      assert.ok(tmCode.includes('Quit JARVIS'), 'Must include Quit JARVIS');
      assert.ok(tmCode.includes('notifyBackgroundMode'), 'Must support background notification');
    });

    test('WindowManager resolves built entry HTML files and dist/assistant.html uses relative paths', () => {
      const wm = new WindowManager({ settingsStore: new SettingsStore() });
      const assistantEntry = wm.getEntryHtmlPath('assistant');
      const settingsEntry = wm.getEntryHtmlPath('settings');

      assert.ok(fs.existsSync(assistantEntry), 'Resolved assistant entry HTML must exist on disk');
      assert.ok(fs.existsSync(settingsEntry), 'Resolved settings entry HTML must exist on disk');

      // Verify production dist entry exists and uses relative asset paths compatible with file:// URLs
      const distAssistant = path.resolve('dist/assistant.html');
      assert.ok(fs.existsSync(distAssistant), 'dist/assistant.html must exist from build');
      assert.equal(assistantEntry, distAssistant, 'getEntryHtmlPath must prioritize built dist/ file');

      const content = fs.readFileSync(distAssistant, 'utf8');
      assert.ok(content.includes('./assets/'), 'Built HTML must reference scripts via relative ./assets/ paths');
      assert.ok(!content.includes('src="/assets/'), 'Built HTML must not reference scripts via absolute /assets/ paths');
    });
  });

  describe('UI Integration & Desktop Settings Verification', () => {
    test('settings.html contains Desktop & Background configuration section', () => {
      const html = fs.readFileSync(path.resolve('settings.html'), 'utf8');
      assert.ok(html.includes('id="tab-desktop-app"'), 'Must contain Desktop & Background category tab');
      assert.ok(html.includes('id="pane-desktop-app"'), 'Must contain Desktop & Background category pane');
      assert.ok(html.includes('id="desk-cfg-minimize-to-tray"'), 'Must have minimize-to-tray toggle');
      assert.ok(html.includes('id="desk-cfg-start-minimized"'), 'Must have start-minimized toggle');
      assert.ok(html.includes('id="desk-cfg-launch-on-startup"'), 'Must have launch-on-startup toggle');
      assert.ok(html.includes('id="desk-cfg-start-background-services"'), 'Must have start-background-services toggle');
      assert.ok(html.includes('id="desk-cfg-desktop-notifications"'), 'Must have desktop-notifications toggle');
      assert.ok(html.includes('id="desk-cfg-global-shortcut"'), 'Must have global shortcut input');
      assert.ok(html.includes('initDesktopSettings'), 'Must call initDesktopSettings');
      assert.ok(html.includes('applyGlobalShortcut'), 'Must handle applyGlobalShortcut');
    });

    test('assistant.html contains desktop minimize action and backend connection indicators', () => {
      const html = fs.readFileSync(path.resolve('assistant.html'), 'utf8');
      assert.ok(html.includes('id="btn-desktop-minimize"'), 'Must have desktop minimize button');
      assert.ok(html.includes('id="nav-desktop-settings"'), 'Must have desktop mode navigation item');
      assert.ok(html.includes('id="backend-connection-banner"'), 'Must have backend connection alert banner');
      assert.ok(html.includes('initDesktopFeatures'), 'Must call initDesktopFeatures');
      assert.ok(html.includes('minimizeToTrayAction'), 'Must have minimizeToTrayAction handler');
    });
  });

  describe('Background Wake-Word Detection IPC & Desktop Supervision', () => {
    test('preload.cjs exposes background wake-word API without leaking ipcRenderer', () => {
      const preloadCode = fs.readFileSync(path.resolve('desktop/preload.cjs'), 'utf8');
      assert.ok(preloadCode.includes('onWakeWordDetected'), 'Must expose onWakeWordDetected');
      assert.ok(preloadCode.includes("ipcRenderer.on('desktop:wake-word-detected'"), 'Must bind desktop:wake-word-detected IPC channel');
    });

    test('service-manager.cjs implements loopback wake listener and tracks wakeWord status', () => {
      const smCode = fs.readFileSync(path.resolve('desktop/service-manager.cjs'), 'utf8');
      assert.ok(smCode.includes('startWakeListener(port = 8003)'), 'Must define startWakeListener on port 8003');
      assert.ok(smCode.includes("wakeWord: 'offline'"), 'Must track wakeWord status');
      assert.ok(smCode.includes('this.wakeServer.close'), 'Must cleanly close wakeServer on shutdown');
      assert.ok(smCode.includes("emit('wake-word-detected'"), 'Must emit wake-word-detected event');
    });

    test('desktop/main.cjs wires background wake-word restoration to renderer', () => {
      const mainCode = fs.readFileSync(path.resolve('desktop/main.cjs'), 'utf8');
      assert.ok(mainCode.includes("serviceManager.on('wake-word-detected'"), 'Must listen for wake-word-detected event');
      assert.ok(mainCode.includes("windowManager.mainWindow.show()"), 'Must restore window if hidden');
      assert.ok(mainCode.includes("windowManager.mainWindow.restore()"), 'Must restore window if minimized');
      assert.ok(mainCode.includes("webContents.send('desktop:wake-word-detected'"), 'Must send IPC event to renderer');
    });

    test('assistant.html binds desktop wake listener and maintains truthful mic status', () => {
      const html = fs.readFileSync(path.resolve('assistant.html'), 'utf8');
      assert.ok(html.includes('jarvisDesktop.onWakeWordDetected'), 'Must subscribe to onWakeWordDetected');
      assert.ok(html.includes('notifyLocalAgentWakePause'), 'Must implement echo-isolation pause/resume during speech');
      assert.ok(html.includes('WAKE WORD: READY'), 'Must display READY state when background listener is active');
      assert.ok(html.includes('WAKE WORD: NO MIC'), 'Must display NO MIC state when microphone is absent');
      assert.ok(html.includes('WAKE WORD: OFF'), 'Must display OFF state when listener is disabled');
    });
  });
});

