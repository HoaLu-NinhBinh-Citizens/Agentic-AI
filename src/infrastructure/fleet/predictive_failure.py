"""Predictive failure detection (Phase 14.4).

Predicts hardware failures before they occur:
- Anomaly trend analysis
- Pattern recognition
- Failure prediction models
- Alert generation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PredictionConfidence(Enum):
    """Prediction confidence levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class PredictionMetric:
    """Metric for prediction."""
    name: str
    current_value: float
    trend: float  # positive = increasing (bad for most metrics)
    variance: float
    
    @property
    def trend_direction(self) -> str:
        return "increasing" if self.trend > 0 else "decreasing"


@dataclass
class FailurePrediction:
    """Failure prediction."""
    prediction_id: str
    board_id: str
    
    # What will fail
    component: str
    failure_type: str  # memory_leak, thermal, mechanical, etc.
    
    # When
    predicted_time: datetime
    time_to_failure_hours: float
    
    # Confidence
    confidence: PredictionConfidence
    confidence_score: float  # 0.0 - 1.0
    
    # Evidence
    metrics: list[PredictionMetric]
    indicators: list[str]
    
    # Recommendation
    action: str = ""
    urgency: str = "medium"


class TrendAnalyzer:
    """Analyzes metric trends."""
    
    def analyze_trend(
        self,
        values: list[float],
        timestamps: list[datetime],
    ) -> PredictionMetric:
        """Analyze trend in values."""
        import statistics
        
        if len(values) < 2:
            return PredictionMetric(name="unknown", current_value=0, trend=0, variance=0)
        
        # Calculate trend (simple linear regression)
        n = len(values)
        current_value = values[-1]
        
        # Simple trend: difference from mean
        mean = statistics.mean(values)
        trend = (values[-1] - values[0]) / max(1, n - 1)
        
        variance = statistics.variance(values) if len(values) > 1 else 0
        
        return PredictionMetric(
            name="metric",
            current_value=current_value,
            trend=trend,
            variance=variance,
        )


class PatternRecognizer:
    """Recognizes failure patterns."""
    
    # Known failure patterns
    PATTERNS = {
        "memory_leak": {
            "metrics": ["memory_usage"],
            "condition": lambda m: m.trend > 0.1,
        },
        "thermal_drift": {
            "metrics": ["temperature"],
            "condition": lambda m: m.trend > 0.05,
        },
        "performance_degradation": {
            "metrics": ["response_time"],
            "condition": lambda m: m.trend > 0.2,
        },
        "hardware_wear": {
            "metrics": ["error_count"],
            "condition": lambda m: m.trend > 0.05,
        },
    }
    
    def recognize(self, metrics: list[PredictionMetric]) -> list[str]:
        """Recognize failure patterns."""
        patterns = []
        
        for pattern_name, pattern_def in self.PATTERNS.items():
            for metric in metrics:
                if metric.name in pattern_def["metrics"]:
                    if pattern_def["condition"](metric):
                        patterns.append(pattern_name)
        
        return patterns


class PredictiveAnalyzer:
    """Main predictive failure analyzer."""
    
    def __init__(self) -> None:
        self._predictions: list[FailurePrediction] = []
        self._trend_analyzer = TrendAnalyzer()
        self._pattern_recognizer = PatternRecognizer()
    
    def predict(
        self,
        board_id: str,
        metrics: list[PredictionMetric],
    ) -> list[FailurePrediction]:
        """Predict failures for a board."""
        predictions = []
        
        # Recognize patterns
        patterns = self._pattern_recognizer.recognize(metrics)
        
        for pattern in patterns:
            # Calculate time to failure
            time_to_failure = self._estimate_time_to_failure(metrics)
            
            # Calculate confidence
            confidence, score = self._calculate_confidence(metrics)
            
            prediction = FailurePrediction(
                prediction_id=f"pred_{board_id}_{pattern}_{datetime.now().timestamp()}",
                board_id=board_id,
                component=self._get_component(pattern),
                failure_type=pattern,
                predicted_time=datetime.now() + timedelta(hours=time_to_failure),
                time_to_failure_hours=time_to_failure,
                confidence=confidence,
                confidence_score=score,
                metrics=metrics,
                indicators=patterns,
                action=self._get_action(pattern),
            )
            
            predictions.append(prediction)
        
        self._predictions.extend(predictions)
        return predictions
    
    def _estimate_time_to_failure(self, metrics: list[PredictionMetric]) -> float:
        """Estimate time to failure in hours."""
        if not metrics:
            return 168.0  # 1 week default
        
        # Find metric with highest trend
        max_trend = max(m.trend for m in metrics)
        
        if max_trend <= 0:
            return 720.0  # 30 days
        
        # Simple estimation based on trend
        # Assume failure when metric reaches threshold
        threshold = 100.0
        current = max(m.current_value for m in metrics)
        
        if max_trend > 0:
            hours = (threshold - current) / max_trend if max_trend > 0 else 168
            return max(1, min(720, hours))
        
        return 168.0
    
    def _calculate_confidence(
        self,
        metrics: list[PredictionMetric],
    ) -> tuple[PredictionConfidence, float]:
        """Calculate prediction confidence."""
        if not metrics:
            return PredictionConfidence.LOW, 0.3
        
        # Check consistency (low variance = high confidence)
        avg_variance = sum(m.variance for m in metrics) / len(metrics)
        
        # Check trend strength
        avg_trend = sum(abs(m.trend) for m in metrics) / len(metrics)
        
        score = min(1.0, avg_trend * 10 + (1 - avg_variance / 100) * 0.3)
        
        if score > 0.7:
            return PredictionConfidence.HIGH, score
        elif score > 0.4:
            return PredictionConfidence.MEDIUM, score
        else:
            return PredictionConfidence.LOW, score
    
    def _get_component(self, pattern: str) -> str:
        """Get component at risk."""
        mapping = {
            "memory_leak": "memory",
            "thermal_drift": "thermal",
            "performance_degradation": "cpu",
            "hardware_wear": "hardware",
        }
        return mapping.get(pattern, "unknown")
    
    def _get_action(self, pattern: str) -> str:
        """Get recommended action."""
        mapping = {
            "memory_leak": "Schedule maintenance for memory inspection",
            "thermal_drift": "Check cooling system and ambient temperature",
            "performance_degradation": "Review recent firmware changes",
            "hardware_wear": "Order replacement board",
        }
        return mapping.get(pattern, "Monitor closely")


class PredictiveFailureEngine:
    """Main predictive failure engine.
    
    Phase 14.4: Predictive failure - Predict before it happens
    """
    
    def __init__(self) -> None:
        self._analyzer = PredictiveAnalyzer()
        self._predictions: list[FailurePrediction] = []
    
    def analyze(
        self,
        board_id: str,
        metric_data: dict[str, tuple[list[float], list[datetime]]],
    ) -> list[FailurePrediction]:
        """Analyze board for potential failures."""
        metrics = []
        
        for name, (values, timestamps) in metric_data.items():
            metric = self._analyzer._trend_analyzer.analyze_trend(values, timestamps)
            metric.name = name
            metrics.append(metric)
        
        predictions = self._analyzer.predict(board_id, metrics)
        self._predictions.extend(predictions)
        
        logger.info("Predictions generated", board_id=board_id, count=len(predictions))
        return predictions
    
    def get_predictions(
        self,
        board_id: str | None = None,
        min_confidence: float = 0.0,
    ) -> list[FailurePrediction]:
        """Get current predictions."""
        predictions = self._predictions
        
        if board_id:
            predictions = [p for p in predictions if p.board_id == board_id]
        
        predictions = [p for p in predictions if p.confidence_score >= min_confidence]
        
        return sorted(predictions, key=lambda p: p.time_to_failure_hours)
    
    def get_critical_predictions(self) -> list[FailurePrediction]:
        """Get predictions requiring immediate attention."""
        predictions = self.get_predictions(min_confidence=0.6)
        return [p for p in predictions if p.time_to_failure_hours < 24]


# Global engine
_predictive_engine: PredictiveFailureEngine | None = None


def get_predictive_engine() -> PredictiveFailureEngine:
    """Get global predictive engine."""
    global _predictive_engine
    if _predictive_engine is None:
        _predictive_engine = PredictiveFailureEngine()
    return _predictive_engine


if __name__ == "__main__":
    engine = get_predictive_engine()
    
    # Simulate metric data
    import random
    from datetime import timedelta
    
    metric_data = {
        "memory_usage": (
            [60 + i * 0.5 + random.gauss(0, 2) for i in range(100)],
            [datetime.now() - timedelta(hours=100-i) for i in range(100)],
        ),
        "temperature": (
            [50 + i * 0.1 + random.gauss(0, 1) for i in range(100)],
            [datetime.now() - timedelta(hours=100-i) for i in range(100)],
        ),
    }
    
    predictions = engine.analyze("board_001", metric_data)
    
    print("Predictive Failure Analysis")
    print("=" * 40)
    print(f"Predictions: {len(predictions)}")
    
    for pred in predictions:
        print(f"\n[{pred.confidence.value.upper()}] {pred.failure_type}")
        print(f"  Component: {pred.component}")
        print(f"  Time to failure: {pred.time_to_failure_hours:.1f} hours")
        print(f"  Action: {pred.action}")
