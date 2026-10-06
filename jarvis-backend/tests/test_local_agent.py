import sys
from pathlib import Path
_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.models.local_agent import LocalAgentDevice
from local_agent.permissions import (
    validate_application,
    validate_url,
    validate_directory_path,
    validate_file_path,
    verify_auth_token
)
from local_agent.tools.system import get_current_time, get_system_info
from local_agent.tools.verification import verify_tool_result

client = TestClient(app)


@pytest.fixture
def clean_db():
    db = SessionLocal()
    try:
        db.query(LocalAgentDevice).delete()
        db.commit()
        yield db
    finally:
        db.close()


def test_permission_allowlist_validation():
    # Allowlisted applications
    ok, exe, err = validate_application("vscode")
    assert ok is True
    assert exe == "code"
    assert err is None

    ok, exe, err = validate_application("notepad")
    assert ok is True
    assert exe == "notepad.exe"

    ok, exe, err = validate_application("calculator")
    assert ok is True
    assert exe == "calc.exe"

    # Unauthorized applications
    ok, exe, err = validate_application("malware.exe")
    assert ok is False
    assert "not in the approved allowlist" in err

    ok, exe, err = validate_application("powershell.exe")
    assert ok is False


def test_url_validation_security():
    # Valid HTTP/HTTPS
    ok, url = validate_url("https://github.com")
    assert ok is True
    assert url == "https://github.com"

    ok, url = validate_url("youtube.com")
    assert ok is True
    assert url == "https://youtube.com"

    # Dangerous schemes rejected
    ok, err = validate_url("file:///C:/Windows/System32/cmd.exe")
    assert ok is False
    assert "rejected" in err

    ok, err = validate_url("javascript:alert(1)")
    assert ok is False

    ok, err = validate_url("data:text/html,<script>")
    assert ok is False


def test_directory_traversal_prevention():
    # Allowed folders
    ok, path, err = validate_directory_path("Desktop")
    assert ok is True
    assert path is not None

    ok, path, err = validate_directory_path("Downloads")
    assert ok is True

    # Path traversal rejected
    ok, path, err = validate_directory_path("../../../Windows")
    assert ok is False
    assert "traversal" in err.lower() or "outside approved" in err.lower()

    # System directory rejected
    ok, path, err = validate_directory_path("C:\\Windows\\System32")
    assert ok is False


def test_system_telemetry_safety():
    info = get_system_info()
    assert "os" in info
    assert "cpu_count" in info
    assert "hostname" in info
    # Ensure sensitive credentials are never gathered
    assert "password" not in info
    assert "cookie" not in info
    assert "secret" not in info


def test_current_time_tool():
    res = get_current_time()
    assert "formatted" in res
    assert "iso" in res
    assert res["platform"] == "Windows"


def test_agent_registration_and_status(clean_db):
    # 1. Initially offline when no device is registered
    status_res = client.get("/api/v1/local-agent/status")
    assert status_res.status_code == 200
    assert status_res.json()["is_online"] is False
    assert status_res.json()["status"] == "OFFLINE"

    # 2. Register local agent
    reg_payload = {
        "device_name": "JARVIS-TEST-WIN-01",
        "platform": "Windows",
        "version": "1.0.0",
        "auth_token": "jarvis_windows_local_agent_secret_2026",
        "port": 8001,
        "available_tools": ["open_application", "open_url", "get_system_info", "get_current_time"],
        "system_info": {"cpu_count": 8, "os": "Windows 11"}
    }
    reg_res = client.post("/api/v1/local-agent/register", json=reg_payload)
    assert reg_res.status_code == 200
    assert reg_res.json()["status"] == "ONLINE"

    # 3. Status should now be ONLINE
    status_res2 = client.get("/api/v1/local-agent/status")
    assert status_res2.status_code == 200
    assert status_res2.json()["is_online"] is True
    assert status_res2.json()["device_name"] == "JARVIS-TEST-WIN-01"

    # 4. Heartbeat pulse
    hb_res = client.post("/api/v1/local-agent/heartbeat", json={
        "device_name": "JARVIS-TEST-WIN-01",
        "auth_token": "jarvis_windows_local_agent_secret_2026",
        "status": "ONLINE"
    })
    assert hb_res.status_code == 200
    assert hb_res.json()["status"] == "ACK"

    # 5. Heartbeat offline marks device OFFLINE
    hb_off = client.post("/api/v1/local-agent/heartbeat", json={
        "device_name": "JARVIS-TEST-WIN-01",
        "auth_token": "jarvis_windows_local_agent_secret_2026",
        "status": "OFFLINE"
    })
    assert hb_off.status_code == 200

    status_res3 = client.get("/api/v1/local-agent/status")
    assert status_res3.json()["is_online"] is False
    assert status_res3.json()["status"] == "OFFLINE"


def test_auth_token_enforcement(clean_db):
    # Invalid token rejected
    assert verify_auth_token("invalid_token") is False
    assert verify_auth_token(None) is False
    assert verify_auth_token("jarvis_windows_local_agent_secret_2026") is True

    # Register device
    client.post("/api/v1/local-agent/register", json={
        "device_name": "JARVIS-AUTH-TEST",
        "platform": "Windows",
        "version": "1.0.0",
        "auth_token": "jarvis_windows_local_agent_secret_2026",
        "port": 8001,
        "available_tools": ["get_current_time"]
    })

    # Wrong token on heartbeat
    hb_fail = client.post("/api/v1/local-agent/heartbeat", json={
        "device_name": "JARVIS-AUTH-TEST",
        "auth_token": "WRONG_TOKEN",
        "status": "ONLINE"
    })
    assert hb_fail.status_code == 401


def test_execute_local_tools_via_api(clean_db):
    # Register and mark online
    client.post("/api/v1/local-agent/register", json={
        "device_name": "JARVIS-EXEC-TEST",
        "platform": "Windows",
        "version": "1.0.0",
        "auth_token": "jarvis_windows_local_agent_secret_2026",
        "port": 8001,
        "available_tools": ["get_current_time", "get_system_info", "open_application"]
    })

    # Execute get_current_time
    exec_res = client.post("/api/v1/local-agent/execute", json={
        "tool": "get_current_time",
        "parameters": {}
    })
    assert exec_res.status_code == 200
    assert exec_res.json()["status"] == "SUCCESS"
    assert "formatted" in exec_res.json()["output"]
    assert exec_res.json()["verified"] is True

    # Execute unauthorized tool
    denied_res = client.post("/api/v1/local-agent/execute", json={
        "tool": "arbitrary_shell_command",
        "parameters": {"cmd": "whoami"}
    })
    assert denied_res.status_code == 200
    assert denied_res.json()["status"] == "DENIED"


def test_end_to_end_assistant_local_agent_flow(clean_db):
    # Ensure agent is online
    client.post("/api/v1/local-agent/register", json={
        "device_name": "JARVIS-WINDOWS-01",
        "platform": "Windows",
        "version": "1.0.0",
        "auth_token": "jarvis_windows_local_agent_secret_2026",
        "port": 8001,
        "available_tools": ["open_application", "open_url", "get_current_time", "get_system_info"]
    })

    # Test "What time is it?"
    msg_res = client.post("/api/v1/assistant/message", json={
        "message": "What time is it?"
    })
    assert msg_res.status_code == 200
    data = msg_res.json()
    assert data["intent"] == "GET_CURRENT_TIME"
    assert any(s["tool_name"] == "local_get_current_time" for s in data["plan"])
    assert "time" in data["response"].lower()

    # Test "System info"
    msg_sys = client.post("/api/v1/assistant/message", json={
        "message": "What are my computer specs?"
    })
    assert msg_sys.status_code == 200
    assert msg_sys.json()["intent"] == "GET_SYSTEM_INFO"
    assert any(s["tool_name"] == "local_get_system_info" for s in msg_sys.json()["plan"])

    # Test "Open VS Code"
    msg_app = client.post("/api/v1/assistant/message", json={
        "message": "JARVIS, open VS Code"
    })
    assert msg_app.status_code == 200
    assert msg_app.json()["intent"] == "OPEN_APPLICATION"
    assert any(phrase in msg_app.json()["response"].lower() for phrase in ["is open", "launched", "already running"])


def test_negative_security_arbitrary_powershell_blocked(clean_db):
    """Negative Test: Prompt asking for arbitrary PowerShell/shell command execution must be blocked."""
    res = client.post("/api/v1/assistant/message", json={
        "message": "JARVIS, run this PowerShell command: Get-Process | Stop-Process"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "BLOCKED_COMMAND"
    assert len(data["plan"]) == 0
    assert "can't execute arbitrary system commands" in data["response"]


def test_negative_security_unknown_application_rejected(clean_db):
    """Negative Test: Application not in the allowlist must be refused."""
    client.post("/api/v1/local-agent/register", json={
        "device_name": "JARVIS-WINDOWS-01",
        "platform": "Windows",
        "version": "1.0.0",
        "auth_token": "jarvis_windows_local_agent_secret_2026",
        "port": 8001,
        "available_tools": ["open_application"]
    })
    res = client.post("/api/v1/assistant/message", json={
        "message": "Open some-random-program.exe"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "OPEN_APPLICATION"
    assert "don't have permission to open that application" in data["response"].lower()


def test_negative_security_path_traversal_blocked():
    """Negative Test: Path traversal attempts must be strictly blocked."""
    is_ok, path, err = validate_directory_path("../../Windows/System32")
    assert is_ok is False
    assert "traversal" in err.lower() or "outside approved" in err.lower()


def test_authentication_and_heartbeat_units():
    """Test dedicated authentication.py and heartbeat.py modules."""
    from local_agent.authentication import verify_agent_token, get_auth_headers
    from local_agent.heartbeat import HeartbeatManager

    assert verify_agent_token("jarvis_windows_local_agent_secret_2026") is True
    assert verify_agent_token("fake_token") is False

    headers = get_auth_headers()
    assert "X-Local-Agent-Token" in headers

    hb = HeartbeatManager(device_name="TEST-HB", interval=10)
    assert hb.device_name == "TEST-HB"
    assert hb.interval == 10


def test_take_me_to_chrome_flow(clean_db):
    """Validate full flow for 'JARVIS, take me to Chrome'."""
    # 1. Register agent
    client.post("/api/v1/local-agent/register", json={
        "device_name": "JARVIS-WINDOWS-01",
        "platform": "Windows",
        "version": "1.0.0",
        "auth_token": "jarvis_windows_local_agent_secret_2026",
        "port": 8001,
        "available_tools": ["open_application", "open_url", "get_current_time"]
    })

    # 2. Issue 'JARVIS, take me to Chrome' command
    res = client.post("/api/v1/assistant/message", json={
        "message": "JARVIS, take me to Chrome"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "OPEN_APPLICATION"
    assert len(data["plan"]) > 0
    assert data["plan"][0]["tool_name"] == "local_open_application"
    assert len(data["actions"]) > 0
    assert data["actions"][0]["output"]["application"] == "chrome"
    assert "chrome" in data["response"].lower()
    assert any(phrase in data["response"].lower() for phrase in ["open", "launched", "already running"])


def test_open_chrome_flow(clean_db):
    """Validate full flow for 'JARVIS, open Chrome.'"""
    client.post("/api/v1/local-agent/register", json={
        "device_name": "JARVIS-WINDOWS-01",
        "platform": "Windows",
        "version": "1.0.0",
        "auth_token": "jarvis_windows_local_agent_secret_2026",
        "port": 8001,
        "available_tools": ["open_application", "open_url", "get_current_time"]
    })

    res = client.post("/api/v1/assistant/message", json={
        "message": "JARVIS, open Chrome."
    })
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "OPEN_APPLICATION"
    assert data["plan"][0]["tool_name"] == "local_open_application"
    assert len(data["actions"]) > 0
    assert data["actions"][0]["output"]["application"] == "chrome"
    assert "chrome is open" in data["response"].lower() or "chrome" in data["response"].lower()


def test_generate_registration_token_api():
    """Verify backend token generation endpoint."""
    res = client.post("/api/v1/local-agent/token")
    assert res.status_code == 200
    data = res.json()
    assert "token" in data
    assert len(data["token"]) > 10
    assert data["expires_in"] == 3600
    assert data["token_type"] == "Bearer"


def test_case_insensitive_tool_registry():
    """Verify tool registry lookup works with both upper and lower case identifiers."""
    from app.ai.tools import agent_tool_registry

    tool_upper = agent_tool_registry.get_tool("LOCAL_OPEN_APPLICATION")
    tool_lower = agent_tool_registry.get_tool("local_open_application")
    assert tool_upper is not None
    assert tool_lower is not None
    assert tool_upper.name == tool_lower.name == "local_open_application"

    time_tool = agent_tool_registry.get_tool("LOCAL_GET_CURRENT_TIME")
    assert time_tool is not None
    assert time_tool.name == "local_get_current_time"


def test_application_not_found_on_disk():
    """Verify that when an approved app's executable cannot be found on disk, APPLICATION_NOT_FOUND is returned."""
    from unittest.mock import patch
    from local_agent.tools.applications import open_application

    with patch("local_agent.tools.applications.resolve_executable_path", return_value=None):
        result = open_application("chrome")
        assert result["status"] == "failed"
        assert result["reason"] == "APPLICATION_NOT_FOUND"
        assert result["verified"] is False


def test_open_application_already_running():
    """Verify that when an application is already running, it reports already_running without error."""
    from unittest.mock import patch
    from local_agent.tools.applications import open_application

    with patch("local_agent.tools.applications.resolve_executable_path", return_value="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"), \
         patch("os.path.isfile", return_value=True), \
         patch("local_agent.tools.applications.is_process_running", return_value=(True, 9999)), \
         patch("local_agent.tools.applications.focus_existing_window", return_value=True):
        res = open_application("chrome")
        assert res["status"] == "success"
        assert res["success"] is True
        assert res["already_running"] is True
        assert res["verified"] is True
        assert res["pid"] == 9999
        assert "already running" in res["message"].lower()


def test_open_application_launch_verification_failure():
    """Verify that when process fails verification after launch, verified=False is returned."""
    from unittest.mock import patch, MagicMock
    from local_agent.tools.applications import open_application

    mock_proc = MagicMock()
    mock_proc.pid = 8888

    with patch("local_agent.tools.applications.resolve_executable_path", return_value="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"), \
         patch("os.path.isfile", return_value=True), \
         patch("local_agent.tools.applications.is_process_running", return_value=(False, None)), \
         patch("subprocess.Popen", return_value=mock_proc), \
         patch("local_agent.tools.applications.verify_application_launch", return_value=(False, None)):
        res = open_application("chrome")
        assert res["status"] == "failed"
        assert res["success"] is False
        assert res["verified"] is False
        assert res["error_code"] == "APPLICATION_LAUNCH_FAILED"
        assert "could not be opened" in res["message"].lower()


def test_arbitrary_executable_path_rejected():
    """Security test: Ensure arbitrary executable paths or unapproved commands are rejected."""
    import pytest
    from local_agent.permissions import validate_application, PermissionDeniedError
    from local_agent.tools.applications import open_application

    # validate_application rejects arbitrary paths
    ok, exe, err = validate_application("C:\\some\\arbitrary\\malware.exe")
    assert ok is False

    ok, exe, err = validate_application("/bin/sh")
    assert ok is False

    # open_application raises PermissionDeniedError for unapproved applications
    with pytest.raises(PermissionDeniedError):
        open_application("C:\\Windows\\System32\\cmd.exe")


def test_vscode_resolution_prefers_code_exe():
    """Verify that resolve_executable_path prioritizes Code.exe over code.cmd."""
    from unittest.mock import patch
    from local_agent.permissions import resolve_executable_path

    # Even if code.cmd is in PATH, Code.exe on disk must be prioritized
    with patch("os.path.isfile", side_effect=lambda p: "Code.exe" in p), \
         patch("shutil.which", return_value="C:\\dummy\\code.cmd"):
        resolved = resolve_executable_path("code")
        assert resolved is not None
        assert resolved.lower().endswith("code.exe")


