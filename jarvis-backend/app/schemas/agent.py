from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class AgentMessageRequest(BaseModel):
    message: str = Field(..., description="User command or conversational query")
    conversation_id: Optional[int] = Field(None, description="Existing conversation session ID")
    input_type: str = Field("text", description="Input modality: text, voice, image, multimodal")
    image_data: Optional[str] = Field(None, description="Base64 encoded image or data URI")
    image_metadata: Optional[Dict[str, Any]] = Field(None, description="Metadata such as filename, mime_type")


class MultimodalMessageRequest(BaseModel):
    message: Optional[str] = Field("", description="Accompanying user prompt or question")
    content: Optional[str] = Field(None, description="Alternative field name for message/prompt")
    input_type: str = Field("multimodal", description="Modality type: image, voice, text, multimodal")
    image_data: Optional[str] = Field(None, description="Base64 encoded image string or data URI")
    conversation_id: Optional[int] = Field(None, description="Existing conversation session ID")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Image metadata (dimensions, filename, mime_type)")



class PlanStepSchema(BaseModel):
    step_number: int
    tool_name: Optional[str] = None
    risk_level: str = "LOW_RISK"
    status: str = "PENDING"


class ToolActionSchema(BaseModel):
    tool_name: str
    status: str
    output: Optional[Any] = None
    duration_ms: Optional[float] = None
    error: Optional[str] = None


class VerificationSchema(BaseModel):
    status: str  # VERIFIED, FAILED, NOT_APPLICABLE
    tool: str
    entity_id: Optional[Any] = None
    detail: Optional[str] = None


class AgentMessageResponse(BaseModel):
    response: str
    intent: str
    confidence: float
    plan: List[Dict[str, Any]] = []
    actions: List[Dict[str, Any]] = []
    verification: List[Dict[str, Any]] = []
    verified: bool = True
    conversation_id: Optional[int] = None
    execution_time_ms: float = 0.0
    agent_state: str = "RESPONDING"  # THINKING, EXECUTING, VERIFYING, RESPONDING, ERROR
    plan_id: Optional[str] = None
    success: Optional[bool] = None
    completed_steps: Optional[int] = None
    total_steps: Optional[int] = None
    failed_step: Optional[int] = None
    steps: Optional[List[Dict[str, Any]]] = None
    requires_clarification: Optional[bool] = None
    slots: Optional[Dict[str, Any]] = None


class IntentResult(BaseModel):
    intent: str
    confidence: float
    entities: Dict[str, Any] = {}
    raw_input: str


class PlanStep(BaseModel):
    step_number: int
    name: str
    description: str
    tool: Optional[str] = None
    status: str = "PENDING"


class ToolExecutionResult(BaseModel):
    tool_name: str
    status: str
    output: Any
    duration_ms: Optional[float] = None
    error: Optional[str] = None


class AgentPipelineStatus(BaseModel):
    stage: str
    stage_number: int
    total_stages: int = 6
    is_active: bool = False
    details: Dict[str, Any] = {}
