"""Unified ReviewEngine pipeline — single entry point for all code review operations.

Architecture:
    1. CodeContext: Unified context object with all detector-needed information
    2. Detector: Abstract base for all detectors (ML, Security, Quality, Embedded)
    3. UnifiedReviewEngine: Orchestrates context building, detection, and output
    4. ResultFormatter: Output formatting (Markdown, JSON, etc.)
    5. SuggestionEngine: Generate intelligent fix suggestions

Usage:
    engine = UnifiedReviewEngine(config)
    result = await engine.review(paths, focus_areas=["security", "quality"])
    print(result.output)
"""

from src.application.workflows.unified.review_engine import (
    UnifiedReviewEngine,
    ReviewEngineConfig,
    ReviewResult,
)
from src.application.workflows.unified.code_context import (
    CodeContext,
    CodeContextBuilder,
)
from src.application.workflows.unified.detector_base import (
    Detector,
    DetectorConfig,
    Finding,
    DetectorRegistry,
)
from src.application.workflows.unified.result_formatter import (
    ResultFormatter,
    MarkdownFormatter,
    JsonFormatter,
    ConsoleFormatter,
)
from src.application.workflows.unified.suggestion_engine import (
    SuggestionEngine,
    FixOption,
)

__all__ = [
    # Core
    "UnifiedReviewEngine",
    "ReviewEngineConfig",
    "ReviewResult",
    # Context
    "CodeContext",
    "CodeContextBuilder",
    # Detectors
    "Detector",
    "DetectorRegistry",
    "DetectorConfig",
    "Finding",
    # Formatters
    "ResultFormatter",
    "MarkdownFormatter",
    "JsonFormatter",
    "ConsoleFormatter",
    # Suggestions
    "SuggestionEngine",
    "FixOption",
]
