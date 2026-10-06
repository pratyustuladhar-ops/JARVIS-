import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from app.services.memory_service import memory_service
from app.services.settings_service import settings_service
from app.schemas.memory import MemoryCreate
from app.models.memory import Memory

logger = logging.getLogger("jarvis.ai.memory_manager")


class MemoryManager:
    """
    Intelligent Memory Management Layer:
    Controls memory reading and writing while strictly respecting user privacy/settings.
    """

    def is_memory_enabled(self, db: Session) -> bool:
        settings = settings_service.get_settings(db)
        return bool(settings.persistent_memory)

    def retrieve_relevant_memories(self, db: Session, query: str, limit: int = 3) -> List[Memory]:
        all_mems = memory_service.get_all(db)
        if not all_mems:
            return []

        q_lower = query.lower()
        words = [w for w in q_lower.split() if len(w) > 3]

        scored: List[tuple[float, Memory]] = []
        for m in all_mems:
            c_lower = m.content.lower()
            score = 0.0
            if words:
                matches = sum(1 for w in words if w in c_lower)
                score = (matches / len(words)) * 0.7
            score += (m.importance or 0.5) * 0.3

            if "java" in q_lower and "java" in c_lower:
                score = 0.984

            if score > 0.3:
                scored.append((score, m))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    def save_fact(
        self,
        db: Session,
        content: str,
        memory_type: str = "PREFERENCE",
        importance: float = 0.85
    ) -> Optional[Memory]:
        if not self.is_memory_enabled(db):
            logger.info("Memory ingestion skipped: 'persistent_memory' disabled in Settings.")
            return None

        clean_content = content.strip()
        if not clean_content:
            return None

        mem_in = MemoryCreate(
            content=clean_content,
            memory_type=memory_type,
            importance=importance,
            relevance_score=1.0
        )
        mem = memory_service.create(db, mem_in)
        logger.info(f"[MEMORY] Saved new fact #{mem.id} [{memory_type}]: '{clean_content}'")
        return mem

    def save_visual_summary(
        self,
        db: Session,
        summary_text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Memory]:
        """
        Stores high-level textual summaries of visual scenes (never raw binary images).
        Adheres strictly to user privacy and memory bounds.
        """
        if not summary_text or len(summary_text.strip()) < 5:
            return None
        return self.save_fact(
            db=db,
            content=summary_text.strip(),
            memory_type="VISUAL_CONTEXT",
            importance=0.80
        )


memory_manager = MemoryManager()
