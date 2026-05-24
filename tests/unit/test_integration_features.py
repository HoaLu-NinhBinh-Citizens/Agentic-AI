"""Unit tests for web search, MCP servers, streaming, workspace, and git."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.infrastructure.web.web_search import (
    SearchResult,
    SearchResponse,
    SearchCache,
    DuckDuckGoSearch,
    WebSearchManager,
    SearchProvider,
)
from src.infrastructure.mcp.mcp_servers import (
    FilesystemMCPServer,
    GitMCPServer,
    MemoryMCPServer,
    MCPToolInput,
    MCPToolResult,
)
from src.infrastructure.streaming.time_travel_stream import (
    StreamToken,
    StreamChunk,
    TimeTravelStreamBuffer,
    FlushStrategy,
    StreamingFormatter,
)
from src.infrastructure.workspace.workspace_manager import (
    WorkspaceConfig,
    WorkspaceState,
    WorkspaceManager,
)
from src.infrastructure.git.git_integration import (
    GitRepo,
    GitCommit,
    GitBranch,
    GitError,
)


# =============================================================================
# Web Search Tests
# =============================================================================

class TestSearchResult:
    """Tests for SearchResult."""

    def test_create_result(self):
        """Test creating search result."""
        result = SearchResult(
            title="Test",
            url="https://example.com",
            snippet="Test snippet",
        )
        
        assert result.title == "Test"
        assert result.url == "https://example.com"


class TestSearchCache:
    """Tests for SearchCache."""

    def test_create_cache(self):
        """Test creating cache."""
        cache = SearchCache(max_size=100)
        
        assert cache._max_size == 100

    def test_cache_get_set(self):
        """Test cache operations."""
        cache = SearchCache()
        response = SearchResponse(
            query="test",
            results=[],
            provider="test",
        )
        
        cache.set("test", "duckduckgo", response)
        cached = cache.get("test", "duckduckgo")
        
        assert cached is not None
        assert cached.query == "test"


class TestDuckDuckGoSearch:
    """Tests for DuckDuckGoSearch."""

    def test_create_search(self):
        """Test creating search instance."""
        search = DuckDuckGoSearch()
        
        assert search.base_url == "https://duckduckgo.com/html/"


# =============================================================================
# MCP Server Tests
# =============================================================================

class TestFilesystemMCPServer:
    """Tests for FilesystemMCPServer."""

    def test_create_server(self, tmp_path):
        """Test creating server."""
        server = FilesystemMCPServer(tmp_path)
        
        assert server.root == tmp_path
        assert len(server.tools) > 0

    def test_tools_available(self, tmp_path):
        """Test tools are available."""
        server = FilesystemMCPServer(tmp_path)
        
        tool_names = [t.name for t in server.tools]
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "list_directory" in tool_names


class TestMemoryMCPServer:
    """Tests for MemoryMCPServer."""

    def test_create_server(self):
        """Test creating server."""
        server = MemoryMCPServer()
        
        assert len(server.tools) > 0

    @pytest.mark.asyncio
    async def test_memory_set_get(self):
        """Test memory set and get."""
        server = MemoryMCPServer()
        
        # Set
        result = await server.call_tool(MCPToolInput(
            name="memory_set",
            arguments={"key": "test", "value": "hello"}
        ))
        assert not result.is_error
        
        # Get
        result = await server.call_tool(MCPToolInput(
            name="memory_get",
            arguments={"key": "test"}
        ))
        assert "hello" in result.content[0]["text"]


# =============================================================================
# Streaming Tests
# =============================================================================

class TestStreamToken:
    """Tests for StreamToken."""

    def test_create_token(self):
        """Test creating token."""
        token = StreamToken(
            content="hello",
            index=0,
        )
        
        assert token.content == "hello"
        assert token.index == 0


class TestTimeTravelStreamBuffer:
    """Tests for TimeTravelStreamBuffer."""

    def test_create_buffer(self):
        """Test creating buffer."""
        buffer = TimeTravelStreamBuffer()
        
        assert buffer.content == ""
        assert buffer.is_finalized is False

    @pytest.mark.asyncio
    async def test_add_tokens(self):
        """Test adding tokens."""
        buffer = TimeTravelStreamBuffer(
            flush_strategy=FlushStrategy.ON_WORD
        )
        
        token = StreamToken(content="hello", index=0)
        await buffer.add_token(token)
        
        assert "hello" in buffer.content

    def test_snapshot(self):
        """Test snapshot functionality."""
        buffer = TimeTravelStreamBuffer()
        
        snapshot = buffer.take_snapshot()
        
        assert snapshot.content == ""
        assert snapshot.index == 0


class TestStreamingFormatter:
    """Tests for StreamingFormatter."""

    def test_detect_format(self):
        """Test format detection."""
        formatter = StreamingFormatter()
        
        assert formatter._detect_format('{"key": "value"}') == "json"
        assert formatter._detect_format("# Header") == "markdown"
        assert formatter._detect_format("plain text") == "plain"


# =============================================================================
# Workspace Tests
# =============================================================================

class TestWorkspaceConfig:
    """Tests for WorkspaceConfig."""

    def test_create_config(self, tmp_path):
        """Test creating config."""
        config = WorkspaceConfig(
            name="test",
            root=tmp_path,
        )
        
        assert config.name == "test"
        assert config.root == tmp_path


class TestWorkspaceManager:
    """Tests for WorkspaceManager."""

    def test_create_manager(self, tmp_path):
        """Test creating manager."""
        manager = WorkspaceManager(tmp_path / "workspaces")
        
        assert len(manager.list_workspaces()) == 0

    def test_create_workspace(self, tmp_path):
        """Test creating workspace."""
        manager = WorkspaceManager(tmp_path / "workspaces")
        
        workspace = manager.create_workspace(
            name="test",
            root=tmp_path / "test",
        )
        
        assert workspace.config.name == "test"
        assert workspace.workspace_id is not None

    def test_get_workspace(self, tmp_path):
        """Test getting workspace."""
        manager = WorkspaceManager(tmp_path / "workspaces")
        created = manager.create_workspace(
            name="test",
            root=tmp_path / "test",
        )
        
        retrieved = manager.get_workspace(created.workspace_id)
        
        assert retrieved is not None
        assert retrieved.config.name == "test"


# =============================================================================
# Git Tests
# =============================================================================

class TestGitCommit:
    """Tests for GitCommit."""

    def test_create_commit(self):
        """Test creating commit."""
        commit = GitCommit(
            hash="abc123",
            short_hash="abc",
            message="Test commit",
            author="Test",
            author_email="test@example.com",
            date=datetime.now(),
        )
        
        assert commit.hash == "abc123"
        assert commit.message == "Test commit"


class TestGitBranch:
    """Tests for GitBranch."""

    def test_create_branch(self):
        """Test creating branch."""
        branch = GitBranch(
            name="main",
            is_current=True,
            is_remote=False,
        )
        
        assert branch.name == "main"
        assert branch.is_current is True


class TestGitError:
    """Tests for GitError."""

    def test_raise_error(self):
        """Test raising git error."""
        with pytest.raises(GitError):
            raise GitError("Test error")
