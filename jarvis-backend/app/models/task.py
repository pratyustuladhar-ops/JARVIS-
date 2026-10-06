from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.core.database import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="AI WORKING", index=True)  # AI WORKING, WAITING FOR INPUT, SCHEDULED, COMPLETED, PAUSED, CANCELLED
    priority = Column(String(30), default="MEDIUM", index=True)   # LOW, MEDIUM, HIGH, CRITICAL
    due_date = Column(DateTime, nullable=True)
    progress = Column(Integer, default=0)                         # 0 - 100 percentage
    eta = Column(String(100), nullable=True)                      # e.g. "~14m", "Queue: 18:00 UTC"
    category = Column(String(100), default="General")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
