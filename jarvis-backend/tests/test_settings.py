from app.models.cms import CMSConfig


def test_get_settings(client):
    response = client.get("/api/v1/settings")
    assert response.status_code == 200
    data = response.json()
    assert "assistant_name" in data
    assert data["assistant_name"] == "JARVIS"
    assert "creativity_level" in data
    assert "memory_enabled" in data


def test_update_settings_put(client, db_session):
    update_payload = {
        "assistant_name": "JARVIS_MARK_VII",
        "operator_identity": "TONY_STARK",
        "creativity_level": 0.55,
        "memory_enabled": True,
        "similarity_threshold": 92
    }
    response = client.put("/api/v1/settings", json=update_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["assistant_name"] == "JARVIS_MARK_VII"
    assert data["operator_identity"] == "TONY_STARK"
    assert data["creativity_level"] == 0.55
    assert data["similarity_threshold"] == 92

    # Verify retrieval
    get_res = client.get("/api/v1/settings")
    assert get_res.status_code == 200
    assert get_res.json()["assistant_name"] == "JARVIS_MARK_VII"

    # Verify individual CMSConfig row synchronization in database
    cms_row = db_session.query(CMSConfig).filter(CMSConfig.key == "assistant_name").first()
    assert cms_row is not None
    assert cms_row.value == "JARVIS_MARK_VII"



def test_get_and_put_individual_setting(client):
    # GET individual key
    res = client.get("/api/v1/settings/assistant_name")
    assert res.status_code == 200
    data = res.json()
    assert data["key"] == "assistant_name"
    assert "value" in data

    # PUT individual key
    put_res = client.put("/api/v1/settings/assistant_name", json={"value": "JARVIS_PRIME"})
    assert put_res.status_code == 200
    assert put_res.json()["value"] == "JARVIS_PRIME"

    # Verify main settings reflects it
    get_all = client.get("/api/v1/settings")
    assert get_all.json()["assistant_name"] == "JARVIS_PRIME"


def test_system_status(client):
    res = client.get("/api/v1/system/status")
    assert res.status_code == 200
    data = res.json()
    assert data["api"] == "ONLINE"
    assert data["database"] == "CONNECTED"
    assert data["backend"] == "ONLINE"
    assert data["environment"] == "development"
    assert data["ai_engine"] == "STANDBY"  # Compliant: not claiming ONLINE until AI engine ready


def test_reset_settings(client):
    # First change a value
    client.put("/api/v1/settings", json={"assistant_name": "TEMP_NAME"})
    assert client.get("/api/v1/settings").json()["assistant_name"] == "TEMP_NAME"

    # Reset
    reset_res = client.post("/api/v1/settings/reset")
    assert reset_res.status_code == 200
    assert reset_res.json()["assistant_name"] == "JARVIS"

    # Verify get returns default
    assert client.get("/api/v1/settings").json()["assistant_name"] == "JARVIS"


def test_settings_export_and_purge(client):
    export_res = client.get("/api/v1/settings/export")
    assert export_res.status_code == 200
    assert "manifest" in export_res.json()

    purge_res = client.post("/api/v1/settings/purge-cache")
    assert purge_res.status_code == 200
    assert purge_res.json()["status"] == "PURGED"
