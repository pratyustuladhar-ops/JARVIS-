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
    Enforces thread-safety, bounded failure retries, reconnection callbacks on backend restarts,
    and diagnostics reporting.
    """

    def __init__(
        self,
        backend_url: str = BACKEND_URL,
        device_name: str = DEVICE_NAME,
        interval: int = HEARTBEAT_INTERVAL_SECONDS,
        auth_token: Optional[str] = None,
        on_reconnect_needed: Optional[Any] = None
    ):
        self.backend_url = backend_url.rstrip("/")
        self.device_name = device_name
        self.interval = interval
        self.auth_token = (auth_token or get_agent_token()).strip()
        self.on_reconnect_needed = on_reconnect_needed
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.last_beat_time: Optional[float] = None
        self.last_beat_success: bool = False
        self.consecutive_failures: int = 0
        self.last_error: Optional[str] = None

    def _get_target_urls(self, path: str) -> list:
        urls = [f"{self.backend_url}{path}"]
        if "localhost" in self.backend_url:
            urls.append(f"{self.backend_url.replace('localhost', '127.0.0.1')}{path}")
        return urls

    def send_pulse(self, status: str = "ONLINE") -> bool:
        """Sends a single heartbeat pulse to the backend with URL fallback and re-registration handling."""
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

        success = False
        last_exc: Optional[Exception] = None
        target_urls = self._get_target_urls("/local-agent/heartbeat")

        for url in target_urls:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if 200 <= resp.status < 300:
                        self.last_beat_time = time.time()
                        self.last_beat_success = True
                        self.consecutive_failures = 0
                        self.last_error = None
                        success = True
                        break
            except urllib.error.HTTPError as he:
                last_exc = he
                self.last_error = f"HTTP {he.code}: {he.reason}"
                logger.warning(f"Heartbeat pulse rejected by backend ({he.code}): {he.reason}")
                # Backend restarted or device unregistered -> attempt immediate re-registration
                if he.code == 401 and self.on_reconnect_needed and status == "ONLINE":
                    logger.info("Heartbeat returned 401; attempting device re-registration with backend...")
                    try:
                        re_reg = self.on_reconnect_needed()
                        if re_reg:
                            logger.info("Re-registration succeeded; resending pulse...")
                            with urllib.request.urlopen(req, timeout=5) as resp2:
                                if 200 <= resp2.status < 300:
                                    self.last_beat_time = time.time()
                                    self.last_beat_success = True
                                    self.consecutive_failures = 0
                                    self.last_error = None
                                    return True
                    except Exception as re_err:
                        logger.debug(f"Re-registration attempt failed: {re_err}")
                break
            except Exception as e:
                last_exc = e
                self.last_error = str(e)
                logger.debug(f"Heartbeat attempt failed reaching {url}: {e}")

        if not success:
            self.last_beat_success = False
            self.consecutive_failures += 1
            if status == "ONLINE":
                logger.debug(f"Heartbeat pulse failed (consecutive failures: {self.consecutive_failures}): {last_exc}")
                # If consecutive failures exceed threshold, attempt re-registration if callback configured
                if self.consecutive_failures >= 3 and self.on_reconnect_needed:
                    try:
                        self.on_reconnect_needed()
                    except Exception:
                        pass
            return False

        return True

    def start(self) -> None:
        """Starts the background heartbeat loop thread safely without duplicates."""
        with self._lock:
            if self._running or (self._thread and self._thread.is_alive()):
                logger.debug("Heartbeat loop already running. Duplicate thread avoided.")
                return

            self._running = True

            def _loop():
                # Send initial pulse immediately
                self.send_pulse("ONLINE")
                while self._running:
                    # Adaptive sleep: 3s on failure for quick recovery, normal interval on success
                    sleep_time = 3 if (not self.last_beat_success and self._running) else self.interval
                    time.sleep(sleep_time)
                    if self._running:
                        self.send_pulse("ONLINE")

            self._thread = threading.Thread(target=_loop, daemon=True, name="JarvisHeartbeatThread")
            self._thread.start()
            logger.info(f"Heartbeat loop started (interval={self.interval}s).")

    def stop(self) -> None:
        """Stops the heartbeat loop safely and informs backend agent is OFFLINE."""
        with self._lock:
            self._running = False
            try:
                self.send_pulse("OFFLINE")
            except Exception:
                pass
            self.last_beat_success = False
            logger.info("Heartbeat loop stopped.")

    def get_diagnostics(self) -> Dict[str, Any]:
        """Returns structured heartbeat health and diagnostic metrics."""
        now = time.time()
        seconds_since_last = round(now - self.last_beat_time, 2) if self.last_beat_time else None
        return {
            "device_name": self.device_name,
            "running": self._running,
            "interval_seconds": self.interval,
            "last_beat_time": self.last_beat_time,
            "seconds_since_last_beat": seconds_since_last,
            "last_beat_success": self.last_beat_success,
            "consecutive_failures": self.consecutive_failures,
            "last_error": self.last_error
        }
