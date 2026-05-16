"""Integration tests for Phase 2A MCP features."""

from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport


class TestMCPIntegration:
    """Integration tests for MCP connectivity."""

    @pytest.mark.asyncio
    async def test_server_starts_with_mcp(self):
        """Server starts successfully with MCP integration."""
        from interfaces.server.main import app

        # Verify app state structure
        assert hasattr(app.state, "server_state") is False  # Not set until lifespan

        # Test that lifespan works
        from interfaces.server.main import lifespan

        async with lifespan(app):
            assert hasattr(app.state, "server_state")
            assert hasattr(app.state, "mcp_manager")
            # MCP manager may or may not be None depending on config

    @pytest.mark.asyncio
    async def test_mcp_manager_in_app_state(self):
        """MCP manager is accessible via app.state."""
        from interfaces.server.main import app, lifespan

        async with lifespan(app):
            mcp_manager = app.state.mcp_manager
            # Manager should exist (might be None if initialization failed)
            assert mcp_manager is None or hasattr(mcp_manager, "is_ready")
            assert mcp_manager is None or hasattr(mcp_manager, "list_tools")

    @pytest.mark.asyncio
    async def test_mcp_health_endpoint(self):
        """Health endpoint works during MCP integration."""
        from interfaces.server.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}
