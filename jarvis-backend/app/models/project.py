from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.core.database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="ACTIVE", index=True)  # ACTIVE, PAUSED, COMPLETED
    progress = Column(Integer, default=0)                      # 0 - 100 percentage
    repo_path = Column(String(500), nullable=True)             # e.g. "/workspace/java-core-engine"
    technologies = Column(String(255), nullable=True)          # e.g. "Java, Spring Boot, PostgreSQL"
    file_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
