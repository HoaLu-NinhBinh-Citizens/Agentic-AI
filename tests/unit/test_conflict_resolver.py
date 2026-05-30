"""Tests for multi-fix conflict resolution."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.fix_engine.models import Fix, FixSeverity, FixStatus
from src.core.fix_engine.conflict_resolver import (
    ConflictType,
    ResolutionStrategy,
    FixConflict,
    ConflictResolution,
    ConflictReport,
    ConflictResolver,
    apply_with_conflict_resolution,
)


@pytest.fixture
def sample_fixes():
    """Create sample fixes for testing."""
    return [
        Fix(
            id="fix_1",
            file_path="src/test.py",
            line_start=10,
            line_end=10,
            old_text="print('hello')",
            new_text="logger.info('hello')",
            reason="Use logging",
            rule_id="QUAL006",
            severity=FixSeverity.WARNING,
        ),
        Fix(
            id="fix_2",
            file_path="src/test.py",
            line_start=15,
            line_end=15,
            old_text="except:",
            new_text="except Exception:",
            reason="Specific exception",
            rule_id="QUAL003",
            severity=FixSeverity.WARNING,
        ),
        Fix(
            id="fix_3",
            file_path="src/test.py",
            line_start=25,
            line_end=25,
            old_text="value = 100",
            new_text="value = MAX_VALUE",
            reason="Use constant",
            rule_id="QUAL007",
            severity=FixSeverity.INFO,
        ),
    ]


@pytest.fixture
def overlapping_fixes():
    """Create fixes that overlap in lines."""
    return [
        Fix(
            id="fix_a",
            file_path="src/test.py",
            line_start=10,
            line_end=15,
            old_text="# block 1",
            new_text="# new block 1",
            reason="Block fix A",
            rule_id="TEST_A",
            severity=FixSeverity.WARNING,
        ),
        Fix(
            id="fix_b",
            file_path="src/test.py",
            line_start=12,
            line_end=18,
            old_text="# block 2",
            new_text="# new block 2",
            reason="Block fix B",
            rule_id="TEST_B",
            severity=FixSeverity.WARNING,
        ),
    ]


@pytest.fixture
def same_line_fixes():
    """Create fixes targeting the same line."""
    return [
        Fix(
            id="fix_x",
            file_path="src/test.py",
            line_start=10,
            line_end=10,
            old_text="value = 100",
            new_text="value = 200",
            reason="Fix X",
            rule_id="TEST_X",
            severity=FixSeverity.WARNING,
        ),
        Fix(
            id="fix_y",
            file_path="src/test.py",
            line_start=10,
            line_end=10,
            old_text="value = 100",
            new_text="value = 300",
            reason="Fix Y",
            rule_id="TEST_Y",
            severity=FixSeverity.ERROR,
        ),
    ]


@pytest.fixture
def different_file_fixes():
    """Create fixes in different files."""
    return [
        Fix(
            id="fix_p",
            file_path="src/a.py",
            line_start=10,
            line_end=10,
            old_text="import os",
            new_text="import os, sys",
            reason="Add import",
            rule_id="IMP001",
            severity=FixSeverity.INFO,
        ),
        Fix(
            id="fix_q",
            file_path="src/b.py",
            line_start=20,
            line_end=20,
            old_text="import sys",
            new_text="import os, sys",
            reason="Add import",
            rule_id="IMP001",
            severity=FixSeverity.INFO,
        ),
    ]


class TestConflictResolver:
    """Tests for ConflictResolver class."""

    def test_detect_no_conflicts_in_different_files(self, different_file_fixes):
        """Test that fixes in different files don't conflict."""
        resolver = ConflictResolver()
        conflicts = resolver.detect_conflicts(different_file_fixes)

        assert len(conflicts) == 0

    def test_detect_no_conflicts_non_overlapping(self, sample_fixes):
        """Test that non-overlapping fixes don't conflict."""
        resolver = ConflictResolver()
        conflicts = resolver.detect_conflicts(sample_fixes)

        assert len(conflicts) == 0

    def test_detect_overlapping_lines(self, overlapping_fixes):
        """Test detection of overlapping fixes."""
        resolver = ConflictResolver()
        conflicts = resolver.detect_conflicts(overlapping_fixes)

        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == ConflictType.OVERLAPPING_LINES
        assert conflicts[0].severity in ("high", "medium")

    def test_detect_same_line_fixes(self, same_line_fixes):
        """Test detection of fixes on the same line."""
        resolver = ConflictResolver()
        conflicts = resolver.detect_conflicts(same_line_fixes)

        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == ConflictType.OVERLAPPING_LINES
        assert conflicts[0].fix_a.id in ("fix_x", "fix_y")
        assert conflicts[0].fix_b.id in ("fix_x", "fix_y")

    def test_detect_no_conflicts_with_gap(self):
        """Test that fixes with sufficient gap don't conflict."""
        fixes = [
            Fix(
                id="fix_1",
                file_path="src/test.py",
                line_start=10,
                line_end=10,
                old_text="a",
                new_text="b",
                reason="Test",
                rule_id="TEST1",
                severity=FixSeverity.INFO,
            ),
            Fix(
                id="fix_2",
                file_path="src/test.py",
                line_start=20,
                line_end=20,
                old_text="c",
                new_text="d",
                reason="Test",
                rule_id="TEST2",
                severity=FixSeverity.INFO,
            ),
        ]

        resolver = ConflictResolver(overlap_window=3)
        conflicts = resolver.detect_conflicts(fixes)

        assert len(conflicts) == 0


class TestConflictResolution:
    """Tests for conflict resolution strategies."""

    def test_resolve_overlap_by_line_order(self, overlapping_fixes):
        """Test resolution orders by line number."""
        resolver = ConflictResolver()
        conflicts = resolver.detect_conflicts(overlapping_fixes)

        resolutions = resolver.resolve_conflicts(conflicts)

        assert len(resolutions) == 1
        resolution = resolutions[0]

        # Earlier fix should come first
        if overlapping_fixes[0].line_start < overlapping_fixes[1].line_start:
            assert resolution.strategy == ResolutionStrategy.APPLY_A_FIRST
        else:
            assert resolution.strategy == ResolutionStrategy.APPLY_B_FIRST

    def test_resolve_by_severity_error_first(self):
        """Test that error severity is prioritized."""
        fixes = [
            Fix(
                id="fix_error",
                file_path="src/test.py",
                line_start=10,
                line_end=10,
                old_text="a",
                new_text="b",
                reason="Error",
                rule_id="ERR001",
                severity=FixSeverity.ERROR,
            ),
            Fix(
                id="fix_warn",
                file_path="src/test.py",
                line_start=10,
                line_end=10,
                old_text="a",
                new_text="c",
                reason="Warning",
                rule_id="WARN001",
                severity=FixSeverity.WARNING,
            ),
        ]

        resolver = ConflictResolver()
        conflicts = resolver.detect_conflicts(fixes)
        resolutions = resolver.resolve_conflicts(conflicts)

        assert len(resolutions) == 1
        # Error fix should come first
        assert resolutions[0].resolved_fixes[0].id == "fix_error"


class TestGetSafeOrder:
    """Tests for get_safe_order method."""

    def test_preserves_non_conflicting_order(self, sample_fixes):
        """Test that non-conflicting fixes preserve their order."""
        resolver = ConflictResolver()
        safe_order = resolver.get_safe_order(sample_fixes)

        assert len(safe_order) == 3
        ids = [f.id for f in safe_order]
        assert ids == ["fix_1", "fix_2", "fix_3"]

    def test_orders_conflicting_fixes_by_line(self, overlapping_fixes):
        """Test that conflicting fixes are ordered correctly."""
        resolver = ConflictResolver()
        safe_order = resolver.get_safe_order(overlapping_fixes)

        assert len(safe_order) == 2
        # Earlier fix should come first
        assert safe_order[0].line_start <= safe_order[1].line_start

    def test_returns_empty_for_empty_list(self):
        """Test empty input returns empty list."""
        resolver = ConflictResolver()
        safe_order = resolver.get_safe_order([])

        assert safe_order == []


class TestGenerateReport:
    """Tests for generate_report method."""

    def test_report_with_no_conflicts(self, sample_fixes):
        """Test report generation with no conflicts."""
        resolver = ConflictResolver()
        report = resolver.generate_report(sample_fixes)

        assert len(report.conflicts) == 0
        assert len(report.resolutions) == 0
        assert not report.has_unresolved
        assert len(report.safe_order) == 3

    def test_report_with_conflicts(self, overlapping_fixes):
        """Test report generation with conflicts."""
        resolver = ConflictResolver()
        report = resolver.generate_report(overlapping_fixes)

        assert len(report.conflicts) == 1
        assert report.has_unresolved
        assert len(report.resolutions) == 1

    def test_report_severity_counts(self, overlapping_fixes):
        """Test severity count properties."""
        resolver = ConflictResolver()
        report = resolver.generate_report(overlapping_fixes)

        if report.conflicts:
            assert report.high_severity_count + report.medium_severity_count + report.low_severity_count == len(report.conflicts)


class TestApplyWithConflictResolution:
    """Tests for apply_with_conflict_resolution helper."""

    def test_apply_without_conflicts(self, sample_fixes, monkeypatch):
        """Test applying fixes without conflicts."""
        mock_tool = MagicMock()
        mock_batch = MagicMock()
        mock_tool.apply_batch.return_value = mock_batch

        result = apply_with_conflict_resolution(sample_fixes, mock_tool, resolve_conflicts=True)

        assert result == mock_batch
        mock_tool.apply_batch.assert_called_once()

    def test_apply_with_conflict_resolution_disabled(self, sample_fixes, monkeypatch):
        """Test applying with conflict resolution disabled."""
        mock_tool = MagicMock()
        mock_batch = MagicMock()
        mock_tool.apply_batch.return_value = mock_batch

        result = apply_with_conflict_resolution(sample_fixes, mock_tool, resolve_conflicts=False)

        mock_tool.apply_batch.assert_called_once_with(sample_fixes)


class TestFixConflict:
    """Tests for FixConflict dataclass."""

    def test_autogenerates_description(self):
        """Test that description is auto-generated."""
        fix_a = Fix(
            id="fix_a",
            file_path="src/test.py",
            line_start=10,
            line_end=10,
            old_text="a",
            new_text="b",
            reason="Test",
            rule_id="TEST",
            severity=FixSeverity.WARNING,
        )
        fix_b = Fix(
            id="fix_b",
            file_path="src/test.py",
            line_start=12,
            line_end=12,
            old_text="c",
            new_text="d",
            reason="Test",
            rule_id="TEST",
            severity=FixSeverity.WARNING,
        )

        conflict = FixConflict(
            conflict_type=ConflictType.OVERLAPPING_LINES,
            fix_a=fix_a,
            fix_b=fix_b,
            overlap_lines=(10, 12),
            severity="medium",
        )

        assert conflict.description
        assert "fix_a" in conflict.description or "10" in conflict.description


class TestConflictResolverEdgeCases:
    """Edge case tests for ConflictResolver."""

    def test_single_fix_no_conflict(self):
        """Test single fix doesn't cause conflict."""
        fix = Fix(
            id="fix_1",
            file_path="src/test.py",
            line_start=10,
            line_end=10,
            old_text="a",
            new_text="b",
            reason="Test",
            rule_id="TEST",
            severity=FixSeverity.INFO,
        )

        resolver = ConflictResolver()
        conflicts = resolver.detect_conflicts([fix])

        assert len(conflicts) == 0

    def test_adjacent_fixes_conflict(self):
        """Test adjacent fixes may conflict based on window."""
        fixes = [
            Fix(
                id="fix_1",
                file_path="src/test.py",
                line_start=10,
                line_end=10,
                old_text="a",
                new_text="b",
                reason="Test",
                rule_id="TEST1",
                severity=FixSeverity.INFO,
            ),
            Fix(
                id="fix_2",
                file_path="src/test.py",
                line_start=12,
                line_end=12,
                old_text="c",
                new_text="d",
                reason="Test",
                rule_id="TEST2",
                severity=FixSeverity.INFO,
            ),
        ]

        # With window of 0, no conflict
        resolver = ConflictResolver(overlap_window=0)
        conflicts = resolver.detect_conflicts(fixes)
        assert len(conflicts) == 0

        # With window of 3, may conflict
        resolver = ConflictResolver(overlap_window=3)
        conflicts = resolver.detect_conflicts(fixes)
        # May or may not conflict based on overlap calculation

    def test_identical_fixes_conflict(self):
        """Test identical fixes are detected as conflicting."""
        fixes = [
            Fix(
                id="fix_1",
                file_path="src/test.py",
                line_start=10,
                line_end=10,
                old_text="same",
                new_text="a",
                reason="Test",
                rule_id="TEST",
                severity=FixSeverity.WARNING,
            ),
            Fix(
                id="fix_2",
                file_path="src/test.py",
                line_start=10,
                line_end=10,
                old_text="same",
                new_text="b",
                reason="Test",
                rule_id="TEST",
                severity=FixSeverity.WARNING,
            ),
        ]

        resolver = ConflictResolver()
        conflicts = resolver.detect_conflicts(fixes)

        assert len(conflicts) >= 1
