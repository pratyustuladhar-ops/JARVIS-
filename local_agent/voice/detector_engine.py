"""
Offline Wake-Word Inference Engine for JARVIS Local Agent.
Integrates openWakeWord with ONNX runtime for on-device detection of "Hey JARVIS".
Includes mock engine for unit tests and deterministic offline verification.
"""

import os
import logging
from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any, Optional
import numpy as np

logger = logging.getLogger("jarvis.local_agent.detector_engine")


class BaseWakeWordEngine(ABC):
    """Abstract interface for local offline wake-word detector engines."""

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the engine and model weights are ready for inference."""
        pass

    @abstractmethod
    def predict(self, audio_frame: np.ndarray) -> Tuple[bool, float, str]:
        """
        Processes one audio frame (16kHz 16-bit PCM numpy array).
        Returns: (is_detected: bool, confidence: float, model_name: str)
        """
        pass

    @abstractmethod
    def reset(self) -> None:
        """Resets internal model state, buffers, and accumulators."""
        pass


class OpenWakeWordEngine(BaseWakeWordEngine):
    """
    Local offline wake-word inference engine powered by openWakeWord + ONNX Runtime.
    Model: hey_jarvis_v0.1.onnx (Apache-2.0).
    """

    def __init__(
        self,
        model_name_or_path: str = "hey_jarvis_v0.1.onnx",
        threshold: float = 0.5
    ):
        env_model = os.getenv("JARVIS_WAKE_WORD_MODEL_PATH")
        self.model_path = env_model if env_model else model_name_or_path

        env_sens = os.getenv("JARVIS_WAKE_WORD_SENSITIVITY")
        self.threshold = float(env_sens) if env_sens is not None else threshold

        self.model = None
        self.is_ready = False
        self.last_error: Optional[str] = None
        self.target_key: Optional[str] = None

        self._load_model()

    def _load_model(self):
        try:
            import openwakeword
            from openwakeword.model import Model

            # Initialize model with ONNX inference framework
            self.model = Model(
                wakeword_models=[self.model_path],
                inference_framework="onnx"
            )
            # Find the actual dictionary key loaded by openWakeWord
            keys = list(self.model.models.keys())
            self.target_key = keys[0] if keys else None
            self.is_ready = True
            self.last_error = None
            logger.info(f"OpenWakeWordEngine initialized successfully with model '{self.target_key}' (threshold={self.threshold})")

        except Exception as e:
            self.is_ready = False
            self.last_error = f"Failed to initialize openWakeWord: {str(e)}"
            logger.warning(self.last_error)

    def is_available(self) -> bool:
        return self.is_ready and self.model is not None

    def predict(self, audio_frame: np.ndarray) -> Tuple[bool, float, str]:
        if not self.is_ready or not self.model:
            return False, 0.0, ""

        try:
            # openWakeWord expects 16-bit signed PCM audio frame
            if audio_frame.dtype != np.int16:
                audio_frame = audio_frame.astype(np.int16)

            predictions = self.model.predict(audio_frame)
            score = 0.0

            if self.target_key and self.target_key in predictions:
                score = float(predictions[self.target_key])
            elif predictions:
                # Use max score across all loaded models
                score = float(max(predictions.values()))

            detected = score >= self.threshold
            return detected, score, self.target_key or "hey_jarvis"

        except Exception as e:
            logger.warning(f"Prediction error in OpenWakeWordEngine: {e}")
            return False, 0.0, ""

    def reset(self) -> None:
        if self.model and hasattr(self.model, "reset"):
            try:
                self.model.reset()
            except Exception:
                pass


class MockWakeWordEngine(BaseWakeWordEngine):
    """
    Deterministic Mock Engine for unit tests.
    Triggers wake word detection on specific frame count or when explicitly signaled.
    """

    def __init__(self, trigger_after_frames: int = -1, threshold: float = 0.5):
        self.trigger_after_frames = trigger_after_frames
        self.threshold = threshold
        self.frame_count = 0
        self.force_trigger = False
        self.is_ready = True

    def is_available(self) -> bool:
        return self.is_ready

    def predict(self, audio_frame: np.ndarray) -> Tuple[bool, float, str]:
        self.frame_count += 1
        if self.force_trigger or (self.trigger_after_frames > 0 and self.frame_count == self.trigger_after_frames):
            self.force_trigger = False
            return True, 0.98, "mock_hey_jarvis"
        return False, 0.05, "mock_hey_jarvis"

    def reset(self) -> None:
        self.frame_count = 0
        self.force_trigger = False
