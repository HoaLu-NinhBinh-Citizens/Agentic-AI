"""Reconciliation Engine with vector clock conflict resolution.

Resolves conflicts between cache entries from different sources.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from src.infrastructure.cache.tool.types import CacheEntry, VectorClock

logger = logging.getLogger(__name__)


@dataclass
class ReconciliationConfig:
    """Configuration for reconciliation."""

    max_clock_drift_seconds: float = 60.0
    conflict_resolution: str = "last_write_wins"
    enable_clock_check: bool = True


class ConflictError(Exception):
    """Conflict detected during reconciliation."""

    pass


class ReconciliationEngine:
    """Reconciliation engine with vector clock.

    Vector clock operations:
    - increment(node_id): Increment clock for node
    - merge(other): Merge another vector clock
    - happens_before(other): Check causal ordering
    - is_concurrent(other): Check for concurrent updates

    Conflict resolution strategies:
    - last_write_wins: Use entry with latest timestamp
    - causal: Use entry with causal precedence
    - merge: Merge values (requires mergeable types)
    """

    def __init__(self, config: ReconciliationConfig | None = None) -> None:
        self.config = config or ReconciliationConfig()

        self._node_id = f"node_{int(time.time() * 1000)}"
        self._vector_clock = VectorClock()
        self._local_clock = VectorClock()

        self._conflicts_resolved = 0
        self._conflicts_detected = 0

    @property
    def node_id(self) -> str:
        """Get this node's ID."""
        return self._node_id

    def increment_clock(self) -> None:
        """Increment local vector clock."""
        self._vector_clock.increment(self._node_id)
        self._local_clock.increment(self._node_id)

    def merge_clock(self, remote_clock: dict[str, int]) -> None:
        """Merge a remote vector clock.

        Args:
            remote_clock: Remote vector clock dictionary
        """
        self._vector_clock.merge(remote_clock)
        self._local_clock.merge(remote_clock)

    def get_clock(self) -> dict[str, int]:
        """Get current vector clock."""
        return self._vector_clock.to_dict()

    def get_local_clock(self) -> dict[str, int]:
        """Get local vector clock (without remote merges)."""
        return self._local_clock.to_dict()

    def happens_before(self, other: dict[str, int]) -> bool:
        """Check if local clock happens-before another clock.

        Args:
            other: Another vector clock dictionary

        Returns:
            True if local happens-before other
        """
        other_clock = VectorClock.from_dict(other)
        return self._vector_clock.happens_before(other_clock)

    def is_concurrent(self, other: dict[str, int]) -> bool:
        """Check if local clock is concurrent with another.

        Args:
            other: Another vector clock dictionary

        Returns:
            True if concurrent (neither happens-before the other)
        """
        other_clock = VectorClock.from_dict(other)
        return self._vector_clock.is_concurrent(other_clock)

    def resolve(
        self,
        local_entry: CacheEntry,
        remote_entry: CacheEntry,
    ) -> CacheEntry:
        """Resolve conflict between two entries.

        Args:
            local_entry: Local cache entry
            remote_entry: Remote cache entry

        Returns:
            Resolved cache entry

        Raises:
            ConflictError: If conflict cannot be resolved
        """
        self._conflicts_detected += 1

        if not self.config.enable_clock_check:
            return self._resolve_by_timestamp(local_entry, remote_entry)

        local_clock = local_entry.vector_clock
        remote_clock = remote_entry.vector_clock

        if not local_clock:
            return remote_entry

        if not remote_clock:
            return local_entry

        if self.happens_before(remote_clock):
            return remote_entry

        if self.is_concurrent(remote_clock):
            return self._resolve_concurrent(local_entry, remote_entry)

        return local_entry

    def _resolve_concurrent(
        self,
        local_entry: CacheEntry,
        remote_entry: CacheEntry,
    ) -> CacheEntry:
        """Resolve concurrent entries.

        Args:
            local_entry: Local entry
            remote_entry: Remote entry

        Returns:
            Resolved entry
        """
        self._conflicts_resolved += 1

        if self.config.conflict_resolution == "last_write_wins":
            return self._resolve_by_timestamp(local_entry, remote_entry)

        if self.config.conflict_resolution == "causal":
            return self._resolve_causal(local_entry, remote_entry)

        if self.config.conflict_resolution == "merge":
            return self._resolve_merge(local_entry, remote_entry)

        return self._resolve_by_timestamp(local_entry, remote_entry)

    def _resolve_by_timestamp(
        self,
        local_entry: CacheEntry,
        remote_entry: CacheEntry,
    ) -> CacheEntry:
        """Resolve by timestamp (last write wins).

        Args:
            local_entry: Local entry
            remote_entry: Remote entry

        Returns:
            Entry with latest timestamp
        """
        if remote_entry.created_at > local_entry.created_at:
            return remote_entry
        return local_entry

    def _resolve_causal(
        self,
        local_entry: CacheEntry,
        remote_entry: CacheEntry,
    ) -> CacheEntry:
        """Resolve by causal ordering.

        Args:
            local_entry: Local entry
            remote_entry: Remote entry

        Returns:
            Entry with causal precedence
        """
        if self.happens_before(remote_entry.vector_clock):
            return remote_entry
        return local_entry

    def _resolve_merge(
        self,
        local_entry: CacheEntry,
        remote_entry: CacheEntry,
    ) -> CacheEntry:
        """Attempt to merge entries.

        Args:
            local_entry: Local entry
            remote_entry: Remote entry

        Returns:
            Merged entry or one of the originals
        """
        try:
            if isinstance(local_entry.value, dict) and isinstance(remote_entry.value, dict):
                merged_value = {**local_entry.value, **remote_entry.value}

                local_clock = VectorClock.from_dict(local_entry.vector_clock)
                remote_clock = VectorClock.from_dict(remote_entry.vector_clock)
                local_clock.merge(remote_clock.to_dict())

                return CacheEntry(
                    key=local_entry.key,
                    value=merged_value,
                    state=local_entry.state,
                    created_at=max(local_entry.created_at, remote_entry.created_at),
                    expires_at=local_entry.expires_at or remote_entry.expires_at,
                    vector_clock=local_clock.to_dict(),
                    metadata={**local_entry.metadata, **remote_entry.metadata},
                )

        except Exception as e:
            logger.warning(f"Merge failed: {e}")

        return self._resolve_by_timestamp(local_entry, remote_entry)

    def should_refresh(
        self,
        entry: CacheEntry,
        max_drift: float | None = None,
    ) -> bool:
        """Check if entry should be refreshed due to clock drift.

        Args:
            entry: Cache entry
            max_drift: Maximum allowed clock drift

        Returns:
            True if should refresh
        """
        if not self.config.enable_clock_check:
            return False

        max_drift = max_drift or self.config.max_clock_drift_seconds

        entry_clock = entry.vector_clock
        if not entry_clock:
            return True

        now = time.time()
        latest_timestamp = max(entry_clock.values()) if entry_clock else 0

        return now - latest_timestamp > max_drift

    def attach_clock(self, entry: CacheEntry) -> CacheEntry:
        """Attach current vector clock to entry.

        Args:
            entry: Cache entry

        Returns:
            Entry with attached vector clock
        """
        self.increment_clock()
        entry.vector_clock = self.get_clock()
        return entry

    def get_stats(self) -> dict[str, Any]:
        """Get reconciliation statistics."""
        return {
            "node_id": self._node_id,
            "conflicts_detected": self._conflicts_detected,
            "conflicts_resolved": self._conflicts_resolved,
            "conflict_rate": (
                self._conflicts_resolved / self._conflicts_detected
                if self._conflicts_detected > 0
                else 0.0
            ),
            "vector_clock": self.get_clock(),
            "config": {
                "max_clock_drift_seconds": self.config.max_clock_drift_seconds,
                "conflict_resolution": self.config.conflict_resolution,
            },
        }
