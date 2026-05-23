"""Tests for predictive failure."""

import pytest
from src.infrastructure.fleet.predictive_failure import (
    PredictiveFailureEngine,
    PredictionConfidence,
)


class TestPredictiveFailureEngine:
    def test_engine_creation(self):
        engine = PredictiveFailureEngine()
        assert engine is not None

    def test_analyze_empty(self):
        engine = PredictiveFailureEngine()
        
        predictions = engine.analyze("board_001", {})
        # Should not raise

    def test_get_predictions(self):
        engine = PredictiveFailureEngine()
        
        predictions = engine.get_predictions()
        assert isinstance(predictions, list)

    def test_get_predictions_with_board_filter(self):
        engine = PredictiveFailureEngine()
        
        predictions = engine.get_predictions(board_id="board_001")
        assert isinstance(predictions, list)

    def test_get_critical_predictions(self):
        engine = PredictiveFailureEngine()
        
        critical = engine.get_critical_predictions()
        assert isinstance(critical, list)


class TestTrendAnalyzer:
    def test_trend_direction(self):
        from src.infrastructure.fleet.predictive_failure import TrendAnalyzer, PredictionMetric
        
        analyzer = TrendAnalyzer()
        
        # Test increasing trend
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        metric = analyzer.analyze_trend(values, [])
        assert metric.trend_direction == "increasing"
