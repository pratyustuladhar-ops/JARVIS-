import time
import json
import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.activity_service import activity_service
from app.voice.wake_word.schemas import WakeWordConfig, WakeWordEvent, WakeWordStatusResponse
from app.voice.wake_word.provider import BaseWakeWordProvider, get_wake_word_provider

logger = logging.getLogger("jarvis.voice.wake_word.service")


class WakeWordService:
    """
    Central service orchestrating hands-free Wake Word state machine, provider lifecycle,
    self-activation avoidance, and privacy-enforced activity audit logging.
    """

    VOICE_STATES = [
        "IDLE",
        "WAKE_WORD_LISTENING",
        "WAKE_WORD_DETECTED",
        "LISTENING",
        "PROCESSING",
        "ANALYZING",
        "EXECUTING",
        "VERIFYING",
        "RESPONDING",
        "ERROR"
    ]

    def __init__(self):
        self.provider: BaseWakeWordProvider = get_wake_word_provider()
        self.is_enabled: bool = getattr(settings, "WAKE_WORD_ENABLED", False)
        self.active_state: str = "WAKE_WORD_LISTENING" if self.is_enabled else "IDLE"
        self.wake_phrase: str = getattr(settings, "WAKE_PHRASE", "Hey JARVIS")
        self.wake_response: str = getattr(settings, "WAKE_ACKNOWLEDGMENT", "Yes?")
        self.command_timeout: int = getattr(settings, "COMMAND_TIMEOUT_SECONDS", 8)
        self.follow_up_timeout: int = getattr(settings, "FOLLOW_UP_TIMEOUT_SECONDS", 8)
        self.auto_resume_listening: bool = getattr(settings, "AUTO_RESUME_LISTENING", True)
        self.last_detection_timestamp: float = 0.0

        if self.is_enabled:
            self.provider.start()

    def is_running(self) -> bool:
        """Returns True if hands-free wake word listening is actively running."""
        return self.is_enabled and self.provider.is_running()

    def start(self) -> bool:
        """Starts local wake word detection."""
        self.is_enabled = True
        self.provider.start()
        self.active_state = "WAKE_WORD_LISTENING"
        return True

    def stop(self) -> bool:
        """Stops local wake word detection."""
        self.is_enabled = False
        self.provider.stop()
        self.active_state = "IDLE"
        return True

    def transition_state(self, new_state: str) -> bool:
        """Transitions state machine to a valid voice state."""
        if new_state in self.VOICE_STATES:
            self.active_state = new_state
            return True
        return False

    def notify_tts_start(self) -> None:
        """Called when JARVIS begins speaking via TTS to prevent acoustic self-activation."""
        self.pause_detection_for_speech()

    def notify_tts_end(self) -> None:
        """Called when JARVIS finishes speaking via TTS."""
        self.resume_detection_after_speech()

    def on_wake_detected(self, phrase: str) -> bool:
        """Handles detection of the wake phrase. Rejects if paused during TTS."""
        if self.provider.is_paused():
            return False
        self.active_state = "WAKE_WORD_DETECTED"
        self.last_detection_timestamp = time.time()
        return True

    def handle_command_timeout(self) -> str:
        """Handles expiration of the command listening window."""
        self.active_state = "WAKE_WORD_LISTENING" if self.is_enabled else "IDLE"
        return "I didn't hear a command."

    def on_follow_up_timeout(self) -> None:
        """Handles expiration of the follow-up command window."""
        self.active_state = "WAKE_WORD_LISTENING" if self.is_enabled else "IDLE"

    def get_status(self) -> WakeWordStatusResponse:
        """Returns the current state and capabilities of the hands-free subsystem."""
        provider_stat = "ACTIVE" if self.provider.is_running() else ("PAUSED" if self.provider.is_paused() else "STANDBY")
        return WakeWordStatusResponse(
            is_enabled=self.is_enabled,
            enabled=self.is_enabled,
            wake_phrase=self.wake_phrase,
            wake_response=self.wake_response,
            provider=getattr(settings, "WAKE_WORD_PROVIDER", "local"),
            provider_status=provider_stat,
            active_state=self.active_state,
            state=self.active_state,
            command_timeout=self.command_timeout,
            command_timeout_seconds=self.command_timeout,
            follow_up_timeout=self.follow_up_timeout,
            follow_up_timeout_seconds=self.follow_up_timeout,
            auto_resume_listening=self.auto_resume_listening,
            is_paused=self.provider.is_paused()
        )

    def set_enabled(self, db: Session, enabled: bool) -> WakeWordStatusResponse:
        """Enables or disables hands-free wake word listening mode."""
        prev = self.is_enabled
        self.is_enabled = enabled

        if enabled:
            self.provider.start()
            self.active_state = "WAKE_WORD_LISTENING"
            activity_service.record_activity(
                db=db,
                event_type="WAKE_WORD_ENABLED",
                title="Hands-Free Wake Word Activated",
                description=f"Local wake word detector listening for '{self.wake_phrase}'.",
                status="INFO",
                metadata_json=json.dumps({"wake_phrase": self.wake_phrase, "provider": getattr(settings, "WAKE_WORD_PROVIDER", "local")})
            )
        else:
            self.provider.stop()
            self.active_state = "IDLE"
            activity_service.record_activity(
                db=db,
                event_type="WAKE_WORD_DISABLED",
                title="Hands-Free Wake Word Deactivated",
                description="JARVIS reverted to manual push-to-talk microphone mode.",
                status="INFO"
            )

        logger.info(f"Wake word master state changed from {prev} to {enabled}.")
        return self.get_status()

    def record_event(self, db: Session, event: WakeWordEvent) -> Dict[str, Any]:
        """
        Records meaningful wake word audit events in the Activity table.
        Strict Privacy: Rejects and never logs raw audio streams or sensitive conversation data.
        """
        valid_types = {
            "WAKE_WORD_ENABLED",
            "WAKE_WORD_DISABLED",
            "WAKE_WORD_DETECTED",
            "VOICE_COMMAND_STARTED",
            "VOICE_COMMAND_COMPLETED",
            "VOICE_COMMAND_FAILED"
        }

        etype = event.event_type if event.event_type in valid_types else "VOICE_COMMAND_COMPLETED"
        status_flag = "SUCCESS" if "COMPLETED" in etype or "ENABLED" in etype or "DETECTED" in etype else ("ERROR" if "FAILED" in etype else "INFO")

        # Strip any accidental audio payload from metadata
        clean_meta = {}
        if event.metadata:
            for k, v in event.metadata.items():
                if k not in ["audio", "raw_audio", "wav", "pcm", "stream"]:
                    clean_meta[k] = v

        if event.duration_ms:
            clean_meta["duration_ms"] = event.duration_ms
        if event.wake_phrase:
            clean_meta["wake_phrase"] = event.wake_phrase

        # Update service active state tracking
        if etype == "WAKE_WORD_DETECTED":
            self.active_state = "WAKE_WORD_DETECTED"
            self.last_detection_timestamp = time.time()
        elif etype == "VOICE_COMMAND_STARTED":
            self.active_state = "LISTENING"
        elif etype == "VOICE_COMMAND_COMPLETED":
            self.active_state = "WAKE_WORD_LISTENING" if self.is_enabled else "IDLE"
        elif etype == "VOICE_COMMAND_FAILED":
            self.active_state = "ERROR"

        record = activity_service.record_activity(
            db=db,
            event_type=etype,
            title=f"Voice Telemetry: {etype.replace('_', ' ').title()}",
            description=event.detail or f"Hands-free event '{etype}' recorded.",
            status=status_flag,
            metadata_json=json.dumps(clean_meta) if clean_meta else None
        )

        return {
            "status": "recorded",
            "activity_id": record.id,
            "event_type": etype,
            "active_state": self.active_state
        }

    def pause_detection_for_speech(self) -> None:
        """Called when JARVIS begins speaking via TTS to prevent acoustic self-activation."""
        self.provider.pause()
        self.active_state = "RESPONDING"
        logger.debug("Wake word detection paused while JARVIS speaks.")

    def resume_detection_after_speech(self) -> None:
        """Called when JARVIS finishes speaking via TTS."""
        if self.is_enabled:
            self.provider.resume()
            self.active_state = "WAKE_WORD_LISTENING"
        else:
            self.active_state = "IDLE"
        logger.debug("Wake word detection resumed after speech completion.")


wake_word_service = WakeWordService()
