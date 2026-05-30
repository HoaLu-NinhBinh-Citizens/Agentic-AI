"""Tests for the Unified Suggestion Engine.

Run with: python -m pytest tests/unit/test_suggestion_engine.py
"""

from __future__ import annotations

import pytest

from src.application.suggestion.suggestion_engine import (
    FixOption,
    FixTemplate,
    RiskLevel,
    SuggestionConfig,
    SuggestionResult,
    UnifiedSuggestionEngine,
)
from src.application.suggestion.patch_generator import (
    DiffFormat,
    LineChange,
    Patch,
    PatchGenerator,
    PatchOptions,
    generate_quick_diff,
)


# ─── Test RiskLevel ─────────────────────────────────────────────────────────────


class TestRiskLevel:
    """Tests for RiskLevel enum."""

    def test_risk_levels_exist(self):
        """Verify all risk levels are defined."""
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_to_numeric(self):
        """Test numeric conversion for ranking."""
        assert RiskLevel.LOW.to_numeric() == 0
        assert RiskLevel.MEDIUM.to_numeric() == 1
        assert RiskLevel.HIGH.to_numeric() == 2
        assert RiskLevel.CRITICAL.to_numeric() == 3


# ─── Test FixOption ──────────────────────────────────────────────────────────────


class TestFixOption:
    """Tests for FixOption dataclass."""

    def test_fix_option_creation(self):
        """Test creating a fix option."""
        option = FixOption(
            id="test-1",
            description="Test fix",
            old_code="old = 1",
            new_code="new = 2",
            risk=RiskLevel.LOW,
            confidence=0.9,
        )

        assert option.id == "test-1"
        assert option.description == "Test fix"
        assert option.risk == RiskLevel.LOW
        assert option.confidence == 0.9
        assert option.automated is False
        assert option.requires_review is True

    def test_to_dict(self):
        """Test conversion to dictionary."""
        option = FixOption(
            id="test-1",
            description="Test fix",
            old_code="old = 1",
            new_code="new = 2",
            risk=RiskLevel.LOW,
        )
        d = option.to_dict()

        assert d["id"] == "test-1"
        assert d["risk"] == "low"
        assert d["confidence"] == 1.0

    def test_generate_diff(self):
        """Test diff generation."""
        option = FixOption(
            id="test-1",
            description="Test fix",
            old_code="old = 1\nold = 2",
            new_code="new = 1\nnew = 2",
            risk=RiskLevel.LOW,
        )

        diff = option.generate_diff("test.py")
        assert "---" in diff
        assert "+++" in diff
        assert "old = 1" in diff
        assert "new = 1" in diff


# ─── Test SuggestionResult ──────────────────────────────────────────────────────


class TestSuggestionResult:
    """Tests for SuggestionResult dataclass."""

    def test_result_creation(self):
        """Test creating a suggestion result."""
        option = FixOption(
            id="test-1",
            description="Test fix",
            old_code="old",
            new_code="new",
            risk=RiskLevel.LOW,
        )

        result = SuggestionResult(
            finding_id="TEST001",
            file_path="test.py",
            line=10,
            rule_id="TEST001",
            options=[option],
            best_option=option,
        )

        assert result.finding_id == "TEST001"
        assert result.file_path == "test.py"
        assert result.line == 10
        assert len(result.options) == 1
        assert result.best_option == option

    def test_to_dict(self):
        """Test conversion to dictionary."""
        option = FixOption(
            id="test-1",
            description="Test fix",
            old_code="old",
            new_code="new",
            risk=RiskLevel.LOW,
        )

        result = SuggestionResult(
            finding_id="TEST001",
            file_path="test.py",
            line=10,
            rule_id="TEST001",
            options=[option],
        )

        d = result.to_dict()
        assert d["finding_id"] == "TEST001"
        assert len(d["options"]) == 1


# ─── Test SuggestionConfig ─────────────────────────────────────────────────────


class TestSuggestionConfig:
    """Tests for SuggestionConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SuggestionConfig()

        assert config.max_options_per_finding == 3
        assert config.include_llm_fixes is True
        assert config.llm_model == "llama3"
        assert config.confidence_threshold == 0.5
        assert config.prefer_automated is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = SuggestionConfig(
            max_options_per_finding=5,
            include_llm_fixes=False,
            confidence_threshold=0.8,
        )

        assert config.max_options_per_finding == 5
        assert config.include_llm_fixes is False
        assert config.confidence_threshold == 0.8


# ─── Test UnifiedSuggestionEngine ───────────────────────────────────────────────


class TestUnifiedSuggestionEngine:
    """Tests for UnifiedSuggestionEngine."""

    @pytest.fixture
    def engine(self):
        """Create a suggestion engine for testing."""
        config = SuggestionConfig(
            include_llm_fixes=False,  # Disable LLM for unit tests
            max_options_per_finding=3,
        )
        return UnifiedSuggestionEngine(config=config)

    @pytest.mark.asyncio
    async def test_engine_initialization(self):
        """Test engine initializes correctly."""
        engine = UnifiedSuggestionEngine()
        assert engine.config is not None
        assert engine._templates is not None

    @pytest.mark.asyncio
    async def test_template_fix_generation(self, engine):
        """Test template-based fix generation."""
        from src.application.workflows.unified.detector_base import Finding
        from src.shared.enums.severity import Severity

        finding = Finding(
            rule_id="QUAL003",
            rule_name="Broad Except",
            severity=Severity.HIGH,  # Unified: HIGH instead of WARNING
            file="test.py",
            line=10,
            end_line=10,
            message="Broad except clause",
        )

        result = await engine.generate(finding, context=None)

        assert result.rule_id == "QUAL003"
        assert len(result.options) > 0

        # Check first option has expected attributes
        option = result.options[0]
        assert option.id is not None
        assert option.description is not None
        assert option.risk in [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH]

    @pytest.mark.asyncio
    async def test_multiple_options_generated(self, engine):
        """Test that multiple fix options are generated."""
        from src.application.workflows.unified.detector_base import Finding
        from src.shared.enums.severity import Severity

        finding = Finding(
            rule_id="SEC001",
            rule_name="Hardcoded Secret",
            severity=Severity.CRITICAL,  # Unified: CRITICAL instead of ERROR
            file="test.py",
            line=5,
            end_line=5,
            message="Hardcoded secret detected",
        )

        result = await engine.generate(finding, context=None)

        assert len(result.options) >= 1
        assert result.context_snippet != ""

    @pytest.mark.asyncio
    async def test_ranking_prefers_automated(self):
        """Test that automated options are ranked higher."""
        config = SuggestionConfig(
            prefer_automated=True,
            include_llm_fixes=False,
        )
        engine = UnifiedSuggestionEngine(config=config)

        from src.application.workflows.unified.detector_base import Finding
        from src.shared.enums.severity import Severity

        finding = Finding(
            rule_id="QUAL003",
            rule_name="Broad Except",
            severity=Severity.HIGH,  # Unified: HIGH instead of WARNING
            file="test.py",
            line=10,
            end_line=10,
        )

        result = await engine.generate(finding, context=None)

        if len(result.options) > 1:
            # First option should be best (highest confidence, lowest risk)
            assert result.options[0].confidence >= result.options[-1].confidence


# ─── Test PatchGenerator ───────────────────────────────────────────────────────


class TestPatchGenerator:
    """Tests for PatchGenerator."""

    @pytest.fixture
    def generator(self):
        """Create a patch generator for testing."""
        return PatchGenerator()

    def test_basic_diff(self, generator):
        """Test basic diff generation."""
        old_code = "line1\nline2\nline3\n"
        new_code = "line1\nmodified\nline3\n"

        diff = generator.generate_from_strings(old_code, new_code, "test.py")

        assert "---" in diff
        assert "+++" in diff
        assert "-line2" in diff
        assert "+modified" in diff

    def test_patch_creation(self, generator):
        """Test Patch object creation."""
        old_code = "old content"
        new_code = "new content"

        patch = generator.generate(old_code, new_code, "test.py")

        assert patch.file_path == "test.py"
        assert patch.old_hash != ""
        assert patch.new_hash != ""
        assert patch.stats["added"] > 0 or patch.stats["deleted"] > 0

    def test_json_format(self, generator):
        """Test JSON output format."""
        import json

        old_code = "old\n"
        new_code = "new\n"

        json_output = generator.generate_json(old_code, new_code, "test.py")
        data = json.loads(json_output)

        assert "file_path" in data
        assert "stats" in data

    def test_html_format(self, generator):
        """Test HTML output format."""
        old_code = "old\n"
        new_code = "new\n"

        html_output = generator.generate_html(old_code, new_code, "test.py")

        assert "<html>" in html_output
        assert "<pre>" in html_output
        assert "added" in html_output or "deleted" in html_output

    def test_patch_stats(self, generator):
        """Test patch statistics calculation."""
        old_code = "line1\nline2\nline3\n"
        new_code = "line1\nnew2\nline3\nline4\n"

        patch = generator.generate(old_code, new_code, "test.py")

        assert patch.stats["added"] >= 0
        assert patch.stats["deleted"] >= 0

    def test_quick_diff_function(self):
        """Test quick diff utility function."""
        old = "a\nb\n"
        new = "a\nc\n"

        diff = generate_quick_diff(old, new, "test.py")

        assert isinstance(diff, str)
        assert "---" in diff


# ─── Test DiffFormat Options ────────────────────────────────────────────────────


class TestDiffFormatOptions:
    """Tests for different diff format options."""

    def test_all_formats_available(self):
        """Verify all diff formats are available."""
        assert DiffFormat.UNIFIED.value == "unified"
        assert DiffFormat.SIDE_BY_SIDE.value == "side_by_side"
        assert DiffFormat.CONTEXT.value == "context"
        assert DiffFormat.HTML.value == "html"
        assert DiffFormat.JSON.value == "json"

    def test_patch_options(self):
        """Test PatchOptions configuration."""
        options = PatchOptions(
            format=DiffFormat.HTML,
            context_lines=5,
            ignore_whitespace=True,
            colorize=True,
        )

        assert options.format == DiffFormat.HTML
        assert options.context_lines == 5
        assert options.ignore_whitespace is True
        assert options.colorize is True


# ─── Test Edge Cases ───────────────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_code_diff(self):
        """Test diff with empty code."""
        generator = PatchGenerator()
        patch = generator.generate("", "", "empty.py")

        assert patch.file_path == "empty.py"
        assert patch.has_changes is False

    def test_identical_code_diff(self):
        """Test diff with identical code."""
        generator = PatchGenerator()
        code = "same\ncontent\n"
        patch = generator.generate(code, code, "same.py")

        assert patch.has_changes is False

    def test_whitespace_ignore(self):
        """Test whitespace-ignoring diff."""
        generator = PatchGenerator(PatchOptions(ignore_whitespace=True))
        old = "a  b\nc"
        new = "a b\nc"

        patch = generator.generate(old, new, "test.py")
        # Should detect no changes when whitespace is ignored
        assert patch.stats["added"] == 0


# ─── Run Tests ──────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
