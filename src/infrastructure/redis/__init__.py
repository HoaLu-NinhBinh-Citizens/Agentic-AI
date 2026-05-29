"""Redis Infrastructure Module.

Provides:
- High availability Redis client (Sentinel, Cluster, Replicated)
- Health check for Redis connectivity
- Startup integration helpers
"""

from infrastructure.redis.high_availability import (
    RedisHA,
    RedisHAConfig,
    RedisTopology,
    RedisEndpoint,
    create_redis_ha,
)
from infrastructure.redis.health_check import (
    RedisHealthChecker,
    RedisHealthCheckResult,
    HealthStatus,
    create_health_checker_from_env,
)
from infrastructure.redis.startup_integration import (
    check_redis_health,
    wait_for_redis,
    get_redis_info,
    add_redis_health_routes,
)

__all__ = [
    # High Availability
    "RedisHA",
    "RedisHAConfig",
    "RedisTopology",
    "RedisEndpoint",
    "create_redis_ha",
    # Health Check
    "RedisHealthChecker",
    "RedisHealthCheckResult",
    "HealthStatus",
    "create_health_checker_from_env",
    # Startup Integration
    "check_redis_health",
    "wait_for_redis",
    "get_redis_info",
    "add_redis_health_routes",
]
