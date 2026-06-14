"""集成测试共享 fixtures"""
import pytest
from fastapi.testclient import TestClient
from vid2note_server.main import app
from vid2note_core.storage.db import Database

@pytest.fixture
def client(tmp_path):
    Database.reset_instance()
    Database(str(tmp_path / "test.db"))
    yield TestClient(app)
    Database.reset_instance()
