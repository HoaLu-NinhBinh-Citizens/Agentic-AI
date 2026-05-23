"""Flaky test detector (Phase 7.7).

Detects and analyzes flaky tests in firmware test suites:
- Retry logic with statistical analysis
- Pattern detection for flaky behavior
- Root cause classification
- Fleet-wide flaky test tracking

Tier 1 value component.
"""

from __future__ import annotations

import hashlib
import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class FlakyPattern(Enum):
    """Types of flaky test patterns."""
    TIMING_SENSITIVE = "timing_sensitive"      # Race conditions, timeouts
    RESOURCE_CONTENTION = "resource_contention"  # Shared resources, memory
    EXTERNAL_DEPENDENCY = "external_dependency"  # Network, hardware
    INTERMITTENT_HARDWARE = "intermittent_hardware"  # Hardware instability
    RANDOM_BEHAVIOR = "random_behavior"        # Non-deterministic
    ENVIRONMENTAL = "environmental"            # Environment differences
    UNKNOWN = "unknown"


class TestResult(Enum):
    """Test execution result."""
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIP = "skip"


@dataclass
class TestRun:
    """Single test execution."""
    test_id: str
    result: TestResult
    duration_ms: float
    timestamp: datetime
    board_id: str = ""
    firmware_version: str = ""
    error_message: str = ""
    retry_count: int = 0


@dataclass
class FlakyTestResult:
    """Analysis result for a flaky test."""
    test_id: str
    test_name: str
    
    # Statistics
    total_runs: int = 0
    pass_count: int = 0
    fail_count: int = 0
    pass_rate: float = 0.0
    
    # Pattern analysis
    pattern: FlakyPattern = FlakyPattern.UNKNOWN
    confidence: float = 0.0  # 0.0 - 1.0
    suspected_causes: list[str] = field(default_factory=list)
    
    # Timing analysis
    avg_duration_ms: float = 0.0
    std_dev_ms: float = 0.0
    is_timing_sensitive: bool = False
    
    # Recommendations
    recommendations: list[str] = field(default_factory=list)
    
    # Metadata
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    affected_boards: list[str] = field(default_factory=list)
    affected_firmware_versions: list[str] = field(default_factory=list)


class FlakyTestDetector:
    """Detect flaky tests using statistical analysis.
    
    Phase 7.7: Flaky test detector
    
    Requirements:
    - Run test ≥3 times before committing generated test
    - Track flaky patterns across fleet
    - Classify root causes
    """
    
    # Thresholds for flaky detection
    MIN_RUNS_FOR_ANALYSIS = 3
    FLaky_THRESHOLD = 0.95  # Pass rate below this = flaky
    
    # Timing sensitivity thresholds
    TIMING_SENSITIVE_CV = 0.3  # Coefficient of variation
    
    def __init__(self) -> None:
        self._test_runs: dict[str, list[TestRun]] = {}
        self._flaky_tests: dict[str, FlakyTestResult] = {}
    
    def record_run(self, run: TestRun) -> None:
        """Record a test execution."""
        if run.test_id not in self._test_runs:
            self._test_runs[run.test_id] = []
        
        self._test_runs[run.test_id].append(run)
        
        # Check if flaky after each run
        if len(self._test_runs[run.test_id]) >= self.MIN_RUNS_FOR_ANALYSIS:
            self._analyze_test(run.test_id)
    
    def record_result(
        self,
        test_id: str,
        result: TestResult,
        duration_ms: float,
        board_id: str = "",
        error_message: str = "",
    ) -> FlakyTestResult | None:
        """Convenience method to record a result."""
        run = TestRun(
            test_id=test_id,
            result=result,
            duration_ms=duration_ms,
            timestamp=datetime.now(),
            board_id=board_id,
            error_message=error_message,
        )
        self.record_run(run)
        return self._flaky_tests.get(test_id)
    
    def _analyze_test(self, test_id: str) -> FlakyTestResult | None:
        """Analyze test runs for flakiness."""
        runs = self._test_runs.get(test_id, [])
        if len(runs) < self.MIN_RUNS_FOR_ANALYSIS:
            return None
        
        # Calculate statistics
        total = len(runs)
        passes = sum(1 for r in runs if r.result == TestResult.PASS)
        pass_rate = passes / total if total > 0 else 0.0
        
        # Timing analysis
        durations = [r.duration_ms for r in runs if r.duration_ms > 0]
        avg_duration = statistics.mean(durations) if durations else 0.0
        std_dev = statistics.stdev(durations) if len(durations) > 1 else 0.0
        cv = std_dev / avg_duration if avg_duration > 0 else 0.0  # Coefficient of variation
        
        # Determine if flaky
        is_flaky = pass_rate < self.FLAKy_THRESHOLD and passes > 0 and passes < total
        
        if is_flaky:
            # Analyze pattern
            pattern, causes, recommendations = self._analyze_pattern(runs, cv)
            
            result = FlakyTestResult(
                test_id=test_id,
                test_name=test_id,  # Could be enhanced with actual name
                total_runs=total,
                pass_count=passes,
                fail_count=total - passes,
                pass_rate=pass_rate,
                pattern=pattern,
                confidence=min(1.0, (1.0 - pass_rate) * 2),  # Higher confidence for more flaky
                suspected_causes=causes,
                avg_duration_ms=avg_duration,
                std_dev_ms=std_dev,
                is_timing_sensitive=cv > self.TIMING_SENSITIVE_CV,
                recommendations=recommendations,
                first_seen=min(r.timestamp for r in runs),
                last_seen=max(r.timestamp for r in runs),
                affected_boards=list(set(r.board_id for r in runs if r.board_id)),
                affected_firmware_versions=list(set(r.firmware_version for r in runs if r.firmware_version)),
            )
            
            self._flaky_tests[test_id] = result
            return result
        
        return None
    
    def _analyze_pattern(
        self,
        runs: list[TestRun],
        timing_cv: float,
    ) -> tuple[FlakyPattern, list[str], list[str]]:
        """Analyze test runs to determine flaky pattern."""
        causes = []
        recommendations = []
        
        # Check for timing sensitivity
        if timing_cv > self.TIMING_SENSITIVE_CV:
            pattern = FlakyPattern.TIMING_SENSITIVE
            causes.append("High timing variation detected (CV > 30%)")
            recommendations.append("Add retry logic with exponential backoff")
            recommendations.append("Increase test timeout value")
            recommendations.append("Check for resource contention")
        
        # Check for resource contention
        error_keywords = ["lock", "mutex", "semaphore", "contention", "busy"]
        if any(kw in r.error_message.lower() for r in runs for kw in error_keywords):
            pattern = FlakyPattern.RESOURCE_CONTENTION
            causes.append("Resource contention detected")
            recommendations.append("Add timeout to lock acquisitions")
            recommendations.append("Consider test isolation")
        
        # Check for external dependencies
        ext_keywords = ["network", "http", "dns", "timeout", "connection"]
        if any(kw in r.error_message.lower() for r in runs for kw in ext_keywords):
            pattern = FlakyPattern.EXTERNAL_DEPENDENCY
            causes.append("External dependency failure detected")
            recommendations.append("Mock external services in tests")
            recommendations.append("Add circuit breaker for external calls")
        
        # Check for hardware issues
        hw_keywords = ["hardware", "probe", "jtag", "swd", "board", "usb"]
        if any(kw in r.error_message.lower() for r in runs for kw in hw_keywords):
            pattern = FlakyPattern.INTERMITTENT_HARDWARE
            causes.append("Hardware instability detected")
            recommendations.append("Check probe connections")
            recommendations.append("Run hardware diagnostics")
            recommendations.append("Consider hardware pool rotation")
        
        # Check for randomness
        if len(set(r.result for r in runs)) > 1:
            # Check if passes/fails are evenly distributed
            passes = sum(1 for r in runs if r.result == TestResult.PASS)
            if 0.3 < passes / len(runs) < 0.7:
                pattern = FlakyPattern.RANDOM_BEHAVIOR
                causes.append("Non-deterministic behavior detected")
                recommendations.append("Seed random number generators")
                recommendations.append("Review test for race conditions")
        
        # Default
        if not causes:
            pattern = FlakyPattern.UNKNOWN
            causes.append("Unknown flakiness pattern")
            recommendations.append("Increase retry count")
            recommendations.append("Collect more data points")
        
        return pattern, causes, recommendations
    
    def get_flaky_tests(self) -> list[FlakyTestResult]:
        """Get all detected flaky tests."""
        return list(self._flaky_tests.values())
    
    def get_flaky_test(self, test_id: str) -> FlakyTestResult | None:
        """Get flaky test analysis."""
        return self._flaky_tests.get(test_id)
    
    def is_flaky(self, test_id: str) -> bool:
        """Check if a test is currently flaky."""
        return test_id in self._flaky_tests
    
    def get_test_runs(self, test_id: str) -> list[TestRun]:
        """Get all runs for a test."""
        return self._test_runs.get(test_id, [])
    
    def get_statistics(self) -> dict[str, Any]:
        """Get flaky test statistics."""
        flaky_tests = self.get_flaky_tests()
        
        if not flaky_tests:
            return {
                "total_tests_tracked": len(self._test_runs),
                "flaky_count": 0,
                "flaky_rate": 0.0,
                "by_pattern": {},
            }
        
        by_pattern: dict[str, int] = {}
        for test in flaky_tests:
            pattern_name = test.pattern.value
            by_pattern[pattern_name] = by_pattern.get(pattern_name, 0) + 1
        
        return {
            "total_tests_tracked": len(self._test_runs),
            "flaky_count": len(flaky_tests),
            "flaky_rate": len(flaky_tests) / len(self._test_runs) if self._test_runs else 0.0,
            "by_pattern": by_pattern,
            "most_common_pattern": max(by_pattern.items(), key=lambda x: x[1])[0] if by_pattern else None,
            "affected_boards": len(set(b for t in flaky_tests for b in t.affected_boards)),
        }
    
    def export_for_review(self) -> list[dict[str, Any]]:
        """Export flaky tests for review."""
        results = []
        for test in self.get_flaky_tests():
            results.append({
                "test_id": test.test_id,
                "pass_rate": f"{test.pass_rate:.1%}",
                "pattern": test.pattern.value,
                "confidence": f"{test.confidence:.1%}",
                "causes": test.suspected_causes,
                "recommendations": test.recommendations,
                "runs": test.total_runs,
            })
        return results


class FlakyTestRetryHandler:
    """Handle retry logic for flaky tests."""
    
    def __init__(self, max_retries: int = 3) -> None:
        self._max_retries = max_retries
        self._retry_history: dict[str, list[bool]] = {}  # test_id -> [success per retry]
    
    def should_retry(self, test_id: str, attempt: int) -> bool:
        """Determine if test should be retried."""
        return attempt < self._max_retries
    
    def record_attempt(self, test_id: str, success: bool) -> None:
        """Record attempt result."""
        if test_id not in self._retry_history:
            self._retry_history[test_id] = []
        self._retry_history[test_id].append(success)
    
    def get_final_result(self, test_id: str) -> bool | None:
        """Get final result after retries."""
        attempts = self._retry_history.get(test_id, [])
        if not attempts:
            return None
        return any(attempts)  # Pass if any attempt passed
    
    def get_retry_stats(self, test_id: str) -> dict[str, Any]:
        """Get retry statistics for a test."""
        attempts = self._retry_history.get(test_id, [])
        if not attempts:
            return {"total_attempts": 0}
        
        passes = sum(1 for a in attempts if a)
        return {
            "total_attempts": len(attempts),
            "passes": passes,
            "failures": len(attempts) - passes,
            "pass_on_retry": passes > 0 and not attempts[0],
            "avg_retries_per_run": len(attempts) / max(1, len(set(attempts))),
        }


# Global singleton
_detector: FlakyTestDetector | None = None


def get_flaky_detector() -> FlakyTestDetector:
    """Get global flaky test detector."""
    global _detector
    if _detector is None:
        _detector = FlakyTestDetector()
    return _detector


# CLI for testing
if __name__ == "__main__":
    detector = FlakyTestDetector()
    
    # Simulate flaky test
    print("Simulating flaky test behavior:")
    print("-" * 50)
    
    # Test 1: Flaky due to timing
    for i in range(5):
        # Pass 80% of the time, fail 20%
        success = i % 5 != 0
        result = detector.record_result(
            test_id="test_timing_sensitive",
            result=TestResult.PASS if success else TestResult.FAIL,
            duration_ms=100 + (i * 10),  # Variable timing
            error_message="Timeout waiting for resource" if not success else "",
        )
    
    # Test 2: Consistent pass
    for i in range(3):
        detector.record_result(
            test_id="test_stable",
            result=TestResult.PASS,
            duration_ms=50,
        )
    
    # Check results
    print("\nFlaky Tests Detected:")
    stats = detector.get_statistics()
    print(f"  Total tests: {stats['total_tests_tracked']}")
    print(f"  Flaky count: {stats['flaky_count']}")
    print(f"  Flaky rate: {stats['flaky_rate']:.1%}")
    
    if stats['flaky_count'] > 0:
        for test in detector.get_flaky_tests():
            print(f"\n  {test.test_id}:")
            print(f"    Pass rate: {test.pass_rate:.1%}")
            print(f"    Pattern: {test.pattern.value}")
            print(f"    Confidence: {test.confidence:.1%}")
            print(f"    Causes: {test.suspected_causes[:2]}")
            print(f"    Recommendations: {test.recommendations[:2]}")
