"""测试健康检查"""

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_create_task(client):
    resp = client.post("/api/v1/tasks", json={"video_url": "https://youtube.com/x"})
    assert resp.status_code == 200
    assert "task_id" in resp.json()
