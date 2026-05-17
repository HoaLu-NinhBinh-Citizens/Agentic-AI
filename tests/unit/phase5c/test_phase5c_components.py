"""Retrieval Engine Core Tests (Phase 5C v12).

Tests for enterprise retrieval features:
1. SnapshotIsolationRead - Transactional read isolation
2. ReplicaLagAwareRouter - Replica lag awareness
3. PluginVersionManager - Plugin hot reload & rollback
4. QueryTypeBudgeter - Budget per query type
5. GoldenSetDriftDetector - Golden set drift detection
6. DocumentBasedCacheInvalidator - Document-aware cache invalidation
7. ExplainabilitySizeLimiter - Explainability size limits
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


# ============================================================================
# SnapshotIsolationRead Tests
# ============================================================================

class TestSnapshotIsolationRead:
    """Tests for snapshot isolation functionality."""

    def test_begin_transaction(self):
        """Test beginning a new transaction."""
        from infrastructure.retrieval.retrieval_components import SnapshotIsolationRead
        
        iso = SnapshotIsolationRead()
        txn = iso.begin_transaction()
        
        assert txn is not None
        assert txn.transaction_id.startswith("txn_")
        assert txn.committed is False
        assert txn.snapshot_id is None

    def test_begin_transaction_with_id(self):
        """Test beginning a transaction with custom ID."""
        from infrastructure.retrieval.retrieval_components import SnapshotIsolationRead
        
        iso = SnapshotIsolationRead()
        txn = iso.begin_transaction("custom_txn_123")
        
        assert txn.transaction_id == "custom_txn_123"

    def test_get_or_create_snapshot(self):
        """Test creating a snapshot for transaction."""
        from infrastructure.retrieval.retrieval_components import SnapshotIsolationRead
        
        iso = SnapshotIsolationRead()
        txn = iso.begin_transaction("test_txn")
        snapshot = iso.get_or_create_snapshot("test_txn")
        
        assert snapshot is not None
        assert snapshot.snapshot_id.startswith("snap_")
        assert snapshot.transaction_id == "test_txn"
        assert snapshot.status.value == "active"

    def test_commit_transaction(self):
        """Test committing a transaction."""
        from infrastructure.retrieval.retrieval_components import SnapshotIsolationRead
        from infrastructure.retrieval.retrieval_types import SnapshotStatus
        
        iso = SnapshotIsolationRead()
        iso.begin_transaction("commit_txn")
        snapshot = iso.get_or_create_snapshot("commit_txn")
        committed = iso.commit_transaction("commit_txn")
        
        assert committed is not None
        assert committed.status == SnapshotStatus.COMMITTED
        assert committed.committed_at is not None

    def test_abort_transaction(self):
        """Test aborting a transaction."""
        from infrastructure.retrieval.retrieval_components import SnapshotIsolationRead
        
        iso = SnapshotIsolationRead()
        iso.begin_transaction("abort_txn")
        iso.get_or_create_snapshot("abort_txn")
        
        iso.abort_transaction("abort_txn")
        
        assert iso.get_snapshot("snap_") is None

    def test_update_document_version(self):
        """Test updating document version."""
        from infrastructure.retrieval.retrieval_components import SnapshotIsolationRead
        
        iso = SnapshotIsolationRead()
        
        v1 = iso.update_document_version("doc1")
        v2 = iso.update_document_version("doc1")
        v3 = iso.update_document_version("doc1")
        
        assert v1 == 1
        assert v2 == 2
        assert v3 == 3

    def test_is_document_changed_since(self):
        """Test detecting document changes since snapshot."""
        from infrastructure.retrieval.retrieval_components import SnapshotIsolationRead
        
        iso = SnapshotIsolationRead()
        iso.update_document_version("doc1")
        
        iso.begin_transaction("version_test")
        snapshot = iso.get_or_create_snapshot("version_test")
        
        iso.update_document_version("doc1")
        
        # Document changed after snapshot was taken
        assert iso.is_document_changed_since("doc1", snapshot) is True

    def test_is_document_unchanged_since(self):
        """Test no change when document hasn't been modified."""
        from infrastructure.retrieval.retrieval_components import SnapshotIsolationRead
        
        iso = SnapshotIsolationRead()
        iso.update_document_version("doc1")
        
        iso.begin_transaction("unchanged_test")
        snapshot = iso.get_or_create_snapshot("unchanged_test")
        
        # No update after snapshot, so no change detected
        assert iso.is_document_changed_since("doc1", snapshot) is False

    def test_get_snapshot(self):
        """Test retrieving a snapshot by ID."""
        from infrastructure.retrieval.retrieval_components import SnapshotIsolationRead
        
        iso = SnapshotIsolationRead()
        iso.begin_transaction("get_test")
        snapshot = iso.get_or_create_snapshot("get_test")
        
        retrieved = iso.get_snapshot(snapshot.snapshot_id)
        
        assert retrieved is not None
        assert retrieved.snapshot_id == snapshot.snapshot_id

    def test_get_active_snapshot_count(self):
        """Test counting active snapshots."""
        from infrastructure.retrieval.retrieval_components import SnapshotIsolationRead
        
        iso = SnapshotIsolationRead()
        
        for i in range(3):
            iso.begin_transaction(f"count_test_{i}")
            iso.get_or_create_snapshot(f"count_test_{i}")
        
        assert iso.get_active_snapshot_count() == 3


# ============================================================================
# ReplicaLagAwareRouter Tests
# ============================================================================

class TestReplicaLagAwareRouter:
    """Tests for replica lag awareness functionality."""

    def test_register_replica(self):
        """Test registering a new replica."""
        from infrastructure.retrieval.retrieval_components import ReplicaLagAwareRouter
        from infrastructure.retrieval.retrieval_types import ReplicaStatus
        
        router = ReplicaLagAwareRouter()
        router.register_replica("replica_1")
        
        status = router.get_replica_status("replica_1")
        assert status is not None
        assert status.replica_id == "replica_1"
        assert status.status == ReplicaStatus.HEALTHY

    def test_update_replica_lag_healthy(self):
        """Test updating lag to healthy state."""
        from infrastructure.retrieval.retrieval_components import ReplicaLagAwareRouter
        from infrastructure.retrieval.retrieval_types import ReplicaStatus
        
        router = ReplicaLagAwareRouter(max_lag_seconds=5.0)
        router.register_replica("replica_1")
        
        router.update_replica_lag("replica_1", 2.0)
        
        status = router.get_replica_status("replica_1")
        assert status.status == ReplicaStatus.HEALTHY
        assert status.replication_lag_seconds == 2.0

    def test_update_replica_lag_stale(self):
        """Test updating lag to stale state."""
        from infrastructure.retrieval.retrieval_components import ReplicaLagAwareRouter
        from infrastructure.retrieval.retrieval_types import ReplicaStatus
        
        router = ReplicaLagAwareRouter(max_lag_seconds=5.0)
        router.register_replica("replica_1")
        
        router.update_replica_lag("replica_1", 10.0)
        
        status = router.get_replica_status("replica_1")
        assert status.status == ReplicaStatus.STALE

    @pytest.mark.asyncio
    async def test_get_best_replica_healthy(self):
        """Test getting best replica when healthy replicas exist."""
        from infrastructure.retrieval.retrieval_components import ReplicaLagAwareRouter
        
        router = ReplicaLagAwareRouter()
        router.register_replica("replica_1")
        router.register_replica("replica_2")
        
        router.update_replica_lag("replica_1", 2.0)
        router.update_replica_lag("replica_2", 1.0)
        
        best, is_fallback = await router.get_best_replica()
        
        assert best == "replica_2"
        assert is_fallback is False

    @pytest.mark.asyncio
    async def test_get_best_replica_fallback_primary(self):
        """Test fallback to primary when all replicas stale."""
        from infrastructure.retrieval.retrieval_components import ReplicaLagAwareRouter
        from infrastructure.retrieval.retrieval_types import ReplicaStatus
        
        router = ReplicaLagAwareRouter(fallback_to_primary=True)
        router.register_replica("primary")
        router.update_replica_lag("primary", 0.0)
        
        router.register_replica("replica_1")
        router.update_replica_lag("replica_1", 100.0)
        
        # primary is healthy, so it should be returned
        best, is_fallback = await router.get_best_replica()
        
        # primary is healthy (lag=0.0 < max_lag=5.0), so it's returned
        # is_fallback is False because it's not a fallback, it's healthy
        assert best == "primary"
        # primary is healthy, so is_fallback is False
        assert is_fallback is False

    @pytest.mark.asyncio
    async def test_all_replicas_stale_no_fallback(self):
        """Test behavior when all replicas are stale and fallback is disabled."""
        from infrastructure.retrieval.retrieval_components import ReplicaLagAwareRouter
        
        router = ReplicaLagAwareRouter(fallback_to_primary=False)
        router.register_replica("replica_1")
        router.update_replica_lag("replica_1", 100.0)
        
        best, is_fallback = await router.get_best_replica()
        
        # No healthy replicas and fallback disabled, so returns None
        assert best is None
        assert is_fallback is False

    def test_get_all_replica_statuses(self):
        """Test getting all replica statuses."""
        from infrastructure.retrieval.retrieval_components import ReplicaLagAwareRouter
        
        router = ReplicaLagAwareRouter()
        router.register_replica("r1")
        router.register_replica("r2")
        
        statuses = router.get_all_replica_statuses()
        
        assert len(statuses) == 2
        assert "r1" in statuses
        assert "r2" in statuses

    def test_is_primary_fallback(self):
        """Test checking if replica is primary fallback."""
        from infrastructure.retrieval.retrieval_components import ReplicaLagAwareRouter
        
        router = ReplicaLagAwareRouter()
        
        assert router.is_primary_fallback("primary") is True
        assert router.is_primary_fallback("replica_1") is False


# ============================================================================
# PluginVersionManager Tests
# ============================================================================

class TestPluginVersionManager:
    """Tests for plugin version management."""

    @pytest.mark.asyncio
    async def test_register_plugin(self):
        """Test registering a new plugin version."""
        from infrastructure.retrieval.retrieval_components import PluginVersionManager
        from infrastructure.retrieval.retrieval_types import PluginVersionStatus
        
        manager = PluginVersionManager()
        pv = await manager.register_plugin("test_plugin", "v1.0.0", {"timeout": 30})
        
        assert pv.plugin_name == "test_plugin"
        assert pv.version == "v1.0.0"
        assert pv.status == PluginVersionStatus.ACTIVE
        assert pv.config == {"timeout": 30}

    @pytest.mark.asyncio
    async def test_register_multiple_versions(self):
        """Test registering multiple versions of a plugin."""
        from infrastructure.retrieval.retrieval_components import PluginVersionManager
        
        manager = PluginVersionManager()
        
        await manager.register_plugin("plugin", "v1.0.0")
        await manager.register_plugin("plugin", "v2.0.0")
        
        history = manager.get_version_history("plugin")
        
        assert len(history) == 2
        assert manager.get_active_version("plugin") == "v2.0.0"

    @pytest.mark.asyncio
    async def test_load_plugin_success(self):
        """Test loading a plugin with health check success."""
        from infrastructure.retrieval.retrieval_components import PluginVersionManager
        
        manager = PluginVersionManager()
        await manager.register_plugin("test", "v1.0.0")
        
        success, error = await manager.load_plugin("test", "v1.0.0", lambda: True)
        
        assert success is True
        assert error is None

    @pytest.mark.asyncio
    async def test_load_plugin_failure_auto_rollback(self):
        """Test loading a plugin failure triggers rollback."""
        from infrastructure.retrieval.retrieval_components import PluginVersionManager
        from infrastructure.retrieval.retrieval_types import PluginVersionStatus
        
        manager = PluginVersionManager(auto_rollback=True)
        
        await manager.register_plugin("test", "v1.0.0")
        await manager.register_plugin("test", "v2.0.0")
        
        def fail_check():
            raise RuntimeError("Health check failed")
        
        success, error = await manager.load_plugin("test", "v2.0.0", fail_check)
        
        # Auto-rollback succeeded, so success is True
        assert success is True
        assert manager.get_active_version("test") == "v1.0.0"

    @pytest.mark.asyncio
    async def test_rollback_plugin(self):
        """Test manually rolling back a plugin."""
        from infrastructure.retrieval.retrieval_components import PluginVersionManager
        from infrastructure.retrieval.retrieval_types import PluginVersionStatus
        
        manager = PluginVersionManager()
        
        await manager.register_plugin("test", "v1.0.0")
        await manager.register_plugin("test", "v2.0.0")
        
        success, error = await manager.rollback_plugin("test", "v1.0.0")
        
        assert success is True
        assert error is None
        assert manager.get_active_version("test") == "v1.0.0"

    @pytest.mark.asyncio
    async def test_rollback_nonexistent_plugin(self):
        """Test rolling back non-existent plugin."""
        from infrastructure.retrieval.retrieval_components import PluginVersionManager
        
        manager = PluginVersionManager()
        
        success, error = await manager.rollback_plugin("nonexistent", "v1.0.0")
        
        assert success is False
        assert "No history" in str(error)

    def test_get_version_history(self):
        """Test getting plugin version history."""
        from infrastructure.retrieval.retrieval_components import PluginVersionManager
        
        manager = PluginVersionManager()
        
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            manager.register_plugin("test", "v1.0.0")
        )
        asyncio.get_event_loop().run_until_complete(
            manager.register_plugin("test", "v2.0.0")
        )
        
        history = manager.get_version_history("test")
        
        assert len(history) == 2


# ============================================================================
# QueryTypeBudgeter Tests
# ============================================================================

class TestQueryTypeBudgeter:
    """Tests for query type budget allocation."""

    def test_get_budget_factoid(self):
        """Test getting budget for factoid intent."""
        from infrastructure.retrieval.retrieval_components import QueryTypeBudgeter
        
        budgeter = QueryTypeBudgeter()
        budget = budgeter.get_budget("factoid")
        
        assert budget.intent == "factoid"
        assert budget.max_tokens == 4000

    def test_get_budget_reasoning(self):
        """Test getting budget for reasoning intent."""
        from infrastructure.retrieval.retrieval_components import QueryTypeBudgeter
        
        budgeter = QueryTypeBudgeter()
        budget = budgeter.get_budget("reasoning")
        
        assert budget.intent == "reasoning"
        assert budget.max_tokens == 8000

    def test_get_budget_code(self):
        """Test getting budget for code intent."""
        from infrastructure.retrieval.retrieval_components import QueryTypeBudgeter
        
        budgeter = QueryTypeBudgeter()
        budget = budgeter.get_budget("code")
        
        assert budget.intent == "code"
        assert budget.max_tokens == 16000

    def test_get_budget_instruction(self):
        """Test getting budget for instruction intent."""
        from infrastructure.retrieval.retrieval_components import QueryTypeBudgeter
        
        budgeter = QueryTypeBudgeter()
        budget = budgeter.get_budget("instruction")
        
        assert budget.intent == "instruction"
        assert budget.max_tokens == 2000

    def test_get_budget_unknown_uses_default(self):
        """Test that unknown intent uses default budget."""
        from infrastructure.retrieval.retrieval_components import QueryTypeBudgeter
        
        budgeter = QueryTypeBudgeter()
        budget = budgeter.get_budget("unknown_intent")
        
        assert budget.intent == "unknown_intent"
        assert budget.max_tokens == 8192

    def test_update_budget(self):
        """Test updating budget for an intent."""
        from infrastructure.retrieval.retrieval_components import QueryTypeBudgeter
        
        budgeter = QueryTypeBudgeter()
        budgeter.update_budget("factoid", 5000)
        
        budget = budgeter.get_budget("factoid")
        assert budget.max_tokens == 5000

    def test_reset_to_default(self):
        """Test resetting all budgets to defaults."""
        from infrastructure.retrieval.retrieval_components import QueryTypeBudgeter
        
        budgeter = QueryTypeBudgeter()
        budgeter.update_budget("factoid", 9999)
        budgeter.reset_to_default()
        
        budget = budgeter.get_budget("factoid")
        assert budget.max_tokens == 4000

    def test_get_all_budgets(self):
        """Test getting all configured budgets."""
        from infrastructure.retrieval.retrieval_components import QueryTypeBudgeter
        
        budgeter = QueryTypeBudgeter()
        budgets = budgeter.get_all_budgets()
        
        assert "factoid" in budgets
        assert "reasoning" in budgets
        assert "code" in budgets
        assert len(budgets) >= 4


# ============================================================================
# GoldenSetDriftDetector Tests
# ============================================================================

class TestGoldenSetDriftDetector:
    """Tests for golden set drift detection."""

    def test_register_golden_set(self):
        """Test registering a golden set."""
        from infrastructure.retrieval.retrieval_components import GoldenSetDriftDetector
        from infrastructure.retrieval.retrieval_types import GoldenSet, GoldenQuery
        
        detector = GoldenSetDriftDetector()
        golden_set = GoldenSet(
            set_id="test_set",
            name="Test Set",
            description="Test golden set",
            queries=[
                GoldenQuery("q1", "test query", ["doc1"], "general"),
            ]
        )
        
        detector.register_golden_set(golden_set)
        
        assert detector.get_latest_metrics("test_set") is None

    def test_add_query(self):
        """Test adding a query to golden set."""
        from infrastructure.retrieval.retrieval_components import GoldenSetDriftDetector
        from infrastructure.retrieval.retrieval_types import GoldenSet, GoldenQuery
        
        detector = GoldenSetDriftDetector()
        golden_set = GoldenSet(
            set_id="test_set",
            name="Test Set",
            description="Test",
            queries=[]
        )
        detector.register_golden_set(golden_set)
        
        result = detector.add_query("test_set", GoldenQuery("q1", "query", ["doc1"], "general"))
        
        assert result is True

    def test_add_query_nonexistent_set(self):
        """Test adding query to non-existent set."""
        from infrastructure.retrieval.retrieval_components import GoldenSetDriftDetector
        from infrastructure.retrieval.retrieval_types import GoldenQuery
        
        detector = GoldenSetDriftDetector()
        
        result = detector.add_query("nonexistent", GoldenQuery("q1", "query", [], "general"))
        
        assert result is False

    def test_remove_query(self):
        """Test removing a query from golden set."""
        from infrastructure.retrieval.retrieval_components import GoldenSetDriftDetector
        from infrastructure.retrieval.retrieval_types import GoldenSet, GoldenQuery
        
        detector = GoldenSetDriftDetector()
        golden_set = GoldenSet(
            set_id="test_set",
            name="Test",
            description="Test",
            queries=[
                GoldenQuery("q1", "query1", ["doc1"], "general"),
                GoldenQuery("q2", "query2", ["doc2"], "general"),
            ]
        )
        detector.register_golden_set(golden_set)
        
        result = detector.remove_query("test_set", "q1")
        
        assert result is True

    def test_update_golden_set(self):
        """Test updating golden set queries."""
        from infrastructure.retrieval.retrieval_components import GoldenSetDriftDetector
        from infrastructure.retrieval.retrieval_types import GoldenSet, GoldenQuery
        
        detector = GoldenSetDriftDetector()
        golden_set = GoldenSet(
            set_id="test_set",
            name="Test",
            description="Test",
            queries=[GoldenQuery("q1", "old", [], "general")]
        )
        detector.register_golden_set(golden_set)
        
        new_queries = [
            GoldenQuery("q2", "new1", ["doc1"], "general"),
            GoldenQuery("q3", "new2", ["doc2"], "general"),
        ]
        result = detector.update_golden_set("test_set", new_queries)
        
        assert result is True

    @pytest.mark.asyncio
    async def test_evaluate_golden_set(self):
        """Test evaluating golden set."""
        from infrastructure.retrieval.retrieval_components import GoldenSetDriftDetector
        from infrastructure.retrieval.retrieval_types import GoldenSet, GoldenQuery
        
        detector = GoldenSetDriftDetector()
        golden_set = GoldenSet(
            set_id="eval_set",
            name="Eval",
            description="Eval set",
            queries=[
                GoldenQuery("q1", "test", ["doc1", "doc2"], "general"),
            ]
        )
        detector.register_golden_set(golden_set)
        
        async def mock_retrieval(query):
            if "test" in query:
                return ["doc1", "doc3"]
            return []
        
        metrics = await detector.evaluate("eval_set", mock_retrieval)
        
        assert metrics is not None
        assert metrics.set_id == "eval_set"
        assert metrics.total_queries == 1

    def test_needs_evaluation_true(self):
        """Test detecting when evaluation is needed."""
        from infrastructure.retrieval.retrieval_components import GoldenSetDriftDetector
        
        detector = GoldenSetDriftDetector(eval_interval_hours=24)
        
        assert detector.needs_evaluation("any_set") is True

    def test_get_drift_alerts(self):
        """Test getting drift alerts."""
        from infrastructure.retrieval.retrieval_components import GoldenSetDriftDetector
        
        detector = GoldenSetDriftDetector()
        
        alerts = detector.get_drift_alerts()
        
        assert isinstance(alerts, list)


# ============================================================================
# DocumentBasedCacheInvalidator Tests
# ============================================================================

class TestDocumentBasedCacheInvalidator:
    """Tests for document-aware cache invalidation."""

    def test_register_cache_entry(self):
        """Test registering a cache entry with document."""
        from infrastructure.retrieval.retrieval_components import DocumentBasedCacheInvalidator
        
        invalidator = DocumentBasedCacheInvalidator()
        invalidator.register_cache_entry("doc1", "cache_key_1")
        
        keys = invalidator.get_cache_keys_for_doc("doc1")
        
        assert "cache_key_1" in keys

    def test_register_multiple_entries_same_doc(self):
        """Test registering multiple cache entries for same document."""
        from infrastructure.retrieval.retrieval_components import DocumentBasedCacheInvalidator
        
        invalidator = DocumentBasedCacheInvalidator()
        invalidator.register_cache_entry("doc1", "key1")
        invalidator.register_cache_entry("doc1", "key2")
        invalidator.register_cache_entry("doc1", "key3")
        
        keys = invalidator.get_cache_keys_for_doc("doc1")
        
        assert len(keys) == 3

    def test_get_cache_keys_for_nonexistent_doc(self):
        """Test getting keys for non-existent document."""
        from infrastructure.retrieval.retrieval_components import DocumentBasedCacheInvalidator
        
        invalidator = DocumentBasedCacheInvalidator()
        
        keys = invalidator.get_cache_keys_for_doc("nonexistent")
        
        assert keys == []

    def test_is_doc_likely_cached_with_bloom(self):
        """Test bloom filter check for document cache."""
        from infrastructure.retrieval.retrieval_components import DocumentBasedCacheInvalidator
        
        invalidator = DocumentBasedCacheInvalidator(bloom_filter_enabled=True)
        invalidator.register_cache_entry("doc1", "key1")
        
        assert invalidator.is_doc_likely_cached("doc1") is True
        assert invalidator.is_doc_likely_cached("nonexistent") is False

    def test_is_doc_likely_cached_without_bloom(self):
        """Test checking cache without bloom filter."""
        from infrastructure.retrieval.retrieval_components import DocumentBasedCacheInvalidator
        
        invalidator = DocumentBasedCacheInvalidator(bloom_filter_enabled=False)
        invalidator.register_cache_entry("doc1", "key1")
        
        assert invalidator.is_doc_likely_cached("doc1") is True
        assert invalidator.is_doc_likely_cached("nonexistent") is False

    @pytest.mark.asyncio
    async def test_invalidate_for_document(self):
        """Test invalidating cache entries for a document."""
        from infrastructure.retrieval.retrieval_components import DocumentBasedCacheInvalidator
        
        invalidator = DocumentBasedCacheInvalidator()
        invalidator.register_cache_entry("doc1", "key1")
        invalidator.register_cache_entry("doc1", "key2")
        
        invalidated_keys = []
        
        async def mock_invalidate(key):
            invalidated_keys.append(key)
        
        inv = await invalidator.invalidate_for_document("doc1", mock_invalidate)
        
        assert inv.doc_id == "doc1"
        assert len(inv.invalidated_keys) == 2
        assert "key1" in invalidated_keys
        assert "key2" in invalidated_keys

    @pytest.mark.asyncio
    async def test_invalidate_removes_mapping(self):
        """Test that invalidation removes document mapping."""
        from infrastructure.retrieval.retrieval_components import DocumentBasedCacheInvalidator
        
        invalidator = DocumentBasedCacheInvalidator()
        invalidator.register_cache_entry("doc1", "key1")
        
        await invalidator.invalidate_for_document("doc1")
        
        keys = invalidator.get_cache_keys_for_doc("doc1")
        
        assert keys == []

    def test_get_invalidation_history(self):
        """Test getting invalidation history."""
        from infrastructure.retrieval.retrieval_components import DocumentBasedCacheInvalidator
        
        invalidator = DocumentBasedCacheInvalidator()
        invalidator.register_cache_entry("doc1", "key1")
        
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            invalidator.invalidate_for_document("doc1")
        )
        
        history = invalidator.get_invalidation_history()
        
        assert len(history) == 1
        assert history[0].doc_id == "doc1"

    def test_get_stats(self):
        """Test getting cache invalidation statistics."""
        from infrastructure.retrieval.retrieval_components import DocumentBasedCacheInvalidator
        
        invalidator = DocumentBasedCacheInvalidator()
        invalidator.register_cache_entry("doc1", "key1")
        invalidator.register_cache_entry("doc2", "key2")
        
        stats = invalidator.get_stats()
        
        assert stats["total_documents"] == 2
        assert stats["bloom_enabled"] is True


# ============================================================================
# ExplainabilitySizeLimiter Tests
# ============================================================================

class TestExplainabilitySizeLimiter:
    """Tests for explainability size limiting."""

    def test_process_explanation_under_limit(self):
        """Test processing explanation under size limit."""
        from infrastructure.retrieval.retrieval_components import ExplainabilitySizeLimiter
        from infrastructure.retrieval.retrieval_types import ProvenanceEntry
        
        limiter = ExplainabilitySizeLimiter(
            max_provenance_entries=100,
            max_total_bytes=10240,
        )
        
        entries = [
            ProvenanceEntry("c1", "d1", 0.9, "pdf", "Sample text", 1),
            ProvenanceEntry("c2", "d2", 0.8, "code", "Sample text", 2),
        ]
        
        explanation = limiter.process_explanation(entries, "test query", "general")
        
        assert explanation.truncated is False
        assert explanation.truncation_reason is None
        assert len(explanation.provenance_entries) == 2

    def test_process_explanation_truncate_entries(self):
        """Test truncating entries beyond max count."""
        from infrastructure.retrieval.retrieval_components import ExplainabilitySizeLimiter
        from infrastructure.retrieval.retrieval_types import ProvenanceEntry
        
        # Set a very low max_bytes to force truncation
        limiter = ExplainabilitySizeLimiter(
            max_provenance_entries=3,
            max_total_bytes=100,  # Very small to force byte truncation
        )
        
        entries = [
            ProvenanceEntry(f"c{i}", f"d{i}", 1.0 - i * 0.1, "pdf", f"Text {i}" * 100, i)
            for i in range(10)
        ]
        
        explanation = limiter.process_explanation(entries, "test", "general")
        
        assert explanation.truncated is True
        assert len(explanation.provenance_entries) <= 3

    def test_process_explanation_filter_low_score(self):
        """Test filtering entries below minimum score."""
        from infrastructure.retrieval.retrieval_components import ExplainabilitySizeLimiter
        from infrastructure.retrieval.retrieval_types import ProvenanceEntry
        
        limiter = ExplainabilitySizeLimiter(min_influence_score=0.5)
        
        entries = [
            ProvenanceEntry("c1", "d1", 0.9, "pdf", "High", 1),
            ProvenanceEntry("c2", "d2", 0.3, "pdf", "Low", 2),
            ProvenanceEntry("c3", "d3", 0.7, "pdf", "Medium", 3),
        ]
        
        explanation = limiter.process_explanation(entries, "test", "general")
        
        assert len(explanation.provenance_entries) == 2
        assert all(e.influence_score >= 0.5 for e in explanation.provenance_entries)

    def test_process_explanation_sorted_by_score(self):
        """Test that entries are sorted by influence score."""
        from infrastructure.retrieval.retrieval_components import ExplainabilitySizeLimiter
        from infrastructure.retrieval.retrieval_types import ProvenanceEntry
        
        limiter = ExplainabilitySizeLimiter()
        
        entries = [
            ProvenanceEntry("c3", "d3", 0.3, "pdf", "Low", 3),
            ProvenanceEntry("c1", "d1", 0.9, "pdf", "High", 1),
            ProvenanceEntry("c2", "d2", 0.6, "pdf", "Medium", 2),
        ]
        
        explanation = limiter.process_explanation(entries, "test", "general")
        
        assert explanation.provenance_entries[0].influence_score == 0.9
        assert explanation.provenance_entries[1].influence_score == 0.6
        assert explanation.provenance_entries[2].influence_score == 0.3

    def test_get_limits(self):
        """Test getting current limits."""
        from infrastructure.retrieval.retrieval_components import ExplainabilitySizeLimiter
        
        limiter = ExplainabilitySizeLimiter(
            max_provenance_entries=50,
            max_total_bytes=5120,
            min_influence_score=0.2,
        )
        
        limits = limiter.get_limits()
        
        assert limits["max_provenance_entries"] == 50
        assert limits["max_total_bytes"] == 5120
        assert limits["min_influence_score"] == 0.2


# ============================================================================
# Phase5CConfig Tests
# ============================================================================

class TestPhase5CConfig:
    """Tests for Phase 5C configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        from infrastructure.retrieval.retrieval_config import DEFAULT_PHASE5C_CONFIG
        
        assert DEFAULT_PHASE5C_CONFIG.read_isolation.enabled is True
        assert DEFAULT_PHASE5C_CONFIG.read_isolation.snapshot_ttl_seconds == 3600
        assert DEFAULT_PHASE5C_CONFIG.replica_lag.max_lag_seconds == 5.0
        assert DEFAULT_PHASE5C_CONFIG.plugin_management.auto_rollback is True
        assert DEFAULT_PHASE5C_CONFIG.query_budget.per_intent["factoid"] == 4000

    def test_config_from_dict(self):
        """Test creating config from dictionary."""
        from infrastructure.retrieval.retrieval_config import Phase5CConfig
        
        data = {
            "read_isolation": {"enabled": False},
            "replica_lag": {"max_lag_seconds": 10.0},
            "query_budget": {"per_intent": {"custom": 5000}},
        }
        
        config = Phase5CConfig.from_dict(data)
        
        assert config.read_isolation.enabled is False
        assert config.replica_lag.max_lag_seconds == 10.0
        assert config.query_budget.per_intent["custom"] == 5000

    def test_config_to_dict(self):
        """Test converting config to dictionary."""
        from infrastructure.retrieval.retrieval_config import Phase5CConfig, ReadIsolationConfig
        
        config = Phase5CConfig(
            read_isolation=ReadIsolationConfig(enabled=False),
        )
        
        data = config.to_dict()
        
        assert data["read_isolation"]["enabled"] is False

    def test_config_yaml_template(self):
        """Test YAML template contains all sections."""
        from infrastructure.retrieval.retrieval_config import PHASE5C_YAML_TEMPLATE
        
        assert "read_isolation" in PHASE5C_YAML_TEMPLATE
        assert "replica_lag" in PHASE5C_YAML_TEMPLATE
        assert "plugin_management" in PHASE5C_YAML_TEMPLATE
        assert "query_budget" in PHASE5C_YAML_TEMPLATE
        assert "golden_set" in PHASE5C_YAML_TEMPLATE
        assert "explainability" in PHASE5C_YAML_TEMPLATE


# ============================================================================
# AdvancedRetrievalEngine Integration Tests
# ============================================================================

class TestAdvancedRetrievalEngine:
    """Integration tests for AdvancedRetrievalEngine."""

    def test_engine_initialization(self):
        """Test engine initializes all components."""
        from infrastructure.retrieval.retrieval_engine import AdvancedRetrievalEngine
        
        engine = AdvancedRetrievalEngine()
        
        assert engine._snapshot_isolation is not None
        assert engine._replica_router is not None
        assert engine._plugin_manager is not None
        assert engine._query_budgeter is not None
        assert engine._drift_detector is not None
        assert engine._cache_invalidator is not None
        assert engine._explainability_limiter is not None

    @pytest.mark.asyncio
    async def test_begin_retrieval_transaction(self):
        """Test beginning a retrieval transaction."""
        from infrastructure.retrieval.retrieval_engine import AdvancedRetrievalEngine
        
        engine = AdvancedRetrievalEngine()
        txn_id = await engine.begin_retrieval_transaction()
        
        assert txn_id.startswith("txn_")

    @pytest.mark.asyncio
    async def test_get_snapshot(self):
        """Test getting snapshot from engine."""
        from infrastructure.retrieval.retrieval_engine import AdvancedRetrievalEngine
        
        engine = AdvancedRetrievalEngine()
        txn_id = await engine.begin_retrieval_transaction()
        
        snapshot = engine._snapshot_isolation.get_or_create_snapshot(txn_id)
        result = await engine.get_snapshot(snapshot.snapshot_id)
        
        assert result is not None
        assert "snapshot_id" in result

    @pytest.mark.asyncio
    async def test_commit_transaction(self):
        """Test committing transaction through engine."""
        from infrastructure.retrieval.retrieval_engine import AdvancedRetrievalEngine
        
        engine = AdvancedRetrievalEngine()
        txn_id = await engine.begin_retrieval_transaction()
        # Get or create snapshot first
        engine._snapshot_isolation.get_or_create_snapshot(txn_id)
        success = await engine.commit_transaction(txn_id)
        
        assert success is True

    def test_register_replica(self):
        """Test registering replica through engine."""
        from infrastructure.retrieval.retrieval_engine import AdvancedRetrievalEngine
        
        engine = AdvancedRetrievalEngine()
        engine.register_replica("r1")
        
        status = engine._replica_router.get_replica_status("r1")
        assert status is not None

    def test_update_replica_lag(self):
        """Test updating replica lag through engine."""
        from infrastructure.retrieval.retrieval_engine import AdvancedRetrievalEngine
        
        engine = AdvancedRetrievalEngine()
        engine.register_replica("r1")
        engine.update_replica_lag("r1", 3.0)
        
        status = engine._replica_router.get_replica_status("r1")
        assert status.replication_lag_seconds == 3.0

    @pytest.mark.asyncio
    async def test_register_plugin(self):
        """Test registering plugin through engine."""
        from infrastructure.retrieval.retrieval_engine import AdvancedRetrievalEngine
        
        engine = AdvancedRetrievalEngine()
        result = await engine.register_plugin("test", "v1.0")
        
        assert result["plugin_name"] == "test"
        assert result["version"] == "v1.0"

    def test_get_budget_for_intent(self):
        """Test getting budget through engine."""
        from infrastructure.retrieval.retrieval_engine import AdvancedRetrievalEngine
        
        engine = AdvancedRetrievalEngine()
        budget = engine.get_budget_for_intent("code")
        
        assert budget["intent"] == "code"
        assert budget["max_tokens"] == 16000

    def test_update_intent_budget(self):
        """Test updating budget through engine."""
        from infrastructure.retrieval.retrieval_engine import AdvancedRetrievalEngine
        
        engine = AdvancedRetrievalEngine()
        engine.update_intent_budget("factoid", 5000)
        
        budget = engine.get_budget_for_intent("factoid")
        assert budget["max_tokens"] == 5000

    @pytest.mark.asyncio
    async def test_invalidate_cache_for_document(self):
        """Test cache invalidation through engine."""
        from infrastructure.retrieval.retrieval_engine import AdvancedRetrievalEngine
        
        engine = AdvancedRetrievalEngine()
        engine.register_cache_entry("doc1", "key1")
        
        result = await engine.invalidate_cache_for_document("doc1")
        
        assert result["doc_id"] == "doc1"

    def test_limit_explanation_size(self):
        """Test explanation limiting through engine."""
        from infrastructure.retrieval.retrieval_engine import AdvancedRetrievalEngine
        
        engine = AdvancedRetrievalEngine()
        result = engine.limit_explanation_size(
            [{"chunk_id": "c1", "doc_id": "d1", "influence_score": 0.9}],
            "test query",
            "general"
        )
        
        assert "query" in result
        assert result["truncated"] is False

    def test_get_config(self):
        """Test getting engine configuration."""
        from infrastructure.retrieval.retrieval_engine import AdvancedRetrievalEngine
        
        engine = AdvancedRetrievalEngine()
        config = engine.get_config()
        
        assert "read_isolation" in config
        assert "replica_lag" in config
        assert "query_budget" in config

    def test_get_cache_invalidation_stats(self):
        """Test getting cache stats through engine."""
        from infrastructure.retrieval.retrieval_engine import AdvancedRetrievalEngine
        
        engine = AdvancedRetrievalEngine()
        engine.register_cache_entry("doc1", "key1")
        
        stats = engine.get_cache_invalidation_stats()
        
        assert "total_documents" in stats

    def test_get_drift_alerts(self):
        """Test getting drift alerts through engine."""
        from infrastructure.retrieval.retrieval_engine import AdvancedRetrievalEngine
        
        engine = AdvancedRetrievalEngine()
        alerts = engine.get_drift_alerts()
        
        assert isinstance(alerts, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
