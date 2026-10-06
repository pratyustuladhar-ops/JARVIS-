from datetime import datetime
from typing import Optional, Dict, Any, Union
from pydantic import BaseModel, ConfigDict, Field


class SettingItemResponse(BaseModel):
    key: str
    value: Any
    type: str = "string"
    category: str = "general"
    description: Optional[str] = None
    is_active: bool = True
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SettingItemUpdate(BaseModel):
    value: Any
    type: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class SystemSettings(BaseModel):
    # General
    assistant_name: str = Field(default="JARVIS", description="Primary AI assistant callsign")
    operator_identity: str = Field(default="COMMANDER_STARK", description="Designation of system operator")
    operator_callsign: str = Field(default="COMMANDER_STARK", description="Alias for operator_identity")
    language: str = Field(default="EN-US (English - Tactical Synthesized)", description="Language profile")
    synthesis_language: str = Field(default="EN-US (English - Tactical Synthesized)", description="Alias for language")
    timezone: str = Field(default="UTC+00:00 (ZULU MILITARY STANDARD)", description="System time clock standard")
    system_temporal_clock: str = Field(default="UTC+00:00 (ZULU MILITARY STANDARD)", description="Alias for timezone")
    date_format: str = Field(default="YYYY-MM-DD HH:mm:ss.ms (ISO-8601 DEFENSE)", description="Date and timestamp notation")
    timestamp_notation: str = Field(default="YYYY-MM-DD HH:mm:ss.ms (ISO-8601 DEFENSE)", description="Alias for date_format")
    theme: str = Field(default="dark", description="Visual theme profile")
    interface_density: str = Field(default="TACTICAL COMPACT", description="UI element spacing density")
    viewport_density: str = Field(default="TACTICAL COMPACT", description="Alias for interface_density")
    hud_coordinates_overlay: bool = Field(default=True, description="Render HUD orbital crosshairs")

    # AI Assistant & Heuristics
    assistant_personality: str = Field(default="Autonomous Commander", description="Behavioral personality preset")
    behavioral_preset: str = Field(default="Autonomous Commander", description="Alias for assistant_personality")
    response_style: str = Field(default="Concise Tactical", description="Tone and format of AI responses")
    response_length: str = Field(default="Standard", description="Response token conciseness")
    creativity_level: float = Field(default=0.32, description="Model sampling temperature between 0.0 and 1.0")
    temperature: float = Field(default=0.32, description="Alias for creativity_level")
    default_model: str = Field(default="HYBRID SWARM ROUTER", description="Active neural engine")
    neural_backbone: str = Field(default="HYBRID SWARM ROUTER", description="Alias for default_model")
    streaming_responses: bool = Field(default=True, description="Stream token telemetry in real-time")
    streaming_token_telemetry: bool = Field(default=True, description="Alias for streaming_responses")
    context_awareness: int = Field(default=128000, description="Task context token window budget")
    context_budget: int = Field(default=128000, description="Alias for context_awareness")
    auto_verification: bool = Field(default=True, description="Auto-verify solution in background compiler")
    multi_turn_reasoning: bool = Field(default=True, description="Permit multi-hop subagent reasoning")
    reasoning_depth: int = Field(default=4, description="Reasoning search depth level (1-5)")

    # Memory & Recall
    memory_enabled: bool = Field(default=True, description="Master switch for persistent neural memory")
    persistent_memory: bool = Field(default=True, description="Alias for memory_enabled")
    automatic_memory: bool = Field(default=True, description="Index terminal commands and diffs autonomously")
    autonomous_ingestion: bool = Field(default=True, description="Alias for automatic_memory")
    memory_importance_threshold: int = Field(default=85, description="Cosine relevance cutoff percentage")
    similarity_threshold: int = Field(default=85, description="Alias for memory_importance_threshold")
    conversation_retention: str = Field(default="30_days", description="Session retention policy")

    # Notifications & Alerts
    task_notifications: bool = Field(default=True, description="Notify when autonomous tasks complete")
    notify_task_completion: bool = Field(default=True, description="Alias for task_notifications")
    project_notifications: bool = Field(default=True, description="Notify on project milestone changes")
    ai_notifications: bool = Field(default=True, description="Notify on agent clarification requests")
    notify_escalations: bool = Field(default=True, description="Alias for ai_notifications")
    system_notifications: bool = Field(default=True, description="Alert on kernel telemetry anomalies")
    notify_telemetry_anomalies: bool = Field(default=True, description="Alias for system_notifications")
    activity_notifications: bool = Field(default=True, description="Record and stream audit events")
    desktop_notifications: bool = Field(default=True, description="Level 4 security emergency alerts")
    notify_security_broadcast: bool = Field(default=True, description="Alias for desktop_notifications")
    notify_audio_ping: bool = Field(default=False, description="Acoustic 440Hz HUD audio tone on transmit")

    # Appearance & HUD
    color_accent: str = Field(default="CYBERNETIC CYAN", description="Primary chromatic palette")
    glow_intensity: int = Field(default=64, description="Optical glow percentage (0-100)")
    animation_intensity: bool = Field(default=True, description="Enable UI animations and sweeps")
    particle_vfx: bool = Field(default=True, description="Floating atmospheric shimmer particles")
    glassmorphism: bool = Field(default=True, description="Substrate blur filtration")
    sidebar_behavior: str = Field(default="docked", description="Sidebar behavior (docked / collapsible)")

    # Security & Privacy
    isolated_docker_sandbox: bool = Field(default=True, description="Execute commands in ephemeral sandbox container")
    tool_execution_policy: str = Field(default="Human-in-the-Loop (HITL)", description="HITL or Full Autonomous")
    emergency_sandbox: bool = Field(default=False, description="Isolate external outward network sockets")
    privacy_preferences: bool = Field(default=True, description="Strip sensitive credentials before indexing")

    # Voice & Speech Synthesis
    voice_enabled: bool = Field(default=True, description="Enable automatic Text-to-Speech audio response")
    voice_name: str = Field(default="default", description="Browser synthesizer voice identifier")
    voice_rate: float = Field(default=1.0, description="Speech rate multiplier (0.5 to 2.0)")
    voice_pitch: float = Field(default=1.0, description="Speech pitch multiplier (0.5 to 2.0)")
    voice_volume: float = Field(default=1.0, description="Audio volume percentage (0.0 to 1.0)")

    # Wake Word & Hands-Free (Step 10)
    wake_word_enabled: bool = Field(default=False, description="Master switch for hands-free wake-word detection")
    wake_phrase: str = Field(default="Hey JARVIS", description="Activation wake phrase")
    wake_response: str = Field(default="Yes?", description="Verbal acknowledgement upon wake detection")
    command_timeout: int = Field(default=8, description="Silence timeout waiting for command in seconds")
    follow_up_timeout: int = Field(default=8, description="Follow-up command window in seconds")
    auto_resume_listening: bool = Field(default=True, description="Automatically return to wake-word detection after TTS")
    wake_word_sensitivity: float = Field(default=0.7, description="Wake-word spotter sensitivity threshold (0.0-1.0)")
    wake_word_provider: str = Field(default="local", description="Wake word engine provider: local, porcupine, mock")

    # Windows Local Agent
    local_agent_enabled: bool = Field(default=True, description="Enable Windows Local Agent computer actions")
    local_agent_confirmation_required: bool = Field(default=False, description="Require confirmation for medium-risk local actions")
    local_agent_heartbeat_interval: int = Field(default=10, description="Local agent heartbeat interval in seconds")
    local_agent_device_name: str = Field(default="JARVIS-WINDOWS-01", description="Primary Windows local agent callsign")

    # Multimodal & Vision Intelligence (Step 9)
    vision_enabled: bool = Field(default=True, description="Enable multimodal vision capabilities")
    screen_understanding_enabled: bool = Field(default=True, description="Allow screen analysis and screenshot understanding")
    ocr_enabled: bool = Field(default=True, description="Allow OCR text extraction from visual inputs")
    speak_vision_responses: bool = Field(default=False, description="Speak multimodal and vision responses via TTS")
    vision_privacy_mode: bool = Field(default=False, description="Never retain temporary visual buffers or summaries")

    # Future CMS / Dynamic parameters
    extra_params: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(extra="ignore")


class SystemSettingsUpdate(BaseModel):
    assistant_name: Optional[str] = None
    operator_identity: Optional[str] = None
    operator_callsign: Optional[str] = None
    language: Optional[str] = None
    synthesis_language: Optional[str] = None
    timezone: Optional[str] = None
    system_temporal_clock: Optional[str] = None
    date_format: Optional[str] = None
    timestamp_notation: Optional[str] = None
    theme: Optional[str] = None
    interface_density: Optional[str] = None
    viewport_density: Optional[str] = None
    hud_coordinates_overlay: Optional[bool] = None

    assistant_personality: Optional[str] = None
    behavioral_preset: Optional[str] = None
    response_style: Optional[str] = None
    response_length: Optional[str] = None
    creativity_level: Optional[float] = None
    temperature: Optional[float] = None
    default_model: Optional[str] = None
    neural_backbone: Optional[str] = None
    streaming_responses: Optional[bool] = None
    streaming_token_telemetry: Optional[bool] = None
    context_awareness: Optional[int] = None
    context_budget: Optional[int] = None
    auto_verification: Optional[bool] = None
    multi_turn_reasoning: Optional[bool] = None
    reasoning_depth: Optional[int] = None

    memory_enabled: Optional[bool] = None
    persistent_memory: Optional[bool] = None
    automatic_memory: Optional[bool] = None
    autonomous_ingestion: Optional[bool] = None
    memory_importance_threshold: Optional[int] = None
    similarity_threshold: Optional[int] = None
    conversation_retention: Optional[str] = None

    task_notifications: Optional[bool] = None
    notify_task_completion: Optional[bool] = None
    project_notifications: Optional[bool] = None
    ai_notifications: Optional[bool] = None
    notify_escalations: Optional[bool] = None
    system_notifications: Optional[bool] = None
    notify_telemetry_anomalies: Optional[bool] = None
    activity_notifications: Optional[bool] = None
    desktop_notifications: Optional[bool] = None
    notify_security_broadcast: Optional[bool] = None
    notify_audio_ping: Optional[bool] = None

    color_accent: Optional[str] = None
    glow_intensity: Optional[int] = None
    animation_intensity: Optional[bool] = None
    particle_vfx: Optional[bool] = None
    glassmorphism: Optional[bool] = None
    sidebar_behavior: Optional[str] = None

    isolated_docker_sandbox: Optional[bool] = None
    tool_execution_policy: Optional[str] = None
    emergency_sandbox: Optional[bool] = None
    privacy_preferences: Optional[bool] = None

    voice_enabled: Optional[bool] = None
    voice_name: Optional[str] = None
    voice_rate: Optional[float] = None
    voice_pitch: Optional[float] = None
    voice_volume: Optional[float] = None

    wake_word_enabled: Optional[bool] = None
    wake_phrase: Optional[str] = None
    wake_response: Optional[str] = None
    command_timeout: Optional[int] = None
    follow_up_timeout: Optional[int] = None
    auto_resume_listening: Optional[bool] = None
    wake_word_sensitivity: Optional[float] = None
    wake_word_provider: Optional[str] = None

    local_agent_enabled: Optional[bool] = None
    local_agent_confirmation_required: Optional[bool] = None
    local_agent_heartbeat_interval: Optional[int] = None
    local_agent_device_name: Optional[str] = None

    vision_enabled: Optional[bool] = None
    screen_understanding_enabled: Optional[bool] = None
    ocr_enabled: Optional[bool] = None
    speak_vision_responses: Optional[bool] = None
    vision_privacy_mode: Optional[bool] = None

    extra_params: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(extra="ignore")


class SystemStatusResponse(BaseModel):
    api: str = "ONLINE"
    database: str = "CONNECTED"
    backend: str = "ONLINE"
    environment: str = "development"
    ai_engine: str = "STANDBY"
    kernel_version: str = "Linux 6.8.0-jarvis-rt-x86_64 // v4.2.1-SEC"
    settings_endpoint: str = "/api/v1/settings"
    memory_pool: str = "4.2 GB / 16.0 GB ALLOCATED"
    worker_threads: str = "16 THREADS ACTIVE (ASYNC IO)"
    latency_ms: int = 12
    uptime_percentage: float = 99.98
    build_version: str = "2025.02.18-REL"


# Canonical aliases
SettingsResponse = SystemSettings
SettingsUpdate = SystemSettingsUpdate
SettingResponse = SettingItemResponse
SettingUpdate = SettingItemUpdate
TelemetrySummary = SystemStatusResponse
