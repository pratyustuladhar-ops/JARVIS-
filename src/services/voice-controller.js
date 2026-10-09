/**
 * JARVIS Voice State Manager & Hands-Free Wake-Word Controller
 * Implements a robust state machine, session token invalidation, bounded backoff retry,
 * microphone permission handling, and TTS acoustic isolation.
 */

export const WakeWordState = {
  DISABLED: 'DISABLED',
  REQUESTING_PERMISSION: 'REQUESTING_PERMISSION',
  STARTING: 'STARTING',
  LISTENING_FOR_WAKE_WORD: 'LISTENING_FOR_WAKE_WORD',
  WAKE_WORD_DETECTED: 'WAKE_WORD_DETECTED',
  LISTENING_FOR_COMMAND: 'LISTENING_FOR_COMMAND',
  PROCESSING_COMMAND: 'PROCESSING_COMMAND',
  RESPONDING: 'RESPONDING',
  RESTARTING: 'RESTARTING',
  ERROR: 'ERROR'
};

export class WakeWordController {
  constructor(options = {}) {
    this.options = {
      wakePhrase: 'Hey JARVIS',
      wakeAcknowledgment: 'Yes?',
      commandTimeoutMs: 8000,
      maxRetries: 5,
      baseBackoffMs: 500,
      maxBackoffMs: 4000,
      onStateChange: () => {},
      onWakeDetected: () => {},
      onCommandReceived: () => {},
      onError: () => {},
      SpeechRecognition: options.SpeechRecognition || null,
      ...options
    };

    this.state = WakeWordState.DISABLED;
    this.enabled = false;
    this.sessionId = 0;
    this.retryAttempts = 0;

    this.recognition = null;
    this.restartTimer = null;
    this.commandTimer = null;
    this.ttsGuardTimer = null;

    this.isSpeaking = false;
    this.isPausedForManualMic = false;
    this.lastError = null;

    // Load persisted enabled setting if available in browser
    if (typeof window !== 'undefined' && window.localStorage) {
      const saved = window.localStorage.getItem('jarvis_wake_word_enabled');
      if (saved === 'true') {
        this.enabled = true;
      } else if (saved === 'false') {
        this.enabled = false;
      }
    }
  }

  getState() {
    return this.state;
  }

  isEnabled() {
    return this.enabled;
  }

  getLastError() {
    return this.lastError;
  }

  setState(newState, detail = null) {
    const prevState = this.state;
    this.state = newState;
    if (this.options.onStateChange) {
      this.options.onStateChange(newState, prevState, detail);
    }
  }

  /**
   * Check if the browser supports Speech Recognition.
   */
  isSupported() {
    if (this.options.SpeechRecognition) return true;
    if (typeof window !== 'undefined') {
      return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
    }
    return false;
  }

  /**
   * Enable hands-free wake word listening.
   */
  async enable() {
    this.enabled = true;
    this.persistPreference(true);
    this.retryAttempts = 0;
    this.lastError = null;

    return this.startSession();
  }

  /**
   * Disable hands-free wake word listening.
   * Completely tears down current session, clears all pending timers, and prevents zombie restarts.
   */
  disable() {
    this.enabled = false;
    this.persistPreference(false);
    this.sessionId++; // Invalidate any in-flight callbacks or timers
    this.clearAllTimers();

    if (this.recognition) {
      try {
        this.recognition.onstart = null;
        this.recognition.onresult = null;
        this.recognition.onerror = null;
        this.recognition.onend = null;
        this.recognition.abort();
      } catch (e) {
        // Safe to ignore abort errors during shutdown
      }
      this.recognition = null;
    }

    this.setState(WakeWordState.DISABLED);
    return true;
  }

  /**
   * Toggle wake-word listening on or off.
   */
  async toggle() {
    if (this.enabled) {
      this.disable();
      return false;
    } else {
      await this.enable();
      return true;
    }
  }

  /**
   * Start a fresh, valid recognition session with a unique session ID.
   */
  async startSession() {
    // 1. Invalidate previous session and clear timers
    const session = ++this.sessionId;
    this.clearAllTimers();

    // 2. Check browser support
    if (!this.isSupported()) {
      this.lastError = "Speech Recognition API not supported in this browser. Please use Google Chrome or Microsoft Edge.";
      this.setState(WakeWordState.ERROR, this.lastError);
      if (this.options.onError) this.options.onError(this.lastError);
      return false;
    }

    // 3. Request / check microphone permission
    this.setState(WakeWordState.STARTING);

    const SpeechRecognition = this.options.SpeechRecognition ||
      (typeof window !== 'undefined' ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null);

    if (!SpeechRecognition) {
      this.lastError = "SpeechRecognition constructor unavailable.";
      this.setState(WakeWordState.ERROR, this.lastError);
      return false;
    }

    // Clean up any stale recognition instance
    if (this.recognition) {
      try {
        this.recognition.onstart = null;
        this.recognition.onresult = null;
        this.recognition.onerror = null;
        this.recognition.onend = null;
        this.recognition.abort();
      } catch (e) {}
      this.recognition = null;
    }

    try {
      const rec = new SpeechRecognition();
      rec.continuous = true;
      rec.interimResults = true;
      rec.lang = 'en-US';

      rec.onstart = () => {
        // If this callback belongs to an old session or disabled state, abort
        if (session !== this.sessionId || !this.enabled) {
          try { rec.abort(); } catch (e) {}
          return;
        }

        this.retryAttempts = 0;
        this.lastError = null;
        if (!this.isSpeaking && !this.isPausedForManualMic) {
          this.setState(WakeWordState.LISTENING_FOR_WAKE_WORD);
        }
      };

      rec.onresult = (event) => {
        if (session !== this.sessionId || !this.enabled) return;
        if (this.isSpeaking || this.isPausedForManualMic) return;

        let interim = '';
        let final = '';

        for (let i = event.resultIndex; i < event.results.length; ++i) {
          const item = event.results[i];
          if (item.isFinal) {
            final += item[0].transcript;
          } else {
            interim += item[0].transcript;
          }
        }

        const transcript = (final || interim).trim();
        if (!transcript) return;

        // If we are actively listening for a command following wake-word detection
        if (this.state === WakeWordState.LISTENING_FOR_COMMAND) {
          if (final.trim()) {
            this.clearTimer('commandTimer');
            this.setState(WakeWordState.PROCESSING_COMMAND);
            if (this.options.onCommandReceived) {
              this.options.onCommandReceived(final.trim());
            }
          }
          return;
        }

        // If we are listening for the wake word
        if (this.state === WakeWordState.LISTENING_FOR_WAKE_WORD) {
          const normalized = transcript.toLowerCase();
          const target = (this.options.wakePhrase || 'Hey JARVIS').toLowerCase();
          
          // Match "Hey JARVIS", "JARVIS", "OK JARVIS", "Hi JARVIS"
          const matched = normalized.includes(target) || /\b(?:hey\s+|hi\s+|ok\s+)?jarvis\b/i.test(normalized);

          if (matched) {
            // Check if user spoke a trailing command in the same breath (e.g., "Hey JARVIS open Chrome")
            const trailing = normalized.replace(/.*?\bjarvis\b[\s,.]*/i, '').trim();

            this.setState(WakeWordState.WAKE_WORD_DETECTED);
            if (this.options.onWakeDetected) {
              this.options.onWakeDetected(trailing);
            }

            if (trailing) {
              // Direct command execution
              this.setState(WakeWordState.PROCESSING_COMMAND);
              if (this.options.onCommandReceived) {
                this.options.onCommandReceived(trailing);
              }
            } else {
              // Await command in next speech window
              this.startCommandWindow(session);
            }
          }
        }
      };

      rec.onerror = (event) => {
        if (session !== this.sessionId || !this.enabled) return;

        const err = event.error;
        if (err === 'not-allowed' || err === 'service-not-allowed') {
          // Microphone permission was denied
          this.lastError = "Microphone permission denied. Please allow microphone access in browser settings.";
          this.enabled = false;
          this.persistPreference(false);
          this.setState(WakeWordState.ERROR, this.lastError);
          if (this.options.onError) this.options.onError(this.lastError);
          return;
        }

        if (err === 'no-speech') {
          // Normal silence, let onend handle bounded restart
          return;
        }

        this.lastError = `Speech recognition error: ${err}`;
      };

      rec.onend = () => {
        // If disabled or superseded by a newer session, do not restart
        if (session !== this.sessionId || !this.enabled) {
          return;
        }

        // Do not auto-restart if manual mic is using audio
        if (this.isPausedForManualMic) {
          return;
        }

        // Controlled bounded retry with exponential backoff
        this.scheduleRestart(session);
      };

      this.recognition = rec;
      rec.start();
      return true;

    } catch (err) {
      if (session === this.sessionId && this.enabled) {
        this.lastError = err.message || "Failed to start speech recognition.";
        this.scheduleRestart(session);
      }
      return false;
    }
  }

  /**
   * Schedule a controlled restart after recognition ends or drops.
   */
  scheduleRestart(session) {
    if (session !== this.sessionId || !this.enabled) return;

    if (this.retryAttempts >= this.options.maxRetries) {
      this.lastError = "Voice connection interrupted. Click WAKE WORD to reconnect.";
      this.setState(WakeWordState.ERROR, this.lastError);
      if (this.options.onError) this.options.onError(this.lastError);
      return;
    }

    this.setState(WakeWordState.RESTARTING);
    const delay = Math.min(
      this.options.baseBackoffMs * Math.pow(1.5, this.retryAttempts),
      this.options.maxBackoffMs
    );
    this.retryAttempts++;

    this.restartTimer = setTimeout(() => {
      if (session === this.sessionId && this.enabled && !this.isPausedForManualMic) {
        this.startSession();
      }
    }, delay);
  }

  /**
   * Start a dedicated time window to listen for the user's voice command.
   */
  startCommandWindow(session) {
    this.setState(WakeWordState.LISTENING_FOR_COMMAND);
    this.clearTimer('commandTimer');

    this.commandTimer = setTimeout(() => {
      if (session === this.sessionId && this.state === WakeWordState.LISTENING_FOR_COMMAND) {
        // Command window timed out, return to wake word listening
        this.setState(WakeWordState.LISTENING_FOR_WAKE_WORD);
      }
    }, this.options.commandTimeoutMs);
  }

  /**
   * Acoustic isolation: notify controller that JARVIS TTS speech has begun.
   */
  notifySpeakingStart() {
    this.isSpeaking = true;
    this.clearTimer('ttsGuardTimer');
    if (this.enabled && this.state !== WakeWordState.DISABLED) {
      this.setState(WakeWordState.RESPONDING);
    }
  }

  /**
   * Acoustic isolation: notify controller that JARVIS TTS speech has finished.
   */
  notifySpeakingEnd() {
    this.isSpeaking = false;
    this.clearTimer('ttsGuardTimer');

    // Add a 300ms guard period to prevent speaker echo feedback
    this.ttsGuardTimer = setTimeout(() => {
      if (this.enabled && this.state === WakeWordState.RESPONDING && !this.isPausedForManualMic) {
        this.setState(WakeWordState.LISTENING_FOR_WAKE_WORD);
      }
    }, 350);
  }

  /**
   * Pause wake detector when manual push-to-talk mic is clicked.
   */
  pauseForManualMic() {
    this.isPausedForManualMic = true;
    this.clearAllTimers();
    if (this.recognition) {
      try {
        this.recognition.abort();
      } catch (e) {}
    }
  }

  /**
   * Resume wake detector when manual push-to-talk mic finishes.
   */
  resumeFromManualMic() {
    this.isPausedForManualMic = false;
    if (this.enabled) {
      this.startSession();
    }
  }

  clearTimer(timerName) {
    if (this[timerName]) {
      clearTimeout(this[timerName]);
      this[timerName] = null;
    }
  }

  clearAllTimers() {
    this.clearTimer('restartTimer');
    this.clearTimer('commandTimer');
    this.clearTimer('ttsGuardTimer');
  }

  persistPreference(val) {
    if (typeof window !== 'undefined' && window.localStorage) {
      try {
        window.localStorage.setItem('jarvis_wake_word_enabled', val ? 'true' : 'false');
      } catch (e) {}
    }
  }
}
