"""
Unit Tests for Phase 4: Introspection, Health, Healing, Metrics
"""

import asyncio
from datetime import datetime, timedelta

import pytest

from src.introspection.introspector import (
    Introspector,
    BehaviorReport,
    BehaviorMetrics,
    AgentPerformance,
)
from src.introspection.anomalies import (
    Anomaly,
    AnomalyType,
    Severity,
    AnomalyDetector,
)
from src.introspection.improvements import (
    Improvement,
    ImprovementCategory,
    Priority,
    ImprovementAnalyzer,
)
from src.health.health_check import (
    HealthCheck,
    HealthStatus,
    HealthCheckResult,
    HealthChecks,
)
from src.health.monitor import HealthMonitor, HealthReport
from src.healing.self_healer import (
    SelfHealer,
    RecoveryStrategy,
    RecoveryResult,
)
from src.metrics.collector import MetricsCollector, MetricPoint


# ============ Introspector Tests ============

class TestIntrospector:
    def test_introspector_creation(self):
        """Test introspector creation."""
        introspector = Introspector(agent_id="test-agent")
        assert introspector.agent_id == "test-agent"

    def test_record_task_start(self):
        """Test recording task start."""
        introspector = Introspector(agent_id="test-agent")
        introspector.record_task_start("task-1", {"type": "test"})

        assert "task-1" in introspector._task_history
        assert introspector._task_history["task-1"]["status"] == "running"

    def test_record_task_complete(self):
        """Test recording task completion."""
        introspector = Introspector(agent_id="test-agent")

        introspector.record_task_start("task-1")
        introspector.record_task_complete("task-1", success=True, duration_ms=1000)

        assert introspector._metrics.total_tasks == 1
        assert introspector._metrics.successful_tasks == 1

    def test_analyze_performance(self):
        """Test behavior analysis."""
        introspector = Introspector(agent_id="test-agent")

        # Record some tasks
        introspector.record_task_start("task-1")
        introspector.record_task_complete("task-1", success=True, duration_ms=100)

        introspector.record_task_start("task-2")
        introspector.record_task_complete("task-2", success=True, duration_ms=200)

        report = introspector.analyze()

        assert report.agent_id == "test-agent"
        assert report.metrics.total_tasks == 2
        assert report.metrics.successful_tasks == 2
        assert report.metrics.success_rate == 1.0


# ============ Anomaly Detector Tests ============

class TestAnomalyDetector:
    def test_detector_creation(self):
        """Test detector creation."""
        detector = AnomalyDetector()
        assert detector is not None

    def test_register_check(self):
        """Test registering checks."""
        detector = AnomalyDetector()

        def my_check():
            return 0.05

        detector.register_check("error_rate", my_check)
        assert "error_rate" in detector._checks

    def test_register_threshold(self):
        """Test registering thresholds."""
        detector = AnomalyDetector()
        detector.register_threshold("error_rate", max=0.1)

        assert "error_rate" in detector._thresholds
        assert detector._thresholds["error_rate"]["max"] == 0.1

    def test_detect_error_rate_anomaly(self):
        """Test error rate anomaly detection."""
        detector = AnomalyDetector()

        anomaly = detector.detect_error_rate_anomaly(
            error_count=15,
            total_requests=100,
            threshold=0.1,
        )

        assert anomaly is not None
        assert anomaly.type == AnomalyType.HIGH_ERROR_RATE
        assert anomaly.severity in [Severity.WARNING, Severity.ERROR, Severity.CRITICAL]

    def test_detect_no_anomaly_when_healthy(self):
        """Test no anomaly when within threshold."""
        detector = AnomalyDetector()

        anomaly = detector.detect_error_rate_anomaly(
            error_count=5,
            total_requests=100,
            threshold=0.1,
        )

        assert anomaly is None


# ============ Improvement Analyzer Tests ============

class TestImprovementAnalyzer:
    def test_analyzer_creation(self):
        """Test analyzer creation."""
        analyzer = ImprovementAnalyzer()
        assert analyzer is not None

    def test_analyze_errors(self):
        """Test error analysis."""
        analyzer = ImprovementAnalyzer()

        suggestions = analyzer.analyze(
            error_patterns=[{
                "error_type": "TimeoutError",
                "occurrence_count": 10,
            }],
            performance_metrics={},
            recent_tasks=[],
        )

        assert len(suggestions.improvements) >= 1

    def test_generate_summary(self):
        """Test summary generation."""
        analyzer = ImprovementAnalyzer()

        suggestions = analyzer.analyze(
            error_patterns=[],
            performance_metrics={},
            recent_tasks=[],
        )

        assert suggestions.summary is not None
        assert len(suggestions.summary) > 0


# ============ Health Check Tests ============

class TestHealthCheckResult:
    def test_result_creation(self):
        """Test health check result creation."""
        result = HealthCheckResult(
            check_name="test",
            status=HealthStatus.HEALTHY,
            message="All good",
        )

        assert result.check_name == "test"
        assert result.status == HealthStatus.HEALTHY
        assert result.is_healthy


class TestHealthChecks:
    def test_custom_check(self):
        """Test custom health check."""
        check = HealthChecks.custom_check(
            name="my_check",
            description="My custom check",
            check_func=lambda: True,
        )

        assert check.name == "my_check"
        result = check.execute()
        assert result.status == HealthStatus.HEALTHY


# ============ Health Monitor Tests ============

class TestHealthMonitor:
    def test_monitor_creation(self):
        """Test health monitor creation."""
        monitor = HealthMonitor()
        assert monitor is not None

    def test_register_check(self):
        """Test registering health checks."""
        monitor = HealthMonitor()

        check = HealthChecks.custom_check(
            name="test_check",
            description="Test",
            check_func=lambda: True,
        )

        monitor.register_check(check)
        assert "test_check" in monitor._checks

    def test_check(self):
        """Test running health checks."""
        monitor = HealthMonitor()

        check = HealthChecks.custom_check(
            name="healthy_check",
            description="Always healthy",
            check_func=lambda: True,
        )
        monitor.register_check(check)

        report = monitor.check()

        assert isinstance(report, HealthReport)
        assert "healthy_check" in report.checks

    def test_get_check_status(self):
        """Test getting check status."""
        monitor = HealthMonitor()

        check = HealthChecks.custom_check(
            name="status_check",
            description="Status check",
            check_func=lambda: True,
        )
        monitor.register_check(check)
        monitor.check()

        status = monitor.get_check_status("status_check")
        assert status == HealthStatus.HEALTHY


# ============ Self-Healer Tests ============

class TestSelfHealer:
    def test_healer_creation(self):
        """Test self-healer creation."""
        healer = SelfHealer()
        assert healer is not None

    def test_register_handler(self):
        """Test registering recovery handlers."""
        healer = SelfHealer()

        async def my_handler(failure):
            return True

        healer.register_handler(RecoveryStrategy.CLEAR_CACHE, my_handler)
        assert RecoveryStrategy.CLEAR_CACHE in healer._handlers

    def test_determine_strategies(self):
        """Test strategy determination."""
        healer = SelfHealer()

        strategies = healer._determine_strategies({"type": "llm_timeout"})
        assert len(strategies) > 0
        assert RecoveryStrategy.RETRY_WITH_BACKOFF in strategies

    def test_get_recovery_stats(self):
        """Test getting recovery statistics."""
        healer = SelfHealer()
        stats = healer.get_recovery_stats()

        assert "total_recoveries" in stats
        assert "successful_recoveries" in stats
        assert "success_rate" in stats


# ============ Metrics Collector Tests ============

class TestMetricsCollector:
    def test_collector_creation(self):
        """Test metrics collector creation."""
        collector = MetricsCollector()
        assert collector is not None

    def test_increment_counter(self):
        """Test incrementing counter."""
        collector = MetricsCollector()
        collector.increment("requests_total")
        collector.increment("requests_total")

        assert collector.get_counter("requests_total") == 2

    def test_gauge(self):
        """Test gauge metric."""
        collector = MetricsCollector()
        collector.gauge("memory_usage", 512.5)

        assert collector.get_gauge("memory_usage") == 512.5

    def test_histogram(self):
        """Test histogram metric."""
        collector = MetricsCollector()

        for i in range(10):
            collector.histogram("request_duration", float(i))

        stats = collector.get_histogram_stats("request_duration")
        assert stats["count"] == 10
        assert stats["mean"] == 4.5

    def test_timing(self):
        """Test timing metric."""
        collector = MetricsCollector()
        collector.timing("my_function", 150)

        stats = collector.get_histogram_stats("my_function_ms")
        assert stats["count"] == 1
        assert stats["sum"] == 150

    def test_get_all_metrics(self):
        """Test getting all metrics."""
        collector = MetricsCollector()
        collector.increment("counter_metric")
        collector.gauge("gauge_metric", 100)
        collector.histogram("histogram_metric", 50)

        metrics = collector.get_all_metrics()

        assert "counter_metric" in metrics
        assert "gauge_metric" in metrics
        assert "histogram_metric" in metrics

    def test_reset(self):
        """Test resetting metrics."""
        collector = MetricsCollector()
        collector.increment("test_counter")
        collector.gauge("test_gauge", 100)

        collector.reset()

        assert collector.get_counter("test_counter") == 0
        assert collector.get_gauge("test_gauge") is None


class TestMetricPoint:
    def test_point_creation(self):
        """Test metric point creation."""
        point = MetricPoint(name="test", value=42.0)
        assert point.name == "test"
        assert point.value == 42.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
