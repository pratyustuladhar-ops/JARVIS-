def test_cms_config_crud_and_content_map(client):
    # 1. Fetch CMS content map
    map_res = client.get("/api/v1/cms/content")
    assert map_res.status_code == 200
    content_map = map_res.json()
    assert isinstance(content_map, dict)
    assert "dashboard" in content_map

    # 2. List configs
    list_res = client.get("/api/v1/cms/config")
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1

    # 3. Create/Upsert CMS config
    new_cfg = {
        "key": "theme.hud_glow_intensity",
        "value": "0.85",
        "type": "number",
        "category": "theme",
        "description": "HUD glow intensity factor",
        "is_active": True
    }
    create_res = client.post("/api/v1/cms/config", json=new_cfg)
    assert create_res.status_code == 201
    cfg_id = create_res.json()["id"]

    # 4. Update CMS config
    update_res = client.put(f"/api/v1/cms/config/{cfg_id}", json={"value": "0.95"})
    assert update_res.status_code == 200
    assert update_res.json()["value"] == "0.95"

    # 5. Delete CMS config
    del_res = client.delete(f"/api/v1/cms/config/{cfg_id}")
    assert del_res.status_code == 200
