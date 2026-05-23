"""Tests for evaluation framework."""

import pytest
from src.application.evaluation.evaluation_framework import (
    EvaluationFramework,
    EvaluationType,
    EvaluationResult,
)


class TestEvaluationFramework:
    def test_framework_creation(self):
        framework = EvaluationFramework()
        assert framework is not None

    def test_create_suite(self):
        framework = EvaluationFramework()
        suite = framework.create_suite("Test Suite")
        
        assert suite.name == "Test Suite"
        assert suite.suite_id is not None

    def test_record_result(self):
        framework = EvaluationFramework()
        
        result = EvaluationResult(
            evaluation_id="eval_001",
            evaluation_type=EvaluationType.RAG_BASELINE,
            timestamp=None,
            accuracy=0.85,
            latency_ms=500,
            total_queries=100,
            successful_queries=85,
        )
        
        framework.record_result(result)
        
        summary = framework.get_summary(EvaluationType.RAG_BASELINE)
        assert summary["total_evaluations"] == 1

    def test_get_summary(self):
        framework = EvaluationFramework()
        
        result = EvaluationResult(
            evaluation_id="eval_001",
            evaluation_type=EvaluationType.BASELINE,
            timestamp=None,
            accuracy=0.75,
            latency_ms=300,
            total_queries=50,
            successful_queries=38,
        )
        framework.record_result(result)
        
        summary = framework.get_summary()
        assert summary["total_evaluations"] == 1
        assert "avg_accuracy" in summary

    def test_compare(self):
        framework = EvaluationFramework()
        
        baseline = EvaluationResult(
            evaluation_id="base_001",
            evaluation_type=EvaluationType.BASELINE,
            timestamp=None,
            accuracy=0.70,
            latency_ms=400,
            total_queries=100,
            successful_queries=70,
        )
        
        candidate = EvaluationResult(
            evaluation_id="cand_001",
            evaluation_type=EvaluationType.FINE_TUNED,
            timestamp=None,
            accuracy=0.80,
            latency_ms=350,
            total_queries=100,
            successful_queries=80,
        )
        
        framework.record_result(baseline)
        framework.record_result(candidate)
        
        comparison = framework.compare(EvaluationType.BASELINE, EvaluationType.FINE_TUNED)
        assert comparison is not None
        assert abs(comparison.accuracy_diff - 0.10) < 0.001
