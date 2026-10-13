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
    Enforces reconnection on backend restarts, background reconnection retries on startup,
    URL fallbacks, and diagnostics reporting.
    """

    def __init__(self, backend_url: str = BACKEND_URL, auth_token: Optional[str] = None):
        self.backend_url = backend_url.rstrip("/")
        self.auth_token = (auth_token or get_agent_token()).strip()
        self.device_name = DEVICE_NAME
        self.is_registered = False
        self.available_tools: list = []
        self.last_connection_error: Optional[str] = None
        self._reconnect_thread: Optional[threading.Thread] = None
        self._reconnect_running = False
        self._lock = threading.Lock()
        self.heartbeat_manager = HeartbeatManager(
            backend_url=self.backend_url,
            device_name=self.device_name,
            interval=HEARTBEAT_INTERVAL_SECONDS,
            auth_token=self.auth_token,
            on_reconnect_needed=self.re_register
        )

    def _get_target_urls(self, path: str) -> list:
        base = self.backend_url
        target_paths = []
        if not base.endswith("/api/v1") and not path.startswith("/api/v1"):
            target_paths.append(f"/api/v1{path}")
        target_paths.append(path)

        urls = []
        for p in target_paths:
            urls.append(f"{base}{p}")
            if "localhost" in base:
                urls.append(f"{base.replace('localhost', '127.0.0.1')}{p}")
        return list(dict.fromkeys(urls))

    def _post(self, path: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        target_urls = self._get_target_urls(path)
        data = json.dumps(payload).encode("utf-8")
        headers = get_auth_headers(self.auth_token)

        last_error = None
        for url in target_urls:
            req = urllib.request.Request(
                url,
                data=data,
                headers=headers,
                method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if 200 <= resp.status < 300:
                        self.last_connection_error = None
                        return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as he:
                last_error = f"HTTP {he.code}: {he.reason}"
                logger.warning(f"Backend HTTP error reaching {url}: {last_error}")
                if he.code != 404:
                    break
            except Exception as e:
                last_error = str(e)
                logger.debug(f"Connection error reaching {url}: {e}")

        self.last_connection_error = last_error
        return None

    def register(self, available_tools: list) -> bool:
        """Registers the local agent device with the FastAPI backend."""
        self.available_tools = available_tools
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
            self.last_connection_error = None
            logger.info(f"Registered device '{self.device_name}' with backend.")
            return True

        self.is_registered = False
        return False

    def re_register(self) -> bool:
        """Re-registers the device with backend following a backend restart or 401 response."""
        if not self.available_tools:
            return False
        logger.info(f"Initiating re-registration for '{self.device_name}' with backend...")
        success = self.register(self.available_tools)
        if success:
            logger.info(f"Re-registration successful for '{self.device_name}'.")
        else:
            logger.warning(f"Re-registration failed for '{self.device_name}': {self.last_connection_error}")
        return success

    def start_background_reconnect(self, available_tools: list) -> None:
        """Starts a background reconnection task when initial startup registration fails."""
        with self._lock:
            if self._reconnect_running:
                return
            self._reconnect_running = True

            def _reconnect_worker():
                logger.info(f"Background reconnection loop started for {self.device_name}...")
                while self._reconnect_running and not self.is_registered:
                    time.sleep(3)
                    if not self._reconnect_running:
                        break
                    success = self.register(available_tools)
                    if success:
                        logger.info(f"Background reconnection successful. Synchronized with backend.")
                        self.start_heartbeat_loop()
                        break
                self._reconnect_running = False

            self._reconnect_thread = threading.Thread(target=_reconnect_worker, daemon=True, name="JarvisReconnectThread")
            self._reconnect_thread.start()

    def send_heartbeat(self) -> bool:
        """Sends a periodic heartbeat pulse to the backend."""
        return self.heartbeat_manager.send_pulse("ONLINE")

    def start_heartbeat_loop(self) -> None:
        """Starts background heartbeat thread."""
        self.heartbeat_manager.start()

    def stop(self) -> None:
        """Stops the heartbeat loop and marks agent offline."""
        self._reconnect_running = False
        self.is_registered = False
        self.heartbeat_manager.stop()

    def get_diagnostics(self) -> Dict[str, Any]:
        """Provides full connection and heartbeat telemetry for agent diagnostics."""
        hb_diag = self.heartbeat_manager.get_diagnostics()
        return {
            "device_name": self.device_name,
            "backend_url": self.backend_url,
            "is_registered": self.is_registered,
            "last_connection_error": self.last_connection_error,
            "heartbeat": hb_diag
        }
