"""Phase 5C v12 – Advanced RetrievalEngine.

Integrates all Phase 5C enterprise features:
1. SnapshotIsolationRead - Transactional read isolation
2. ReplicaLagAwareRouter - Replica lag awareness
3. PluginVersionManager - Plugin hot reload & rollback
4. QueryTypeBudgeter - Budget per query type
5. GoldenSetDriftDetector - Golden set drift detection
6. DocumentBasedCacheInvalidator - Document-aware cache invalidation
7. ExplainabilitySizeLimiter - Explainability size limits
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

from .retrieval_components import (
    DocumentBasedCacheInvalidator,
    ExplainabilitySizeLimiter,
    GoldenSetDriftDetector,
    PluginVersionManager,
    QueryTypeBudgeter,
    ReplicaLagAwareRouter,
    SnapshotIsolationRead,
)
from .retrieval_config import Phase5CConfig, DEFAULT_PHASE5C_CONFIG
from .retrieval_types import (
    AdvancedRetrievalRequest,
    AdvancedRetrievalResponse,
    GoldenQuery,
    GoldenSet,
    ProvenanceEntry,
    QueryIntent,
    RetrievalExplanation,
)


logger = logging.getLogger(__name__)


class AdvancedRetrievalEngine:
    """Advanced RetrievalEngine with Phase 5C enterprise features.
    
    This engine wraps an existing retrieval system and adds:
    - Transactional snapshot isolation for consistent reads
    - Replica lag awareness for multi-region deployments
    - Plugin hot reload with automatic rollback
    - Per-query-type token budgets
    - Golden set drift detection and alerting
    - Document-aware cache invalidation
    - Explainability output size limits
    """
    
    def __init__(
        self,
        config: Optional[Phase5CConfig] = None,
        retrieval_fn: Optional[Callable] = None,
    ):
        self._config = config or DEFAULT_PHASE5C_CONFIG
        
        self._snapshot_isolation = SnapshotIsolationRead(
            snapshot_ttl_seconds=self._config.read_isolation.snapshot_ttl_seconds,
            max_snapshots=self._config.read_isolation.max_snapshots,
        )
        
        self._replica_router = ReplicaLagAwareRouter(
            max_lag_seconds=self._config.replica_lag.max_lag_seconds,
            fallback_to_primary=self._config.replica_lag.fallback_to_primary,
            check_interval_seconds=self._config.replica_lag.check_interval_seconds,
        )
        
        self._plugin_manager = PluginVersionManager(
            auto_rollback=self._config.plugin_management.auto_rollback,
            version_history_size=self._config.plugin_management.version_history_size,
            rollback_cooldown_seconds=self._config.plugin_management.rollback_cooldown_seconds,
        )
        
        self._query_budgeter = QueryTypeBudgeter(
            per_intent=self._config.query_budget.per_intent,
            default_max_tokens=self._config.query_budget.default_max_tokens,
            default_max_chunks=self._config.query_budget.default_max_chunks,
            default_timeout_seconds=self._config.query_budget.default_timeout_seconds,
        )
        
        self._drift_detector = GoldenSetDriftDetector(
            eval_interval_hours=self._config.golden_set.eval_interval_hours,
            drift_threshold=self._config.golden_set.drift_threshold,
            alert_webhook=self._config.golden_set.alert_webhook,
        )
        
        self._cache_invalidator = DocumentBasedCacheInvalidator(
            bloom_filter_enabled=self._config.cache.bloom_filter_enabled,
            bloom_filter_fp_rate=self._config.cache.bloom_filter_false_positive,
            mapping_ttl_seconds=self._config.cache.mapping_ttl_seconds,
        )
        
        self._explainability_limiter = ExplainabilitySizeLimiter(
            max_provenance_entries=self._config.explainability.max_provenance_entries,
            max_total_bytes=self._config.explainability.max_total_bytes,
            min_influence_score=self._config.explainability.min_influence_score,
        )
        
        self._retrieval_fn = retrieval_fn
        self._active_retrievals: dict[str, dict] = {}
    
    # =========================================================================
    # Snapshot Isolation Methods
    # =========================================================================
    
    async def begin_retrieval_transaction(
        self,
        transaction_id: Optional[str] = None,
    ) -> str:
        """Begin a retrieval transaction with snapshot isolation.
        
        Returns:
            transaction_id for the new transaction
        """
        txn = self._snapshot_isolation.begin_transaction(transaction_id)
        self._active_retrievals[txn.transaction_id] = {
            "started_at": int(time.time()),
            "snapshot": None,
        }
        return txn.transaction_id
    
    async def get_snapshot(
        self,
        snapshot_id: str,
    ) -> Optional[dict]:
        """Get snapshot data by ID."""
        snapshot = self._snapshot_isolation.get_snapshot(snapshot_id)
        if snapshot:
            return {
                "snapshot_id": snapshot.snapshot_id,
                "transaction_id": snapshot.transaction_id,
                "created_at": snapshot.created_at,
                "committed_at": snapshot.committed_at,
                "status": snapshot.status.value,
                "document_versions": snapshot.document_versions,
            }
        return None
    
    async def commit_transaction(self, transaction_id: str) -> bool:
        """Commit the transaction."""
        snapshot = self._snapshot_isolation.commit_transaction(transaction_id)
        if transaction_id in self._active_retrievals:
            del self._active_retrievals[transaction_id]
        return snapshot is not None
    
    async def abort_transaction(self, transaction_id: str) -> None:
        """Abort the transaction without committing."""
        self._snapshot_isolation.abort_transaction(transaction_id)
        if transaction_id in self._active_retrievals:
            del self._active_retrievals[transaction_id]
    
    # =========================================================================
    # Replica Lag Router Methods
    # =========================================================================
    
    async def set_replica_lag_threshold(self, threshold_seconds: float) -> None:
        """Set the maximum acceptable replica lag threshold."""
        self._config.replica_lag.max_lag_seconds = threshold_seconds
        self._replica_router = ReplicaLagAwareRouter(
            max_lag_seconds=threshold_seconds,
            fallback_to_primary=self._config.replica_lag.fallback_to_primary,
            check_interval_seconds=self._config.replica_lag.check_interval_seconds,
        )
    
    def register_replica(self, replica_id: str) -> None:
        """Register a new replica."""
        self._replica_router.register_replica(replica_id)
    
    def update_replica_lag(self, replica_id: str, lag_seconds: float) -> None:
        """Update replica's replication lag."""
        self._replica_router.update_replica_lag(replica_id, lag_seconds)
    
    async def get_best_replica(self) -> tuple[Optional[str], bool]:
        """Get best replica for read query."""
        return await self._replica_router.get_best_replica()
    
    # =========================================================================
    # Plugin Version Manager Methods
    # =========================================================================
    
    async def register_plugin(
        self,
        plugin_name: str,
        version: str,
        config: Optional[dict] = None,
    ) -> dict:
        """Register a new plugin version."""
        pv = await self._plugin_manager.register_plugin(plugin_name, version, config)
        return {
            "plugin_name": pv.plugin_name,
            "version": pv.version,
            "status": pv.status.value,
            "rollback_count": pv.rollback_count,
        }
    
    async def load_plugin(
        self,
        plugin_name: str,
        version: str,
    ) -> tuple[bool, Optional[str]]:
        """Load a plugin with health check."""
        return await self._plugin_manager.load_plugin(plugin_name, version)
    
    async def rollback_plugin(
        self,
        plugin_name: str,
        target_version: str,
    ) -> tuple[bool, Optional[str]]:
        """Rollback plugin to a specific version."""
        return await self._plugin_manager.rollback_plugin(plugin_name, target_version)
    
    def get_active_plugin_version(self, plugin_name: str) -> Optional[str]:
        """Get currently active plugin version."""
        return self._plugin_manager.get_active_version(plugin_name)
    
    # =========================================================================
    # Query Type Budgeter Methods
    # =========================================================================
    
    def get_budget_for_intent(self, intent: str) -> dict:
        """Get budget configuration for an intent."""
        budget = self._query_budgeter.get_budget(intent)
        return {
            "intent": budget.intent,
            "max_tokens": budget.max_tokens,
            "max_chunks": budget.max_chunks,
            "timeout_seconds": budget.timeout_seconds,
        }
    
    def update_intent_budget(self, intent: str, max_tokens: int) -> None:
        """Update budget for a query intent."""
        self._query_budgeter.update_budget(intent, max_tokens)
    
    # =========================================================================
    # Golden Set Drift Detector Methods
    # =========================================================================
    
    async def update_golden_set(
        self,
        set_id: str,
        queries: list[dict],
    ) -> bool:
        """Update golden set with new queries."""
        golden_queries = [
            GoldenQuery(
                query_id=q.get("query_id", f"q_{i}"),
                query_text=q["query_text"],
                expected_doc_ids=q.get("expected_doc_ids", []),
                intent=q.get("intent", "general"),
            )
            for i, q in enumerate(queries)
        ]
        
        golden_set = GoldenSet(
            set_id=set_id,
            name=queries[0].get("name", set_id) if queries else set_id,
            description=queries[0].get("description", "") if queries else "",
            queries=golden_queries,
        )
        
        self._drift_detector.register_golden_set(golden_set)
        return True
    
    async def evaluate_golden_set(
        self,
        set_id: str,
    ) -> Optional[dict]:
        """Evaluate golden set against retrieval function."""
        if not self._retrieval_fn:
            return None
        
        async def retrieval_wrapper(query_text: str) -> list:
            request = AdvancedRetrievalRequest(query=query_text)
            response = await self.retrieve(request)
            return [hit.chunk_id for hit in response.hits]
        
        metrics = await self._drift_detector.evaluate(set_id, retrieval_wrapper)
        
        if metrics:
            return {
                "set_id": metrics.set_id,
                "eval_time": metrics.eval_time,
                "recall_at_1": metrics.recall_at_1,
                "recall_at_5": metrics.recall_at_5,
                "recall_at_10": metrics.recall_at_10,
                "mrr": metrics.mean_reciprocal_rank,
                "total_queries": metrics.total_queries,
                "drift_detected": metrics.drift_detected,
                "drift_reason": metrics.drift_reason,
            }
        return None
    
    def get_golden_set_metrics(self, set_id: str) -> Optional[dict]:
        """Get latest metrics for a golden set."""
        metrics = self._drift_detector.get_latest_metrics(set_id)
        if metrics:
            return {
                "set_id": metrics.set_id,
                "recall_at_5": metrics.recall_at_5,
                "drift_detected": metrics.drift_detected,
            }
        return None
    
    def get_drift_alerts(self) -> list[dict]:
        """Get all drift alerts."""
        return [
            {
                "alert_id": a.alert_id,
                "set_id": a.set_id,
                "drift_percentage": a.drift_percentage,
                "recommendations": a.recommendations,
            }
            for a in self._drift_detector.get_drift_alerts()
        ]
    
    # =========================================================================
    # Document-Aware Cache Invalidation Methods
    # =========================================================================
    
    async def invalidate_cache_for_document(self, doc_id: str) -> dict:
        """Invalidate all cache entries for a document."""
        invalidation = await self._cache_invalidator.invalidate_for_document(doc_id)
        return {
            "invalidation_id": invalidation.invalidation_id,
            "doc_id": invalidation.doc_id,
            "invalidated_keys": invalidation.invalidated_keys,
            "reason": invalidation.reason,
            "timestamp": invalidation.timestamp,
        }
    
    def register_cache_entry(self, doc_id: str, cache_key: str) -> None:
        """Register a cache entry with its document."""
        self._cache_invalidator.register_cache_entry(doc_id, cache_key)
    
    def get_cache_invalidation_stats(self) -> dict:
        """Get cache invalidation statistics."""
        return self._cache_invalidator.get_stats()
    
    # =========================================================================
    # Explainability Methods
    # =========================================================================
    
    def limit_explanation_size(
        self,
        entries: list[dict],
        query: str,
        intent: str,
    ) -> dict:
        """Limit explanation size and return processed explanation."""
        provenance_entries = [
            ProvenanceEntry(
                chunk_id=e["chunk_id"],
                doc_id=e["doc_id"],
                influence_score=e.get("influence_score", 1.0),
                source_type=e.get("source_type", "unknown"),
                text_preview=e.get("text_preview", "")[:200],
                rank=e.get("rank", 0),
                vector_score=e.get("vector_score", 0.0),
                lexical_score=e.get("lexical_score", 0.0),
            )
            for e in entries
        ]
        
        explanation = self._explainability_limiter.process_explanation(
            provenance_entries,
            query,
            intent,
        )
        
        return {
            "query": explanation.query,
            "intent": explanation.intent,
            "total_chunks": explanation.total_chunks,
            "provenance_entries": [
                {
                    "chunk_id": e.chunk_id,
                    "doc_id": e.doc_id,
                    "influence_score": e.influence_score,
                    "source_type": e.source_type,
                    "rank": e.rank,
                    "vector_score": e.vector_score,
                    "lexical_score": e.lexical_score,
                }
                for e in explanation.provenance_entries
            ],
            "total_bytes": explanation.total_bytes,
            "truncated": explanation.truncated,
            "truncation_reason": explanation.truncation_reason,
        }
    
    # =========================================================================
    # Main Retrieval Method
    # =========================================================================
    
    async def retrieve(
        self,
        request: AdvancedRetrievalRequest,
    ) -> AdvancedRetrievalResponse:
        """Perform retrieval with all Phase 5C features applied."""
        budget = self._query_budgeter.get_budget(request.intent.value)
        
        snapshot_id = request.snapshot_id
        is_primary_fallback = False
        replica_used = None
        
        if self._config.read_isolation.enabled:
            replica_used, is_primary_fallback = await self._replica_router.get_best_replica()
            
            if request.snapshot_id:
                snapshot = self._snapshot_isolation.get_snapshot(request.snapshot_id)
            else:
                txn_id = await self.begin_retrieval_transaction()
                snapshot = self._snapshot_isolation.get_or_create_snapshot(txn_id)
                snapshot_id = snapshot.snapshot_id
                self._active_retrievals[txn_id]["snapshot"] = snapshot
        
        hits = []
        if self._retrieval_fn:
            try:
                hits = await self._retrieval_fn(
                    request.query,
                    top_k=budget.max_chunks,
                )
            except Exception as e:
                logger.error(f"Retrieval failed: {e}")
        
        explanation = None
        if request.require_explanation and hits:
            provenance = [
                {
                    "chunk_id": hit.chunk_id if hasattr(hit, "chunk_id") else str(hit),
                    "doc_id": hit.metadata.get("doc_id", "") if hasattr(hit, "metadata") else "",
                    "influence_score": 1.0 / (i + 1),
                    "source_type": hit.source_type if hasattr(hit, "source_type") else "unknown",
                    "text_preview": hit.text[:200] if hasattr(hit, "text") else "",
                    "rank": i,
                    "vector_score": hit.vector_score if hasattr(hit, "vector_score") else 0.0,
                    "lexical_score": hit.lexical_score if hasattr(hit, "lexical_score") else 0.0,
                }
                for i, hit in enumerate(hits)
            ]
            
            explanation = self.limit_explanation_size(
                provenance,
                request.query,
                request.intent.value,
            )
        
        metadata = {
            "intent": request.intent.value,
            "budget_applied": budget.max_tokens,
        }
        
        if is_primary_fallback:
            metadata["warning"] = "Primary fallback used due to all replicas being stale"
        
        return AdvancedRetrievalResponse(
            hits=hits,
            explanation=explanation,
            snapshot_id=snapshot_id,
            replica_used=replica_used,
            budget_used=budget,
            metadata=metadata,
        )
    
    # =========================================================================
    # Configuration Methods
    # =========================================================================
    
    def get_config(self) -> dict:
        """Get current configuration."""
        return self._config.to_dict()
    
    def update_config(self, config: Phase5CConfig) -> None:
        """Update configuration at runtime."""
        self._config = config
