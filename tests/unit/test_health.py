"""Tests for health checker."""

import pytest
from infrastructure.observability.health import (
    HealthChecker,
    HealthStatus,
    ServerHealth,
)


class TestHealthChecker:
    """Tests for HealthChecker."""

    @pytest.fixture
    def checker(self):
        """Create a fresh health checker for each test."""
        return HealthChecker(include_degraded_in_ready=True)

    @pytest.mark.asyncio
    async def test_liveness_returns_alive(self, checker):
        """Test that liveness always returns alive."""
        result = await checker.get_liveness()
        assert result["status"] == "alive"

    @pytest.mark.asyncio
    async def test_readiness_healthy_when_no_servers(self, checker):
        """Test readiness is healthy when no servers registered."""
        report = await checker.get_readiness()
        assert report.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_readiness_healthy_with_healthy_servers(self, checker):
        """Test readiness is healthy when all servers are healthy."""
        await checker.update_server_health("server1", HealthStatus.HEALTHY)
        await checker.update_server_health("server2", HealthStatus.HEALTHY)

        report = await checker.get_readiness()

        assert report.status == HealthStatus.HEALTHY
        assert report.servers["server1"] == "healthy"
        assert report.servers["server2"] == "healthy"

    @pytest.mark.asyncio
    async def test_readiness_degraded_with_degraded_servers(self, checker):
        """Test readiness is degraded when servers are degraded."""
        await checker.update_server_health("server1", HealthStatus.HEALTHY)
        await checker.update_server_health("server2", HealthStatus.DEGRADED)

        report = await checker.get_readiness()

        assert report.status == HealthStatus.DEGRADED
        assert "degraded" in report.reason.lower()

    @pytest.mark.asyncio
    async def test_readiness_unhealthy_with_failed_servers(self, checker):
        """Test readiness is unhealthy when servers fail."""
        await checker.update_server_health("server1", HealthStatus.HEALTHY)
        await checker.update_server_health("server2", HealthStatus.UNHEALTHY)

        report = await checker.get_readiness()

        assert report.status == HealthStatus.UNHEALTHY
        assert "unhealthy" in report.reason.lower()

    @pytest.mark.asyncio
    async def test_permanently_failed_marks_server(self, checker):
        """Test marking a server as permanently failed."""
        await checker.update_server_health("server1", HealthStatus.HEALTHY)
        await checker.mark_permanently_failed("server1")

        report = await checker.get_readiness()

        assert report.status == HealthStatus.DEGRADED
        assert "server1" in report.details["permanently_failed"]

    @pytest.mark.asyncio
    async def test_server_availability(self, checker):
        """Test server availability check."""
        await checker.update_server_health("server1", HealthStatus.HEALTHY)
        await checker.update_server_health("server2", HealthStatus.UNHEALTHY)
        await checker.mark_permanently_failed("server3")

        assert await checker.is_server_available("server1")
        assert not await checker.is_server_available("server2")
        assert not await checker.is_server_available("server3")

    @pytest.mark.asyncio
    async def test_unknown_server_is_available(self, checker):
        """Test that unknown servers are considered available."""
        assert await checker.is_server_available("unknown-server")

    @pytest.mark.asyncio
    async def test_get_server_health(self, checker):
        """Test getting specific server health."""
        await checker.update_server_health(
            "server1",
            HealthStatus.DEGRADED,
            circuit_state="open",
            last_error="Connection refused",
        )

        health = await checker.get_server_health("server1")

        assert health is not None
        assert health.name == "server1"
        assert health.status == HealthStatus.DEGRADED
        assert health.circuit_state == "open"
        assert health.last_error == "Connection refused"

    @pytest.mark.asyncio
    async def test_degraded_excluded_when_configured(self):
        """Test that degraded is excluded from ready when configured."""
        checker = HealthChecker(include_degraded_in_ready=False)

        await checker.update_server_health("server1", HealthStatus.DEGRADED)

        report = await checker.get_readiness()

        assert report.status == HealthStatus.DEGRADED


class TestServerHealth:
    """Tests for ServerHealth dataclass."""

    def test_server_health_creation(self):
        """Test creating a server health record."""
        health = ServerHealth(
            name="test-server",
            status=HealthStatus.HEALTHY,
            circuit_state="closed",
        )

        assert health.name == "test-server"
        assert health.status == HealthStatus.HEALTHY
        assert health.circuit_state == "closed"
        assert health.last_error is None
        assert health.restart_count == 0
