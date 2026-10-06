from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class CMSConfigBase(BaseModel):
    key: str
    value: str
    type: Optional[str] = "string"  # string, number, boolean, json, markdown
    category: Optional[str] = "general"
    description: Optional[str] = None
    is_active: Optional[bool] = True


class CMSConfigCreate(CMSConfigBase):
    pass


class CMSConfigUpdate(BaseModel):
    value: Optional[str] = None
    type: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class CMSConfigResponse(CMSConfigBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
