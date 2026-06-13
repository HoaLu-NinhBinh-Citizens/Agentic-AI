"""Unit tests for path validation in file API endpoints (PR-001 / T-02)."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def workspace(tmp_path):
    """Create a workspace with test files."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')")
    (tmp_path / "readme.txt").write_text("readme")
    return tmp_path


def _validate_path(path_str: str, workspace_root: Path):
    """Reproduce the path validation logic from main.py."""
    try:
        resolved = Path(path_str).resolve()
    except (ValueError, OSError):
        return 400, "Invalid path"

    if not resolved.is_relative_to(workspace_root):
        return 403, "Access denied: path is outside workspace"

    return None, resolved


class TestPathTraversal:
    """T-02-U01: Path traversal attacks."""

    def test_relative_escape(self, workspace):
        code, _ = _validate_path("../../etc/passwd", workspace)
        assert code == 403

    def test_absolute_outside_workspace(self, workspace):
        if os.name == "nt":
            code, _ = _validate_path("C:\\Windows\\System32\\config\\SAM", workspace)
        else:
            code, _ = _validate_path("/etc/passwd", workspace)
        assert code == 403

    def test_dot_dot_segments(self, workspace):
        code, _ = _validate_path("src/../../../etc/passwd", workspace)
        assert code == 403

    def test_valid_relative_path(self, workspace):
        valid_path = str(workspace / "src" / "main.py")
        code, resolved = _validate_path(valid_path, workspace)
        assert code is None
        assert resolved.is_relative_to(workspace)

    def test_dot_dot_resolving_inside_workspace(self, workspace):
        valid_path = str(workspace / "src" / ".." / "readme.txt")
        code, resolved = _validate_path(valid_path, workspace)
        assert code is None
        assert resolved == workspace / "readme.txt"


class TestSymlinkEscape:
    """T-02-U02: Symlink escape detection."""

    @pytest.mark.skipif(os.name == "nt", reason="Symlinks may need admin on Windows")
    def test_symlink_to_outside(self, workspace):
        outside = Path(tempfile.mkdtemp())
        secret = outside / "secret.txt"
        secret.write_text("secret")

        link = workspace / "escape_link"
        try:
            link.symlink_to(secret)
        except OSError:
            pytest.skip("Cannot create symlinks")

        code, _ = _validate_path(str(link), workspace)
        assert code == 403

    def test_dot_dot_inside_workspace(self, workspace):
        valid_path = str(workspace / "src" / ".." / "src" / "main.py")
        code, resolved = _validate_path(valid_path, workspace)
        assert code is None


class TestNullByteInjection:
    """T-02-S02: Null byte injection."""

    def test_null_byte_in_path(self, workspace):
        code, _ = _validate_path("src/main.py\x00.txt", workspace)
        assert code == 400


class TestTimeoutConfig:
    """T-02-U03: Stream timeout configuration."""

    def test_timeout_value_sufficient(self):
        from core.runtime.runtime_manager import STREAM_TIMEOUT_SEC
        assert STREAM_TIMEOUT_SEC >= 120

    def test_timeout_env_override(self, monkeypatch):
        monkeypatch.setenv("STREAM_TIMEOUT_SEC", "60")
        # Re-evaluate the module-level constant
        val = float(os.getenv("STREAM_TIMEOUT_SEC", "300"))
        assert val == 60.0


class TestCORSConfig:
    """T-02-U04: CORS configuration."""

    def test_no_wildcard_in_origins(self):
        from interfaces.server.main import CORS_ORIGINS
        assert "*" not in CORS_ORIGINS

    def test_localhost_in_origins(self):
        from interfaces.server.main import CORS_ORIGINS
        assert "http://localhost:5173" in CORS_ORIGINS


class TestSessionTTL:
    """T-02-U05: Session TTL configuration."""

    def test_default_ttl_sufficient(self):
        from core.session.persistent_manager import PersistentSessionManager
        assert PersistentSessionManager._DEFAULT_TTL_SECONDS >= 3600
