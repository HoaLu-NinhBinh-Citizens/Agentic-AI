"""Unit tests for LSP client."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.lsp.lsp_client import (
    LSPConnection,
    LSPServer,
    LSPLanguageServerManager,
    LSPError,
    TextDocument,
)


class TestLSPConnection:
    """Tests for LSPConnection."""

    def test_create_connection(self):
        """Test creating connection."""
        conn = LSPConnection(
            server_command=["pyright-langserver", "--stdio"],
            workspace_root=Path.cwd(),
        )
        
        assert conn.server_command == ["pyright-langserver", "--stdio"]
        assert conn.workspace_root == Path.cwd()

    @pytest.mark.asyncio
    async def test_send_notification(self):
        """Test sending notification."""
        conn = LSPConnection(
            server_command=["echo"],
            workspace_root=Path.cwd(),
        )
        
        # Mock process
        conn._process = MagicMock()
        conn._process.stdin = AsyncMock()
        
        # Should not raise
        await conn.send_notification("initialized", {})


class TestLSPServer:
    """Tests for LSPServer."""

    def test_get_language(self):
        """Test language detection from extension."""
        conn = LSPConnection(
            server_command=["echo"],
            workspace_root=Path.cwd(),
        )
        server = LSPServer(conn)
        
        assert server._get_language(Path("test.py")) == "python"
        assert server._get_language(Path("test.ts")) == "typescript"
        assert server._get_language(Path("test.rs")) == "rust"
        assert server._get_language(Path("test.go")) == "go"

    def test_get_language_unknown(self):
        """Test unknown extension."""
        conn = LSPConnection(
            server_command=["echo"],
            workspace_root=Path.cwd(),
        )
        server = LSPServer(conn)
        
        assert server._get_language(Path("test.xyz")) == "plaintext"


class TestLSPLanguageServerManager:
    """Tests for LSPLanguageServerManager."""

    def test_create_manager(self):
        """Test creating manager."""
        manager = LSPLanguageServerManager(Path.cwd())
        
        assert manager.workspace_root == Path.cwd()
        assert len(manager._servers) == 0

    def test_get_language(self):
        """Test language detection."""
        manager = LSPLanguageServerManager(Path.cwd())
        
        assert manager._get_language(Path("test.py")) == "python"
        assert manager._get_language(Path("test.js")) == "javascript"
