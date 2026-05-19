"""Legacy alias for src.tools module."""

from src.core.tools.schema import (
    Tool,
    ToolParameter,
    ToolResult,
    ToolPermission,
    ToolCategory,
    ParameterType,
    ToolExecutionRequest,
    tool,
)
from src.core.tools.registry import ToolRegistry, get_tool_registry
from src.core.tools.executor import ToolExecutor, ToolNotFoundError, ToolValidationError
from src.core.tools.context import ToolContext, ToolExecutionMode, create_sandbox_context, create_dry_run_context
from src.core.tools.cache import ToolResultCache

__all__ = [
    "Tool",
    "ToolParameter",
    "ToolResult",
    "ToolPermission",
    "ToolCategory",
    "ParameterType",
    "ToolExecutionRequest",
    "tool",
    "ToolRegistry",
    "get_tool_registry",
    "ToolExecutor",
    "ToolNotFoundError",
    "ToolValidationError",
    "ToolContext",
    "ToolExecutionMode",
    "create_sandbox_context",
    "create_dry_run_context",
    "ToolResultCache",
]
