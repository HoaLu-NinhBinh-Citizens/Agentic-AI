"""QA Dashboard for test coverage and quality metrics (Phase 14.6).

Provides unified view of test quality metrics:
- Coverage tracking
- Flaky test monitoring
- Success rate trends
- Board utilization
- Regression detection
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MetricTrend(Enum):
    """Trend direction for metrics."""
    UP = "up"
    DOWN = "down"
    STABLE = "stable"


@dataclass
class CoverageMetrics:
    """Test coverage metrics."""
    line_coverage: float = 0.0
    branch_coverage: float = 0.0
    function_coverage: float = 0.0
    total_lines: int = 0
    covered_lines: int = 0
    total_branches: int = 0
    covered_branches: int = 0
    uncovered_lines: list[str] = field(default_factory=list)


@dataclass
class TestMetrics:
    """Test execution metrics."""
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    flaky: int = 0
    
    @property
    def pass_rate(self) -> float:
        total = self.passed + self.failed
        return self.passed / total if total > 0 else 0.0
    
    @property
    def success_rate(self) -> float:
        total = self.total_tests - self.skipped
        return self.passed / total if total > 0 else 0.0


@dataclass
class BoardMetrics:
    """Board utilization metrics."""
    total_boards: int = 0
    available: int = 0
    in_use: int = 0
    maintenance: int = 0
    error: int = 0
    utilization_rate: float = 0.0
    avg_test_duration_minutes: float = 0.0


@dataclass
class TrendData:
    """Trend data point."""
    timestamp: datetime
    value: float


@dataclass
class DashboardSnapshot:
    """Complete dashboard snapshot."""
    timestamp: datetime
    
    # Coverage
    coverage: CoverageMetrics = field(default_factory=CoverageMetrics)
    
    # Tests
    test_metrics: TestMetrics = field(default_factory=TestMetrics)
    flaky_test_count: int = 0
    
    # Boards
    board_metrics: BoardMetrics = field(default_factory=BoardMetrics)
    
    # Trends (last 7 days)
    pass_rate_trend: list[TrendData] = field(default_factory=list)
    coverage_trend: list[TrendData] = field(default_factory=list)
    flaky_test_trend: list[TrendData] = field(default_factory=list)
    
    # Alerts
    critical_alerts: int = 0
    recent_failures: list[str] = field(default_factory=list)
    regression_detected: bool = False
    
    @property
    def overall_health_score(self) -> float:
        """Calculate overall health score (0-100)."""
        coverage_score = self.coverage.line_coverage * 30  # 30% weight
        success_score = self.test_metrics.success_rate * 40  # 40% weight
        flaky_penalty = (self.flaky_test_count / max(1, self.test_metrics.total_tests)) * 20  # Up to 20% penalty
        board_score = self.board_metrics.utilization_rate * 10  # 10% weight
        
        return coverage_score + success_score + board_score - flaky_penalty


class QADashboard:
    """QA Dashboard aggregating metrics from multiple sources.
    
    Phase 14.6: QA dashboard
    """
    
    def __init__(self) -> None:
        self._snapshots: list[DashboardSnapshot] = []
        self._test_results: list[TestMetrics] = []
        self._coverage_results: list[CoverageMetrics] = []
        self._flaky_tests: dict[str, int] = {}  # test_id -> failure_count
    
    def record_test_results(self, metrics: TestMetrics) -> None:
        """Record test execution metrics."""
        self._test_results.append(metrics)
        self._test_results = self._test_results[-100:]  # Keep last 100
    
    def record_coverage(self, coverage: CoverageMetrics) -> None:
        """Record coverage metrics."""
        self._coverage_results.append(coverage)
        self._coverage_results = self._coverage_results[-100:]  # Keep last 100
    
    def record_flaky_test(self, test_id: str) -> None:
        """Record flaky test occurrence."""
        self._flaky_tests[test_id] = self._flaky_tests.get(test_id, 0) + 1
    
    def get_snapshot(self) -> DashboardSnapshot:
        """Get current dashboard snapshot."""
        # Aggregate test metrics
        test_metrics = TestMetrics()
        for m in self._test_results[-100:]:
            test_metrics.total_tests += m.total_tests
            test_metrics.passed += m.passed
            test_metrics.failed += m.failed
            test_metrics.skipped += m.skipped
        
        # Latest coverage
        coverage = self._coverage_results[-1] if self._coverage_results else CoverageMetrics()
        
        # Flaky test count
        flaky_count = len([t for t, c in self._flaky_tests.items() if c >= 3])
        
        # Trends
        pass_rate_trend = self._calculate_trend(
            [(m.timestamp, m.pass_rate) for m in self._test_results[-7:]]
        )
        coverage_trend = self._calculate_trend(
            [(m.timestamp, m.line_coverage) for m in self._coverage_results[-7:]]
        )
        
        snapshot = DashboardSnapshot(
            timestamp=datetime.now(),
            coverage=coverage,
            test_metrics=test_metrics,
            flaky_test_count=flaky_count,
            pass_rate_trend=pass_rate_trend,
            coverage_trend=coverage_trend,
            flaky_test_trend=self._calculate_flaky_trend(),
        )
        
        self._snapshots.append(snapshot)
        self._snapshots = self._snapshots[-30:]  # Keep last 30
        
        return snapshot
    
    def _calculate_trend(self, data: list[tuple[datetime, float]]) -> list[TrendData]:
        """Calculate trend from data points."""
        return [
            TrendData(timestamp=ts, value=val)
            for ts, val in data
        ]
    
    def _calculate_flaky_trend(self) -> list[TrendData]:
        """Calculate flaky test trend."""
        now = datetime.now()
        return [
            TrendData(
                timestamp=now - timedelta(days=i),
                value=len([t for t, c in self._flaky_tests.items() if c >= i])
            )
            for i in range(7, 0, -1)
        ]
    
    def get_trend_direction(self, metric: str) -> MetricTrend:
        """Get trend direction for a metric."""
        if len(self._snapshots) < 2:
            return MetricTrend.STABLE
        
        recent = self._snapshots[-1]
        previous = self._snapshots[-2]
        
        if metric == "pass_rate":
            diff = recent.test_metrics.pass_rate - previous.test_metrics.pass_rate
        elif metric == "coverage":
            diff = recent.coverage.line_coverage - previous.coverage.line_coverage
        elif metric == "flaky":
            diff = previous.flaky_test_count - recent.flaky_test_count  # Lower is better
        else:
            return MetricTrend.STABLE
        
        if abs(diff) < 0.01:
            return MetricTrend.STABLE
        return MetricTrend.UP if diff > 0 else MetricTrend.DOWN
    
    def detect_regressions(self) -> list[str]:
        """Detect test regressions."""
        regressions = []
        
        if len(self._test_results) < 2:
            return regressions
        
        recent = self._test_results[-1]
        previous = self._test_results[-2]
        
        # Check if pass rate dropped
        if recent.pass_rate < previous.pass_rate - 0.1:
            regressions.append(
                f"Pass rate dropped: {previous.pass_rate:.1%} -> {recent.pass_rate:.1%}"
            )
        
        # Check for new failures
        if recent.failed > previous.failed:
            regressions.append(
                f"New failures: +{recent.failed - previous.failed}"
            )
        
        return regressions
    
    def get_uncovered_areas(self) -> list[str]:
        """Get areas with low coverage."""
        if not self._coverage_results:
            return []
        
        latest = self._coverage_results[-1]
        return latest.uncovered_lines[-20:]  # Top 20 uncovered areas
    
    def get_top_flaky_tests(self, limit: int = 10) -> list[tuple[str, int]]:
        """Get most flaky tests."""
        sorted_tests = sorted(
            self._flaky_tests.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        return sorted_tests[:limit]
    
    def get_success_rate_by_module(self) -> dict[str, float]:
        """Calculate success rate by module (simulated)."""
        # This would integrate with actual test results
        return {
            "core": 0.95,
            "drivers": 0.88,
            "middleware": 0.92,
            "tests": 0.78,
        }
    
    def export_dashboard_data(self) -> dict[str, Any]:
        """Export dashboard data for visualization."""
        snapshot = self.get_snapshot()
        
        return {
            "timestamp": snapshot.timestamp.isoformat(),
            "health_score": snapshot.overall_health_score,
            "coverage": {
                "line": snapshot.coverage.line_coverage,
                "branch": snapshot.coverage.branch_coverage,
                "function": snapshot.coverage.function_coverage,
            },
            "tests": {
                "total": snapshot.test_metrics.total_tests,
                "passed": snapshot.test_metrics.passed,
                "failed": snapshot.test_metrics.failed,
                "skipped": snapshot.test_metrics.skipped,
                "pass_rate": snapshot.test_metrics.pass_rate,
            },
            "flaky_tests": snapshot.flaky_test_count,
            "boards": {
                "total": snapshot.board_metrics.total_boards,
                "available": snapshot.board_metrics.available,
                "utilization": snapshot.board_metrics.utilization_rate,
            },
            "trends": {
                "pass_rate": [(t.timestamp.isoformat(), t.value) for t in snapshot.pass_rate_trend],
                "coverage": [(t.timestamp.isoformat(), t.value) for t in snapshot.coverage_trend],
            },
            "alerts": {
                "critical": snapshot.critical_alerts,
                "regressions": snapshot.regression_detected,
            },
            "top_flaky": self.get_top_flaky_tests(5),
        }


# Global singleton
_dashboard: QADashboard | None = None


def get_qa_dashboard() -> QADashboard:
    """Get global QA dashboard."""
    global _dashboard
    if _dashboard is None:
        _dashboard = QADashboard()
    return _dashboard


if __name__ == "__main__":
    dashboard = get_qa_dashboard()
    
    # Simulate test results
    dashboard.record_test_results(TestMetrics(
        total_tests=100,
        passed=85,
        failed=10,
        skipped=5,
    ))
    
    dashboard.record_coverage(CoverageMetrics(
        line_coverage=0.78,
        branch_coverage=0.65,
        function_coverage=0.82,
    ))
    
    # Record flaky tests
    dashboard.record_flaky_test("test_uart_timeout")
    dashboard.record_flaky_test("test_uart_timeout")
    dashboard.record_flaky_test("test_gpio_interrupt")
    
    # Get snapshot
    snapshot = dashboard.get_snapshot()
    
    print("=" * 60)
    print("QA Dashboard Snapshot")
    print("=" * 60)
    print(f"Health Score: {snapshot.overall_health_score:.1f}/100")
    print()
    print("Coverage:")
    print(f"  Lines: {snapshot.coverage.line_coverage:.1%}")
    print(f"  Branch: {snapshot.coverage.branch_coverage:.1%}")
    print(f"  Functions: {snapshot.coverage.function_coverage:.1%}")
    print()
    print("Tests:")
    print(f"  Total: {snapshot.test_metrics.total_tests}")
    print(f"  Passed: {snapshot.test_metrics.passed}")
    print(f"  Failed: {snapshot.test_metrics.failed}")
    print(f"  Pass Rate: {snapshot.test_metrics.pass_rate:.1%}")
    print()
    print(f"Flaky Tests: {snapshot.flaky_test_count}")
    
    # Top flaky
    print("\nTop Flaky Tests:")
    for test, count in dashboard.get_top_flaky_tests():
        print(f"  {test}: {count} failures")
    
    # Export
    data = dashboard.export_dashboard_data()
    print(f"\nDashboard data exported: {len(data)} keys")
