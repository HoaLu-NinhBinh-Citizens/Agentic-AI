"""Unit tests for the unified Severity enum.

Tests the unified Severity enum across all code review modules.
"""

from __future__ import annotations

import pytest

from src.shared.enums.severity import (
    Severity,
    MLSeverity,
    FindingSeverity,
    ReportSeverity,
    ml_to_unified,
    finding_to_unified,
    risk_to_unified,
)


class TestSeverityBasics:
    """Basic tests for Severity enum."""

    def test_all_severity_levels_defined(self) -> None:
        """Test all severity levels are defined."""
        assert Severity.CRITICAL.value == "critical"
        assert Severity.HIGH.value == "high"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.LOW.value == "low"
        assert Severity.INFO.value == "info"

    def test_severity_weights(self) -> None:
        """Test severity weights are correct."""
        assert Severity.CRITICAL.weight == 100
        assert Severity.HIGH.weight == 75
        assert Severity.MEDIUM.weight == 50
        assert Severity.LOW.weight == 25
        assert Severity.INFO.weight == 10

    def test_severity_emoji(self) -> None:
        """Test severity emoji values."""
        assert Severity.CRITICAL.emoji == "🔴"
        assert Severity.HIGH.emoji == "🟠"
        assert Severity.MEDIUM.emoji == "🟡"
        assert Severity.LOW.emoji == "🔵"
        assert Severity.INFO.emoji == "⚪"


class TestSeverityComparison:
    """Tests for Severity comparison operators."""

    def test_greater_than(self) -> None:
        """Test > operator."""
        assert Severity.CRITICAL > Severity.HIGH
        assert Severity.HIGH > Severity.MEDIUM
        assert Severity.MEDIUM > Severity.LOW
        assert Severity.LOW > Severity.INFO

    def test_greater_than_or_equal(self) -> None:
        """Test >= operator."""
        assert Severity.CRITICAL >= Severity.HIGH
        assert Severity.CRITICAL >= Severity.CRITICAL
        assert Severity.HIGH >= Severity.MEDIUM
        assert Severity.HIGH >= Severity.HIGH

    def test_less_than(self) -> None:
        """Test < operator."""
        assert Severity.INFO < Severity.LOW
        assert Severity.LOW < Severity.MEDIUM
        assert Severity.MEDIUM < Severity.HIGH
        assert Severity.HIGH < Severity.CRITICAL

    def test_less_than_or_equal(self) -> None:
        """Test <= operator."""
        assert Severity.INFO <= Severity.LOW
        assert Severity.INFO <= Severity.INFO
        assert Severity.LOW <= Severity.MEDIUM
        assert Severity.LOW <= Severity.LOW

    def test_sorting_order(self) -> None:
        """Test that severities sort correctly."""
        severities = [Severity.INFO, Severity.CRITICAL, Severity.LOW, Severity.HIGH, Severity.MEDIUM]
        sorted_severities = sorted(severities)
        expected = [Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
        assert sorted_severities == expected


class TestSeverityFromString:
    """Tests for Severity.from_string() method."""

    def test_case_insensitive_parsing(self) -> None:
        """Test case-insensitive string parsing."""
        assert Severity.from_string("critical") == Severity.CRITICAL
        assert Severity.from_string("CRITICAL") == Severity.CRITICAL
        assert Severity.from_string("Critical") == Severity.CRITICAL
        assert Severity.from_string("high") == Severity.HIGH
        assert Severity.from_string("HIGH") == Severity.HIGH
        assert Severity.from_string("medium") == Severity.MEDIUM
        assert Severity.from_string("low") == Severity.LOW
        assert Severity.from_string("info") == Severity.INFO

    def test_unknown_returns_info(self) -> None:
        """Test that unknown strings return INFO as default."""
        assert Severity.from_string("unknown") == Severity.INFO
        assert Severity.from_string("") == Severity.INFO
        assert Severity.from_string("xyz") == Severity.INFO


class TestSeverityFromOldFormat:
    """Tests for Severity.from_old_format() conversion method."""

    def test_ml_severity_conversion(self) -> None:
        """Test conversion from MLSeverity format."""
        assert Severity.from_old_format("CRITICAL") == Severity.CRITICAL
        assert Severity.from_old_format("HIGH") == Severity.HIGH
        assert Severity.from_old_format("MEDIUM") == Severity.MEDIUM

    def test_finding_severity_conversion(self) -> None:
        """Test conversion from FindingSeverity format."""
        assert Severity.from_old_format("ERROR") == Severity.CRITICAL
        assert Severity.from_old_format("WARNING") == Severity.HIGH
        # INFO in Finding maps to INFO (not MEDIUM)
        assert Severity.from_old_format("INFO") == Severity.INFO
        assert Severity.from_old_format("HINT") == Severity.INFO

    def test_legacy_aliases(self) -> None:
        """Test conversion from legacy formats."""
        assert Severity.from_old_format("FATAL") == Severity.CRITICAL
        assert Severity.from_old_format("DEBUG") == Severity.INFO

    def test_case_insensitive(self) -> None:
        """Test case-insensitive conversion."""
        assert Severity.from_old_format("error") == Severity.CRITICAL
        assert Severity.from_old_format("Error") == Severity.CRITICAL
        assert Severity.from_old_format("warning") == Severity.HIGH


class TestSeverityToNumeric:
    """Tests for Severity.to_numeric() method."""

    def test_to_numeric(self) -> None:
        """Test numeric conversion."""
        assert Severity.CRITICAL.to_numeric() == 100
        assert Severity.HIGH.to_numeric() == 75
        assert Severity.MEDIUM.to_numeric() == 50
        assert Severity.LOW.to_numeric() == 25
        assert Severity.INFO.to_numeric() == 10


class TestSeverityLegacyFormats:
    """Tests for legacy format conversion methods."""

    def test_to_legacy_ml(self) -> None:
        """Test conversion to MLSeverity format."""
        assert Severity.CRITICAL.to_legacy_ml() == "CRITICAL"
        assert Severity.HIGH.to_legacy_ml() == "HIGH"
        assert Severity.MEDIUM.to_legacy_ml() == "MEDIUM"

    def test_to_legacy_finding(self) -> None:
        """Test conversion to FindingSeverity format."""
        assert Severity.CRITICAL.to_legacy_finding() == "error"
        assert Severity.HIGH.to_legacy_finding() == "warning"
        assert Severity.MEDIUM.to_legacy_finding() == "info"
        assert Severity.LOW.to_legacy_finding() == "hint"
        assert Severity.INFO.to_legacy_finding() == "info"


class TestSeverityIsCriticalOrHigh:
    """Tests for Severity.is_critical_or_high() method."""

    def test_is_critical_or_high(self) -> None:
        """Test is_critical_or_high() method."""
        assert Severity.CRITICAL.is_critical_or_high() is True
        assert Severity.HIGH.is_critical_or_high() is True
        assert Severity.MEDIUM.is_critical_or_high() is False
        assert Severity.LOW.is_critical_or_high() is False
        assert Severity.INFO.is_critical_or_high() is False


class TestSeverityStringRepresentation:
    """Tests for Severity string representations."""

    def test_str_representation(self) -> None:
        """Test __str__ method."""
        assert str(Severity.CRITICAL) == "critical"
        assert str(Severity.HIGH) == "high"
        assert str(Severity.MEDIUM) == "medium"
        assert str(Severity.LOW) == "low"
        assert str(Severity.INFO) == "info"

    def test_repr_representation(self) -> None:
        """Test __repr__ method."""
        assert "CRITICAL" in repr(Severity.CRITICAL)
        assert "weight=100" in repr(Severity.CRITICAL)


class TestBackwardCompatibilityAliases:
    """Tests for backward compatibility aliases."""

    def test_ml_severity_alias(self) -> None:
        """Test MLSeverity alias."""
        assert MLSeverity.CRITICAL == Severity.CRITICAL
        assert MLSeverity.HIGH == Severity.HIGH
        assert MLSeverity.MEDIUM == Severity.MEDIUM

    def test_finding_severity_alias(self) -> None:
        """Test FindingSeverity alias."""
        assert FindingSeverity.CRITICAL == Severity.CRITICAL
        assert FindingSeverity.HIGH == Severity.HIGH
        assert FindingSeverity.MEDIUM == Severity.MEDIUM
        assert FindingSeverity.LOW == Severity.LOW
        assert FindingSeverity.INFO == Severity.INFO

    def test_report_severity_alias(self) -> None:
        """Test ReportSeverity alias."""
        assert ReportSeverity.CRITICAL == Severity.CRITICAL
        assert ReportSeverity.HIGH == Severity.HIGH


class TestConverterFunctions:
    """Tests for converter functions."""

    def test_ml_to_unified_from_string(self) -> None:
        """Test ml_to_unified with string input."""
        assert ml_to_unified("CRITICAL") == Severity.CRITICAL
        assert ml_to_unified("HIGH") == Severity.HIGH
        assert ml_to_unified("MEDIUM") == Severity.MEDIUM

    def test_ml_to_unified_from_enum(self) -> None:
        """Test ml_to_unified with MLSeverity input."""
        assert ml_to_unified(MLSeverity.CRITICAL) == Severity.CRITICAL
        assert ml_to_unified(MLSeverity.HIGH) == Severity.HIGH
        assert ml_to_unified(MLSeverity.MEDIUM) == Severity.MEDIUM

    def test_finding_to_unified(self) -> None:
        """Test finding_to_unified function."""
        assert finding_to_unified("ERROR") == Severity.CRITICAL
        assert finding_to_unified("WARNING") == Severity.HIGH
        # INFO in Finding maps to INFO (not MEDIUM)
        assert finding_to_unified("INFO") == Severity.INFO
        assert finding_to_unified("HINT") == Severity.INFO

    def test_risk_to_unified(self) -> None:
        """Test risk_to_unified function."""
        assert risk_to_unified("low") == Severity.LOW
        assert risk_to_unified("medium") == Severity.MEDIUM
        assert risk_to_unified("high") == Severity.HIGH
        assert risk_to_unified("critical") == Severity.CRITICAL

    def test_risk_to_unified_case_insensitive(self) -> None:
        """Test risk_to_unified is case insensitive."""
        assert risk_to_unified("LOW") == Severity.LOW
        assert risk_to_unified("Medium") == Severity.MEDIUM
        assert risk_to_unified("HIGH") == Severity.HIGH

    def test_risk_to_unified_invalid(self) -> None:
        """Test risk_to_unified returns MEDIUM for invalid input."""
        assert risk_to_unified("invalid") == Severity.MEDIUM
        assert risk_to_unified("") == Severity.MEDIUM


class TestSeverityFromWeight:
    """Tests for Severity.from_weight() method."""

    def test_exact_weights(self) -> None:
        """Test from_weight with exact values."""
        assert Severity.from_weight(100) == Severity.CRITICAL
        assert Severity.from_weight(75) == Severity.HIGH
        assert Severity.from_weight(50) == Severity.MEDIUM
        assert Severity.from_weight(25) == Severity.LOW
        assert Severity.from_weight(10) == Severity.INFO

    def test_closest_weight(self) -> None:
        """Test from_weight returns closest match."""
        assert Severity.from_weight(80) == Severity.HIGH  # Closer to 75 than 100
        assert Severity.from_weight(60) == Severity.MEDIUM  # Closer to 50 than 75
        assert Severity.from_weight(0) == Severity.INFO  # Closest to 10
        assert Severity.from_weight(150) == Severity.CRITICAL  # Closest to 100


class TestSeverityIntegration:
    """Integration tests for Severity with other components."""

    def test_severity_in_list(self) -> None:
        """Test Severity works in lists."""
        severities = list(Severity)
        assert len(severities) == 5
        assert Severity.CRITICAL in severities
        assert Severity.INFO in severities

    def test_severity_in_dict(self) -> None:
        """Test Severity works as dict keys."""
        severity_map = {Severity.CRITICAL: "urgent", Severity.INFO: "info"}
        assert severity_map[Severity.CRITICAL] == "urgent"
        assert severity_map[Severity.INFO] == "info"

    def test_severity_in_set(self) -> None:
        """Test Severity works in sets."""
        severity_set = {Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM}
        assert len(severity_set) == 3
        assert Severity.CRITICAL in severity_set

    def test_severity_comparison_chain(self) -> None:
        """Test chained comparisons."""
        s = Severity.HIGH
        assert Severity.INFO < s <= Severity.CRITICAL
