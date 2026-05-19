"""Legacy alias for src.tools.schema module."""

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

__all__ = ["Tool", "ToolParameter", "ToolResult", "ToolPermission", "ToolCategory", "ParameterType", "ToolExecutionRequest", "tool"]
