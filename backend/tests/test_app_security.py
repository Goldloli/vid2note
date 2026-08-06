"""Application-level security regression tests."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import Request
from starlette.responses import Response

from src.main import add_security_headers, app, global_exception_handler


def _request(path: str = "/api/v1/test") -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("localhost", 8765),
        }
    )


def test_global_exception_response_does_not_leak_internal_message():
    response = asyncio.run(
        global_exception_handler(_request(), RuntimeError("secret-internal-detail"))
    )
    body = json.loads(response.body)
    assert response.status_code == 500
    assert "secret-internal-detail" not in response.body.decode()
    assert body["request_id"]


def test_security_headers_are_added():
    async def call_next(_request):
        return Response("ok")

    response = asyncio.run(add_security_headers(_request(), call_next))
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "SAMEORIGIN"
    assert "default-src 'self'" in response.headers["content-security-policy"]


def test_importing_v1_app_does_not_create_legacy_config(tmp_path):
    config_dir = tmp_path / "config"
    env = os.environ.copy()
    env["CONFIG_DIR"] = str(config_dir)
    result = subprocess.run(
        [sys.executable, "-c", "import src.main"],
        cwd=Path(__file__).resolve().parent.parent,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not (config_dir / "config.yaml").exists()


def test_legacy_upload_and_process_routes_are_not_exposed():
    paths = {path for route in app.routes if (path := getattr(route, "path", None))}
    assert not any(path.startswith("/api/v1/upload") for path in paths)
    assert not any(path.startswith("/api/v1/process") for path in paths)
