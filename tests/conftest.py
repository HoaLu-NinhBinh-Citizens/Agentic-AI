"""Pytest configuration for Phase 1A tests."""

from __future__ import annotations

import pytest


@pytest.fixture
async def test_client():
    """Create an async HTTP client for testing the FastAPI app."""
    from httpx import ASGITransport, AsyncClient

    from interfaces.server.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
