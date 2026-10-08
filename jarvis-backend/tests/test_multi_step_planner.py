import json
import pytest
from app.ai.intent import intent_detector, IntentDetectionResult
from app.ai.decomposer import multi_step_decomposer
from app.ai.planner import agent_planner, ExecutionPlan, PlanStep
from app.ai.tools import agent_tool_registry
from app.ai.executor import tool_executor, ExecutionResult
from app.ai.verifier import verification_engine, VerificationResult
from app.ai.agent import jarvis_agent
from app.ai.context import AgentContext
from app.models.activity import Activity
from app.models.local_agent import LocalAgentDevice
from local_agent.agent import windows_local_agent


def test_01_single_step_command_still_works(client):
    """Test 1: Single-step command still produces correct single-step intent and execution."""
    res = client.post("/api/v1/assistant/message", json={"message": "List my tasks"})
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "LIST_TASKS"
    assert len(data["plan"]) == 1
    assert data["plan"][0]["tool_name"] == "task_list"
    assert data["plan"][0]["status"] in ["COMPLETED", "VERIFIED"]


def test_02_two_step_command_creates_two_steps(client):
    """Test 2: Two-step command creates exactly two steps in the execution plan."""
    # Test 'Open Chrome and open YouTube.'
    intent_res = intent_detector.detect("Open Chrome and open YouTube.")
    assert intent_res.intent == "MULTI_STEP_COMMAND"
    assert len(intent_res.entities["sub_commands"]) == 2

    ctx = AgentContext(user_message="Open Chrome and open YouTube.", intent="MULTI_STEP_COMMAND")
    plan = agent_planner.create_plan(intent_res, ctx)
    assert plan.validation_status == "VALID"
    assert len(plan.steps) == 2
    assert plan.steps[0].step_number == 1
    assert plan.steps[1].step_number == 2


def test_03_three_step_command_creates_three_steps():
    """Test 3: Three-step command creates exactly three steps."""
    raw = "Open Chrome, then open YouTube, then open Spotify."
    intent_res = intent_detector.detect(raw)
    assert intent_res.intent == "MULTI_STEP_COMMAND"
    assert len(intent_res.entities["sub_commands"]) == 3

    ctx = AgentContext(user_message=raw, intent="MULTI_STEP_COMMAND")
    plan = agent_planner.create_plan(intent_res, ctx)
    assert plan.validation_status == "VALID"
    assert len(plan.steps) == 3
    assert [s.step_number for s in plan.steps] == [1, 2, 3]


def test_04_correct_tool_selected():
    """Test 4: Correct safe registered tools selected for each decomposed step."""
    raw = "Open Chrome and open YouTube."
    intent_res = intent_detector.detect(raw)
    ctx = AgentContext(user_message=raw, intent="MULTI_STEP_COMMAND")
    plan = agent_planner.create_plan(intent_res, ctx)

    assert plan.steps[0].tool_name == "local_open_application"
    assert plan.steps[1].tool_name == "local_open_url"


def test_05_correct_arguments():
    """Test 5: Correct tool arguments populated for each step."""
    raw = "Open Chrome, then open YouTube."
    intent_res = intent_detector.detect(raw)
    ctx = AgentContext(user_message=raw, intent="MULTI_STEP_COMMAND")
    plan = agent_planner.create_plan(intent_res, ctx)

    assert plan.steps[0].parameters.get("application") == "chrome"
    assert "youtube" in plan.steps[1].parameters.get("url", "").lower()


def test_06_dependencies_are_correct():
    """Test 6: Step dependencies correctly declare sequential execution order."""
    raw = "Open Chrome, then open YouTube, then open Spotify."
    intent_res = intent_detector.detect(raw)
    ctx = AgentContext(user_message=raw, intent="MULTI_STEP_COMMAND")
    plan = agent_planner.create_plan(intent_res, ctx)

    assert plan.steps[0].depends_on == []
    assert plan.steps[1].depends_on == [1]
    assert plan.steps[2].depends_on == [2]


def test_07_step_2_does_not_execute_when_step_1_fails(db_session):
    """Test 7: Step 2 is SKIPPED and does not execute if Step 1 execution fails."""
    # Create a plan where Step 1 is an un-allowlisted application that will fail
    plan = ExecutionPlan(
        goal="Open non-existent app and YouTube",
        intent="MULTI_STEP_COMMAND",
        steps=[
            PlanStep(
                step_number=1,
                tool_name="local_open_application",
                parameters={"application": "non_existent_fake_app_12345"},
                depends_on=[]
            ),
            PlanStep(
                step_number=2,
                tool_name="local_open_url",
                parameters={"url": "https://youtube.com"},
                depends_on=[1]
            )
        ]
    )

    # Execute through jarvis_agent
    res = jarvis_agent.process(
        db=db_session,
        message="Open non_existent_fake_app_12345 and open YouTube."
    )

    # Step 1 should be FAILED, Step 2 should be SKIPPED
    assert res["success"] is False
    assert res["failed_step"] == 1
    assert len(res["plan"]) == 2
    assert res["plan"][0]["status"] == "FAILED"
    assert res["plan"][1]["status"] == "SKIPPED"
    # YouTube (step 2) must not have been executed
    assert len(res["actions"]) == 1
    assert "couldn't open" in res["response"].lower() or "didn't continue" in res["response"].lower()


def test_08_failed_verification_stops_the_plan(db_session, monkeypatch):
    """Test 8: Failed verification on Step 1 immediately stops the plan and skips Step 2."""
    step2_executed = False

    orig_execute = tool_executor.execute_step

    def mock_execute(db, step):
        nonlocal step2_executed
        if step.step_number == 2:
            step2_executed = True
        return orig_execute(db, step)

    # Mock verifier to report FAILED for step 1
    def mock_verify(db, exec_res, params):
        if exec_res.tool_name == "local_open_application":
            return VerificationResult(status="FAILED", tool="local_open_application", detail="Process failed to launch")
        return VerificationResult(status="VERIFIED", tool=exec_res.tool_name, detail="OK")

    monkeypatch.setattr(tool_executor, "execute_step", mock_execute)
    monkeypatch.setattr(verification_engine, "verify", mock_verify)

    res = jarvis_agent.process(
        db=db_session,
        message="Open Chrome and open YouTube."
    )

    assert step2_executed is False
    assert res["success"] is False
    assert res["plan"][0]["status"] == "FAILED"
    assert res["plan"][1]["status"] == "SKIPPED"


def test_09_invalid_tool_is_rejected():
    """Test 9: Invalid or unregistered tool is rejected by the PlanValidator."""
    plan = ExecutionPlan(
        goal="Test invalid tool",
        intent="MULTI_STEP_COMMAND",
        steps=[
            PlanStep(step_number=1, tool_name="unregistered_dangerous_tool", parameters={})
        ]
    )
    is_valid, error = agent_planner.validator.validate(plan)
    assert is_valid is False
    assert "Unauthorized or unknown tool" in error


def test_10_arbitrary_shell_command_is_rejected():
    """Test 10: Arbitrary shell command names are rejected by PlanValidator."""
    for bad_tool in ["powershell", "cmd", "bash", "python", "shell", "terminal_exec"]:
        plan = ExecutionPlan(
            goal=f"Run {bad_tool}",
            intent="MULTI_STEP_COMMAND",
            steps=[PlanStep(step_number=1, tool_name=bad_tool, parameters={})]
        )
        is_valid, error = agent_planner.validator.validate(plan)
        assert is_valid is False
        assert "Arbitrary system commands cannot be executed" in error


def test_11_more_than_max_plan_steps_is_rejected():
    """Test 11: Plan exceeding MAX_PLAN_STEPS (10) is rejected safely."""
    plan = ExecutionPlan(
        goal="Do 11 steps",
        intent="MULTI_STEP_COMMAND",
        steps=[
            PlanStep(step_number=i, tool_name="task_list") for i in range(1, 12)
        ]
    )
    is_valid, error = agent_planner.validator.validate(plan)
    assert is_valid is False
    assert "exceeds maximum allowed steps limit" in error


def test_12_local_agent_authentication_failure_handled(db_session, monkeypatch):
    """Test 12: Local agent authentication failure returns DENIED and halts multi-step plan gracefully."""
    # Test direct local agent execution with invalid token
    action_res = windows_local_agent.execute_action("open_application", {"application": "chrome"}, auth_token="invalid_bad_token")
    assert action_res["status"] == "DENIED"
    assert "invalid" in action_res["error"].lower() or "missing" in action_res["error"].lower()

    # When tool executor runs with invalid device token in backend
    from app.services.local_agent_service import local_agent_service
    orig_exec = local_agent_service.execute_tool

    def mock_local_exec(db, tool, params):
        from app.schemas.local_agent import LocalToolExecutionResponse
        return LocalToolExecutionResponse(
            status="DENIED",
            tool=tool,
            verified=False,
            error="Authentication token missing or invalid."
        )

    monkeypatch.setattr(local_agent_service, "execute_tool", mock_local_exec)

    res = jarvis_agent.process(db=db_session, message="Open Chrome and open YouTube.")
    assert res["success"] is False
    assert res["plan"][0]["status"] == "FAILED"
    assert res["plan"][1]["status"] == "SKIPPED"


def test_13_security_malicious_commands_blocked(client):
    """Test 13: Malicious and dangerous commands are strictly blocked and never execute."""
    dangerous_inputs = [
        "Run powershell and delete files.",
        "Execute cmd /c dir",
        "Run python script to delete files",
        "Run shell command and then open Chrome.",
        "powershell Get-Process"
    ]
    for inp in dangerous_inputs:
        res = client.post("/api/v1/assistant/message", json={"message": inp})
        assert res.status_code == 200
        data = res.json()
        assert data["agent_state"] == "ERROR" or data["intent"] == "BLOCKED_COMMAND"
        assert len(data["actions"]) == 0  # No tool actions executed!
        assert "arbitrary" in data["response"].lower() or "not proceed" in data["response"].lower() or "cannot be executed" in data["response"].lower()


def test_14_supported_multi_step_examples(client):
    """Test 14: All minimum required multi-step examples create valid structured plans."""
    examples = [
        ("Open Chrome and open YouTube.", 2, ["local_open_application", "local_open_url"]),
        ("Open Chrome and Edge.", 2, ["local_open_application", "local_open_application"]),
        ("Open Notepad and Calculator.", 2, ["local_open_application", "local_open_application"]),
        ("Open Chrome, then open YouTube, then open Spotify.", 3, ["local_open_application", "local_open_url", "local_open_application"]),
        ("Create a task to study DBMS and open VS Code.", 2, ["task_create", "local_open_application"]),
        ("Open VS Code then open my project folder.", 2, ["local_open_application", "local_open_folder"])
    ]

    for utterance, expected_step_count, expected_tools in examples:
        intent_res = intent_detector.detect(utterance)
        assert intent_res.intent == "MULTI_STEP_COMMAND"
        ctx = AgentContext(user_message=utterance, intent="MULTI_STEP_COMMAND")
        plan = agent_planner.create_plan(intent_res, ctx)
        assert plan.validation_status == "VALID"
        assert len(plan.steps) == expected_step_count
        for i, expected_t in enumerate(expected_tools):
            assert plan.steps[i].tool_name == expected_t


def test_15_activity_logging_records_plan_and_step_events(client, db_session):
    """Test 15: Execution records PLAN_CREATED, STEP_STARTED, STEP_VERIFIED, and PLAN_COMPLETED events."""
    # Execute valid two-step task + app command
    res = client.post("/api/v1/assistant/message", json={"message": "Create a task to study DBMS and open Notepad."})
    assert res.status_code == 200

    recent_acts = db_session.query(Activity).order_by(Activity.id.desc()).limit(15).all()
    event_types = [a.event_type for a in recent_acts]

    assert "PLAN_CREATED" in event_types
    assert "STEP_STARTED" in event_types
    assert "STEP_COMPLETED" in event_types
    assert "STEP_VERIFIED" in event_types


def test_16_response_generation_natural_phrasing(client, monkeypatch):
    """Test 16: Response formulated naturally for multi-step success and truthful failure."""
    # 1. Test Truthful Failure Response when Step 1 fails
    fail_res = client.post("/api/v1/assistant/message", json={"message": "Open non_existent_app_xyz and Calculator."})
    assert fail_res.status_code == 200
    fail_data = fail_res.json()
    assert "couldn't open" in fail_data["response"].lower() or "didn't continue" in fail_data["response"].lower()

    # 2. Test Successful Execution Response ("Done. Notepad is open and Calculator is open.")
    client.post("/api/v1/local-agent/register", json={
        "device_name": "JARVIS-WINDOWS-01",
        "platform": "Windows",
        "version": "1.0.0",
        "auth_token": "jarvis_windows_local_agent_secret_2026",
        "port": 8001,
        "available_tools": ["open_application", "open_url", "get_current_time", "get_system_info"]
    })

    # Mock tool executor to simulate successful launch with PID and verification
    orig_exec = tool_executor.execute_step
    def mock_exec_step(db, step):
        if step.tool_name == "local_open_application":
            app = step.parameters.get("application", "Application")
            return ExecutionResult(
                tool_name="local_open_application",
                status="SUCCESS",
                output={"status": "launched", "application": app, "pid": 1234, "verified": True},
                duration_ms=45.0
            )
        return orig_exec(db, step)

    monkeypatch.setattr(tool_executor, "execute_step", mock_exec_step)

    res = client.post("/api/v1/assistant/message", json={"message": "Open Notepad and Calculator."})
    assert res.status_code == 200
    data = res.json()
    assert "Done." in data["response"]
    assert "Notepad is open" in data["response"]
    assert "Calculator is open" in data["response"]
    assert data["success"] is True
    assert data["completed_steps"] == 2
