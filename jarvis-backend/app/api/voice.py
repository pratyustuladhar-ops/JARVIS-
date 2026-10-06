import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional

from app.core.database import get_db
from app.voice.wake_word.schemas import WakeWordConfig, WakeWordEvent, WakeWordStatusResponse, ToggleWakeWordRequest
from app.voice.wake_word.service import wake_word_service

logger = logging.getLogger("jarvis.api.voice")
router = APIRouter()


@router.get("/wake-word/status", response_model=WakeWordStatusResponse, summary="Get hands-free wake word engine status")
def get_wake_word_status():
    """Returns current state machine status, active wake phrase, timeouts, and provider info."""
    return wake_word_service.get_status()


@router.post("/wake-word/toggle", response_model=WakeWordStatusResponse, summary="Toggle hands-free wake word listening")
def toggle_wake_word(
    request: Optional[ToggleWakeWordRequest] = None,
    enabled: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """Enables or disables hands-free wake word detection mode."""
    target_enabled = enabled if enabled is not None else (request.enabled if request is not None else False)
    return wake_word_service.set_enabled(db, target_enabled)


@router.post("/wake-word/event", response_model=Dict[str, Any], summary="Report hands-free voice event")
def log_wake_word_event(event: WakeWordEvent, db: Session = Depends(get_db)):
    """
    Records wake detection, command execution, or timeout events in the audit log.
    Strict privacy: Raw audio is rejected and never persisted.
    """
    return wake_word_service.record_event(db, event)
