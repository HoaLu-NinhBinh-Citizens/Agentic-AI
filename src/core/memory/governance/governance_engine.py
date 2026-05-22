"""Memory Governance Engine - integrates all governance components.

Combines provenance, PII, confidence decay, and retention policies
into a unified governance layer for memory operations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .provenance import ProvenanceTracker, ProvenanceLevel, FactProvenance
from .pii_policy import PIIRedactor, PIIPolicy, PIIDetector, PIIMatch
from .confidence_decay import ConfidenceDecay, DecayStrategy
from .retention_policy import RetentionPolicy, MemoryType, MemoryTTL

logger = logging.getLogger(__name__)


@dataclass
class GovernanceConfig:
    """Configuration for memory governance."""

    enable_provenance: bool = True
    enable_pii_detection: bool = True
    enable_confidence_decay: bool = True
    enable_retention_policy: bool = True
    default_provenance_level: ProvenanceLevel = ProvenanceLevel.MEDIUM
    default_memory_type: MemoryType = MemoryType.WORKING
    pii_policy: PIIPolicy | None = None
    decay_strategy: DecayStrategy = DecayStrategy.EXPONENTIAL


@dataclass
class GovernanceResult:
    """Result of a governance operation."""

    fact_id: str
    allowed: bool
    redacted_content: str | None = None
    provenance: FactProvenance | None = None
    pii_detected: list[PIIMatch] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "fact_id": self.fact_id,
            "allowed": self.allowed,
            "redacted_content": self.redacted_content,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "pii_detected": [m.to_dict() for m in self.pii_detected],
            "error": self.error,
        }


@dataclass
class RetrievalResult:
    """Governed retrieval result."""

    fact_id: str
    content: str
    can_use_as_basis: bool
    provenance_level: ProvenanceLevel
    confidence: float
    memory_type: MemoryType
    age_seconds: int


class MemoryGovernance:
    """Unified governance engine for memory operations.

    Integrates:
    - Provenance tracking
    - PII detection and redaction
    - Confidence decay
    - Retention policy (TTL)
    """

    def __init__(self, config: GovernanceConfig | None = None) -> None:
        """Initialize memory governance.

        Args:
            config: Governance configuration.
        """
        self._config = config or GovernanceConfig()
        self._provenance = ProvenanceTracker()
        self._pii_detector = PIIDetector(self._config.pii_policy or PIIPolicy())
        self._pii_redactor = PIIRedactor(self._config.pii_policy or PIIPolicy())
        self._confidence_decay = ConfidenceDecay(strategy=self._config.decay_strategy)
        self._retention_policy = RetentionPolicy()

    async def preprocess_for_storage(
        self,
        fact_id: str,
        content: str,
        source: str,
        source_id: str = "",
        memory_type: MemoryType | None = None,
        provenance_level: ProvenanceLevel | None = None,
    ) -> GovernanceResult:
        """Preprocess content before storing in memory.

        This method:
        1. Detects and optionally redacts PII
        2. Registers provenance
        3. Sets up confidence decay
        4. Configures retention policy

        Args:
            fact_id: Unique identifier for the fact.
            content: Content to store.
            source: Source of the content.
            source_id: Identifier of the source.
            memory_type: Type of memory.
            provenance_level: Provenance level.

        Returns:
            GovernanceResult with processed content and metadata.
        """
        result = GovernanceResult(fact_id=fact_id, allowed=True)
        effective_memory_type = memory_type or self._config.default_memory_type
        effective_provenance = provenance_level or self._config.default_provenance_level

        if self._config.enable_pii_detection:
            pii_matches = self._pii_detector.detect(content)
            result.pii_detected = pii_matches

            if pii_matches:
                policy = self._config.pii_policy or PIIPolicy()
                if policy.redact_before_storage:
                    result.redacted_content, _ = self._pii_redactor.redact(content)
                    logger.info(
                        "governance_pii_redacted: fact_id=%s, types=%s",
                        fact_id,
                        [m.pii_type.value for m in pii_matches],
                    )
                else:
                    result.redacted_content = content

                result.allowed = True
            else:
                result.redacted_content = content
        else:
            result.redacted_content = content

        if self._config.enable_provenance:
            provenance = self._provenance.register(
                fact_id=fact_id,
                source=source,
                source_id=source_id,
                level=effective_provenance,
            )
            result.provenance = provenance

        if self._config.enable_confidence_decay:
            self._confidence_decay.register(fact_id=fact_id)

        if self._config.enable_retention_policy:
            self._retention_policy.register(
                fact_id=fact_id,
                memory_type=effective_memory_type,
            )

        return result

    async def verify_content(
        self,
        fact_id: str,
        verified_by: str = "user",
    ) -> bool:
        """Upgrade provenance after verification.

        Args:
            fact_id: Fact identifier.
            verified_by: Who verified it.

        Returns:
            True if upgraded, False if not found.
        """
        return self._provenance.upgrade(
            fact_id,
            ProvenanceLevel.VERIFIED,
            verified_by=verified_by,
        )

    async def check_retrieval(
        self,
        fact_id: str,
        min_provenance_level: ProvenanceLevel = ProvenanceLevel.LOW,
        min_confidence: float = 0.1,
    ) -> RetrievalResult | None:
        """Check if fact can be retrieved and used.

        Args:
            fact_id: Fact identifier.
            min_provenance_level: Minimum required provenance.
            min_confidence: Minimum required confidence.

        Returns:
            RetrievalResult or None if fact not eligible.
        """
        provenance = self._provenance.get(fact_id)
        if not provenance:
            return None

        if provenance.level.value < min_provenance_level.value:
            return None

        confidence = self._confidence_decay.get_confidence(fact_id)
        if confidence is not None and confidence < min_confidence:
            return None

        retention = self._retention_policy.check(fact_id)
        if retention.is_expired:
            return None

        memory_type = retention.memory_type
        age_seconds = 0
        if fact_id in self._retention_policy._timestamps:
            _, created_at = self._retention_policy._timestamps[fact_id]
            age_seconds = int(__import__("time").time()) - created_at

        can_use = self._provenance.can_use_as_basis(fact_id)

        return RetrievalResult(
            fact_id=fact_id,
            content="",
            can_use_as_basis=can_use,
            provenance_level=provenance.level,
            confidence=confidence or 1.0,
            memory_type=memory_type,
            age_seconds=age_seconds,
        )

    async def filter_for_rag(
        self,
        fact_ids: list[str],
        min_provenance: ProvenanceLevel = ProvenanceLevel.MEDIUM,
        min_confidence: float = 0.3,
    ) -> list[str]:
        """Filter facts suitable for RAG context.

        Fact KHÔNG CÓ provenance → không được dùng làm basis.

        Args:
            fact_ids: List of fact IDs to filter.
            min_provenance: Minimum provenance level.
            min_confidence: Minimum confidence.

        Returns:
            Filtered list of fact IDs suitable for RAG.
        """
        filtered = self._provenance.filter_by_provenance(fact_ids, min_provenance)
        filtered = self._confidence_decay.filter_by_confidence(filtered, min_confidence)

        results = self._retention_policy.check_batch(filtered)
        filtered = [
            r.fact_id for r in results
            if not r.is_expired
        ]

        return filtered

    async def get_stats(self) -> dict[str, Any]:
        """Get governance statistics.

        Returns:
            Statistics dictionary.
        """
        return {
            "provenance": self._provenance.get_stats(),
            "confidence_decay": self._confidence_decay.get_stats(),
            "retention": self._retention_policy.get_stats(),
        }

    async def cleanup(self) -> list[str]:
        """Clean up expired facts.

        Returns:
            List of cleaned up fact IDs.
        """
        expired = self._retention_policy.get_facts_to_cleanup()

        for fact_id in expired:
            self._provenance._provenance.pop(fact_id, None)
            self._confidence_decay.remove(fact_id)
            self._retention_policy.remove(fact_id)

        logger.info("governance_cleanup: removed %d expired facts", len(expired))
        return expired
