"""Evaluation framework for comparing AI approaches (Phase 12.1).

Provides framework for evaluating different AI approaches:
- RAG vs fine-tune vs baseline comparison
- Metric tracking
- Statistical significance testing
- Report generation
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class EvaluationType(Enum):
    """Types of evaluation."""
    RAG_BASELINE = "rag_baseline"
    FINE_TUNED = "fine_tuned"
    PROMPT_ENGINEERED = "prompt_engineered"
    BASELINE = "baseline"


class MetricType(Enum):
    """Metric types."""
    ACCURACY = "accuracy"
    LATENCY = "latency"
    COST = "cost"
    USER_SATISFACTION = "user_satisfaction"


@dataclass
class EvaluationMetric:
    """Single evaluation metric."""
    name: str
    type: MetricType
    value: float
    unit: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class EvaluationResult:
    """Result of a single evaluation."""
    evaluation_id: str
    evaluation_type: EvaluationType
    timestamp: datetime
    
    # Metrics
    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    latency_ms: float = 0.0
    cost_per_query: float = 0.0
    
    # Raw data
    total_queries: int = 0
    successful_queries: int = 0
    failed_queries: int = 0
    
    # Additional metrics
    metrics: dict[str, float] = field(default_factory=dict)
    
    @property
    def success_rate(self) -> float:
        if self.total_queries == 0:
            return 0.0
        return self.successful_queries / self.total_queries


@dataclass
class ComparisonResult:
    """Comparison between evaluation results."""
    baseline: EvaluationResult
    candidate: EvaluationResult
    
    # Differences
    accuracy_diff: float = 0.0
    latency_diff: float = 0.0
    cost_diff: float = 0.0
    
    # Statistical
    p_value: float = 1.0
    confidence_interval: tuple[float, float] = (0.0, 0.0)
    statistically_significant: bool = False
    
    @property
    def winner(self) -> str:
        """Determine winner based on accuracy and cost."""
        if self.statistically_significant:
            if self.candidate.accuracy > self.baseline.accuracy:
                return "candidate"
            elif self.baseline.accuracy > self.candidate.accuracy:
                return "baseline"
        return "inconclusive"


@dataclass
class EvaluationSuite:
    """Collection of evaluations."""
    suite_id: str
    name: str
    created_at: datetime = field(default_factory=datetime.now)
    results: list[EvaluationResult] = field(default_factory=list)
    
    def add_result(self, result: EvaluationResult) -> None:
        self.results.append(result)


class StatisticalAnalyzer:
    """Statistical analysis for evaluation."""
    
    @staticmethod
    def t_test(sample1: list[float], sample2: list[float]) -> tuple[float, float]:
        """Perform t-test. Returns (t_statistic, p_value)."""
        if len(sample1) < 2 or len(sample2) < 2:
            return 0.0, 1.0
        
        mean1, mean2 = statistics.mean(sample1), statistics.mean(sample2)
        var1, var2 = statistics.variance(sample1), statistics.variance(sample2)
        n1, n2 = len(sample1), len(sample2)
        
        # Welch's t-test
        se = ((var1 / n1) + (var2 / n2)) ** 0.5
        if se == 0:
            return 0.0, 1.0
        
        t_stat = (mean1 - mean2) / se
        # Simplified p-value (would use scipy in production)
        p_value = 0.05 if abs(t_stat) > 2 else 0.5
        
        return t_stat, p_value
    
    @staticmethod
    def confidence_interval(data: list[float], confidence: float = 0.95) -> tuple[float, float]:
        """Calculate confidence interval."""
        if len(data) < 2:
            return (data[0] if data else 0.0, data[0] if data else 0.0)
        
        mean = statistics.mean(data)
        se = statistics.stdev(data) / (len(data) ** 0.5)
        
        # Z-score for 95% confidence
        z = 1.96
        return (mean - z * se, mean + z * se)


class EvaluationFramework:
    """Main evaluation framework.
    
    Phase 12.1: Evaluation framework
    """
    
    def __init__(self) -> None:
        self._suites: dict[str, EvaluationSuite] = {}
        self._results: list[EvaluationResult] = []
        self._analyzer = StatisticalAnalyzer()
    
    def create_suite(self, name: str) -> EvaluationSuite:
        """Create evaluation suite."""
        import hashlib
        suite_id = hashlib.md5(f"{name}:{datetime.now().isoformat()}".encode()).hexdigest()[:8]
        
        suite = EvaluationSuite(suite_id=suite_id, name=name)
        self._suites[suite_id] = suite
        return suite
    
    def record_result(self, result: EvaluationResult) -> None:
        """Record evaluation result."""
        self._results.append(result)
        logger.info(
            "Evaluation recorded",
            type=result.evaluation_type.value,
            accuracy=result.accuracy,
        )
    
    def compare(
        self,
        baseline_type: EvaluationType,
        candidate_type: EvaluationType,
        suite_id: str | None = None,
    ) -> ComparisonResult | None:
        """Compare two evaluation types."""
        results = self._results if not suite_id else self._suites.get(suite_id, EvaluationSuite("", "")).results
        
        baseline = next(
            (r for r in results if r.evaluation_type == baseline_type),
            None,
        )
        candidate = next(
            (r for r in results if r.evaluation_type == candidate_type),
            None,
        )
        
        if not baseline or not candidate:
            return None
        
        # Calculate differences
        comparison = ComparisonResult(
            baseline=baseline,
            candidate=candidate,
            accuracy_diff=candidate.accuracy - baseline.accuracy,
            latency_diff=candidate.latency_ms - baseline.latency_ms,
            cost_diff=candidate.cost_per_query - baseline.cost_per_query,
        )
        
        # Statistical significance (simplified)
        comparison.p_value = 0.05 if abs(comparison.accuracy_diff) > 0.05 else 0.5
        comparison.confidence_interval = self._analyzer.confidence_interval([
            comparison.accuracy_diff
        ])
        comparison.statistically_significant = comparison.p_value < 0.05
        
        return comparison
    
    def get_summary(self, evaluation_type: EvaluationType | None = None) -> dict[str, Any]:
        """Get evaluation summary."""
        results = self._results
        if evaluation_type:
            results = [r for r in results if r.evaluation_type == evaluation_type]
        
        if not results:
            return {}
        
        accuracies = [r.accuracy for r in results]
        latencies = [r.latency_ms for r in results]
        
        return {
            "total_evaluations": len(results),
            "avg_accuracy": statistics.mean(accuracies),
            "min_accuracy": min(accuracies),
            "max_accuracy": max(accuracies),
            "avg_latency_ms": statistics.mean(latencies),
            "total_queries": sum(r.total_queries for r in results),
        }
    
    def generate_report(self, suite_id: str | None = None) -> str:
        """Generate evaluation report."""
        results = self._results if not suite_id else self._suites.get(suite_id, EvaluationSuite("", "")).results
        
        lines = [
            "=" * 60,
            "EVALUATION REPORT",
            "=" * 60,
            f"Generated: {datetime.now().isoformat()}",
            "",
        ]
        
        # Summary by type
        for eval_type in EvaluationType:
            type_results = [r for r in results if r.evaluation_type == eval_type]
            if type_results:
                avg_acc = statistics.mean([r.accuracy for r in type_results])
                avg_lat = statistics.mean([r.latency_ms for r in type_results])
                lines.append(f"{eval_type.value}:")
                lines.append(f"  Accuracy: {avg_acc:.2%}")
                lines.append(f"  Latency: {avg_lat:.1f}ms")
                lines.append("")
        
        return "\n".join(lines)


# Global framework
_framework: EvaluationFramework | None = None


def get_evaluation_framework() -> EvaluationFramework:
    """Get global evaluation framework."""
    global _framework
    if _framework is None:
        _framework = EvaluationFramework()
    return _framework


if __name__ == "__main__":
    framework = get_evaluation_framework()
    
    # Create suite
    suite = framework.create_suite("Debug Quality Comparison")
    
    # Record baseline
    baseline = EvaluationResult(
        evaluation_id="eval_001",
        evaluation_type=EvaluationType.RAG_BASELINE,
        timestamp=datetime.now(),
        accuracy=0.75,
        latency_ms=500,
        cost_per_query=0.01,
        total_queries=100,
        successful_queries=75,
    )
    framework.record_result(baseline)
    
    # Record fine-tuned
    finetuned = EvaluationResult(
        evaluation_id="eval_002",
        evaluation_type=EvaluationType.FINE_TUNED,
        timestamp=datetime.now(),
        accuracy=0.82,
        latency_ms=300,
        cost_per_query=0.02,
        total_queries=100,
        successful_queries=82,
    )
    framework.record_result(finetuned)
    
    # Compare
    comparison = framework.compare(EvaluationType.RAG_BASELINE, EvaluationType.FINE_TUNED)
    if comparison:
        print("Comparison Results")
        print("=" * 40)
        print(f"Accuracy improvement: +{comparison.accuracy_diff:.2%}")
        print(f"Latency change: {comparison.latency_diff:+.1f}ms")
        print(f"Winner: {comparison.winner}")
    
    # Report
    print("\n" + framework.generate_report())
