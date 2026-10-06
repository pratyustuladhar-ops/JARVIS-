from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.core.database import Base


class LocalAgentDevice(Base):
    __tablename__ = "local_agent_devices"

    id = Column(Integer, primary_key=True, index=True)
    device_name = Column(String(100), unique=True, index=True, nullable=False)
    status = Column(String(50), default="OFFLINE", nullable=False)  # ONLINE, OFFLINE, UNKNOWN
    platform = Column(String(50), default="Windows", nullable=False)
    version = Column(String(50), default="1.0.0", nullable=False)
    auth_token_hash = Column(String(255), nullable=True)
    ip_address = Column(String(100), nullable=True)
    port = Column(Integer, default=8001, nullable=True)
    available_tools = Column(Text, nullable=True)  # JSON list
    system_info = Column(Text, nullable=True)      # JSON dict
    last_heartbeat = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
