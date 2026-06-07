"""Data models for the Universal Repo Handler.

Shared dataclasses used across detection, analysis, build, fix, and streaming
phases of the universal repository processing pipeline.

Requirements: 1.2, 2.1, 5.6, 6.4
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


# ─── Named Constants ─────────────────────────────────────────────────────────

# Confidence thresholds
MIN_CONFIDENCE = 0.0
MAX_CONFIDENCE = 1.0
NO_CONFIDENT_FIX_THRESHOLD = 0.3
AUTO_APPLY_FIX_THRESHOLD = 0.7

# Build defaults
DEFAULT_BUILD_TIMEOUT_SECONDS = 180

# Iterative cycle limits
MAX_FIX_ITERATIONS = 3

# Detection limits
MAX_SCAN_FILES = 50_000


# ─── Language Models ─────────────────────────────────────────────────────────


@dataclass
class LanguageStats:
    """Statistics for a single detected language."""

    file_count: int
    lines_of_code: int
    percentage_files: float
    percentage_loc: float


@dataclass
class LanguageDistribution:
    """Language breakdown of a repository."""

    primary_language: str
    languages: dict[str, LanguageStats]


# ─── Detection Models ────────────────────────────────────────────────────────


@dataclass
class Framework:
    """Detected framework within a repository."""

    name: str
    version: str | None
    language: str
    detected_from: str  # Config/import pattern that triggered detection


@dataclass
class BuildToolInfo:
    """Detected build tool with its configuration."""

    name: str  # "npm", "cargo", "cmake", "make", etc.
    config_file: Path
    build_commands: list[str]
    relevance_score: float  # Ranking by proximity and dependency position


@dataclass
class ProjectProfile:
    """Complete detection result for a repository.

    Contains language distribution, frameworks, build tools, entry points,
    dependency manifests, and a confidence score for the overall detection.
    """

    repo_path: Path
    languages: LanguageDistribution
    frameworks: list[Framework]
    build_tools: list[BuildToolInfo]
    entry_points: list[Path]
    dependency_manifests: list[Path]
    confidence: float  # MIN_CONFIDENCE to MAX_CONFIDENCE
    detected_at: datetime
    file_tree_hash: str


# ─── Build Models ────────────────────────────────────────────────────────────


@dataclass
class BuildCommand:
    """A discovered or configured build command."""

    command: list[str]
    working_directory: Path
    environment: dict[str, str]
    timeout_seconds: int = DEFAULT_BUILD_TIMEOUT_SECONDS


@dataclass
class CompilerError:
    """Structured representation of a single compiler error.

    Normalized from multiple compiler output formats (gcc, tsc, rustc, go, javac)
    into a common schema for downstream processing.
    """

    file_path: str
    line: int
    column: int
    severity: str  # "error", "warning", "note"
    error_code: str  # e.g., "TS2304", "E0308", "C2065"
    message: str
    compiler: str  # "gcc", "tsc", "rustc", "go", "javac"
    raw_output: str = ""
    suggestions: list[str] = field(default_factory=list)


# ─── Fix Models ──────────────────────────────────────────────────────────────


@dataclass
class FixPatch:
    """A code repair suggestion for a detected error.

    Contains the original and replacement code, file location,
    confidence score, and source of the fix (template or LLM).
    """

    file_path: str
    line_start: int
    line_end: int
    old_code: str
    new_code: str
    explanation: str
    confidence: float  # MIN_CONFIDENCE to MAX_CONFIDENCE
    source: str  # "template" or "llm"
    error_ref: CompilerError | None = None


# ─── Result Models ───────────────────────────────────────────────────────────


@dataclass
class BuildResult:
    """Result of a single build execution."""

    success: bool
    errors: list[CompilerError]
    warnings: list[CompilerError]
    output: str
    duration_ms: float
    command: BuildCommand


@dataclass
class IterativeBuildResult:
    """Result of the full iterative build-fix cycle.

    Tracks all iterations, resolved/remaining errors,
    and applied/failed patches across the cycle.
    """

    final_success: bool
    iterations_run: int
    errors_resolved: list[CompilerError]
    errors_remaining: list[CompilerError]
    patches_applied: list[FixPatch]
    patches_failed: list[FixPatch]
    build_results: list[BuildResult]


@dataclass
class DependencyResult:
    """Result of dependency installation (pre-build step)."""

    success: bool
    installed_packages: list[str]
    failed_packages: list[str]
    error_message: str = ""


# ─── Streaming Models ────────────────────────────────────────────────────────


@dataclass
class PipelineProgressEvent:
    """Progress event for WebSocket streaming during pipeline execution.

    Emitted by each pipeline phase (detection, analysis, build, fix, complete)
    to provide real-time feedback to the user interface.
    """

    phase: str  # "detection", "analysis", "build", "fix", "complete"
    progress_percent: float
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
