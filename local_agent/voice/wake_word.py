import logging
import threading
from typing import Optional, Callable

logger = logging.getLogger("jarvis.local_agent.wake_word")


class LocalAgentWakeWordDetector:
    """
    Windows Local Agent Wake Word Detector Component.
    Enables autonomous desktop wake detection with local keyword processing,
    echo prevention during speech synthesis, and secure backend routing.
    """

    def __init__(self, wake_phrase: str = "Hey JARVIS", on_wake_callback: Optional[Callable[[], None]] = None):
        self.wake_phrase = wake_phrase
        self.on_wake_callback = on_wake_callback
        self.is_active = False
        self.is_paused = False
        self._lock = threading.Lock()

    def start(self) -> bool:
        with self._lock:
            self.is_active = True
            self.is_paused = False
            logger.info(f"LocalAgentWakeWordDetector active for '{self.wake_phrase}'.")
            return True

    def stop(self) -> bool:
        with self._lock:
            self.is_active = False
            self.is_paused = False
            logger.info("LocalAgentWakeWordDetector stopped.")
            return True

    def pause(self) -> None:
        """Pause listening during TTS to avoid echo loop."""
        with self._lock:
            self.is_paused = True
            logger.debug("LocalAgentWakeWordDetector paused during TTS.")

    def resume(self) -> None:
        """Resume listening after TTS finishes."""
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

    def on_audio_phrase(self, phrase_or_text: str) -> bool:
        """Alias for process_candidate."""
        return self.process_candidate(phrase_or_text)

    def process_candidate(self, phrase_or_text: str) -> bool:
        """Evaluates detected audio transcript against wake phrase."""
        if not self.is_active or self.is_paused:
            return False

        norm = "".join(ch.lower() for ch in phrase_or_text if ch.isalnum() or ch.isspace()).strip()
        target = "".join(ch.lower() for ch in self.wake_phrase if ch.isalnum() or ch.isspace()).strip()

        if target in norm or ("jarvis" in norm and ("hey" in norm or "ok" in norm or "hi" in norm)):
            logger.info(f"Wake phrase match detected: '{phrase_or_text}' -> Triggering activation.")
            if self.on_wake_callback:
                try:
                    self.on_wake_callback()
                except Exception as e:
                    logger.error(f"Error in on_wake_callback: {e}")
            return True

        return False

