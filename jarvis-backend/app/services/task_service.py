from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskUpdate


class TaskService:
    def get_all(self, db: Session, skip: int = 0, limit: int = 50) -> List[Task]:
        return db.query(Task).order_by(Task.updated_at.desc()).offset(skip).limit(limit).all()

    def get_by_id(self, db: Session, task_id: int) -> Optional[Task]:
        return db.query(Task).filter(Task.id == task_id).first()

    def create(self, db: Session, task_in: TaskCreate) -> Task:
        task = Task(**task_in.model_dump())
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    def update(self, db: Session, task_id: int, task_in: TaskUpdate) -> Optional[Task]:
        task = self.get_by_id(db, task_id)
        if not task:
            return None
        update_data = task_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(task, field, value)
        db.commit()
        db.refresh(task)
        return task

    def delete(self, db: Session, task_id: int) -> bool:
        task = self.get_by_id(db, task_id)
        if not task:
            return False
        db.delete(task)
        db.commit()
        return True


task_service = TaskService()
