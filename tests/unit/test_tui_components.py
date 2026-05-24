"""Unit tests for TUI Components.

Tests for:
- Color: ANSI color codes
- Theme: Styling themes
- BoxStyle: Box drawing
- ToolCard: Tool result display
- MessageCard: Message display
- ProgressIndicator: Loading indicators
"""

from __future__ import annotations

import pytest
from src.infrastructure.tui.components import (
    Color,
    Theme,
    Style,
    BoxStyle,
    render_box,
    ToolCard,
    MessageCard,
    ProgressIndicator,
    Spinner,
    Table,
    StatusBar,
    get_terminal_width,
    get_terminal_height,
)


class TestColor:
    """Tests for Color ANSI codes."""

    def test_reset_code(self):
        """Test reset color code."""
        assert Color.RESET == "\033[0m"

    def test_color_codes(self):
        """Test foreground color codes."""
        assert Color.RED.startswith("\033[")
        assert Color.GREEN.startswith("\033[")
        assert Color.BLUE.startswith("\033[")
        assert Color.YELLOW.startswith("\033[")
        assert Color.CYAN.startswith("\033[")


class TestTheme:
    """Tests for Theme constants."""

    def test_theme_colors_exist(self):
        """Test theme color constants exist."""
        assert hasattr(Theme, 'PRIMARY')
        assert hasattr(Theme, 'SUCCESS')
        assert hasattr(Theme, 'ERROR')
        assert hasattr(Theme, 'WARNING')


class TestStyle:
    """Tests for Style dataclass."""

    def test_style_defaults(self):
        """Test style with defaults."""
        style = Style()
        assert style.bold is False
        assert style.italic is False

    def test_style_apply(self):
        """Test applying style to text."""
        style = Style(bold=True)
        styled = style.apply("text")
        assert "text" in styled


class TestBoxStyle:
    """Tests for BoxStyle."""

    def test_box_style_defaults(self):
        """Test default box style."""
        style = BoxStyle()
        assert style.top_left == "┌"
        assert style.bottom_right == "┘"

    def test_box_style_rounded(self):
        """Test rounded box style."""
        style = BoxStyle.rounded()
        assert style.top_left == "╭"


class TestRenderBox:
    """Tests for render_box function."""

    def test_render_box_basic(self):
        """Test basic box rendering."""
        result = render_box("Hello")
        assert "Hello" in result
        assert "┌" in result
        assert "┘" in result

    def test_render_box_with_style(self):
        """Test box with custom style."""
        style = BoxStyle(border_color=Color.RED)
        result = render_box("Test", style=style)
        assert "Test" in result


class TestToolCard:
    """Tests for ToolCard."""

    def test_tool_card_creation(self):
        """Test tool card creation."""
        card = ToolCard(name="read", result="content")
        assert card.name == "read"
        assert card.result == "content"

    def test_tool_card_render(self):
        """Test tool card rendering."""
        card = ToolCard(name="bash", success=True)
        result = card.render()
        assert "bash" in result.lower()

    def test_tool_card_with_error(self):
        """Test tool card with error."""
        card = ToolCard(name="test", success=False, error="Failed")
        result = card.render()
        assert "test" in result.lower()


class TestMessageCard:
    """Tests for MessageCard."""

    def test_message_card_creation(self):
        """Test message card creation."""
        card = MessageCard(role="user", content="Hello")
        assert card.role == "user"
        assert card.content == "Hello"

    def test_message_card_render(self):
        """Test message card rendering."""
        card = MessageCard(role="assistant", content="Response")
        result = card.render()
        assert "Response" in result


class TestProgressIndicator:
    """Tests for ProgressIndicator."""

    def test_progress_indicator_creation(self):
        """Test creating progress indicator."""
        progress = ProgressIndicator()
        assert progress is not None

    def test_progress_render(self):
        """Test progress rendering."""
        progress = ProgressIndicator(message="Loading...")
        result = progress.render()
        assert "Loading" in result or len(result) > 0


class TestSpinner:
    """Tests for Spinner."""

    def test_spinner_creation(self):
        """Test creating spinner."""
        spinner = Spinner()
        assert spinner is not None

    def test_spinner_render(self):
        """Test spinner rendering."""
        spinner = Spinner()
        result = spinner.render()
        assert len(result) > 0


class TestTable:
    """Tests for Table."""

    def test_table_creation(self):
        """Test table creation."""
        table = Table(["Col1", "Col2"])
        assert table is not None

    def test_table_add_row(self):
        """Test adding row to table."""
        table = Table(["A", "B"])
        table.add_row(["1", "2"])
        result = table.render()
        assert "A" in result or "1" in result


class TestStatusBar:
    """Tests for StatusBar."""

    def test_status_bar_creation(self):
        """Test creating status bar."""
        bar = StatusBar()
        assert bar is not None

    def test_status_bar_render(self):
        """Test status bar rendering."""
        bar = StatusBar()
        result = bar.render()
        assert len(result) > 0


class TestTerminalHelpers:
    """Tests for terminal helper functions."""

    def test_terminal_width(self):
        """Test getting terminal width."""
        width = get_terminal_width()
        assert width > 0
        assert width <= 1000

    def test_terminal_height(self):
        """Test getting terminal height."""
        height = get_terminal_height()
        assert height > 0
        assert height <= 500


class TestRenderingIntegration:
    """Integration tests for TUI rendering."""

    def test_combined_output(self):
        """Test combining multiple components."""
        card = MessageCard(role="user", content="Test message")
        status = StatusBar()
        
        output = card.render() + "\n" + status.render()
        
        assert "Test" in output
        assert len(output) > 0

    def test_theme_consistency(self):
        """Test using same theme colors."""
        card = MessageCard(role="assistant", content="Test")
        status = StatusBar()
        
        card_output = card.render()
        status_output = status.render()
        
        # Both should use theme colors
        assert len(card_output) > 0
        assert len(status_output) > 0
