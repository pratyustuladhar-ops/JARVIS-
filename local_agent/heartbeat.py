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
    AGENT_VERSION,
    HEARTBEAT_INTERVAL_SECONDS
)
from local_agent.authentication import get_auth_headers, get_agent_token

logger = logging.getLogger("jarvis.local_agent.heartbeat")


class HeartbeatManager:
    """
    Manages periodic heartbeats from the Windows Local Agent to the JARVIS backend.
    """

    def __init__(
        self,
        backend_url: str = BACKEND_URL,
        device_name: str = DEVICE_NAME,
        interval: int = HEARTBEAT_INTERVAL_SECONDS,
        auth_token: Optional[str] = None
    ):
        self.backend_url = backend_url.rstrip("/")
        self.device_name = device_name
        self.interval = interval
        self.auth_token = auth_token or get_agent_token()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.last_beat_time: Optional[float] = None
        self.last_beat_success: bool = False

    def send_pulse(self, status: str = "ONLINE") -> bool:
        """Sends a single heartbeat pulse to the backend."""
        url = f"{self.backend_url}/local-agent/heartbeat"
        payload = {
            "device_name": self.device_name,
            "auth_token": self.auth_token,
            "status": status,
            "metrics": {
                "timestamp": time.time(),
                "agent_version": AGENT_VERSION
            }
        }
        data = json.dumps(payload).encode("utf-8")
        headers = get_auth_headers(self.auth_token)
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if 200 <= resp.status < 300:
                    self.last_beat_time = time.time()
                    self.last_beat_success = True
                    return True
        except Exception as e:
            logger.debug(f"Heartbeat pulse to backend failed: {e}")
            self.last_beat_success = False

        return False

    def start(self) -> None:
        """Starts the background heartbeat loop thread."""
        if self._running:
            return

        self._running = True

        def _loop():
            # Send initial pulse immediately
            self.send_pulse("ONLINE")
            while self._running:
                time.sleep(self.interval)
                if self._running:
                    self.send_pulse("ONLINE")

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()
        logger.info(f"Heartbeat loop started (interval={self.interval}s).")

    def stop(self) -> None:
        """Stops the heartbeat loop and informs backend agent is OFFLINE."""
        self._running = False
        try:
            self.send_pulse("OFFLINE")
        except Exception:
            pass
        logger.info("Heartbeat loop stopped.")
