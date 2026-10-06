from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse
from app.services.project_service import project_service

router = APIRouter()


@router.get("", response_model=List[ProjectResponse], summary="List all projects")
def get_projects(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return project_service.get_all(db, skip=skip, limit=limit)


@router.get("/{project_id}", response_model=ProjectResponse, summary="Get project by ID")
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = project_service.get_by_id(db, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project #{project_id} not found."
        )
    return project


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED, summary="Create project")
def create_project(proj_in: ProjectCreate, db: Session = Depends(get_db)):
    return project_service.create(db, proj_in)


@router.put("/{project_id}", response_model=ProjectResponse, summary="Update project")
def update_project(project_id: int, proj_in: ProjectUpdate, db: Session = Depends(get_db)):
    project = project_service.update(db, project_id, proj_in)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project #{project_id} not found."
        )
    return project


@router.delete("/{project_id}", status_code=status.HTTP_200_OK, summary="Delete project")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    success = project_service.delete(db, project_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project #{project_id} not found."
        )
    return {"message": f"Project #{project_id} successfully deleted."}
