from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Dict, Any
from app.core.database import get_db
from app.services.dashboard_service import dashboard_service

router = APIRouter()


@router.get("", response_model=Dict[str, Any], summary="Get Command Center Dashboard Telemetry")
def get_dashboard_telemetry(db: Session = Depends(get_db)):
    """
    Returns full telemetry required for the JARVIS HUD Command Center dashboard,
    including agent status, active tasks, project matrix, AI cognitive insight,
    and real-time system metrics.
    """
    return dashboard_service.get_dashboard_data(db)
