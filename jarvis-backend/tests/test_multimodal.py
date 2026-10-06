import sys
from pathlib import Path
_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import pytest
from unittest.mock import patch
from app.schemas.local_agent import LocalToolExecutionResponse
from app.vision.service import vision_service
from app.ai.tools import tool_registry
from app.models.memory import Memory


# Helper: 1x1 valid transparent PNG base64
SAMPLE_PNG_BASE64 = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


# ==============================================================================
# 1. TEXT INPUT STILL WORKS
# ==============================================================================
def test_01_text_input_backward_compatibility(client):
    payload = {"message": "Hello JARVIS, are you online?"}
    res = client.post("/api/v1/assistant/message", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "response" in data
    assert len(data["response"]) > 0


# ==============================================================================
# 2. VOICE INPUT STILL WORKS
# ==============================================================================
def test_02_voice_input_multimodal_endpoint(client):
    payload = {
        "message": "What time is it?",
        "input_type": "voice"
    }
    res = client.post("/api/v1/assistant/multimodal", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "response" in data
    assert data["intent"] in ["GET_CURRENT_TIME", "SYSTEM_STATUS", "CHAT", "GENERAL_QUERY"]


# ==============================================================================
# 3. SCREENSHOT REQUEST (Autonomous 2-Step Chained Plan)
# ==============================================================================
def test_03_screenshot_request_flow(client):
    mock_local_res = LocalToolExecutionResponse(
        status="SUCCESS",
        tool="capture_screen",
        output={
            "resolution": "1920x1080",
            "format": "PNG",
            "size_bytes": 1024,
            "image_data": SAMPLE_PNG_BASE64
        },
        verified=True
    )

    with patch("app.services.local_agent_service.local_agent_service.execute_tool", return_value=mock_local_res):
        res = client.post("/api/v1/assistant/message", json={"message": "What is on my screen?"})
        assert res.status_code == 200
        data = res.json()
        assert data["intent"] == "SCREEN_ANALYSIS"
        assert len(data["plan"]) == 2
        assert data["plan"][0]["tool_name"] == "local_capture_screen"
        assert data["plan"][1]["tool_name"] == "vision_analysis"
        assert "response" in data
        assert "screen" in data["response"].lower() or "application" in data["response"].lower() or "see" in data["response"].lower()


# ==============================================================================
# 4. SCREENSHOT PERMISSION OR LOCAL AGENT FAILURE
# ==============================================================================
def test_04_screenshot_permission_or_agent_failure(client):
    mock_failure = LocalToolExecutionResponse(
        status="DENIED",
        tool="capture_screen",
        output={},
        verified=False,
        error="Screen capture permission denied by user policy or local agent is offline"
    )

    with patch("app.services.local_agent_service.local_agent_service.execute_tool", return_value=mock_failure):
        res = client.post("/api/v1/assistant/message", json={"message": "What is on my screen?"})
        assert res.status_code == 200
        data = res.json()
        assert "couldn't" in data["response"].lower() or "failed" in data["response"].lower() or "denied" in data["response"].lower()


# ==============================================================================
# 5. IMAGE ANALYSIS DIRECT MULTIMODAL INTAKE
# ==============================================================================
def test_05_image_analysis_multimodal_endpoint(client):
    payload = {
        "message": "What does this image show?",
        "input_type": "image",
        "image_data": SAMPLE_PNG_BASE64,
        "mime_type": "image/png",
        "filename": "test_diagram.png"
    }
    res = client.post("/api/v1/assistant/multimodal", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] in ["IMAGE_ANALYSIS", "VISION_QUERY"]
    assert "response" in data
    assert len(data["response"]) > 0


# ==============================================================================
# 6. OCR REQUEST
# ==============================================================================
def test_06_ocr_request_flow(client):
    payload = {
        "message": "Read this error in the screenshot",
        "input_type": "image",
        "image_data": SAMPLE_PNG_BASE64,
        "mime_type": "image/png"
    }
    res = client.post("/api/v1/assistant/multimodal", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "OCR_REQUEST"
    assert "response" in data


# ==============================================================================
# 7. VISION PROVIDER FAILURE FALLBACK
# ==============================================================================
def test_07_vision_provider_failure_handling(client):
    failed_analysis = {
        "status": "failed",
        "reason": "EXECUTION_ERROR",
        "error": "Vision API timeout",
        "verified": False
    }
    with patch.object(vision_service, "analyze_image", return_value=failed_analysis):
        payload = {
            "message": "Analyze this screenshot",
            "input_type": "image",
            "image_data": SAMPLE_PNG_BASE64
        }
        res = client.post("/api/v1/assistant/multimodal", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "couldn't" in data["response"].lower() or "unable" in data["response"].lower() or "error" in data["response"].lower() or "unsuccessful" in data["response"].lower()


# ==============================================================================
# 8. INVALID IMAGE PAYLOAD
# ==============================================================================
def test_08_invalid_image_payload(client):
    payload = {
        "message": "Explain this file",
        "input_type": "image",
        "image_data": "data:text/plain;base64,SGVsbG8gV29ybGQ=",  # Not an image
        "mime_type": "text/plain"
    }
    res = client.post("/api/v1/assistant/multimodal", json=payload)
    assert res.status_code in [200, 400]
    if res.status_code == 200:
        data = res.json()
        assert "couldn't" in data["response"].lower() or "unsupported" in data["response"].lower() or "failed" in data["response"].lower()


# ==============================================================================
# 9. LARGE IMAGE THRESHOLD REJECTION
# ==============================================================================
def test_09_large_image_threshold(client):
    # Construct a payload simulated over 10MB
    huge_data = "data:image/png;base64," + ("A" * (14 * 1024 * 1024))
    payload = {
        "message": "Analyze this giant image",
        "input_type": "image",
        "image_data": huge_data,
        "mime_type": "image/png"
    }
    res = client.post("/api/v1/assistant/multimodal", json=payload)
    assert res.status_code in [200, 400]
    if res.status_code == 200:
        data = res.json()
        assert "exceeds" in data["response"].lower() or "large" in data["response"].lower() or "couldn't" in data["response"].lower()


# ==============================================================================
# 10. TOOL REGISTRY AUTHORIZATION
# ==============================================================================
def test_10_tool_registry_authorization():
    cap_tool = tool_registry.get("local_capture_screen")
    assert cap_tool is not None
    assert cap_tool.permission == "USER_INITIATED"
    assert cap_tool.name == "local_capture_screen"
    assert "quality" in cap_tool.input_schema["properties"]
    assert "image_data" in cap_tool.output_schema["properties"]
    assert cap_tool.verification_method == "verify_image_data_non_empty"

    vis_tool = tool_registry.get("vision_analysis")
    assert vis_tool is not None
    assert "image_data" in vis_tool.input_schema["properties"]
    assert "description" in vis_tool.output_schema["properties"]
    assert vis_tool.verification_method == "verify_structured_analysis"

    ocr_tool = tool_registry.get("vision_ocr")
    assert ocr_tool is not None
    assert "image_data" in ocr_tool.input_schema["properties"]
    assert "text" in ocr_tool.output_schema["properties"]
    assert ocr_tool.verification_method == "verify_ocr_non_empty"


# ==============================================================================
# 11. SECURITY RESTRICTIONS: NO ARBITRARY SCREENSHOT PATHS
# ==============================================================================
def test_11_security_restrictions_no_arbitrary_paths():
    from local_agent.permissions import is_tool_allowed, validate_screen_capture
    # Tool must be allowed
    assert is_tool_allowed("capture_screen") is True
    # Attempting to supply arbitrary output path must be rejected by validator
    assert validate_screen_capture({"output_path": "C:\\Windows\\System32\\dump.png"})[0] is False
    assert validate_screen_capture({})[0] is True


# ==============================================================================
# 12. EXISTING WINDOWS LOCAL AGENT TOOLS STILL WORK
# ==============================================================================
def test_12_existing_windows_local_tools_unaffected(client):
    mock_app_res = LocalToolExecutionResponse(
        status="SUCCESS",
        tool="open_application",
        output={"app_name": "notepad", "status": "launched"},
        verified=True
    )
    with patch("app.services.local_agent_service.local_agent_service.execute_tool", return_value=mock_app_res):
        res = client.post("/api/v1/assistant/message", json={"message": "Open Notepad"})
        assert res.status_code == 200
        data = res.json()
        assert data["intent"] == "OPEN_APPLICATION"
        assert data["verified"] is True


# ==============================================================================
# 13. EXISTING TASK AND PROJECT COMMANDS STILL WORK
# ==============================================================================
def test_13_existing_task_and_project_commands(client):
    res_task = client.post("/api/v1/assistant/message", json={"message": "Create a task to audit database indexes"})
    assert res_task.status_code == 200
    assert res_task.json()["intent"] in ["CREATE_TASK", "TASK_CREATE"]

    res_proj = client.post("/api/v1/assistant/message", json={"message": "List my projects"})
    assert res_proj.status_code == 200
    assert res_proj.json()["intent"] in ["PROJECT_QUERY", "LIST_PROJECTS"]


# ==============================================================================
# 14. MULTIMODAL MEMORY PRIVACY (NO RAW IMAGES IN MEMORY)
# ==============================================================================
def test_14_multimodal_memory_privacy(client, db_session):
    payload = {
        "message": "Remember that this is my DBMS project",
        "input_type": "text"
    }
    res = client.post("/api/v1/assistant/message", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] in ["MEMORY_SAVE", "CREATE_PROJECT", "CHAT", "QUESTION"]

    # Verify no raw base64 data URIs were written into Memory records
    memories = db_session.query(Memory).all()
    for mem in memories:
        assert not mem.content.startswith("data:image/")
        assert len(mem.content) < 50000  # Never storing massive image blobs


# ==============================================================================
# 15. MULTIMODAL + VOICE INTEGRATION
# ==============================================================================
def test_15_multimodal_plus_voice_integration(client):
    mock_local_res = LocalToolExecutionResponse(
        status="SUCCESS",
        tool="capture_screen",
        output={
            "resolution": "1920x1080",
            "format": "PNG",
            "size_bytes": 1024,
            "image_data": SAMPLE_PNG_BASE64
        },
        verified=True
    )

    with patch("app.services.local_agent_service.local_agent_service.execute_tool", return_value=mock_local_res):
        payload = {
            "message": "JARVIS, what am I looking at?",
            "input_type": "voice"
        }
        res = client.post("/api/v1/assistant/multimodal", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["intent"] in ["SCREEN_ANALYSIS", "SCREEN_CONTEXT_REQUEST", "VISION_QUERY"]
        assert "response" in data
        # Synthesized text response is clean for TTS
        assert "```" not in data["response"]
