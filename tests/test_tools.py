"""
Unit Tests for AI_support Tools Module
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from src.tools.schema import (
    Tool,
    ToolParameter,
    ToolResult,
    ToolPermission,
    ToolCategory,
    ParameterType,
    ToolExecutionRequest,
    tool,
)
from src.tools.registry import ToolRegistry, get_tool_registry
from src.tools.executor import (
    ToolExecutor,
    ToolNotFoundError,
    ToolValidationError,
)
from src.tools.context import (
    ToolContext,
    ToolExecutionMode,
    create_sandbox_context,
    create_dry_run_context,
)
from src.tools.cache import ToolResultCache


# ============ Schema Tests ============

class TestToolParameter:
    def test_parameter_validation_string(self):
        """Test string parameter validation."""
        param = ToolParameter(
            name="path",
            type=ParameterType.STRING,
            required=True,
        )

        valid, error = param.validate("test")
        assert valid is True
        assert error is None

        valid, error = param.validate(None)
        assert valid is False

    def test_parameter_validation_integer(self):
        """Test integer parameter validation."""
        param = ToolParameter(
            name="count",
            type=ParameterType.INTEGER,
            min_value=0,
            max_value=100,
        )

        valid, _ = param.validate(50)
        assert valid is True

        valid, _ = param.validate(-1)
        assert valid is False

        valid, _ = param.validate(101)
        assert valid is False


class TestTool:
    def test_tool_creation(self):
        """Test tool creation."""
        tool_def = Tool(
            name="test_tool",
            description="A test tool",
            category=ToolCategory.CUSTOM,
        )

        assert tool_def.name == "test_tool"
        assert tool_def.category == ToolCategory.CUSTOM

    def test_tool_validate_params(self):
        """Test parameter validation."""
        tool_def = Tool(
            name="test_tool",
            description="A test tool",
            parameters=[
                ToolParameter(name="path", type=ParameterType.STRING),
                ToolParameter(name="count", type=ParameterType.INTEGER, required=False),
            ],
        )

        valid, error = tool_def.validate_params({"path": "test", "count": 5})
        assert valid is True

        valid, error = tool_def.validate_params({"path": "test"})
        assert valid is True  # count is optional


class TestToolResult:
    def test_result_creation(self):
        """Test result creation."""
        result = ToolResult(
            tool_name="test_tool",
            success=True,
            output="result data",
        )

        assert result.success is True
        assert result.output == "result data"
        assert result.cached is False

    def test_result_to_dict(self):
        """Test result serialization."""
        result = ToolResult(
            tool_name="test_tool",
            success=True,
            output="data",
        )

        data = result.to_dict()
        assert data["tool_name"] == "test_tool"
        assert data["success"] is True


# ============ Registry Tests ============

class TestToolRegistry:
    def test_registry_register(self):
        """Test tool registration."""
        registry = ToolRegistry()

        tool_def = Tool(
            name="my_tool",
            description="My tool",
        )

        registry.register(tool_def)
        assert registry.has_tool("my_tool")
        assert registry.count() == 1

    def test_registry_unregister(self):
        """Test tool unregistration."""
        registry = ToolRegistry()

        tool_def = Tool(name="my_tool", description="My tool")
        registry.register(tool_def)
        registry.unregister("my_tool")

        assert not registry.has_tool("my_tool")

    def test_registry_get(self):
        """Test tool retrieval."""
        registry = ToolRegistry()

        tool_def = Tool(name="my_tool", description="My tool")
        registry.register(tool_def)

        retrieved = registry.get("my_tool")
        assert retrieved is not None
        assert retrieved.name == "my_tool"

    def test_registry_search(self):
        """Test tool search."""
        registry = ToolRegistry()

        registry.register(Tool(
            name="file_read",
            description="Read a file",
            category=ToolCategory.FILE,
            tags=["file"],
        ))
        registry.register(Tool(
            name="file_write",
            description="Write a file",
            category=ToolCategory.FILE,
            tags=["file"],
        ))
        registry.register(Tool(
            name="git_status",
            description="Git status",
            category=ToolCategory.GIT,
        ))

        file_tools = registry.search(category=ToolCategory.FILE)
        assert len(file_tools) == 2

        tagged_tools = registry.search(tags=["file"])
        assert len(tagged_tools) == 2

    def test_registry_by_category(self):
        """Test get by category."""
        registry = ToolRegistry()

        registry.register(Tool(
            name="file_read",
            description="Read",
            category=ToolCategory.FILE,
        ))
        registry.register(Tool(
            name="git_status",
            description="Git",
            category=ToolCategory.GIT,
        ))

        file_tools = registry.get_by_category(ToolCategory.FILE)
        assert len(file_tools) == 1


# ============ Executor Tests ============

class TestToolExecutor:
    def test_executor_register_and_execute(self):
        """Test tool execution."""
        registry = ToolRegistry()
        executor = ToolExecutor(registry)

        def my_handler(params, context):
            return f"Hello, {params['name']}!"

        tool_def = Tool(
            name="greet",
            description="Greet someone",
            handler=my_handler,
            parameters=[
                ToolParameter(name="name", type=ParameterType.STRING),
            ],
        )
        registry.register(tool_def)

        result = asyncio.run(executor.execute("greet", {"name": "World"}))
        assert result.success is True
        assert result.output == "Hello, World!"

    def test_executor_tool_not_found(self):
        """Test tool not found error."""
        registry = ToolRegistry()
        executor = ToolExecutor(registry)

        with pytest.raises(ToolNotFoundError):
            asyncio.run(executor.execute("nonexistent", {}))

    def test_executor_validation_error(self):
        """Test validation error."""
        registry = ToolRegistry()
        executor = ToolExecutor(registry)

        registry.register(Tool(
            name="test_tool",
            description="Test",
            parameters=[
                ToolParameter(name="required_param", type=ParameterType.STRING, required=True),
            ],
            handler=lambda p, c: p,
        ))

        result = asyncio.run(executor.execute("test_tool", {}))
        assert result.success is False
        assert "required_param" in result.error


# ============ Context Tests ============

class TestToolContext:
    def test_context_path_allowed(self):
        """Test path permission checking."""
        context = create_sandbox_context(
            workspace_root=Path("/workspace"),
            allowed_paths=[Path("/workspace/src")],
            denied_paths=[Path("/workspace/secret")],
        )

        assert context.is_path_allowed(Path("/workspace/src/main.c")) is True
        assert context.is_path_allowed(Path("/workspace/secret.txt")) is False

    def test_context_variables(self):
        """Test context variables."""
        context = ToolContext()
        context.set_variable("key", "value")

        assert context.get_variable("key") == "value"
        assert context.get_variable("missing", "default") == "default"


# ============ Cache Tests ============

class TestToolResultCache:
    def test_cache_set_get(self):
        """Test cache set and get."""
        cache = ToolResultCache(max_size=10, ttl_seconds=3600)

        result = ToolResult(
            tool_name="test",
            success=True,
            output="data",
        )

        cache.set("key1", result)
        cached = cache.get("key1")

        assert cached is not None
        assert cached.output == "data"

    def test_cache_miss(self):
        """Test cache miss."""
        cache = ToolResultCache()

        cached = cache.get("nonexistent")
        assert cached is None

    def test_cache_lru_eviction(self):
        """Test LRU eviction."""
        cache = ToolResultCache(max_size=2)

        for i in range(3):
            result = ToolResult(tool_name="test", success=True, output=f"data{i}")
            cache.set(f"key{i}", result)

        # First key should be evicted
        assert cache.get("key0") is None
        assert cache.get("key1") is not None

    def test_cache_stats(self):
        """Test cache statistics."""
        cache = ToolResultCache(collect_stats=True)

        cache.set("key1", ToolResult(tool_name="test", success=True, output="data"))
        cache.get("key1")  # Hit
        cache.get("key2")  # Miss

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_cache_invalidate(self):
        """Test cache invalidation."""
        cache = ToolResultCache()

        cache.set("key1", ToolResult(tool_name="test", success=True, output="data"))
        cache.invalidate("key1")

        assert cache.get("key1") is None


# ============ Integration Tests ============

class TestToolsIntegration:
    def test_full_tool_lifecycle(self):
        """Test complete tool lifecycle."""
        # Create registry
        registry = ToolRegistry()

        # Define and register tool
        def my_tool(params, context):
            return params["value"] * 2

        tool_def = Tool(
            name="double",
            description="Double a value",
            handler=my_tool,
            parameters=[
                ToolParameter(name="value", type=ParameterType.INTEGER),
            ],
            cacheable=True,
        )
        registry.register(tool_def)

        # Create executor with cache
        cache = ToolResultCache()
        executor = ToolExecutor(registry, cache=cache)

        # Execute
        result = asyncio.run(executor.execute("double", {"value": 21}))
        assert result.success is True
        assert result.output == 42

    def test_global_registry(self):
        """Test global registry."""
        registry = get_tool_registry()
        assert registry is not None

        # Same instance should be returned
        registry2 = get_tool_registry()
        assert registry is registry2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
