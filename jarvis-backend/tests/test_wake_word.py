import sys
from pathlib import Path
_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import pytest
from unittest.mock import patch, MagicMock
from app.voice.wake_word.service import wake_word_service
from app.voice.wake_word.provider import (
    LocalKeywordSpotterProvider,
    MockWakeWordProvider,
    get_wake_word_provider
)
from app.voice.wake_word.schemas import WakeWordEvent
from app.schemas.local_agent import LocalToolExecutionResponse
from local_agent.voice.wake_word import LocalAgentWakeWordDetector


# ==============================================================================
# 1. WAKE WORD ENABLED
# ==============================================================================
def test_01_wake_word_enabled(client):
    res = client.post("/api/v1/voice/wake-word/toggle", json={"enabled": True})
    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is True
    assert data["state"] == "WAKE_WORD_LISTENING"
    assert wake_word_service.is_running() is True


# ==============================================================================
# 2. WAKE WORD DISABLED
# ==============================================================================
def test_02_wake_word_disabled(client):
    res = client.post("/api/v1/voice/wake-word/toggle", json={"enabled": False})
    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is False
    assert data["state"] == "IDLE"
    assert wake_word_service.is_running() is False


# ==============================================================================
# 3. WAKE PHRASE DETECTION
# ==============================================================================
def test_03_wake_phrase_detection():
    provider = LocalKeywordSpotterProvider(wake_phrase="Hey JARVIS", sensitivity=0.7)
    
    assert provider.detect_phrase("hey jarvis") is True
    assert provider.detect_phrase("Hey JARVIS, open Chrome") is True
    assert provider.detect_phrase("jarvis wake up") is True
    assert provider.detect_phrase("ok jarvis") is True


# ==============================================================================
# 4. FALSE WAKE PHRASE REJECTION
# ==============================================================================
def test_04_false_wake_phrase():
    provider = LocalKeywordSpotterProvider(wake_phrase="Hey JARVIS", sensitivity=0.7)
    
    assert provider.detect_phrase("What is the weather today") is False
    assert provider.detect_phrase("Hey Siri, tell me a joke") is False
    assert provider.detect_phrase("Hello Alexa") is False
    assert provider.detect_phrase("Good morning computer") is False


# ==============================================================================
# 5. MICROPHONE PERMISSION DENIED HANDLING
# ==============================================================================
def test_05_microphone_permission_denied(client):
    # Simulate client logging mic access denial
    event_payload = {
        "event_type": "MIC_PERMISSION_DENIED",
        "phrase": "Hey JARVIS",
        "metadata": {"error": "not-allowed", "browser": "Chrome"}
    }
    res = client.post("/api/v1/voice/wake-word/event", json=event_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ["recorded", "logged"]

    # Status remains accessible and does not crash backend
    stat_res = client.get("/api/v1/voice/wake-word/status")
    assert stat_res.status_code == 200


# ==============================================================================
# 6. STT FAILURE HANDLING
# ==============================================================================
def test_06_stt_failure_handling(client):
    event_payload = {
        "event_type": "VOICE_COMMAND_FAILED",
        "phrase": "Hey JARVIS",
        "metadata": {"reason": "audio-capture-timeout"}
    }
    res = client.post("/api/v1/voice/wake-word/event", json=event_payload)
    assert res.status_code == 200
    assert wake_word_service.get_status().state != "ERROR" or wake_word_service.transition_state("IDLE")


# ==============================================================================
# 7. EMPTY COMMAND HANDLING
# ==============================================================================
def test_07_empty_command(client):
    wake_word_service.start()
    wake_word_service.on_wake_detected("Hey JARVIS")
    assert wake_word_service.get_status().state == "WAKE_WORD_DETECTED"
    
    # Silence timeout triggers silence notification
    wake_word_service.transition_state("LISTENING")
    notification = wake_word_service.handle_command_timeout()
    assert notification == "I didn't hear a command."
    assert wake_word_service.get_status().state == "WAKE_WORD_LISTENING"


# ==============================================================================
# 8. COMMAND TIMEOUT
# ==============================================================================
def test_08_command_timeout():
    status = wake_word_service.get_status()
    assert status.command_timeout_seconds == 8
    wake_word_service.transition_state("LISTENING")
    res = wake_word_service.handle_command_timeout()
    assert res == "I didn't hear a command."
    assert wake_word_service.get_status().state == "WAKE_WORD_LISTENING"


# ==============================================================================
# 9. FOLLOW-UP TIMEOUT
# ==============================================================================
def test_09_follow_up_timeout():
    wake_word_service.start()
    status = wake_word_service.get_status()
    assert status.follow_up_timeout_seconds == 8

    # When follow-up window expires, returns to wake word listening
    wake_word_service.on_follow_up_timeout()
    assert wake_word_service.get_status().state == "WAKE_WORD_LISTENING"


# ==============================================================================
# 10. TTS RESPONSE GENERATION
# ==============================================================================
def test_10_tts_response(client):
    res = client.post("/api/v1/assistant/message", json={"message": "What time is it?"})
    assert res.status_code == 200
    data = res.json()
    assert "response" in data
    assert len(data["response"]) > 0


# ==============================================================================
# 11. WAKE DETECTOR PAUSED DURING TTS
# ==============================================================================
def test_11_wake_detector_paused_during_tts():
    wake_word_service.start()
    assert wake_word_service.get_status().is_paused is False

    # When TTS synthesis begins, wake detector MUST be paused
    wake_word_service.notify_tts_start()
    assert wake_word_service.get_status().is_paused is True
    assert wake_word_service.get_status().state == "RESPONDING"


# ==============================================================================
# 12. WAKE DETECTOR RESUMES AFTER TTS
# ==============================================================================
def test_12_wake_detector_resumes_after_tts():
    # When TTS finishes, detector resumes
    wake_word_service.notify_tts_end()
    assert wake_word_service.get_status().is_paused is False
    assert wake_word_service.get_status().state in ["WAKE_WORD_LISTENING", "LISTENING"]


# ==============================================================================
# 13. NO SELF-ACTIVATION PREVENTION
# ==============================================================================
def test_13_no_self_activation():
    # Simulate JARVIS speaking
    wake_word_service.notify_tts_start()
    assert wake_word_service.get_status().is_paused is True

    # If the microphone captures audio while speaking, it must NOT trigger wake word
    result = wake_word_service.on_wake_detected("Hey JARVIS")
    assert result is False  # Blocked!
    assert wake_word_service.get_status().state == "RESPONDING"

    wake_word_service.notify_tts_end()


# ==============================================================================
# 14. TEXT ASSISTANT REMAINS FUNCTIONAL
# ==============================================================================
def test_14_text_assistant_remains_functional(client):
    res = client.post("/api/v1/assistant/message", json={"message": "Hello JARVIS, status report."})
    assert res.status_code == 200
    data = res.json()
    assert "response" in data
    assert data["intent"] in ["SYSTEM_STATUS", "CHAT", "GENERAL_QUERY", "PROJECT_QUERY"]


# ==============================================================================
# 15. MANUAL MICROPHONE REMAINS FUNCTIONAL
# ==============================================================================
def test_15_manual_microphone_remains_functional(client):
    # Multimodal endpoint with voice input type represents manual mic transmit
    res = client.post(
        "/api/v1/assistant/multimodal",
        json={"message": "Show me my system information", "input_type": "voice"}
    )
    assert res.status_code == 200
    data = res.json()
    assert "response" in data
    assert "SYSTEM" in data["intent"] or "CHAT" in data["intent"] or "GENERAL" in data["intent"]


# ==============================================================================
# 16. WINDOWS LOCAL AGENT COMMAND (Flow 1)
# ==============================================================================
def test_16_windows_local_agent_command(client):
    mock_local_res = LocalToolExecutionResponse(
        status="SUCCESS",
        tool="launch_application",
        output={"app_name": "chrome", "pid": 4892, "status": "running"},
        verified=True,
        verification_details={"process_found": True, "pid": 4892}
    )

    with patch("app.services.local_agent_service.local_agent_service.execute_tool", return_value=mock_local_res):
        res = client.post("/api/v1/assistant/message", json={"message": "Open Chrome"})
        assert res.status_code == 200
        data = res.json()
        assert "response" in data
        assert "chrome" in data["response"].lower() or "open" in data["response"].lower()
        # Verified
        if data.get("verification"):
            assert any(v["status"] == "VERIFIED" for v in data["verification"])


# ==============================================================================
# 17. FAILED WINDOWS LOCAL AGENT COMMAND (Flow 5: Truthful Failure)
# ==============================================================================
def test_17_failed_windows_local_agent_command(client):
    mock_local_failed = LocalToolExecutionResponse(
        status="FAILED",
        tool="launch_application",
        output={},
        error="Target executable not found in PATH",
        verified=False,
        verification_details={"process_found": False}
    )

    with patch("app.services.local_agent_service.local_agent_service.execute_tool", return_value=mock_local_failed):
        res = client.post("/api/v1/assistant/message", json={"message": "Open Chrome"})
        assert res.status_code == 200
        data = res.json()
        resp_text = data["response"].lower()
        # JARVIS must NOT claim "Chrome is open" on failure
        assert "chrome is open" not in resp_text
        assert ("couldn't" in resp_text or "could not" in resp_text or "failed" in resp_text or "unable" in resp_text or "not found" in resp_text or "error" in resp_text)


# ==============================================================================
# 18. MULTIMODAL VISION COMMAND (Flow 3)
# ==============================================================================
def test_18_multimodal_vision_command(client):
    mock_screen = LocalToolExecutionResponse(
        status="SUCCESS",
        tool="capture_screen",
        output={"resolution": "1920x1080", "format": "PNG", "image_data": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="},
        verified=True,
        verification_details={"frame_valid": True}
    )

    with patch("app.services.local_agent_service.local_agent_service.execute_tool", return_value=mock_screen):
        res = client.post("/api/v1/assistant/message", json={"message": "What is on my screen?"})
        assert res.status_code == 200
        data = res.json()
        assert "response" in data
        assert len(data["response"]) > 0


# ==============================================================================
# 19. SECURITY RESTRICTIONS
# ==============================================================================
def test_19_security_restrictions(client):
    # Destructive or arbitrary system commands must be rejected by planner
    destructive_queries = [
        "powershell rm -rf C:\\",
        "execute python print('hacked')",
        "install keylogger",
        "dump browser cookies"
    ]
    for q in destructive_queries:
        res = client.post("/api/v1/assistant/message", json={"message": q})
        assert res.status_code == 200
        data = res.json()
        # Must not have executed arbitrary shell tool
        if data.get("actions"):
            for act in data["actions"]:
                assert act["tool"] not in ["powershell", "arbitrary_exec", "eval", "keylogger"]


# ==============================================================================
# 20. PRIVACY RESTRICTIONS (Zero raw microphone recordings stored)
# ==============================================================================
def test_20_privacy_restrictions(client):
    # Log an event
    client.post("/api/v1/voice/wake-word/event", json={
        "event_type": "VOICE_COMMAND_COMPLETED",
        "phrase": "Hey JARVIS",
        "metadata": {"duration_ms": 120}
    })

    # Retrieve recent activities
    act_res = client.get("/api/v1/activity/")
    assert act_res.status_code == 200
    activities = act_res.json()
    for act in activities:
        # Check description and title: zero audio blobs
        desc = str(act.get("description", ""))
        assert "data:audio" not in desc
        assert "blob:" not in desc
        assert ".wav" not in desc
        assert ".mp3" not in desc


# ==============================================================================
# 21. DESKTOP LOCAL AGENT WAKE WORD DETECTOR (Unit test)
# ==============================================================================
def test_21_local_agent_wake_detector():
    detector = LocalAgentWakeWordDetector(wake_phrase="Hey JARVIS")
    assert detector.is_running() is False
    assert detector.start() is True
    assert detector.is_running() is True
    
    # Pausing during TTS
    detector.pause()
    assert detector.is_paused is True
    assert detector.on_audio_phrase("Hey JARVIS") is False  # Blocked while paused
    
    detector.resume()
    assert detector.is_paused is False
    assert detector.on_audio_phrase("Hey JARVIS") is True   # Detected
    
    detector.stop()
    assert detector.is_running() is False
