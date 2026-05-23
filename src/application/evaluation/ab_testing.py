"""A/B testing framework (Phase 12.2).

Provides A/B testing infrastructure:
- Traffic splitting
- Statistical analysis
- Multi-variant support
- Result tracking
"""

from __future__ import annotations

import hashlib
import logging
import random
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class Variant(Enum):
    """A/B test variant."""
    CONTROL = "control"
    TREATMENT_A = "treatment_a"
    TREATMENT_B = "treatment_b"


@dataclass
class ABConfig:
    """A/B test configuration."""
    test_id: str
    name: str
    
    # Split ratio (should sum to 1.0)
    control_ratio: float = 0.5
    treatment_a_ratio: float = 0.5
    
    # Traffic
    target_users: int = 1000
    duration_days: int = 7
    
    # Guardrails
    min_sample_size: int = 100
    stop_on_significance: bool = True
    significance_level: float = 0.05


@dataclass
class UserAssignment:
    """User assignment to variant."""
    user_id: str
    variant: Variant
    assigned_at: datetime
    test_id: str


@dataclass
class MetricObservation:
    """Single metric observation."""
    test_id: str
    user_id: str
    variant: Variant
    metric_name: str
    value: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ABResult:
    """A/B test result."""
    test_id: str
    variant: Variant
    sample_size: int
    mean: float
    variance: float
    confidence_interval: tuple[float, float] = (0.0, 0.0)


@dataclass
class ABComparison:
    """Comparison between variants."""
    control: ABResult
    treatment: ABResult
    
    # Difference
    mean_diff: float = 0.0
    relative_diff: float = 0.0
    
    # Statistical
    p_value: float = 1.0
    statistically_significant: bool = False
    winner: Variant | None = None
    
    # Recommendation
    recommended_variant: Variant | None = None
    confidence: float = 0.0


class TrafficSplitter:
    """Traffic splitting logic."""
    
    def assign(
        self,
        user_id: str,
        config: ABConfig,
    ) -> Variant:
        """Assign user to variant."""
        # Deterministic assignment based on user_id hash
        hash_value = int(hashlib.md5(f"{config.test_id}:{user_id}".encode()).hexdigest(), 16)
        normalized = (hash_value % 10000) / 10000.0
        
        if normalized < config.control_ratio:
            return Variant.CONTROL
        elif normalized < config.control_ratio + config.treatment_a_ratio:
            return Variant.TREATMENT_A
        else:
            return Variant.TREATMENT_B


class StatisticalAnalyzer:
    """Statistical analysis for A/B tests."""
    
    @staticmethod
    def calculate_stats(values: list[float]) -> tuple[float, float]:
        """Calculate mean and variance."""
        if not values:
            return 0.0, 0.0
        
        mean = statistics.mean(values)
        variance = statistics.variance(values) if len(values) > 1 else 0.0
        return mean, variance
    
    @staticmethod
    def two_sample_ttest(
        control: list[float],
        treatment: list[float],
    ) -> tuple[float, float]:
        """Two-sample t-test. Returns (t_stat, p_value)."""
        if len(control) < 2 or len(treatment) < 2:
            return 0.0, 1.0
        
        mean_c, var_c = statistics.mean(control), statistics.variance(control)
        mean_t, var_t = statistics.mean(treatment), statistics.variance(treatment)
        
        n_c, n_t = len(control), len(treatment)
        se = ((var_c / n_c) + (var_t / n_t)) ** 0.5
        
        if se == 0:
            return 0.0, 1.0
        
        t_stat = (mean_t - mean_c) / se
        
        # Simplified p-value
        p_value = 0.05 if abs(t_stat) > 1.96 else 0.5
        
        return t_stat, p_value
    
    @staticmethod
    def confidence_interval(
        values: list[float],
        confidence: float = 0.95,
    ) -> tuple[float, float]:
        """Calculate confidence interval."""
        if len(values) < 2:
            return (values[0] if values else 0.0, values[0] if values else 0.0)
        
        mean = statistics.mean(values)
        se = statistics.stdev(values) / (len(values) ** 0.5)
        z = 1.96 if confidence == 0.95 else 2.576
        
        return (mean - z * se, mean + z * se)


class ABTestingFramework:
    """A/B testing framework.
    
    Phase 12.2: A/B testing
    """
    
    def __init__(self) -> None:
        self._configs: dict[str, ABConfig] = {}
        self._assignments: dict[str, UserAssignment] = {}
        self._observations: list[MetricObservation] = []
        self._splitter = TrafficSplitter()
        self._analyzer = StatisticalAnalyzer()
    
    def create_test(self, config: ABConfig) -> str:
        """Create new A/B test."""
        self._configs[config.test_id] = config
        logger.info("A/B test created", test_id=config.test_id, name=config.name)
        return config.test_id
    
    def assign_user(self, test_id: str, user_id: str) -> Variant:
        """Assign user to variant."""
        assignment_key = f"{test_id}:{user_id}"
        
        # Return existing assignment if present
        if assignment_key in self._assignments:
            return self._assignments[assignment_key].variant
        
        config = self._configs.get(test_id)
        if not config:
            return Variant.CONTROL
        
        variant = self._splitter.assign(user_id, config)
        
        assignment = UserAssignment(
            user_id=user_id,
            variant=variant,
            assigned_at=datetime.now(),
            test_id=test_id,
        )
        self._assignments[assignment_key] = assignment
        
        return variant
    
    def record_metric(
        self,
        test_id: str,
        user_id: str,
        metric_name: str,
        value: float,
    ) -> None:
        """Record metric observation."""
        assignment_key = f"{test_id}:{user_id}"
        assignment = self._assignments.get(assignment_key)
        
        if not assignment:
            logger.warning("Unknown user assignment", test_id=test_id, user_id=user_id)
            return
        
        observation = MetricObservation(
            test_id=test_id,
            user_id=user_id,
            variant=assignment.variant,
            metric_name=metric_name,
            value=value,
        )
        self._observations.append(observation)
    
    def get_results(self, test_id: str) -> dict[Variant, ABResult]:
        """Get results for each variant."""
        obs = [o for o in self._observations if o.test_id == test_id]
        
        results = {}
        for variant in [Variant.CONTROL, Variant.TREATMENT_A]:
            variant_obs = [o.value for o in obs if o.variant == variant]
            
            if variant_obs:
                mean, variance = self._analyzer.calculate_stats(variant_obs)
                ci = self._analyzer.confidence_interval(variant_obs)
                
                results[variant] = ABResult(
                    test_id=test_id,
                    variant=variant,
                    sample_size=len(variant_obs),
                    mean=mean,
                    variance=variance,
                    confidence_interval=ci,
                )
        
        return results
    
    def compare(self, test_id: str) -> ABComparison | None:
        """Compare variants."""
        results = self.get_results(test_id)
        
        if Variant.CONTROL not in results or Variant.TREATMENT_A not in results:
            return None
        
        control = results[Variant.CONTROL]
        treatment = results[Variant.TREATMENT_A]
        
        # Get observations for statistical test
        obs = [o for o in self._observations if o.test_id == test_id]
        control_values = [o.value for o in obs if o.variant == Variant.CONTROL]
        treatment_values = [o.value for o in obs if o.variant == Variant.TREATMENT_A]
        
        _, p_value = self._analyzer.two_sample_ttest(control_values, treatment_values)
        
        comparison = ABComparison(
            control=control,
            treatment=treatment,
            mean_diff=treatment.mean - control.mean,
            relative_diff=(treatment.mean - control.mean) / control.mean if control.mean != 0 else 0,
            p_value=p_value,
            statistically_significant=p_value < 0.05,
        )
        
        if comparison.statistically_significant:
            if treatment.mean > control.mean:
                comparison.winner = Variant.TREATMENT_A
            else:
                comparison.winner = Variant.CONTROL
        
        comparison.recommended_variant = comparison.winner
        comparison.confidence = 1.0 - p_value
        
        return comparison
    
    def is_significant(self, test_id: str) -> bool:
        """Check if test has reached significance."""
        comparison = self.compare(test_id)
        return comparison.statistically_significant if comparison else False
    
    def stop_test(self, test_id: str) -> None:
        """Stop A/B test."""
        if test_id in self._configs:
            del self._configs[test_id]
            logger.info("A/B test stopped", test_id=test_id)


# Global framework
_ab_framework: ABTestingFramework | None = None


def get_ab_testing_framework() -> ABTestingFramework:
    """Get global A/B testing framework."""
    global _ab_framework
    if _ab_framework is None:
        _ab_framework = ABTestingFramework()
    return _ab_framework


if __name__ == "__main__":
    framework = get_ab_testing_framework()
    
    # Create test
    config = ABConfig(
        test_id="test_001",
        name="New Debug UI vs Old",
        control_ratio=0.5,
        treatment_a_ratio=0.5,
        target_users=1000,
    )
    framework.create_test(config)
    
    # Simulate users
    for i in range(200):
        user_id = f"user_{i}"
        variant = framework.assign_user("test_001", user_id)
        
        # Record metrics
        accuracy = 0.7 + random.gauss(0.05, 0.1) if variant == Variant.TREATMENT_A else 0.65 + random.gauss(0.05, 0.1)
        framework.record_metric("test_001", user_id, "accuracy", accuracy)
    
    # Results
    results = framework.get_results("test_001")
    print("A/B Test Results")
    print("=" * 40)
    for variant, result in results.items():
        print(f"{variant.value}: {result.mean:.2%} (n={result.sample_size})")
    
    # Comparison
    comparison = framework.compare("test_001")
    if comparison:
        print(f"\nRelative improvement: {comparison.relative_diff:+.1%}")
        print(f"Statistically significant: {comparison.statistically_significant}")
        print(f"Recommended: {comparison.recommended_variant.value if comparison.recommended_variant else 'N/A'}")
