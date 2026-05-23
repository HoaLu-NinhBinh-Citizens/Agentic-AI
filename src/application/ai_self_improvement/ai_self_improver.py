"""AI self-improvement features (Phase 16.4).

Provides AI self-improvement capabilities:
- Auto test case generation from coverage gaps
- Architecture improvement suggestions
- Learning from user rejections
- Auto fine-tuning triggers
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CoverageGapType(Enum):
    """Types of coverage gaps."""
    UNCOVERED_FUNCTION = "uncovered_function"
    UNCOVERED_BRANCH = "uncovered_branch"
    EDGE_CASE = "edge_case"
    ERROR_PATH = "error_path"


@dataclass
class CoverageGap:
    """Coverage gap information."""
    gap_id: str
    gap_type: CoverageGapType
    location: str  # file:line or function name
    severity: str = "medium"  # low, medium, high
    
    # Details
    description: str = ""
    suggested_test: str = ""
    estimated_complexity: int = 1  # 1-5
    
    # Metadata
    discovered_at: datetime = field(default_factory=datetime.now)
    attempts: int = 0


@dataclass
class Rejection:
    """User rejection of AI suggestion."""
    rejection_id: str
    suggestion_id: str
    
    # Context
    user_id: str
    suggestion_type: str  # patch, explanation, code
    suggestion_content: str
    
    # Rejection reason
    reason: str = ""
    reason_category: str = ""  # incorrect, style, safety, other
    
    # Feedback
    user_correction: str = ""
    
    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)
    session_id: str = ""


@dataclass
class ArchitectureSuggestion:
    """Architecture improvement suggestion."""
    suggestion_id: str
    title: str
    description: str
    
    # Impact
    impact_type: str = "performance"  # performance, maintainability, reliability
    estimated_improvement: str = ""
    
    # Implementation
    complexity: str = "medium"  # low, medium, high
    estimated_effort_hours: float = 0.0
    
    # Details
    affected_components: list[str] = field(default_factory=list)
    risk_level: str = "low"
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    confidence: float = 0.0  # 0.0 - 1.0


class CoverageGapAnalyzer:
    """Analyzes coverage gaps and suggests tests."""
    
    def __init__(self) -> None:
        self._gaps: list[CoverageGap] = []
    
    def analyze(self, coverage_report: dict[str, Any]) -> list[CoverageGap]:
        """Analyze coverage report for gaps."""
        gaps = []
        
        # Check uncovered functions
        for func_name, covered in coverage_report.get("functions", {}).items():
            if not covered:
                gaps.append(CoverageGap(
                    gap_id=f"gap_{len(gaps)}",
                    gap_type=CoverageGapType.UNCOVERED_FUNCTION,
                    location=func_name,
                    description=f"Function {func_name} is not covered by tests",
                    suggested_test=self._suggest_test_for_function(func_name),
                ))
        
        # Check uncovered branches
        for location, covered in coverage_report.get("branches", {}).items():
            if not covered:
                gaps.append(CoverageGap(
                    gap_id=f"gap_{len(gaps)}",
                    gap_type=CoverageGapType.UNCOVERED_BRANCH,
                    location=location,
                    severity="high",
                    description=f"Uncovered code path at {location}",
                    suggested_test="Add test for error handling path",
                ))
        
        self._gaps.extend(gaps)
        return gaps
    
    def _suggest_test_for_function(self, func_name: str) -> str:
        """Suggest test for uncovered function."""
        return f"def test_{func_name}():\n    # Test {func_name}\n    pass"


class RejectionLearner:
    """Learns from user rejections."""
    
    def __init__(self) -> None:
        self._rejections: list[Rejection] = []
        self._patterns: dict[str, int] = {}  # pattern -> count
    
    def record_rejection(self, rejection: Rejection) -> None:
        """Record user rejection."""
        self._rejections.append(rejection)
        
        # Extract pattern
        pattern = self._extract_pattern(rejection.reason)
        self._patterns[pattern] = self._patterns.get(pattern, 0) + 1
        
        logger.info("Rejection recorded", pattern=pattern)
    
    def _extract_pattern(self, reason: str) -> str:
        """Extract rejection pattern."""
        reason_lower = reason.lower()
        
        if "incorrect" in reason_lower:
            return "incorrect_logic"
        elif "style" in reason_lower or "format" in reason_lower:
            return "style_issue"
        elif "safety" in reason_lower or "security" in reason_lower:
            return "safety_concern"
        elif "performance" in reason_lower or "slow" in reason_lower:
            return "performance_issue"
        else:
            return "other"
    
    def get_common_patterns(self) -> list[tuple[str, int]]:
        """Get most common rejection patterns."""
        return sorted(self._patterns.items(), key=lambda x: x[1], reverse=True)
    
    def get_confidence_calibration(self) -> dict[str, float]:
        """Calculate confidence calibration from rejections."""
        total = len(self._rejections)
        if total == 0:
            return {"accuracy": 0.0, "calibration_error": 0.0}
        
        # Simplified calibration
        accepted = sum(1 for r in self._rejections if r.reason_category == "accepted")
        accuracy = accepted / total
        
        # Calibration error (difference between stated confidence and actual)
        # Simplified: assume average stated confidence was 0.7
        calibration_error = abs(0.7 - accuracy)
        
        return {
            "accuracy": accuracy,
            "calibration_error": calibration_error,
            "sample_size": total,
        }


class ArchitectureAnalyzer:
    """Analyzes architecture and suggests improvements."""
    
    def __init__(self) -> None:
        self._suggestions: list[ArchitectureSuggestion] = []
    
    def analyze(self, codebase_metrics: dict[str, Any]) -> list[ArchitectureSuggestion]:
        """Analyze codebase for improvement opportunities."""
        suggestions = []
        
        # Check for large modules
        for module, size in codebase_metrics.get("module_sizes", {}).items():
            if size > 5000:  # Lines of code
                suggestions.append(ArchitectureSuggestion(
                    suggestion_id=f"sug_{len(suggestions)}",
                    title=f"Refactor large module: {module}",
                    description=f"Module {module} has {size} lines. Consider splitting.",
                    impact_type="maintainability",
                    estimated_improvement="Improved maintainability and testability",
                    complexity="high",
                    estimated_effort_hours=8.0,
                    affected_components=[module],
                    risk_level="medium",
                    confidence=0.85,
                ))
        
        # Check for circular dependencies
        for cycle in codebase_metrics.get("dependency_cycles", []):
            suggestions.append(ArchitectureSuggestion(
                suggestion_id=f"sug_{len(suggestions)}",
                title="Remove circular dependency",
                description=f"Circular dependency detected: {' -> '.join(cycle)}",
                impact_type="maintainability",
                estimated_improvement="Reduced coupling",
                complexity="medium",
                estimated_effort_hours=4.0,
                affected_components=cycle,
                risk_level="low",
                confidence=0.95,
            ))
        
        self._suggestions.extend(suggestions)
        return suggestions


class AISelfImprover:
    """Main AI self-improvement system.
    
    Phase 16.4: AI self-improvement
    """
    
    def __init__(self) -> None:
        self._coverage_analyzer = CoverageGapAnalyzer()
        self._rejection_learner = RejectionLearner()
        self._architecture_analyzer = ArchitectureAnalyzer()
        self._fine_tune_triggered = False
    
    def analyze_coverage_gaps(self, coverage_report: dict[str, Any]) -> list[CoverageGap]:
        """Analyze and suggest tests for coverage gaps."""
        return self._coverage_analyzer.analyze(coverage_report)
    
    def record_rejection(self, rejection: Rejection) -> None:
        """Record user rejection."""
        self._rejection_learner.record_rejection(rejection)
    
    def analyze_architecture(self, metrics: dict[str, Any]) -> list[ArchitectureSuggestion]:
        """Analyze architecture and suggest improvements."""
        return self._architecture_analyzer.analyze(metrics)
    
    def should_trigger_fine_tune(self) -> tuple[bool, str]:
        """Check if fine-tuning should be triggered."""
        patterns = self._rejection_learner.get_common_patterns()
        
        if not patterns:
            return False, "Not enough data"
        
        # Trigger if we have enough rejections with a clear pattern
        top_pattern, count = patterns[0]
        
        if count >= 100:
            self._fine_tune_triggered = True
            return True, f"Triggered by {count} rejections of type '{top_pattern}'"
        
        return False, "Threshold not reached"
    
    def get_improvement_report(self) -> dict[str, Any]:
        """Generate improvement report."""
        return {
            "coverage_gaps": len(self._coverage_analyzer._gaps),
            "rejections_recorded": len(self._rejection_learner._rejections),
            "common_patterns": self._rejection_learner.get_common_patterns()[:5],
            "calibration": self._rejection_learner.get_confidence_calibration(),
            "architecture_suggestions": len(self._architecture_analyzer._suggestions),
            "fine_tune_triggered": self._fine_tune_triggered,
        }


# Global system
_self_improver: AISelfImprover | None = None


def get_ai_self_improver() -> AISelfImprover:
    """Get global AI self-improver."""
    global _self_improver
    if _self_improver is None:
        _self_improver = AISelfImprover()
    return _self_improver


if __name__ == "__main__":
    improver = get_ai_self_improver()
    
    # Analyze coverage gaps
    coverage_report = {
        "functions": {
            "calculate_checksum": True,
            "validate_input": False,
            "process_data": True,
        },
        "branches": {
            "file.c:42": False,
        },
    }
    
    gaps = improver.analyze_coverage_gaps(coverage_report)
    print("Coverage Gap Analysis")
    print("=" * 40)
    print(f"Gaps found: {len(gaps)}")
    for gap in gaps:
        print(f"  [{gap.gap_type.value}] {gap.location}")
        print(f"    Suggestion: {gap.suggested_test[:50]}...")
    
    # Record rejection
    rejection = Rejection(
        rejection_id="r1",
        suggestion_id="s1",
        user_id="user1",
        suggestion_type="patch",
        suggestion_content="Fix buffer overflow",
        reason="The fix is incorrect for edge case",
        reason_category="incorrect",
    )
    improver.record_rejection(rejection)
    
    # Check fine-tune trigger
    should_tune, reason = improver.should_trigger_fine_tune()
    print(f"\nFine-tune trigger: {should_tune} - {reason}")
    
    # Report
    report = improver.get_improvement_report()
    print(f"\nImprovement Report: {report}")
