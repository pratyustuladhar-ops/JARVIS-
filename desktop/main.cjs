const { app, ipcMain, globalShortcut, shell, Notification } = require('electron');
const path = require('path');
const { SettingsStore } = require('./settings-store.cjs');
const { ServiceManager } = require('./service-manager.cjs');
const { WindowManager } = require('./window-manager.cjs');
const { TrayManager } = require('./tray-manager.cjs');
const { StartupManager } = require('./startup-manager.cjs');

// Prevent multiple instances
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  console.log('[JARVIS] Another instance is already running. Exiting.');
  app.quit();
  process.exit(0);
}

// Instantiate core modules
const settingsStore = new SettingsStore();
const startupManager = new StartupManager();
const serviceManager = new ServiceManager({
  repoRoot: path.resolve(__dirname, '..'),
  backendUrl: settingsStore.get('backendUrl'),
  localAgentUrl: settingsStore.get('localAgentUrl')
});

let windowManager = null;
let trayManager = null;
let currentRegisteredShortcut = null;

function registerGlobalShortcut(shortcutKey) {
  if (currentRegisteredShortcut) {
    try {
      globalShortcut.unregister(currentRegisteredShortcut);
    } catch {
      // ignore
    }
    currentRegisteredShortcut = null;
  }

  if (!shortcutKey || typeof shortcutKey !== 'string') return false;

  try {
    const success = globalShortcut.register(shortcutKey, () => {
      if (windowManager) {
        windowManager.toggle();
      }
    });

    if (success) {
      currentRegisteredShortcut = shortcutKey;
      console.log(`[JARVIS] Registered global shortcut: ${shortcutKey}`);
      return true;
    } else {
      console.warn(`[JARVIS] Failed to register global shortcut or conflict detected: ${shortcutKey}`);
      return false;
    }
  } catch (err) {
    console.error(`[JARVIS] Error registering shortcut ${shortcutKey}:`, err.message);
    return false;
  }
}

function updateWindowsLoginItem(enable) {
  try {
    if (enable) {
      const res = startupManager.enableStartup();
      return res.success;
    } else {
      const res = startupManager.disableStartup();
      return res.success;
    }
  } catch (err) {
    console.error('[JARVIS] Failed to set login item settings:', err.message);
    return false;
  }
}

// App lifecycle
app.on('second-instance', () => {
  if (windowManager) {
    windowManager.showAssistant();
  }
});

app.whenReady().then(async () => {
  console.log('[JARVIS] Starting Windows Desktop Application...');

  // 1. Initialize Window Manager
  windowManager = new WindowManager({
    settingsStore,
    getTrayManager: () => trayManager
  });
  const mainWindow = windowManager.createMainWindow();

  // 2. Initialize System Tray
  trayManager = new TrayManager({
    getMainWindow: () => windowManager.mainWindow,
    toggleWindow: () => windowManager.toggle(),
    showAssistant: () => windowManager.showAssistant(),
    showSettings: () => windowManager.showSettings(),
    quitApp: () => {
      windowManager.setQuitting();
      app.quit();
    },
    refreshHealth: async () => {
      const status = await serviceManager.checkAll();
      if (trayManager) trayManager.updateContextMenu();
      if (windowManager && windowManager.mainWindow && !windowManager.mainWindow.isDestroyed()) {
        windowManager.mainWindow.webContents.send('desktop:service-status-changed', status);
      }
    },
    settingsStore,
    serviceManager
  });
  trayManager.init();

  // 3. Register Global Shortcut
  const currentShortcut = settingsStore.get('globalShortcut');
  registerGlobalShortcut(currentShortcut);

  // 4. Update Windows startup preference
  const launchOnStartup = settingsStore.get('launchOnStartup');
  updateWindowsLoginItem(launchOnStartup);

  // 5. Connect service manager events
  serviceManager.on('status-change', (status) => {
    if (trayManager) trayManager.updateContextMenu();
    if (windowManager && windowManager.mainWindow && !windowManager.mainWindow.isDestroyed()) {
      windowManager.mainWindow.webContents.send('desktop:service-status-changed', status);
    }
  });

  // Start background wake-word listener on loopback port 8003
  serviceManager.startWakeListener(8003);
  serviceManager.on('wake-word-detected', (data) => {
    console.log('[JARVIS] Background wake word event received:', (data && data.wake_phrase) || 'Hey JARVIS');
    if (windowManager && windowManager.mainWindow && !windowManager.mainWindow.isDestroyed()) {
      if (!windowManager.mainWindow.isVisible()) {
        windowManager.mainWindow.show();
      }
      if (windowManager.mainWindow.isMinimized()) {
        windowManager.mainWindow.restore();
      }
      windowManager.mainWindow.focus();
      windowManager.mainWindow.webContents.send('desktop:wake-word-detected', data);
    }
  });

  // 6. Start Background Services if configured
  const settings = settingsStore.getAll();
  if (settings.startBackgroundServices) {
    try {
      console.log('[JARVIS] Checking and starting background services...');
      await serviceManager.startBackend({ waitForReady: true, timeoutMs: 15000 });
      await serviceManager.startLocalAgent({ waitForReady: true, timeoutMs: 10000 });
      console.log('[JARVIS] Background services online and verified.');
    } catch (err) {
      console.warn('[JARVIS] Note during background service startup:', err.message);
    }
  }

  // 7. Initial health check and start polling
  await serviceManager.checkAll();
  serviceManager.startPolling(4000);
});

// Setup IPC handlers
ipcMain.handle('desktop:get-settings', async () => {
  const current = settingsStore.getAll();
  const startupStatus = startupManager.getStartupStatus();
  return {
    ...current,
    osLoginItemEnabled: startupStatus.enabled,
    startupStatus
  };
});

ipcMain.handle('desktop:update-settings', async (_event, partial) => {
  if (!partial || typeof partial !== 'object') {
    throw new Error('Invalid settings object');
  }

  // Handle shortcut update
  let shortcutRegistered = true;
  if (typeof partial.globalShortcut === 'string') {
    shortcutRegistered = registerGlobalShortcut(partial.globalShortcut);
    if (!shortcutRegistered) {
      // Revert or keep current shortcut
      partial.globalShortcut = currentRegisteredShortcut || settingsStore.get('globalShortcut');
    }
  }

  // Handle login item update
  if (typeof partial.launchOnStartup === 'boolean') {
    updateWindowsLoginItem(partial.launchOnStartup);
  }

  const result = settingsStore.set(partial);

  // Update tray context menu with any updated URLs or options
  if (trayManager) {
    trayManager.updateContextMenu();
  }

  return {
    ...result,
    shortcutRegistered
  };
});

ipcMain.handle('desktop:get-service-status', async () => {
  return serviceManager.status;
});

ipcMain.handle('desktop:check-health', async () => {
  const res = await serviceManager.checkAll();
  if (trayManager) trayManager.updateContextMenu();
  return res;
});

ipcMain.handle('desktop:restart-services', async () => {
  await serviceManager.shutdownAll();
  const settings = settingsStore.getAll();
  if (settings.startBackgroundServices) {
    try {
      await serviceManager.startBackend({ waitForReady: true, timeoutMs: 15000 });
      await serviceManager.startLocalAgent({ waitForReady: true, timeoutMs: 10000 });
    } catch (err) {
      console.warn('[JARVIS] Note during background service restart:', err.message);
    }
  }
  const status = await serviceManager.checkAll();
  return status;
});

ipcMain.handle('desktop:open-control-panel', async () => {
  const settings = settingsStore.getAll();
  const url = settings.webControlPanelUrl || 'http://localhost:5173';
  await shell.openExternal(url);
  return { success: true, url };
});

ipcMain.handle('desktop:minimize-to-tray', async () => {
  if (windowManager && windowManager.mainWindow) {
    windowManager.mainWindow.hide();
    if (trayManager) {
      trayManager.notifyBackgroundMode();
    }
  }
  return { success: true };
});

ipcMain.handle('desktop:show-notification', async (_event, { title, body }) => {
  const settings = settingsStore.getAll();
  if (!settings.showDesktopNotifications) return { shown: false };

  if (Notification.isSupported()) {
    new Notification({
      title: title || 'JARVIS System',
      body: body || ''
    }).show();
    return { shown: true };
  }
  return { shown: false };
});

ipcMain.handle('desktop:quit-app', async () => {
  if (windowManager) {
    windowManager.setQuitting();
  }
  app.quit();
});

// App shutdown lifecycle with graceful async cleanup
let isQuittingCleanly = false;
app.on('before-quit', (event) => {
  if (isQuittingCleanly) {
    return;
  }
  event.preventDefault();
  if (windowManager) {
    windowManager.setQuitting();
  }
  try {
    globalShortcut.unregisterAll();
  } catch {}
  if (trayManager) {
    trayManager.destroy();
  }
  serviceManager.shutdownAll().finally(() => {
    isQuittingCleanly = true;
    app.quit();
  });
});

app.on('window-all-closed', () => {
  const settings = settingsStore.getAll();
  if (!settings.minimizeToTrayOnClose) {
    app.quit();
  }
});
