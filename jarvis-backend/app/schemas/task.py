from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    status: Optional[str] = "AI WORKING"
    priority: Optional[str] = "MEDIUM"
    due_date: Optional[datetime] = None
    progress: Optional[int] = 0
    eta: Optional[str] = None
    category: Optional[str] = "General"


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[datetime] = None
    progress: Optional[int] = None
    eta: Optional[str] = None
    category: Optional[str] = None


class TaskResponse(TaskBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
