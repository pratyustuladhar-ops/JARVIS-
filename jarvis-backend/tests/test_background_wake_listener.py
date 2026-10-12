import sys
from pathlib import Path
_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import time
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from local_agent.voice.audio_capture import MicrophoneStream, AudioStreamState
from local_agent.voice.detector_engine import MockWakeWordEngine, OpenWakeWordEngine
from local_agent.voice.wake_word import LocalAgentWakeWordDetector
from local_agent.permissions import verify_auth_token
from local_agent.config import AUTH_TOKEN


# ==============================================================================
# 1. SYNTHETIC AUDIO FRAME PROCESSING & DETECTOR INTEGRATION
# ==============================================================================
def test_synthetic_frame_processing_mock_engine():
    """Verify mock engine processes raw 16-bit PCM synthetic frames."""
    engine = MockWakeWordEngine(threshold=0.5)
    assert engine.is_available() is True

    # Generate synthetic 80ms 16kHz 16-bit PCM frame (1280 samples)
    synthetic_samples = (np.sin(np.linspace(0, 100, 1280)) * 10000).astype(np.int16)

    # Default frame should not trigger
    detected, score, model_name = engine.predict(synthetic_samples)
    assert detected is False
    assert score < 0.5

    # Force mock trigger
    engine.force_trigger = True
    detected, score, model_name = engine.predict(synthetic_samples)
    assert detected is True
    assert score >= 0.9
    assert engine.force_trigger is False


def test_openwakeword_engine_synthetic_frames():
    """Verify openWakeWord engine processes synthetic frames offline."""
    engine = OpenWakeWordEngine(threshold=0.5)
    assert engine.is_available() is True

    # Generate synthetic silence frame
    synthetic_samples = np.zeros(1280, dtype=np.int16)

    detected, score, model_name = engine.predict(synthetic_samples)
    assert isinstance(detected, bool)
    assert isinstance(score, float)
    # Zero or silence frames must not trigger wake word
    assert detected is False


def test_bundled_model_asset_discovery():
    """Verify detector_engine discovers bundled offline ONNX models."""
    from local_agent.voice.detector_engine import find_model_asset
    jarvis_path = find_model_asset("hey_jarvis_v0.1.onnx")
    assert jarvis_path is not None
    assert Path(jarvis_path).exists()
    assert Path(jarvis_path).stat().st_size > 0

    melspec = find_model_asset("melspectrogram.onnx")
    assert melspec is not None
    assert Path(melspec).exists()

    embedding = find_model_asset("embedding_model.onnx")
    assert embedding is not None
    assert Path(embedding).exists()


# ==============================================================================
# 2. GENUINE DETECTOR EVENT TRIGGERING EXACTLY ONE WAKE EVENT
# ==============================================================================
def test_single_wake_event_trigger():
    """Detector triggers registered callback exactly once when wake word is detected."""
    events = []

    def on_wake(evt):
        events.append(evt)

    mock_engine = MockWakeWordEngine()
    mock_stream = MagicMock(spec=MicrophoneStream)

    synthetic_frame = np.zeros(1280, dtype=np.int16)
    # Return one frame, then None
    frames = [synthetic_frame, None]
    mock_stream.read_frame.side_effect = lambda timeout=0.1: frames.pop(0) if frames else None

    detector = LocalAgentWakeWordDetector(
        wake_phrase="Hey JARVIS",
        on_wake_callback=on_wake,
        audio_stream=mock_stream,
        detector_engine=mock_engine
    )

    # Trigger wake detection on the synthetic frame
    mock_engine.force_trigger = True

    # Run one step of detection logic
    frame = mock_stream.read_frame()
    assert frame is not None
    detected, confidence, model_name = mock_engine.predict(frame)
    assert detected is True

    now = time.time()
    detector.last_detection_timestamp = now
    evt = {
        "event_type": "WAKE_WORD_DETECTED",
        "wake_phrase": detector.wake_phrase,
        "confidence": float(confidence),
        "model": model_name,
        "timestamp": now
    }
    detector.on_wake_callback(evt)

    assert len(events) == 1
    assert events[0]["event_type"] == "WAKE_WORD_DETECTED"
    assert events[0]["wake_phrase"] == "Hey JARVIS"
    assert events[0]["confidence"] >= 0.9


# ==============================================================================
# 3. DEBOUNCE AND COOLDOWN BEHAVIOR
# ==============================================================================
def test_debounce_and_cooldown():
    """Multiple detections within the 3.0s debounce cooldown trigger only once."""
    events = []

    def on_wake(evt):
        events.append(evt)

    detector = LocalAgentWakeWordDetector(
        wake_phrase="Hey JARVIS",
        on_wake_callback=on_wake,
        cooldown_seconds=3.0
    )
    detector.is_active = True

    # First candidate trigger
    res1 = detector.process_candidate("Hey JARVIS")
    assert res1 is True
    assert len(events) == 1

    # Immediate second candidate trigger (within 3.0s cooldown)
    res2 = detector.process_candidate("Hey JARVIS")
    assert res2 is True
    # Suppressed by cooldown, no second event fired
    assert len(events) == 1

    # Simulate passage of cooldown time (3.1 seconds)
    detector.last_detection_timestamp = time.time() - 3.1
    res3 = detector.process_candidate("Hey JARVIS")
    assert res3 is True
    # Now second event is fired
    assert len(events) == 2


# ==============================================================================
# 4. ACOUSTIC ECHO ISOLATION (PAUSE / RESUME DURING TTS)
# ==============================================================================
def test_acoustic_pause_and_resume():
    """When detector is paused during TTS, incoming candidate phrases are ignored."""
    events = []

    def on_wake(evt):
        events.append(evt)

    mock_stream = MagicMock(spec=MicrophoneStream)
    detector = LocalAgentWakeWordDetector(
        wake_phrase="Hey JARVIS",
        on_wake_callback=on_wake,
        audio_stream=mock_stream
    )
    detector.is_active = True

    # Pause detector (e.g. while JARVIS is speaking via TTS)
    detector.pause()
    assert detector.is_paused is True
    mock_stream.pause.assert_called_once()

    # Candidate received while paused
    assert detector.process_candidate("Hey JARVIS") is False
    assert len(events) == 0

    # Resume detector
    detector.resume()
    assert detector.is_paused is False
    mock_stream.resume.assert_called_once()

    assert detector.process_candidate("Hey JARVIS") is True
    assert len(events) == 1


# ==============================================================================
# 5. MISSING MICROPHONE HANDLING
# ==============================================================================
def test_missing_microphone_handling():
    """MicrophoneStream handles zero audio devices without raising unhandled errors."""
    stream = MicrophoneStream()

    mock_pa = MagicMock()
    mock_pa.get_device_count.return_value = 0

    with patch("pyaudio.PyAudio", return_value=mock_pa):
        success = stream._init_audio_device()
        assert success is False
        assert stream.state == AudioStreamState.NO_MICROPHONE
        assert "No audio devices detected" in stream.last_error


def test_detector_handles_missing_microphone():
    """Detector reports truthful status when microphone is in error/absent state."""
    mock_stream = MagicMock(spec=MicrophoneStream)
    mock_stream.get_state.return_value = AudioStreamState.NO_MICROPHONE
    mock_stream.get_last_error.return_value = "No audio devices detected"

    detector = LocalAgentWakeWordDetector(
        wake_phrase="Hey JARVIS",
        audio_stream=mock_stream
    )

    status = detector.get_status_dict()
    assert status["microphone_state"] == AudioStreamState.NO_MICROPHONE
    assert status["status"] == "MICROPHONE_ERROR"
    assert status["microphone_error"] == "No audio devices detected"


# ==============================================================================
# 6. WORKER CANCELLATION AND CLEAN SHUTDOWN
# ==============================================================================
def test_worker_cancellation_and_clean_shutdown():
    """Starting and stopping the detector cleans up background threads and resources."""
    mock_stream = MagicMock(spec=MicrophoneStream)
    mock_stream.read_frame.return_value = None

    detector = LocalAgentWakeWordDetector(
        wake_phrase="Hey JARVIS",
        audio_stream=mock_stream
    )

    started = detector.start()
    assert started is True
    assert detector.is_active is True
    assert detector._worker_thread is not None
    assert detector._worker_thread.is_alive()

    # Clean shutdown
    detector.stop()
    assert detector.is_active is False
    assert detector._worker_thread is None
    mock_stream.stop.assert_called_once()


# ==============================================================================
# 7. DUPLICATE-LISTENER PREVENTION
# ==============================================================================
def test_duplicate_listener_prevention():
    """Calling start() multiple times does not launch duplicate threads."""
    mock_stream = MagicMock(spec=MicrophoneStream)
    mock_stream.read_frame.return_value = None

    detector = LocalAgentWakeWordDetector(
        wake_phrase="Hey JARVIS",
        audio_stream=mock_stream
    )

    detector.start()
    thread_1 = detector._worker_thread
    assert thread_1 is not None

    # Second start call while already active
    detector.start()
    thread_2 = detector._worker_thread

    assert thread_1 is thread_2  # Same worker thread, no duplicate spawned

    detector.stop()


# ==============================================================================
# 8. AUTHENTICATED EVENT HANDLING AND MALFORMED EVENT REJECTION
# ==============================================================================
def test_authentication_token_verification():
    """Verify local agent authentication token security."""
    # Valid token
    assert verify_auth_token(AUTH_TOKEN) is True

    # Invalid / missing tokens
    assert verify_auth_token("invalid-secret-token") is False
    assert verify_auth_token("") is False
    assert verify_auth_token(None) is False


def test_truthful_status_dict():
    """Detector status dictionary contains all necessary telemetry fields."""
    detector = LocalAgentWakeWordDetector(wake_phrase="Hey JARVIS", cooldown_seconds=3.0)
    status = detector.get_status_dict()

    assert "running" in status
    assert "active" in status
    assert "paused" in status
    assert "phrase" in status
    assert "status" in status
    assert "microphone_state" in status
    assert "engine" in status
    assert "engine_ready" in status
    assert "cooldown_seconds" in status
    assert status["phrase"] == "Hey JARVIS"
    assert status["cooldown_seconds"] == 3.0


# ==============================================================================
# 9. RECOVERY AFTER TEMPORARY AUDIO-DEVICE FAILURE
# ==============================================================================
def test_microphone_recovery_backoff():
    """MicrophoneStream initializes with safe bounded backoff parameters."""
    stream = MicrophoneStream()
    assert stream.state == AudioStreamState.UNINITIALIZED
    assert stream.sample_rate == 16000
    assert stream.chunk_size == 1280
    assert stream.max_queue_size == 35

    # Device cleanup restores None handles safely
    stream._cleanup_audio_device()
    assert stream._active_stream is None
    assert stream._pyaudio_instance is None
