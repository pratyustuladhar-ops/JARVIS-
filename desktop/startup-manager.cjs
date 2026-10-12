const { app } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawnSync } = require('child_process');

/**
 * Windows Per-User Startup Registration Manager for JARVIS.
 * Safely registers or removes launch-at-login entries using per-user HKCU registry
 * and per-user Startup folder shortcuts without requesting administrator privileges.
 */
class StartupManager {
  constructor(options = {}) {
    this.appName = options.appName || 'JARVIS';
    this.appData = options.appData || (app ? app.getPath('appData') : (process.env.APPDATA || ''));
    this.startupDir = options.startupDir || (this.appData
      ? path.join(this.appData, 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
      : null);
    this.shortcutPath = this.startupDir ? path.join(this.startupDir, `${this.appName}.lnk`) : null;
  }

  isPackaged() {
    return app ? app.isPackaged : false;
  }

  getTargetExecutablePath() {
    if (this.isPackaged()) {
      return process.execPath;
    }
    // In development mode, check if a packaged release build exists
    const candidateRelease = path.resolve(__dirname, '..', 'release-builds', 'JARVIS-win32-x64', 'JARVIS.exe');
    if (fs.existsSync(candidateRelease)) {
      return candidateRelease;
    }
    return null;
  }

  getStartupStatus() {
    let openAtLogin = false;
    let executable = null;
    let shortcutExists = false;

    if (this.shortcutPath && fs.existsSync(this.shortcutPath)) {
      shortcutExists = true;
    }

    try {
      if (app && typeof app.getLoginItemSettings === 'function') {
        const loginSettings = app.getLoginItemSettings();
        openAtLogin = !!loginSettings.openAtLogin;
        executable = loginSettings.executableWillLaunchAtLogin || null;
      }
    } catch {}

    const enabled = openAtLogin || shortcutExists;
    return {
      enabled,
      openAtLogin,
      shortcutExists,
      executable,
      isPackaged: this.isPackaged()
    };
  }

  enableStartup(options = {}) {
    const launchArgs = options.args || ['--minimized'];
    const targetPath = options.execPath || this.getTargetExecutablePath();

    if (!targetPath) {
      return {
        success: true,
        enabled: true,
        configured: false,
        note: 'Startup preference saved. Windows startup entry activates upon installing or packaging the standalone application.'
      };
    }

    try {
      // 1. Electron LoginItemSettings (HKCU Run registry key)
      if (app && typeof app.setLoginItemSettings === 'function') {
        app.setLoginItemSettings({
          openAtLogin: true,
          path: targetPath,
          args: launchArgs
        });
      }

      // 2. Per-user Startup folder shortcut
      this.createStartupShortcut(targetPath, launchArgs);

      return {
        success: true,
        enabled: true,
        targetPath,
        args: launchArgs
      };
    } catch (err) {
      return {
        success: false,
        error: err.message
      };
    }
  }

  disableStartup() {
    try {
      // 1. Remove Electron LoginItemSettings
      if (app && typeof app.setLoginItemSettings === 'function') {
        app.setLoginItemSettings({
          openAtLogin: false
        });
      }

      // 2. Remove Startup folder shortcut
      this.removeStartupShortcut();

      return {
        success: true,
        enabled: false
      };
    } catch (err) {
      return {
        success: false,
        error: err.message
      };
    }
  }

  createStartupShortcut(targetPath, args = ['--minimized']) {
    if (!this.shortcutPath || !this.startupDir) return false;
    try {
      if (!fs.existsSync(this.startupDir)) {
        fs.mkdirSync(this.startupDir, { recursive: true });
      }

      const argsStr = args.join(' ');
      const vbsScript = [
        'Set oWS = WScript.CreateObject("WScript.Shell")',
        `sLinkFile = "${this.shortcutPath.replace(/\\/g, '\\\\')}"`,
        'Set oLink = oWS.CreateShortcut(sLinkFile)',
        `oLink.TargetPath = "${targetPath.replace(/\\/g, '\\\\')}"`,
        `oLink.Arguments = "${argsStr}"`,
        'oLink.Description = "JARVIS Autonomous AI Assistant (Background Launch)"',
        `oLink.WorkingDirectory = "${path.dirname(targetPath).replace(/\\/g, '\\\\')}"`,
        'oLink.Save'
      ].join('\r\n');

      const tempVbs = path.join(this.appData || process.env.TEMP, `create_jarvis_shortcut_${Date.now()}.vbs`);
      fs.writeFileSync(tempVbs, vbsScript, 'utf8');
      try {
        spawnSync('cscript.exe', ['//nologo', tempVbs], { timeout: 4000 });
      } finally {
        try { fs.unlinkSync(tempVbs); } catch {}
      }
      return fs.existsSync(this.shortcutPath);
    } catch (err) {
      return false;
    }
  }

  removeStartupShortcut() {
    if (this.shortcutPath && fs.existsSync(this.shortcutPath)) {
      try {
        fs.unlinkSync(this.shortcutPath);
        return true;
      } catch {
        return false;
      }
    }
    return true;
  }
}

module.exports = { StartupManager };
