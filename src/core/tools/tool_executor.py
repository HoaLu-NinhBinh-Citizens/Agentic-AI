"""
Execute tool calls from LLM output and feed results back.

DEPRECATED: This module is deprecated. Use src.core.tools.executor.ToolExecutor instead.

The parsing functionality has been merged into the main ToolExecutor class.
This module will be removed in a future version.
"""

from __future__ import annotations

import warnings

# Emit deprecation warning when module is imported
warnings.warn(
    "src.core.tools.tool_executor is deprecated. "
    "Use src.core.tools.executor.ToolExecutor instead.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export from the new location for backward compatibility
from src.core.tools.executor import ToolExecutor as ToolExecutor

__all__ = ["ToolExecutor"]
