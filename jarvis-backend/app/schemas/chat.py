from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, ConfigDict


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None
    context_token: Optional[str] = None


class ChatResponse(BaseModel):
    message: str
    intent: str
    plan: List[str]
    tool: Optional[str] = None
    status: str
    verified: bool
    conversation_id: Optional[int] = None
    context_token: Optional[str] = None
    memory_accessed: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    intent: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationResponse(BaseModel):
    id: int
    title: str
    context_token: str
    created_at: datetime
    updated_at: datetime
    messages: List[MessageResponse] = []

    model_config = ConfigDict(from_attributes=True)
