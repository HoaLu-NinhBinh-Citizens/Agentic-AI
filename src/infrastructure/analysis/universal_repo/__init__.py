"""Universal Repo Handler — multi-language repository analysis pipeline.

Public API exports and component interface protocols for the universal
repository processing pipeline (detection, analysis, build, fix, streaming).

Requirements: 5.6, 10.1
"""

from __future__ import annotations

from typing import Protocol

from .models import (
    # Data models
    BuildCommand,
    BuildResult,
    BuildToolInfo,
    CompilerError,
    DependencyResult,
    FixPatch,
    Framework,
    IterativeBuildResult,
    LanguageDistribution,
    LanguageStats,
    PipelineProgressEvent,
    ProjectProfile,
    # Named constants
    AUTO_APPLY_FIX_THRESHOLD,
    DEFAULT_BUILD_TIMEOUT_SECONDS,
    MAX_CONFIDENCE,
    MAX_FIX_ITERATIONS,
    MAX_SCAN_FILES,
    MIN_CONFIDENCE,
    NO_CONFIDENT_FIX_THRESHOLD,
)
from .error_parser import ErrorParser, create_error_parser
from .fix_generator import FixGenerator, FileContext
from .progress_emitter import PipelineProgressEmitter
from .rule_engine import UniversalRuleEngine, UniversalRule
from .pipeline import PipelineResult, run_pipeline


# ─── Component Protocols ─────────────────────────────────────────────────────


class CompilerOutputParser(Protocol):
    """Protocol for language-specific compiler output parsers.

    Each supported compiler (gcc, tsc, rustc, go, javac) implements this
    protocol to parse raw build output into structured CompilerError objects
    and format them back into human-readable strings.

    Requirement: 5.6 — Normalized common schema for compiler errors.
    """

    def parse(self, output: str) -> list[CompilerError]:
        """Parse raw compiler output into structured error objects.

        Args:
            output: Raw text output from a compiler invocation.

        Returns:
            List of structured CompilerError objects extracted from the output.
        """
        ...

    def format(self, error: CompilerError) -> str:
        """Format a CompilerError back into a human-readable string.

        Args:
            error: A structured CompilerError object.

        Returns:
            Human-readable string in the compiler's native output format.
        """
        ...


class StreamSink(Protocol):
    """Protocol for pipeline progress event consumers.

    Components that stream real-time progress updates (detection, analysis,
    build phases) emit events through a StreamSink. Implementations may
    forward events to WebSocket connections, log files, or test collectors.

    Requirement: 10.1 — WebSocket progress streaming for analysis pipeline.
    """

    async def emit(self, event: PipelineProgressEvent) -> None:
        """Emit a pipeline progress event to the consumer.

        Args:
            event: Progress event containing phase, percentage, and message.
        """
        ...


__all__ = [
    # Data models
    "ProjectProfile",
    "LanguageDistribution",
    "LanguageStats",
    "BuildToolInfo",
    "Framework",
    "BuildCommand",
    "CompilerError",
    "FixPatch",
    "BuildResult",
    "IterativeBuildResult",
    "DependencyResult",
    "PipelineProgressEvent",
    # Named constants
    "MIN_CONFIDENCE",
    "MAX_CONFIDENCE",
    "NO_CONFIDENT_FIX_THRESHOLD",
    "AUTO_APPLY_FIX_THRESHOLD",
    "DEFAULT_BUILD_TIMEOUT_SECONDS",
    "MAX_FIX_ITERATIONS",
    "MAX_SCAN_FILES",
    # Protocols
    "CompilerOutputParser",
    "StreamSink",
    # Components
    "ErrorParser",
    "create_error_parser",
    "FixGenerator",
    "FileContext",
    "PipelineProgressEmitter",
    "UniversalRuleEngine",
    "UniversalRule",
    # Pipeline
    "PipelineResult",
    "run_pipeline",
]
