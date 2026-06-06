"""Tests for SeverityActionMapper.

Tests cover:
- Action mapping based on severity
- Explicit rule mappings (skip, auto-apply)
- Issue categorization
- CLI argument parsing

Usage:
    python -m pytest tests/unit/test_severity_action_mapper.py -v
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from src.application.workflows.severity_action_mapper import (
    SeverityActionMapper,
    SeverityActionMapperCLI,
    SeverityMapping,
    SeverityAction,
    ActionType,
    apply_auto_fixes,
    format_action_summary,
)
from src.domain.models.review_issue import ReviewIssue, Severity


# ─── SeverityActionMapper Tests ────────────────────────────────────────────────


class TestSeverityActionMapper:
    """Tests for SeverityActionMapper class."""

    def test_default_mapping(self):
        """Test default severity mapping."""
        mapper = SeverityActionMapper()
        
        # CRITICAL should always warn
        issue = ReviewIssue(
            id="test-1",
            rule_id="ML001",
            severity=Severity.CRITICAL,
            file="train.py",
            line=10,
        )
        action = mapper.get_action(issue)
        
        assert action.action_type == ActionType.WARN_CRITICAL
        assert action.requires_confirmation is True
        assert action.should_apply is False

    def test_high_severity_requires_review(self):
        """Test that HIGH severity requires review."""
        mapper = SeverityActionMapper()
        
        issue = ReviewIssue(
            id="test-1",
            rule_id="SEC001",
            severity=Severity.HIGH,
            file="auth.py",
            line=20,
        )
        action = mapper.get_action(issue)
        
        assert action.action_type == ActionType.REVIEW_REQUIRED
        assert action.requires_confirmation is True

    def test_low_severity_auto_fix(self):
        """Test that LOW severity auto-fixes by default."""
        mapper = SeverityActionMapper()
        
        issue = ReviewIssue(
            id="test-1",
            rule_id="QUAL001",
            severity=Severity.LOW,
            file="style.py",
            line=5,
            fixes=[],
        )
        action = mapper.get_action(issue)
        
        # With default threshold "low", LOW issues are auto-fixed
        assert action.action_type == ActionType.AUTO_FIX
        assert action.requires_confirmation is False

    def test_medium_severity_below_threshold(self):
        """Test that MEDIUM severity is skipped when threshold is high."""
        mapper = SeverityActionMapper(
            SeverityMapping(auto_fix_threshold="high")
        )
        
        issue = ReviewIssue(
            id="test-1",
            rule_id="QUAL001",
            severity=Severity.MEDIUM,
            file="style.py",
            line=5,
        )
        action = mapper.get_action(issue)
        
        assert action.action_type == ActionType.SKIP

    def test_explicit_skip_rule(self):
        """Test explicit skip for specific rule."""
        mapper = SeverityActionMapper(
            SeverityMapping(skip_rules=["QUAL001"])
        )
        
        issue = ReviewIssue(
            id="test-1",
            rule_id="QUAL001",
            severity=Severity.LOW,
            file="style.py",
            line=5,
        )
        action = mapper.get_action(issue)
        
        assert action.action_type == ActionType.SKIP
        assert "configured to skip" in action.message

    def test_explicit_auto_apply_rule(self):
        """Test explicit auto-apply for specific rule."""
        mapper = SeverityActionMapper(
            SeverityMapping(auto_apply_rules=["SEC001"])
        )
        
        issue = ReviewIssue(
            id="test-1",
            rule_id="SEC001",
            severity=Severity.HIGH,
            file="auth.py",
            line=20,
        )
        action = mapper.get_action(issue)
        
        assert action.action_type == ActionType.AUTO_FIX
        assert "configured to auto-apply" in action.message

    def test_priority_assignment(self):
        """Test priority assignment based on severity."""
        mapper = SeverityActionMapper()
        
        critical_issue = ReviewIssue(
            id="test-1", rule_id="T1", severity=Severity.CRITICAL,
            file="test.py", line=1
        )
        high_issue = ReviewIssue(
            id="test-2", rule_id="T2", severity=Severity.HIGH,
            file="test.py", line=2
        )
        medium_issue = ReviewIssue(
            id="test-3", rule_id="T3", severity=Severity.MEDIUM,
            file="test.py", line=3
        )
        
        critical_action = mapper.get_action(critical_issue)
        high_action = mapper.get_action(high_issue)
        medium_action = mapper.get_action(medium_issue)
        
        assert critical_action.priority == mapper.PRIORITY_CRITICAL
        assert high_action.priority == mapper.PRIORITY_HIGH
        assert medium_action.priority == mapper.PRIORITY_MEDIUM


# ─── Issue Categorization Tests ────────────────────────────────────────────────


class TestIssueCategorization:
    """Tests for issue categorization."""

    def test_categorize_issues(self):
        """Test categorizing multiple issues."""
        mapper = SeverityActionMapper()
        
        issues = [
            ReviewIssue(
                id="critical-1",
                rule_id="ML001",
                severity=Severity.CRITICAL,
                file="train.py",
                line=1,
            ),
            ReviewIssue(
                id="high-1",
                rule_id="SEC001",
                severity=Severity.HIGH,
                file="auth.py",
                line=1,
            ),
            ReviewIssue(
                id="low-1",
                rule_id="QUAL001",
                severity=Severity.LOW,
                file="style.py",
                line=1,
            ),
        ]
        
        categorized = mapper.categorize_issues(issues)
        
        assert len(categorized[ActionType.WARN_CRITICAL]) == 1
        assert len(categorized[ActionType.REVIEW_REQUIRED]) == 1
        # LOW issues should be AUTO_FIX by default
        assert len(categorized[ActionType.AUTO_FIX]) == 1

    def test_categorize_with_explicit_rules(self):
        """Test categorization respects explicit rules."""
        mapper = SeverityActionMapper(
            SeverityMapping(skip_rules=["QUAL002"])
        )
        
        issues = [
            ReviewIssue(
                id="low-1",
                rule_id="QUAL001",
                severity=Severity.LOW,
                file="style.py",
                line=1,
            ),
            ReviewIssue(
                id="low-skip",
                rule_id="QUAL002",
                severity=Severity.LOW,
                file="style.py",
                line=2,
            ),
        ]
        
        categorized = mapper.categorize_issues(issues)
        
        # QUAL001 should be categorized, QUAL002 should be skipped
        skip_count = len(categorized[ActionType.SKIP])
        assert skip_count >= 1

    def test_get_auto_fix_summary(self):
        """Test getting summary of actions."""
        mapper = SeverityActionMapper()
        
        issues = [
            ReviewIssue(
                id="critical-1",
                rule_id="ML001",
                severity=Severity.CRITICAL,
                file="train.py",
                line=1,
            ),
            ReviewIssue(
                id="high-1",
                rule_id="SEC001",
                severity=Severity.HIGH,
                file="auth.py",
                line=1,
            ),
        ]
        
        summary = mapper.get_auto_fix_summary(issues)
        
        assert summary["total"] == 2
        assert summary["warn_critical"] == 1
        assert summary["review_required"] == 1
        assert summary["auto_fix"] == 0


# ─── SeverityMapping Tests ────────────────────────────────────────────────────


class TestSeverityMapping:
    """Tests for SeverityMapping dataclass."""

    def test_default_mapping(self):
        """Test default mapping values."""
        mapping = SeverityMapping()
        
        assert mapping.auto_fix_threshold == "low"
        assert mapping.warn_on_critical is True
        assert mapping.auto_apply_rules == []
        assert mapping.skip_rules == []

    def test_custom_mapping(self):
        """Test custom mapping values."""
        mapping = SeverityMapping(
            auto_fix_threshold="medium",
            warn_on_critical=False,
            auto_apply_rules=["RULE001", "RULE002"],
            skip_rules=["RULE003"],
        )
        
        assert mapping.auto_fix_threshold == "medium"
        assert mapping.warn_on_critical is False
        assert mapping.auto_apply_rules == ["RULE001", "RULE002"]
        assert mapping.skip_rules == ["RULE003"]


# ─── SeverityAction Tests ─────────────────────────────────────────────────────


class TestSeverityAction:
    """Tests for SeverityAction dataclass."""

    def test_action_creation(self):
        """Test creating a severity action."""
        action = SeverityAction(
            action_type=ActionType.AUTO_FIX,
            should_apply=True,
            requires_confirmation=False,
            priority=2,
            message="Test action",
        )
        
        assert action.action_type == ActionType.AUTO_FIX
        assert action.should_apply is True
        assert action.requires_confirmation is False
        assert action.priority == 2
        assert action.message == "Test action"


# ─── CLI Integration Tests ─────────────────────────────────────────────────────


class TestSeverityActionMapperCLI:
    """Tests for CLI helper class."""

    def test_add_cli_args(self):
        """Test adding CLI arguments to parser."""
        import argparse
        parser = argparse.ArgumentParser()
        
        SeverityActionMapperCLI.add_cli_args(parser)
        
        # Verify arguments were added
        args = parser.parse_args(["--auto-fix"])
        assert args.auto_fix == "low"
        
        args = parser.parse_args(["--auto-fix-level", "high"])
        assert args.auto_fix_level == "high"
    
    def test_cli_argument_defaults(self):
        """Test CLI argument defaults."""
        import argparse
        parser = argparse.ArgumentParser()
        SeverityActionMapperCLI.add_cli_args(parser)
        
        # Default values
        args = parser.parse_args([])
        assert args.auto_fix is None
        assert args.auto_fix_level == "low"


# ─── Apply Auto-Fixes Tests ───────────────────────────────────────────────────


class TestApplyAutoFixes:
    """Tests for apply_auto_fixes function."""

    @pytest.mark.asyncio
    async def test_apply_auto_fixes_empty_list(self):
        """Test applying fixes to empty list."""
        mapper = SeverityActionMapper()
        apply_tool = MagicMock()
        
        results = await apply_auto_fixes([], mapper, apply_tool)
        
        assert results["applied"] == 0
        assert results["skipped"] == 0
        assert results["failed"] == 0

    @pytest.mark.asyncio
    async def test_apply_auto_fixes_skips_non_fixable(self):
        """Test that non-fixable issues are skipped."""
        mapper = SeverityActionMapper()
        
        issue = ReviewIssue(
            id="test-1",
            rule_id="ML001",
            severity=Severity.CRITICAL,
            file="train.py",
            line=5,
        )
        
        apply_tool = MagicMock()
        
        results = await apply_auto_fixes([issue], mapper, apply_tool)
        
        assert results["skipped"] == 1
        assert results["applied"] == 0


# ─── Format Action Summary Tests ───────────────────────────────────────────────


class TestFormatActionSummary:
    """Tests for format_action_summary function."""

    def test_format_empty_summary(self):
        """Test formatting empty summary."""
        mapper = SeverityActionMapper()
        
        summary = format_action_summary([], mapper)
        
        assert "Total Issues:    0" in summary
        assert "Auto-fix:        0" in summary

    def test_format_summary_indicates_auto_fix(self):
        """Test that summary indicates auto-fix count."""
        mapper = SeverityActionMapper()
        
        issues = [
            ReviewIssue(
                id="low-fixable",
                rule_id="QUAL001",
                severity=Severity.LOW,
                file="style.py",
                line=1,
            ),
        ]
        
        summary = format_action_summary(issues, mapper)
        
        assert "1 issue(s) will be auto-fixed" in summary

    def test_format_summary_warns_critical(self):
        """Test that summary warns about critical issues."""
        mapper = SeverityActionMapper()
        
        issues = [
            ReviewIssue(
                id="critical-1",
                rule_id="ML001",
                severity=Severity.CRITICAL,
                file="train.py",
                line=1,
            ),
        ]
        
        summary = format_action_summary(issues, mapper)
        
        assert "CRITICAL issue(s) require explicit approval" in summary
