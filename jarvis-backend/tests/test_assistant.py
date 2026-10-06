def test_chat_project_analysis(client):
    payload = {"message": "Analyze my project"}
    response = client.post("/api/v1/assistant/chat", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "message" in data
    assert data["intent"] == "PROJECT_ANALYSIS"
    assert isinstance(data["plan"], list)
    assert len(data["plan"]) > 0
    assert data["tool"] == "project_analyzer"
    assert data["status"] == "completed"
    assert data["verified"] is True


def test_chat_memory_retrieval(client):
    payload = {"message": "What is my preference for Java?"}
    response = client.post("/api/v1/assistant/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["memory_accessed"] is not None


def test_chat_empty_message(client):
    payload = {"message": "   "}
    response = client.post("/api/v1/assistant/chat", json=payload)
    assert response.status_code == 400


def test_system_status(client):
    response = client.get("/api/v1/assistant/system-status")
    assert response.status_code == 200
    data = response.json()
    assert "node" in data
