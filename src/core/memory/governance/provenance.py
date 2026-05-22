"""Provenance tracking for memory facts.

Tracks the origin and confidence of each memory fact to prevent
hallucinated facts from poisoning RAG responses.

Key principle: FACT KHÔNG CÓ provenance → không được dùng làm basis cho answer.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ProvenanceLevel(str, Enum):
    """Provenance confidence levels.

    Lower levels indicate facts that should not be used as primary basis.
    """

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERIFIED = "verified"


@dataclass
class FactProvenance:
    """Provenance record for a memory fact.

    Attributes:
        fact_id: Unique identifier for the fact.
        level: Provenance level (none/low/medium/high/verified).
        source: Where the fact came from (user_input, tool_result, etc.).
        source_id: Identifier of the source (session_id, tool_call_id, etc.).
        verified_by: If verified, who/what verified it.
        created_at: Unix timestamp when fact was created.
        confidence_initial: Initial confidence score (0-1).
        decay_factor: How fast confidence decays (0-1 per day).
        tags: Arbitrary tags for categorization.
    """

    fact_id: str
    level: ProvenanceLevel = ProvenanceLevel.NONE
    source: str = "unknown"
    source_id: str = ""
    verified_by: str = ""
    created_at: int = field(default_factory=lambda: int(time.time()))
    confidence_initial: float = 1.0
    decay_factor: float = 0.01
    tags: dict[str, Any] = field(default_factory=dict)

    def is_verified(self) -> bool:
        """Check if fact is verified."""
        return self.level == ProvenanceLevel.VERIFIED

    def has_provenance(self) -> bool:
        """Check if fact has meaningful provenance.

        Returns False for NONE level facts which should not be used as basis.
        """
        return self.level != ProvenanceLevel.NONE

    def can_use_as_basis(self) -> bool:
        """Check if fact can be used as basis for RAG answer.

        Only HIGH and VERIFIED facts should be used as primary basis.
        """
        return self.level in (ProvenanceLevel.HIGH, ProvenanceLevel.VERIFIED)

    def get_current_confidence(self, current_time: int | None = None) -> float:
        """Calculate current confidence with decay.

        Args:
            current_time: Current timestamp. Defaults to now.

        Returns:
            Confidence score (0-1).
        """
        if current_time is None:
            current_time = int(time.time())

        days_elapsed = (current_time - self.created_at) / 86400
        confidence = self.confidence_initial * ((1 - self.decay_factor) ** days_elapsed)
        return max(0.0, min(1.0, confidence))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "fact_id": self.fact_id,
            "level": self.level.value,
            "source": self.source,
            "source_id": self.source_id,
            "verified_by": self.verified_by,
            "created_at": self.created_at,
            "confidence_initial": self.confidence_initial,
            "decay_factor": self.decay_factor,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FactProvenance:
        """Create from dictionary."""
        return cls(
            fact_id=data["fact_id"],
            level=ProvenanceLevel(data.get("level", "none")),
            source=data.get("source", "unknown"),
            source_id=data.get("source_id", ""),
            verified_by=data.get("verified_by", ""),
            created_at=data.get("created_at", int(time.time())),
            confidence_initial=data.get("confidence_initial", 1.0),
            decay_factor=data.get("decay_factor", 0.01),
            tags=data.get("tags", {}),
        )


class ProvenanceTracker:
    """Tracks provenance for all memory facts.

    Provides methods to:
    - Register new facts with provenance
    - Upgrade provenance level (e.g., after verification)
    - Query whether a fact can be used as basis
    - Filter facts by provenance level
    """

    def __init__(self) -> None:
        """Initialize the provenance tracker."""
        self._provenance: dict[str, FactProvenance] = {}
        self._fact_index: dict[str, set[str]] = {}

    def register(
        self,
        fact_id: str,
        source: str,
        source_id: str = "",
        level: ProvenanceLevel = ProvenanceLevel.MEDIUM,
        confidence_initial: float = 1.0,
        decay_factor: float = 0.01,
        tags: dict[str, Any] | None = None,
    ) -> FactProvenance:
        """Register a new fact with provenance.

        Args:
            fact_id: Unique identifier for the fact.
            source: Source of the fact (user_input, tool_result, etc.).
            source_id: Identifier of the source.
            level: Initial provenance level.
            confidence_initial: Initial confidence (0-1).
            decay_factor: Decay rate per day (0-1).
            tags: Optional tags for categorization.

        Returns:
            The created provenance record.
        """
        provenance = FactProvenance(
            fact_id=fact_id,
            level=level,
            source=source,
            source_id=source_id,
            confidence_initial=confidence_initial,
            decay_factor=decay_factor,
            tags=tags or {},
        )
        self._provenance[fact_id] = provenance

        if source not in self._fact_index:
            self._fact_index[source] = set()
        self._fact_index[source].add(fact_id)

        return provenance

    def get(self, fact_id: str) -> FactProvenance | None:
        """Get provenance for a fact.

        Args:
            fact_id: Fact identifier.

        Returns:
            Provenance record or None if not found.
        """
        return self._provenance.get(fact_id)

    def upgrade(
        self,
        fact_id: str,
        new_level: ProvenanceLevel,
        verified_by: str = "",
    ) -> bool:
        """Upgrade provenance level for a fact.

        Args:
            fact_id: Fact identifier.
            new_level: New provenance level.
            verified_by: Who/what verified it.

        Returns:
            True if upgraded, False if fact not found.
        """
        provenance = self._provenance.get(fact_id)
        if not provenance:
            return False

        provenance.level = new_level
        if new_level == ProvenanceLevel.VERIFIED and verified_by:
            provenance.verified_by = verified_by

        return True

    def downgrade(self, fact_id: str, new_level: ProvenanceLevel) -> bool:
        """Downgrade provenance level for a fact.

        Use when fact is found to be incorrect.

        Args:
            fact_id: Fact identifier.
            new_level: New provenance level.

        Returns:
            True if downgraded, False if fact not found.
        """
        provenance = self._provenance.get(fact_id)
        if not provenance:
            return False

        provenance.level = new_level
        return True

    def can_use_as_basis(self, fact_id: str) -> bool:
        """Check if fact can be used as basis for answer.

        Args:
            fact_id: Fact identifier.

        Returns:
            True if fact has HIGH or VERIFIED provenance.
        """
        provenance = self._provenance.get(fact_id)
        if not provenance:
            return False
        return provenance.can_use_as_basis()

    def filter_by_provenance(
        self,
        fact_ids: list[str],
        min_level: ProvenanceLevel = ProvenanceLevel.LOW,
    ) -> list[str]:
        """Filter facts by minimum provenance level.

        Args:
            fact_ids: List of fact IDs to filter.
            min_level: Minimum required provenance level.

        Returns:
            Filtered list of fact IDs.
        """
        level_order = [
            ProvenanceLevel.NONE,
            ProvenanceLevel.LOW,
            ProvenanceLevel.MEDIUM,
            ProvenanceLevel.HIGH,
            ProvenanceLevel.VERIFIED,
        ]
        min_index = level_order.index(min_level)

        result = []
        for fact_id in fact_ids:
            provenance = self._provenance.get(fact_id)
            if provenance and level_order.index(provenance.level) >= min_index:
                result.append(fact_id)

        return result

    def get_facts_needing_verification(self, older_than_days: int = 7) -> list[str]:
        """Get facts that should be verified.

        Args:
            older_than_days: Age threshold in days.

        Returns:
            List of fact IDs needing verification.
        """
        cutoff = int(time.time()) - (older_than_days * 86400)
        result = []

        for fact_id, provenance in self._provenance.items():
            if provenance.created_at < cutoff and provenance.level in (
                ProvenanceLevel.LOW,
                ProvenanceLevel.MEDIUM,
            ):
                result.append(fact_id)

        return result

    def get_stats(self) -> dict[str, Any]:
        """Get provenance statistics.

        Returns:
            Statistics dictionary.
        """
        level_counts = {level.value: 0 for level in ProvenanceLevel}
        for provenance in self._provenance.values():
            level_counts[provenance.level.value] += 1

        return {
            "total_facts": len(self._provenance),
            "by_level": level_counts,
            "sources": {k: len(v) for k, v in self._fact_index.items()},
        }

    def clear(self) -> None:
        """Clear all provenance records."""
        self._provenance.clear()
        self._fact_index.clear()
