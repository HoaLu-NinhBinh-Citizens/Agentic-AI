"""Unit tests for RuntimeManager (Phase 1B)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.runtime.runtime_manager import RuntimeManager, StreamInfo
from core.agent.mock_agent import MockAgent


class TestRuntimeManager:
    """Test suite for RuntimeManager."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent."""
        return MockAgent()

    @pytest.fixture
    def manager(self, mock_agent):
        """Create a RuntimeManager instance."""
        return RuntimeManager(mock_agent)

    @pytest.mark.asyncio
    async def test_start_stop(self, manager):
        """Test start and stop lifecycle."""
        await manager.start()
        await manager.stop()

    @pytest.mark.asyncio
    async def test_is_streaming_initially_false(self, manager):
        """Test that is_streaming returns False initially."""
        assert manager.is_streaming("session-1") is False

    @pytest.mark.asyncio
    async def test_get_cancellation_event_none(self, manager):
        """Test that get_cancellation_event returns None for unknown session."""
        assert manager.get_cancellation_event("session-1") is None

    @pytest.mark.asyncio
    async def test_get_stream_owner_none(self, manager):
        """Test that get_stream_owner returns None for unknown session."""
        assert manager.get_stream_owner("session-1") is None

    @pytest.mark.asyncio
    async def test_cancel_stream_not_found(self, manager):
        """Test cancel_stream returns False for unknown session."""
        result = await manager.cancel_stream("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_stream_for_client_not_found(self, manager):
        """Test cancel_stream_for_client returns False for unknown session."""
        mock_client = MagicMock()
        result = await manager.cancel_stream_for_client("nonexistent", mock_client)
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_all_streams_empty(self, manager):
        """Test cancel_all_streams with no streams."""
        await manager.cancel_all_streams()

    @pytest.mark.asyncio
    async def test_execute_creates_stream(self, manager):
        """Test that execute creates a stream."""
        mock_client = MagicMock()
        events = []

        async def send_event(event):
            events.append(event)

        await manager.execute("session-1", "test", send_event, mock_client)
        assert manager.is_streaming("session-1") is True

        await manager.cancel_all_streams()

    @pytest.mark.asyncio
    async def test_execute_completes(self, manager):
        """Test that execute completes a stream."""
        mock_client = MagicMock()
        events = []

        async def send_event(event):
            events.append(event)

        await manager.execute("session-1", "Hi", send_event, mock_client)
        assert manager.is_streaming("session-1") is True

        await asyncio.sleep(0.5)

        assert manager.is_streaming("session-1") is False

        token_events = [e for e in events if e.get("type") == "token"]
        assert len(token_events) == 2

    @pytest.mark.asyncio
    async def test_cancel_stream(self, manager):
        """Test that cancel_stream cancels the stream."""
        mock_client = MagicMock()
        events = []

        async def send_event(event):
            events.append(event)

        await manager.execute("session-1", "Hello", send_event, mock_client)
        assert manager.is_streaming("session-1") is True

        result = await manager.cancel_stream("session-1")
        assert result is True
        assert manager.is_streaming("session-1") is False

    @pytest.mark.asyncio
    async def test_cancel_stream_for_client_wrong_owner(self, manager):
        """Test cancel_stream_for_client returns False for wrong owner."""
        mock_client1 = MagicMock()
        mock_client2 = MagicMock()

        async def send_event(event):
            pass

        await manager.execute("session-1", "test", send_event, mock_client1)

        result = await manager.cancel_stream_for_client("session-1", mock_client2)
        assert result is False

        await manager.cancel_all_streams()

    @pytest.mark.asyncio
    async def test_cancel_stream_for_client_correct_owner(self, manager):
        """Test cancel_stream_for_client with correct owner."""
        mock_client = MagicMock()

        async def send_event(event):
            pass

        await manager.execute("session-1", "Hello", send_event, mock_client)
        assert manager.is_streaming("session-1") is True

        result = await manager.cancel_stream_for_client("session-1", mock_client)
        assert result is True
        assert manager.is_streaming("session-1") is False


class TestStreamInfo:
    """Test suite for StreamInfo."""

    def test_stream_info_creation(self):
        """Test StreamInfo creation."""
        task = MagicMock(spec=asyncio.Task)
        event = asyncio.Event()
        client = MagicMock()

        stream_info = StreamInfo(task, event, client)

        assert stream_info.task is task
        assert stream_info.cancellation_event is event
        assert stream_info.owner_client is client
