"""Editing infrastructure — atomic file writes, diff generation, and patch application.

Modules:
    diff_engine: Line-level unified diff generation, application, and colored output.

Provides:
- Unified diff generation using difflib
- Colored terminal output
- Multi-file coordinated edits via EditPlan
- Diff application with fuzzy matching
- Structured edit plan dataclasses
"""

from src.infrastructure.editing.diff_engine import (
    Confidence,
    DiffEngine,
    EditPlan,
    HunkInfo,
    LineRange,
    Severity,
)

__all__ = [
    "DiffEngine",
    "EditPlan",
    "HunkInfo",
    "LineRange",
    "Severity",
    "Confidence",
]
