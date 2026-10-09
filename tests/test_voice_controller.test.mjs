import { test, describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { WakeWordController, WakeWordState } from '../src/services/voice-controller.js';

// Mock SpeechRecognition for simulating browser events
class MockSpeechRecognition {
  constructor() {
    this.continuous = false;
    this.interimResults = false;
    this.lang = 'en-US';
    this.onstart = null;
    this.onresult = null;
    this.onerror = null;
    this.onend = null;
    this.isStarted = false;
    this.isAborted = false;
  }

  start() {
    this.isStarted = true;
    setTimeout(() => {
      if (this.onstart && !this.isAborted) {
        this.onstart();
      }
    }, 10);
  }

  abort() {
    this.isAborted = true;
    this.isStarted = false;
  }

  stop() {
    this.isStarted = false;
    setTimeout(() => {
      if (this.onend && !this.isAborted) {
        this.onend();
      }
    }, 10);
  }

  simulateResult(transcript, isFinal = true) {
    if (this.onresult && !this.isAborted) {
      this.onresult({
        resultIndex: 0,
        results: [
          [{ transcript }]
        ],
        isFinal
      });
    }
  }

  simulateError(errorType) {
    if (this.onerror && !this.isAborted) {
      this.onerror({ error: errorType });
    }
  }

  simulateEnd() {
    if (this.onend && !this.isAborted) {
      this.onend();
    }
  }
}

describe('WakeWordController State Machine & Lifecycle', () => {

  test('Initial state is DISABLED', () => {
    const controller = new WakeWordController({ SpeechRecognition: MockSpeechRecognition });
    assert.equal(controller.getState(), WakeWordState.DISABLED);
    assert.equal(controller.isEnabled(), false);
  });

  test('Enable starts fresh session and transitions to LISTENING_FOR_WAKE_WORD', async () => {
    let stateChanges = [];
    const controller = new WakeWordController({
      SpeechRecognition: MockSpeechRecognition,
      onStateChange: (state) => stateChanges.push(state)
    });

    await controller.enable();
    assert.equal(controller.isEnabled(), true);
    assert.ok(stateChanges.includes(WakeWordState.STARTING));

    // Wait for mock onstart to fire
    await new Promise((r) => setTimeout(r, 30));
    assert.equal(controller.getState(), WakeWordState.LISTENING_FOR_WAKE_WORD);
    assert.ok(controller.recognition instanceof MockSpeechRecognition);
  });

  test('Disable stops recognition, cancels timers, and sets state to DISABLED', async () => {
    const controller = new WakeWordController({ SpeechRecognition: MockSpeechRecognition });
    await controller.enable();
    await new Promise((r) => setTimeout(r, 20));

    const initialSession = controller.sessionId;
    const oldRec = controller.recognition;

    controller.disable();
    assert.equal(controller.isEnabled(), false);
    assert.equal(controller.getState(), WakeWordState.DISABLED);
    assert.ok(controller.sessionId > initialSession);
    assert.equal(controller.recognition, null);
    assert.equal(oldRec.isAborted, true);
  });

  test('Enable -> Disable -> Enable again reliably resumes fresh session without refresh', async () => {
    const controller = new WakeWordController({ SpeechRecognition: MockSpeechRecognition });

    // 1. Enable
    await controller.enable();
    await new Promise((r) => setTimeout(r, 20));
    assert.equal(controller.getState(), WakeWordState.LISTENING_FOR_WAKE_WORD);
    const session1 = controller.sessionId;

    // 2. Disable
    controller.disable();
    assert.equal(controller.getState(), WakeWordState.DISABLED);
    const session2 = controller.sessionId;

    // 3. Enable again
    await controller.enable();
    await new Promise((r) => setTimeout(r, 20));
    assert.equal(controller.getState(), WakeWordState.LISTENING_FOR_WAKE_WORD);
    const session3 = controller.sessionId;

    assert.ok(session3 > session2);
    assert.ok(session2 > session1);
    assert.ok(controller.recognition !== null);
  });

  test('Stale callbacks from an old session cannot overwrite current state', async () => {
    let oldRecognitionInstance = null;

    class CapturingMockRecognition extends MockSpeechRecognition {
      constructor() {
        super();
        oldRecognitionInstance = this;
      }
    }

    const controller = new WakeWordController({ SpeechRecognition: CapturingMockRecognition });
    await controller.enable();
    await new Promise((r) => setTimeout(r, 20));

    const staleInstance = oldRecognitionInstance;
    controller.disable();

    // Now staleInstance fires late onresult or onstart
    assert.equal(controller.getState(), WakeWordState.DISABLED);
    staleInstance.simulateResult('Hey JARVIS');
    assert.equal(controller.getState(), WakeWordState.DISABLED); // Must not change!
  });

  test('Unexpected termination triggers controlled backoff restart when enabled', async () => {
    let capturedState = null;
    const controller = new WakeWordController({
      SpeechRecognition: MockSpeechRecognition,
      baseBackoffMs: 20,
      onStateChange: (s) => { capturedState = s; }
    });

    await controller.enable();
    await new Promise((r) => setTimeout(r, 20));

    // Simulate unexpected termination
    controller.recognition.simulateEnd();
    assert.equal(controller.getState(), WakeWordState.RESTARTING);

    // Wait for restart timer to fire
    await new Promise((r) => setTimeout(r, 50));
    assert.equal(controller.getState(), WakeWordState.LISTENING_FOR_WAKE_WORD);
  });

  test('Disabling cancels pending restart behavior and prevents resurrection', async () => {
    const controller = new WakeWordController({
      SpeechRecognition: MockSpeechRecognition,
      baseBackoffMs: 80
    });

    await controller.enable();
    await new Promise((r) => setTimeout(r, 20));

    // Simulate end which schedules restart
    controller.recognition.simulateEnd();
    assert.equal(controller.getState(), WakeWordState.RESTARTING);

    // User explicitly turns it OFF during the restart window
    controller.disable();
    assert.equal(controller.getState(), WakeWordState.DISABLED);

    // Wait past the restart delay
    await new Promise((r) => setTimeout(r, 120));
    // Must remain DISABLED and not have auto-restarted
    assert.equal(controller.getState(), WakeWordState.DISABLED);
    assert.equal(controller.recognition, null);
  });

  test('Permission denial (not-allowed) transitions to ERROR and disables feature', async () => {
    let lastReportedError = null;
    const controller = new WakeWordController({
      SpeechRecognition: MockSpeechRecognition,
      onError: (err) => { lastReportedError = err; }
    });

    await controller.enable();
    await new Promise((r) => setTimeout(r, 20));

    controller.recognition.simulateError('not-allowed');
    assert.equal(controller.getState(), WakeWordState.ERROR);
    assert.equal(controller.isEnabled(), false);
    assert.ok(lastReportedError.includes('Microphone permission denied'));
  });

  test('Unsupported browser is handled gracefully', async () => {
    let reportedError = null;
    const controller = new WakeWordController({
      SpeechRecognition: null, // No Web Speech API
      onError: (err) => { reportedError = err; }
    });

    const success = await controller.enable();
    assert.equal(success, false);
    assert.equal(controller.getState(), WakeWordState.ERROR);
    assert.ok(reportedError.includes('not supported'));
  });

  test('TTS speech start and end acoustic isolation', async () => {
    const controller = new WakeWordController({ SpeechRecognition: MockSpeechRecognition });
    await controller.enable();
    await new Promise((r) => setTimeout(r, 20));

    assert.equal(controller.getState(), WakeWordState.LISTENING_FOR_WAKE_WORD);

    // TTS starts speaking
    controller.notifySpeakingStart();
    assert.equal(controller.getState(), WakeWordState.RESPONDING);

    // Result during speaking is ignored to avoid audio echo feedback
    let detected = false;
    controller.options.onWakeDetected = () => { detected = true; };
    controller.recognition.simulateResult('Hey JARVIS');
    assert.equal(detected, false);

    // TTS finishes speaking
    controller.notifySpeakingEnd();
    // Guard period
    await new Promise((r) => setTimeout(r, 400));
    assert.equal(controller.getState(), WakeWordState.LISTENING_FOR_WAKE_WORD);
  });

  test('Manual push-to-talk mic pauses and resumes wake detector cleanly', async () => {
    const controller = new WakeWordController({ SpeechRecognition: MockSpeechRecognition });
    await controller.enable();
    await new Promise((r) => setTimeout(r, 20));

    assert.equal(controller.getState(), WakeWordState.LISTENING_FOR_WAKE_WORD);

    // User clicks manual mic
    controller.pauseForManualMic();
    assert.equal(controller.isPausedForManualMic, true);

    // Manual mic completes
    controller.resumeFromManualMic();
    assert.equal(controller.isPausedForManualMic, false);
    await new Promise((r) => setTimeout(r, 20));
    assert.equal(controller.getState(), WakeWordState.LISTENING_FOR_WAKE_WORD);
  });

});
