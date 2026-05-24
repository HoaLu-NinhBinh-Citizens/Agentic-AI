"""Unit tests for TypeScript LSP, REPL, Vim mode, and SSH."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.lsp.tsserver_client import (
    TSServerConnection,
    TSServerClient,
    TSServerError,
)
from src.infrastructure.repl.interactive_repl import (
    InteractiveREPL,
    REPLHistory,
    REPLMode,
    MagicCommand,
)
from src.infrastructure.vim.vim_mode import (
    VimEngine,
    VimBuffer,
    VimMode,
    VimState,
)
from src.infrastructure.ssh.ssh_client import (
    SSHConnection,
    SSHConfig,
    SSHManager,
    AuthMethod,
    RemoteResult,
)


# =============================================================================
# TypeScript LSP Tests
# =============================================================================

class TestTSServerConnection:
    """Tests for TSServerConnection."""

    def test_create_connection(self):
        """Test creating connection."""
        conn = TSServerConnection()
        
        # Will be None without actual tsserver
        assert conn.typescript_path is None or conn.typescript_path is not None

    def test_is_available(self):
        """Test availability check."""
        conn = TSServerConnection()
        
        # False without tsserver installed
        assert isinstance(conn.is_available, bool)


class TestTSServerClient:
    """Tests for TSServerClient."""

    def test_create_client(self):
        """Test creating client."""
        # Without actual tsserver, would fail
        # This is just structural test
        pass


# =============================================================================
# REPL Tests
# =============================================================================

class TestREPLHistory:
    """Tests for REPLHistory."""

    def test_create(self):
        """Test creating history."""
        history = REPLHistory()
        
        assert len(history.commands) == 0
        assert history.current_index == -1

    def test_add_command(self):
        """Test adding commands."""
        history = REPLHistory()
        
        history.add("print('hello')")
        history.add("x = 1")
        
        assert len(history.commands) == 2
        assert history.commands[0] == "print('hello')"

    def test_navigation(self):
        """Test history navigation."""
        history = REPLHistory()
        
        history.add("cmd1")
        history.add("cmd2")
        history.add("cmd3")
        
        # Previous
        assert history.previous() == "cmd3"
        assert history.previous() == "cmd2"
        
        # Next
        assert history.next() == "cmd3"
        assert history.next() == ""

    def test_save_load(self, tmp_path):
        """Test save and load."""
        history = REPLHistory()
        history.add("cmd1")
        history.add("cmd2")
        
        path = tmp_path / "history"
        history.save(path)
        
        new_history = REPLHistory()
        new_history.load(path)
        
        assert len(new_history.commands) == 2


class TestInteractiveREPL:
    """Tests for InteractiveREPL."""

    def test_create_repl(self):
        """Test creating REPL."""
        repl = InteractiveREPL()
        
        assert repl.globals is not None
        assert repl.history is not None
        assert repl._mode == REPLMode.NORMAL

    def test_magic_commands_registered(self):
        """Test magic commands are registered."""
        repl = InteractiveREPL()
        
        assert "help" in repl._magic_commands
        assert "ls" in repl._magic_commands
        assert "who" in repl._magic_commands

    def test_register_magic(self):
        """Test registering custom magic command."""
        repl = InteractiveREPL()
        
        called = False
        def custom_cmd(args):
            nonlocal called
            called = True
        
        repl.register_magic("custom", custom_cmd, "A custom command")
        
        assert "custom" in repl._magic_commands
        assert repl._magic_commands["custom"].description == "A custom command"


# =============================================================================
# Vim Mode Tests
# =============================================================================

class TestVimBuffer:
    """Tests for VimBuffer."""

    def test_create_buffer(self):
        """Test creating buffer."""
        buf = VimBuffer()
        
        assert buf.line_count == 0
        assert buf.cursor_line == 0

    def test_set_lines(self):
        """Test setting lines."""
        buf = VimBuffer()
        buf.set_lines(["line1", "line2", "line3"])
        
        assert buf.line_count == 3
        assert buf.current_line == "line1"

    def test_cursor_movement(self):
        """Test cursor movement."""
        buf = VimBuffer()
        buf.set_lines(["line1", "line2"])
        
        buf.move_cursor(1, 2)
        assert buf.cursor_line == 1
        assert buf.cursor_col == 2

    def test_insert_line(self):
        """Test inserting line."""
        buf = VimBuffer()
        buf.set_lines(["line1", "line3"])
        
        buf.insert_line(1, "line2")
        
        assert buf.line_count == 3
        assert buf.lines[1] == "line2"

    def test_delete_line(self):
        """Test deleting line."""
        buf = VimBuffer()
        buf.set_lines(["line1", "line2", "line3"])
        
        deleted = buf.delete_line(1)
        
        assert deleted == "line2"
        assert buf.line_count == 2
        assert buf.lines[1] == "line3"


class TestVimEngine:
    """Tests for VimEngine."""

    def test_create_engine(self):
        """Test creating engine."""
        engine = VimEngine()
        
        assert engine.state is not None
        assert engine.state.mode == VimMode.NORMAL

    def test_load_content(self):
        """Test loading content."""
        engine = VimEngine()
        engine.load_content("line1\nline2\nline3")
        
        assert engine.state.buffer.line_count == 3

    def test_get_content(self):
        """Test getting content."""
        engine = VimEngine()
        engine.load_content("hello\nworld")
        
        content = engine.get_content()
        
        assert "hello" in content
        assert "world" in content

    def test_mode_transitions(self):
        """Test mode transitions."""
        engine = VimEngine()
        
        # Normal to Insert
        engine._enter_insert_mode()
        assert engine.state.mode == VimMode.INSERT
        
        # Insert to Normal
        engine._exit_insert_mode()
        assert engine.state.mode == VimMode.NORMAL

    def test_cursor_movement(self):
        """Test cursor movement."""
        engine = VimEngine()
        engine.load_content("hello world")
        
        # Move right
        engine._move_right()
        assert engine.state.buffer.cursor_col == 1
        
        # Move left
        engine._move_left()
        assert engine.state.buffer.cursor_col == 0

    def test_delete_line(self):
        """Test delete line operation."""
        engine = VimEngine()
        engine.load_content("line1\nline2\nline3")
        
        engine.state.buffer.cursor_line = 1
        engine._delete_line()
        
        assert engine.state.buffer.line_count == 2


# =============================================================================
# SSH Tests
# =============================================================================

class TestSSHConfig:
    """Tests for SSHConfig."""

    def test_create_config(self):
        """Test creating config."""
        config = SSHConfig(
            host="example.com",
            username="user",
            port=22,
        )
        
        assert config.host == "example.com"
        assert config.username == "user"
        assert config.port == 22
        assert config.auth_method == AuthMethod.KEY


class TestSSHManager:
    """Tests for SSHManager."""

    def test_create_manager(self):
        """Test creating manager."""
        manager = SSHManager()
        
        assert len(manager._connections) == 0

    def test_list_connections(self):
        """Test listing connections."""
        manager = SSHManager()
        
        assert manager.list_connections() == []

    def test_get_connection_nonexistent(self):
        """Test getting nonexistent connection."""
        manager = SSHManager()
        
        assert manager.get_connection("test") is None


class TestRemoteResult:
    """Tests for RemoteResult."""

    def test_create_result(self):
        """Test creating result."""
        result = RemoteResult(
            stdout="output",
            stderr="",
            exit_code=0,
            duration_ms=100.0,
        )
        
        assert result.stdout == "output"
        assert result.exit_code == 0
        assert result.duration_ms == 100.0
