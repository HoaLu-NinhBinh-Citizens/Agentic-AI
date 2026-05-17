"""Phase 5C v12 – Advanced Context & Retrieval Engine Types.

Data schemas for Phase 5C enterprise features:
- Retrieval snapshots with committed_at timestamp
- Plugin versions and rollback history
- Golden set metrics and drift detection
- Document-to-cache mapping for invalidation
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ============================================================================
# Snapshot Isolation Types
# ============================================================================

class SnapshotStatus(Enum):
    """Status of a retrieval snapshot."""
    ACTIVE = "active"
    COMMITTED = "committed"
    EXPIRED = "expired"


@dataclass
class RetrievalSnapshot:
    """Snapshot of retrieval state at a point in time.
    
    Used for snapshot isolation - each retrieval uses a fixed snapshot
    rather than seeing inconsistent state during transactions.
    """
    snapshot_id: str
    transaction_id: str
    created_at: int = field(default_factory=lambda: int(time.time()))
    committed_at: Optional[int] = None
    status: SnapshotStatus = SnapshotStatus.ACTIVE
    document_versions: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Transaction:
    """Transaction for retrieval operations."""
    transaction_id: str
    started_at: int = field(default_factory=lambda: int(time.time()))
    operations: list[dict] = field(default_factory=list)
    committed: bool = False
    snapshot_id: Optional[str] = None


# ============================================================================
# Plugin Version Management Types
# ============================================================================

class PluginVersionStatus(Enum):
    """Status of a plugin version."""
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    BROKEN = "broken"


@dataclass
class PluginVersion:
    """Versioned plugin with rollback support."""
    plugin_name: str
    version: str
    status: PluginVersionStatus = PluginVersionStatus.ACTIVE
    rollback_count: int = 0
    loaded_at: int = field(default_factory=lambda: int(time.time()))
    error_count: int = 0
    last_error: Optional[str] = None
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginVersionHistory:
    """History of plugin versions for rollback."""
    plugin_name: str
    versions: list[PluginVersion] = field(default_factory=list)
    current_active: Optional[str] = None


# ============================================================================
# Query Type Budget Types
# ============================================================================

@dataclass
class QueryTypeBudget:
    """Budget configuration per query intent."""
    intent: str
    max_tokens: int
    max_chunks: int = 10
    timeout_seconds: float = 30.0


# ============================================================================
# Golden Set & Drift Detection Types
# ============================================================================

@dataclass
class GoldenQuery:
    """A query in the golden evaluation set."""
    query_id: str
    query_text: str
    expected_doc_ids: list[str]
    intent: str
    created_at: int = field(default_factory=lambda: int(time.time()))


@dataclass
class GoldenSet:
    """Collection of golden queries for evaluation."""
    set_id: str
    name: str
    description: str
    queries: list[GoldenQuery] = field(default_factory=list)
    created_at: int = field(default_factory=lambda: int(time.time()))
    updated_at: int = field(default_factory=lambda: int(time.time()))


@dataclass
class GoldenSetMetrics:
    """Metrics from golden set evaluation."""
    set_id: str
    eval_time: int = field(default_factory=lambda: int(time.time()))
    recall_at_1: float = 0.0
    recall_at_5: float = 0.0
    recall_at_10: float = 0.0
    mean_reciprocal_rank: float = 0.0
    total_queries: int = 0
    drift_detected: bool = False
    drift_reason: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DriftAlert:
    """Alert when golden set drift is detected."""
    alert_id: str
    set_id: str
    detected_at: int = field(default_factory=lambda: int(time.time()))
    previous_metrics: Optional[GoldenSetMetrics] = None
    current_metrics: Optional[GoldenSetMetrics] = None
    drift_percentage: float = 0.0
    recommendations: list[str] = field(default_factory=list)


# ============================================================================
# Document-Aware Cache Invalidation Types
# ============================================================================

@dataclass
class DocumentCacheMapping:
    """Maps documents to their cached entries."""
    doc_id: str
    cache_keys: list[str] = field(default_factory=list)
    indexed_at: int = field(default_factory=lambda: int(time.time()))
    last_modified: int = field(default_factory=lambda: int(time.time()))


@dataclass
class CacheInvalidation:
    """Record of cache invalidation event."""
    invalidation_id: str
    doc_id: str
    invalidated_keys: list[str]
    reason: str
    timestamp: int = field(default_factory=lambda: int(time.time()))


# ============================================================================
# Explainability Types
# ============================================================================

@dataclass
class ProvenanceEntry:
    """Single provenance entry for retrieval explainability."""
    chunk_id: str
    doc_id: str
    influence_score: float
    source_type: str
    text_preview: str
    rank: int
    vector_score: float = 0.0
    lexical_score: float = 0.0


@dataclass
class RetrievalExplanation:
    """Complete explanation for a retrieval result."""
    query: str
    intent: str
    total_chunks: int
    provenance_entries: list[ProvenanceEntry] = field(default_factory=list)
    total_bytes: int = 0
    truncated: bool = False
    truncation_reason: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Replica Types
# ============================================================================

class ReplicaStatus(Enum):
    """Status of a read replica."""
    HEALTHY = "healthy"
    STALE = "stale"
    OFFLINE = "offline"


@dataclass
class ReplicaMetrics:
    """Metrics for a read replica."""
    replica_id: str
    replication_lag_seconds: float = 0.0
    status: ReplicaStatus = ReplicaStatus.HEALTHY
    last_heartbeat: int = field(default_factory=lambda: int(time.time()))
    query_count: int = 0
    error_count: int = 0


# ============================================================================
# Query Intent Types
# ============================================================================

class QueryIntent(Enum):
    """Known query intent types."""
    FACTOID = "factoid"
    REASONING = "reasoning"
    CODE = "code"
    INSTRUCTION = "instruction"
    GENERAL = "general"


# ============================================================================
# Retrieval Request/Response Types
# ============================================================================

@dataclass
class AdvancedRetrievalRequest:
    """Advanced retrieval request with all Phase 5C features."""
    query: str
    intent: QueryIntent = QueryIntent.GENERAL
    snapshot_id: Optional[str] = None
    use_primary_for_fresh: bool = False
    require_explanation: bool = False
    max_provenance_entries: int = 100
    include_metadata: bool = True


@dataclass
class AdvancedRetrievalResponse:
    """Advanced retrieval response with provenance."""
    hits: list[Any]  # RetrievalHit
    explanation: Optional[RetrievalExplanation] = None
    snapshot_id: Optional[str] = None
    replica_used: Optional[str] = None
    budget_used: QueryTypeBudget = None
    metadata: dict[str, Any] = field(default_factory=dict)
