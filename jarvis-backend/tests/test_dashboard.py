def test_get_dashboard_telemetry(client):
    response = client.get("/api/v1/dashboard")
    assert response.status_code == 200
    data = response.json()

    assert "assistant_status" in data
    assert data["assistant_status"]["name"] == "JARVIS"
    assert "system_status" in data
    assert data["system_status"]["backend"] == "online"
    assert "agent_pipeline" in data
    assert len(data["agent_pipeline"]["nodes"]) == 6
    assert "active_tasks" in data
    assert len(data["active_tasks"]) >= 1
    assert "projects" in data
    assert len(data["projects"]) >= 1
    assert "recent_activities" in data
    assert "ai_insight" in data
    assert "quick_actions" in data
