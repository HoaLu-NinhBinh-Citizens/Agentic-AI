"""Unit tests for MockAgent."""

from __future__ import annotations

import pytest

from core.agent.mock_agent import MockAgent


class TestMockAgent:
    """Test suite for MockAgent."""

    def setup_method(self):
        """Create a fresh agent for each test."""
        self.agent = MockAgent()
        self.events = []

    async def capture_event(self, event: dict) -> None:
        """Capture events for testing."""
        self.events.append(event)

    @pytest.mark.asyncio
    async def test_stream_response_sends_tokens(self):
        """Test that stream_response sends character tokens."""
        message = "Hi"
        await self.agent.stream_response(message, self.capture_event)

        assert len(self.events) == 3

        assert self.events[0]["type"] == "token"
        assert self.events[0]["data"]["content"] == "H"
        assert self.events[0]["data"]["is_last"] is False

        assert self.events[1]["type"] == "token"
        assert self.events[1]["data"]["content"] == "i"
        assert self.events[1]["data"]["is_last"] is True

        assert self.events[2]["type"] == "done"
        assert self.events[2]["data"]["success"] is True

    @pytest.mark.asyncio
    async def test_stream_response_single_char(self):
        """Test streaming a single character."""
        await self.agent.stream_response("X", self.capture_event)

        assert len(self.events) == 2
        assert self.events[0]["type"] == "token"
        assert self.events[0]["data"]["content"] == "X"
        assert self.events[0]["data"]["is_last"] is True
        assert self.events[1]["type"] == "done"

    @pytest.mark.asyncio
    async def test_stream_response_empty_message(self):
        """Test streaming an empty message."""
        await self.agent.stream_response("", self.capture_event)

        assert len(self.events) == 1
        assert self.events[0]["type"] == "done"
        assert self.events[0]["data"]["success"] is True

    @pytest.mark.asyncio
    async def test_stream_response_deterministic(self):
        """Test that same input produces same output."""
        message = "Hello"

        self.events = []
        await self.agent.stream_response(message, self.capture_event)
        events_copy = self.events.copy()

        self.events = []
        await self.agent.stream_response(message, self.capture_event)

        assert self.events == events_copy

    @pytest.mark.asyncio
    async def test_stream_response_full_message(self):
        """Test streaming a longer message."""
        message = "Hello, World!"
        await self.agent.stream_response(message, self.capture_event)

        token_events = [e for e in self.events if e["type"] == "token"]
        assert len(token_events) == len(message)

        for i, ch in enumerate(message):
            assert token_events[i]["data"]["content"] == ch
            assert token_events[i]["data"]["is_last"] == (i == len(message) - 1)

        done_event = self.events[-1]
        assert done_event["type"] == "done"
        assert done_event["data"]["success"] is True

    @pytest.mark.asyncio
    async def test_is_last_false_for_all_but_last(self):
        """Test that only the last token has is_last=True."""
        message = "ABC"
        await self.agent.stream_response(message, self.capture_event)

        token_events = [e for e in self.events if e["type"] == "token"]
        for i, event in enumerate(token_events[:-1]):
            assert event["data"]["is_last"] is False, f"Token {i} should not be last"

        assert token_events[-1]["data"]["is_last"] is True
