from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.memory import Memory
from app.schemas.memory import MemoryCreate, MemoryUpdate


class MemoryService:
    def get_all(self, db: Session, skip: int = 0, limit: int = 50) -> List[Memory]:
        return db.query(Memory).order_by(Memory.importance.desc(), Memory.created_at.desc()).offset(skip).limit(limit).all()

    def get_by_id(self, db: Session, memory_id: int) -> Optional[Memory]:
        return db.query(Memory).filter(Memory.id == memory_id).first()

    def create(self, db: Session, mem_in: MemoryCreate) -> Memory:
        memory = Memory(**mem_in.model_dump())
        db.add(memory)
        db.commit()
        db.refresh(memory)
        return memory

    def update(self, db: Session, memory_id: int, mem_in: MemoryUpdate) -> Optional[Memory]:
        memory = self.get_by_id(db, memory_id)
        if not memory:
            return None
        update_data = mem_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(memory, field, value)
        db.commit()
        db.refresh(memory)
        return memory

    def delete(self, db: Session, memory_id: int) -> bool:
        memory = self.get_by_id(db, memory_id)
        if not memory:
            return False
        db.delete(memory)
        db.commit()
        return True


memory_service = MemoryService()
