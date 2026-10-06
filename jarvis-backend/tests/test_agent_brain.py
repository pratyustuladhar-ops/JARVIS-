import pytest
from app.ai.agent import jarvis_agent
from app.ai.intent import intent_detector, IntentDetectionResult
from app.ai.planner import agent_planner, ExecutionPlan, PlanStep
from app.ai.tools import agent_tool_registry, BaseAgentTool
from app.ai.executor import tool_executor, ExecutionResult
from app.ai.verifier import verification_engine, VerificationResult
from app.ai.providers import MockAIProvider, OpenAICompatibleProvider


def test_01_simple_chat(client):
    """Test 1: Simple conversational query."""
    res = client.post("/api/v1/assistant/message", json={"message": "Hello JARVIS, are you ready?"})
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] in ["CHAT", "QUESTION"]
    assert "response" in data
    assert data["agent_state"] == "RESPONDING"
    assert data["execution_time_ms"] > 0


def test_02_create_task(client):
    """Test 2: Create task through the AI pipeline with verification."""
    res = client.post("/api/v1/assistant/message", json={"message": "Create a task to finish my DBMS assignment tomorrow"})
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "CREATE_TASK"
    assert len(data["plan"]) > 0
    assert data["plan"][0]["tool_name"] == "task_create"
    assert len(data["actions"]) > 0
    assert data["actions"][0]["status"] == "SUCCESS"
    assert len(data["verification"]) > 0
    assert data["verification"][0]["status"] == "VERIFIED"


def test_03_list_tasks(client):
    """Test 3: List tasks through agent pipeline."""
    res = client.post("/api/v1/assistant/message", json={"message": "List my tasks"})
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "LIST_TASKS"
    assert data["plan"][0]["tool_name"] == "task_list"
    assert data["actions"][0]["status"] == "SUCCESS"
    assert "tasks" in data["response"].lower() or "active" in data["response"].lower()


def test_04_update_task(client):
    """Test 4: Update task status via agent."""
    # First create a task
    create_res = client.post("/api/v1/assistant/message", json={"message": "Create task: Study compiler AST"})
    task_id = create_res.json()["actions"][0]["output"]["id"]

    # Now update it
    update_res = client.post("/api/v1/assistant/message", json={"message": f"Update task #{task_id} to completed"})
    assert update_res.status_code == 200
    data = update_res.json()
    assert data["intent"] == "UPDATE_TASK"
    assert data["plan"][0]["tool_name"] == "task_update"
    assert data["actions"][0]["status"] == "SUCCESS"
    assert data["verification"][0]["status"] == "VERIFIED"


def test_05_delete_task(client):
    """Test 5: Delete task with verification."""
    # Create task to delete
    create_res = client.post("/api/v1/assistant/message", json={"message": "Create task: Temporary test task"})
    task_id = create_res.json()["actions"][0]["output"]["id"]

    # Delete it
    del_res = client.post("/api/v1/assistant/message", json={"message": f"Delete task #{task_id}"})
    assert del_res.status_code == 200
    data = del_res.json()
    assert data["intent"] == "DELETE_TASK"
    assert data["plan"][0]["tool_name"] == "task_delete"
    assert data["verification"][0]["status"] == "VERIFIED"


def test_06_create_project(client):
    """Test 6: Create project repository."""
    res = client.post("/api/v1/assistant/message", json={"message": "Create a project called Autonomous Swarm Engine"})
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "CREATE_PROJECT"
    assert data["plan"][0]["tool_name"] == "project_create"
    assert data["verification"][0]["status"] == "VERIFIED"


def test_07_query_project(client):
    """Test 7: Query project details."""
    res = client.post("/api/v1/assistant/message", json={"message": "Show my projects"})
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "PROJECT_QUERY"
    assert data["plan"][0]["tool_name"] == "project_list"
    assert data["actions"][0]["status"] == "SUCCESS"


def test_08_memory_query(client):
    """Test 8: Memory retrieval."""
    res = client.post("/api/v1/assistant/message", json={"message": "What do you remember about my preferences?"})
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "MEMORY_QUERY"
    assert data["plan"][0]["tool_name"] == "memory_search"


def test_09_memory_creation(client):
    """Test 9: Store a new fact into memory."""
    res = client.post("/api/v1/assistant/message", json={"message": "Remember that I prefer TypeScript for frontend services"})
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "MEMORY_SAVE"
    assert data["plan"][0]["tool_name"] == "memory_create"
    assert data["verification"][0]["status"] == "VERIFIED"


def test_10_system_status(client):
    """Test 10: System diagnostics."""
    res = client.post("/api/v1/assistant/message", json={"message": "System status"})
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "SYSTEM_STATUS"
    assert data["plan"][0]["tool_name"] == "system_status"
    assert data["actions"][0]["status"] == "SUCCESS"


def test_11_low_confidence_intent():
    """Test 11: Low confidence intent handling."""
    # Obscure or ambiguous input
    result = intent_detector.detect("xyz 123 qwerty alpha beta gamma")
    assert result.confidence < 0.99
    assert result.intent in intent_detector.CANDIDATE_INTENTS


def test_12_invalid_tool_rejection(db_session):
    """Test 12: Tool executor rejects unauthorized tools."""
    step = PlanStep(
        step_number=1,
        tool_name="unauthorized_shell_command",
        parameters={"cmd": "rm -rf /"}
    )
    result = tool_executor.execute_step(db_session, step)
    assert result.status == "FAILED"
    assert "not permitted" in result.error


def test_13_invalid_plan_validation():
    """Test 13: Plan validator rejects plans with too many steps or missing parameters."""
    intent_res = IntentDetectionResult(
        intent="CREATE_TASK",
        confidence=0.95,
        entities={},  # Missing title
        strategy_used="rule",
        raw_input=""
    )
    plan = ExecutionPlan(
        goal="Test plan",
        intent="CREATE_TASK",
        steps=[
            PlanStep(step_number=i, tool_name="task_list") for i in range(1, 10)  # > 5 steps
        ]
    )
    is_valid, error = agent_planner.validator.validate(plan)
    assert is_valid is False
    assert "exceeds maximum" in error


def test_14_tool_failure_handling(db_session):
    """Test 14: Graceful handling when tool parameters are invalid in DB."""
    # Delete non-existent task
    step = PlanStep(
        step_number=1,
        tool_name="task_delete",
        parameters={"task_id": 999999}
    )
    result = tool_executor.execute_step(db_session, step)
    assert result.status == "FAILED"
    assert "not found" in result.error


def test_15_verification_failure():
    """Test 15: Verifier correctly flags when expected entity was not created."""
    exec_res = ExecutionResult(
        tool_name="task_create",
        status="SUCCESS",
        output={"id": 999999}  # ID does not exist in db
    )
    # Verification should fail
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        verif = verification_engine.verify(db, exec_res, {"title": "Ghost Task"})
        assert verif.status == "FAILED"
    finally:
        db.close()


def test_16_ai_provider_failure_fallback():
    """Test 16: OpenAI provider gracefully falls back to Mock provider on connection failure."""
    provider = OpenAICompatibleProvider()
    # Test fallback generates response even without valid key
    resp = provider.generate_response("List my tasks", {"intent": "LIST_TASKS", "tool_results": [{"tool_name": "task_list", "status": "SUCCESS", "output": []}]})
    assert "tasks" in resp.lower() or "queue" in resp.lower()
