import os
import time
import logging
import threading
from typing import Optional, Callable, Dict, Any

from local_agent.voice.audio_capture import MicrophoneStream, AudioStreamState
from local_agent.voice.detector_engine import BaseWakeWordEngine, OpenWakeWordEngine, MockWakeWordEngine

logger = logging.getLogger("jarvis.local_agent.wake_word")

COOLDOWN_SECONDS = 3.0  # Debounce window to prevent duplicate activations from a single spoken phrase


class LocalAgentWakeWordDetector:
    """
    Windows Local Agent Wake-Word Detection Subsystem.
    Combines background microphone capture via PyAudio with on-device openWakeWord
    inference for private, low-latency detection of "Hey JARVIS".
    Includes acoustic echo suppression during speech synthesis and debounce logic.
    """

    def __init__(
        self,
        wake_phrase: str = "Hey JARVIS",
        on_wake_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        audio_stream: Optional[MicrophoneStream] = None,
        detector_engine: Optional[BaseWakeWordEngine] = None,
        cooldown_seconds: float = COOLDOWN_SECONDS
    ):
        self.wake_phrase = wake_phrase
        self.on_wake_callback = on_wake_callback
        self.cooldown_seconds = cooldown_seconds

        # Audio stream & Detector engine (dependency injectable for tests)
        self.audio_stream = audio_stream or MicrophoneStream()
        self.detector_engine = detector_engine or OpenWakeWordEngine()

        self.is_active = False
        self.is_paused = False
        self.last_detection_timestamp: float = 0.0
        self.last_error: Optional[str] = None

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        """Starts background microphone capture and inference worker thread."""
        with self._lock:
            if self.is_active and self._worker_thread and self._worker_thread.is_alive():
                return True

            self.is_active = True
            self.is_paused = False
            self._stop_event.clear()

            # Start audio capture
            self.audio_stream.start()

            # Start background detector inference thread
            self._worker_thread = threading.Thread(
                target=self._run_detector_loop,
                name="JarvisWakeWordDetectorWorker",
                daemon=True
            )
            self._worker_thread.start()
            logger.info(f"LocalAgentWakeWordDetector started for '{self.wake_phrase}' (engine={type(self.detector_engine).__name__}).")
            return True

    def stop(self) -> bool:
        """Stops background audio capture and inference worker cleanly."""
        self._stop_event.set()
        with self._lock:
            self.is_active = False
            self.is_paused = False

        if self.audio_stream:
            self.audio_stream.stop()

        if self._worker_thread:
            if self._worker_thread.is_alive():
                self._worker_thread.join(timeout=2.0)
            self._worker_thread = None

        logger.info("LocalAgentWakeWordDetector stopped.")
        return True

    def pause(self) -> None:
        """Pause listening during TTS vocalization to avoid acoustic echo loop."""
        with self._lock:
            self.is_paused = True
        if self.audio_stream:
            self.audio_stream.pause()
        logger.debug("LocalAgentWakeWordDetector paused during TTS.")

    def resume(self) -> None:
        """Resume listening after TTS vocalization completes."""
        if self.audio_stream:
            self.audio_stream.resume()
        if self.detector_engine:
            self.detector_engine.reset()
        with self._lock:
            self.is_paused = False
        logger.debug("LocalAgentWakeWordDetector resumed.")

    def is_running(self) -> bool:
        """Returns True if detector is active and not paused."""
        with self._lock:
            return self.is_active and not self.is_paused

    def is_paused_state(self) -> bool:
        """Returns True if detector is currently paused."""
        with self._lock:
            return self.is_paused

    def get_status_dict(self) -> Dict[str, Any]:
        """Provides comprehensive, truthful status readout for IPC and HTTP health probes."""
        with self._lock:
            mic_state = self.audio_stream.get_state() if self.audio_stream else "UNAVAILABLE"
            mic_err = self.audio_stream.get_last_error() if self.audio_stream else None
            engine_ready = self.detector_engine.is_available() if self.detector_engine else False

            if mic_state in (AudioStreamState.NO_MICROPHONE, AudioStreamState.ERROR):
                status_str = "MICROPHONE_ERROR"
            elif not engine_ready:
                status_str = "ENGINE_UNAVAILABLE"
            elif not self.is_active:
                status_str = "DISABLED"
            elif self.is_paused:
                status_str = "PAUSED"
            elif mic_state == AudioStreamState.STARTING:
                status_str = "STARTING"
            elif mic_state == AudioStreamState.RECONNECTING:
                status_str = "RECONNECTING"
            elif mic_state == AudioStreamState.LISTENING:
                status_str = "READY"
            else:
                status_str = "DISABLED"

            is_genuinely_ready = bool(self.is_active and not self.is_paused and engine_ready and mic_state == AudioStreamState.LISTENING)

            return {
                "running": self.is_active and not self.is_paused,
                "ready": is_genuinely_ready,
                "active": self.is_active,
                "paused": self.is_paused,
                "phrase": self.wake_phrase,
                "status": status_str,
                "microphone_state": mic_state,
                "microphone_error": mic_err,
                "engine": type(self.detector_engine).__name__,
                "engine_ready": engine_ready,
                "last_detection_timestamp": self.last_detection_timestamp,
                "cooldown_seconds": self.cooldown_seconds
            }

    def _run_detector_loop(self):
        """Dedicated background audio frame processing loop."""
        while not self._stop_event.is_set():
            if self.is_paused:
                time.sleep(0.08)
                continue

            frame = self.audio_stream.read_frame(timeout=0.1)
            if frame is None:
                continue

            # Run offline inference
            try:
                detected, confidence, model_name = self.detector_engine.predict(frame)
            except Exception as e:
                logger.warning(f"Engine prediction exception: {e}")
                continue

            if detected:
                now = time.time()
                # Enforce debounce cooldown to prevent multi-triggering
                if now - self.last_detection_timestamp < self.cooldown_seconds:
                    logger.debug(f"Wake word detected but suppressed by debounce cooldown ({now - self.last_detection_timestamp:.2f}s < {self.cooldown_seconds}s).")
                    continue

                self.last_detection_timestamp = now
                logger.info(f"Wake word '{self.wake_phrase}' detected! (confidence={confidence:.2f}, model={model_name})")

                event_data = {
                    "event_type": "WAKE_WORD_DETECTED",
                    "wake_phrase": self.wake_phrase,
                    "confidence": float(confidence),
                    "model": model_name,
                    "timestamp": now
                }

                if self.on_wake_callback:
                    try:
                        self.on_wake_callback(event_data)
                    except Exception as cb_err:
                        logger.error(f"Error executing on_wake_callback: {cb_err}")

                # Reset detector state to flush buffers
                self.detector_engine.reset()

    # Legacy text candidate evaluation preserved for backend/unit-test compatibility
    def on_audio_phrase(self, phrase_or_text: str) -> bool:
        return self.process_candidate(phrase_or_text)

    def process_candidate(self, phrase_or_text: str) -> bool:
        """Evaluates detected audio transcript against wake phrase."""
        if not self.is_active or self.is_paused:
            return False

        norm = "".join(ch.lower() for ch in phrase_or_text if ch.isalnum() or ch.isspace()).strip()
        target = "".join(ch.lower() for ch in self.wake_phrase if ch.isalnum() or ch.isspace()).strip()

        if target in norm or ("jarvis" in norm and ("hey" in norm or "ok" in norm or "hi" in norm)):
            now = time.time()
            if now - self.last_detection_timestamp < self.cooldown_seconds:
                return True

            self.last_detection_timestamp = now
            logger.info(f"Wake phrase match detected: '{phrase_or_text}' -> Triggering activation.")
            if self.on_wake_callback:
                try:
                    event_data = {
                        "event_type": "WAKE_WORD_DETECTED",
                        "wake_phrase": self.wake_phrase,
                        "confidence": 1.0,
                        "candidate": phrase_or_text,
                        "timestamp": now
                    }
                    self.on_wake_callback(event_data)
                except Exception as e:
                    logger.error(f"Error in on_wake_callback: {e}")
            return True

        return False
