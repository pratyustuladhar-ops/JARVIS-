import sys
from pathlib import Path
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import json
import logging
from typing import Dict, Any, Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

from local_agent.config import (
    DEVICE_NAME,
    PLATFORM,
    AGENT_VERSION,
    LOCAL_SERVER_HOST,
    LOCAL_SERVER_PORT,
    AUTH_TOKEN,
    BACKEND_URL
)
from local_agent.permissions import verify_auth_token, PermissionDeniedError, normalize_tool_name
from local_agent.tools import (
    get_current_time,
    get_system_info,
    open_application,
    open_url,
    list_allowed_directory,
    open_file,
    open_folder,
    capture_screen,
    verify_tool_result
)
from local_agent.connection import BackendConnection
from local_agent.voice.wake_word import LocalAgentWakeWordDetector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [JARVIS-LOCAL-AGENT]: %(message)s")
logger = logging.getLogger("jarvis.local_agent")


class WindowsLocalAgent:
    """
    JARVIS Windows Local Agent:
    Executes explicitly approved, allowlisted computer-level actions with strict security,
    permission checks, process verification, and authenticated backend coordination.
    """

    AVAILABLE_TOOLS = [
        "get_current_time",
        "get_system_info",
        "open_application",
        "open_url",
        "list_allowed_directory",
        "open_file",
        "open_folder",
        "capture_screen"
    ]

    def __init__(self):
        self.device_name = DEVICE_NAME
        self.platform = PLATFORM
        self.version = AGENT_VERSION
        self.connection = BackendConnection()
        self.wake_detector = LocalAgentWakeWordDetector(on_wake_callback=self._handle_wake_detection)
        self.is_running = False
        self._server: Optional[HTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None

    def _handle_wake_detection(self, event_data: Optional[Dict[str, Any]] = None):
        logger.info(f"Local agent captured wake word on {self.device_name}. Waking JARVIS.")
        # Non-blocking notification to JARVIS backend and Electron supervisor
        def notify_targets():
            # 1. Notify Backend audit endpoint
            try:
                import urllib.request
                backend_base = getattr(self.connection, "backend_url", None) or BACKEND_URL
                url = f"{backend_base}/voice/wake-word/event"
                payload = json.dumps({
                    "event_type": "WAKE_WORD_DETECTED",
                    "wake_phrase": self.wake_detector.wake_phrase,
                    "detail": f"Wake word captured locally by {self.device_name}.",
                    "metadata": event_data or {}
                }).encode("utf-8")
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=3)
            except Exception as e:
                logger.debug(f"Backend wake notification skipped/unreachable: {e}")

            # 2. Notify Electron supervisor directly if listening on loopback
            try:
                import urllib.request
                electron_port = os.getenv("JARVIS_ELECTRON_EVENT_PORT", "8003")
                electron_url = f"http://127.0.0.1:{electron_port}/wake"
                event_payload = event_data or {"event_type": "WAKE_WORD_DETECTED", "wake_phrase": self.wake_detector.wake_phrase}
                req = urllib.request.Request(
                    electron_url,
                    data=json.dumps(event_payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                urllib.request.urlopen(req, timeout=2)
            except Exception as e:
                logger.debug(f"Electron supervisor wake webhook skipped: {e}")

        threading.Thread(target=notify_targets, daemon=True).start()


    def execute_action(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Main execution dispatcher with security and verification enforcement.
        Maps backend and local tool names to explicitly approved local tools.
        """
        # 0. Tool Name Normalization
        resolved_tool = normalize_tool_name(tool_name)

        # 1. Authentication Check
        if not verify_auth_token(auth_token):
            logger.warning(f"Unauthorized execution attempt for tool '{resolved_tool}' - invalid token.")
            return {
                "status": "DENIED",
                "tool": resolved_tool,
                "verified": False,
                "error": "Authentication token missing or invalid."
            }

        # 2. Tool Allowlist Check
        if resolved_tool not in self.AVAILABLE_TOOLS:
            logger.warning(f"Unregistered tool requested: '{resolved_tool}' (raw: '{tool_name}')")
            return {
                "status": "DENIED",
                "tool": resolved_tool,
                "verified": False,
                "error": f"Tool '{resolved_tool}' is not in the local agent tool allowlist."
            }

        logger.info(f"Executing approved tool '{resolved_tool}' with parameters: {parameters}")

        # 3. Safe Execution
        try:
            raw_result = None
            if resolved_tool == "get_current_time":
                raw_result = get_current_time()
            elif resolved_tool == "get_system_info":
                raw_result = get_system_info()
            elif resolved_tool == "open_application":
                app_target = parameters.get("application") or parameters.get("name") or parameters.get("app")
                raw_result = open_application(str(app_target))
            elif resolved_tool == "open_url":
                url_target = parameters.get("url") or parameters.get("link")
                raw_result = open_url(str(url_target))
            elif resolved_tool == "list_allowed_directory":
                dir_target = parameters.get("directory") or parameters.get("path") or "Desktop"
                raw_result = list_allowed_directory(str(dir_target))
            elif resolved_tool == "open_file":
                file_target = parameters.get("file_path") or parameters.get("file")
                raw_result = open_file(str(file_target))
            elif resolved_tool == "open_folder":
                folder_target = parameters.get("folder_path") or parameters.get("folder") or parameters.get("path") or "Desktop"
                raw_result = open_folder(str(folder_target))
            elif resolved_tool == "capture_screen":
                quality = int(parameters.get("quality", 85))
                max_dim = int(parameters.get("max_dimension", 1920))
                raw_result = capture_screen(quality=quality, max_dimension=max_dim)

            # 4. Result Verification
            verif = verify_tool_result(resolved_tool, raw_result if isinstance(raw_result, dict) else {"status": "success"})
            is_success = True
            if isinstance(raw_result, dict):
                if (raw_result.get("status") in ["failed", "denied", "error"] or
                    raw_result.get("verified") is False or
                    raw_result.get("success") is False):
                    is_success = False

            if not verif.get("verified", True) or verif.get("status") == "FAILED":
                is_success = False

            if not is_success:
                err_msg = None
                if isinstance(raw_result, dict):
                    err_msg = raw_result.get("error") or raw_result.get("message") or raw_result.get("reason")
                return {
                    "status": "FAILED",
                    "tool": resolved_tool,
                    "output": raw_result,
                    "verified": False,
                    "detail": verif.get("detail", "Execution reported failure."),
                    "error": err_msg or verif.get("detail") or "Execution failed."
                }

            return {
                "status": "SUCCESS",
                "tool": resolved_tool,
                "output": raw_result,
                "verified": True,
                "detail": verif.get("detail", "Operation completed.")
            }

        except PermissionDeniedError as pe:
            logger.warning(f"Permission denied for '{resolved_tool}': {pe}")
            return {
                "status": "DENIED",
                "tool": resolved_tool,
                "verified": False,
                "error": str(pe)
            }
        except Exception as e:
            logger.error(f"Error executing '{resolved_tool}': {e}")
            return {
                "status": "FAILED",
                "tool": resolved_tool,
                "verified": False,
                "error": str(e)
            }

    def _start_local_bridge_server(self):
        """Starts a loopback-only HTTP server allowing local authenticated requests."""
        agent_ref = self

        class AgentHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                return  # Silence access logs

            def _send_status_json(self):
                """Shared logic for GET and HEAD status responses."""
                resp = {
                    "device_name": agent_ref.device_name,
                    "status": "ONLINE" if agent_ref.is_running else "STANDBY",
                    "wake_word_detector": agent_ref.wake_detector.get_status_dict(),
                    "available_tools": agent_ref.AVAILABLE_TOOLS
                }
                return json.dumps(resp).encode("utf-8")

            def _send_cors_headers(self):
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, HEAD, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Local-Agent-Token, Authorization")

            def do_OPTIONS(self):
                self.send_response(204)
                self._send_cors_headers()
                self.end_headers()

            def do_HEAD(self):
                """Respond to HEAD requests (prevents 501 from base class)."""
                path = self.path.split("?")[0]
                if path in ["/status", "/health"]:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._send_cors_headers()
                    self.end_headers()
                else:
                    self.send_response(404)
                    self._send_cors_headers()
                    self.end_headers()

            def do_GET(self):
                path = self.path.split("?")[0]
                if path in ["/status", "/health"]:
                    body = self._send_status_json()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_response(404)
                self._send_cors_headers()
                self.end_headers()

            def do_POST(self):
                path = self.path.split("?")[0]
                token = self.headers.get("X-Local-Agent-Token")
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length) if length > 0 else b"{}"
                try:
                    payload = json.loads(body.decode("utf-8")) if body else {}
                except Exception:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "FAILED", "error": "Malformed JSON payload"}).encode("utf-8"))
                    return

                # Wake-word candidate detection endpoint
                if path in ["/wake-word/candidate", "/wake", "/wake-word/detect"]:
                    phrase = payload.get("phrase") or payload.get("text") or payload.get("candidate", "")
                    detected = agent_ref.wake_detector.process_candidate(phrase)
                    res = {
                        "status": "SUCCESS",
                        "detected": detected,
                        "phrase": phrase,
                        "wake_phrase": agent_ref.wake_detector.wake_phrase,
                        "detector_running": agent_ref.wake_detector.is_running()
                    }
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(res).encode("utf-8"))
                    return

                # Authenticated wake-word control endpoints
                if path in ["/wake-word/toggle", "/wake-word/control"]:
                    if not verify_auth_token(token):
                        self.send_response(401)
                        self.send_header("Content-Type", "application/json")
                        self._send_cors_headers()
                        self.end_headers()
                        self.wfile.write(json.dumps({"status": "DENIED", "error": "Unauthorized"}).encode("utf-8"))
                        return

                    target_enabled = payload.get("enabled", True)
                    if target_enabled:
                        agent_ref.wake_detector.start()
                    else:
                        agent_ref.wake_detector.stop()

                    res = {
                        "status": "SUCCESS",
                        "wake_word_detector": agent_ref.wake_detector.get_status_dict()
                    }
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(res).encode("utf-8"))
                    return

                if path in ["/wake-word/pause", "/wake-word/resume"]:
                    if not verify_auth_token(token):
                        self.send_response(401)
                        self.send_header("Content-Type", "application/json")
                        self._send_cors_headers()
                        self.end_headers()
                        self.wfile.write(json.dumps({"status": "DENIED", "error": "Unauthorized"}).encode("utf-8"))
                        return

                    if "pause" in path:
                        agent_ref.wake_detector.pause()
                    else:
                        agent_ref.wake_detector.resume()

                    res = {
                        "status": "SUCCESS",
                        "wake_word_detector": agent_ref.wake_detector.get_status_dict()
                    }
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(res).encode("utf-8"))
                    return

                if path not in ["/execute", "/tools/execute"]:
                    self.send_response(404)
                    self.send_header("Content-Type", "application/json")
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "FAILED", "error": f"Endpoint '{path}' not found"}).encode("utf-8"))
                    return

                tool = payload.get("tool") or payload.get("tool_name")
                params = payload.get("parameters", {})
                res = agent_ref.execute_action(tool, params, auth_token=token)

                # Return appropriate HTTP code reflecting execution / auth outcome
                if res.get("status") == "DENIED":
                    http_code = 401 if "authentication" in (res.get("error") or "").lower() else 403
                elif res.get("status") == "FAILED":
                    http_code = 200  # Transport succeeded; action result conveys status
                else:
                    http_code = 200

                self.send_response(http_code)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(res).encode("utf-8"))

        class ReusableHTTPServer(HTTPServer):
            allow_reuse_address = True

        try:
            self._server = ReusableHTTPServer((LOCAL_SERVER_HOST, LOCAL_SERVER_PORT), AgentHandler)
            self._server_thread = threading.Thread(target=self._server.serve_forever, daemon=True, name="JarvisBridgeServer")
            self._server_thread.start()
            logger.info(f"Loopback bridge listening on {LOCAL_SERVER_HOST}:{LOCAL_SERVER_PORT}")
        except Exception as e:
            logger.error(f"Loopback server could not bind to port {LOCAL_SERVER_PORT}: {e}")
            self._server = None
            raise RuntimeError(f"Port {LOCAL_SERVER_PORT} is unavailable (likely another agent process is running): {e}")

    def start(self, retry_backend: bool = True, max_startup_retries: int = 5):
        """Starts the local agent, registers with backend, and sends heartbeats."""
        if self.is_running:
            logger.warning(f"Local agent {self.device_name} is already running.")
            return

        logger.info(f"Starting {self.device_name} (Windows Local Agent v{self.version})...")

        # Start loopback server
        self._start_local_bridge_server()
        self.is_running = True

        # Activate wake-word detector
        self.wake_detector.start()

        # Register with backend with retry
        registered = self.connection.register(self.AVAILABLE_TOOLS)
        retries = 0
        while not registered and retry_backend and retries < max_startup_retries:
            retries += 1
            logger.warning(f"Connection to backend failed (attempt {retries}/{max_startup_retries}): {self.connection.last_connection_error}. Retrying in 2 seconds...")
            time.sleep(2)
            registered = self.connection.register(self.AVAILABLE_TOOLS)

        if registered:
            self.connection.start_heartbeat_loop()
            logger.info(f"Local agent {self.device_name} is ONLINE and synchronized with JARVIS Core.")
        else:
            logger.error(f"STARTUP NOTICE: Could not register with backend at {self.connection.backend_url} ({self.connection.last_connection_error}). Starting background reconnection worker.")
            # Start background reconnection thread to automatically connect when backend becomes available
            self.connection.start_background_reconnect(self.AVAILABLE_TOOLS)

    def stop(self):
        """Stops the local agent gracefully."""
        logger.info(f"Stopping {self.device_name}...")
        self.is_running = False
        self.wake_detector.stop()
        self.connection.stop()
        if self._server:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass
            self._server = None
        logger.info("Local agent stopped.")


# Singleton instance
windows_local_agent = WindowsLocalAgent()

if __name__ == "__main__":
    agent = WindowsLocalAgent()
    try:
        agent.start()
        print(f"\n[JARVIS-WINDOWS-AGENT] Running as {DEVICE_NAME}. Press Ctrl+C to terminate.\n")
        threading.Event().wait()
    except KeyboardInterrupt:
        agent.stop()
        sys.exit(0)
