"""Tests for the CARV API server."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import json

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.app.api_server import (
    app,
    ServerState,
    MetricUpdate,
    LogEntry,
    ToolStatus,
    TaskRequest,
)


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def server_state():
    """Create a fresh ServerState instance for testing."""
    return ServerState()


# =============================================================================
# ServerState Tests
# =============================================================================

class TestServerState:
    """Tests for the ServerState class."""

    def test_initialization(self):
        """Test that ServerState initializes with correct defaults."""
        state = ServerState()
        
        assert state.agent is None
        assert state.task_count == 0
        assert state.success_count == 0
        assert state.error_count == 0
        assert len(state.logs) == 0
        assert len(state.websocket_connections) == 0
        assert state._metrics == {"cpu": 0.0, "memory": 0.0, "speed": 0.0, "temperature": 0.0}
        assert len(state._tool_statuses) == 0

    def test_uptime_calculation(self, server_state):
        """Test that uptime is calculated correctly."""
        import time
        initial_uptime = server_state.uptime
        time.sleep(0.01)
        later_uptime = server_state.uptime
        
        assert later_uptime > initial_uptime

    def test_add_log(self, server_state):
        """Test adding log entries."""
        entry = server_state.add_log("info", "TestSource", "Test message")
        
        assert entry.level == "info"
        assert entry.source == "TestSource"
        assert entry.message == "Test message"
        assert entry.timestamp is not None
        assert len(server_state.logs) == 1

    def test_add_log_respects_max_logs(self, server_state):
        """Test that old logs are removed when exceeding max_logs."""
        server_state.max_logs = 5
        
        for i in range(10):
            server_state.add_log("info", "Test", f"Message {i}")
        
        assert len(server_state.logs) == 5
        assert server_state.logs[0].message == "Message 5"
        assert server_state.logs[-1].message == "Message 9"

    def test_add_log_levels(self, server_state):
        """Test all valid log levels."""
        for level in ["debug", "info", "warn", "error"]:
            entry = server_state.add_log(level, "Test", "Test")
            assert entry.level == level

    def test_update_metrics(self, server_state):
        """Test updating metrics."""
        server_state.update_metrics({"cpu": 50.0, "memory": 75.0})
        
        assert server_state._metrics["cpu"] == 50.0
        assert server_state._metrics["memory"] == 75.0

    def test_update_tool_status(self, server_state):
        """Test updating tool status."""
        server_state.update_tool_status("TestTool", "operational", 100)
        
        assert "TestTool" in server_state._tool_statuses
        tool = server_state._tool_statuses["TestTool"]
        assert tool.tool == "TestTool"
        assert tool.status == "operational"
        assert tool.latency == 100


# =============================================================================
# Health & Status Endpoints
# =============================================================================

class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_check(self, client):
        """Test the health endpoint returns correct status."""
        response = client.get("/api/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    def test_status_endpoint(self, client):
        """Test the status endpoint returns system info."""
        response = client.get("/api/status")
        
        assert response.status_code == 200
        data = response.json()
        assert "agent_initialized" in data
        assert "model" in data
        assert "rag_ready" in data
        assert "uptime_seconds" in data
        assert "task_count" in data


# =============================================================================
# Metrics Endpoints
# =============================================================================

class TestMetricsEndpoints:
    """Tests for metrics endpoints."""

    def test_get_metrics(self, client):
        """Test getting current metrics."""
        response = client.get("/api/metrics")
        
        assert response.status_code == 200
        data = response.json()
        assert "cpu" in data
        assert "memory" in data
        assert "speed" in data
        assert "temperature" in data
        assert "timestamp" in data

    def test_update_metrics(self, client):
        """Test updating metrics via POST."""
        response = client.post("/api/metrics", json={
            "cpu": 75.5,
            "memory": 80.0,
            "speed": 2000.0,
            "temperature": 45.0
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_update_metrics_validation(self, client):
        """Test that metric validation works (cpu must be 0-100)."""
        # Valid - all required fields
        response = client.post("/api/metrics", json={
            "cpu": 50.0,
            "memory": 60.0,
            "speed": 1500.0,
            "temperature": 45.0
        })
        assert response.status_code == 200
        
        # Invalid - cpu out of range
        response = client.post("/api/metrics", json={
            "cpu": 150.0,
            "memory": 60.0,
            "speed": 1500.0,
            "temperature": 45.0
        })
        assert response.status_code == 422  # Validation error


# =============================================================================
# Logs Endpoints
# =============================================================================

class TestLogsEndpoints:
    """Tests for logs endpoints."""

    def test_get_logs_empty(self, client):
        """Test getting logs when empty."""
        response = client.get("/api/logs")
        
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert "total" in data
        assert isinstance(data["logs"], list)

    def test_add_log(self, client):
        """Test adding a log entry."""
        response = client.post("/api/logs", json={
            "level": "info",
            "source": "TestSource",
            "message": "Test message"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_get_logs_with_limit(self, client):
        """Test getting logs with limit parameter."""
        # Add some logs first
        for i in range(10):
            client.post("/api/logs", json={
                "level": "info",
                "source": "Test",
                "message": f"Log {i}"
            })
        
        response = client.get("/api/logs?limit=5")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["logs"]) <= 5

    def test_get_logs_with_level_filter(self, client):
        """Test filtering logs by level."""
        # Add logs of different levels
        client.post("/api/logs", json={"level": "debug", "source": "Test", "message": "Debug"})
        client.post("/api/logs", json={"level": "info", "source": "Test", "message": "Info"})
        client.post("/api/logs", json={"level": "error", "source": "Test", "message": "Error"})
        
        response = client.get("/api/logs?level=error")
        
        assert response.status_code == 200
        data = response.json()
        for log in data["logs"]:
            assert log["level"] == "error"

    def test_add_log_invalid_level(self, client):
        """Test that invalid log levels are rejected."""
        response = client.post("/api/logs", json={
            "level": "invalid_level",
            "source": "Test",
            "message": "Test"
        })
        
        assert response.status_code == 422  # Validation error


# =============================================================================
# Tools Endpoints
# =============================================================================

class TestToolsEndpoints:
    """Tests for tools endpoints."""

    def test_get_tools_empty(self, client):
        """Test getting tools when none exist."""
        response = client.get("/api/tools")
        
        assert response.status_code == 200
        data = response.json()
        assert "tools" in data
        assert "count" in data

    def test_update_tool(self, client):
        """Test updating a tool's status."""
        response = client.post("/api/tools", json={
            "tool": "TestTool",
            "status": "operational",
            "latency": 50
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_update_tool_invalid_status(self, client):
        """Test that invalid tool status is rejected."""
        response = client.post("/api/tools", json={
            "tool": "TestTool",
            "status": "invalid_status",
            "latency": 50
        })
        
        assert response.status_code == 422


# =============================================================================
# Tasks Endpoints
# =============================================================================

class TestTasksEndpoints:
    """Tests for tasks endpoints."""

    def test_create_task_without_agent(self, client):
        """Test creating a task when agent is not initialized."""
        response = client.post("/api/tasks", json={
            "task": "Test task",
            "plan_mode": False
        })
        
        # Should fail because agent is not initialized
        assert response.status_code == 503
        data = response.json()
        assert "detail" in data

    def test_create_task_empty_task(self, client):
        """Test that empty task is rejected."""
        response = client.post("/api/tasks", json={
            "task": "",
            "plan_mode": False
        })
        
        assert response.status_code == 422


# =============================================================================
# CORS Tests
# =============================================================================

class TestCORS:
    """Tests for CORS configuration."""

    def test_cors_headers_present(self, client):
        """Test that CORS headers are included in responses."""
        response = client.get(
            "/api/health",
            headers={"Origin": "http://localhost:3001"}
        )
        
        assert response.status_code == 200
        # CORS headers should be added by middleware


# =============================================================================
# WebSocket Tests
# =============================================================================

class TestWebSocketEndpoint:
    """Tests for WebSocket endpoint."""

    def test_websocket_connection(self, client):
        """Test WebSocket connection establishment."""
        with client.websocket_connect("/ws/stream") as websocket:
            # Should receive initial connection message
            data = websocket.receive_json()
            assert data["type"] == "connection"
            assert data["data"]["status"] == "connected"
            
            # Should receive initial metrics
            data = websocket.receive_json()
            assert data["type"] == "metric_update"

    def test_websocket_ping(self, client):
        """Test WebSocket ping-pong."""
        with client.websocket_connect("/ws/stream") as websocket:
            # Receive initial messages
            websocket.receive_json()  # connection
            websocket.receive_json()  # metric_update
            
            # Send ping
            websocket.send_text("ping")
            
            # Should receive pong
            data = websocket.receive_json()
            assert data["type"] == "pong"
            assert "timestamp" in data["data"]

    def test_websocket_subscribe(self, client):
        """Test WebSocket subscription."""
        with client.websocket_connect("/ws/stream") as websocket:
            # Receive initial messages
            websocket.receive_json()
            websocket.receive_json()
            
            # Subscribe to a channel
            websocket.send_text("subscribe:metrics")
            
            # Should receive subscription confirmation
            data = websocket.receive_json()
            assert data["type"] == "subscribed"
            assert data["data"]["channel"] == "metrics"


# =============================================================================
# Pydantic Models Tests
# =============================================================================

class TestPydanticModels:
    """Tests for Pydantic models."""

    def test_metric_update_valid(self):
        """Test valid MetricUpdate model."""
        m = MetricUpdate(cpu=50.0, memory=75.0, speed=1500.0, temperature=45.0)
        assert m.cpu == 50.0

    def test_metric_update_cpu_range(self):
        """Test CPU validation (0-100)."""
        # Valid - all required fields with valid CPU
        MetricUpdate(cpu=0.0, memory=50.0, speed=1500.0, temperature=45.0)
        MetricUpdate(cpu=100.0, memory=50.0, speed=1500.0, temperature=45.0)
        MetricUpdate(cpu=50.0, memory=50.0, speed=1500.0, temperature=45.0)
        
        # Invalid - should raise (cpu out of range)
        with pytest.raises(Exception):
            MetricUpdate(cpu=-10.0, memory=50.0, speed=1500.0, temperature=45.0)
        with pytest.raises(Exception):
            MetricUpdate(cpu=150.0, memory=50.0, speed=1500.0, temperature=45.0)

    def test_log_entry_valid_levels(self):
        """Test LogEntry with valid levels."""
        for level in ["debug", "info", "warn", "error"]:
            entry = LogEntry(level=level, source="Test", message="Test")
            assert entry.level == level

    def test_log_entry_invalid_level(self):
        """Test LogEntry with invalid level."""
        with pytest.raises(Exception):
            LogEntry(level="critical", source="Test", message="Test")

    def test_tool_status_valid_statuses(self):
        """Test ToolStatus with valid statuses."""
        for status in ["operational", "degraded", "offline"]:
            tool = ToolStatus(tool="Test", status=status, latency=100)
            assert tool.status == status

    def test_tool_status_invalid_status(self):
        """Test ToolStatus with invalid status."""
        with pytest.raises(Exception):
            ToolStatus(tool="Test", status="unknown", latency=100)

    def test_task_request_valid(self):
        """Test valid TaskRequest."""
        task = TaskRequest(task="Test task", plan_mode=True)
        assert task.task == "Test task"
        assert task.plan_mode is True

    def test_task_request_empty_task(self):
        """Test that empty task is rejected."""
        with pytest.raises(Exception):
            TaskRequest(task="")
