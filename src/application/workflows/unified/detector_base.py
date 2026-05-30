"""Detector base class — abstract interface for all code review detectors.

All detectors inherit from this base class, which provides:
- Standard detect() interface accepting CodeContext
- Batch detection for cross-file analysis
- Statistics tracking
- Configuration management

Supported detector types:
- MlDetector: ML-based pattern detection (ML001-ML007)
- SecurityDetector: Security vulnerability detection
- QualityDetector: Code quality issues
- EmbeddedDetector: Embedded/C firmware issues (CRASH, ASSERT, memory)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.application.workflows.unified.code_context import CodeContext
from src.shared.enums.severity import Severity

logger = logging.getLogger(__name__)


# Backward compatibility alias
FindingSeverity = Severity


# ─── Finding Class ─────────────────────────────────────────────────────────────


@dataclass
class Finding:
    """A code issue found by a detector.

    Attributes:
        rule_id: Unique rule identifier (e.g., "SEC001", "ML001")
        rule_name: Human-readable rule name
        severity: Severity level
        file: File path
        line: Start line number (1-based)
        end_line: End line number
        column: Start column (0-based)
        message: Human-readable description
        fix: Suggested fix text
        confidence: Detection confidence (0.0-1.0)
        context: Surrounding code context
        detector: Name of detector that found this
        metadata: Additional rule-specific metadata
    """
    rule_id: str
    rule_name: str
    severity: FindingSeverity
    file: str
    line: int
    end_line: int
    column: int = 0
    message: str = ""
    fix: str = ""
    confidence: float = 1.0
    context: str = ""
    detector: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "severity": self.severity.value,
            "file": self.file,
            "line": self.line,
            "end_line": self.end_line,
            "column": self.column,
            "message": self.message,
            "fix": self.fix,
            "confidence": self.confidence,
            "context": self.context,
            "detector": self.detector,
            "metadata": self.metadata,
        }

    @property
    def location(self) -> str:
        """Human-readable location string."""
        if self.line == self.end_line:
            return f"{self.file}:{self.line}"
        return f"{self.file}:{self.line}-{self.end_line}"

    def rank_key(self) -> tuple[float, float, int]:
        """Sorting key for prioritizing findings.

        Returns:
            Tuple of (severity_score, confidence, line_number)
        """
        return (
            self.severity.to_numeric(),
            self.confidence,
            -self.line,  # Negative for descending order
        )


# ─── Detector Stats ───────────────────────────────────────────────────────────


@dataclass
class DetectorStats:
    """Statistics for a detector's operation."""
    files_scanned: int = 0
    findings_count: int = 0
    errors_count: int = 0
    execution_time_ms: float = 0.0

    def increment_files(self) -> None:
        """Increment files scanned counter."""
        self.files_scanned += 1

    def add_findings(self, count: int) -> None:
        """Add findings count."""
        self.findings_count += count

    def add_error(self) -> None:
        """Increment error counter."""
        self.errors_count += 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "files_scanned": self.files_scanned,
            "findings_count": self.findings_count,
            "errors_count": self.errors_count,
            "execution_time_ms": self.execution_time_ms,
        }


# ─── Base Detector Class ──────────────────────────────────────────────────────


class Detector(ABC):
    """Abstract base class for all code review detectors.

    All detectors must implement the detect() method which receives a CodeContext
    and returns a list of Finding objects.

    The detect_batch() method provides cross-file analysis capability by default,
    but can be overridden for optimized batch processing.

    Usage:
        class MyDetector(Detector):
            def detect(self, context: CodeContext) -> list[Finding]:
                # Analyze context and return findings
                return findings

        detector = MyDetector(config)
        findings = detector.detect(context)
    """

    def __init__(self, config: "DetectorConfig | None" = None) -> None:
        """Initialize detector.

        Args:
            config: Detector configuration
        """
        self.config = config or DetectorConfig()
        self._stats = DetectorStats()
        self._name = self.__class__.__name__.replace("Detector", "").lower()

    @property
    def name(self) -> str:
        """Detector name (derived from class name)."""
        return self._name

    @property
    def stats(self) -> DetectorStats:
        """Get detector statistics."""
        return self._stats

    @abstractmethod
    def detect(self, context: CodeContext) -> list[Finding]:
        """Detect issues in a single file.

        Args:
            context: Unified code context for the file

        Returns:
            List of findings from this detector
        """
        pass

    def detect_batch(
        self,
        contexts: dict[Path, CodeContext],
    ) -> list[Finding]:
        """Run detector on multiple files with cross-file context.

        Default implementation iterates over files individually.
        Override this for optimized batch processing.

        Args:
            contexts: Dict mapping file paths to their contexts

        Returns:
            Combined list of findings from all files
        """
        findings: list[Finding] = []

        for file_path, ctx in contexts.items():
            try:
                self._stats.increment_files()
                file_findings = self.detect(ctx)
                self._stats.add_findings(len(file_findings))
                findings.extend(file_findings)
            except Exception as e:
                logger.warning(
                    "Detector %s failed on %s: %s",
                    self._name, file_path, e
                )
                self._stats.add_error()

        return findings

    def filter_by_config(self, findings: list[Finding]) -> list[Finding]:
        """Filter findings based on detector configuration.

        Args:
            findings: Raw findings from detect()

        Returns:
            Filtered findings
        """
        if not self.config.focus_areas:
            return findings

        # Filter by focus areas (metadata)
        return [
            f for f in findings
            if not self.config.focus_areas or
            any(area in f.metadata.get("tags", []) for area in self.config.focus_areas)
        ]

    def filter_by_confidence(
        self,
        findings: list[Finding],
        threshold: Optional[float] = None,
    ) -> list[Finding]:
        """Filter findings by confidence threshold.

        Args:
            findings: Findings to filter
            threshold: Minimum confidence (uses config if None)

        Returns:
            Filtered findings
        """
        min_confidence = threshold or self.config.confidence_threshold
        return [f for f in findings if f.confidence >= min_confidence]

    def sort_findings(self, findings: list[Finding]) -> list[Finding]:
        """Sort findings by priority (severity, confidence, line).

        Args:
            findings: Findings to sort

        Returns:
            Sorted findings
        """
        return sorted(findings, key=lambda f: f.rank_key(), reverse=True)


# ─── Detector Config ──────────────────────────────────────────────────────────


@dataclass
class DetectorConfig:
    """Configuration shared by all detectors.

    Attributes:
        enabled: Whether detector is active
        focus_areas: List of areas to focus on (e.g., ["security", "quality"])
        severity_filter: Only return findings of these severities
        confidence_threshold: Minimum confidence to report
        languages: Restrict to specific languages
        max_findings_per_file: Cap findings per file (0 = unlimited)
    """
    enabled: bool = True
    focus_areas: list[str] = field(default_factory=list)
    severity_filter: list[str] = field(default_factory=list)
    confidence_threshold: float = 0.5
    languages: list[str] = field(default_factory=list)
    max_findings_per_file: int = 0

    def should_run(self, language: str) -> bool:
        """Check if detector should run for this language.

        Args:
            language: File language

        Returns:
            True if should run
        """
        if not self.languages:
            return True
        return language in self.languages


# ─── Detector Registry ────────────────────────────────────────────────────────


class DetectorRegistry:
    """Registry for managing available detectors.

    Usage:
        registry = DetectorRegistry()
        registry.register("security", SecurityDetector(config))
        registry.register("quality", QualityDetector(config))

        detectors = registry.get_enabled()
        for detector in detectors:
            findings.extend(detector.detect(context))
    """

    def __init__(self) -> None:
        self._detectors: dict[str, Detector] = {}

    def register(self, name: str, detector: Detector) -> None:
        """Register a detector.

        Args:
            name: Unique detector name
            detector: Detector instance
        """
        self._detectors[name] = detector

    def unregister(self, name: str) -> bool:
        """Unregister a detector.

        Args:
            name: Detector name

        Returns:
            True if removed
        """
        return self._detectors.pop(name, None) is not None

    def get(self, name: str) -> Optional[Detector]:
        """Get a detector by name.

        Args:
            name: Detector name

        Returns:
            Detector or None
        """
        return self._detectors.get(name)

    def get_enabled(self) -> list[Detector]:
        """Get all enabled detectors.

        Returns:
            List of enabled detectors
        """
        return [d for d in self._detectors.values() if d.config.enabled]

    def get_by_category(self, category: str) -> list[Detector]:
        """Get detectors by category.

        Args:
            category: Category name (e.g., "security", "quality")

        Returns:
            Matching detectors
        """
        return [
            d for d in self._detectors.values()
            if category in d.name or category in d.__class__.__name__.lower()
        ]

    def list_all(self) -> list[str]:
        """List all registered detector names.

        Returns:
            List of names
        """
        return list(self._detectors.keys())
