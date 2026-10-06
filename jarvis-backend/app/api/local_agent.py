import logging
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.local_agent_service import local_agent_service
from app.schemas.local_agent import (
    LocalAgentRegisterRequest,
    LocalAgentHeartbeatRequest,
    LocalAgentDeviceResponse,
    LocalAgentStatusResponse,
    LocalToolExecutionRequest,
    LocalToolExecutionResponse
)

logger = logging.getLogger("jarvis.api.local_agent")
router = APIRouter()


@router.post("/token", summary="Generate Secure Agent Registration Token")
def generate_agent_token(
    db: Session = Depends(get_db)
):
    """
    Generates a secure registration credential token for a new Windows Local Agent.
    """
    token = local_agent_service.generate_registration_token(db)
    return {"token": token, "expires_in": 3600, "token_type": "Bearer"}


@router.post("/register", response_model=LocalAgentDeviceResponse, summary="Register Windows Local Agent")
def register_local_agent(
    req: LocalAgentRegisterRequest,
    db: Session = Depends(get_db)
):
    """
    Registers a local Windows agent device with JARVIS Core.
    Sets status to ONLINE upon successful registration.
    """
    device = local_agent_service.register_device(db, req)
    return device


@router.post("/heartbeat", summary="Record Agent Heartbeat Pulse")
def record_heartbeat(
    hb: LocalAgentHeartbeatRequest,
    db: Session = Depends(get_db)
):
    """
    Records periodic heartbeat pulse from Windows Local Agent.
    Updates last_heartbeat timestamp and status.
    """
    success = local_agent_service.record_heartbeat(db, hb)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Heartbeat authentication failed or device not recognized."
        )
    return {"status": "ACK", "device_name": hb.device_name}


@router.get("/status", response_model=LocalAgentStatusResponse, summary="Get Local Agent Status")
def get_local_agent_status(
    db: Session = Depends(get_db)
):
    """
    Reports whether the Windows Local Agent is currently ONLINE or OFFLINE.
    Does NOT report ONLINE without an active heartbeat in the last 35 seconds.
    """
    return local_agent_service.get_status(db)


@router.get("/devices", response_model=List[LocalAgentDeviceResponse], summary="List Registered Local Agents")
def list_local_devices(
    db: Session = Depends(get_db)
):
    """
    Lists all local agent devices registered in the JARVIS cluster for Admin Panel inspection.
    """
    return local_agent_service.get_devices(db)


@router.post("/execute", response_model=LocalToolExecutionResponse, summary="Execute Approved Local Tool")
def execute_local_tool(
    req: LocalToolExecutionRequest,
    db: Session = Depends(get_db)
):
    """
    Routes an approved computer-level tool to the connected Windows agent.
    Rejects unauthorized tools and returns verified execution outcome.
    """
    result = local_agent_service.execute_tool(db, req.tool, req.parameters)
    return result
