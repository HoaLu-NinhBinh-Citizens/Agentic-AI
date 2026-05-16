"""Unit tests for WebSocketClient."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from interfaces.server.websocket.client import WebSocketClient


class TestWebSocketClient:
    """Test suite for WebSocketClient."""

    @pytest.fixture
    def mock_websocket(self):
        """Create a mock WebSocket."""
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()
        ws.receive_json = AsyncMock()
        return ws

    @pytest.fixture
    def client(self, mock_websocket):
        """Create a WebSocketClient instance."""
        return WebSocketClient(mock_websocket, "test-session")

    @pytest.mark.asyncio
    async def test_start_creates_tasks(self, client):
        """Test that start() creates sender and heartbeat tasks."""
        await client.start()
        assert client._sender_task is not None
        assert client._heartbeat_task is not None
        assert not client._sender_task.done()
        assert not client._heartbeat_task.done()
        await client.close()

    @pytest.mark.asyncio
    async def test_send_event_queues_event(self, client, mock_websocket):
        """Test that send_event queues the event."""
        await client.start()
        event = {"type": "token", "data": {"content": "H"}}
        result = await client.send_event(event)
        assert result is True
        await asyncio.sleep(0.1)
        mock_websocket.send_json.assert_called()
        await client.close()

    @pytest.mark.asyncio
    async def test_send_event_when_cancelled(self, client):
        """Test that send_event returns False when cancelled."""
        await client.start()
        client._cancelled = True
        event = {"type": "token", "data": {"content": "H"}}
        result = await client.send_event(event)
        assert result is False
        await client.close()

    @pytest.mark.asyncio
    async def test_is_cancelled(self, client):
        """Test is_cancelled property."""
        assert client.is_cancelled() is False
        client._cancelled = True
        assert client.is_cancelled() is True

    @pytest.mark.asyncio
    async def test_close_cancels_tasks(self, client, mock_websocket):
        """Test that close() cancels all tasks."""
        await client.start()
        await client.close()
        await asyncio.sleep(0.1)
        assert client._sender_task.done()
        assert client._heartbeat_task.done()
        mock_websocket.close.assert_called()

    @pytest.mark.asyncio
    async def test_backpressure_drops_old_token(self, client, mock_websocket):
        """Test that backpressure drops oldest token when queue is full."""
        await client.start()

        event = {"type": "token", "data": {"content": "X"}}
        for _ in range(150):
            await client.send_event(event)

        await asyncio.sleep(0.2)
        assert mock_websocket.send_json.call_count >= 100

        done_event = {"type": "done", "data": {"success": True}}
        result = await client.send_event(done_event)
        assert result is True
        await client.close()

    @pytest.mark.asyncio
    async def test_connection_closed_event(self, client):
        """Test connection_closed_event is set when closed."""
        event = client.connection_closed_event()
        assert not event.is_set()
        await client.close()
        assert event.is_set()
