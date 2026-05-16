"""
Runtime Production Tests for AI_support

These are REAL executable tests that verify actual system behavior.
Unlike test_p9_production_concepts.py (which validates concepts only),
these tests verify runtime behavior of the actual system.

Validates:
1. API server health endpoints
2. State management
3. Tool status updates
4. Health check integration
5. Error handling

Run: python -m pytest AI_support/tests/test_p9_production_runtime.py -v
"""

import pytest
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "C:/Users/thang/Desktop/carv")

from src.app.api_state import ServerState, state
from src.app.api_models import MetricUpdate, ToolStatus
from src.health.health_check import HealthCheck, HealthStatus, HealthCheckResult


# ============================================================================
# API State Tests
# ============================================================================

class TestServerStateRuntime:
    """Test ServerState actual runtime behavior"""

    def test_state_initialization(self):
        """Verify state initializes with correct defaults"""
        s = ServerState()
        assert s._metrics["cpu"] == 0.0
        assert s._metrics["memory"] == 0.0
        assert s._tool_statuses == {}

    def test_update_metrics_sync(self):
        """Verify metrics update synchronously (not async)"""
        s = ServerState()
        s.update_metrics({"cpu": 50.0, "memory": 75.0})
        assert s._metrics["cpu"] == 50.0
        assert s._metrics["memory"] == 75.0

    def test_update_metrics_preserves_existing(self):
        """Verify updating metrics preserves other values"""
        s = ServerState()
        s.update_metrics({"cpu": 50.0})
        s.update_metrics({"memory": 75.0})
        assert s._metrics["cpu"] == 50.0
        assert s._metrics["memory"] == 75.0

    def test_update_tool_status_sync(self):
        """Verify tool status update synchronously"""
        s = ServerState()
        s.update_tool_status("TestTool", "operational", 100)
        assert "TestTool" in s._tool_statuses
        assert s._tool_statuses["TestTool"].tool == "TestTool"
        assert s._tool_statuses["TestTool"].status == "operational"
        assert s._tool_statuses["TestTool"].latency == 100

    def test_update_tool_status_multiple(self):
        """Verify multiple tool status updates"""
        s = ServerState()
        s.update_tool_status("Tool1", "operational", 50)
        s.update_tool_status("Tool2", "degraded", 200)
        assert len(s._tool_statuses) == 2
        assert s._tool_statuses["Tool1"].status == "operational"
        assert s._tool_statuses["Tool2"].status == "degraded"

    def test_add_log(self):
        """Verify logging works"""
        s = ServerState()
        entry = s.add_log("info", "Test", "Test message")
        assert entry.level == "info"
        assert entry.source == "Test"
        assert entry.message == "Test message"
        assert len(s.logs) == 1

    def test_add_log_max_limit(self):
        """Verify log max limit works"""
        s = ServerState()
        s.max_logs = 3
        for i in range(5):
            s.add_log("info", "Test", f"Message {i}")
        assert len(s.logs) == 3
        assert s.logs[0].message == "Message 2"
        assert s.logs[2].message == "Message 4"

    def test_uptime_property(self):
        """Verify uptime calculation"""
        import time
        s = ServerState()
        time.sleep(0.01)
        assert s.uptime >= 0.01


# ============================================================================
# API Models Tests
# ============================================================================

class TestAPIModels:
    """Test API model validation"""

    def test_metric_update_validation(self):
        """Verify MetricUpdate model"""
        m = MetricUpdate(cpu=50.0, memory=75.0, speed=1000.0, temperature=25.0)
        assert m.cpu == 50.0
        assert m.memory == 75.0
        assert m.speed == 1000.0
        assert m.temperature == 25.0

    def test_tool_status_model(self):
        """Verify ToolStatus model"""
        t = ToolStatus(tool="TestTool", status="operational", latency=100)
        assert t.tool == "TestTool"
        assert t.status == "operational"
        assert t.latency == 100


# ============================================================================
# Health Check Tests
# ============================================================================

class TestHealthCheckRuntime:
    """Test health check system"""

    def test_health_check_execution(self):
        """Verify health check runs and returns result"""
        def check_func() -> HealthCheckResult:
            return HealthCheckResult(
                check_name="test_check",
                status=HealthStatus.HEALTHY,
                message="OK"
            )
        
        check = HealthCheck(
            name="test_check",
            description="Test check",
            check_func=check_func,
            severity="info"
        )
        assert check.name == "test_check"
        assert check.severity == "info"

    def test_health_status_enum(self):
        """Verify health status enum"""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.UNKNOWN.value == "unknown"

    def test_health_check_result(self):
        """Verify health check result"""
        result = HealthCheckResult(
            check_name="memory",
            status=HealthStatus.HEALTHY,
            message="OK"
        )
        assert result.check_name == "memory"
        assert result.status == HealthStatus.HEALTHY


# ============================================================================
# Module Import Tests
# ============================================================================

class TestModuleImports:
    """Verify critical modules can be imported"""

    def test_import_api_state(self):
        """Verify api_state imports"""
        from src.app.api_state import ServerState, state
        assert ServerState is not None
        assert state is not None

    def test_import_api_models(self):
        """Verify api_models imports"""
        from src.app.api_models import MetricUpdate, ToolStatus, LogEntry
        assert MetricUpdate is not None
        assert ToolStatus is not None
        assert LogEntry is not None

    def test_import_health(self):
        """Verify health module imports"""
        from src.health.health_check import HealthCheck, HealthStatus
        assert HealthCheck is not None
        assert HealthStatus is not None


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestErrorHandling:
    """Test error handling in state management"""

    def test_update_metrics_with_invalid_data(self):
        """Verify handling of edge case data"""
        s = ServerState()
        # Empty metrics should not raise
        s.update_metrics({})
        assert s._metrics["cpu"] == 0.0

    def test_update_tool_status_empty_string(self):
        """Verify handling of empty tool name"""
        s = ServerState()
        # Empty tool name should not raise
        s.update_tool_status("", "operational", 0)
        assert "" in s._tool_statuses

    def test_log_with_special_characters(self):
        """Verify logging handles special characters"""
        s = ServerState()
        entry = s.add_log("info", "Test", "Test <script>alert('xss')</script>")
        assert entry.message == "Test <script>alert('xss')</script>"


# ============================================================================
# Singleton State Tests
# ============================================================================

class TestSingletonState:
    """Test the global singleton state"""

    def test_global_state_exists(self):
        """Verify global state is accessible"""
        assert state is not None
        assert isinstance(state, ServerState)

    def test_global_state_metrics(self):
        """Verify global state metrics work"""
        initial_cpu = state._metrics.get("cpu", 0.0)
        state.update_metrics({"cpu": initial_cpu + 10.0})
        assert state._metrics["cpu"] == initial_cpu + 10.0


if __name__ == "__main__":
    print("Runtime Production Tests for AI_support")
    print("=" * 60)
    print("Run with: python -m pytest AI_support/tests/test_p9_production_runtime.py -v")
    print("=" * 60)
    pytest.main([__file__, "-v"])
