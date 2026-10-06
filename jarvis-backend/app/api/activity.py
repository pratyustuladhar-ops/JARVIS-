from typing import List, Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services.activity_service import activity_service

router = APIRouter()


@router.get("", response_model=List[Dict[str, Any]], summary="Get recent JARVIS activities")
def get_activities(limit: int = 15, db: Session = Depends(get_db)):
    """Returns the live audit stream and activity timeline."""
    activities = activity_service.get_recent(db, limit=limit)
    return [
        {
            "id": a.id,
            "event_type": a.event_type,
            "title": a.title,
            "description": a.description,
            "status": a.status,
            "timestamp": a.timestamp.isoformat(),
            "time": a.timestamp.strftime("%H:%M")
        }
        for a in activities
    ]
