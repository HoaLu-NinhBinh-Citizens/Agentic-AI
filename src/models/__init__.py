"""Legacy alias for backward compatibility with tests.

This module redirects imports from src.models.* to the appropriate modules
to maintain compatibility with test files that use legacy import paths.
"""

# Build-related classes - redirect to infrastructure
from src.infrastructure.models.build import BuildError, BuildResult, RuntimeDiagnosis, ToolResult

# Task-related classes - redirect to infrastructure
from src.infrastructure.models.task import (
    TaskResult,
    AgentState,
    TaskPlan,
    ActionObservation,
    ExperienceEntry,
)

__all__ = [
    # Build
    "BuildError",
    "BuildResult",
    "RuntimeDiagnosis",
    "ToolResult",
    # Task
    "TaskResult",
    "AgentState",
    "TaskPlan",
    "ActionObservation",
    "ExperienceEntry",
]
