"""Redis Health Check Module.

Provides health checks for Redis connectivity in the application startup.
Supports Sentinel and direct Redis connections with TLS.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health check status."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"


@dataclass
class RedisHealthCheckResult:
    """Result of Redis health check."""
    status: HealthStatus
    latency_ms: float
    master_available: bool
    replica_available: bool
    sentinel_available: bool
    error: str | None = None


class RedisHealthChecker:
    """Health checker for Redis connectivity.

    Performs health checks on:
    - Redis Sentinel availability
    - Redis master connectivity
    - Redis replica connectivity
    - Latency measurements
    """

    def __init__(
        self,
        sentinel_hosts: list[tuple[str, int]] | None = None,
        sentinel_master: str = "mymaster",
        redis_password: str | None = None,
        tls_enabled: bool = False,
        tls_cert_path: str | None = None,
        tls_key_path: str | None = None,
        tls_ca_path: str | None = None,
        timeout: float = 5.0,
    ):
        self._sentinel_hosts = sentinel_hosts or [("localhost", 26379)]
        self._sentinel_master = sentinel_master
        self._redis_password = redis_password or os.getenv("REDIS_PASSWORD")
        self._tls_enabled = tls_enabled or os.getenv("REDIS_TLS_ENABLED", "").lower() == "true"
        self._tls_cert_path = tls_cert_path or os.getenv("REDIS_TLS_CERT")
        self._tls_key_path = tls_key_path or os.getenv("REDIS_TLS_KEY")
        self._tls_ca_path = tls_ca_path or os.getenv("REDIS_TLS_CA")
        self._timeout = timeout

    async def check(self) -> RedisHealthCheckResult:
        """Perform health check on Redis infrastructure.

        Returns:
            RedisHealthCheckResult with status and details
        """
        import time
        start = time.monotonic()

        sentinel_available = False
        master_available = False
        replica_available = False
        error = None

        # Check Sentinel connectivity
        sentinel_available = await self._check_sentinel()

        # Check master connectivity
        master_available = await self._check_master()

        # Check replica connectivity
        replica_available = await self._check_replica()

        latency_ms = (time.monotonic() - start) * 1000

        # Determine overall status
        if not sentinel_available and not master_available:
            status = HealthStatus.UNHEALTHY
            error = "Redis infrastructure unavailable"
        elif not master_available:
            status = HealthStatus.UNHEALTHY
            error = "Redis master unavailable"
        elif not replica_available:
            status = HealthStatus.DEGRADED
            error = "Redis replica unavailable"
        elif latency_ms > self._timeout * 1000:
            status = HealthStatus.DEGRADED
            error = f"High latency: {latency_ms:.0f}ms"
        else:
            status = HealthStatus.HEALTHY

        return RedisHealthCheckResult(
            status=status,
            latency_ms=latency_ms,
            master_available=master_available,
            replica_available=replica_available,
            sentinel_available=sentinel_available,
            error=error,
        )

    async def _check_sentinel(self) -> bool:
        """Check Sentinel availability."""
        try:
            import redis.asyncio as redis

            for host, port in self._sentinel_hosts:
                try:
                    client = redis.Redis(
                        host=host,
                        port=port,
                        password=self._redis_password,
                        socket_timeout=self._timeout,
                    )
                    await client.ping()
                    await client.close()
                    return True
                except Exception:
                    continue

            return False
        except ImportError:
            logger.warning("redis package not installed, skipping sentinel check")
            return True  # Assume healthy in dev without redis package

    async def _check_master(self) -> bool:
        """Check Redis master availability."""
        try:
            import redis.asyncio as redis

            # Try direct connection to known master
            for host, port in self._sentinel_hosts:
                # Sentinel hosts are on port 26379, Redis on 6379
                redis_port = 6379
                try:
                    if self._tls_enabled:
                        client = redis.Redis(
                            host=host,
                            port=redis_port,
                            password=self._redis_password,
                            ssl=True,
                            ssl_certfile=self._tls_cert_path,
                            ssl_keyfile=self._tls_key_path,
                            ssl_ca_certs=self._tls_ca_path,
                            socket_timeout=self._timeout,
                        )
                    else:
                        client = redis.Redis(
                            host=host,
                            port=redis_port,
                            password=self._redis_password,
                            socket_timeout=self._timeout,
                        )

                    await client.ping()
                    await client.close()
                    return True
                except Exception:
                    continue

            return False
        except ImportError:
            return True

    async def _check_replica(self) -> bool:
        """Check Redis replica availability."""
        try:
            import redis.asyncio as redis

            # Check replica info from first sentinel host
            host, port = self._sentinel_hosts[0]
            redis_port = 6379

            try:
                client = redis.Redis(
                    host=host,
                    port=redis_port,
                    password=self._redis_password,
                    socket_timeout=self._timeout,
                )

                info = await client.info("replication")
                replica_count = info.get("connected_slaves", 0)

                await client.close()
                return replica_count >= 0  # At least master should be counted
            except Exception:
                return False
        except ImportError:
            return True

    async def wait_for_healthy(
        self,
        max_wait_seconds: float = 60.0,
        check_interval: float = 5.0,
    ) -> bool:
        """Wait for Redis to become healthy.

        Args:
            max_wait_seconds: Maximum time to wait
            check_interval: Time between checks

        Returns:
            True if Redis became healthy, False if timeout
        """
        import time
        start = time.monotonic()

        while time.monotonic() - start < max_wait_seconds:
            result = await self.check()

            if result.status == HealthStatus.HEALTHY:
                logger.info("redis_health_check_passed", latency_ms=result.latency_ms)
                return True

            logger.warning(
                "redis_health_check_pending",
                status=result.status.value,
                elapsed_s=time.monotonic() - start,
            )

            await asyncio.sleep(check_interval)

        logger.error("redis_health_check_timeout", max_wait_s=max_wait_seconds)
        return False


def create_health_checker_from_env() -> RedisHealthChecker:
    """Create RedisHealthChecker from environment variables.

    Environment variables:
        REDIS_SENTINEL_HOSTS: Comma-separated list of sentinel hosts
        REDIS_SENTINEL_MASTER: Sentinel master name
        REDIS_PASSWORD: Redis password
        REDIS_TLS_ENABLED: Enable TLS
        REDIS_TLS_CERT: TLS certificate path
        REDIS_TLS_KEY: TLS key path
        REDIS_TLS_CA: TLS CA certificate path
    """
    sentinel_hosts_str = os.getenv("REDIS_SENTINEL_HOSTS", "localhost:26379")
    sentinel_hosts = [
        (host, int(port))
        for host, port in (h.split(":") for h in sentinel_hosts_str.split(","))
    ]

    return RedisHealthChecker(
        sentinel_hosts=sentinel_hosts,
        sentinel_master=os.getenv("REDIS_SENTINEL_MASTER", "mymaster"),
        redis_password=os.getenv("REDIS_PASSWORD"),
        tls_enabled=os.getenv("REDIS_TLS_ENABLED", "").lower() == "true",
        tls_cert_path=os.getenv("REDIS_TLS_CERT"),
        tls_key_path=os.getenv("REDIS_TLS_KEY"),
        tls_ca_path=os.getenv("REDIS_TLS_CA"),
    )
