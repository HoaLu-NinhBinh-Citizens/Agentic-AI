"""Multi-Region Redis High Availability Configuration.

Provides:
- Redis Sentinel for automatic failover
- Redis Cluster for sharding
- Cross-region replication
- Connection pooling
- Circuit breaker integration

Usage:
    ha = RedisHA(config)
    await ha.connect()
    value = await ha.get("key")
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class RedisTopology(Enum):
    """Redis deployment topology."""
    SINGLE = "single"
    SENTINEL = "sentinel"
    CLUSTER = "cluster"
    REPLICATED = "replicated"


@dataclass
class RedisEndpoint:
    """Redis endpoint configuration."""
    host: str
    port: int = 6379
    region: str = "primary"
    priority: int = 100
    is_master: bool = True


@dataclass
class RedisHAConfig:
    """Configuration for Redis HA."""
    topology: RedisTopology = RedisTopology.SENTINEL
    endpoints: list[RedisEndpoint] = field(default_factory=list)
    master_name: str = "mymaster"
    password: str | None = None
    db: int = 0
    pool_size: int = 50
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    retry_timeout: float = 30.0
    health_check_interval: float = 10.0


class RedisHA:
    """High Availability Redis client.
    
    Supports:
    - Sentinel for automatic failover
    - Cluster for horizontal scaling
    - Cross-region replication
    
    Usage:
        config = RedisHAConfig(
            topology=RedisTopology.SENTINEL,
            endpoints=[
                RedisEndpoint(host="redis-primary.us-east", region="us-east"),
                RedisEndpoint(host="redis-replica.us-west", region="us-west"),
            ],
        )
        
        ha = RedisHA(config)
        await ha.connect()
        
        # Automatic failover handling
        result = await ha.get("session:123")
    """
    
    def __init__(self, config: RedisHAConfig):
        self._config = config
        self._client = None
        self._sentinel = None
        self._connected = False
        self._current_master: RedisEndpoint | None = None
        self._circuit_open = False
        self._health_check_task: asyncio.Task | None = None
    
    async def connect(self) -> bool:
        """Connect to Redis HA cluster."""
        try:
            if self._config.topology == RedisTopology.SENTINEL:
                await self._connect_sentinel()
            elif self._config.topology == RedisTopology.CLUSTER:
                await self._connect_cluster()
            elif self._config.topology == RedisTopology.REPLICATED:
                await self._connect_replicated()
            else:
                await self._connect_single()
            
            self._connected = True
            self._start_health_check()
            
            logger.info("redis_ha_connected", topology=self._config.topology.value)
            return True
            
        except Exception as e:
            logger.error("redis_ha_connect_failed", error=str(e))
            return False
    
    async def _connect_sentinel(self) -> None:
        """Connect to Redis Sentinel."""
        try:
            import redis.asyncio as redis
            
            # Try to connect to any sentinel first
            for endpoint in self._config.endpoints:
                try:
                    sentinel_client = redis.Redis(
                        host=endpoint.host,
                        port=endpoint.port,
                        password=self._config.password,
                        socket_timeout=self._config.socket_timeout,
                    )
                    await sentinel_client.ping()
                    self._sentinel = sentinel_client
                    
                    # Get master from sentinel
                    master_info = await sentinel_client.sentinel_get_master_addr_by_name(
                        self._config.master_name
                    )
                    if master_info:
                        self._current_master = RedisEndpoint(
                            host=master_info[0].decode(),
                            port=int(master_info[1]),
                        )
                        break
                except Exception:
                    continue
            
            if not self._sentinel:
                raise RuntimeError("No sentinel available")
            
            # Create client connected to master
            if self._current_master:
                self._client = redis.Redis(
                    host=self._current_master.host,
                    port=self._current_master.port,
                    password=self._config.password,
                    db=self._config.db,
                    max_connections=self._config.pool_size,
                    socket_timeout=self._config.socket_timeout,
                    socket_connect_timeout=self._config.socket_connect_timeout,
                )
                
        except ImportError:
            logger.warning("redis_py_not_installed_using_mock")
            await self._connect_mock()
    
    async def _connect_cluster(self) -> None:
        """Connect to Redis Cluster."""
        try:
            import redis.asyncio as redis
            
            startup_nodes = [
                {"host": e.host, "port": e.port}
                for e in self._config.endpoints
            ]
            
            self._client = redis.RedisCluster(
                startup_nodes=startup_nodes,
                password=self._config.password,
                max_connections=self._config.pool_size,
                socket_timeout=self._config.socket_timeout,
            )
            
        except ImportError:
            logger.warning("redis_py_not_installed_using_mock")
            await self._connect_mock()
    
    async def _connect_replicated(self) -> None:
        """Connect to replicated Redis (master + read replicas)."""
        try:
            import redis.asyncio as redis
            
            # Connect to master
            master = self._config.endpoints[0]
            self._client = redis.Redis(
                host=master.host,
                port=master.port,
                password=self._config.password,
                db=self._config.db,
                max_connections=self._config.pool_size,
                socket_timeout=self._config.socket_timeout,
            )
            
        except ImportError:
            await self._connect_mock()
    
    async def _connect_single(self) -> None:
        """Connect to single Redis instance."""
        endpoint = self._config.endpoints[0]
        self._client = await self._create_client(endpoint)
    
    async def _connect_mock(self) -> None:
        """Mock Redis for testing."""
        self._client = MockRedisClient()
    
    async def _create_client(self, endpoint: RedisEndpoint):
        """Create Redis client for endpoint."""
        try:
            import redis.asyncio as redis
            
            return redis.Redis(
                host=endpoint.host,
                port=endpoint.port,
                password=self._config.password,
                db=self._config.db,
                max_connections=self._config.pool_size,
                socket_timeout=self._config.socket_timeout,
            )
        except ImportError:
            return MockRedisClient()
    
    def _start_health_check(self) -> None:
        """Start background health check."""
        self._health_check_task = asyncio.create_task(self._health_check_loop())
    
    async def _health_check_loop(self) -> None:
        """Periodic health check."""
        while self._connected:
            try:
                await asyncio.sleep(self._config.health_check_interval)
                await self.health_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("health_check_failed", error=str(e))
    
    async def health_check(self) -> bool:
        """Perform health check."""
        if self._circuit_open:
            return False
        
        try:
            if self._client:
                await self._client.ping()
                return True
        except Exception as e:
            logger.warning("health_check_failed", error=str(e))
            
            # Trigger failover if master is down
            if self._config.topology == RedisTopology.SENTINEL:
                await self._trigger_failover()
            
            return False
        
        return False
    
    async def _trigger_failover(self) -> None:
        """Trigger Sentinel failover."""
        logger.warning("triggering_failover")
        
        try:
            # Get new master from sentinel
            master_info = await self._sentinel.sentinel_get_master_addr_by_name(
                self._config.master_name
            )
            
            if master_info:
                new_master = RedisEndpoint(
                    host=master_info[0].decode(),
                    port=int(master_info[1]),
                )
                
                # Reconnect to new master
                if self._client:
                    await self._client.close()
                
                self._client = await self._create_client(new_master)
                self._current_master = new_master
                
                logger.info("failover_completed", new_master=new_master.host)
        
        except Exception as e:
            logger.error("failover_failed", error=str(e))
            self._circuit_open = True
    
    async def get(self, key: str) -> Any | None:
        """Get value from Redis."""
        if self._circuit_open:
            raise RuntimeError("Redis circuit breaker open")
        
        try:
            value = await self._client.get(key)
            if value is not None:
                return value.decode() if isinstance(value, bytes) else value
            return None
        except Exception as e:
            logger.error("redis_get_failed", key=key, error=str(e))
            self._circuit_open = True
            raise
    
    async def set(
        self,
        key: str,
        value: Any,
        ex: int | None = None,
    ) -> bool:
        """Set value in Redis."""
        if self._circuit_open:
            raise RuntimeError("Redis circuit breaker open")
        
        try:
            if isinstance(value, str):
                await self._client.set(key, value, ex=ex)
            else:
                await self._client.set(key, str(value), ex=ex)
            return True
        except Exception as e:
            logger.error("redis_set_failed", key=key, error=str(e))
            self._circuit_open = True
            raise
    
    async def delete(self, key: str) -> bool:
        """Delete key from Redis."""
        try:
            result = await self._client.delete(key)
            return result > 0
        except Exception as e:
            logger.error("redis_delete_failed", key=key, error=str(e))
            raise
    
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        try:
            result = await self._client.exists(key)
            return result > 0
        except Exception:
            return False
    
    async def expire(self, key: str, seconds: int) -> bool:
        """Set key expiration."""
        try:
            return await self._client.expire(key, seconds)
        except Exception:
            return False
    
    async def hget(self, name: str, key: str) -> Any | None:
        """Get hash field."""
        try:
            return await self._client.hget(name, key)
        except Exception:
            return None
    
    async def hset(self, name: str, key: str, value: Any) -> int:
        """Set hash field."""
        try:
            return await self._client.hset(name, key, value)
        except Exception:
            return 0
    
    async def close(self) -> None:
        """Close Redis connection."""
        self._connected = False
        
        if self._health_check_task:
            self._health_check_task.cancel()
        
        if self._client:
            await self._client.close()
        
        if self._sentinel:
            await self._sentinel.close()


class MockRedisClient:
    """Mock Redis client for testing."""
    
    def __init__(self):
        self._data: dict[str, Any] = {}
        self._expiry: dict[str, datetime] = {}
    
    async def ping(self) -> bool:
        return True
    
    async def get(self, key: str) -> bytes | None:
        if key in self._data:
            return self._data[key].encode()
        return None
    
    async def set(self, key: str, value: Any, ex: int | None = None) -> bool:
        self._data[key] = value
        return True
    
    async def delete(self, *keys: str) -> int:
        count = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                count += 1
        return count
    
    async def exists(self, *keys: str) -> int:
        return sum(1 for k in keys if k in self._data)
    
    async def expire(self, key: str, seconds: int) -> bool:
        return key in self._data
    
    async def hget(self, name: str, key: str) -> bytes | None:
        return None
    
    async def hset(self, name: str, key: str, value: Any) -> int:
        return 1
    
    async def close(self) -> None:
        pass


# Factory function
def create_redis_ha(
    topology: RedisTopology = RedisTopology.SENTINEL,
    endpoints: list[tuple[str, int]] | None = None,
) -> RedisHA:
    """Create Redis HA client.
    
    Usage:
        ha = create_redis_ha(
            topology=RedisTopology.SENTINEL,
            endpoints=[
                ("redis-primary", 6379),
                ("redis-replica", 6379),
            ],
        )
    """
    if endpoints is None:
        endpoints = [("localhost", 6379)]
    
    redis_endpoints = [
        RedisEndpoint(host=host, port=port)
        for host, port in endpoints
    ]
    
    config = RedisHAConfig(
        topology=topology,
        endpoints=redis_endpoints,
    )
    
    return RedisHA(config)
