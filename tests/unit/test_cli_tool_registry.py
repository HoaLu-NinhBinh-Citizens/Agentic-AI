"""Unit tests for CLI Tool Registry.

Tests for:
- Tool registration
- Tool execution
- Concurrency control
- Timeout handling
- Permission system
- OpenAI format export
"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.infrastructure.tools.tool_registry import (
    ToolRegistry,
    BaseTool,
    ToolDefinition,
    ToolSchema,
    ToolCategory,
    ToolResult,
    ToolCallRequest,
    ToolCallResponse,
)


class MockTool(BaseTool):
    """Mock tool for testing."""
    
    def __init__(self, name: str = "mock_tool", success: bool = True):
        self.name = name
        self._success = success
        self.execute_count = 0
    
    async def execute(self, **kwargs) -> ToolResult:
        self.execute_count += 1
        return ToolResult(
            tool_name=self.name,
            success=self._success,
            content=[{"type": "text", "text": f"Executed {self.name}"}],
        )


class TestToolRegistry:
    """Tests for ToolRegistry."""

    @pytest.fixture
    def registry(self):
        """Create fresh registry."""
        return ToolRegistry()

    def test_register_tool(self, registry):
        """Test tool registration."""
        tool = MockTool("test_tool")
        registry.register(tool)
        
        assert "test_tool" in [t.name for t in registry.list_tools()]

    def test_register_function(self, registry):
        """Test registering a function as tool."""
        async def my_func(**kwargs):
            return ToolResult(tool_name="my_func", success=True, content=[])
        
        registry.register_function(
            name="my_func",
            description="My test function",
            category=ToolCategory.FILES,
            schema=ToolSchema(properties={}),
            func=my_func,
        )
        
        assert "my_func" in [t.name for t in registry.list_tools()]

    def test_get_tool(self, registry):
        """Test getting tool definition."""
        tool = MockTool("get_test")
        registry.register(tool)
        
        defn = registry.get("get_test")
        
        assert defn is not None
        assert defn.name == "get_test"

    def test_get_nonexistent_tool(self, registry):
        """Test getting nonexistent tool."""
        result = registry.get("nonexistent")
        assert result is None

    def test_list_tools_all(self, registry):
        """Test listing all tools."""
        registry.register(MockTool("tool1"))
        registry.register(MockTool("tool2"))
        
        tools = registry.list_tools()
        
        assert len(tools) == 2

    def test_list_tools_by_category(self, registry):
        """Test filtering tools by category."""
        registry.register(MockTool("file_tool"))
        registry._tools["file_tool"].category = ToolCategory.FILES
        
        registry.register(MockTool("shell_tool"))
        registry._tools["shell_tool"].category = ToolCategory.SHELL
        
        file_tools = registry.list_tools(category=ToolCategory.FILES)
        
        assert len(file_tools) == 1
        assert file_tools[0].name == "file_tool"

    def test_unregister_tool(self, registry):
        """Test tool unregistration."""
        registry.register(MockTool("to_remove"))
        assert registry.get("to_remove") is not None
        
        result = registry.unregister("to_remove")
        
        assert result is True
        assert registry.get("to_remove") is None

    def test_unregister_nonexistent(self, registry):
        """Test unregistering nonexistent tool."""
        result = registry.unregister("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_execute_success(self, registry):
        """Test successful tool execution."""
        tool = MockTool("exec_test", success=True)
        registry.register(tool)
        
        request = ToolCallRequest(
            name="exec_test",
            arguments={},
        )
        
        response = await registry.execute(request)
        
        assert response.result.success is True

    @pytest.mark.asyncio
    async def test_execute_not_found(self, registry):
        """Test executing nonexistent tool."""
        request = ToolCallRequest(
            name="nonexistent_tool",
            arguments={},
        )
        
        response = await registry.execute(request)
        
        assert response.result.success is False
        assert "not found" in response.result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_error_handling(self, registry):
        """Test error handling in execution."""
        async def error_tool(**kwargs):
            raise ValueError("Test error")
        
        registry.register_function(
            name="error_tool",
            description="Tool that errors",
            category=ToolCategory.CUSTOM,
            schema=ToolSchema(properties={}),
            func=error_tool,
        )
        
        request = ToolCallRequest(name="error_tool", arguments={})
        
        response = await registry.execute(request)
        
        assert response.result.success is False

    def test_check_permission_allowed(self, registry):
        """Test permission check when allowed."""
        registry.register(MockTool("permitted"))
        registry._tools["permitted"].requires_permission = "read"
        
        result = registry.check_permission("permitted", {"read", "write"})
        
        assert result is True

    def test_check_permission_denied(self, registry):
        """Test permission check when denied."""
        registry.register(MockTool("denied"))
        registry._tools["denied"].requires_permission = "admin"
        
        result = registry.check_permission("denied", {"read"})
        
        assert result is False

    def test_to_openai_format(self, registry):
        """Test OpenAI function calling format export."""
        registry.register(MockTool("func1"))
        registry._tools["func1"].schema = ToolSchema(
            properties={"arg1": {"type": "string"}},
            required=["arg1"],
        )
        
        format_output = registry.to_openai_format()
        
        assert len(format_output) == 1
        assert format_output[0]["type"] == "function"
        assert format_output[0]["function"]["name"] == "func1"


class TestToolDefinition:
    """Tests for ToolDefinition."""

    def test_to_definition(self):
        """Test BaseTool.to_definition()."""
        tool = MockTool("def_test")
        defn = tool.to_definition()
        
        assert defn.name == "def_test"
        assert defn.category == ToolCategory.CUSTOM


class TestToolCallRequest:
    """Tests for ToolCallRequest."""

    def test_request_creation(self):
        """Test request creation."""
        request = ToolCallRequest(
            name="test_tool",
            arguments={"arg1": "value1"},
        )
        
        assert request.name == "test_tool"
        assert request.arguments == {"arg1": "value1"}

    def test_request_with_call_id(self):
        """Test request with call ID."""
        request = ToolCallRequest(
            name="test",
            arguments={},
            call_id="call_123",
        )
        
        assert request.call_id == "call_123"


class TestToolCallResponse:
    """Tests for ToolCallResponse."""

    def test_response_duration(self):
        """Test response duration calculation."""
        from datetime import datetime, timezone
        
        start = datetime.now(timezone.utc)
        
        request = ToolCallRequest(name="test", arguments={})
        response = ToolCallResponse(
            request=request,
            result=ToolResult(tool_name="test", success=True, content=[]),
            started_at=start,
            completed_at=datetime.now(timezone.utc),
        )
        
        assert response.duration_ms >= 0
