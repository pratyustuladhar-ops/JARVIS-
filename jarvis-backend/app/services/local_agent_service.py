import sys
import json
import logging
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

# Ensure parent directory containing local_agent is in sys.path
_repo_root = Path(__file__).resolve().parent.parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from app.models.local_agent import LocalAgentDevice
from app.schemas.local_agent import (
    LocalAgentRegisterRequest,
    LocalAgentHeartbeatRequest,
    LocalAgentDeviceResponse,
    LocalAgentStatusResponse,
    LocalToolExecutionResponse
)
from app.services.activity_service import activity_service
from app.core.config import settings

logger = logging.getLogger("jarvis.services.local_agent")


class LocalAgentService:
    """
    Backend coordination service for Windows Local Agents:
    Manages registration, heartbeat monitoring, offline detection, and safe tool routing.
    """

    HEARTBEAT_TIMEOUT = timedelta(seconds=35)

    def register_device(self, db: Session, req: LocalAgentRegisterRequest) -> LocalAgentDevice:
        device = db.query(LocalAgentDevice).filter(LocalAgentDevice.device_name == req.device_name).first()
        tools_json = json.dumps(req.available_tools)
        sys_info_json = json.dumps(req.system_info) if req.system_info else None

        is_new = (device is None)
        if is_new:
            device = LocalAgentDevice(
                device_name=req.device_name,
                status="ONLINE",
                platform=req.platform,
                version=req.version,
                auth_token_hash=req.auth_token,
                port=req.port,
                available_tools=tools_json,
                system_info=sys_info_json,
                last_heartbeat=datetime.utcnow()
            )
            db.add(device)
        else:
            device.status = "ONLINE"
            device.platform = req.platform
            device.version = req.version
            device.auth_token_hash = req.auth_token
            device.port = req.port
            device.available_tools = tools_json
            if sys_info_json:
                device.system_info = sys_info_json
            device.last_heartbeat = datetime.utcnow()

        db.commit()
        db.refresh(device)

        # Log Activity (REGISTERED for new device, CONNECTED for reconnecting)
        event_name = "LOCAL_AGENT_REGISTERED" if is_new else "LOCAL_AGENT_CONNECTED"
        activity_service.record_activity(
            db=db,
            event_type=event_name,
            title=f"Local Agent {'Registered' if is_new else 'Connected'}: {req.device_name}",
            description=f"Windows Local Agent v{req.version} authenticated on port {req.port}.",
            status="SUCCESS",
            metadata_json=json.dumps({
                "device_name": req.device_name,
                "platform": req.platform,
                "tools_count": len(req.available_tools)
            })
        )
        return device

    def generate_registration_token(self, db: Session) -> str:
        """Generates a secure registration credential token for a local agent."""
        import secrets
        return f"jarvis_token_{secrets.token_urlsafe(24)}"

    def record_heartbeat(self, db: Session, hb: LocalAgentHeartbeatRequest) -> bool:
        device = db.query(LocalAgentDevice).filter(LocalAgentDevice.device_name == hb.device_name).first()
        if not device:
            return False

        if hb.auth_token != device.auth_token_hash:
            logger.warning(f"Heartbeat token mismatch for {hb.device_name}")
            return False

        old_status = device.status
        device.status = hb.status
        device.last_heartbeat = datetime.utcnow()
        db.commit()

        if hb.status == "OFFLINE" and old_status != "OFFLINE":
            activity_service.record_activity(
                db=db,
                event_type="LOCAL_AGENT_DISCONNECTED",
                title=f"Local Agent Disconnected: {hb.device_name}",
                description=f"Local agent {hb.device_name} reported offline or stopped heartbeat pulse.",
                status="WARNING",
                metadata_json=json.dumps({"device_name": hb.device_name})
            )

        return True

    def get_status(self, db: Session) -> LocalAgentStatusResponse:
        """
        Determines if local agent is active and online based on recent heartbeat.
        Does NOT report ONLINE without an actual heartbeat within timeout.
        """
        device = db.query(LocalAgentDevice).order_by(LocalAgentDevice.updated_at.desc()).first()
        total_devices = db.query(LocalAgentDevice).count()

        if not device or not device.last_heartbeat:
            return LocalAgentStatusResponse(
                is_online=False,
                status="OFFLINE",
                device_name="NO_DEVICE_REGISTERED",
                platform="Windows",
                version="1.0.0",
                last_heartbeat=None,
                available_tools=[],
                total_devices=total_devices
            )

        # Verify heartbeat threshold
        now = datetime.utcnow()
        is_fresh = (now - device.last_heartbeat) <= self.HEARTBEAT_TIMEOUT
        is_online = (device.status == "ONLINE") and is_fresh

        tools = []
        if device.available_tools:
            try:
                tools = json.loads(device.available_tools)
            except Exception:
                pass

        return LocalAgentStatusResponse(
            is_online=is_online,
            status="ONLINE" if is_online else "OFFLINE",
            device_name=device.device_name,
            platform=device.platform,
            version=device.version,
            last_heartbeat=device.last_heartbeat,
            available_tools=tools,
            total_devices=total_devices
        )

    def get_devices(self, db: Session) -> List[LocalAgentDeviceResponse]:
        devices = db.query(LocalAgentDevice).all()
        now = datetime.utcnow()
        results = []
        for d in devices:
            is_fresh = d.last_heartbeat and ((now - d.last_heartbeat) <= self.HEARTBEAT_TIMEOUT)
            stat = "ONLINE" if (d.status == "ONLINE" and is_fresh) else "OFFLINE"
            tools = []
            if d.available_tools:
                try:
                    tools = json.loads(d.available_tools)
                except Exception:
                    pass
            sys_info = None
            if d.system_info:
                try:
                    sys_info = json.loads(d.system_info)
                except Exception:
                    pass

            results.append(LocalAgentDeviceResponse(
                id=d.id,
                device_name=d.device_name,
                status=stat,
                platform=d.platform,
                version=d.version,
                port=d.port,
                available_tools=tools,
                system_info=sys_info,
                last_heartbeat=d.last_heartbeat,
                created_at=d.created_at,
                updated_at=d.updated_at
            ))
        return results

    def execute_tool(
        self,
        db: Session,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> LocalToolExecutionResponse:
        """
        Routes an approved local tool action to the connected Windows Local Agent.
        """
        status_info = self.get_status(db)

        # Check online status
        if not status_info.is_online:
            activity_service.record_activity(
                db=db,
                event_type="LOCAL_TOOL_DENIED",
                title=f"Local Tool Blocked: {tool_name}",
                description="Action blocked: Windows Local Agent is currently OFFLINE.",
                status="WARNING"
            )
            return LocalToolExecutionResponse(
                status="DENIED",
                tool=tool_name,
                verified=False,
                error=f"Windows Local Agent ({status_info.device_name}) is currently OFFLINE. Please start the agent."
            )

        # Record tool request
        activity_service.record_activity(
            db=db,
            event_type="LOCAL_TOOL_REQUESTED",
            title=f"Local Tool Requested: {tool_name}",
            description=f"Action '{tool_name}' dispatched to {status_info.device_name}.",
            status="INFO"
        )

        device = db.query(LocalAgentDevice).filter(LocalAgentDevice.device_name == status_info.device_name).first()
        port = device.port if device and device.port else 8001
        token = device.auth_token_hash if device else "jarvis_windows_local_agent_secret_2026"

        # Attempt 1: Call loopback server on 127.0.0.1:{port}
        res_data = None
        try:
            url = f"http://127.0.0.1:{port}/execute"
            payload = json.dumps({"tool": tool_name, "parameters": parameters}).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Local-Agent-Token": token
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                if 200 <= resp.status < 300:
                    res_data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.info(f"Loopback HTTP bridge failed ({e}), attempting direct agent runner...")

        # Attempt 2: If loopback HTTP did not answer, use in-process WindowsLocalAgent instance
        if not res_data:
            try:
                from local_agent.agent import windows_local_agent
                res_data = windows_local_agent.execute_action(tool_name, parameters, auth_token=token)
            except Exception as ex:
                res_data = {
                    "status": "FAILED",
                    "tool": tool_name,
                    "verified": False,
                    "error": f"Failed reaching local agent execution bridge: {ex}"
                }

        # Activity logging based on outcome
        if res_data.get("status") == "SUCCESS":
            activity_service.record_activity(
                db=db,
                event_type="LOCAL_TOOL_EXECUTED",
                title=f"Local Tool Executed: {tool_name}",
                description=f"Action '{tool_name}' successfully executed on Windows.",
                status="SUCCESS"
            )
            if res_data.get("verified"):
                activity_service.record_activity(
                    db=db,
                    event_type="LOCAL_TOOL_VERIFIED",
                    title=f"Local Tool Verified: {tool_name}",
                    description=res_data.get("detail", f"Verified execution of '{tool_name}'."),
                    status="SUCCESS"
                )
        elif res_data.get("status") == "DENIED":
            activity_service.record_activity(
                db=db,
                event_type="LOCAL_TOOL_DENIED",
                title=f"Local Tool Denied: {tool_name}",
                description=res_data.get("error", f"Permission denied for '{tool_name}'."),
                status="WARNING"
            )

        return LocalToolExecutionResponse(
            status=res_data.get("status", "FAILED"),
            tool=tool_name,
            output=res_data.get("output"),
            verified=res_data.get("verified", False),
            detail=res_data.get("detail"),
            error=res_data.get("error")
        )


local_agent_service = LocalAgentService()
