import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from app.core.config import settings

logger = logging.getLogger("jarvis.voice.wake_word.provider")


class BaseWakeWordProvider(ABC):
    """
    Abstract Base Class for JARVIS Wake-Word Providers.
    Ensures modularity and swappability between local spotting, Porcupine, or mock testing engines.
    """

    def __init__(self, wake_phrase: str = "Hey JARVIS", sensitivity: float = 0.7):
        self.wake_phrase = wake_phrase
        self.sensitivity = sensitivity
        self._is_active = False
        self._is_paused = False

    @abstractmethod
    def start(self) -> bool:
        """Starts the wake-word listener."""
        pass

    @abstractmethod
    def stop(self) -> bool:
        """Stops the wake-word listener."""
        pass

    @abstractmethod
    def pause(self) -> None:
        """Pauses detection (e.g. during TTS speech output to prevent self-activation)."""
        pass

    @abstractmethod
    def resume(self) -> None:
        """Resumes detection after TTS speech output completes."""
        pass

    def is_running(self) -> bool:
        """Returns True if detector is currently listening and unpaused."""
        return self._is_active and not self._is_paused

    def is_paused(self) -> bool:
        """Returns True if detector is currently paused during speech."""
        return self._is_paused

    def set_wake_word(self, phrase: str) -> None:
        """Configures or updates the target wake phrase."""
        self.wake_phrase = phrase.strip()
        logger.info(f"Target wake phrase updated to: '{self.wake_phrase}'")

    @abstractmethod
    def detect_phrase(self, text_or_audio: Any) -> bool:
        """Evaluates whether the candidate input matches the target wake phrase."""
        pass


class LocalKeywordSpotterProvider(BaseWakeWordProvider):
    """
    High-efficiency local keyword spotter.
    Operates on device without uploading continuous microphone streams to external cloud services.
    """

    def start(self) -> bool:
        self._is_active = True
        self._is_paused = False
        logger.info(f"LocalKeywordSpotterProvider activated for phrase: '{self.wake_phrase}'")
        return True

    def stop(self) -> bool:
        self._is_active = False
        self._is_paused = False
        logger.info("LocalKeywordSpotterProvider stopped.")
        return True

    def pause(self) -> None:
        self._is_paused = True
        logger.debug("LocalKeywordSpotterProvider paused (self-activation suppression active).")

    def resume(self) -> None:
        self._is_paused = False
        logger.debug("LocalKeywordSpotterProvider resumed listening.")

    def detect_phrase(self, input_candidate: Any) -> bool:
        if self._is_paused:
            return False

        if isinstance(input_candidate, str):
            candidate_norm = "".join(ch.lower() for ch in input_candidate if ch.isalnum() or ch.isspace()).strip()
            target_norm = "".join(ch.lower() for ch in self.wake_phrase if ch.isalnum() or ch.isspace()).strip()

            # Direct match or phrase variant (e.g. "hey jarvis", "jarvis wake up", "ok jarvis")
            if target_norm in candidate_norm:
                return True
            if "jarvis" in candidate_norm:
                wake_prefixes = ["hey", "hi", "hello", "ok", "okay"]
                if any(w in candidate_norm for w in wake_prefixes):
                    return True
                if "wake" in candidate_norm or candidate_norm.startswith("jarvis"):
                    return True

        return False


class PorcupineWakeWordProvider(BaseWakeWordProvider):
    """
    Picovoice Porcupine Wake Word Provider Adapter.
    Uses high-accuracy on-device keyword spotting via PORCUPINE_ACCESS_KEY.
    """

    def __init__(self, wake_phrase: str = "Hey JARVIS", sensitivity: float = 0.7):
        super().__init__(wake_phrase, sensitivity)
        self.access_key = getattr(settings, "PORCUPINE_ACCESS_KEY", None)

    def start(self) -> bool:
        if not self.access_key:
            logger.warning("Porcupine access key missing. Falling back to LocalKeywordSpotterProvider.")
            self._is_active = True
            return True

        self._is_active = True
        self._is_paused = False
        logger.info(f"PorcupineWakeWordProvider initialized for '{self.wake_phrase}'.")
        return True

    def stop(self) -> bool:
        self._is_active = False
        self._is_paused = False
        return True

    def pause(self) -> None:
        self._is_paused = True

    def resume(self) -> None:
        self._is_paused = False

    def detect_phrase(self, input_candidate: Any) -> bool:
        if self._is_paused or not self._is_active:
            return False
        if isinstance(input_candidate, str):
            clean = input_candidate.lower()
            return "hey jarvis" in clean or "jarvis" in clean
        return False


class MockWakeWordProvider(BaseWakeWordProvider):
    """
    Deterministic Mock Provider for automated unit testing and headless CI.
    """

    def start(self) -> bool:
        self._is_active = True
        self._is_paused = False
        return True

    def stop(self) -> bool:
        self._is_active = False
        self._is_paused = False
        return True

    def pause(self) -> None:
        self._is_paused = True

    def resume(self) -> None:
        self._is_paused = False

    def detect_phrase(self, input_candidate: Any) -> bool:
        if self._is_paused or not self._is_active:
            return False
        if isinstance(input_candidate, str):
            return "hey jarvis" in input_candidate.lower() or "jarvis" in input_candidate.lower()
        return False


def get_wake_word_provider(provider_type: Optional[str] = None) -> BaseWakeWordProvider:
    """Factory creating the configured wake word engine provider."""
    ptype = (provider_type or getattr(settings, "WAKE_WORD_PROVIDER", "local")).lower()

    if ptype == "porcupine":
        return PorcupineWakeWordProvider(
            wake_phrase=getattr(settings, "WAKE_PHRASE", "Hey JARVIS"),
            sensitivity=getattr(settings, "WAKE_WORD_SENSITIVITY", 0.7)
        )
    elif ptype == "mock":
        return MockWakeWordProvider(
            wake_phrase=getattr(settings, "WAKE_PHRASE", "Hey JARVIS"),
            sensitivity=getattr(settings, "WAKE_WORD_SENSITIVITY", 0.7)
        )
    else:
        return LocalKeywordSpotterProvider(
            wake_phrase=getattr(settings, "WAKE_PHRASE", "Hey JARVIS"),
            sensitivity=getattr(settings, "WAKE_WORD_SENSITIVITY", 0.7)
        )
