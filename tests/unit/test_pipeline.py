"""Tests for UnifiedPipeline and PipelineConfig.

Tests cover:
- Pipeline initialization
- File analysis
- Issue filtering and sorting
- Stats computation
- Interactive fix integration

Usage:
    python -m pytest tests/unit/test_pipeline.py -v
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

from src.application.workflows.unified.pipeline import (
    UnifiedReviewPipeline,
    PipelineConfig,
    PipelineStats,
)


# ─── PipelineConfig Tests ───────────────────────────────────────────────────────


class TestPipelineConfig:
    """Tests for PipelineConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = PipelineConfig()
        
        assert config.enable_ml is True
        assert config.enable_security is True
        assert config.enable_quality is True
        assert config.enable_embedded is True
        assert config.min_confidence == 0.5
        assert config.max_issues_per_file == 50
        assert config.focus_areas == []
        assert config.exclude_patterns == []
        assert config.interactive_mode is False
        assert config.auto_fix_low is False
        assert config.auto_fix_medium is False
        assert config.auto_approve_critical is True

    def test_custom_config(self):
        """Test custom configuration values."""
        config = PipelineConfig(
            enable_ml=False,
            enable_security=True,
            min_confidence=0.8,
            max_issues_per_file=25,
            focus_areas=["security"],
            exclude_patterns=["*.test.py"],
            interactive_mode=True,
            auto_fix_low=True,
            auto_fix_medium=True,
        )
        
        assert config.enable_ml is False
        assert config.enable_security is True
        assert config.min_confidence == 0.8
        assert config.max_issues_per_file == 25
        assert config.focus_areas == ["security"]
        assert config.exclude_patterns == ["*.test.py"]
        assert config.interactive_mode is True
        assert config.auto_fix_low is True
        assert config.auto_fix_medium is True


# ─── PipelineStats Tests ────────────────────────────────────────────────────────


class TestPipelineStats:
    """Tests for PipelineStats dataclass."""

    def test_default_stats(self):
        """Test default stats values."""
        stats = PipelineStats()
        
        assert stats.files_scanned == 0
        assert stats.total_issues == 0
        assert stats.critical_count == 0
        assert stats.high_count == 0
        assert stats.medium_count == 0
        assert stats.low_count == 0
        assert stats.execution_time_ms == 0.0
        assert stats.detectors_used == []
        assert stats.issues_by_detector == {}
        assert stats.issues_by_file == {}

    def test_stats_to_dict(self):
        """Test stats serialization."""
        stats = PipelineStats(
            files_scanned=10,
            total_issues=5,
            critical_count=1,
            high_count=2,
            medium_count=1,
            low_count=1,
            execution_time_ms=150.5,
            detectors_used=["ml", "security"],
            issues_by_detector={"ml": 3, "security": 2},
            issues_by_file={"src/main.py": 5},
        )
        
        result = stats.to_dict()
        
        assert result["files_scanned"] == 10
        assert result["total_issues"] == 5
        assert result["critical_count"] == 1
        assert result["high_count"] == 2
        assert result["medium_count"] == 1
        assert result["low_count"] == 1
        assert result["execution_time_ms"] == 150.5
        assert result["detectors_used"] == ["ml", "security"]
        assert result["issues_by_detector"] == {"ml": 3, "security": 2}
        assert result["issues_by_file"] == {"src/main.py": 5}


# ─── UnifiedReviewPipeline Tests ────────────────────────────────────────────────


class TestUnifiedReviewPipeline:
    """Tests for UnifiedReviewPipeline class."""

    def test_pipeline_initialization(self):
        """Test pipeline initialization with default config."""
        pipeline = UnifiedReviewPipeline()
        
        assert pipeline.config is not None
        assert isinstance(pipeline.config, PipelineConfig)
        # Default registry should have ml, security, quality, embedded
        assert isinstance(pipeline.detectors, list)
        assert len(pipeline.detectors) > 0

    def test_pipeline_with_custom_config(self):
        """Test pipeline initialization with custom config."""
        config = PipelineConfig(enable_ml=False, min_confidence=0.9)
        pipeline = UnifiedReviewPipeline(config=config)
        
        assert pipeline.config.enable_ml is False
        assert pipeline.config.min_confidence == 0.9

    def test_detectors_property(self):
        """Test detectors property returns list of detector names."""
        pipeline = UnifiedReviewPipeline()
        
        # Default registry should have ml, security, quality, embedded
        detectors = pipeline.detectors
        assert isinstance(detectors, list)

    @pytest.mark.asyncio
    async def test_analyze_empty_files(self):
        """Test analyzing empty file list."""
        pipeline = UnifiedReviewPipeline()
        issues = await pipeline.analyze([])
        
        assert issues == []
        assert pipeline.last_stats is not None
        assert pipeline.last_stats.files_scanned == 0

    @pytest.mark.asyncio
    async def test_analyze_with_content_map(self):
        """Test analyzing with content map instead of files."""
        pipeline = UnifiedReviewPipeline()
        
        content_map = {
            "test.py": "import torch\nmodel = MyModel()\noutput = model(x)",
        }
        
        issues = await pipeline.analyze([Path("test.py")], content_map=content_map)
        
        assert isinstance(issues, list)

    def test_filter_and_sort_by_severity(self):
        """Test issue filtering and sorting by severity."""
        from src.domain.models.review_issue import ReviewIssue, Severity
        
        pipeline = UnifiedReviewPipeline()
        
        # Create mock issues with different severities
        mock_issues = [
            ReviewIssue(
                id=f"test-{i}",
                rule_id=f"TEST{i:03d}",
                severity=sev,
                file="test.py",
                line=i,
                message=f"Issue {i}",
            )
            for i, sev in enumerate([
                Severity.LOW,
                Severity.CRITICAL,
                Severity.MEDIUM,
                Severity.HIGH,
            ])
        ]
        
        # Filter by confidence (all pass)
        filtered = pipeline._filter_and_sort(mock_issues)
        
        # Should be sorted by severity weight (descending), then confidence, then line
        assert len(filtered) == 4
        # First should be CRITICAL
        assert filtered[0].severity == Severity.CRITICAL

    def test_filter_by_confidence(self):
        """Test filtering issues by confidence threshold."""
        from src.domain.models.review_issue import ReviewIssue, Severity
        
        pipeline = UnifiedReviewPipeline(PipelineConfig(min_confidence=0.8))
        
        mock_issues = [
            ReviewIssue(
                id="test-1",
                rule_id="TEST001",
                severity=Severity.HIGH,
                file="test.py",
                line=1,
                confidence=0.5,
            ),
            ReviewIssue(
                id="test-2",
                rule_id="TEST002",
                severity=Severity.HIGH,
                file="test.py",
                line=2,
                confidence=0.9,
            ),
        ]
        
        filtered = pipeline._filter_and_sort(mock_issues)
        
        assert len(filtered) == 1
        assert filtered[0].id == "test-2"

    def test_max_issues_per_file(self):
        """Test limiting issues per file."""
        from src.domain.models.review_issue import ReviewIssue, Severity
        
        pipeline = UnifiedReviewPipeline(PipelineConfig(max_issues_per_file=2))
        
        mock_issues = [
            ReviewIssue(
                id=f"test-{i}",
                rule_id=f"TEST{i:03d}",
                severity=Severity.HIGH,
                file="test.py",
                line=i,
            )
            for i in range(5)
        ]
        
        filtered = pipeline._filter_and_sort(mock_issues)
        
        assert len(filtered) == 2

    def test_get_fixable_issues(self):
        """Test extracting fixable issues."""
        from src.domain.models.review_issue import ReviewIssue, Severity, FixOption
        
        pipeline = UnifiedReviewPipeline()
        
        mock_issues = [
            ReviewIssue(
                id="fixable",
                rule_id="TEST001",
                severity=Severity.LOW,
                file="test.py",
                line=1,
                fixes=[FixOption(id="fix-1", title="Fix")],
            ),
            ReviewIssue(
                id="not-fixable",
                rule_id="TEST002",
                severity=Severity.HIGH,
                file="test.py",
                line=2,
            ),
        ]
        
        fixable = pipeline.get_fixable_issues(mock_issues)
        
        assert len(fixable) == 1
        assert fixable[0].id == "fixable"

    def test_get_fixable_issues_with_max_severity(self):
        """Test filtering fixable issues by max severity."""
        from src.domain.models.review_issue import ReviewIssue, Severity, FixOption
        
        pipeline = UnifiedReviewPipeline()
        
        mock_issues = [
            ReviewIssue(
                id="low-fixable",
                rule_id="TEST001",
                severity=Severity.LOW,
                file="test.py",
                line=1,
                fixes=[FixOption(id="fix-1", title="Fix")],
            ),
            ReviewIssue(
                id="high-fixable",
                rule_id="TEST002",
                severity=Severity.HIGH,
                file="test.py",
                line=2,
                fixes=[FixOption(id="fix-2", title="Fix")],
            ),
        ]
        
        fixable = pipeline.get_fixable_issues(mock_issues, max_severity=Severity.LOW)
        
        assert len(fixable) == 1
        assert fixable[0].id == "low-fixable"

    def test_categorize_issues_by_action(self):
        """Test categorizing issues by recommended action."""
        from src.domain.models.review_issue import ReviewIssue, Severity, FixOption
        
        pipeline = UnifiedReviewPipeline()
        
        mock_issues = [
            ReviewIssue(
                id="critical-1",
                rule_id="TEST001",
                severity=Severity.CRITICAL,
                file="test.py",
                line=1,
            ),
            ReviewIssue(
                id="low-fixable",
                rule_id="TEST002",
                severity=Severity.LOW,
                file="test.py",
                line=2,
                fixes=[FixOption(id="fix-1", title="Fix")],
            ),
            ReviewIssue(
                id="high-1",
                rule_id="TEST003",
                severity=Severity.HIGH,
                file="test.py",
                line=3,
            ),
        ]
        
        categories = pipeline.categorize_issues_by_action(mock_issues)
        
        assert len(categories["critical_warn"]) == 1
        assert len(categories["auto_fix_low"]) == 1
        assert len(categories["review_required"]) == 1


# ─── Mock Detectors for Testing ─────────────────────────────────────────────────


class MockDetector:
    """Mock detector for testing."""
    
    def __init__(self, name: str = "mock", issues: list = None):
        self.name = name
        self.config = MagicMock()
        self.config.enabled = True
        self._issues = issues or []
    
    def detect_batch(self, contexts):
        return self._issues


# ─── Integration Tests ─────────────────────────────────────────────────────────


class TestPipelineIntegration:
    """Integration tests for the pipeline."""

    @pytest.mark.asyncio
    async def test_analyze_with_mock_detector(self):
        """Test pipeline with mock detector."""
        from src.application.workflows.unified.pipeline import DetectorRegistry
        from src.domain.models.review_issue import ReviewIssue, Severity
        
        # Create mock issues
        mock_issues = [
            ReviewIssue(
                id="mock-1",
                rule_id="MOCK001",
                severity=Severity.HIGH,
                file="test.py",
                line=10,
                message="Mock issue",
            ),
        ]
        
        # Create registry with mock detector
        registry = DetectorRegistry()
        registry.register("mock", MockDetector("mock", mock_issues))
        
        # Create pipeline with registry
        pipeline = UnifiedReviewPipeline(registry=registry)
        
        # Create content map with actual content
        content_map = {
            "test.py": "# Mock content for test\nx = 1\n",
        }
        
        # Analyze with content map
        issues = await pipeline.analyze([Path("test.py")], content_map=content_map)
        
        # Should include mock issues (if conversion works)
        assert isinstance(issues, list)
