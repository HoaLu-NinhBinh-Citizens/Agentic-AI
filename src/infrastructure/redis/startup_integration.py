"""Redis health check integration for application startup.

This module demonstrates how to integrate Redis health checks
into the application startup sequence.

Usage:
    from infrastructure.redis.startup_integration import (
        check_redis_health,
        wait_for_redis,
    )

    # During application startup:
    await check_redis_health()
    await wait_for_redis(max_wait_seconds=60)
"""

from __future__ import annotations

import asyncio
import logging
import os

from infrastructure.redis.health_check import (
    RedisHealthChecker,
    RedisHealthCheckResult,
    HealthStatus,
    create_health_checker_from_env,
)

logger = logging.getLogger(__name__)


async def check_redis_health() -> RedisHealthCheckResult:
    """Perform Redis health check during startup.

    Returns:
        RedisHealthCheckResult with health status details

    Raises:
        RuntimeError: If Redis is unhealthy and failsafe is enabled
    """
    checker = create_health_checker_from_env()
    result = await checker.check()

    # Log health status
    if result.status == HealthStatus.HEALTHY:
        logger.info(
            "redis_health_check_passed",
            latency_ms=result.latency_ms,
            master=result.master_available,
            replica=result.replica_available,
        )
    elif result.status == HealthStatus.DEGRADED:
        logger.warning(
            "redis_health_check_degraded",
            latency_ms=result.latency_ms,
            error=result.error,
        )
    else:
        logger.error(
            "redis_health_check_failed",
            error=result.error,
            sentinel=result.sentinel_available,
            master=result.master_available,
        )

    return result


async def wait_for_redis(
    max_wait_seconds: float = 60.0,
    fail_fast: bool = False,
) -> bool:
    """Wait for Redis to become healthy during startup.

    Args:
        max_wait_seconds: Maximum time to wait for Redis
        fail_fast: If True, raise exception on failure

    Returns:
        True if Redis became healthy within timeout

    Raises:
        RuntimeError: If fail_fast=True and Redis doesn't become healthy
    """
    checker = create_health_checker_from_env()

    logger.info("waiting_for_redis", max_wait_s=max_wait_seconds)

    if await checker.wait_for_healthy(max_wait_seconds=max_wait_seconds):
        logger.info("redis_ready")
        return True

    if fail_fast:
        raise RuntimeError(
            f"Redis did not become healthy within {max_wait_seconds}s"
        )

    logger.warning("redis_not_ready_continuing_anyway")
    return False


async def get_redis_info() -> dict | None:
    """Get Redis cluster information.

    Returns:
        Dict with Redis info or None if unavailable
    """
    try:
        import redis.asyncio as redis

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        client = redis.from_url(redis_url)

        info = await client.info()
        await client.close()

        return {
            "version": info.get("redis_version"),
            "mode": info.get("redis_mode"),
            "connected_clients": info.get("connected_clients"),
            "used_memory_human": info.get("used_memory_human"),
            "uptime_seconds": info.get("uptime_in_seconds"),
        }
    except Exception as e:
        logger.debug("redis_info_unavailable", error=str(e))
        return None


# Example startup integration for FastAPI/Starlette
async def add_redis_health_routes(app):
    """Add Redis health check routes to FastAPI app.

    Example:
        from fastapi import FastAPI
        from infrastructure.redis.startup_integration import add_redis_health_routes

        app = FastAPI()
        await add_redis_health_routes(app)
    """
    try:
        from fastapi import APIRouter, HTTPException

        router = APIRouter(prefix="/health", tags=["health"])

        @router.get("/redis")
        async def redis_health():
            """Redis health endpoint."""
            result = await check_redis_health()

            if result.status == HealthStatus.HEALTHY:
                return {
                    "status": "healthy",
                    "latency_ms": round(result.latency_ms, 2),
                    "details": {
                        "master_available": result.master_available,
                        "replica_available": result.replica_available,
                    },
                }
            elif result.status == HealthStatus.DEGRADED:
                return {
                    "status": "degraded",
                    "error": result.error,
                    "latency_ms": round(result.latency_ms, 2),
                }
            else:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "status": "unhealthy",
                        "error": result.error,
                    },
                )

        return router

    except ImportError:
        logger.warning("fastapi_not_available_skipping_route_integration")
        return None
