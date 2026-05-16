"""Unit tests for ConnectionManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from interfaces.server.websocket.manager import ConnectionManager


class TestConnectionManager:
    """Test suite for ConnectionManager."""

    def setup_method(self):
        """Create a fresh manager for each test."""
        self.manager = ConnectionManager()

    @pytest.mark.asyncio
    async def test_connect_adds_websocket(self):
        """Test that connect adds WebSocket to the dictionary."""
        ws = MagicMock()
        ws.accept = AsyncMock()

        await self.manager.connect("session-1", ws)
        ws.accept.assert_called_once()

        connections = self.manager.get_connections("session-1")
        assert len(connections) == 1
        assert connections[0] == ws

    @pytest.mark.asyncio
    async def test_connect_multiple_sessions(self):
        """Test connecting multiple websockets to same session."""
        ws1 = MagicMock()
        ws1.accept = AsyncMock()
        ws2 = MagicMock()
        ws2.accept = AsyncMock()

        await self.manager.connect("session-1", ws1)
        await self.manager.connect("session-1", ws2)

        connections = self.manager.get_connections("session-1")
        assert len(connections) == 2
        assert ws1 in connections
        assert ws2 in connections

    @pytest.mark.asyncio
    async def test_disconnect_removes_websocket(self):
        """Test that disconnect removes WebSocket from dict."""
        ws = MagicMock()
        ws.accept = AsyncMock()

        await self.manager.connect("session-1", ws)
        assert len(self.manager.get_connections("session-1")) == 1

        self.manager.disconnect("session-1", ws)
        assert len(self.manager.get_connections("session-1")) == 0

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_session(self):
        """Test that disconnect handles nonexistent session gracefully."""
        ws = MagicMock()
        self.manager.disconnect("nonexistent", ws)

    @pytest.mark.asyncio
    async def test_send_to_session_sends_to_all(self):
        """Test that send_to_session sends to all connections."""
        ws1 = MagicMock()
        ws1.accept = AsyncMock()
        ws1.send_json = AsyncMock()
        ws2 = MagicMock()
        ws2.accept = AsyncMock()
        ws2.send_json = AsyncMock()

        await self.manager.connect("session-1", ws1)
        await self.manager.connect("session-1", ws2)

        event = {"type": "test", "data": {"value": 123}}
        await self.manager.send_to_session("session-1", event)

        ws1.send_json.assert_called_once_with(event)
        ws2.send_json.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_send_to_nonexistent_session(self):
        """Test that send_to_session handles nonexistent session gracefully."""
        event = {"type": "test"}
        await self.manager.send_to_session("nonexistent", event)

    @pytest.mark.asyncio
    async def test_close_all_for_session(self):
        """Test that close_all_for_session removes all connections."""
        ws1 = MagicMock()
        ws1.accept = AsyncMock()
        ws2 = MagicMock()
        ws2.accept = AsyncMock()

        await self.manager.connect("session-1", ws1)
        await self.manager.connect("session-1", ws2)

        self.manager.close_all_for_session("session-1")

        assert len(self.manager.get_connections("session-1")) == 0
        assert "session-1" not in self.manager._connections

    @pytest.mark.asyncio
    async def test_get_connections_empty_for_nonexistent(self):
        """Test that get_connections returns empty list for unknown session."""
        connections = self.manager.get_connections("nonexistent")
        assert connections == []

    @pytest.mark.asyncio
    async def test_disconnect_only_removes_target(self):
        """Test that disconnect only removes the specified WebSocket."""
        ws1 = MagicMock()
        ws1.accept = AsyncMock()
        ws2 = MagicMock()
        ws2.accept = AsyncMock()

        await self.manager.connect("session-1", ws1)
        await self.manager.connect("session-1", ws2)

        self.manager.disconnect("session-1", ws1)

        connections = self.manager.get_connections("session-1")
        assert len(connections) == 1
        assert ws2 in connections
        assert ws1 not in connections
