def test_projects_crud(client):
    # 1. List projects
    res = client.get("/api/v1/projects")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    # 2. Create project
    new_proj = {
        "name": "Neural Reasoning Kernel",
        "description": "Autonomous planning and tool-calling graph executor",
        "status": "ACTIVE",
        "progress": 45,
        "repo_path": "/workspace/neural-kernel",
        "technologies": "Python, PyTorch, FastAPI",
        "file_count": 32
    }
    create_res = client.post("/api/v1/projects", json=new_proj)
    assert create_res.status_code == 201
    proj_id = create_res.json()["id"]

    # 3. Get project by ID
    get_res = client.get(f"/api/v1/projects/{proj_id}")
    assert get_res.status_code == 200
    assert get_res.json()["name"] == new_proj["name"]

    # 4. Update project
    update_res = client.put(f"/api/v1/projects/{proj_id}", json={"progress": 55})
    assert update_res.status_code == 200
    assert update_res.json()["progress"] == 55

    # 5. Delete project
    del_res = client.delete(f"/api/v1/projects/{proj_id}")
    assert del_res.status_code == 200

    # 6. Verify deletion
    verify_res = client.get(f"/api/v1/projects/{proj_id}")
    assert verify_res.status_code == 404
