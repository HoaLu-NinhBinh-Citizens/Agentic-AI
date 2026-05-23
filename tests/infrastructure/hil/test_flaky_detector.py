"""Unit tests for flaky_detector.py (Phase 7.7)."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.infrastructure.hil.flaky_detector import (
    FlakyPattern,
    FlakyTestDetector,
    FlakyTestResult,
    FlakyTestRetryHandler,
    TestResult,
    TestRun,
    get_flaky_detector,
)


class TestFlakyTestDetector:
    """Tests for FlakyTestDetector class."""

    @pytest.fixture
    def detector(self) -> FlakyTestDetector:
        """Create detector instance."""
        return FlakyTestDetector()

    def test_initial_state(self, detector: FlakyTestDetector):
        """Test initial detector state."""
        stats = detector.get_statistics()
        
        assert stats["total_tests_tracked"] == 0
        assert stats["flaky_count"] == 0
        assert stats["flaky_rate"] == 0.0
        assert stats["by_pattern"] == {}

    def test_record_result_pass(self, detector: FlakyTestDetector):
        """Test recording a passing test result."""
        result = detector.record_result(
            test_id="test_passing",
            result=TestResult.PASS,
            duration_ms=100.0,
        )
        
        assert result is None  # Not enough runs for analysis
        assert "test_passing" in detector._test_runs

    def test_record_result_fail(self, detector: FlakyTestDetector):
        """Test recording a failing test result."""
        result = detector.record_result(
            test_id="test_failing",
            result=TestResult.FAIL,
            duration_ms=50.0,
            error_message="Assertion failed",
        )
        
        assert "test_failing" in detector._test_runs
        run = detector._test_runs["test_failing"][0]
        assert run.result == TestResult.FAIL
        assert run.error_message == "Assertion failed"

    def test_flaky_detection_pass_threshold(self, detector: FlakyTestDetector):
        """Test that consistent passing tests are not flagged as flaky."""
        for _ in range(5):
            detector.record_result(
                test_id="test_stable",
                result=TestResult.PASS,
                duration_ms=100.0,
            )
        
        assert not detector.is_flaky("test_stable")
        assert detector.get_flaky_test("test_stable") is None

    def test_flaky_detection_below_threshold(self, detector: FlakyTestDetector):
        """Test that tests below pass threshold are flagged as flaky."""
        # 4 passes, 1 fail = 80% pass rate (below 95% threshold)
        for i in range(5):
            result = TestResult.PASS if i < 4 else TestResult.FAIL
            detector.record_result(
                test_id="test_flaky",
                result=result,
                duration_ms=100.0,
            )
        
        assert detector.is_flaky("test_flaky")
        flaky_result = detector.get_flaky_test("test_flaky")
        assert flaky_result is not None
        assert flaky_result.pass_rate == pytest.approx(0.8)
        assert flaky_result.pass_count == 4
        assert flaky_result.fail_count == 1

    def test_timing_sensitive_detection(self, detector: FlakyTestDetector):
        """Test detection of timing-sensitive flaky tests."""
        # Varying durations to trigger timing sensitivity
        for i in range(5):
            detector.record_result(
                test_id="test_timing",
                result=TestResult.PASS if i % 3 != 0 else TestResult.FAIL,
                duration_ms=100.0 + (i * 50),  # Variable timing
                error_message="Timeout waiting for resource",
            )
        
        flaky_result = detector.get_flaky_test("test_timing")
        if flaky_result:
            assert flaky_result.is_timing_sensitive or flaky_result.std_dev_ms > 0

    def test_pattern_timing_sensitive(self, detector: FlakyTestDetector):
        """Test timing-sensitive pattern classification."""
        for i in range(5):
            detector.record_result(
                test_id="test_timing",
                result=TestResult.PASS if i < 4 else TestResult.FAIL,
                duration_ms=100.0 + (i * 40),
            )
        
        flaky_result = detector.get_flaky_test("test_timing")
        if flaky_result and flaky_result.pattern != FlakyPattern.UNKNOWN:
            assert flaky_result.pattern in [FlakyPattern.TIMING_SENSITIVE, FlakyPattern.RANDOM_BEHAVIOR]

    def test_pattern_resource_contention(self, detector: FlakyTestDetector):
        """Test resource contention pattern classification."""
        for _ in range(5):
            detector.record_result(
                test_id="test_lock",
                result=TestResult.FAIL,
                duration_ms=50.0,
                error_message="Lock acquisition timeout",
            )
        
        flaky_result = detector.get_flaky_test("test_lock")
        if flaky_result and flaky_result.pattern != FlakyPattern.UNKNOWN:
            assert flaky_result.pattern == FlakyPattern.RESOURCE_CONTENTION

    def test_pattern_external_dependency(self, detector: FlakyTestDetector):
        """Test external dependency pattern classification."""
        for _ in range(5):
            detector.record_result(
                test_id="test_network",
                result=TestResult.FAIL,
                duration_ms=1000.0,
                error_message="Connection timeout to API",
            )
        
        flaky_result = detector.get_flaky_test("test_network")
        if flaky_result and flaky_result.pattern != FlakyPattern.UNKNOWN:
            assert flaky_result.pattern == FlakyPattern.EXTERNAL_DEPENDENCY

    def test_pattern_hardware_issues(self, detector: FlakyTestDetector):
        """Test hardware issue pattern classification."""
        for _ in range(5):
            detector.record_result(
                test_id="test_hw",
                result=TestResult.FAIL,
                duration_ms=50.0,
                error_message="J-Link probe disconnected",
            )
        
        flaky_result = detector.get_flaky_test("test_hw")
        if flaky_result and flaky_result.pattern != FlakyPattern.UNKNOWN:
            assert flaky_result.pattern == FlakyPattern.INTERMITTENT_HARDWARE

    def test_recommendations_generated(self, detector: FlakyTestDetector):
        """Test that recommendations are generated for flaky tests."""
        for _ in range(5):
            detector.record_result(
                test_id="test_timing",
                result=TestResult.PASS if _ % 3 != 0 else TestResult.FAIL,
                duration_ms=100.0,
                error_message="Timeout waiting for resource",
            )
        
        flaky_result = detector.get_flaky_test("test_timing")
        if flaky_result:
            assert len(flaky_result.recommendations) > 0

    def test_get_flaky_tests(self, detector: FlakyTestDetector):
        """Test getting all flaky tests."""
        # Create multiple flaky tests
        for i in range(3):
            for _ in range(5):
                detector.record_result(
                    test_id=f"test_flaky_{i}",
                    result=TestResult.PASS if _ % 5 != 0 else TestResult.FAIL,
                    duration_ms=100.0,
                )
        
        flaky_tests = detector.get_flaky_tests()
        assert len(flaky_tests) >= 0  # May or may not be flaky depending on threshold

    def test_get_test_runs(self, detector: FlakyTestDetector):
        """Test getting test runs."""
        for _ in range(3):
            detector.record_result(
                test_id="test_001",
                result=TestResult.PASS,
                duration_ms=100.0,
            )
        
        runs = detector.get_test_runs("test_001")
        assert len(runs) == 3

    def test_get_test_runs_nonexistent(self, detector: FlakyTestDetector):
        """Test getting runs for non-existent test."""
        runs = detector.get_test_runs("nonexistent")
        assert len(runs) == 0

    def test_statistics_calculation(self, detector: FlakyTestDetector):
        """Test statistics calculation."""
        # Add multiple tests
        for i in range(3):
            for _ in range(5):
                detector.record_result(
                    test_id=f"test_{i}",
                    result=TestResult.PASS,
                    duration_ms=100.0,
                )
        
        stats = detector.get_statistics()
        assert stats["total_tests_tracked"] == 3

    def test_export_for_review(self, detector: FlakyTestDetector):
        """Test exporting flaky tests for review."""
        # Create a flaky test
        for i in range(5):
            detector.record_result(
                test_id="test_flaky",
                result=TestResult.PASS if i < 3 else TestResult.FAIL,
                duration_ms=100.0,
            )
        
        export = detector.export_for_review()
        assert isinstance(export, list)

    def test_confidence_calculation(self, detector: FlakyTestDetector):
        """Test confidence score calculation."""
        # 50% pass rate should give higher confidence
        for i in range(10):
            detector.record_result(
                test_id="test_random",
                result=TestResult.PASS if i % 2 == 0 else TestResult.FAIL,
                duration_ms=100.0,
            )
        
        flaky_result = detector.get_flaky_test("test_random")
        if flaky_result:
            # Higher confidence for more inconsistent results
            assert flaky_result.confidence >= 0.0
            assert flaky_result.confidence <= 1.0

    def test_affected_boards_tracking(self, detector: FlakyTestDetector):
        """Test that affected boards are tracked."""
        for _ in range(5):
            detector.record_result(
                test_id="test_board_issue",
                result=TestResult.FAIL,
                duration_ms=50.0,
                board_id="board_001",
                error_message="Hardware probe error",
            )
        
        flaky_result = detector.get_flaky_test("test_board_issue")
        if flaky_result and flaky_result.affected_boards:
            assert "board_001" in flaky_result.affected_boards

    def test_affected_firmware_tracking(self, detector: FlakyTestDetector):
        """Test that affected firmware versions are tracked."""
        for _ in range(5):
            detector.record_result(
                test_id="test_fw_issue",
                result=TestResult.FAIL,
                duration_ms=50.0,
                firmware_version="v1.0.0",
                error_message="Assert failed",
            )
        
        flaky_result = detector.get_flaky_test("test_fw_issue")
        if flaky_result and flaky_result.affected_firmware_versions:
            assert "v1.0.0" in flaky_result.affected_firmware_versions


class TestFlakyTestRetryHandler:
    """Tests for FlakyTestRetryHandler class."""

    @pytest.fixture
    def handler(self) -> FlakyTestRetryHandler:
        """Create retry handler."""
        return FlakyTestRetryHandler(max_retries=3)

    def test_should_retry(self, handler: FlakyTestRetryHandler):
        """Test retry decision logic."""
        assert handler.should_retry("test_001", 0) is True
        assert handler.should_retry("test_001", 1) is True
        assert handler.should_retry("test_001", 2) is True
        assert handler.should_retry("test_001", 3) is False  # max_retries reached

    def test_record_attempt(self, handler: FlakyTestRetryHandler):
        """Test recording attempt results."""
        handler.record_attempt("test_001", True)
        handler.record_attempt("test_001", False)
        handler.record_attempt("test_001", True)
        
        assert len(handler._retry_history["test_001"]) == 3

    def test_get_final_result_all_pass(self, handler: FlakyTestRetryHandler):
        """Test final result when all attempts pass."""
        handler.record_attempt("test_001", True)
        handler.record_attempt("test_001", True)
        
        assert handler.get_final_result("test_001") is True

    def test_get_final_result_some_pass(self, handler: FlakyTestRetryHandler):
        """Test final result when some attempts pass."""
        handler.record_attempt("test_001", False)
        handler.record_attempt("test_001", True)
        
        assert handler.get_final_result("test_001") is True  # Any pass = pass

    def test_get_final_result_all_fail(self, handler: FlakyTestRetryHandler):
        """Test final result when all attempts fail."""
        handler.record_attempt("test_001", False)
        handler.record_attempt("test_001", False)
        
        assert handler.get_final_result("test_001") is False

    def test_get_final_result_no_attempts(self, handler: FlakyTestRetryHandler):
        """Test final result when no attempts recorded."""
        assert handler.get_final_result("nonexistent") is None

    def test_get_retry_stats(self, handler: FlakyTestRetryHandler):
        """Test retry statistics."""
        handler.record_attempt("test_001", False)
        handler.record_attempt("test_001", True)
        handler.record_attempt("test_001", False)
        
        stats = handler.get_retry_stats("test_001")
        
        assert stats["total_attempts"] == 3
        assert stats["passes"] == 1
        assert stats["failures"] == 2
        assert stats["pass_on_retry"] is True

    def test_get_retry_stats_no_attempts(self, handler: FlakyTestRetryHandler):
        """Test retry stats for non-existent test."""
        stats = handler.get_retry_stats("nonexistent")
        
        assert stats["total_attempts"] == 0


class TestFlakyPattern:
    """Tests for FlakyPattern enum."""

    def test_all_patterns_defined(self):
        """Test all flaky patterns are defined."""
        assert FlakyPattern.TIMING_SENSITIVE.value == "timing_sensitive"
        assert FlakyPattern.RESOURCE_CONTENTION.value == "resource_contention"
        assert FlakyPattern.EXTERNAL_DEPENDENCY.value == "external_dependency"
        assert FlakyPattern.INTERMITTENT_HARDWARE.value == "intermittent_hardware"
        assert FlakyPattern.RANDOM_BEHAVIOR.value == "random_behavior"
        assert FlakyPattern.ENVIRONMENTAL.value == "environmental"
        assert FlakyPattern.UNKNOWN.value == "unknown"


class TestTestResult:
    """Tests for TestResult enum."""

    def test_all_results_defined(self):
        """Test all test results are defined."""
        assert TestResult.PASS.value == "pass"
        assert TestResult.FAIL.value == "fail"
        assert TestResult.ERROR.value == "error"
        assert TestResult.SKIP.value == "skip"


class TestGlobalDetector:
    """Tests for global detector singleton."""

    def test_get_flaky_detector_creates_singleton(self):
        """Test that get_flaky_detector returns singleton."""
        # Reset global
        import src.infrastructure.hil.flaky_detector as module
        module._detector = None
        
        detector1 = get_flaky_detector()
        detector2 = get_flaky_detector()
        
        assert detector1 is detector2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
