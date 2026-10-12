import sys
import json
import hmac
import logging
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timedelta, timezone
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

BACKEND_TO_LOCAL_TOOL_MAP: Dict[str, str] = {
    "local_open_application": "open_application",
    "open_application": "open_application",
    "local_open_url": "open_url",
    "open_url": "open_url",
    "local_get_system_info": "get_system_info",
    "get_system_info": "get_system_info",
    "local_get_current_time": "get_current_time",
    "get_current_time": "get_current_time",
    "local_list_directory": "list_allowed_directory",
    "list_allowed_directory": "list_allowed_directory",
    "local_open_file": "open_file",
    "open_file": "open_file",
    "local_open_folder": "open_folder",
    "open_folder": "open_folder",
    "local_capture_screen": "capture_screen",
    "capture_screen": "capture_screen",
}


class LocalAgentService:
    """
    Backend coordination service for Windows Local Agents:
    Manages registration, heartbeat monitoring, offline detection, and safe tool routing.
    """

    HEARTBEAT_TIMEOUT = timedelta(seconds=35)

    def register_device(self, db: Session, req: LocalAgentRegisterRequest) -> LocalAgentDevice:
        # Enforce authentication against configured local agent token
        configured_token = getattr(settings, "LOCAL_AGENT_TOKEN", "jarvis_windows_local_agent_secret_2026").strip()
        provided_token = (req.auth_token or "").strip()
        if not hmac.compare_digest(provided_token, configured_token):
            logger.warning(f"Registration failed for '{req.device_name}': invalid authentication token.")
            raise ValueError("Invalid authentication token.")

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
                auth_token_hash=provided_token,
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
            device.auth_token_hash = provided_token
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

        configured_token = getattr(settings, "LOCAL_AGENT_TOKEN", "jarvis_windows_local_agent_secret_2026").strip()
        provided_token = (hb.auth_token or "").strip()
        device_token = (device.auth_token_hash or "").strip()

        token_valid = hmac.compare_digest(provided_token, device_token) or hmac.compare_digest(provided_token, configured_token)
        if not token_valid:
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

    def get_status(self, db: Session, probe_bridge: bool = False) -> LocalAgentStatusResponse:
        """
        Determines if local agent is active and online based on recent authenticated heartbeat.
        Does NOT report ONLINE without an actual authenticated heartbeat within timeout.
        Evicts SQLAlchemy session cache to prevent stale heartbeat reads across execution steps.
        """
        db.expire_all()
        device = db.query(LocalAgentDevice).order_by(
            LocalAgentDevice.last_heartbeat.desc().nullslast(),
            LocalAgentDevice.updated_at.desc()
        ).first()
        total_devices = db.query(LocalAgentDevice).count()
        timeout_sec = getattr(settings, "LOCAL_AGENT_HEARTBEAT_TIMEOUT_SECONDS", 35)

        if not device or not device.last_heartbeat:
            return LocalAgentStatusResponse(
                is_online=False,
                status="OFFLINE",
                device_name="NO_DEVICE_REGISTERED",
                platform="Windows",
                version="1.0.0",
                last_heartbeat=None,
                available_tools=[],
                total_devices=total_devices,
                connection_error="No registered device with valid heartbeat found.",
                heartbeat_timeout_seconds=timeout_sec,
                seconds_since_last_heartbeat=None
            )

        now = datetime.utcnow()
        last_hb = device.last_heartbeat
        if last_hb and last_hb.tzinfo is not None:
            last_hb = last_hb.astimezone(timezone.utc).replace(tzinfo=None)

        seconds_since = (now - last_hb).total_seconds() if last_hb else None
        is_fresh = bool(seconds_since is not None and 0 <= seconds_since <= timeout_sec)
        is_online = (device.status == "ONLINE") and is_fresh
        connection_error = None

        # Probe healthy loopback bridge if heartbeat timed out during execution to prevent false drops
        if probe_bridge and (not is_online or not is_fresh) and device.status != "OFFLINE":
            port = device.port if device and device.port else getattr(settings, "LOCAL_AGENT_PORT", 8001)
            token = getattr(settings, "LOCAL_AGENT_TOKEN", "jarvis_windows_local_agent_secret_2026").strip()
            try:
                probe_req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/status",
                    headers={"X-Local-Agent-Token": token},
                    method="GET"
                )
                with urllib.request.urlopen(probe_req, timeout=1.5) as resp:
                    if 200 <= resp.status < 300:
                        bridge_data = json.loads(resp.read().decode("utf-8"))
                        if bridge_data.get("status") == "ONLINE":
                            device.status = "ONLINE"
                            device.last_heartbeat = datetime.utcnow()
                            db.commit()
                            is_online = True
                            seconds_since = 0.0
                            connection_error = None
            except Exception as ex:
                connection_error = f"Loopback status probe on port {port} failed: {ex}"
        elif not is_online:
            if not is_fresh and seconds_since is not None:
                connection_error = f"Heartbeat expired: {int(seconds_since)}s elapsed (timeout: {timeout_sec}s)."
            else:
                connection_error = f"Agent status is {device.status}."

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
            total_devices=total_devices,
            connection_error=connection_error,
            heartbeat_timeout_seconds=timeout_sec,
            seconds_since_last_heartbeat=round(seconds_since, 2) if seconds_since is not None else None
        )

    def get_devices(self, db: Session) -> List[LocalAgentDeviceResponse]:
        db.expire_all()
        devices = db.query(LocalAgentDevice).all()
        now = datetime.utcnow()
        timeout_sec = getattr(settings, "LOCAL_AGENT_HEARTBEAT_TIMEOUT_SECONDS", 35)
        results = []
        for d in devices:
            last_hb = d.last_heartbeat
            if last_hb and last_hb.tzinfo is not None:
                last_hb = last_hb.astimezone(timezone.utc).replace(tzinfo=None)
            is_fresh = bool(last_hb and (now - last_hb).total_seconds() <= timeout_sec)
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
        Translates backend registry tool names to agent approved names and enforces verification.
        """
        resolved_tool = BACKEND_TO_LOCAL_TOOL_MAP.get(tool_name, tool_name)
        status_info = self.get_status(db, probe_bridge=True)

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
        port = device.port if device and device.port else getattr(settings, "LOCAL_AGENT_PORT", 8001)
        token = getattr(settings, "LOCAL_AGENT_TOKEN", "jarvis_windows_local_agent_secret_2026").strip()

        # Attempt 1: Call loopback server on 127.0.0.1:{port}
        res_data = None
        try:
            url = f"http://127.0.0.1:{port}/execute"
            payload = json.dumps({"tool": resolved_tool, "parameters": parameters}).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Local-Agent-Token": token
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if 200 <= resp.status < 300:
                    res_data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as he:
            try:
                res_data = json.loads(he.read().decode("utf-8"))
            except Exception:
                res_data = {
                    "status": "DENIED" if he.code in (401, 403) else "FAILED",
                    "tool": resolved_tool,
                    "verified": False,
                    "error": f"HTTP {he.code}: {he.reason}"
                }
        except Exception as e:
            logger.info(f"Loopback HTTP bridge failed ({e}), attempting direct agent runner...")

        # Attempt 2: If loopback HTTP did not answer, use in-process WindowsLocalAgent instance
        if not res_data:
            try:
                from local_agent.agent import windows_local_agent
                res_data = windows_local_agent.execute_action(resolved_tool, parameters, auth_token=token)
            except Exception as ex:
                res_data = {
                    "status": "FAILED",
                    "tool": resolved_tool,
                    "verified": False,
                    "error": f"Failed reaching local agent execution bridge: {ex}"
                }

        is_verified = res_data.get("verified", False)
        status_str = res_data.get("status", "FAILED")
        if status_str == "SUCCESS" and not is_verified:
            status_str = "FAILED"

        # Activity logging based on outcome
        if status_str == "SUCCESS":
            activity_service.record_activity(
                db=db,
                event_type="LOCAL_TOOL_EXECUTED",
                title=f"Local Tool Executed: {tool_name}",
                description=f"Action '{tool_name}' successfully executed on Windows.",
                status="SUCCESS"
            )
            activity_service.record_activity(
                db=db,
                event_type="LOCAL_TOOL_VERIFIED",
                title=f"Local Tool Verified: {tool_name}",
                description=res_data.get("detail", f"Verified execution of '{tool_name}'."),
                status="SUCCESS"
            )
        elif status_str == "DENIED":
            activity_service.record_activity(
                db=db,
                event_type="LOCAL_TOOL_DENIED",
                title=f"Local Tool Denied: {tool_name}",
                description=res_data.get("error", f"Permission denied for '{tool_name}'."),
                status="WARNING"
            )
        else:
            activity_service.record_activity(
                db=db,
                event_type="LOCAL_TOOL_FAILED",
                title=f"Local Tool Failed: {tool_name}",
                description=res_data.get("error") or res_data.get("detail") or f"Action '{tool_name}' failed.",
                status="ERROR"
            )

        return LocalToolExecutionResponse(
            status=status_str,
            tool=tool_name,
            output=res_data.get("output"),
            verified=is_verified,
            detail=res_data.get("detail"),
            error=res_data.get("error")
        )


local_agent_service = LocalAgentService()
