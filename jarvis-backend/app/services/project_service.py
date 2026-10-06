from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectUpdate


class ProjectService:
    def get_all(self, db: Session, skip: int = 0, limit: int = 50) -> List[Project]:
        return db.query(Project).order_by(Project.updated_at.desc()).offset(skip).limit(limit).all()

    def get_by_id(self, db: Session, project_id: int) -> Optional[Project]:
        return db.query(Project).filter(Project.id == project_id).first()

    def create(self, db: Session, proj_in: ProjectCreate) -> Project:
        project = Project(**proj_in.model_dump())
        db.add(project)
        db.commit()
        db.refresh(project)
        return project

    def update(self, db: Session, project_id: int, proj_in: ProjectUpdate) -> Optional[Project]:
        project = self.get_by_id(db, project_id)
        if not project:
            return None
        update_data = proj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(project, field, value)
        db.commit()
        db.refresh(project)
        return project

    def delete(self, db: Session, project_id: int) -> bool:
        project = self.get_by_id(db, project_id)
        if not project:
            return False
        db.delete(project)
        db.commit()
        return True


project_service = ProjectService()
