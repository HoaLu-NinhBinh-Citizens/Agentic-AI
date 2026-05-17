"""Phase 5C v12 – Advanced Context & Retrieval Engine Components.

Implements all Phase 5C enterprise features:
1. SnapshotIsolationRead - Transactional read isolation
2. ReplicaLagAwareRouter - Replica lag awareness
3. PluginVersionManager - Plugin hot reload & rollback
4. QueryTypeBudgeter - Budget per query type
5. GoldenSetDriftDetector - Golden set drift detection
6. DocumentBasedCacheInvalidator - Cache invalidation based on doc update
7. ExplainabilitySizeLimiter - Explainability size limits
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from .retrieval_types import (
    CacheInvalidation,
    DocumentCacheMapping,
    DriftAlert,
    GoldenQuery,
    GoldenSet,
    GoldenSetMetrics,
    PluginVersion,
    PluginVersionHistory,
    PluginVersionStatus,
    ProvenanceEntry,
    QueryTypeBudget,
    ReplicaMetrics,
    ReplicaStatus,
    RetrievalExplanation,
    RetrievalSnapshot,
    SnapshotStatus,
    Transaction,
)
from .retrieval_config import (
    CacheConfig,
    ExplainabilityConfig,
    GoldenSetConfig,
    Phase5CConfig,
    PluginManagementConfig,
    QueryBudgetConfig,
    ReplicaLagConfig,
    DEFAULT_PHASE5C_CONFIG,
)


logger = logging.getLogger(__name__)


# ============================================================================
# 1. Snapshot Isolation Read
# ============================================================================

class SnapshotIsolationRead:
    """Implements snapshot isolation for retrieval.
    
    Each retrieval uses a fixed snapshot_id, ensuring consistent reads
    even when transactions are committing new snapshots.
    """
    
    def __init__(
        self,
        snapshot_ttl_seconds: int = 3600,
        max_snapshots: int = 100,
    ):
        self._ttl_seconds = snapshot_ttl_seconds
        self._max_snapshots = max_snapshots
        self._snapshots: dict[str, RetrievalSnapshot] = {}
        self._transactions: dict[str, Transaction] = {}
        self._document_versions: dict[str, int] = defaultdict(int)
    
    def begin_transaction(self, transaction_id: Optional[str] = None) -> Transaction:
        """Begin a new transaction."""
        txn_id = transaction_id or f"txn_{uuid.uuid4().hex[:12]}"
        
        transaction = Transaction(
            transaction_id=txn_id,
            started_at=int(time.time()),
        )
        self._transactions[txn_id] = transaction
        return transaction
    
    def get_or_create_snapshot(self, transaction_id: str) -> RetrievalSnapshot:
        """Get existing snapshot or create new one for transaction."""
        if transaction_id in self._transactions:
            txn = self._transactions[transaction_id]
            if txn.snapshot_id:
                return self._snapshots.get(txn.snapshot_id)
        
        snapshot_id = f"snap_{uuid.uuid4().hex[:12]}"
        snapshot = RetrievalSnapshot(
            snapshot_id=snapshot_id,
            transaction_id=transaction_id,
            document_versions=dict(self._document_versions),
        )
        self._snapshots[snapshot_id] = snapshot
        
        if len(self._snapshots) > self._max_snapshots:
            self._cleanup_expired_snapshots()
        
        if transaction_id in self._transactions:
            self._transactions[transaction_id].snapshot_id = snapshot_id
        
        return snapshot
    
    def commit_transaction(self, transaction_id: str) -> Optional[RetrievalSnapshot]:
        """Commit transaction and finalize snapshot."""
        if transaction_id not in self._transactions:
            return None
        
        txn = self._transactions[transaction_id]
        if txn.snapshot_id and txn.snapshot_id in self._snapshots:
            snapshot = self._snapshots[txn.snapshot_id]
            snapshot.status = SnapshotStatus.COMMITTED
            snapshot.committed_at = int(time.time())
            txn.committed = True
            return snapshot
        
        return None
    
    def abort_transaction(self, transaction_id: str) -> None:
        """Abort transaction without committing."""
        if transaction_id in self._transactions:
            txn = self._transactions[transaction_id]
            if txn.snapshot_id and txn.snapshot_id in self._snapshots:
                del self._snapshots[txn.snapshot_id]
            del self._transactions[transaction_id]
    
    def get_snapshot(self, snapshot_id: str) -> Optional[RetrievalSnapshot]:
        """Get snapshot by ID."""
        return self._snapshots.get(snapshot_id)
    
    def update_document_version(self, doc_id: str) -> int:
        """Update document version (called when document changes)."""
        self._document_versions[doc_id] += 1
        return self._document_versions[doc_id]
    
    def is_document_changed_since(
        self,
        doc_id: str,
        snapshot: RetrievalSnapshot
    ) -> bool:
        """Check if document changed since snapshot."""
        current_version = self._document_versions.get(doc_id, 0)
        snapshot_version = snapshot.document_versions.get(doc_id, 0)
        return current_version > snapshot_version
    
    def _cleanup_expired_snapshots(self) -> None:
        """Remove expired snapshots."""
        now = int(time.time())
        expired = [
            sid for sid, snap in self._snapshots.items()
            if snap.status == SnapshotStatus.EXPIRED or
            (snap.status == SnapshotStatus.ACTIVE and
             now - snap.created_at > self._ttl_seconds)
        ]
        for sid in expired:
            del self._snapshots[sid]
    
    def get_active_snapshot_count(self) -> int:
        """Get count of active snapshots."""
        return len([
            s for s in self._snapshots.values()
            if s.status in (SnapshotStatus.ACTIVE, SnapshotStatus.COMMITTED)
        ])


# ============================================================================
# 2. Replica Lag Aware Router
# ============================================================================

class ReplicaLagAwareRouter:
    """Routes queries based on replica lag.
    
    Routes read queries to replicas with acceptable lag,
    or falls back to primary when all replicas are stale.
    """
    
    def __init__(
        self,
        max_lag_seconds: float = 5.0,
        fallback_to_primary: bool = True,
        check_interval_seconds: float = 10.0,
    ):
        self._max_lag = max_lag_seconds
        self._fallback_to_primary = fallback_to_primary
        self._check_interval = check_interval_seconds
        self._replicas: dict[str, ReplicaMetrics] = {}
        self._primary_id = "primary"
        self._last_check: dict[str, float] = {}
        self._lock = asyncio.Lock()
    
    def register_replica(self, replica_id: str) -> None:
        """Register a new replica."""
        self._replicas[replica_id] = ReplicaMetrics(
            replica_id=replica_id,
            status=ReplicaStatus.HEALTHY,
        )
    
    def update_replica_lag(self, replica_id: str, lag_seconds: float) -> None:
        """Update replica's replication lag."""
        if replica_id in self._replicas:
            self._replicas[replica_id].replication_lag_seconds = lag_seconds
            
            if lag_seconds > self._max_lag:
                self._replicas[replica_id].status = ReplicaStatus.STALE
            else:
                self._replicas[replica_id].status = ReplicaStatus.HEALTHY
            
            self._replicas[replica_id].last_heartbeat = int(time.time())
    
    async def get_best_replica(self) -> tuple[Optional[str], bool]:
        """Get best replica for read query.
        
        Returns:
            Tuple of (replica_id, is_primary_fallback)
        """
        async with self._lock:
            healthy_replicas = [
                (rid, m) for rid, m in self._replicas.items()
                if m.status == ReplicaStatus.HEALTHY
            ]
            
            if healthy_replicas:
                healthy_replicas.sort(key=lambda x: x[1].replication_lag_seconds)
                return healthy_replicas[0][0], False
            
            if self._fallback_to_primary:
                if self._primary_id in self._replicas:
                    return self._primary_id, True
            
            return None, False
    
    def get_replica_status(self, replica_id: str) -> Optional[ReplicaMetrics]:
        """Get replica status."""
        return self._replicas.get(replica_id)
    
    def get_all_replica_statuses(self) -> dict[str, ReplicaMetrics]:
        """Get all replica statuses."""
        return dict(self._replicas)
    
    def is_primary_fallback(self, replica_id: str) -> bool:
        """Check if replica is primary being used as fallback."""
        return replica_id == self._primary_id


# ============================================================================
# 3. Plugin Version Manager
# ============================================================================

class PluginVersionManager:
    """Manages plugin versions with hot reload and rollback.
    
    Tracks plugin versions, supports rollback on failure,
    and maintains version history.
    """
    
    def __init__(
        self,
        auto_rollback: bool = True,
        version_history_size: int = 5,
        rollback_cooldown_seconds: int = 60,
    ):
        self._auto_rollback = auto_rollback
        self._history_size = version_history_size
        self._cooldown = rollback_cooldown_seconds
        self._plugins: dict[str, PluginVersionHistory] = {}
        self._last_rollback: dict[str, int] = {}
        self._lock = asyncio.Lock()
    
    async def register_plugin(
        self,
        plugin_name: str,
        version: str,
        config: Optional[dict] = None,
    ) -> PluginVersion:
        """Register a new plugin version."""
        async with self._lock:
            if plugin_name not in self._plugins:
                self._plugins[plugin_name] = PluginVersionHistory(
                    plugin_name=plugin_name,
                )
            
            pv = PluginVersion(
                plugin_name=plugin_name,
                version=version,
                config=config or {},
            )
            
            history = self._plugins[plugin_name]
            
            for existing in history.versions:
                if existing.version == version:
                    return existing
            
            history.versions.append(pv)
            history.current_active = version
            
            if len(history.versions) > self._history_size:
                deprecated = [
                    v for v in history.versions
                    if v.status == PluginVersionStatus.DEPRECATED
                ]
                if deprecated:
                    history.versions.remove(deprecated[0])
            
            return pv
    
    async def load_plugin(
        self,
        plugin_name: str,
        version: str,
        health_check_fn: Optional[Callable] = None,
    ) -> tuple[bool, Optional[str]]:
        """Load a plugin version with health check.
        
        Returns:
            Tuple of (success, error_message)
        """
        async with self._lock:
            if plugin_name not in self._plugins:
                return False, f"Plugin {plugin_name} not registered"
            
            history = self._plugins[plugin_name]
            
            version_obj = next(
                (v for v in history.versions if v.version == version),
                None
            )
            
            if not version_obj:
                return False, f"Version {version} not found"
            
            if health_check_fn:
                try:
                    if asyncio.iscoroutinefunction(health_check_fn):
                        await health_check_fn()
                    else:
                        health_check_fn()
                    
                    version_obj.status = PluginVersionStatus.ACTIVE
                    history.current_active = version
                    
                    for v in history.versions:
                        if v.version != version:
                            v.status = PluginVersionStatus.DEPRECATED
                    
                    return True, None
                    
                except Exception as e:
                    version_obj.status = PluginVersionStatus.BROKEN
                    version_obj.error_count += 1
                    version_obj.last_error = str(e)
                    
                    if self._auto_rollback:
                        return await self._rollback_to_last_good(plugin_name)
                    
                    return False, str(e)
            
            version_obj.status = PluginVersionStatus.ACTIVE
            history.current_active = version
            return True, None
    
    async def _rollback_to_last_good(
        self,
        plugin_name: str,
    ) -> tuple[bool, Optional[str]]:
        """Rollback to last known good version."""
        now = int(time.time())
        
        if plugin_name in self._last_rollback:
            if now - self._last_rollback[plugin_name] < self._cooldown:
                return False, f"Cooldown period active for {plugin_name}"
        
        history = self._plugins.get(plugin_name)
        if not history:
            return False, f"No history for {plugin_name}"
        
        good_versions = [
            v for v in history.versions
            if v.status == PluginVersionStatus.ACTIVE and v.error_count == 0
        ]
        
        if not good_versions:
            deprecated = [
                v for v in history.versions
                if v.status == PluginVersionStatus.DEPRECATED
            ]
            if deprecated:
                good_versions = deprecated
        
        if not good_versions:
            return False, f"No good version to rollback to for {plugin_name}"
        
        last_good = good_versions[0]
        last_good.status = PluginVersionStatus.ACTIVE
        history.current_active = last_good.version
        last_good.rollback_count += 1
        
        self._last_rollback[plugin_name] = now
        
        logger.warning(
            f"Auto-rolled back {plugin_name} to version {last_good.version}"
        )
        
        return True, None
    
    async def rollback_plugin(
        self,
        plugin_name: str,
        target_version: str,
    ) -> tuple[bool, Optional[str]]:
        """Manually rollback to a specific version."""
        async with self._lock:
            history = self._plugins.get(plugin_name)
            if not history:
                return False, f"No history for {plugin_name}"
            
            target = next(
                (v for v in history.versions if v.version == target_version),
                None
            )
            
            if not target:
                return False, f"Version {target_version} not found"
            
            for v in history.versions:
                v.status = PluginVersionStatus.DEPRECATED
            
            target.status = PluginVersionStatus.ACTIVE
            history.current_active = target_version
            target.rollback_count += 1
            
            return True, None
    
    def get_active_version(self, plugin_name: str) -> Optional[str]:
        """Get currently active version."""
        history = self._plugins.get(plugin_name)
        return history.current_active if history else None
    
    def get_version_history(self, plugin_name: str) -> list[PluginVersion]:
        """Get version history for a plugin."""
        history = self._plugins.get(plugin_name)
        return list(history.versions) if history else []


# ============================================================================
# 4. Query Type Budgeter
# ============================================================================

class QueryTypeBudgeter:
    """Allocates token budget per query type.
    
    Each query intent gets its own max_tokens budget,
    with defaults for unknown types.
    """
    
    def __init__(
        self,
        per_intent: Optional[dict[str, int]] = None,
        default_max_tokens: int = 8192,
        default_max_chunks: int = 10,
        default_timeout_seconds: float = 30.0,
    ):
        self._per_intent = per_intent or {
            "factoid": 4000,
            "reasoning": 8000,
            "code": 16000,
            "instruction": 2000,
            "general": 8192,
        }
        self._default_tokens = default_max_tokens
        self._default_chunks = default_max_chunks
        self._default_timeout = default_timeout_seconds
    
    def get_budget(self, intent: str) -> QueryTypeBudget:
        """Get budget for a query intent."""
        max_tokens = self._per_intent.get(
            intent.lower(),
            self._default_tokens
        )
        
        return QueryTypeBudget(
            intent=intent,
            max_tokens=max_tokens,
            max_chunks=self._default_chunks,
            timeout_seconds=self._default_timeout,
        )
    
    def get_all_budgets(self) -> dict[str, QueryTypeBudget]:
        """Get all configured budgets."""
        return {
            intent: self.get_budget(intent)
            for intent in self._per_intent
        }
    
    def update_budget(self, intent: str, max_tokens: int) -> None:
        """Update budget for an intent."""
        self._per_intent[intent.lower()] = max_tokens
    
    def reset_to_default(self) -> None:
        """Reset all budgets to defaults."""
        self._per_intent = {
            "factoid": 4000,
            "reasoning": 8000,
            "code": 16000,
            "instruction": 2000,
            "general": 8192,
        }


# ============================================================================
# 5. Golden Set Drift Detector
# ============================================================================

class GoldenSetDriftDetector:
    """Detects drift in golden set evaluation.
    
    Periodically evaluates golden queries and alerts
    when recall degrades beyond threshold.
    """
    
    def __init__(
        self,
        eval_interval_hours: int = 24,
        drift_threshold: float = 0.1,
        alert_webhook: Optional[str] = None,
    ):
        self._interval_hours = eval_interval_hours
        self._drift_threshold = drift_threshold
        self._alert_webhook = alert_webhook
        self._golden_sets: dict[str, GoldenSet] = {}
        self._metrics_history: dict[str, list[GoldenSetMetrics]] = defaultdict(list)
        self._last_eval: dict[str, int] = {}
        self._alerts: list[DriftAlert] = []
    
    def register_golden_set(self, golden_set: GoldenSet) -> None:
        """Register a golden set for evaluation."""
        self._golden_sets[golden_set.set_id] = golden_set
    
    def add_query(self, set_id: str, query: GoldenQuery) -> bool:
        """Add a query to golden set."""
        if set_id not in self._golden_sets:
            return False
        self._golden_sets[set_id].queries.append(query)
        return True
    
    def remove_query(self, set_id: str, query_id: str) -> bool:
        """Remove a query from golden set."""
        if set_id not in self._golden_sets:
            return False
        gs = self._golden_sets[set_id]
        gs.queries = [q for q in gs.queries if q.query_id != query_id]
        return True
    
    def update_golden_set(self, set_id: str, queries: list[GoldenQuery]) -> bool:
        """Update all queries in golden set."""
        if set_id not in self._golden_sets:
            return False
        self._golden_sets[set_id].queries = queries
        return True
    
    async def evaluate(
        self,
        set_id: str,
        retrieval_fn: Callable,
    ) -> Optional[GoldenSetMetrics]:
        """Evaluate golden set against retrieval function.
        
        Args:
            set_id: Golden set to evaluate
            retrieval_fn: Function that takes query text and returns doc_ids
            
        Returns:
            Evaluation metrics or None if set not found
        """
        if set_id not in self._golden_sets:
            return None
        
        gs = self._golden_sets[set_id]
        
        if len(gs.queries) == 0:
            return None
        
        metrics = GoldenSetMetrics(set_id=set_id)
        metrics.total_queries = len(gs.queries)
        
        rr_sum = 0.0
        hits_at_1 = 0
        hits_at_5 = 0
        hits_at_10 = 0
        
        for query in gs.queries:
            retrieved = await retrieval_fn(query.query_text)
            retrieved_ids = set(retrieved[:10])
            expected_ids = set(query.expected_doc_ids)
            
            if not expected_ids:
                continue
            
            relevant_in_top = len(retrieved_ids & expected_ids)
            
            if relevant_in_top > 0:
                if relevant_in_top >= 1:
                    hits_at_1 += 1
                if relevant_in_top >= min(5, len(expected_ids)):
                    hits_at_5 += 1
                if relevant_in_top >= min(10, len(expected_ids)):
                    hits_at_10 += 1
                
                for i, doc_id in enumerate(retrieved[:10]):
                    if doc_id in expected_ids:
                        rr_sum += 1.0 / (i + 1)
                        break
        
        metrics.recall_at_1 = hits_at_1 / metrics.total_queries if metrics.total_queries > 0 else 0
        metrics.recall_at_5 = hits_at_5 / metrics.total_queries if metrics.total_queries > 0 else 0
        metrics.recall_at_10 = hits_at_10 / metrics.total_queries if metrics.total_queries > 0 else 0
        metrics.mean_reciprocal_rank = rr_sum / metrics.total_queries if metrics.total_queries > 0 else 0
        
        self._metrics_history[set_id].append(metrics)
        self._last_eval[set_id] = int(time.time())
        
        if len(self._metrics_history[set_id]) > 1:
            prev = self._metrics_history[set_id][-2]
            recall_diff = prev.recall_at_5 - metrics.recall_at_5
            recall_pct = prev.recall_at_5 * self._drift_threshold
            
            if recall_diff > recall_pct:
                metrics.drift_detected = True
                metrics.drift_reason = (
                    f"Recall@5 dropped from {prev.recall_at_5:.3f} to {metrics.recall_at_5:.3f}"
                )
                
                alert = DriftAlert(
                    alert_id=f"alert_{uuid.uuid4().hex[:8]}",
                    set_id=set_id,
                    previous_metrics=prev,
                    current_metrics=metrics,
                    drift_percentage=(recall_diff / prev.recall_at_5 if prev.recall_at_5 > 0 else 0),
                    recommendations=self._generate_recommendations(metrics),
                )
                self._alerts.append(alert)
                
                if self._alert_webhook:
                    await self._send_alert(alert)
        
        return metrics
    
    def _generate_recommendations(self, metrics: GoldenSetMetrics) -> list[str]:
        """Generate recommendations based on metrics."""
        recs = []
        
        if metrics.recall_at_5 < 0.5:
            recs.append("Consider retraining embedding model")
        if metrics.recall_at_5 < 0.7:
            recs.append("Review and update golden set queries")
        if metrics.mean_reciprocal_rank < 0.5:
            recs.append("Check chunking strategy and index quality")
        
        recs.append("Review recent document changes for impact")
        return recs
    
    async def _send_alert(self, alert: DriftAlert) -> None:
        """Send drift alert via webhook."""
        if not self._alert_webhook:
            return
        
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                payload = {
                    "alert_id": alert.alert_id,
                    "set_id": alert.set_id,
                    "drift_percentage": alert.drift_percentage,
                    "recommendations": alert.recommendations,
                }
                async with session.post(
                    self._alert_webhook,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=5),
                ):
                    pass
        except Exception as e:
            logger.error(f"Failed to send drift alert: {e}")
    
    def get_latest_metrics(self, set_id: str) -> Optional[GoldenSetMetrics]:
        """Get latest evaluation metrics."""
        history = self._metrics_history.get(set_id)
        return history[-1] if history else None
    
    def get_drift_alerts(self) -> list[DriftAlert]:
        """Get all drift alerts."""
        return list(self._alerts)
    
    def needs_evaluation(self, set_id: str) -> bool:
        """Check if golden set needs evaluation."""
        if set_id not in self._last_eval:
            return True
        
        now = int(time.time())
        interval_seconds = self._interval_hours * 3600
        return now - self._last_eval[set_id] > interval_seconds


# ============================================================================
# 6. Document-Based Cache Invalidation
# ============================================================================

class DocumentBasedCacheInvalidator:
    """Invalidates cache entries based on document updates.
    
    Tracks which documents map to which cache keys,
    and invalidates related entries when documents change.
    """
    
    def __init__(
        self,
        bloom_filter_enabled: bool = True,
        bloom_filter_fp_rate: float = 0.01,
        mapping_ttl_seconds: int = 86400,
    ):
        self._bloom_enabled = bloom_filter_enabled
        self._fp_rate = bloom_filter_fp_rate
        self._mapping_ttl = mapping_ttl_seconds
        self._doc_to_keys: dict[str, DocumentCacheMapping] = {}
        self._key_to_docs: dict[str, set[str]] = defaultdict(set)
        self._bloom_filter: Optional[set] = set()
        self._invalidations: list[CacheInvalidation] = []
        self._lock = asyncio.Lock()
    
    def register_cache_entry(self, doc_id: str, cache_key: str) -> None:
        """Register a cache entry with its document."""
        if doc_id not in self._doc_to_keys:
            self._doc_to_keys[doc_id] = DocumentCacheMapping(
                doc_id=doc_id,
                cache_keys=[],
            )
        
        if cache_key not in self._doc_to_keys[doc_id].cache_keys:
            self._doc_to_keys[doc_id].cache_keys.append(cache_key)
            self._key_to_docs[cache_key].add(doc_id)
            
            if self._bloom_enabled:
                self._add_to_bloom_filter(doc_id)
    
    def _add_to_bloom_filter(self, doc_id: str) -> None:
        """Add document to bloom filter."""
        if len(self._bloom_filter) < 10000:
            self._bloom_filter.add(hash(doc_id))
    
    def is_doc_likely_cached(self, doc_id: str) -> bool:
        """Check if document might be in cache (bloom filter)."""
        if not self._bloom_enabled:
            return doc_id in self._doc_to_keys
        
        return hash(doc_id) in self._bloom_filter
    
    def get_cache_keys_for_doc(self, doc_id: str) -> list[str]:
        """Get all cache keys that contain a document."""
        mapping = self._doc_to_keys.get(doc_id)
        return list(mapping.cache_keys) if mapping else []
    
    async def invalidate_for_document(
        self,
        doc_id: str,
        cache_invalidate_fn: Optional[Callable] = None,
    ) -> CacheInvalidation:
        """Invalidate all cache entries containing a document."""
        async with self._lock:
            cache_keys = self.get_cache_keys_for_doc(doc_id)
            
            if cache_invalidate_fn and cache_keys:
                for key in cache_keys:
                    try:
                        if asyncio.iscoroutinefunction(cache_invalidate_fn):
                            await cache_invalidate_fn(key)
                        else:
                            cache_invalidate_fn(key)
                    except Exception as e:
                        logger.warning(f"Cache invalidation failed for {key}: {e}")
            
            invalidation = CacheInvalidation(
                invalidation_id=f"inv_{uuid.uuid4().hex[:8]}",
                doc_id=doc_id,
                invalidated_keys=list(cache_keys),
                reason="document_updated",
            )
            self._invalidations.append(invalidation)
            
            if doc_id in self._doc_to_keys:
                for key in self._doc_to_keys[doc_id].cache_keys:
                    if key in self._key_to_docs:
                        self._key_to_docs[key].discard(doc_id)
                del self._doc_to_keys[doc_id]
            
            return invalidation
    
    def get_invalidation_history(self) -> list[CacheInvalidation]:
        """Get recent invalidation history."""
        return list(self._invalidations[-100:])
    
    def get_stats(self) -> dict:
        """Get statistics."""
        return {
            "total_documents": len(self._doc_to_keys),
            "total_cache_keys": len(self._key_to_docs),
            "total_invalidations": len(self._invalidations),
            "bloom_filter_size": len(self._bloom_filter) if self._bloom_enabled else 0,
            "bloom_enabled": self._bloom_enabled,
        }


# ============================================================================
# 7. Explainability Size Limiter
# ============================================================================

class ExplainabilitySizeLimiter:
    """Limits explainability output size.
    
    Caps provenance entries and total bytes to prevent
    performance impact from large explanations.
    """
    
    def __init__(
        self,
        max_provenance_entries: int = 100,
        max_total_bytes: int = 10240,
        min_influence_score: float = 0.1,
    ):
        self._max_entries = max_provenance_entries
        self._max_bytes = max_total_bytes
        self._min_score = min_influence_score
    
    def process_explanation(
        self,
        entries: list[ProvenanceEntry],
        query: str,
        intent: str,
    ) -> RetrievalExplanation:
        """Process and limit explanation size.
        
        Args:
            entries: Raw provenance entries
            query: Original query
            intent: Query intent
            
        Returns:
            Limited explanation
        """
        filtered = [
            e for e in entries
            if e.influence_score >= self._min_score
        ]
        
        filtered.sort(key=lambda x: x.influence_score, reverse=True)
        
        if len(filtered) > self._max_entries:
            filtered = filtered[:self._max_entries]
        
        truncated = False
        truncation_reason = None
        total_bytes = self._estimate_size(filtered)
        
        if total_bytes > self._max_bytes:
            original_len = len(filtered)
            
            while filtered and total_bytes > self._max_bytes:
                filtered.pop()
                total_bytes = self._estimate_size(filtered)
            
            truncated = True
            truncation_reason = (
                f"Truncated from {original_len} to {len(filtered)} entries "
                f"to fit {self._max_bytes} byte limit"
            )
        
        return RetrievalExplanation(
            query=query,
            intent=intent,
            total_chunks=len(entries),
            provenance_entries=filtered,
            total_bytes=total_bytes,
            truncated=truncated,
            truncation_reason=truncation_reason,
        )
    
    def _estimate_size(self, entries: list[ProvenanceEntry]) -> int:
        """Estimate JSON size of entries."""
        return len(json.dumps([
            {
                "chunk_id": e.chunk_id,
                "doc_id": e.doc_id,
                "influence_score": e.influence_score,
                "source_type": e.source_type,
                "text_preview": e.text_preview[:200] if e.text_preview else "",
                "rank": e.rank,
                "vector_score": e.vector_score,
                "lexical_score": e.lexical_score,
            }
            for e in entries
        ]))
    
    def get_limits(self) -> dict:
        """Get current limits."""
        return {
            "max_provenance_entries": self._max_entries,
            "max_total_bytes": self._max_bytes,
            "min_influence_score": self._min_score,
        }
