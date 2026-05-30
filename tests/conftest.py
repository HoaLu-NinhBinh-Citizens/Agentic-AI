"""Pytest configuration for Phase 1A tests."""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pytest


@pytest.fixture(scope="session")
def project_root_path():
    """Return project root path."""
    return Path(__file__).parent.parent


@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


@pytest.fixture
async def test_client():
    """Create an async HTTP client for testing the FastAPI app."""
    from httpx import ASGITransport, AsyncClient

    from interfaces.server.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
