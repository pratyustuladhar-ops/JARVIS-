const fs = require('fs');
const path = require('path');

const DEFAULT_SETTINGS = {
  startMinimized: false,
  minimizeToTrayOnClose: true,
  launchOnStartup: false,
  startBackgroundServices: true,
  showDesktopNotifications: true,
  globalShortcut: 'CommandOrControl+Shift+J',
  backendUrl: 'http://127.0.0.1:8000',
  localAgentUrl: 'http://127.0.0.1:8001',
  webControlPanelUrl: 'http://localhost:5173',
};

class SettingsStore {
  /**
   * @param {string} [storagePath] Optional explicit path for testing or override
   */
  constructor(storagePath = null) {
    this.storagePath = storagePath;
    this.settings = { ...DEFAULT_SETTINGS };
    this.init();
  }

  init() {
    if (!this.storagePath) {
      try {
        const { app } = require('electron');
        if (app && typeof app.getPath === 'function') {
          const userDataDir = app.getPath('userData');
          this.storagePath = path.join(userDataDir, 'jarvis-desktop-settings.json');
        }
      } catch (e) {
        // Fallback for test / headless runner
        this.storagePath = path.join(process.cwd(), '.desktop-settings.json');
      }
    }

    this.load();
  }

  load() {
    try {
      if (this.storagePath && fs.existsSync(this.storagePath)) {
        const raw = fs.readFileSync(this.storagePath, 'utf8');
        const parsed = JSON.parse(raw);
        this.settings = { ...DEFAULT_SETTINGS, ...parsed };
      }
    } catch (err) {
      console.warn('[SettingsStore] Failed to load settings from disk, using defaults:', err.message);
      this.settings = { ...DEFAULT_SETTINGS };
    }
  }

  save() {
    try {
      if (!this.storagePath) return false;
      const dir = path.dirname(this.storagePath);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      fs.writeFileSync(this.storagePath, JSON.stringify(this.settings, null, 2), 'utf8');
      return true;
    } catch (err) {
      console.error('[SettingsStore] Failed to save settings to disk:', err.message);
      return false;
    }
  }

  getAll() {
    return { ...this.settings };
  }

  get(key) {
    return this.settings[key];
  }

  set(partial) {
    if (!partial || typeof partial !== 'object') {
      throw new Error('Settings update must be an object');
    }

    // Sanitize and validate known fields
    const updated = { ...this.settings };
    if (typeof partial.startMinimized === 'boolean') {
      updated.startMinimized = partial.startMinimized;
    }
    if (typeof partial.minimizeToTrayOnClose === 'boolean') {
      updated.minimizeToTrayOnClose = partial.minimizeToTrayOnClose;
    }
    if (typeof partial.launchOnStartup === 'boolean') {
      updated.launchOnStartup = partial.launchOnStartup;
    }
    if (typeof partial.startBackgroundServices === 'boolean') {
      updated.startBackgroundServices = partial.startBackgroundServices;
    }
    if (typeof partial.showDesktopNotifications === 'boolean') {
      updated.showDesktopNotifications = partial.showDesktopNotifications;
    }
    if (typeof partial.globalShortcut === 'string' && partial.globalShortcut.trim()) {
      updated.globalShortcut = partial.globalShortcut.trim();
    }
    if (typeof partial.backendUrl === 'string' && partial.backendUrl.startsWith('http')) {
      updated.backendUrl = partial.backendUrl.trim();
    }
    if (typeof partial.localAgentUrl === 'string' && partial.localAgentUrl.startsWith('http')) {
      updated.localAgentUrl = partial.localAgentUrl.trim();
    }
    if (typeof partial.webControlPanelUrl === 'string' && partial.webControlPanelUrl.startsWith('http')) {
      updated.webControlPanelUrl = partial.webControlPanelUrl.trim();
    }

    this.settings = updated;
    const saved = this.save();
    return { success: saved, settings: { ...this.settings } };
  }

  reset() {
    this.settings = { ...DEFAULT_SETTINGS };
    this.save();
    return { ...this.settings };
  }
}

module.exports = { SettingsStore, DEFAULT_SETTINGS };
