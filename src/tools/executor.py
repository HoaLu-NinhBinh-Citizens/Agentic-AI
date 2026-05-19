"""Legacy alias for src.tools.executor module."""

from src.core.tools.executor import ToolExecutor, ToolNotFoundError, ToolValidationError

__all__ = ["ToolExecutor", "ToolNotFoundError", "ToolValidationError"]
