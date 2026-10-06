from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime
from app.core.database import Base


class Memory(Base):
    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    memory_type = Column(String(50), default="PREFERENCE", index=True)  # FACT, PREFERENCE, CODEBASE, EPISODIC, SEMANTIC
    importance = Column(Float, default=0.5)                             # 0.0 - 1.0 scale
    relevance_score = Column(Float, default=1.0)                        # 0.0 - 1.0 match score
    embedding_id = Column(String(255), nullable=True)                  # Pointer for future vector DB / embeddings
    tags = Column(String(255), nullable=True)                          # Comma-separated or JSON tags
    metadata_json = Column(Text, nullable=True)                        # Contextual metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
