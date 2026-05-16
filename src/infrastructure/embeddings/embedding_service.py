"""EmbeddingService for generating text embeddings using Ollama bge-m3.

Features:
|- Async HTTP via reused aiohttp.ClientSession
|- LRU cache with configurable maxsize
|- Retry logic with exponential backoff + jitter
|- Dynamic dimension handling
|- Embedding validation
|- Structured error codes for agent error handling
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
from collections import OrderedDict
from enum import Enum
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


class EmbeddingErrorCode(str, Enum):
    """Error codes for embedding operations.
    
    Maps to SemanticMemory ErrorCode:
    - TIMEOUT -> EMBEDDING_TIMEOUT
    - NETWORK_ERROR -> EMBEDDING_NETWORK_ERROR
    - SERVICE_UNAVAILABLE -> OLLAMA_UNAVAILABLE
    """
    NONE = "NONE"
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    HTTP_ERROR = "HTTP_ERROR"
    EMPTY_RESULT = "EMPTY_RESULT"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


class EmbeddingCache:
    """Simple LRU cache for embeddings."""

    def __init__(self, maxsize: int = 4096) -> None:
        """Initialize the cache.

        Args:
            maxsize: Maximum number of entries.
        """
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._maxsize = maxsize
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> list[float] | None:
        """Get embedding from cache.

        Args:
            key: Cache key (raw text hash).

        Returns:
            Cached embedding or None.
        """
        async with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            return None

    async def put(self, key: str, embedding: list[float]) -> None:
        """Put embedding in cache.

        Args:
            key: Cache key.
            embedding: Embedding vector.
        """
        async with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                if len(self._cache) >= self._maxsize:
                    self._cache.popitem(last=False)
                self._cache[key] = embedding

    async def clear(self) -> None:
        """Clear the cache."""
        async with self._lock:
            self._cache.clear()

    @property
    def size(self) -> int:
        """Get current cache size."""
        return len(self._cache)


class EmbeddingService:
    """Service for generating text embeddings using Ollama.

    Uses bge-m3 model for high-quality multilingual embeddings.
    
    Agent Error Handling:
        - last_error_code: Last error code (EmbeddingErrorCode)
        - Use with SemanticMemory ErrorCode for retry decisions
    """

    DEFAULT_MODEL = "bge-m3:latest"
    DEFAULT_URL = "http://localhost:11434/api/embeddings"
    TIMEOUT_SECONDS = 3.0
    MAX_RETRIES = 2
    RETRY_DELAY = 0.1

    def __init__(
        self,
        ollama_url: str = DEFAULT_URL,
        model: str = DEFAULT_MODEL,
        cache_maxsize: int = 4096,
    ) -> None:
        """Initialize the embedding service.

        Args:
            ollama_url: Ollama API URL.
            model: Model name for embeddings.
            cache_maxsize: Maximum cache size.
        """
        self._url = ollama_url
        self._model = model
        self._session: aiohttp.ClientSession | None = None
        self._cache = EmbeddingCache(maxsize=cache_maxsize)
        self._dimension: int | None = None
        self._init_lock = asyncio.Lock()
        self._initialized = False
        self._last_error_code: EmbeddingErrorCode = EmbeddingErrorCode.NONE

    @property
    def last_error_code(self) -> EmbeddingErrorCode:
        """Get the last error code for agent consumption."""
        return self._last_error_code

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the HTTP session.

        Returns:
            aiohttp ClientSession.
        """
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.TIMEOUT_SECONDS)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _ensure_initialized(self) -> None:
        """Ensure service is initialized."""
        async with self._init_lock:
            if not self._initialized:
                try:
                    session = await self._get_session()
                    test_embedding = await self.embed("init")
                    if test_embedding:
                        self._dimension = len(test_embedding)
                        self._initialized = True
                        logger.info("EmbeddingService initialized with dimension %d", self._dimension)
                except Exception as e:
                    logger.error("Failed to initialize EmbeddingService: %s", str(e))
                    raise

    @property
    def dimension(self) -> int | None:
        """Get embedding dimension."""
        return self._dimension

    def _make_cache_key(self, text: str) -> str:
        """Create cache key from text.

        Args:
            text: Text to hash.

        Returns:
            Cache key (hash).
        """
        return hashlib.sha256(text.encode()).hexdigest()

    def _map_error_code(self, code: EmbeddingErrorCode) -> str | None:
        """Map EmbeddingErrorCode to SemanticMemory ErrorCode string.
        
        Args:
            code: EmbeddingErrorCode to map.
            
        Returns:
            SemanticMemory ErrorCode string or None.
        """
        mapping = {
            EmbeddingErrorCode.TIMEOUT: "EMBEDDING_TIMEOUT",
            EmbeddingErrorCode.NETWORK_ERROR: "EMBEDDING_NETWORK_ERROR",
            EmbeddingErrorCode.SERVICE_UNAVAILABLE: "OLLAMA_UNAVAILABLE",
            EmbeddingErrorCode.HTTP_ERROR: "OLLAMA_UNAVAILABLE",
            EmbeddingErrorCode.EMPTY_RESULT: "OLLAMA_UNAVAILABLE",
        }
        return mapping.get(code)

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for text.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector, or empty list on failure.
            Check last_error_code for error details.
        """
        self._last_error_code = EmbeddingErrorCode.NONE

        if not text or not text.strip():
            return []

        cache_key = self._make_cache_key(text)
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached

        for attempt in range(self.MAX_RETRIES):
            try:
                session = await self._get_session()
                payload = {"model": self._model, "prompt": text}

                async with session.post(self._url, json=payload) as response:
                    if response.status != 200:
                        text_response = await response.text()
                        logger.warning(
                            "Embedding request failed with status %d: %s",
                            response.status,
                            text_response,
                        )
                        if response.status >= 500:
                            self._last_error_code = EmbeddingErrorCode.SERVICE_UNAVAILABLE
                        else:
                            self._last_error_code = EmbeddingErrorCode.HTTP_ERROR
                        if attempt < self.MAX_RETRIES - 1:
                            delay = min(1.0, 0.1 * (2 ** attempt))
                            await asyncio.sleep(delay + random.uniform(0, 0.05))
                            continue
                        return []

                    data = await response.json()
                    embedding = data.get("embedding", [])

                    if not isinstance(embedding, list) or len(embedding) == 0:
                        logger.error("Empty embedding returned from Ollama")
                        self._last_error_code = EmbeddingErrorCode.EMPTY_RESULT
                        if attempt < self.MAX_RETRIES - 1:
                            delay = min(1.0, 0.1 * (2 ** attempt))
                            await asyncio.sleep(delay + random.uniform(0, 0.05))
                            continue
                        return []

                    logger.debug(
                        "memory_embedding_dimension: dim=%d",
                        len(embedding),
                    )

                    await self._cache.put(cache_key, embedding)
                    if self._dimension is None:
                        self._dimension = len(embedding)
                    return embedding

            except asyncio.TimeoutError:
                logger.warning(
                    "Embedding request timed out (attempt %d/%d)",
                    attempt + 1,
                    self.MAX_RETRIES,
                )
                self._last_error_code = EmbeddingErrorCode.TIMEOUT
                if attempt < self.MAX_RETRIES - 1:
                    delay = min(1.0, 0.1 * (2 ** attempt))
                    await asyncio.sleep(delay + random.uniform(0, 0.05))
                    continue
            except aiohttp.ClientError as e:
                logger.error(
                    "Embedding request network error (attempt %d/%d): %s",
                    attempt + 1,
                    self.MAX_RETRIES,
                    str(e),
                )
                self._last_error_code = EmbeddingErrorCode.NETWORK_ERROR
                if attempt < self.MAX_RETRIES - 1:
                    delay = min(1.0, 0.1 * (2 ** attempt))
                    await asyncio.sleep(delay + random.uniform(0, 0.05))
                    continue
            except Exception as e:
                logger.error(
                    "Embedding request failed (attempt %d/%d): %s",
                    attempt + 1,
                    self.MAX_RETRIES,
                    str(e),
                )
                self._last_error_code = EmbeddingErrorCode.NETWORK_ERROR
                if attempt < self.MAX_RETRIES - 1:
                    delay = min(1.0, 0.1 * (2 ** attempt))
                    await asyncio.sleep(delay + random.uniform(0, 0.05))
                    continue

        logger.error("Embedding failed after %d attempts for text: %s", self.MAX_RETRIES, text[:100])
        return []

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors.
        """
        results = []
        for text in texts:
            embedding = await self.embed(text)
            results.append(embedding)
        return results

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def health_check(self) -> bool:
        """Check if the embedding service is healthy.

        Returns:
            True if service is healthy.
        """
        try:
            result = await self.embed("health check")
            return len(result) > 0
        except Exception as e:
            logger.warning("EmbeddingService health check failed: %s", str(e))
            return False

    async def get_stats(self) -> dict[str, Any]:
        """Get service statistics.

        Returns:
            Statistics dictionary.
        """
        return {
            "cache_size": self._cache.size,
            "cache_maxsize": self._cache._maxsize,
            "dimension": self._dimension,
            "model": self._model,
            "url": self._url,
            "last_error_code": self._last_error_code.value,
        }
