"""Refactoring support for AI_SUPPORT.

Interactive refactoring engine with support for:
- Extract function: Convert code blocks to reusable functions
- Inline function: Replace function calls with function body
- Rename symbol: Rename variables, functions, classes across scope
- Move code: Move code to another file or class
- Multi-file undo/redo: Track and revert changes across the project

Usage:
    from src.infrastructure.refactoring import RefactorEngine, UndoManager
    
    engine = RefactorEngine(project_root)
    result = await engine.extract_function(
        file_path, code, start_line, end_line, "my_function"
    )
    
    # Multi-file undo/redo
    manager = UndoManager(project_root)
    manager.checkpoint(changes, "description")
    manager.undo()
    manager.redo()
"""
from __future__ import annotations

from .refactor_engine import (
    RefactorEngine,
    RefactorResult,
    ExtractFunctionResult,
    RenameSymbolResult,
    InlineResult,
    create_refactor_engine,
)
from .undo_manager import (
    UndoManager,
    UndoCheckpoint,
    Change,
)

__all__ = [
    "RefactorEngine",
    "RefactorResult",
    "ExtractFunctionResult",
    "RenameSymbolResult",
    "InlineResult",
    "create_refactor_engine",
    "UndoManager",
    "UndoCheckpoint",
    "Change",
]
