"""Unit tests for Interactive TUI."""

from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.infrastructure.tui.interactive_tui import (
    TUIRenderer,
    StreamingTUIPanel,
    StreamState,
    InputHandler,
)


class TestTUIRenderer:
    """Tests for base TUIRenderer."""

    def test_create_renderer(self):
        """Test creating renderer."""
        renderer = TUIRenderer(width=80)
        
        assert renderer.width == 80

    def test_ansi_colors(self):
        """Test ANSI color codes."""
        renderer = TUIRenderer()
        
        assert "\033[" in renderer.cyan("test")
        assert "\033[" in renderer.green("test")
        assert "\033[" in renderer.red("test")

    def test_render_message(self):
        """Test message rendering."""
        renderer = TUIRenderer()
        
        result = renderer.render_message("user", "Hello")
        
        assert "Hello" in result
        assert "[user]" in result.lower()

    def test_render_tool_card(self):
        """Test tool card rendering."""
        renderer = TUIRenderer()
        
        result = renderer.render_tool_card("read", "success", 100.0)
        
        assert "read" in result.lower()
        assert "success" in result.lower()


class TestStreamState:
    """Tests for StreamState."""

    def test_create_state(self):
        """Test creating stream state."""
        state = StreamState()
        
        assert state.content == ""
        assert state.is_complete is False
        assert len(state.tool_calls) == 0

    def test_state_with_content(self):
        """Test state with content."""
        state = StreamState(content="Hello world")
        
        assert state.content == "Hello world"
        assert state.is_complete is False


class TestStreamingTUIPanel:
    """Tests for StreamingTUIPanel."""

    @pytest.fixture
    def panel(self):
        """Create test panel."""
        return StreamingTUIPanel(use_rich=False)

    def test_add_message(self, panel):
        """Test adding a message."""
        panel.add_message("user", "Hello")
        
        assert len(panel.messages) == 1
        assert panel.messages[0]["role"] == "user"
        assert panel.messages[0]["content"] == "Hello"

    def test_add_tool_call(self, panel):
        """Test adding tool call."""
        panel.add_tool_call("read", {"path": "test.py"})
        
        assert len(panel.tool_calls) == 1
        assert panel.tool_calls[0]["name"] == "read"
        assert panel.tool_calls[0]["status"] == "running"

    def test_complete_tool_call_success(self, panel):
        """Test completing tool call successfully."""
        panel.add_tool_call("read", {})
        panel.complete_tool_call(result="file content")
        
        tool = panel.tool_calls[0]
        assert tool["status"] == "success"
        assert tool["result"] == "file content"

    def test_complete_tool_call_error(self, panel):
        """Test completing tool call with error."""
        panel.add_tool_call("read", {})
        panel.complete_tool_call(error="File not found")
        
        tool = panel.tool_calls[0]
        assert tool["status"] == "error"
        assert tool["error"] == "File not found"

    def test_update_stream(self, panel):
        """Test updating stream content."""
        panel.update_stream("Hello")
        panel.update_stream(" world")
        
        assert panel.state.content == "Hello world"

    def test_complete_stream(self, panel):
        """Test completing stream."""
        panel.update_stream("Done")
        panel.complete_stream()
        
        assert panel.state.is_complete is True

    def test_render_empty(self, panel):
        """Test rendering empty panel."""
        with patch('src.infrastructure.tui.interactive_tui.HAS_RICH', False):
            result = panel.render()
            
            assert isinstance(result, str)
            assert "Agentic-AI" in result


class TestInputHandler:
    """Tests for InputHandler."""

    def test_create_handler(self):
        """Test creating input handler."""
        handler = InputHandler()
        
        assert len(handler.history) == 0
        assert handler.history_index == -1

    def test_add_to_history(self, monkeypatch):
        """Test adding to history."""
        handler = InputHandler()
        
        # Mock input
        def mock_input(prompt):
            return "test input"
        
        monkeypatch.setattr("builtins.input", mock_input)
        
        result = handler.get_input()
        
        assert result == "test input"
