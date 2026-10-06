from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.cms import CMSConfigCreate, CMSConfigUpdate, CMSConfigResponse
from app.services.cms_service import cms_service

router = APIRouter()


@router.get("/config", response_model=List[CMSConfigResponse], summary="List all CMS configurations")
def get_cms_configs(category: Optional[str] = None, only_active: bool = True, db: Session = Depends(get_db)):
    """Retrieves dynamic configuration elements for UI and agent customization."""
    return cms_service.get_all(db, category=category, only_active=only_active)


@router.get("/content", response_model=Dict[str, Any], summary="Get grouped CMS content map")
def get_cms_content_map(db: Session = Depends(get_db)):
    """Returns all active CMS configuration values organized by category for the frontend."""
    return cms_service.get_content_map(db)


@router.post("/config", response_model=CMSConfigResponse, status_code=status.HTTP_201_CREATED, summary="Create or upsert CMS config")
def create_cms_config(config_in: CMSConfigCreate, db: Session = Depends(get_db)):
    return cms_service.create(db, config_in)


@router.put("/config/{config_id}", response_model=CMSConfigResponse, summary="Update CMS config")
def update_cms_config(config_id: int, config_in: CMSConfigUpdate, db: Session = Depends(get_db)):
    updated = cms_service.update(db, config_id, config_in)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"CMS Config #{config_id} not found."
        )
    return updated


@router.delete("/config/{config_id}", status_code=status.HTTP_200_OK, summary="Delete CMS config")
def delete_cms_config(config_id: int, db: Session = Depends(get_db)):
    success = cms_service.delete(db, config_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"CMS Config #{config_id} not found."
        )
    return {"message": f"CMS Config #{config_id} successfully deleted."}
