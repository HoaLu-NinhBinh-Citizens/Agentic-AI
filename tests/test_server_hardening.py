"""Integration tests for server hardening (PR-001 / T-02).

Tests CORS enforcement, path validation via HTTP, and timeout configuration.
"""

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

# Ensure src/ is on path
_SRC_DIR = Path(__file__).parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


@pytest.fixture
def workspace(tmp_path):
    """Create a workspace with test files."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')")
    (tmp_path / "readme.txt").write_text("readme content")
    return tmp_path


@pytest.fixture
def test_client(workspace):
    """Create a FastAPI test client with workspace root set."""
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip("fastapi[testclient] not installed")

    from interfaces.server.main import app

    app.state.workspace_root = workspace
    client = TestClient(app, raise_server_exceptions=False)
    return client


class TestFileAPIPathValidation:
    """T-02-I01: File API rejects out-of-workspace paths."""

    def test_read_file_rejects_outside_workspace(self, test_client):
        if os.name == "nt":
            resp = test_client.get("/api/fs/read", params={"path": "C:\\Windows\\System32\\drivers\\etc\\hosts"})
        else:
            resp = test_client.get("/api/fs/read", params={"path": "/etc/passwd"})
        assert resp.status_code == 403

    def test_read_file_accepts_workspace_file(self, test_client, workspace):
        path = str(workspace / "readme.txt")
        resp = test_client.get("/api/fs/read", params={"path": path})
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "readme content"

    def test_read_file_rejects_nonexistent(self, test_client, workspace):
        path = str(workspace / "nonexistent.txt")
        resp = test_client.get("/api/fs/read", params={"path": path})
        assert resp.status_code == 404

    def test_read_dir_rejects_outside_workspace(self, test_client):
        if os.name == "nt":
            resp = test_client.get("/api/fs/dir", params={"path": "C:\\Windows"})
        else:
            resp = test_client.get("/api/fs/dir", params={"path": "/etc"})
        assert resp.status_code == 403

    def test_read_dir_accepts_workspace_dir(self, test_client, workspace):
        path = str(workspace / "src")
        resp = test_client.get("/api/fs/dir", params={"path": path})
        assert resp.status_code == 200
        data = resp.json()
        assert any(item["name"] == "main.py" for item in data["items"])


class TestCORSEnforcement:
    """T-02-I03: CORS header enforcement."""

    def test_cors_rejects_bad_origin(self, test_client):
        resp = test_client.options(
            "/health",
            headers={
                "Origin": "http://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") != "http://evil.example.com"

    def test_cors_accepts_good_origin(self, test_client):
        resp = test_client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


class TestDirectoryAsFile:
    """T-02-S01: Directory path passed to read_file."""

    def test_directory_to_read_file(self, test_client, workspace):
        path = str(workspace / "src")
        resp = test_client.get("/api/fs/read", params={"path": path})
        assert resp.status_code == 404
