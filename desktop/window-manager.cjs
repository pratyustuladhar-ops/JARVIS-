const { BrowserWindow, shell, app } = require('electron');
const path = require('path');
const fs = require('fs');

class WindowManager {
  /**
   * @param {object} options
   * @param {object} options.settingsStore
   * @param {() => object} options.getTrayManager
   */
  constructor(options) {
    this.options = options;
    this.mainWindow = null;
    this.isQuitting = false;
  }

  createMainWindow() {
    const iconPath = path.join(__dirname, 'assets', 'icon.ico');

    this.mainWindow = new BrowserWindow({
      width: 1280,
      height: 860,
      minWidth: 960,
      minHeight: 650,
      title: 'JARVIS // Autonomous AI Personal Assistant',
      backgroundColor: '#06080C',
      icon: fs.existsSync(iconPath) ? iconPath : undefined,
      show: false, // will show when ready-to-show unless startMinimized
      webPreferences: {
        preload: path.join(__dirname, 'preload.cjs'),
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        webSecurity: true,
      }
    });

    // Remove default menu bar for sleek futuristic HUD app feel
    this.mainWindow.setMenuBarVisibility(false);

    // Load Assistant URL
    this.loadAssistantUrl();

    // Show when ready, unless startMinimized is configured
    this.mainWindow.once('ready-to-show', () => {
      const settings = this.options.settingsStore.getAll();
      if (!settings.startMinimized) {
        this.mainWindow.show();
        this.mainWindow.focus();
      }
    });

    // Intercept close event for Minimize to Tray
    this.mainWindow.on('close', (event) => {
      if (this.isQuitting) {
        return;
      }

      const settings = this.options.settingsStore.getAll();
      if (settings.minimizeToTrayOnClose) {
        event.preventDefault();
        this.mainWindow.hide();
        const tray = this.options.getTrayManager ? this.options.getTrayManager() : null;
        if (tray) {
          tray.notifyBackgroundMode();
          tray.updateContextMenu();
        }
      }
    });

    // Handle show / hide updates for tray
    this.mainWindow.on('show', () => {
      const tray = this.options.getTrayManager ? this.options.getTrayManager() : null;
      if (tray) tray.updateContextMenu();
    });

    this.mainWindow.on('hide', () => {
      const tray = this.options.getTrayManager ? this.options.getTrayManager() : null;
      if (tray) tray.updateContextMenu();
    });

    // Security: Restrict new windows and external links to system browser
    this.mainWindow.webContents.setWindowOpenHandler(({ url }) => {
      try {
        const parsed = new URL(url);
        if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
          shell.openExternal(url);
        }
      } catch (err) {
        console.warn('[WindowManager] Disallowed window open for URL:', url);
      }
      return { action: 'deny' };
    });

    // Security: Restrict in-window navigations to safe app routes
    this.mainWindow.webContents.on('will-navigate', (event, url) => {
      try {
        const parsed = new URL(url);
        const isLocalHost = parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1';
        const isFile = parsed.protocol === 'file:';
        if (!isLocalHost && !isFile) {
          event.preventDefault();
          shell.openExternal(url);
        }
      } catch {
        event.preventDefault();
      }
    });

    return this.mainWindow;
  }

  loadAssistantUrl() {
    const isDev = process.argv.includes('--dev') || process.env.NODE_ENV === 'development';
    const distAssistant = path.join(path.resolve(__dirname, '..'), 'dist', 'assistant.html');
    const rootAssistant = path.join(path.resolve(__dirname, '..'), 'assistant.html');

    if (isDev) {
      // In dev mode, attempt Vite dev server first
      this.mainWindow.loadURL('http://localhost:5173/assistant.html').catch(() => {
        // Fallback to local file if dev server is not running
        if (fs.existsSync(distAssistant)) {
          this.mainWindow.loadFile(distAssistant);
        } else {
          this.mainWindow.loadFile(rootAssistant);
        }
      });
    } else {
      // Production mode: load bundled HTML directly
      if (fs.existsSync(distAssistant)) {
        this.mainWindow.loadFile(distAssistant);
      } else {
        this.mainWindow.loadFile(rootAssistant);
      }
    }
  }

  toggle() {
    if (!this.mainWindow) return;
    if (this.mainWindow.isMinimized()) {
      this.mainWindow.restore();
      this.mainWindow.focus();
    } else if (this.mainWindow.isVisible()) {
      if (this.mainWindow.isFocused()) {
        this.mainWindow.hide();
      } else {
        this.mainWindow.focus();
      }
    } else {
      this.mainWindow.show();
      this.mainWindow.focus();
    }
  }

  showAssistant() {
    if (!this.mainWindow) return;
    this.loadAssistantUrl();
    if (this.mainWindow.isMinimized()) this.mainWindow.restore();
    this.mainWindow.show();
    this.mainWindow.focus();
  }

  showSettings() {
    if (!this.mainWindow) return;
    const isDev = process.argv.includes('--dev') || process.env.NODE_ENV === 'development';
    const distSettings = path.join(path.resolve(__dirname, '..'), 'dist', 'settings.html');
    const rootSettings = path.join(path.resolve(__dirname, '..'), 'settings.html');

    if (isDev) {
      this.mainWindow.loadURL('http://localhost:5173/settings.html?tab=desktop').catch(() => {
        this.mainWindow.loadFile(fs.existsSync(distSettings) ? distSettings : rootSettings, {
          query: { tab: 'desktop' }
        });
      });
    } else {
      this.mainWindow.loadFile(fs.existsSync(distSettings) ? distSettings : rootSettings, {
        query: { tab: 'desktop' }
      });
    }

    if (this.mainWindow.isMinimized()) this.mainWindow.restore();
    this.mainWindow.show();
    this.mainWindow.focus();
  }

  setQuitting() {
    this.isQuitting = true;
  }
}

module.exports = { WindowManager };
