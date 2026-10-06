def test_tasks_crud(client):
    # 1. List tasks
    res = client.get("/api/v1/tasks")
    assert res.status_code == 200
    initial_count = len(res.json())

    # 2. Create task
    new_task = {
        "title": "Automated AST Compilation Test",
        "description": "Verifying AST trees for test suite",
        "status": "AI WORKING",
        "priority": "HIGH",
        "progress": 50,
        "eta": "~5m"
    }
    create_res = client.post("/api/v1/tasks", json=new_task)
    assert create_res.status_code == 201
    created_task = create_res.json()
    task_id = created_task["id"]
    assert created_task["title"] == new_task["title"]

    # 3. Get task by ID
    get_res = client.get(f"/api/v1/tasks/{task_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == task_id

    # 4. Update task
    update_payload = {"progress": 100, "status": "COMPLETED"}
    update_res = client.put(f"/api/v1/tasks/{task_id}", json=update_payload)
    assert update_res.status_code == 200
    assert update_res.json()["progress"] == 100
    assert update_res.json()["status"] == "COMPLETED"

    # 5. Delete task
    del_res = client.delete(f"/api/v1/tasks/{task_id}")
    assert del_res.status_code == 200

    # 6. Verify deletion
    verify_res = client.get(f"/api/v1/tasks/{task_id}")
    assert verify_res.status_code == 404
