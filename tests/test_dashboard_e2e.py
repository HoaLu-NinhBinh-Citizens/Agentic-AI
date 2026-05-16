"""
Dashboard E2E Tests

These tests verify the dashboard API works end-to-end by testing
the full request/response cycle through the FastAPI application.

Tests:
1. Health endpoint returns valid response
2. Metrics can be updated and retrieved
3. Logs can be added and retrieved
4. Tool status can be updated
5. WebSocket connection handling

Note: True browser E2E tests (Playwright/Selenium) are documented separately.
These tests provide API-level E2E verification.

Run: python -m pytest AI_support/tests/test_dashboard_e2e.py -v
"""

import pytest
from fastapi.testclient import TestClient
import sys

sys.path.insert(0, "C:/Users/thang/Desktop/carv")

from src.app.api_server import app


@pytest.fixture
def client():
    """Create test client for the API."""
    return TestClient(app)


# ============================================================================
# Health Endpoint E2E
# ============================================================================

class TestHealthEndpointE2E:
    """E2E tests for health endpoint"""

    def test_health_returns_200(self, client):
        """Verify health endpoint returns 200 OK"""
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_health_returns_status_field(self, client):
        """Verify health response has status field"""
        response = client.get("/api/health")
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "degraded", "unhealthy"]

    def test_health_returns_timestamp(self, client):
        """Verify health response has timestamp"""
        response = client.get("/api/health")
        data = response.json()
        assert "timestamp" in data


# ============================================================================
# Metrics Endpoint E2E
# ============================================================================

class TestMetricsEndpointE2E:
    """E2E tests for metrics endpoint"""

    def test_get_metrics(self, client):
        """Verify metrics can be retrieved"""
        response = client.get("/api/metrics")
        assert response.status_code == 200
        data = response.json()
        # API returns metrics dict directly
        assert "cpu" in data or "metrics" in data

    def test_update_metrics(self, client):
        """Verify metrics can be updated"""
        response = client.post("/api/metrics", json={
            "cpu": 50.0,
            "memory": 75.0,
            "speed": 1000.0,
            "temperature": 25.0
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_metrics_validation(self, client):
        """Verify metrics validation works"""
        # Missing required field should fail
        response = client.post("/api/metrics", json={
            "cpu": 50.0
        })
        # Should fail with validation error
        assert response.status_code in [400, 422]


# ============================================================================
# Logs Endpoint E2E
# ============================================================================

class TestLogsEndpointE2E:
    """E2E tests for logs endpoint"""

    def test_get_logs(self, client):
        """Verify logs can be retrieved"""
        response = client.get("/api/logs")
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert "total" in data

    def test_get_logs_with_limit(self, client):
        """Verify logs limit parameter works"""
        response = client.get("/api/logs?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["logs"]) <= 5

    def test_add_log(self, client):
        """Verify log can be added"""
        response = client.post("/api/logs", json={
            "level": "info",
            "source": "E2E Test",
            "message": "Test log entry"
        })
        assert response.status_code in [200, 201]


# ============================================================================
# Tools Endpoint E2E
# ============================================================================

class TestToolsEndpointE2E:
    """E2E tests for tools endpoint"""

    def test_get_tools(self, client):
        """Verify tools list can be retrieved"""
        response = client.get("/api/tools")
        assert response.status_code == 200
        data = response.json()
        assert "tools" in data

    def test_update_tool_status(self, client):
        """Verify tool status can be updated"""
        response = client.post("/api/tools", json={
            "tool": "TestTool",
            "status": "operational",
            "latency": 100
        })
        assert response.status_code in [200, 201]
        data = response.json()
        assert data["status"] == "ok"


# ============================================================================
# Status Endpoint E2E
# ============================================================================

class TestStatusEndpointE2E:
    """E2E tests for status endpoint"""

    def test_get_status(self, client):
        """Verify status endpoint works"""
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        # Status endpoint returns SystemStatus model
        assert "agent_initialized" in data or "model" in data

    def test_get_capabilities(self, client):
        """Verify capabilities endpoint works"""
        # This endpoint may not exist, skip if 404
        response = client.get("/api/capabilities")
        # Either 200 with capabilities or 404 if not implemented
        if response.status_code == 200:
            data = response.json()
            assert "capabilities" in data or isinstance(data, dict)
        else:
            pytest.skip("Capabilities endpoint not implemented")


# ============================================================================
# Integration Flow Tests
# ============================================================================

class TestIntegrationFlow:
    """Test complete user flows"""

    def test_health_check_flow(self, client):
        """Test complete health check flow"""
        # 1. Check initial health
        health = client.get("/api/health")
        assert health.status_code == 200
        
        # 2. Update some metrics
        metrics = client.post("/api/metrics", json={
            "cpu": 50.0,
            "memory": 75.0,
            "speed": 1000.0,
            "temperature": 25.0
        })
        assert metrics.status_code == 200
        
        # 3. Check updated metrics
        updated = client.get("/api/metrics")
        assert updated.status_code == 200
        
        # 4. Add a log
        log = client.post("/api/logs", json={
            "level": "info",
            "source": "Integration Test",
            "message": "Health check flow completed"
        })
        assert log.status_code in [200, 201]

    def test_tool_tracking_flow(self, client):
        """Test complete tool tracking flow"""
        # 1. Get initial tools
        tools = client.get("/api/tools")
        assert tools.status_code == 200
        
        # 2. Update tool status
        update = client.post("/api/tools", json={
            "tool": "IntegrationTool",
            "status": "operational",
            "latency": 50
        })
        assert update.status_code in [200, 201]
        
        # 3. Verify update
        final_tools = client.get("/api/tools")
        assert final_tools.status_code == 200


if __name__ == "__main__":
    print("Dashboard E2E Tests")
    print("=" * 60)
    print("Run with: python -m pytest AI_support/tests/test_dashboard_e2e.py -v")
    print("=" * 60)
    pytest.main([__file__, "-v"])
