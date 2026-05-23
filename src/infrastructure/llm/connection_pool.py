"""Connection Pool for LLM Providers.

Provides HTTP connection pooling to reduce connection overhead for LLM API calls.
Uses aiohttp for async HTTP connections.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# Try to import aiohttp for async HTTP
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    logger.warning("aiohttp_not_installed")


@dataclass
class ConnectionPoolConfig:
    """Configuration for connection pool."""
    max_connections: int = 100  # Total connections
    max_connections_per_host: int = 30  # Per-host limit
    keepalive_timeout: int = 30  # Seconds to keep connection alive
    ttl_seconds: int = 300  # Connection TTL


class ConnectionPool:
    """Async HTTP connection pool with configurable limits.
    
    Usage:
        pool = ConnectionPool(config=ConnectionPoolConfig(max_connections=50))
        await pool.start()
        
        async with pool.get_session() as session:
            async with session.get(url) as response:
                data = await response.json()
        
        await pool.stop()
    """
    
    def __init__(self, config: ConnectionPoolConfig | None = None):
        self._config = config or ConnectionPoolConfig()
        self._session: aiohttp.ClientSession | None = None
        self._connector: aiohttp.TCPConnector | None = None
        self._running = False
        self._lock = asyncio.Lock()
        self._metrics = {
            "requests": 0,
            "errors": 0,
            "connection_created": 0,
        }
    
    async def start(self) -> None:
        """Start the connection pool."""
        if not HAS_AIOHTTP:
            raise RuntimeError("aiohttp required for connection pooling")
        
        async with self._lock:
            if self._running:
                return
            
            self._connector = aiohttp.TCPConnector(
                limit=self._config.max_connections,
                limit_per_host=self._config.max_connections_per_host,
                ttl_dns_cache=self._config.ttl_seconds,
                keepalive_timeout=self._config.keepalive_timeout,
            )
            
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=aiohttp.ClientTimeout(total=120),
            )
            
            self._running = True
            logger.info(
                "connection_pool_started",
                max_connections=self._config.max_connections,
                max_per_host=self._config.max_connections_per_host,
            )
    
    async def stop(self) -> None:
        """Stop the connection pool."""
        async with self._lock:
            if not self._running:
                return
            
            if self._session:
                await self._session.close()
                self._session = None
            
            if self._connector:
                await self._connector.close()
                self._connector = None
            
            self._running = False
            logger.info("connection_pool_stopped", metrics=self._metrics)
    
    @property
    def session(self) -> aiohttp.ClientSession:
        """Get the shared session."""
        if not self._session:
            raise RuntimeError("Connection pool not started")
        return self._session
    
    @property
    def is_running(self) -> bool:
        """Check if pool is running."""
        return self._running
    
    def get_metrics(self) -> dict[str, Any]:
        """Get pool metrics."""
        return {
            **self._metrics,
            "running": self._running,
            "max_connections": self._config.max_connections,
            "max_per_host": self._config.max_connections_per_host,
        }


# Global connection pool
_global_pool: ConnectionPool | None = None
_pool_lock = asyncio.Lock()


async def get_connection_pool() -> ConnectionPool:
    """Get the global connection pool instance."""
    global _global_pool
    
    async with _pool_lock:
        if _global_pool is None:
            _global_pool = ConnectionPool()
            await _global_pool.start()
        return _global_pool


async def shutdown_connection_pool() -> None:
    """Shutdown the global connection pool."""
    global _global_pool
    
    async with _pool_lock:
        if _global_pool:
            await _global_pool.stop()
            _global_pool = None


@dataclass
class LLMProviderPoolConfig:
    """Configuration for LLM provider pool."""
    max_concurrent_requests: int = 10  # Per-provider concurrency limit
    request_timeout: float = 120.0  # Request timeout in seconds
    retry_attempts: int = 3  # Number of retry attempts
    retry_backoff_base: float = 1.0  # Base for exponential backoff
    connection_pool_size: int = 20  # HTTP connections per provider


class LLMProviderPool:
    """Pool for managing multiple LLM provider instances.
    
    Provides:
    - Connection pooling per provider
    - Concurrency limiting
    - Automatic retry with backoff
    - Metrics collection
    
    Usage:
        pool = LLMProviderPool()
        await pool.start()
        
        result = await pool.call_provider("openai", "gpt-4", prompt)
        
        await pool.stop()
    """
    
    def __init__(self, config: LLMProviderPoolConfig | None = None):
        self._config = config or LLMProviderPoolConfig()
        self._connection_pool = ConnectionPool(
            ConnectionPoolConfig(max_connections=self._config.connection_pool_size)
        )
        self._running = False
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._metrics: dict[str, dict] = {}
        self._lock = asyncio.Lock()
    
    async def start(self) -> None:
        """Start the provider pool."""
        await self._connection_pool.start()
        self._running = True
        logger.info("llm_provider_pool_started")
    
    async def stop(self) -> None:
        """Stop the provider pool."""
        self._running = False
        await self._connection_pool.stop()
        logger.info("llm_provider_pool_stopped")
    
    def _get_semaphore(self, provider: str) -> asyncio.Semaphore:
        """Get or create semaphore for provider."""
        if provider not in self._semaphores:
            self._semaphores[provider] = asyncio.Semaphore(
                self._config.max_concurrent_requests
            )
        return self._semaphores[provider]
    
    def _get_provider_metrics(self, provider: str) -> dict:
        """Get metrics for provider, creating if needed."""
        if provider not in self._metrics:
            self._metrics[provider] = {
                "requests": 0,
                "errors": 0,
                "retries": 0,
                "total_latency_ms": 0.0,
            }
        return self._metrics[provider]
    
    async def call_provider(
        self,
        provider: str,
        model: str,
        prompt: str,
        call_func: callable,
        *args,
        **kwargs,
    ) -> Any:
        """Call an LLM provider with pooling, concurrency control, and retry.
        
        Args:
            provider: Provider name (e.g., "openai", "anthropic")
            model: Model name
            prompt: Prompt to send
            call_func: Async function to call
            *args, **kwargs: Additional arguments for call_func
        
        Returns:
            Result from provider
            
        Raises:
            Exception: If all retries fail
        """
        if not self._running:
            raise RuntimeError("Provider pool not started")
        
        semaphore = self._get_semaphore(provider)
        metrics = self._get_provider_metrics(provider)
        
        async with semaphore:
            last_error = None
            
            for attempt in range(self._config.retry_attempts):
                start_time = asyncio.get_event_loop().time()
                
                try:
                    metrics["requests"] += 1
                    
                    result = await call_func(
                        session=self._connection_pool.session,
                        model=model,
                        prompt=prompt,
                        *args,
                        **kwargs,
                    )
                    
                    latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                    metrics["total_latency_ms"] += latency_ms
                    
                    return result
                    
                except Exception as e:
                    last_error = e
                    metrics["errors"] += 1
                    
                    if attempt < self._config.retry_attempts - 1:
                        metrics["retries"] += 1
                        backoff = self._config.retry_backoff_base * (2 ** attempt)
                        logger.warning(
                            "llm_provider_retry",
                            provider=provider,
                            model=model,
                            attempt=attempt + 1,
                            error=str(e),
                            backoff=backoff,
                        )
                        await asyncio.sleep(backoff)
                    else:
                        logger.error(
                            "llm_provider_failed",
                            provider=provider,
                            model=model,
                            error=str(e),
                        )
            
            raise last_error
    
    def get_metrics(self) -> dict[str, Any]:
        """Get all provider pool metrics."""
        return {
            "connection_pool": self._connection_pool.get_metrics(),
            "providers": dict(self._metrics),
            "running": self._running,
        }


# Global LLM provider pool
_global_provider_pool: LLMProviderPool | None = None
_provider_pool_lock = asyncio.Lock()


async def get_llm_provider_pool() -> LLMProviderPool:
    """Get the global LLM provider pool instance."""
    global _global_provider_pool
    
    async with _provider_pool_lock:
        if _global_provider_pool is None:
            _global_provider_pool = LLMProviderPool()
            await _global_provider_pool.start()
        return _global_provider_pool


async def shutdown_llm_provider_pool() -> None:
    """Shutdown the global LLM provider pool."""
    global _global_provider_pool
    
    async with _provider_pool_lock:
        if _global_provider_pool:
            await _global_provider_pool.stop()
            _global_provider_pool = None
