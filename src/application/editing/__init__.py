"""Edit Transaction System — diff generation, conflict detection, rollback, apply."""

from src.application.editing.edit_session import (
    ConflictDetector,
    ConflictStrategy,
    DiffChunk,
    DiffRenderer,
    EditBlock,
    EditPlanParser,
    EditResult,
    EditSession,
    EditStatus,
    FileSystemAdapter,
    SessionStats,
)

__all__ = [
    "EditSession",
    "EditBlock",
    "EditStatus",
    "EditResult",
    "ConflictDetector",
    "ConflictStrategy",
    "DiffRenderer",
    "DiffChunk",
    "FileSystemAdapter",
    "SessionStats",
    "EditPlanParser",
]
