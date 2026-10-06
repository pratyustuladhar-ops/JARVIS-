def test_memory_crud(client):
    # 1. List memories
    res = client.get("/api/v1/memory")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    # 2. Create memory
    new_mem = {
        "content": "Operator prefers dark mode HUD interface",
        "memory_type": "PREFERENCE",
        "importance": 0.95
    }
    create_res = client.post("/api/v1/memory", json=new_mem)
    assert create_res.status_code == 201
    mem_id = create_res.json()["id"]

    # 3. Get memory by ID
    get_res = client.get(f"/api/v1/memory/{mem_id}")
    assert get_res.status_code == 200
    assert get_res.json()["content"] == new_mem["content"]

    # 4. Update memory
    update_res = client.put(f"/api/v1/memory/{mem_id}", json={"importance": 1.0})
    assert update_res.status_code == 200
    assert update_res.json()["importance"] == 1.0

    # 5. Delete memory
    del_res = client.delete(f"/api/v1/memory/{mem_id}")
    assert del_res.status_code == 200

    # 6. Verify deletion
    verify_res = client.get(f"/api/v1/memory/{mem_id}")
    assert verify_res.status_code == 404
