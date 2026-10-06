from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.task import TaskCreate, TaskUpdate, TaskResponse
from app.services.task_service import task_service

router = APIRouter()


@router.get("", response_model=List[TaskResponse], summary="List all tasks")
def get_tasks(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return task_service.get_all(db, skip=skip, limit=limit)


@router.get("/{task_id}", response_model=TaskResponse, summary="Get task by ID")
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = task_service.get_by_id(db, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task #{task_id} not found."
        )
    return task


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED, summary="Create task")
def create_task(task_in: TaskCreate, db: Session = Depends(get_db)):
    return task_service.create(db, task_in)


@router.put("/{task_id}", response_model=TaskResponse, summary="Update task")
def update_task(task_id: int, task_in: TaskUpdate, db: Session = Depends(get_db)):
    task = task_service.update(db, task_id, task_in)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task #{task_id} not found."
        )
    return task


@router.delete("/{task_id}", status_code=status.HTTP_200_OK, summary="Delete task")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    success = task_service.delete(db, task_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task #{task_id} not found."
        )
    return {"message": f"Task #{task_id} successfully deleted."}
