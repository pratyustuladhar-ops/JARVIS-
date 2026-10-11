const { Tray, Menu, nativeImage, shell, Notification } = require('electron');
const path = require('path');

class TrayManager {
  /**
   * @param {object} options
   * @param {() => any} options.getMainWindow
   * @param {() => void} options.toggleWindow
   * @param {() => void} options.showAssistant
   * @param {() => void} options.showSettings
   * @param {() => void} options.quitApp
   * @param {() => Promise<void>} options.refreshHealth
   * @param {object} options.settingsStore
   * @param {object} options.serviceManager
   */
  constructor(options) {
    this.options = options;
    this.tray = null;
    this.hasNotifiedBackground = false;
  }

  getIcon() {
    const icoPath = path.join(__dirname, 'assets', 'icon.ico');
    const pngPath = path.join(__dirname, 'assets', 'tray-icon.png');
    try {
      if (process.platform === 'win32' && require('fs').existsSync(icoPath)) {
        return nativeImage.createFromPath(icoPath);
      }
      return nativeImage.createFromPath(pngPath);
    } catch {
      return nativeImage.createEmpty();
    }
  }

  init() {
    try {
      const icon = this.getIcon();
      this.tray = new Tray(icon);
      this.tray.setToolTip('JARVIS // Autonomous AI Personal Assistant');

      // Left click toggles window
      this.tray.on('click', () => {
        if (this.options.toggleWindow) {
          this.options.toggleWindow();
        }
      });

      // Double click shows and focuses
      this.tray.on('double-click', () => {
        if (this.options.showAssistant) {
          this.options.showAssistant();
        }
      });

      this.updateContextMenu();
      return true;
    } catch (err) {
      console.error('[TrayManager] Failed to initialize system tray:', err);
      return false;
    }
  }

  updateContextMenu() {
    if (!this.tray) return;

    const win = this.options.getMainWindow ? this.options.getMainWindow() : null;
    const isVisible = win && win.isVisible();

    const serviceStatus = this.options.serviceManager ? this.options.serviceManager.status : { backend: 'offline', localAgent: 'offline' };
    const backendLabel = `Backend Core: ${serviceStatus.backend.toUpperCase()}`;
    const agentLabel = `Local Agent: ${serviceStatus.localAgent.toUpperCase()}`;

    const contextMenu = Menu.buildFromTemplate([
      {
        label: 'JARVIS Assistant',
        icon: undefined,
        click: () => {
          if (this.options.showAssistant) this.options.showAssistant();
        }
      },
      {
        label: isVisible ? 'Hide JARVIS' : 'Show JARVIS',
        click: () => {
          if (this.options.toggleWindow) this.options.toggleWindow();
        }
      },
      { type: 'separator' },
      {
        label: backendLabel,
        enabled: true,
        click: () => {
          if (this.options.refreshHealth) this.options.refreshHealth();
        }
      },
      {
        label: agentLabel,
        enabled: true,
        click: () => {
          if (this.options.refreshHealth) this.options.refreshHealth();
        }
      },
      { type: 'separator' },
      {
        label: 'Open Web Control Panel',
        click: () => {
          const settings = this.options.settingsStore ? this.options.settingsStore.getAll() : {};
          const url = settings.webControlPanelUrl || 'http://localhost:5173';
          shell.openExternal(url);
        }
      },
      {
        label: 'Desktop Settings',
        click: () => {
          if (this.options.showSettings) this.options.showSettings();
        }
      },
      { type: 'separator' },
      {
        label: 'Quit JARVIS',
        click: () => {
          if (this.options.quitApp) this.options.quitApp();
        }
      }
    ]);

    this.tray.setContextMenu(contextMenu);
  }

  notifyBackgroundMode() {
    const settings = this.options.settingsStore ? this.options.settingsStore.getAll() : {};
    if (!settings.showDesktopNotifications) return;

    if (!this.hasNotifiedBackground) {
      this.hasNotifiedBackground = true;
      if (this.tray && process.platform === 'win32') {
        try {
          this.tray.displayBalloon({
            title: 'JARVIS Active in Background',
            content: 'JARVIS is minimized to the system tray. Click the tray icon or press Ctrl+Shift+J to open.',
            iconType: 'info'
          });
          return;
        } catch {
          // Fallback to Notification
        }
      }

      if (Notification.isSupported()) {
        new Notification({
          title: 'JARVIS Active in Background',
          body: 'JARVIS is minimized to the system tray. Click the tray icon to restore.'
        }).show();
      }
    }
  }

  destroy() {
    if (this.tray) {
      this.tray.destroy();
      this.tray = null;
    }
  }
}

module.exports = { TrayManager };
