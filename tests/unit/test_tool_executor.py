"""Unit tests for ToolExecutor and MCPToolExecutor (Phase 2B)."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from infrastructure.tool_execution.executor import (
    ToolExecutor,
    MCPToolExecutor,
    MockToolExecutor,
)


class TestMockToolExecutor:
    """Test suite for MockToolExecutor."""

    @pytest.fixture
    def executor(self):
        """Create a MockToolExecutor instance."""
        return MockToolExecutor()

    @pytest.mark.asyncio
    async def test_echo_tool(self, executor):
        """Test echo tool returns arguments."""
        result = await executor.execute("echo_test", {"message": "hello"})

        assert "content" in result
        assert len(result["content"]) == 1
        assert "hello" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_default_tool(self, executor):
        """Test default tool returns generic response."""
        result = await executor.execute("some_tool", {"arg": "value"})

        assert "content" in result
        assert len(result["content"]) == 1
        assert "some_tool" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_fail_tool_raises(self, executor):
        """Test fail tool raises exception."""
        with pytest.raises(RuntimeError) as exc_info:
            await executor.execute("fail_test", {})

        assert "fail_test" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_call_count(self, executor):
        """Test call count increments."""
        assert executor.call_count == 0

        await executor.execute("tool1", {})
        assert executor.call_count == 1

        await executor.execute("tool2", {})
        assert executor.call_count == 2


class TestMCPToolExecutor:
    """Test suite for MCPToolExecutor."""

    @pytest.fixture
    def mock_mcp_manager(self):
        """Create a mock MCP manager."""
        manager = MagicMock()
        manager.is_ready = MagicMock(return_value=True)

        mock_result = MagicMock()
        mock_result.model_dump = MagicMock(return_value={
            "content": [{"type": "text", "text": "test result"}]
        })
        manager.call_tool = AsyncMock(return_value=mock_result)

        return manager

    @pytest.fixture
    def executor(self, mock_mcp_manager):
        """Create an MCPToolExecutor instance."""
        return MCPToolExecutor(mock_mcp_manager)

    @pytest.mark.asyncio
    async def test_execute_success(self, executor, mock_mcp_manager):
        """Test successful tool execution."""
        result = await executor.execute("filesystem/read_file", {"path": "/test"})

        mock_mcp_manager.call_tool.assert_called_once_with(
            "filesystem/read_file",
            {"path": "/test"}
        )
        assert "content" in result
        assert result["content"][0]["text"] == "test result"

    @pytest.mark.asyncio
    async def test_execute_mcp_not_ready(self):
        """Test execution fails when MCP not ready."""
        manager = MagicMock()
        manager.is_ready = MagicMock(return_value=False)

        executor = MCPToolExecutor(manager)

        with pytest.raises(RuntimeError) as exc_info:
            await executor.execute("test_tool", {})

        assert "not initialized" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_no_manager(self):
        """Test execution fails when no MCP manager."""
        executor = MCPToolExecutor(None)

        with pytest.raises(RuntimeError) as exc_info:
            await executor.execute("test_tool", {})

        assert "not available" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_returns_dict(self, mock_mcp_manager):
        """Test execution returns dict when model_dump not available."""
        mock_result = {"content": [{"type": "text", "text": "dict result"}]}
        mock_mcp_manager.call_tool = AsyncMock(return_value=mock_result)

        executor = MCPToolExecutor(mock_mcp_manager)
        result = await executor.execute("test_tool", {})

        assert "content" in result
        assert result["content"][0]["text"] == "dict result"
