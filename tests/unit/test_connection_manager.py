"""Unit tests for ConnectionManager (Phase 1B)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from interfaces.server.websocket.manager import (
    ConnectionManager,
    MAX_CONCURRENT_CONNECTIONS_PER_SESSION,
)
from interfaces.server.websocket.client import WebSocketClient


class TestConnectionManager:
    """Test suite for ConnectionManager (Phase 1B)."""

    def setup_method(self):
        """Create a fresh manager for each test."""
        self.manager = ConnectionManager()

    @pytest.fixture
    def mock_websocket(self):
        """Create a mock WebSocket."""
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.close = AsyncMock()
        return ws

    @pytest.mark.asyncio
    async def test_connect_adds_client(self, mock_websocket):
        """Test that connect adds WebSocketClient to the dictionary."""
        client = await self.manager.connect("session-1", mock_websocket)

        assert client is not None
        assert isinstance(client, WebSocketClient)
        mock_websocket.accept.assert_called_once()

        clients = self.manager.get_clients("session-1")
        assert len(clients) == 1

    @pytest.mark.asyncio
    async def test_connect_multiple_clients(self, mock_websocket):
        """Test connecting multiple clients to same session."""
        ws1 = MagicMock()
        ws1.accept = AsyncMock()
        ws1.close = AsyncMock()

        ws2 = MagicMock()
        ws2.accept = AsyncMock()
        ws2.close = AsyncMock()

        client1 = await self.manager.connect("session-1", ws1)
        client2 = await self.manager.connect("session-1", ws2)

        assert client1 is not None
        assert client2 is not None

        clients = self.manager.get_clients("session-1")
        assert len(clients) == 2

    @pytest.mark.asyncio
    async def test_connect_max_limit(self, mock_websocket):
        """Test that max connections limit is enforced."""
        ws_list = []
        for _ in range(MAX_CONCURRENT_CONNECTIONS_PER_SESSION):
            ws = MagicMock()
            ws.accept = AsyncMock()
            ws.close = AsyncMock()
            ws_list.append(ws)
            client = await self.manager.connect("session-1", ws)
            assert client is not None

        ws_extra = MagicMock()
        ws_extra.accept = AsyncMock()
        ws_extra.close = AsyncMock()

        extra_client = await self.manager.connect("session-1", ws_extra)
        assert extra_client is None
        ws_extra.close.assert_called()

    @pytest.mark.asyncio
    async def test_disconnect_removes_client(self, mock_websocket):
        """Test that disconnect removes client from dict."""
        client = await self.manager.connect("session-1", mock_websocket)
        assert len(self.manager.get_clients("session-1")) == 1

        await self.manager.disconnect("session-1", client)
        assert len(self.manager.get_clients("session-1")) == 0

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_session(self):
        """Test that disconnect handles nonexistent session gracefully."""
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.close = AsyncMock()
        client = WebSocketClient(mock_ws, "nonexistent")
        await client.close()

        await self.manager.disconnect("nonexistent", client)

    @pytest.mark.asyncio
    async def test_send_to_session_sends_to_all(self, mock_websocket):
        """Test that send_to_session sends to all clients."""
        ws1 = MagicMock()
        ws1.accept = AsyncMock()
        ws1.close = AsyncMock()

        ws2 = MagicMock()
        ws2.accept = AsyncMock()
        ws2.close = AsyncMock()

        client1 = await self.manager.connect("session-1", ws1)
        client2 = await self.manager.connect("session-1", ws2)

        event = {"type": "test", "data": {"value": 123}}
        await self.manager.send_to_session("session-1", event)

        await asyncio.sleep(0.1)

        # Verify clients are still connected and can send
        assert len(self.manager.get_clients("session-1")) == 2

    @pytest.mark.asyncio
    async def test_send_to_nonexistent_session(self):
        """Test that send_to_session handles nonexistent session gracefully."""
        event = {"type": "test"}
        await self.manager.send_to_session("nonexistent", event)

    @pytest.mark.asyncio
    async def test_close_all_for_session(self, mock_websocket):
        """Test that close_all_for_session closes all clients."""
        client1 = await self.manager.connect("session-1", mock_websocket)
        await self.manager.close_all_for_session("session-1")

        assert len(self.manager.get_clients("session-1")) == 0

    @pytest.mark.asyncio
    async def test_get_client_count(self, mock_websocket):
        """Test get_client_count returns correct number."""
        assert self.manager.get_client_count("session-1") == 0

        await self.manager.connect("session-1", mock_websocket)
        assert self.manager.get_client_count("session-1") == 1

    @pytest.mark.asyncio
    async def test_get_clients_empty_for_nonexistent(self):
        """Test that get_clients returns empty list for unknown session."""
        clients = self.manager.get_clients("nonexistent")
        assert clients == []

    @pytest.mark.asyncio
    async def test_broadcast_to_session(self, mock_websocket):
        """Test broadcast_to_session is alias for send_to_session."""
        await self.manager.connect("session-1", mock_websocket)

        event = {"type": "broadcast"}
        await self.manager.broadcast_to_session("session-1", event)

    @pytest.mark.asyncio
    async def test_close_client(self, mock_websocket):
        """Test close_client closes specific client."""
        client = await self.manager.connect("session-1", mock_websocket)

        await self.manager.close_client("session-1", client)

        assert len(self.manager.get_clients("session-1")) == 0
