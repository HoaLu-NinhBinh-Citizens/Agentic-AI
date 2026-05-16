"""Health check implementation for Phase 2D/2D.1.

Provides:
- Liveness and readiness endpoints
- Degraded state support
- Event loop health monitoring
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ServerHealth:
    """Health status of an MCP server."""

    name: str
    status: HealthStatus
    circuit_state: str = "closed"
    last_error: str | None = None
    restart_count: int = 0


@dataclass
class HealthReport:
    """Overall health report."""

    status: HealthStatus
    reason: str | None = None
    servers: dict[str, str] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    event_loop_healthy: bool = True


class EventLoopHealth:
    """Event loop health monitor.

    Tracks event loop responsiveness by updating a heartbeat timestamp.
    """

    def __init__(self, max_lag_seconds: float = 5.0) -> None:
        """Initialize the event loop health monitor.

        Args:
            max_lag_seconds: Maximum acceptable lag before considering loop stalled.
        """
        self._max_lag = max_lag_seconds
        self._last_heartbeat = time.monotonic()
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Start the heartbeat task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._heartbeat())

    async def stop(self) -> None:
        """Stop the heartbeat task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _heartbeat(self) -> None:
        """Update heartbeat timestamp periodically."""
        while self._running:
            self._last_heartbeat = time.monotonic()
            await asyncio.sleep(1.0)

    def is_alive(self) -> bool:
        """Check if event loop is responsive.

        Returns:
            True if heartbeat is recent (within max_lag_seconds).
        """
        lag = time.monotonic() - self._last_heartbeat
        return lag < self._max_lag

    def get_lag(self) -> float:
        """Get the current lag in seconds.

        Returns:
            Time since last heartbeat in seconds.
        """
        return time.monotonic() - self._last_heartbeat


class HealthChecker:
    """Health checker for runtime components.

    Tracks MCP server health and provides readiness reports.
    """

    def __init__(
        self,
        include_degraded_in_ready: bool = True,
        check_interval: float = 30.0,
        event_loop_max_lag: float = 5.0,
    ) -> None:
        """Initialize health checker.

        Args:
            include_degraded_in_ready: If True, degraded status returns 200.
            check_interval: Interval for health checks in seconds.
            event_loop_max_lag: Maximum acceptable event loop lag in seconds.
        """
        self._include_degraded_in_ready = include_degraded_in_ready
        self._check_interval = check_interval
        self._event_loop_max_lag = event_loop_max_lag

        self._server_health: dict[str, ServerHealth] = {}
        self._lock = asyncio.Lock()
        self._degraded_servers: set[str] = set()
        self._permanently_failed_servers: set[str] = set()
        self._event_loop_health = EventLoopHealth(max_lag_seconds=event_loop_max_lag)

    async def start(self) -> None:
        """Start the health checker background tasks."""
        await self._event_loop_health.start()

    async def stop(self) -> None:
        """Stop the health checker background tasks."""
        await self._event_loop_health.stop()

    async def update_server_health(
        self,
        server_name: str,
        status: HealthStatus,
        circuit_state: str | None = None,
        last_error: str | None = None,
    ) -> None:
        """Update health status for a server.

        Args:
            server_name: Name of the MCP server.
            status: Current health status.
            circuit_state: Circuit breaker state.
            last_error: Last error message.
        """
        async with self._lock:
            self._server_health[server_name] = ServerHealth(
                name=server_name,
                status=status,
                circuit_state=circuit_state or "unknown",
                last_error=last_error,
            )

            if status == HealthStatus.DEGRADED:
                self._degraded_servers.add(server_name)
            else:
                self._degraded_servers.discard(server_name)

    async def mark_permanently_failed(self, server_name: str) -> None:
        """Mark a server as permanently failed.

        Args:
            server_name: Name of the server.
        """
        async with self._lock:
            self._permanently_failed_servers.add(server_name)
            self._degraded_servers.add(server_name)
            self._server_health[server_name] = ServerHealth(
                name=server_name,
                status=HealthStatus.DEGRADED,
                last_error="Permanently failed after max restarts",
            )
            logger.error(
                "Server marked permanently failed",
                extra={"server_name": server_name},
            )

    async def get_liveness(self) -> dict[str, Any]:
        """Get liveness status.

        Returns:
            Liveness report.
        """
        return {
            "status": "alive",
        }

    async def get_readiness(self) -> HealthReport:
        """Get readiness status.

        Returns:
            Readiness report with server details.
        """
        event_loop_healthy = self._event_loop_health.is_alive()
        event_loop_lag = self._event_loop_health.get_lag()

        async with self._lock:
            server_statuses = {}
            unhealthy_count = 0

            for name, health in self._server_health.items():
                server_statuses[name] = health.status.value
                if health.status == HealthStatus.UNHEALTHY:
                    unhealthy_count += 1

            all_degraded = (
                len(self._server_health) > 0
                and self._degraded_servers
                and not self._permanently_failed_servers
            )

            if not event_loop_healthy:
                status = HealthStatus.UNHEALTHY
                reason = f"Event loop stalled (lag: {event_loop_lag:.2f}s)"
            elif unhealthy_count > 0:
                status = HealthStatus.UNHEALTHY
                reason = "One or more servers are unhealthy"
            elif all_degraded and not self._include_degraded_in_ready:
                status = HealthStatus.DEGRADED
                reason = self._get_degraded_reason()
            elif self._degraded_servers:
                status = HealthStatus.DEGRADED
                reason = self._get_degraded_reason()
            else:
                status = HealthStatus.HEALTHY
                reason = None

            return HealthReport(
                status=status,
                reason=reason,
                servers=server_statuses,
                details={
                    "degraded_servers": list(self._degraded_servers),
                    "permanently_failed": list(self._permanently_failed_servers),
                    "event_loop_healthy": event_loop_healthy,
                    "event_loop_lag_seconds": round(event_loop_lag, 2),
                },
                event_loop_healthy=event_loop_healthy,
            )

    def _get_degraded_reason(self) -> str:
        """Get reason for degraded status.

        Returns:
            Human-readable reason.
        """
        if self._permanently_failed_servers:
            return f"Servers permanently failed: {', '.join(self._permanently_failed_servers)}"
        if self._degraded_servers:
            return f"MCP servers degraded: {', '.join(self._degraded_servers)}"
        return "Some services are degraded"

    async def get_server_health(self, server_name: str) -> ServerHealth | None:
        """Get health status for a specific server.

        Args:
            server_name: Name of the server.

        Returns:
            Server health or None if not found.
        """
        async with self._lock:
            return self._server_health.get(server_name)

    async def is_server_available(self, server_name: str) -> bool:
        """Check if a server is available for tool calls.

        Args:
            server_name: Name of the server.

        Returns:
            True if server is healthy and not permanently failed.
        """
        async with self._lock:
            if server_name in self._permanently_failed_servers:
                return False

            health = self._server_health.get(server_name)
            if health is None:
                return True

            return health.status != HealthStatus.UNHEALTHY

    def is_event_loop_healthy(self) -> bool:
        """Check if event loop is healthy.

        Returns:
            True if event loop is responsive.
        """
        return self._event_loop_health.is_alive()
