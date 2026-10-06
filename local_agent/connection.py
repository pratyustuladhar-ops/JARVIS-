import time
import json
import logging
import threading
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

from local_agent.config import (
    BACKEND_URL,
    DEVICE_NAME,
    PLATFORM,
    AGENT_VERSION,
    HEARTBEAT_INTERVAL_SECONDS,
    LOCAL_SERVER_PORT
)
from local_agent.tools.system import get_system_info
from local_agent.authentication import get_auth_headers, get_agent_token
from local_agent.heartbeat import HeartbeatManager

logger = logging.getLogger("jarvis.local_agent.connection")


class BackendConnection:
    """
    Manages authenticated connection and heartbeats between the Windows Local Agent
    and the JARVIS backend.
    """

    def __init__(self, backend_url: str = BACKEND_URL, auth_token: Optional[str] = None):
        self.backend_url = backend_url.rstrip("/")
        self.auth_token = auth_token or get_agent_token()
        self.device_name = DEVICE_NAME
        self.is_registered = False
        self.heartbeat_manager = HeartbeatManager(
            backend_url=self.backend_url,
            device_name=self.device_name,
            interval=HEARTBEAT_INTERVAL_SECONDS,
            auth_token=self.auth_token
        )

    def _post(self, path: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        url = f"{self.backend_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers=get_auth_headers(self.auth_token),
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if 200 <= resp.status < 300:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.warning(f"Connection error reaching {path}: {e}")
            return None

    def register(self, available_tools: list) -> bool:
        """Registers the local agent device with the FastAPI backend."""
        sys_info = get_system_info()
        payload = {
            "device_name": self.device_name,
            "platform": PLATFORM,
            "version": AGENT_VERSION,
            "auth_token": self.auth_token,
            "port": LOCAL_SERVER_PORT,
            "available_tools": available_tools,
            "system_info": sys_info
        }
        res = self._post("/local-agent/register", payload)
        if res:
            self.is_registered = True
            logger.info(f"Registered device '{self.device_name}' with backend.")
            return True
        return False

    def send_heartbeat(self) -> bool:
        """Sends a periodic heartbeat pulse to the backend."""
        return self.heartbeat_manager.send_pulse("ONLINE")

    def start_heartbeat_loop(self) -> None:
        """Starts background heartbeat thread."""
        self.heartbeat_manager.start()

    def stop(self) -> None:
        """Stops the heartbeat loop and marks agent offline."""
        self.heartbeat_manager.stop()
