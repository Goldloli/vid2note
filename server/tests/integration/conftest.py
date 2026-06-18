"""集成测试共享 fixtures"""

import pytest
from fastapi.testclient import TestClient

from vid2note_server.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "data")) as test_client:
        yield test_client
