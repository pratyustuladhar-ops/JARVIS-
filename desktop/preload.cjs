const { contextBridge, ipcRenderer } = require('electron');

/**
 * JARVIS Desktop Preload Script
 * Exposes a strictly isolated and validated API surface to the renderer window.
 */
contextBridge.exposeInMainWorld('jarvisDesktop', {
  isDesktop: true,

  // Settings
  getSettings: () => ipcRenderer.invoke('desktop:get-settings'),
  updateSettings: (settings) => {
    if (typeof settings !== 'object' || settings === null) {
      return Promise.reject(new Error('Settings must be an object'));
    }
    return ipcRenderer.invoke('desktop:update-settings', settings);
  },

  // Service Lifecycle & Health
  getServiceStatus: () => ipcRenderer.invoke('desktop:get-service-status'),
  checkHealth: () => ipcRenderer.invoke('desktop:check-health'),
  restartServices: () => ipcRenderer.invoke('desktop:restart-services'),

  // Desktop Controls
  openControlPanel: () => ipcRenderer.invoke('desktop:open-control-panel'),
  minimizeToTray: () => ipcRenderer.invoke('desktop:minimize-to-tray'),
  showNotification: (options) => {
    const opts = typeof options === 'string' ? { title: 'JARVIS', body: options } : (options || {});
    return ipcRenderer.invoke('desktop:show-notification', opts);
  },
  quitApp: () => ipcRenderer.invoke('desktop:quit-app'),

  // Event Subscriptions
  onServiceStatusChanged: (callback) => {
    if (typeof callback !== 'function') return () => {};
    const listener = (_event, data) => callback(data);
    ipcRenderer.on('desktop:service-status-changed', listener);
    return () => {
      ipcRenderer.removeListener('desktop:service-status-changed', listener);
    };
  },

  onWakeWordDetected: (callback) => {
    if (typeof callback !== 'function') return () => {};
    const listener = (_event, data) => callback(data);
    ipcRenderer.on('desktop:wake-word-detected', listener);
    return () => {
      ipcRenderer.removeListener('desktop:wake-word-detected', listener);
    };
  }
});
