from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.memory import MemoryCreate, MemoryUpdate, MemoryResponse
from app.services.memory_service import memory_service

router = APIRouter()


@router.get("", response_model=List[MemoryResponse], summary="List stored memories")
def get_memories(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return memory_service.get_all(db, skip=skip, limit=limit)


@router.get("/{memory_id}", response_model=MemoryResponse, summary="Get memory by ID")
def get_memory(memory_id: int, db: Session = Depends(get_db)):
    memory = memory_service.get_by_id(db, memory_id)
    if not memory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory #{memory_id} not found."
        )
    return memory


@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED, summary="Create memory")
def create_memory(mem_in: MemoryCreate, db: Session = Depends(get_db)):
    return memory_service.create(db, mem_in)


@router.put("/{memory_id}", response_model=MemoryResponse, summary="Update memory")
def update_memory(memory_id: int, mem_in: MemoryUpdate, db: Session = Depends(get_db)):
    memory = memory_service.update(db, memory_id, mem_in)
    if not memory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory #{memory_id} not found."
        )
    return memory


@router.delete("/{memory_id}", status_code=status.HTTP_200_OK, summary="Delete memory")
def delete_memory(memory_id: int, db: Session = Depends(get_db)):
    success = memory_service.delete(db, memory_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory #{memory_id} not found."
        )
    return {"message": f"Memory #{memory_id} successfully deleted."}
