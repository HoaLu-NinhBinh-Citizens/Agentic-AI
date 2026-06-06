"""LLM fix suggestion cache.

Caches LLM-generated fixes by (rule_id, code_hash) to avoid
redundant API calls for the same issue pattern.

Features:
- In-memory LRU cache with configurable max size
- Optional SQLite persistence for cross-session caching
- Cache key based on rule_id + code content hash
- TTL (time-to-live) for cache entries
- Hit/miss statistics
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default cache settings
DEFAULT_MAX_SIZE = 500
DEFAULT_TTL_SECONDS = 86400 * 7  # 7 days


@dataclass
class CacheEntry:
    """A cached fix suggestion."""

    rule_id: str
    code_hash: str
    suggested_code: str
    explanation: str
    confidence: float
    alternatives: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    hit_count: int = 0

    def is_expired(self, ttl: float) -> bool:
        """Check if entry has exceeded TTL."""
        return (time.time() - self.created_at) > ttl

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "rule_id": self.rule_id,
            "code_hash": self.code_hash,
            "suggested_code": self.suggested_code,
            "explanation": self.explanation,
            "confidence": self.confidence,
            "alternatives": self.alternatives,
            "created_at": self.created_at,
            "hit_count": self.hit_count,
        }


@dataclass
class CacheStats:
    """Cache usage statistics."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    size: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "size": self.size,
            "hit_rate": round(self.hit_rate, 3),
        }


def _compute_code_hash(code: str) -> str:
    """Compute a stable hash for code content.

    Strips whitespace variations to match semantically equivalent code.
    """
    normalized = code.strip().replace("\r\n", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


class FixCache:
    """In-memory LRU cache for LLM fix suggestions.

    Caches by (rule_id, code_hash) so the same issue pattern
    doesn't require repeated LLM calls.
    """

    def __init__(
        self,
        max_size: int = DEFAULT_MAX_SIZE,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        persist_path: Optional[str | Path] = None,
    ):
        """Initialize the fix cache.

        Args:
            max_size: Maximum number of cached entries
            ttl_seconds: Time-to-live for entries in seconds
            persist_path: Optional SQLite path for persistence
        """
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._stats = CacheStats()
        self._persist_path = Path(persist_path) if persist_path else None

        if self._persist_path:
            self._init_db()
            self._load_from_db()

    def _make_key(self, rule_id: str, code: str) -> str:
        """Create cache key from rule_id and code content."""
        code_hash = _compute_code_hash(code)
        return f"{rule_id}:{code_hash}"

    def get(self, rule_id: str, code: str) -> Optional[CacheEntry]:
        """Look up a cached fix suggestion.

        Args:
            rule_id: The rule that triggered the finding
            code: The original code content

        Returns:
            CacheEntry if found and not expired, else None
        """
        key = self._make_key(rule_id, code)
        entry = self._cache.get(key)

        if entry is None:
            self._stats.misses += 1
            return None

        if entry.is_expired(self._ttl):
            # Expired — remove and return miss
            del self._cache[key]
            self._stats.misses += 1
            self._stats.size = len(self._cache)
            return None

        # Cache hit — move to end (most recent)
        self._cache.move_to_end(key)
        entry.hit_count += 1
        self._stats.hits += 1
        return entry

    def put(
        self,
        rule_id: str,
        code: str,
        suggested_code: str,
        explanation: str,
        confidence: float = 0.8,
        alternatives: Optional[list[str]] = None,
    ) -> CacheEntry:
        """Store a fix suggestion in the cache.

        Args:
            rule_id: The rule ID
            code: The original code
            suggested_code: The LLM-generated fix
            explanation: Explanation of the fix
            confidence: Confidence score
            alternatives: Alternative suggestions

        Returns:
            The created CacheEntry
        """
        key = self._make_key(rule_id, code)
        code_hash = _compute_code_hash(code)

        entry = CacheEntry(
            rule_id=rule_id,
            code_hash=code_hash,
            suggested_code=suggested_code,
            explanation=explanation,
            confidence=confidence,
            alternatives=alternatives or [],
        )

        # Evict if at capacity
        if len(self._cache) >= self._max_size:
            evicted_key, _ = self._cache.popitem(last=False)
            self._stats.evictions += 1
            logger.debug("Cache eviction: %s", evicted_key)

        self._cache[key] = entry
        self._stats.size = len(self._cache)

        # Persist if configured
        if self._persist_path:
            self._save_entry(key, entry)

        return entry

    def invalidate(self, rule_id: str, code: str) -> bool:
        """Remove a specific entry from the cache.

        Args:
            rule_id: Rule ID
            code: Original code

        Returns:
            True if entry was found and removed
        """
        key = self._make_key(rule_id, code)
        if key in self._cache:
            del self._cache[key]
            self._stats.size = len(self._cache)
            return True
        return False

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        self._stats.size = 0

    @property
    def stats(self) -> CacheStats:
        """Get cache statistics."""
        self._stats.size = len(self._cache)
        return self._stats

    # ─── SQLite Persistence ──────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Initialize SQLite database for persistence."""
        if not self._persist_path:
            return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._persist_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fix_cache (
                key TEXT PRIMARY KEY,
                rule_id TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                suggested_code TEXT NOT NULL,
                explanation TEXT NOT NULL,
                confidence REAL NOT NULL,
                alternatives TEXT NOT NULL DEFAULT '[]',
                created_at REAL NOT NULL,
                hit_count INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()

    def _load_from_db(self) -> None:
        """Load cached entries from SQLite."""
        if not self._persist_path or not self._persist_path.exists():
            return
        try:
            conn = sqlite3.connect(str(self._persist_path))
            cursor = conn.execute(
                "SELECT key, rule_id, code_hash, suggested_code, explanation, "
                "confidence, alternatives, created_at, hit_count FROM fix_cache "
                "ORDER BY created_at DESC LIMIT ?",
                (self._max_size,)
            )
            for row in cursor:
                key, rule_id, code_hash, suggested_code, explanation, \
                    confidence, alts_json, created_at, hit_count = row
                entry = CacheEntry(
                    rule_id=rule_id,
                    code_hash=code_hash,
                    suggested_code=suggested_code,
                    explanation=explanation,
                    confidence=confidence,
                    alternatives=json.loads(alts_json),
                    created_at=created_at,
                    hit_count=hit_count,
                )
                if not entry.is_expired(self._ttl):
                    self._cache[key] = entry
            conn.close()
            self._stats.size = len(self._cache)
        except Exception as e:
            logger.warning("Failed to load fix cache from DB: %s", e)

    def _save_entry(self, key: str, entry: CacheEntry) -> None:
        """Persist a single entry to SQLite."""
        if not self._persist_path:
            return
        try:
            conn = sqlite3.connect(str(self._persist_path))
            conn.execute(
                "INSERT OR REPLACE INTO fix_cache "
                "(key, rule_id, code_hash, suggested_code, explanation, "
                "confidence, alternatives, created_at, hit_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    key, entry.rule_id, entry.code_hash,
                    entry.suggested_code, entry.explanation,
                    entry.confidence, json.dumps(entry.alternatives),
                    entry.created_at, entry.hit_count,
                )
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Failed to persist fix cache entry: %s", e)
