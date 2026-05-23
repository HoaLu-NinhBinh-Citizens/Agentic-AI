"""Benchmark suite for agent quality metrics (Phase 11.4).

Provides:
- MTTD (Mean Time To Detect) measurement
- MTTF (Mean Time To Fix) measurement
- Agent quality metrics
- Acceptance rate tracking
- False positive tracking
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class BenchmarkType(Enum):
    """Type of benchmark."""
    MTTD = "mttd"  # Mean Time To Detect
    MTTF = "mttf"  # Mean Time To Fix
    ACCURACY = "accuracy"
    FALSE_POSITIVE = "false_positive"
    LATENCY = "latency"


@dataclass
class BenchmarkResult:
    """Single benchmark result."""
    benchmark_type: BenchmarkType
    value: float
    unit: str
    timestamp: datetime = field(default_factory=datetime.now)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkSummary:
    """Benchmark summary statistics."""
    benchmark_type: BenchmarkType
    count: int = 0
    total: float = 0.0
    mean: float = 0.0
    min: float = 0.0
    max: float = 0.0
    std_dev: float = 0.0
    
    def update(self, value: float) -> None:
        """Update statistics with new value."""
        self.count += 1
        self.total += value
        
        if self.count == 1:
            self.min = value
            self.max = value
        else:
            self.min = min(self.min, value)
            self.max = max(self.max, value)
        
        self.mean = self.total / self.count


@dataclass
class AgentQualityMetrics:
    """Agent quality metrics."""
    total_sessions: int = 0
    successful_sessions: int = 0
    failed_sessions: int = 0
    acceptance_rate: float = 0.0  # User acceptance
    false_positive_rate: float = 0.0
    avg_detection_time_ms: float = 0.0  # MTTD
    avg_fix_time_ms: float = 0.0  # MTTF
    recommendations_made: int = 0
    recommendations_accepted: int = 0
    bugs_detected: int = 0
    bugs_confirmed: int = 0


class BenchmarkSuite:
    """Benchmark suite for AI_SUPPORT agent.
    
    Phase 11.4: Benchmark suite - MTTD, MTTF
    Phase 11.4b: Agent quality metrics
    """
    
    def __init__(self) -> None:
        self._results: list[BenchmarkResult] = []
        self._summaries: dict[BenchmarkType, BenchmarkSummary] = {
            t: BenchmarkSummary(benchmark_type=t)
            for t in BenchmarkType
        }
        self._quality = AgentQualityMetrics()
        self._session_timers: dict[str, float] = {}
    
    def start_session(self, session_id: str) -> None:
        """Start timing a session."""
        self._session_timers[session_id] = time.time()
        self._quality.total_sessions += 1
    
    def end_session(self, session_id: str, success: bool) -> None:
        """End session timing."""
        start = self._session_timers.pop(session_id, None)
        if start:
            duration_ms = (time.time() - start) * 1000
            self.record(BenchmarkType.LATENCY, duration_ms, "ms", {
                "session_id": session_id,
                "success": success,
            })
        
        if success:
            self._quality.successful_sessions += 1
        else:
            self._quality.failed_sessions += 1
        
        self._update_acceptance_rate()
    
    def record_detection(self, error_type: str, detection_time_ms: float) -> None:
        """Record error detection time (MTTD)."""
        self.record(
            BenchmarkType.MTTD,
            detection_time_ms,
            "ms",
            {"error_type": error_type}
        )
        self._quality.bugs_detected += 1
        self._update_detection_time(detection_time_ms)
    
    def record_fix(
        self,
        error_type: str,
        fix_time_ms: float,
        accepted: bool,
    ) -> None:
        """Record fix time (MTTF)."""
        self.record(
            BenchmarkType.MTTF,
            fix_time_ms,
            "ms",
            {"error_type": error_type, "accepted": accepted}
        )
        self._quality.recommendations_made += 1
        
        if accepted:
            self._quality.recommendations_accepted += 1
            self._quality.bugs_confirmed += 1
            self._update_fix_time(fix_time_ms)
    
    def record_false_positive(self, context: dict[str, Any] | None = None) -> None:
        """Record a false positive detection."""
        self.record(
            BenchmarkType.FALSE_POSITIVE,
            1.0,
            "count",
            context or {}
        )
    
    def record_accuracy(self, correct: bool, context: dict[str, Any] | None = None) -> None:
        """Record prediction accuracy."""
        value = 1.0 if correct else 0.0
        self.record(
            BenchmarkType.ACCURACY,
            value,
            "ratio",
            context or {}
        )
    
    def record(
        self,
        benchmark_type: BenchmarkType,
        value: float,
        unit: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Record a benchmark result."""
        result = BenchmarkResult(
            benchmark_type=benchmark_type,
            value=value,
            unit=unit,
            context=context or {},
        )
        
        self._results.append(result)
        self._summaries[benchmark_type].update(value)
    
    def _update_acceptance_rate(self) -> None:
        """Update acceptance rate calculation."""
        total = self._quality.successful_sessions + self._quality.failed_sessions
        if total > 0:
            self._quality.acceptance_rate = self._quality.successful_sessions / total
    
    def _update_detection_time(self, time_ms: float) -> None:
        """Update average detection time."""
        n = self._quality.bugs_detected
        if n == 1:
            self._quality.avg_detection_time_ms = time_ms
        else:
            self._quality.avg_detection_time_ms = (
                (self._quality.avg_detection_time_ms * (n - 1) + time_ms) / n
            )
    
    def _update_fix_time(self, time_ms: float) -> None:
        """Update average fix time."""
        n = self._quality.bugs_confirmed
        if n == 1:
            self._quality.avg_fix_time_ms = time_ms
        else:
            self._quality.avg_fix_time_ms = (
                (self._quality.avg_fix_time_ms * (n - 1) + time_ms) / n
            )
    
    def get_summary(self, benchmark_type: BenchmarkType) -> BenchmarkSummary:
        """Get summary for a benchmark type."""
        return self._summaries[benchmark_type]
    
    def get_quality_metrics(self) -> AgentQualityMetrics:
        """Get full quality metrics."""
        return self._quality
    
    def get_report(self) -> dict[str, Any]:
        """Generate benchmark report."""
        return {
            "generated_at": datetime.now().isoformat(),
            "quality_metrics": {
                "total_sessions": self._quality.total_sessions,
                "successful_sessions": self._quality.successful_sessions,
                "failed_sessions": self._quality.failed_sessions,
                "acceptance_rate": f"{self._quality.acceptance_rate:.1%}",
                "bugs_detected": self._quality.bugs_detected,
                "bugs_confirmed": self._quality.bugs_confirmed,
                "false_positive_rate": f"{self._quality.false_positive_rate:.1%}",
                "avg_detection_time_ms": f"{self._quality.avg_detection_time_ms:.1f}",
                "avg_fix_time_ms": f"{self._quality.avg_fix_time_ms:.1f}",
            },
            "benchmarks": {
                t.value: {
                    "count": s.count,
                    "mean": round(s.mean, 2),
                    "min": round(s.min, 2) if s.count > 0 else 0,
                    "max": round(s.max, 2) if s.count > 0 else 0,
                }
                for t, s in self._summaries.items()
                if s.count > 0
            },
        }
    
    def reset(self) -> None:
        """Reset all benchmarks."""
        self._results.clear()
        self._summaries = {
            t: BenchmarkSummary(benchmark_type=t)
            for t in BenchmarkType
        }
        self._quality = AgentQualityMetrics()
        self._session_timers.clear()


# Global singleton
_benchmark_suite: BenchmarkSuite | None = None


def get_benchmark_suite() -> BenchmarkSuite:
    """Get global benchmark suite instance."""
    global _benchmark_suite
    if _benchmark_suite is None:
        _benchmark_suite = BenchmarkSuite()
    return _benchmark_suite


# CLI for running benchmarks
if __name__ == "__main__":
    import sys
    
    suite = get_benchmark_suite()
    
    # Simulate some benchmarks
    print("Running simulated benchmarks...")
    
    suite.start_session("test-001")
    time.sleep(0.1)
    suite.end_session("test-001", success=True)
    
    suite.record_detection("HardFault", 150.0)
    suite.record_fix("HardFault", 500.0, accepted=True)
    
    suite.record_accuracy(True, {"task": "pattern_match"})
    suite.record_accuracy(False, {"task": "root_cause"})
    
    report = suite.get_report()
    
    print("\n" + "=" * 50)
    print("BENCHMARK REPORT")
    print("=" * 50)
    
    print("\nQuality Metrics:")
    for k, v in report["quality_metrics"].items():
        print(f"  {k}: {v}")
    
    print("\nBenchmarks:")
    for k, v in report["benchmarks"].items():
        print(f"  {k}: mean={v['mean']}, count={v['count']}")
