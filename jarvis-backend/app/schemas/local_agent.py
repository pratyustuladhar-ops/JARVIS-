from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class LocalAgentRegisterRequest(BaseModel):
    device_name: str = Field(..., description="Unique device callsign e.g. JARVIS-WINDOWS-01")
    platform: str = Field(default="Windows", description="Operating system platform")
    version: str = Field(default="1.0.0", description="Agent release version")
    auth_token: str = Field(..., description="Authentication secret for device identity")
    port: int = Field(default=8001, description="Local loopback execution port")
    available_tools: List[str] = Field(default_factory=list, description="List of allowlisted tools")
    system_info: Optional[Dict[str, Any]] = Field(default=None, description="Basic hardware & OS telemetry")


class LocalAgentHeartbeatRequest(BaseModel):
    device_name: str
    auth_token: str
    status: str = "ONLINE"
    metrics: Optional[Dict[str, Any]] = None


import json
from pydantic import BaseModel, ConfigDict, Field, field_validator


class LocalAgentDeviceResponse(BaseModel):
    id: int
    device_name: str
    status: str
    platform: str
    version: str
    port: Optional[int] = 8001
    available_tools: List[str] = []
    system_info: Optional[Dict[str, Any]] = None
    last_heartbeat: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    @field_validator("available_tools", mode="before")
    @classmethod
    def parse_tools(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return v or []

    @field_validator("system_info", mode="before")
    @classmethod
    def parse_system_info(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return None
        return v

    model_config = ConfigDict(from_attributes=True)


class LocalAgentStatusResponse(BaseModel):
    is_online: bool
    status: str  # ONLINE, OFFLINE, UNKNOWN
    device_name: str
    platform: str
    version: str
    last_heartbeat: Optional[datetime] = None
    available_tools: List[str] = []
    total_devices: int = 0


class LocalToolExecutionRequest(BaseModel):
    tool: str
    parameters: Dict[str, Any] = {}
    device_name: Optional[str] = None
    auth_token: Optional[str] = None


class LocalToolExecutionResponse(BaseModel):
    status: str  # SUCCESS, FAILED, DENIED
    tool: str
    output: Any = None
    verified: bool = False
    detail: Optional[str] = None
    error: Optional[str] = None
