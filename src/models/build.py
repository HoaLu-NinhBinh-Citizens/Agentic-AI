"""Legacy alias for src.models.build module."""

from src.infrastructure.models.build import BuildError, BuildResult, RuntimeDiagnosis, ToolResult

__all__ = ["BuildError", "BuildResult", "RuntimeDiagnosis", "ToolResult"]
