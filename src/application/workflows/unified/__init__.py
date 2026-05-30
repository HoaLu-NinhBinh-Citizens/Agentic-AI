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
    PipelineStats,
)
from src.application.workflows.unified.code_context import (
    CodeContext,
    CodeContextBuilder,
    DefLocation,
    RefLocation,
    CallGraph,
    ImportInfo,
    ExportInfo,
    CodeChunk,
    FileState,
    CallContext,
    SymbolDef,
)
from src.application.workflows.unified.detector_base import (
    Detector,
    DetectorConfig,
    DetectorStats,
    Finding,
    FindingSeverity,
)
from src.application.workflows.unified.result_formatter import (
    ResultFormatter,
    MarkdownFormatter,
    JsonFormatter,
)

__all__ = [
    # Main engine
    "UnifiedReviewEngine",
    "ReviewEngineConfig",
    "ReviewResult",
    "PipelineStats",
    # Context
    "CodeContext",
    "CodeContextBuilder",
    "DefLocation",
    "RefLocation",
    "CallGraph",
    "ImportInfo",
    "ExportInfo",
    "CodeChunk",
    "FileState",
    "CallContext",
    "SymbolDef",
    # Base
    "Detector",
    "DetectorConfig",
    "DetectorStats",
    "Finding",
    "FindingSeverity",
    # Formatters
    "ResultFormatter",
    "MarkdownFormatter",
    "JsonFormatter",
]
