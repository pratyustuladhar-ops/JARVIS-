def test_get_activity(client):
    res = client.get("/api/v1/activity")
    assert res.status_code == 200
    activities = res.json()
    assert isinstance(activities, list)
    assert len(activities) >= 1
    assert "event_type" in activities[0]
    assert "description" in activities[0]
