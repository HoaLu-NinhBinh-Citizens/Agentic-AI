"""Memory Governance - TTL, provenance, confidence decay, PII policy, dedup.

This module provides governance for memory facts to prevent:
- Hallucinated facts without provenance poisoning RAG
- PII leakage into long-term memory
- Stale/confidence-degraded facts being used as basis
- Unbounded memory growth

Key principle: FACT KHÔNG CÓ provenance → không được dùng làm basis cho answer.
"""

from .provenance import ProvenanceTracker, ProvenanceLevel, FactProvenance
from .pii_policy import PIIRedactor, PIIPolicy, PIIDetector, PIIType
from .confidence_decay import ConfidenceDecay, DecayStrategy, ConfidenceScore
from .retention_policy import RetentionPolicy, MemoryType, MemoryTTL, RetentionResult
from .governance_engine import MemoryGovernance, GovernanceConfig

__all__ = [
    "ProvenanceTracker",
    "ProvenanceLevel",
    "FactProvenance",
    "PIIRedactor",
    "PIIPolicy",
    "PIIDetector",
    "ConfidenceDecay",
    "ConfidenceScore",
    "RetentionPolicy",
    "MemoryTTL",
    "RetentionResult",
    "MemoryGovernance",
    "GovernanceConfig",
]
