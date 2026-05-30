"""Suggestion package - Multi-option fix generation with risk assessment.

This package provides the Unified Suggestion Engine for generating
intelligent, context-aware code fixes with multiple options.

Features:
- Multi-option fix generation (up to 3 per finding)
- Risk level assessment (LOW, MEDIUM, HIGH, CRITICAL)
- Confidence scoring
- Before/after code blocks
- LLM integration with fallback
- Batch processing
- Unified diff generation

Usage:
    from src.application.suggestion import UnifiedSuggestionEngine, PatchGenerator

    # Generate suggestions
    engine = UnifiedSuggestionEngine()
    result = await engine.generate(finding, context)

    # Generate patches
    generator = PatchGenerator()
    patch = generator.generate(old_code, new_code, file_path)

Modules:
    suggestion_engine: Main engine for generating fix suggestions
    patch_generator: Unified diff and patch generation
"""

from __future__ import annotations

from src.application.suggestion.suggestion_engine import (
    FixOption,
    FixTemplate,
    LLMProviderInterface,
    RiskLevel,
    SuggestionConfig,
    SuggestionResult,
    UnifiedSuggestionEngine,
    create_engine,
)
from src.application.suggestion.patch_generator import (
    ChangeType,
    DiffFormat,
    Hunk,
    LineChange,
    Patch,
    PatchGenerator,
    PatchOptions,
    create_patch_generator,
    generate_quick_diff,
)

__all__ = [
    # Suggestion Engine
    "UnifiedSuggestionEngine",
    "SuggestionResult",
    "SuggestionConfig",
    "FixOption",
    "FixTemplate",
    "RiskLevel",
    "LLMProviderInterface",
    "create_engine",
    # Patch Generator
    "PatchGenerator",
    "Patch",
    "PatchOptions",
    "Hunk",
    "LineChange",
    "ChangeType",
    "DiffFormat",
    "create_patch_generator",
    "generate_quick_diff",
]
