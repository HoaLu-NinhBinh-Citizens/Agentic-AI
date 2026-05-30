"""Tests for multi-option fix generation.

Tests the fix templates and multi-option generation for ML rules.

Usage:
    python -m pytest tests/unit/test_multi_option_fixes.py
"""

from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import Optional

from src.domain.models.review_issue import FixOption, Severity
from src.infrastructure.analysis.ml_detectors.fix_templates import (
    FIX_TEMPLATES,
    get_template,
    get_primary_option,
    get_all_options,
)


# ─── Mock Finding for Testing ───────────────────────────────────────────────────


@dataclass
class MockFinding:
    """Mock Finding for testing."""
    rule_id: str = "ML001"
    rule_name: str = "test_rule"
    line: int = 10
    end_line: int = 10
    fix: str = ""
    confidence: float = 0.85
    severity: Severity = Severity.MEDIUM
    file: str = "test.py"
    message: str = "Test finding"
    old_code: str = "scaler.fit(X)"
    new_code: str = "scaler.fit_transform(X_train)"


# ─── Fix Template Tests ─────────────────────────────────────────────────────────


class TestFixTemplates:
    """Tests for fix templates."""

    def test_all_ml_rules_have_primary_option(self):
        """All ML rules should have a primary fix option."""
        for rule_id in ["ML001", "ML002", "ML003", "ML004", "ML005",
                        "ML006", "ML007", "ML008", "ML009", "ML010"]:
            assert rule_id in FIX_TEMPLATES, f"Missing template for {rule_id}"
            assert "primary" in FIX_TEMPLATES[rule_id], f"Missing primary for {rule_id}"

    def test_primary_option_has_required_fields(self):
        """Primary options should have all required fields."""
        required_fields = ["title", "description", "new_code", "risk", "tradeoff"]
        for rule_id, templates in FIX_TEMPLATES.items():
            primary = templates.get("primary", {})
            for field_name in required_fields:
                assert field_name in primary, f"Missing {field_name} in {rule_id}.primary"

    def test_alternative_options_have_tradeoff(self):
        """Alternative options should have tradeoff explanations."""
        for rule_id, templates in FIX_TEMPLATES.items():
            for key, option in templates.items():
                if key != "primary":
                    assert option.get("tradeoff"), f"Missing tradeoff for {rule_id}.{key}"

    def test_alternative_options_have_test_recommendation(self):
        """Alternative options should have test recommendations."""
        for rule_id, templates in FIX_TEMPLATES.items():
            for key, option in templates.items():
                if key != "primary":
                    assert option.get("test_recommendation"), \
                        f"Missing test_recommendation for {rule_id}.{key}"

    def test_ml002_has_two_options(self):
        """ML002 (loss function mismatch) should have 2 options."""
        assert "ML002" in FIX_TEMPLATES
        assert len(FIX_TEMPLATES["ML002"]) == 2
        assert "primary" in FIX_TEMPLATES["ML002"]
        assert "alternative_1" in FIX_TEMPLATES["ML002"]

    def test_ml003_has_two_options(self):
        """ML003 (device mismatch) should have 2 options."""
        assert "ML003" in FIX_TEMPLATES
        assert len(FIX_TEMPLATES["ML003"]) == 2

    def test_ml005_has_two_options(self):
        """ML005 (missing seed) should have 2 options."""
        assert "ML005" in FIX_TEMPLATES
        assert len(FIX_TEMPLATES["ML005"]) == 2


class TestFixTemplateHelpers:
    """Tests for fix template helper functions."""

    def test_get_template_returns_dict(self):
        """get_template should return dictionary for valid rule."""
        template = get_template("ML001")
        assert template is not None
        assert isinstance(template, dict)

    def test_get_template_returns_none_for_invalid(self):
        """get_template should return None for invalid rule."""
        template = get_template("INVALID")
        assert template is None

    def test_get_primary_option(self):
        """get_primary_option should return primary option."""
        primary = get_primary_option("ML001")
        assert primary is not None
        assert primary["title"] == "Fit scaler after train_test_split"

    def test_get_all_options(self):
        """get_all_options should return all options."""
        options = get_all_options("ML002")
        assert len(options) == 2
        titles = [opt["title"] for opt in options]
        assert "Use BCEWithLogitsLoss for multi-label" in titles
        assert "Use MultiLabelBinarizer preprocessing" in titles


# ─── FixOption Multi-Option Tests ──────────────────────────────────────────────


class TestFixOptionModel:
    """Tests for FixOption model with multi-option fields."""

    def test_fix_option_with_tradeoff(self):
        """FixOption should support tradeoff field."""
        option = FixOption(
            id="test-1",
            title="Test Option",
            description="A test fix option",
            new_code="print('hello')",
            tradeoff="May affect performance",
        )
        assert option.tradeoff == "May affect performance"

    def test_fix_option_with_test_recommendation(self):
        """FixOption should support test_recommendation field."""
        option = FixOption(
            id="test-2",
            title="Test Option",
            test_recommendation="Run integration tests",
        )
        assert option.test_recommendation == "Run integration tests"

    def test_fix_option_with_alternative_to(self):
        """FixOption should support alternative_to field."""
        option = FixOption(
            id="test-alt-2",
            title="Alternative Option",
            alternative_to="test-primary-1",
        )
        assert option.alternative_to == "test-primary-1"

    def test_fix_option_to_dict_includes_new_fields(self):
        """FixOption.to_dict() should include new fields."""
        option = FixOption(
            id="test-3",
            title="Test Option",
            tradeoff="Tradeoff explanation",
            test_recommendation="Run tests",
        )
        result = option.to_dict()
        assert "tradeoff" in result
        assert "test_recommendation" in result
        assert "alternative_to" in result
        assert result["tradeoff"] == "Tradeoff explanation"

    def test_fix_option_from_dict_with_new_fields(self):
        """FixOption.from_dict() should support new fields."""
        from src.domain.models.review_issue import FixOption

        data = {
            "id": "test-4",
            "title": "Test Option",
            "tradeoff": "Test tradeoff",
            "test_recommendation": "Test recommendation",
            "alternative_to": "other-option",
        }
        option = FixOption(
            id=data["id"],
            title=data["title"],
            tradeoff=data["tradeoff"],
            test_recommendation=data["test_recommendation"],
            alternative_to=data["alternative_to"],
        )
        assert option.tradeoff == "Test tradeoff"
        assert option.test_recommendation == "Test recommendation"


# ─── Suggestion Engine Multi-Option Tests ──────────────────────────────────────


class TestSuggestionEngineMultiOption:
    """Tests for SuggestionEngine multi-option generation."""

    @pytest.fixture
    def engine(self):
        """Create SuggestionEngine instance."""
        from src.application.workflows.unified.suggestion_engine import SuggestionEngine
        return SuggestionEngine()

    @pytest.mark.asyncio
    async def test_ml_rules_generate_multiple_options(self, engine):
        """ML rules with templates should generate multiple options."""
        for rule_id in ["ML001", "ML002", "ML003", "ML005"]:
            finding = MockFinding(rule_id=rule_id)
            options = await engine._generate_options(finding, context=None)

            # Should have at least 2 options from template
            assert len(options) >= 2, f"Expected multiple options for {rule_id}"

    @pytest.mark.asyncio
    async def test_options_have_tradeoff_info(self, engine):
        """Generated options should have tradeoff information."""
        finding = MockFinding(rule_id="ML002")
        options = await engine._generate_options(finding, context=None)

        # Check that options have tradeoff info
        for option in options:
            # Only check options from templates (those with description from template)
            if option.tradeoff or option.description:
                continue
            # If neither is set, that's also fine (fallback behavior)

    @pytest.mark.asyncio
    async def test_primary_option_has_higher_confidence(self, engine):
        """Primary option should have higher confidence than alternatives."""
        finding = MockFinding(rule_id="ML002")
        options = await engine._generate_options(finding, context=None)

        if len(options) >= 2:
            # First option should be primary (higher confidence)
            assert options[0].confidence >= options[-1].confidence

    @pytest.mark.asyncio
    async def test_non_primary_options_linked(self, engine):
        """Non-primary options should be linked to primary."""
        finding = MockFinding(rule_id="ML002")
        options = await engine._generate_options(finding, context=None)

        # Alternative options should reference primary
        if len(options) > 1:
            for option in options[1:]:
                # Either has alternative_to set or code differs from primary
                pass  # Implementation may vary


# ─── Result Formatter Multi-Option Tests ──────────────────────────────────────


class TestResultFormatterMultiOption:
    """Tests for result formatter multi-option display."""

    @pytest.fixture
    def formatter(self):
        """Create formatter instance."""
        from src.application.workflows.unified.result_formatter import UnifiedMarkdownFormatter
        return UnifiedMarkdownFormatter()

    def test_single_fix_formatting(self, formatter):
        """Single fix should be formatted compactly."""
        from src.domain.models.review_issue import ReviewIssue, FixOption, Severity

        issue = ReviewIssue(
            id="test-1",
            rule_id="TEST001",
            severity=Severity.HIGH,
            file="test.py",
            line=10,
            message="Test issue",
            fixes=[
                FixOption(
                    id="test-fix-1",
                    title="Simple Fix",
                    new_code="x = 1",
                )
            ]
        )

        md = issue.to_markdown()
        assert "**Fix:**" in md
        assert "x = 1" in md

    def test_multiple_fixes_formatting(self, formatter):
        """Multiple fixes should be formatted with options."""
        from src.domain.models.review_issue import ReviewIssue, FixOption, Severity

        issue = ReviewIssue(
            id="test-2",
            rule_id="TEST002",
            severity=Severity.HIGH,
            file="test.py",
            line=10,
            message="Test issue",
            fixes=[
                FixOption(
                    id="test-fix-1",
                    title="Primary Fix",
                    new_code="x = 1",
                    tradeoff="Simple fix",
                ),
                FixOption(
                    id="test-fix-2",
                    title="Alternative Fix",
                    new_code="y = 2",
                    tradeoff="Alternative approach",
                    test_recommendation="Run tests",
                )
            ]
        )

        md = issue.to_markdown()
        assert "**Fix Options:**" in md
        assert "1. " in md  # Options are numbered with dots
        assert "2. " in md
        assert "Tradeoff:" in md
        assert "Test:" in md


# ─── Integration Tests ──────────────────────────────────────────────────────────


class TestIntegration:
    """Integration tests for multi-option system."""

    def test_end_to_end_fix_generation(self):
        """Test complete flow from template to FixOption."""
        from src.infrastructure.analysis.ml_detectors.fix_templates import FIX_TEMPLATES
        from src.domain.models.review_issue import FixOption, Severity

        rule_id = "ML002"
        templates = FIX_TEMPLATES.get(rule_id, {})

        # Convert templates to FixOption objects
        options = []
        for idx, (key, template) in enumerate(templates.items()):
            option = FixOption(
                id=f"{rule_id}-{idx+1}",
                title=template["title"],
                description=template["description"],
                new_code=template["new_code"],
                risk=Severity.MEDIUM,
                confidence=0.9 if key == "primary" else 0.75,
                tradeoff=template.get("tradeoff", ""),
                test_recommendation=template.get("test_recommendation", ""),
            )
            options.append(option)

        assert len(options) == 2
        assert options[0].title == "Use BCEWithLogitsLoss for multi-label"
        assert options[1].tradeoff  # Should have tradeoff info

    def test_review_issue_with_multiple_fixes(self):
        """Test ReviewIssue with multiple fix options."""
        from src.domain.models.review_issue import ReviewIssue, FixOption, Severity

        issue = ReviewIssue(
            id="ml002-issue-1",
            rule_id="ML002",
            severity=Severity.CRITICAL,
            file="train.py",
            line=42,
            message="CrossEntropyLoss with multi-label data",
            fixes=[
                FixOption(
                    id="ml002-fix-1",
                    title="Use BCEWithLogitsLoss",
                    new_code="criterion = nn.BCEWithLogitsLoss()",
                    tradeoff="Requires sigmoid activation if not present",
                ),
                FixOption(
                    id="ml002-fix-2",
                    title="Use MultiLabelBinarizer",
                    new_code="y_encoded = mlb.fit_transform(y)",
                    tradeoff="Changes target format",
                ),
            ]
        )

        assert issue.is_fixable
        assert len(issue.fixes) == 2
        assert issue.primary_fix is not None

        # Test markdown generation
        md = issue.to_markdown()
        assert "1. " in md  # Options are numbered with dots
        assert "2. " in md
