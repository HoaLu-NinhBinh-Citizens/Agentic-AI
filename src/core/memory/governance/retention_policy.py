"""Retention policy and TTL management for memory governance.

Implements TTL-based retention policies for different memory types:
- Working memory: 1 hour
- Long-term memory: 30 days
- Episodic memory: 7 days
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MemoryType(str, Enum):
    """Types of memory with different retention policies."""

    WORKING = "working"
    LONG_TERM = "long_term"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


@dataclass
class MemoryTTL:
    """TTL configuration for a memory type."""

    memory_type: MemoryType
    ttl_seconds: int
    decay_enabled: bool = True
    min_confidence_threshold: float = 0.1
    auto_cleanup: bool = True

    @classmethod
    def default_policy(cls, memory_type: MemoryType) -> MemoryTTL:
        """Get default TTL policy for memory type.

        Args:
            memory_type: Type of memory.

        Returns:
            TTL configuration.
        """
        defaults = {
            MemoryType.WORKING: cls(
                memory_type=memory_type,
                ttl_seconds=3600,
                decay_enabled=True,
                min_confidence_threshold=0.1,
                auto_cleanup=True,
            ),
            MemoryType.LONG_TERM: cls(
                memory_type=memory_type,
                ttl_seconds=30 * 86400,
                decay_enabled=True,
                min_confidence_threshold=0.3,
                auto_cleanup=True,
            ),
            MemoryType.EPISODIC: cls(
                memory_type=memory_type,
                ttl_seconds=7 * 86400,
                decay_enabled=True,
                min_confidence_threshold=0.2,
                auto_cleanup=True,
            ),
            MemoryType.SEMANTIC: cls(
                memory_type=memory_type,
                ttl_seconds=90 * 86400,
                decay_enabled=False,
                min_confidence_threshold=0.5,
                auto_cleanup=False,
            ),
            MemoryType.PROCEDURAL: cls(
                memory_type=memory_type,
                ttl_seconds=180 * 86400,
                decay_enabled=False,
                min_confidence_threshold=0.5,
                auto_cleanup=False,
            ),
        }
        return defaults.get(memory_type, cls(memory_type=memory_type, ttl_seconds=86400))


@dataclass
class RetentionResult:
    """Result of a retention check operation."""

    fact_id: str
    memory_type: MemoryType
    is_expired: bool
    remaining_seconds: int
    should_delete: bool
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "fact_id": self.fact_id,
            "memory_type": self.memory_type.value,
            "is_expired": self.is_expired,
            "remaining_seconds": self.remaining_seconds,
            "should_delete": self.should_delete,
            "reason": self.reason,
        }


class RetentionPolicy:
    """Manages retention policies for different memory types.

    Implements TTL-based retention with configurable policies per memory type.
    """

    def __init__(
        self,
        policies: dict[MemoryType, MemoryTTL] | None = None,
    ) -> None:
        """Initialize retention policy manager.

        Args:
            policies: Custom TTL policies. Uses defaults if not provided.
        """
        self._policies: dict[MemoryType, MemoryTTL] = {}

        if policies:
            self._policies = policies
        else:
            for memory_type in MemoryType:
                self._policies[memory_type] = MemoryTTL.default_policy(memory_type)

        self._timestamps: dict[str, tuple[MemoryType, int]] = {}

    def register(
        self,
        fact_id: str,
        memory_type: MemoryType,
        created_at: int | None = None,
    ) -> None:
        """Register a fact with retention tracking.

        Args:
            fact_id: Unique fact identifier.
            memory_type: Type of memory.
            created_at: Creation timestamp. Uses now if not provided.
        """
        if created_at is None:
            created_at = int(time.time())

        self._timestamps[fact_id] = (memory_type, created_at)

    def check(self, fact_id: str) -> RetentionResult:
        """Check retention status for a fact.

        Args:
            fact_id: Fact identifier.

        Returns:
            RetentionResult with status and recommendations.
        """
        if fact_id not in self._timestamps:
            return RetentionResult(
                fact_id=fact_id,
                memory_type=MemoryType.WORKING,
                is_expired=False,
                remaining_seconds=0,
                should_delete=False,
                reason="Not registered",
            )

        memory_type, created_at = self._timestamps[fact_id]
        policy = self._policies.get(memory_type)

        if not policy:
            return RetentionResult(
                fact_id=fact_id,
                memory_type=memory_type,
                is_expired=False,
                remaining_seconds=0,
                should_delete=False,
                reason="No policy found",
            )

        current_time = int(time.time())
        age_seconds = current_time - created_at
        remaining_seconds = max(0, policy.ttl_seconds - age_seconds)
        is_expired = age_seconds >= policy.ttl_seconds

        return RetentionResult(
            fact_id=fact_id,
            memory_type=memory_type,
            is_expired=is_expired,
            remaining_seconds=remaining_seconds,
            should_delete=is_expired and policy.auto_cleanup,
            reason="TTL expired" if is_expired else "Still valid",
        )

    def check_batch(self, fact_ids: list[str]) -> list[RetentionResult]:
        """Check retention status for multiple facts.

        Args:
            fact_ids: List of fact identifiers.

        Returns:
            List of RetentionResult for each fact.
        """
        return [self.check(fact_id) for fact_id in fact_ids]

    def get_expired_facts(self, memory_type: MemoryType | None = None) -> list[str]:
        """Get all expired fact IDs.

        Args:
            memory_type: Optional filter by memory type.

        Returns:
            List of expired fact IDs.
        """
        expired = []

        for fact_id, (mem_type, _) in self._timestamps.items():
            if memory_type and mem_type != memory_type:
                continue

            result = self.check(fact_id)
            if result.is_expired:
                expired.append(fact_id)

        return expired

    def get_facts_to_cleanup(self) -> list[str]:
        """Get all facts that should be cleaned up.

        Returns:
            List of fact IDs for cleanup.
        """
        cleanup = []

        for fact_id, (mem_type, created_at) in self._timestamps.items():
            policy = self._policies.get(mem_type)
            if not policy or not policy.auto_cleanup:
                continue

            current_time = int(time.time())
            age_seconds = current_time - created_at

            if age_seconds >= policy.ttl_seconds:
                cleanup.append(fact_id)

        return cleanup

    def extend(
        self,
        fact_id: str,
        additional_seconds: int,
    ) -> bool:
        """Extend TTL for a fact.

        Args:
            fact_id: Fact identifier.
            additional_seconds: Seconds to add to TTL.

        Returns:
            True if extended, False if not found.
        """
        if fact_id not in self._timestamps:
            return False

        memory_type, created_at = self._timestamps[fact_id]
        new_created_at = created_at - additional_seconds
        self._timestamps[fact_id] = (memory_type, max(0, new_created_at))
        return True

    def get_ttl(self, memory_type: MemoryType) -> int:
        """Get TTL for a memory type.

        Args:
            memory_type: Type of memory.

        Returns:
            TTL in seconds.
        """
        policy = self._policies.get(memory_type)
        return policy.ttl_seconds if policy else 86400

    def set_policy(self, memory_type: MemoryType, policy: MemoryTTL) -> None:
        """Set custom policy for a memory type.

        Args:
            memory_type: Type of memory.
            policy: TTL policy configuration.
        """
        self._policies[memory_type] = policy

    def get_stats(self) -> dict[str, Any]:
        """Get retention statistics.

        Returns:
            Statistics dictionary.
        """
        by_type: dict[str, dict[str, Any]] = {}

        for memory_type in MemoryType:
            facts_in_type = [
                fid for fid, (mt, _) in self._timestamps.items()
                if mt == memory_type
            ]
            expired_in_type = [
                fid for fid in facts_in_type
                if self.check(fid).is_expired
            ]

            policy = self._policies.get(memory_type)
            by_type[memory_type.value] = {
                "total": len(facts_in_type),
                "expired": len(expired_in_type),
                "ttl_seconds": policy.ttl_seconds if policy else 0,
                "ttl_days": (policy.ttl_seconds // 86400) if policy else 0,
            }

        return {
            "total_registered": len(self._timestamps),
            "by_type": by_type,
        }

    def remove(self, fact_id: str) -> bool:
        """Remove a fact from retention tracking.

        Args:
            fact_id: Fact identifier.

        Returns:
            True if removed, False if not found.
        """
        if fact_id in self._timestamps:
            del self._timestamps[fact_id]
            return True
        return False

    def clear(self) -> None:
        """Clear all tracking."""
        self._timestamps.clear()
