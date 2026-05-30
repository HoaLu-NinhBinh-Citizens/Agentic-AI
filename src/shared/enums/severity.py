"""Unified Severity enum for all code review findings.

This module provides a single, consistent severity level system across
all modules in the codebase, replacing legacy severity enums:
- ML detector: MLSeverity (CRITICAL, HIGH, MEDIUM)
- Unified Finding: FindingSeverity (ERROR, WARNING, INFO, HINT)
- Markdown report: local Severity (CRITICAL, HIGH, MEDIUM, LOW, INFO)
- Suggestion risk: RiskLevel (LOW, MEDIUM, HIGH, CRITICAL)

Usage:
    from src.shared.enums.severity import Severity

    # Direct usage
    severity = Severity.CRITICAL
    print(severity.weight)  # 100

    # Comparison
    assert Severity.CRITICAL > Severity.HIGH

    # Parsing from string
    sev = Severity.from_string("high")  # Severity.HIGH

    # Converting from legacy formats
    sev = Severity.from_old_format("ERROR")  # Severity.CRITICAL
    sev = Severity.from_old_format("WARNING")  # Severity.HIGH
    sev = Severity.from_old_format("HINT")  # Severity.INFO
"""

from __future__ import annotations

from enum import Enum


class Severity(Enum):
    """Unified severity levels for all review findings.

    Levels are ordered from most severe to least:
    - CRITICAL (100): Critical issues causing data loss, security vulnerabilities,
                      or system failures
    - HIGH (75): High-priority issues that should be addressed soon,
                 such as memory leaks or performance problems
    - MEDIUM (50): Moderate issues worth addressing, like code maintainability
    - LOW (25): Minor issues or suggestions for improvement
    - INFO (10): Informational messages, hints, and tips

    Each level has:
    - value: lowercase string identifier
    - weight: numeric value for sorting/comparison
    - emoji: visual representation for reports
    """

    CRITICAL = ("critical", 100, "🔴")
    HIGH = ("high", 75, "🟠")
    MEDIUM = ("medium", 50, "🟡")
    LOW = ("low", 25, "🔵")
    INFO = ("info", 10, "⚪")

    # Backward compatibility aliases for legacy code using ERROR/WARNING/HINT
    ERROR = CRITICAL
    WARNING = HIGH
    HINT = INFO

    def __init__(self, value: str, weight: int, emoji: str) -> None:
        self._value = value
        self.weight = weight
        self.emoji = emoji

    @property
    def value(self) -> str:
        """Get the string value of the severity level."""
        return self._value

    def __ge__(self, other: "Severity") -> bool:
        """Check if this severity is greater than or equal to another."""
        return self.weight >= other.weight

    def __gt__(self, other: "Severity") -> bool:
        """Check if this severity is greater than another."""
        return self.weight > other.weight

    def __le__(self, other: "Severity") -> bool:
        """Check if this severity is less than or equal to another."""
        return self.weight <= other.weight

    def __lt__(self, other: "Severity") -> bool:
        """Check if this severity is less than another."""
        return self.weight < other.weight

    @classmethod
    def from_string(cls, s: str) -> "Severity":
        """Parse severity from string (case-insensitive).

        Args:
            s: String to parse (e.g., "critical", "HIGH", "Medium")

        Returns:
            Matching Severity or INFO as default

        Examples:
            >>> Severity.from_string("critical")
            <Severity.CRITICAL: ...>
            >>> Severity.from_string("high")
            <Severity.HIGH: ...>
            >>> Severity.from_string("unknown")
            <Severity.INFO: ...>
        """
        mapping = {v.value: v for v in cls}
        return mapping.get(s.lower(), cls.INFO)

    @classmethod
    def from_old_format(cls, old: str) -> "Severity":
        """Convert from legacy severity formats.

        Handles conversions from:
        - ML detector: CRITICAL, HIGH, MEDIUM
        - FindingSeverity: ERROR, WARNING, INFO, HINT
        - Other legacy formats: FATAL, DEBUG

        Args:
            old: Legacy severity string

        Returns:
            Equivalent Severity level

        Examples:
            >>> Severity.from_old_format("ERROR")
            <Severity.CRITICAL: ...>
            >>> Severity.from_old_format("WARNING")
            <Severity.HIGH: ...>
            >>> Severity.from_old_format("HINT")
            <Severity.INFO: ...>
            >>> Severity.from_old_format("DEBUG")
            <Severity.INFO: ...>
        """
        legacy_mapping: dict[str, "Severity"] = {
            # FindingSeverity legacy format
            "ERROR": cls.CRITICAL,
            "FATAL": cls.CRITICAL,
            "WARNING": cls.HIGH,
            "INFO": cls.INFO,  # INFO maps to INFO
            "HINT": cls.INFO,
            "DEBUG": cls.INFO,
            # MLSeverity legacy format (same values)
            "CRITICAL": cls.CRITICAL,
            "HIGH": cls.HIGH,
            "MEDIUM": cls.MEDIUM,
            "LOW": cls.LOW,
        }
        return legacy_mapping.get(old.upper(), cls.from_string(old))

    @classmethod
    def from_weight(cls, weight: int) -> "Severity":
        """Get severity from numeric weight.

        Args:
            weight: Numeric weight value

        Returns:
            Severity with closest matching weight

        Examples:
            >>> Severity.from_weight(100)
            <Severity.CRITICAL: ...>
            >>> Severity.from_weight(80)
            <Severity.HIGH: ...>
        """
        closest = min(cls, key=lambda s: abs(s.weight - weight))
        return closest

    def to_numeric(self) -> int:
        """Convert to numeric for sorting.

        Returns:
            Weight value (higher = more severe)
        """
        return self.weight

    def to_legacy_ml(self) -> str:
        """Convert to legacy ML detector format.

        Returns:
            String in MLSeverity format (CRITICAL, HIGH, MEDIUM)
        """
        mapping = {
            self.CRITICAL: "CRITICAL",
            self.HIGH: "HIGH",
            self.MEDIUM: "MEDIUM",
        }
        return mapping.get(self, "MEDIUM")

    def to_legacy_finding(self) -> str:
        """Convert to legacy FindingSeverity format.

        Returns:
            String in FindingSeverity format (error, warning, info, hint)
        """
        mapping = {
            self.CRITICAL: "error",
            self.HIGH: "warning",
            self.MEDIUM: "info",
            self.LOW: "hint",
            self.INFO: "info",
        }
        return mapping.get(self, "info")

    def is_critical_or_high(self) -> bool:
        """Check if severity is CRITICAL or HIGH.

        Useful for filtering actionable findings.

        Returns:
            True if severity is critical or high
        """
        return self in (self.CRITICAL, self.HIGH)

    def __str__(self) -> str:
        """String representation (lowercase)."""
        return self.value

    def __repr__(self) -> str:
        """Detailed representation."""
        return f"Severity.{self.name} (weight={self.weight})"


# Backward compatibility aliases - just reference the Severity members directly
# These allow old code to use MLSeverity.CRITICAL, FindingSeverity.ERROR, etc.
# They are identical to Severity members due to Python's enum comparison
MLSeverity = Severity
FindingSeverity = Severity
ReportSeverity = Severity


# Converter functions for backward compatibility
def ml_to_unified(ml_severity: str | Severity) -> Severity:
    """Convert from ML detector severity to unified Severity.

    Args:
        ml_severity: MLSeverity enum or string ("CRITICAL", "HIGH", "MEDIUM")

    Returns:
        Equivalent unified Severity

    Examples:
        >>> ml_to_unified("CRITICAL")
        <Severity.CRITICAL: ...>
        >>> ml_to_unified(MLSeverity.HIGH)
        <Severity.HIGH: ...>
    """
    if isinstance(ml_severity, Severity):
        return ml_severity
    return Severity.from_old_format(ml_severity)


def finding_to_unified(finding_severity: str | Severity) -> Severity:
    """Convert from FindingSeverity to unified Severity.

    Args:
        finding_severity: FindingSeverity enum or string ("error", "warning", etc.)

    Returns:
        Equivalent unified Severity

    Examples:
        >>> finding_to_unified("ERROR")
        <Severity.CRITICAL: ...>
        >>> finding_to_unified(FindingSeverity.WARNING)
        <Severity.HIGH: ...>
    """
    if isinstance(finding_severity, Severity):
        return finding_severity
    return Severity.from_old_format(finding_severity)


def risk_to_unified(risk: str) -> Severity:
    """Convert from risk level string to unified Severity.

    Args:
        risk: Risk level string ("low", "medium", "high", "critical")

    Returns:
        Equivalent unified Severity

    Examples:
        >>> risk_to_unified("low")
        <Severity.LOW: ...>
        >>> risk_to_unified("high")
        <Severity.HIGH: ...>
    """
    mapping: dict[str, Severity] = {
        "low": Severity.LOW,
        "medium": Severity.MEDIUM,
        "high": Severity.HIGH,
        "critical": Severity.CRITICAL,
    }
    return mapping.get(risk.lower(), Severity.MEDIUM)
