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
    AUTH_TOKEN
)
from local_agent.permissions import verify_auth_token, PermissionDeniedError
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

    def _handle_wake_detection(self):
        logger.info(f"Local agent captured wake word on {self.device_name}. Waking JARVIS.")
        # Non-blocking notification to JARVIS backend
        def notify_backend():
            try:
                import urllib.request
                url = f"{BACKEND_BASE_URL}/voice/wake-word/event"
                payload = json.dumps({
                    "event_type": "WAKE_WORD_DETECTED",
                    "wake_phrase": self.wake_detector.wake_phrase,
                    "detail": f"Wake word captured locally by {self.device_name}."
                }).encode("utf-8")
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=3)
            except Exception as e:
                logger.debug(f"Backend wake notification skipped/unreachable: {e}")

        threading.Thread(target=notify_backend, daemon=True).start()


    def execute_action(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Main execution dispatcher with security and verification enforcement.
        """
        # 1. Authentication Check
        if not verify_auth_token(auth_token):
            logger.warning(f"Unauthorized execution attempt for tool '{tool_name}' - invalid token.")
            return {
                "status": "DENIED",
                "tool": tool_name,
                "verified": False,
                "error": "Authentication token missing or invalid."
            }

        # 2. Tool Allowlist Check
        if tool_name not in self.AVAILABLE_TOOLS:
            logger.warning(f"Unregistered tool requested: '{tool_name}'")
            return {
                "status": "DENIED",
                "tool": tool_name,
                "verified": False,
                "error": f"Tool '{tool_name}' is not in the local agent tool allowlist."
            }

        logger.info(f"Executing approved tool '{tool_name}' with parameters: {parameters}")

        # 3. Safe Execution
        try:
            raw_result = None
            if tool_name == "get_current_time":
                raw_result = get_current_time()
            elif tool_name == "get_system_info":
                raw_result = get_system_info()
            elif tool_name == "open_application":
                app_target = parameters.get("application") or parameters.get("name") or parameters.get("app")
                raw_result = open_application(str(app_target))
            elif tool_name == "open_url":
                url_target = parameters.get("url") or parameters.get("link")
                raw_result = open_url(str(url_target))
            elif tool_name == "list_allowed_directory":
                dir_target = parameters.get("directory") or parameters.get("path") or "Desktop"
                raw_result = list_allowed_directory(str(dir_target))
            elif tool_name == "open_file":
                file_target = parameters.get("file_path") or parameters.get("file")
                raw_result = open_file(str(file_target))
            elif tool_name == "open_folder":
                folder_target = parameters.get("folder_path") or parameters.get("folder") or parameters.get("path") or "Desktop"
                raw_result = open_folder(str(folder_target))
            elif tool_name in ["capture_screen", "local_capture_screen"]:
                quality = int(parameters.get("quality", 85))
                max_dim = int(parameters.get("max_dimension", 1920))
                raw_result = capture_screen(quality=quality, max_dimension=max_dim)

            # 4. Result Verification
            verif = verify_tool_result(tool_name, raw_result if isinstance(raw_result, dict) else {"status": "success"})
            if isinstance(raw_result, dict) and (raw_result.get("status") == "failed" or raw_result.get("verified") is False or raw_result.get("success") is False):
                return {
                    "status": "FAILED",
                    "tool": tool_name,
                    "output": raw_result,
                    "verified": False,
                    "detail": verif.get("detail", "Execution reported failure."),
                    "error": raw_result.get("error") or raw_result.get("message") or raw_result.get("reason") or "Execution failed."
                }

            return {
                "status": "SUCCESS",
                "tool": tool_name,
                "output": raw_result,
                "verified": verif.get("verified", True),
                "detail": verif.get("detail", "Operation completed.")
            }

        except PermissionDeniedError as pe:
            logger.warning(f"Permission denied for '{tool_name}': {pe}")
            return {
                "status": "DENIED",
                "tool": tool_name,
                "verified": False,
                "error": str(pe)
            }
        except Exception as e:
            logger.error(f"Error executing '{tool_name}': {e}")
            return {
                "status": "FAILED",
                "tool": tool_name,
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
                    "wake_word_detector": {
                        "running": agent_ref.wake_detector.is_running(),
                        "phrase": agent_ref.wake_detector.wake_phrase,
                        "paused": agent_ref.wake_detector.is_paused_state()
                    },
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
                    self._send_cors_headers()
                    self.end_headers()
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

                if path not in ["/execute", "/tools/execute"]:
                    self.send_response(404)
                    self._send_cors_headers()
                    self.end_headers()
                    return

                tool = payload.get("tool") or payload.get("tool_name")
                params = payload.get("parameters", {})
                res = agent_ref.execute_action(tool, params, auth_token=token)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(res).encode("utf-8"))

        class ReusableHTTPServer(HTTPServer):
            allow_reuse_address = True

        try:
            self._server = ReusableHTTPServer((LOCAL_SERVER_HOST, LOCAL_SERVER_PORT), AgentHandler)
            self._server_thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._server_thread.start()
            logger.info(f"Loopback bridge listening on {LOCAL_SERVER_HOST}:{LOCAL_SERVER_PORT}")
        except Exception as e:
            logger.warning(f"Loopback server could not bind to port {LOCAL_SERVER_PORT}: {e}")

    def start(self):
        """Starts the local agent, registers with backend, and sends heartbeats."""
        logger.info(f"Starting {self.device_name} (Windows Local Agent v{self.version})...")
        self.is_running = True

        # Activate wake-word detector
        self.wake_detector.start()

        # Start loopback server
        self._start_local_bridge_server()

        # Register with backend
        registered = self.connection.register(self.AVAILABLE_TOOLS)
        if registered:
            self.connection.start_heartbeat_loop()
            logger.info(f"Local agent {self.device_name} is ONLINE and synchronized with JARVIS Core.")
        else:
            logger.warning("Could not register with backend. Operating in standalone mode.")

    def stop(self):
        """Stops the local agent gracefully."""
        logger.info(f"Stopping {self.device_name}...")
        self.is_running = False
        self.connection.stop()
        if self._server:
            try:
                self._server.shutdown()
            except Exception:
                pass
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
