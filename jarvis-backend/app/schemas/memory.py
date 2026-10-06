from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class MemoryBase(BaseModel):
    content: str
    memory_type: Optional[str] = "PREFERENCE"
    importance: Optional[float] = 0.5
    relevance_score: Optional[float] = 1.0
    embedding_id: Optional[str] = None
    tags: Optional[str] = None
    metadata_json: Optional[str] = None


class MemoryCreate(MemoryBase):
    pass


class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    memory_type: Optional[str] = None
    importance: Optional[float] = None
    relevance_score: Optional[float] = None
    embedding_id: Optional[str] = None
    tags: Optional[str] = None
    metadata_json: Optional[str] = None


class MemoryResponse(MemoryBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
