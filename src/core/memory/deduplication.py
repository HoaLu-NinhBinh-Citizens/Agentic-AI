"""Deduplication engine with window-based cosine similarity and optional Bloom filter.

Features:
- Window-based semantic dedup (compares against last N embeddings)
- Optional Bloom filter for exact-match dedup
- Configurable similarity threshold
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)

COSINE_THRESHOLD = 0.95
DEFAULT_WINDOW_SIZE = 20


class DeduplicationEngine:
    """Engine for detecting and filtering duplicate content."""

    def __init__(
        self,
        window_size: int = DEFAULT_WINDOW_SIZE,
        enable_bloom: bool = True,
        bloom_capacity: int = 100000,
        bloom_error_rate: float = 0.01,
    ) -> None:
        """Initialize the deduplication engine.

        Args:
            window_size: Number of recent embeddings to compare against.
            enable_bloom: Whether to enable Bloom filter for exact dedup.
            bloom_capacity: Expected capacity for Bloom filter.
            bloom_error_rate: Acceptable false positive rate for Bloom filter.
        """
        self._window_size = window_size
        self._enable_bloom = enable_bloom
        self._bloom_filter: BloomFilter | None = None
        self._recent_embeddings: deque[tuple[str, list[float]]] = deque(maxlen=window_size)
        self._recent_content: deque[str] = deque(maxlen=window_size)
        self._lock = asyncio.Lock()

        if enable_bloom:
            try:
                from pybloom_live import BloomFilter as BF
                self._bloom_filter = BF(capacity=bloom_capacity, error_rate=bloom_error_rate)
                logger.info(
                    "memory_bloom_initialized: capacity=%d, error_rate=%.4f",
                    bloom_capacity,
                    bloom_error_rate,
                )
            except ImportError:
                logger.warning(
                    "pybloom_live not installed, Bloom filter disabled. "
                    "Install with: pip install pybloom-live"
                )
                self._enable_bloom = False

    async def check_exact_duplicate(self, content: str) -> bool:
        """Check if content is an exact duplicate using Bloom filter.

        Args:
            content: Content to check.

        Returns:
            True if exact duplicate detected.
        """
        if not self._enable_bloom or self._bloom_filter is None:
            return False

        content_hash = self._compute_hash(content)
        return content_hash in self._bloom_filter

    async def add_exact(self, content: str) -> None:
        """Add content to Bloom filter.

        Args:
            content: Content to add.
        """
        if not self._enable_bloom or self._bloom_filter is None:
            return

        content_hash = self._compute_hash(content)
        self._bloom_filter.add(content_hash)

    def _compute_hash(self, content: str) -> str:
        """Compute hash of content.

        Args:
            content: Content to hash.

        Returns:
            SHA256 hash.
        """
        return hashlib.sha256(content.encode()).hexdigest()

    async def check_semantic_duplicate(
        self,
        embedding: list[float],
        content: str | None = None,
    ) -> bool:
        """Check if embedding is semantically similar to recent embeddings.

        Uses cosine similarity against the sliding window of recent embeddings.

        Args:
            embedding: Embedding vector.
            content: Optional content for logging.

        Returns:
            True if duplicate detected.
        """
        if not self._recent_embeddings:
            return False

        query_norm = self._normalize_vector(embedding)
        if query_norm == 0:
            return False

        for _, recent_embedding in self._recent_embeddings:
            similarity = self._cosine_similarity(query_norm, self._normalize_vector(recent_embedding))
            if similarity > COSINE_THRESHOLD:
                logger.info(
                    "memory_store_dedup_skipped: semantic duplicate detected (similarity=%.3f)",
                    similarity,
                )
                return True

        return False

    async def add_embedding(
        self,
        embedding: list[float],
        content: str | None = None,
    ) -> None:
        """Add embedding to the sliding window.

        Args:
            embedding: Embedding vector.
            content: Optional content for logging.
        """
        async with self._lock:
            self._recent_embeddings.append((content or "", embedding.copy()))
            if content:
                self._recent_content.append(content)

    async def check_and_add(
        self,
        content: str,
        embedding: list[float],
    ) -> tuple[bool, str]:
        """Check for duplicates and add if not duplicate.

        Pass an empty list for embedding to skip semantic dedup (bloom-only check).
        This is an intentional optimization: bloom filter catches exact duplicates cheaply
        before spending compute on embedding generation.
        """
        if await self.check_exact_duplicate(content):
            return True, "bloom"

        if embedding and await self.check_semantic_duplicate(embedding, content):
            return True, "cosine"

        await self.add_exact(content)
        await self.add_embedding(embedding, content)

        return False, ""

    async def get_recent_content(self, limit: int = 20) -> list[str]:
        """Get recent content for debugging.

        Args:
            limit: Maximum number of items to return.

        Returns:
            List of recent content strings.
        """
        async with self._lock:
            return list(self._recent_content)[:limit]

    def _normalize_vector(self, vector: list[float]) -> list[float]:
        """Normalize vector to unit length.

        Args:
            vector: Input vector.

        Returns:
            Normalized vector.
        """
        magnitude = math.sqrt(sum(x * x for x in vector))
        if magnitude == 0:
            logger.warning("Attempted to normalize a zero vector — returning zero vector as-is")
            return vector
        return [x / magnitude for x in vector]

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Compute cosine similarity between two vectors.

        Args:
            vec1: First vector.
            vec2: Second vector.

        Returns:
            Cosine similarity (0 to 1).
        """
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        return dot_product

    async def reset(self) -> None:
        """Reset the deduplication engine."""
        async with self._lock:
            self._recent_embeddings.clear()
            self._recent_content.clear()
            if self._bloom_filter is not None:
                if hasattr(self._bloom_filter, 'close'):
                    self._bloom_filter.close()
                self._bloom_filter = None

    async def get_stats(self) -> dict[str, Any]:
        """Get deduplication statistics.

        Returns:
            Statistics dictionary.
        """
        return {
            "window_size": self._window_size,
            "recent_count": len(self._recent_embeddings),
            "bloom_enabled": self._enable_bloom,
            "bloom_filter_active": self._bloom_filter is not None,
        }


class BloomFilter:
    """Simple Bloom filter implementation for exact dedup.

    This is a fallback when pybloom_live is not available.
    """

    def __init__(self, capacity: int, error_rate: float) -> None:
        """Initialize Bloom filter.

        Args:
            capacity: Expected number of items.
            error_rate: Acceptable false positive rate.
        """
        self._capacity = capacity
        self._error_rate = error_rate
        self._size = self._calculate_size(capacity, error_rate)
        self._hash_count = self._calculate_hash_count(self._size, capacity)
        self._bits = [False] * self._size

    def _calculate_size(self, n: int, p: float) -> int:
        """Calculate optimal bit array size.

        Args:
            n: Expected items.
            p: False positive rate.

        Returns:
            Bit array size.
        """
        m = -((n * math.log(p)) / (math.log(2) ** 2))
        return int(m) + 1

    def _calculate_hash_count(self, m: int, n: int) -> int:
        """Calculate optimal hash count.

        Args:
            m: Bit array size.
            n: Expected items.

        Returns:
            Number of hash functions.
        """
        k = (m / n) * math.log(2)
        return max(1, int(k))

    def add(self, item: str) -> None:
        """Add item to filter.

        Args:
            item: Item to add.
        """
        for i in self._get_hash_indexes(item):
            self._bits[i] = True

    def __contains__(self, item: str) -> bool:
        """Check if item might be in filter.

        Args:
            item: Item to check.

        Returns:
            True if possibly in filter.
        """
        return all(self._bits[i] for i in self._get_hash_indexes(item))

    def _get_hash_indexes(self, item: str) -> list[int]:
        """Get hash indexes for item.

        Args:
            item: Item to hash.

        Returns:
            List of bit indexes.
        """
        result = []
        for seed in range(self._hash_count):
            h = hashlib.sha256(f"{item}_{seed}".encode()).hexdigest()
            result.append(int(h, 16) % self._size)
        return result

    def close(self) -> None:
        """Close the filter."""
        pass
