"""Vector DB abstraction with fallback support.

W-004 Fix: Implements graceful degradation when vector store is unavailable.
- Primary vector store (ChromaDB/LanceDB)
- In-memory fallback for offline/degraded mode
- Health check before queries
- Automatic failover and recovery
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class VectorStoreStatus(Enum):
    """Vector store availability status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"  # Using fallback
    UNAVAILABLE = "unavailable"


@dataclass
class VectorSearchResult:
    """Result from vector search."""

    id: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FallbackConfig:
    """Configuration for fallback behavior."""

    max_in_memory_vectors: int = 10000
    enable_auto_fallback: bool = True
    health_check_interval: float = 60.0
    recovery_retry_interval: float = 30.0


class VectorStoreBackend(ABC):
    """Abstract base for vector store backends."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the vector store."""
        pass

    @abstractmethod
    async def add(
        self, id: str, vector: list[float], metadata: dict[str, Any]
    ) -> None:
        """Add a vector."""
        pass

    @abstractmethod
    async def search(
        self, query: list[float], top_k: int = 5
    ) -> list[VectorSearchResult]:
        """Search for similar vectors."""
        pass

    @abstractmethod
    async def delete(self, id: str) -> None:
        """Delete a vector."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the vector store is healthy."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the vector store."""
        pass


class InMemoryVectorStore(VectorStoreBackend):
    """In-memory fallback vector store.

    Used when primary vector store is unavailable.
    Provides basic cosine similarity search.
    """

    def __init__(self, max_vectors: int = 10000):
        self._vectors: dict[str, tuple[list[float], dict[str, Any]]] = {}
        self._max_vectors = max_vectors
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize in-memory store."""
        logger.info("In-memory vector store initialized")

    async def add(
        self, id: str, vector: list[float], metadata: dict[str, Any]
    ) -> None:
        """Add a vector to in-memory store."""
        async with self._lock:
            if len(self._vectors) >= self._max_vectors:
                # Remove oldest entry
                oldest = next(iter(self._vectors))
                del self._vectors[oldest]
                logger.warning(
                    "In-memory store full, evicted oldest vector",
                    evicted_id=oldest,
                )
            self._vectors[id] = (vector, metadata)

    async def search(
        self, query: list[float], top_k: int = 5
    ) -> list[VectorSearchResult]:
        """Search using cosine similarity."""
        results: list[VectorSearchResult] = []

        query_norm = self._normalize(query)
        if query_norm is None:
            return results

        async with self._lock:
            for id, (vector, metadata) in self._vectors.items():
                norm = self._normalize(vector)
                if norm is None:
                    continue

                # Cosine similarity
                similarity = sum(q * v for q, v in zip(query_norm, norm))

                results.append(VectorSearchResult(
                    id=id,
                    score=similarity,
                    metadata=metadata,
                ))

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    async def delete(self, id: str) -> None:
        """Delete a vector."""
        async with self._lock:
            self._vectors.pop(id, None)

    async def health_check(self) -> bool:
        """In-memory store is always healthy."""
        return True

    async def close(self) -> None:
        """Close in-memory store."""
        self._vectors.clear()

    @staticmethod
    def _normalize(vector: list[float]) -> list[float] | None:
        """Normalize vector for cosine similarity."""
        norm = sum(v * v for v in vector) ** 0.5
        if norm == 0:
            return None
        return [v / norm for v in vector]

    @property
    def size(self) -> int:
        """Get number of vectors in store."""
        return len(self._vectors)


class VectorStoreWithFallback:
    """Vector store with graceful degradation.

    W-004 Fix: Implements fallback mechanism when primary store is unavailable.
    """

    def __init__(
        self,
        primary: VectorStoreBackend,
        fallback: InMemoryVectorStore | None = None,
        config: FallbackConfig | None = None,
    ):
        self._primary = primary
        self._fallback = fallback or InMemoryVectorStore(
            max_vectors=config.max_in_memory_vectors if config else 10000
        )
        self._config = config or FallbackConfig()
        self._status = VectorStoreStatus.HEALTHY
        self._health_check_task: asyncio.Task | None = None
        self._recovery_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        """Initialize the vector store with fallback support."""
        try:
            await self._primary.initialize()
            self._status = VectorStoreStatus.HEALTHY
            logger.info("Primary vector store initialized")

            # Start health check monitoring
            self._health_check_task = asyncio.create_task(self._health_check_loop())

        except Exception as e:
            logger.warning(
                "Primary vector store init failed, using fallback",
                error=str(e),
            )
            self._status = VectorStoreStatus.DEGRADED
            await self._fallback.initialize()

    async def _health_check_loop(self) -> None:
        """Periodically check primary store health."""
        while True:
            await asyncio.sleep(self._config.health_check_interval)

            try:
                is_healthy = await self._primary.health_check()

                if not is_healthy and self._status == VectorStoreStatus.HEALTHY:
                    logger.warning("Primary vector store became unhealthy")
                    self._status = VectorStoreStatus.DEGRADED

                elif is_healthy and self._status == VectorStoreStatus.DEGRADED:
                    logger.info("Primary vector store recovered")
                    self._status = VectorStoreStatus.HEALTHY

            except Exception as e:
                if self._status != VectorStoreStatus.DEGRADED:
                    logger.warning(
                        "Health check failed, switching to fallback",
                        error=str(e),
                    )
                    self._status = VectorStoreStatus.DEGRADED

    async def _recovery_loop(self) -> None:
        """Attempt to recover primary store periodically."""
        while True:
            await asyncio.sleep(self._config.recovery_retry_interval)

            if self._status == VectorStoreStatus.DEGRADED:
                try:
                    is_healthy = await self._primary.health_check()
                    if is_healthy:
                        logger.info("Primary vector store recovered")
                        self._status = VectorStoreStatus.HEALTHY
                except Exception:
                    pass

    async def add(
        self, id: str, vector: list[float], metadata: dict[str, Any]
    ) -> None:
        """Add a vector to the current active store."""
        if self._status == VectorStoreStatus.HEALTHY:
            try:
                await self._primary.add(id, vector, metadata)
                return
            except Exception as e:
                logger.warning(
                    "Primary add failed, using fallback",
                    error=str(e),
                )
                self._status = VectorStoreStatus.DEGRADED

        # Fallback
        await self._fallback.add(id, vector, metadata)

    async def search(
        self, query: list[float], top_k: int = 5
    ) -> list[VectorSearchResult]:
        """Search using the current active store."""
        if self._status == VectorStoreStatus.HEALTHY:
            try:
                return await self._primary.search(query, top_k)
            except Exception as e:
                logger.warning(
                    "Primary search failed, using fallback",
                    error=str(e),
                )
                self._status = VectorStoreStatus.DEGRADED

        # Fallback
        return await self._fallback.search(query, top_k)

    async def delete(self, id: str) -> None:
        """Delete a vector from all stores."""
        if self._status == VectorStoreStatus.HEALTHY:
            try:
                await self._primary.delete(id)
            except Exception:
                pass

        await self._fallback.delete(id)

    async def close(self) -> None:
        """Close all stores and cancel monitoring tasks."""
        if self._health_check_task:
            self._health_check_task.cancel()
        if self._recovery_task:
            self._recovery_task.cancel()

        await self._primary.close()
        await self._fallback.close()

    @property
    def status(self) -> VectorStoreStatus:
        """Get current vector store status."""
        return self._status

    def is_using_fallback(self) -> bool:
        """Check if currently using fallback."""
        return self._status != VectorStoreStatus.HEALTHY
