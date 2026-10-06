from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from app.core.database import Base


class CMSConfig(Base):
    """
    CMS / Dynamic Admin Configuration Model
    Allows administrators to dynamically manage the JARVIS system, dashboard contents,
    quick actions, navigation, AI prompts, and feature flags without code modifications.
    """
    __tablename__ = "cms_configs"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(150), unique=True, index=True, nullable=False)
    value = Column(Text, nullable=False)
    type = Column(String(50), default="string")  # string, number, boolean, json, markdown
    category = Column(String(100), default="general", index=True)
    # categories: general, dashboard, assistant, ai, navigation, quick_actions, feature_flags, announcements
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
