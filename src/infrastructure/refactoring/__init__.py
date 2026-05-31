"""Refactoring support for AI_SUPPORT.

Interactive refactoring engine with support for:
- Extract function: Convert code blocks to reusable functions
- Inline function: Replace function calls with function body
- Rename symbol: Rename variables, functions, classes across scope
- Move code: Move code to another file or class

Usage:
    from src.infrastructure.refactoring import RefactorEngine
    
    engine = RefactorEngine(project_root)
    result = await engine.extract_function(
        file_path, code, start_line, end_line, "my_function"
    )
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

__all__ = [
    "RefactorEngine",
    "RefactorResult",
    "ExtractFunctionResult",
    "RenameSymbolResult",
    "InlineResult",
    "create_refactor_engine",
]
