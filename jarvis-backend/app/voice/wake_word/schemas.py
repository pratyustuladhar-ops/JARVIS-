from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class WakeWordConfig(BaseModel):
    enabled: bool = Field(default=False, description="Master toggle for hands-free wake word detection")
    wake_phrase: str = Field(default="Hey JARVIS", description="Activation wake phrase")
    wake_response: str = Field(default="Yes?", description="Verbal acknowledgement upon wake detection")
    command_timeout: int = Field(default=8, description="Silence timeout waiting for command in seconds")
    follow_up_timeout: int = Field(default=8, description="Follow-up command window in seconds")
    auto_resume_listening: bool = Field(default=True, description="Automatically resume wake-word listening after TTS")
    sensitivity: float = Field(default=0.7, description="Wake-word spotter sensitivity threshold (0.0-1.0)")
    provider: str = Field(default="local", description="Wake word engine provider: local, porcupine, mock")


class WakeWordEvent(BaseModel):
    event_type: str = Field(..., description="WAKE_WORD_ENABLED, WAKE_WORD_DISABLED, WAKE_WORD_DETECTED, VOICE_COMMAND_STARTED, VOICE_COMMAND_COMPLETED, VOICE_COMMAND_FAILED")
    wake_phrase: Optional[str] = Field("Hey JARVIS", description="Wake phrase triggered or configured")
    detail: Optional[str] = Field(None, description="Descriptive context or outcome")
    duration_ms: Optional[float] = Field(None, description="Command or synthesis duration in milliseconds")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadata without raw audio recordings")


class WakeWordStatusResponse(BaseModel):
    is_enabled: bool
    enabled: Optional[bool] = None
    wake_phrase: str
    wake_response: str
    provider: str
    provider_status: str  # ACTIVE, STANDBY, PAUSED, OFFLINE
    active_state: str  # IDLE, WAKE_WORD_LISTENING, WAKE_WORD_DETECTED, LISTENING, PROCESSING, ANALYZING, EXECUTING, VERIFYING, RESPONDING, ERROR
    state: Optional[str] = None
    command_timeout: int
    command_timeout_seconds: Optional[int] = None
    follow_up_timeout: int
    follow_up_timeout_seconds: Optional[int] = None
    auto_resume_listening: bool
    is_paused: bool = False


class ToggleWakeWordRequest(BaseModel):
    enabled: bool = Field(..., description="Master toggle for hands-free wake word listening")

