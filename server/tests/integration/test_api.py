"""测试健康检查与基础 API"""


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_prefixed(client):
    """/api/v1/health 是 Dockerfile healthcheck 和 Electron waitForBackend 使用的路径"""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_create_task(client):
    resp = client.post("/api/v1/tasks", json={"video_url": "https://youtube.com/x"})
    assert resp.status_code == 200
    assert "task_id" in resp.json()


def test_list_models(client):
    resp = client.get("/api/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "llm_providers" in data
    assert "asr_providers" in data
    assert "qwen" in data["llm_providers"]
    assert "funasr" in data["asr_providers"]


def test_get_config(client):
    resp = client.get("/api/v1/config")
    assert resp.status_code == 200
    data = resp.json()
    # 不应泄露任何密钥
    assert data["llm_provider"] == "qwen"
