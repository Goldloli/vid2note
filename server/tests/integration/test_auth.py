from fastapi.testclient import TestClient
from vid2note_server.main import create_app

TEST_TOKEN = "test-session-token"


def test_write_request_without_token_is_rejected(tmp_path):
    with TestClient(create_app(tmp_path / "data", api_token=TEST_TOKEN)) as client:
        response = client.post(
            "/api/v1/tasks",
            json={"video_url": "https://example.com/video"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_request_with_wrong_token_is_rejected(tmp_path):
    with TestClient(create_app(tmp_path / "data", api_token=TEST_TOKEN)) as client:
        response = client.get(
            "/api/v1/tasks",
            headers={"Authorization": "Bearer wrong-session-token"},
        )

    assert response.status_code == 401


def test_request_with_correct_token_is_allowed(tmp_path):
    with TestClient(create_app(tmp_path / "data", api_token=TEST_TOKEN)) as client:
        response = client.get(
            "/api/v1/tasks",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )

    assert response.status_code == 200


def test_health_remains_available_for_startup_probe(tmp_path):
    with TestClient(create_app(tmp_path / "data", api_token=TEST_TOKEN)) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
