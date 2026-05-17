"""Retrieval Engine Resilience Tests.

Tests for production-grade features:
1. SnapshotReferenceCounter & SnapshotGCManager
2. VectorSnapshotConsistencyManager
3. GenerationCacheInvalidator
4. DistributionShiftDetector
5. RetrievalAdmissionController
6. CatastrophicRecoveryManager
7. PluginStateMigrationManager
8. LSNBasedLagMetrics
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


# ============================================================================
# 1. Snapshot Reference Counter & GC Manager Tests
# ============================================================================

class TestSnapshotReferenceCounter:
    """Tests for snapshot reference counting."""

    @pytest.mark.asyncio
    async def test_acquire_reference(self):
        """Test acquiring snapshot reference."""
        from infrastructure.retrieval.retrieval_resilience import SnapshotReferenceCounter
        
        counter = SnapshotReferenceCounter()
        count = await counter.acquire("snap1")
        
        assert count == 1
        assert counter.get_ref_count("snap1") == 1

    @pytest.mark.asyncio
    async def test_release_reference(self):
        """Test releasing snapshot reference."""
        from infrastructure.retrieval.retrieval_resilience import SnapshotReferenceCounter
        
        counter = SnapshotReferenceCounter()
        await counter.acquire("snap1")
        await counter.acquire("snap1")
        count = await counter.release("snap1")
        
        assert count == 1

    @pytest.mark.asyncio
    async def test_multiple_references(self):
        """Test multiple reference acquisition."""
        from infrastructure.retrieval.retrieval_resilience import SnapshotReferenceCounter
        
        counter = SnapshotReferenceCounter()
        await counter.acquire("snap1")
        await counter.acquire("snap1")
        await counter.acquire("snap1")
        
        assert counter.get_ref_count("snap1") == 3
        assert counter.is_referenced("snap1") is True

    def test_is_referenced(self):
        """Test checking if snapshot is referenced."""
        from infrastructure.retrieval.retrieval_resilience import SnapshotReferenceCounter
        
        counter = SnapshotReferenceCounter()
        
        assert counter.is_referenced("snap1") is False
        
        import asyncio
        asyncio.get_event_loop().run_until_complete(counter.acquire("snap1"))
        
        assert counter.is_referenced("snap1") is True


class TestSnapshotGCManager:
    """Tests for snapshot GC management."""

    def test_register_snapshot(self):
        """Test registering a snapshot."""
        from infrastructure.retrieval.retrieval_resilience import SnapshotGCManager
        
        gc = SnapshotGCManager()
        gc.register_snapshot("snap1", {"size_bytes": 1000})
        
        stats = gc.get_stats()
        assert stats["total_snapshots"] == 1

    @pytest.mark.asyncio
    async def test_acquire_release_reference(self):
        """Test reference acquire/release through GC manager."""
        from infrastructure.retrieval.retrieval_resilience import SnapshotGCManager
        
        gc = SnapshotGCManager()
        gc.register_snapshot("snap1")
        
        count = await gc.acquire_reference("snap1")
        assert count == 1
        
        count = await gc.release_reference("snap1")
        assert count == 0

    def test_get_safe_to_gc(self):
        """Test getting snapshots safe for GC."""
        from infrastructure.retrieval.retrieval_resilience import SnapshotGCManager
        import time
        
        gc = SnapshotGCManager(max_snapshot_age_seconds=1)
        gc.register_snapshot("snap1")
        
        time.sleep(2)
        
        safe = gc.get_safe_to_gc()
        assert "snap1" in safe

    def test_max_snapshots_limit(self):
        """Test max snapshots limit triggers GC."""
        from infrastructure.retrieval.retrieval_resilience import SnapshotGCManager
        
        gc = SnapshotGCManager(max_snapshots=2)
        
        for i in range(5):
            gc.register_snapshot(f"snap{i}")
        
        safe = gc.get_safe_to_gc()
        assert len(safe) >= 3

    def test_touch_snapshot(self):
        """Test touching snapshot updates last accessed."""
        from infrastructure.retrieval.retrieval_resilience import SnapshotGCManager
        
        gc = SnapshotGCManager()
        gc.register_snapshot("snap1")
        
        gc.touch_snapshot("snap1")
        
        stats = gc.get_stats()
        assert stats["total_snapshots"] == 1


# ============================================================================
# 2. Vector Snapshot Consistency Manager Tests
# ============================================================================

class TestVectorSnapshotConsistencyManager:
    """Tests for vector consistency management."""

    def test_create_segment(self):
        """Test creating immutable segment."""
        from infrastructure.retrieval.retrieval_resilience import VectorSnapshotConsistencyManager
        
        manager = VectorSnapshotConsistencyManager()
        segment = manager.create_segment(["doc1", "doc2"])
        
        assert segment.segment_id.startswith("seg_")
        assert segment.version == 1
        assert segment.doc_ids == ["doc1", "doc2"]
        assert segment.is_immutable is True

    def test_pin_segment(self):
        """Test pinning segment."""
        from infrastructure.retrieval.retrieval_resilience import VectorSnapshotConsistencyManager
        
        manager = VectorSnapshotConsistencyManager()
        segment = manager.create_segment(["doc1"])
        
        manager.pin_segment(segment.segment_id)
        
        assert manager.is_segment_safe_to_compact(segment.segment_id) is False

    def test_unpin_segment(self):
        """Test unpinning segment."""
        from infrastructure.retrieval.retrieval_resilience import VectorSnapshotConsistencyManager
        
        manager = VectorSnapshotConsistencyManager()
        segment = manager.create_segment(["doc1"])
        
        manager.pin_segment(segment.segment_id)
        manager.unpin_segment(segment.segment_id)
        
        assert manager.is_segment_safe_to_compact(segment.segment_id) is True

    def test_get_segments_for_snapshot(self):
        """Test getting segments for version."""
        from infrastructure.retrieval.retrieval_resilience import VectorSnapshotConsistencyManager
        
        manager = VectorSnapshotConsistencyManager()
        manager.create_segment(["doc1"])
        manager.create_segment(["doc2"])
        manager.create_segment(["doc3"])
        
        segments = manager.get_segments_for_snapshot(2)
        assert len(segments) == 2

    @pytest.mark.asyncio
    async def test_compact_old_segments(self):
        """Test compacting old segments."""
        from infrastructure.retrieval.retrieval_resilience import VectorSnapshotConsistencyManager
        
        manager = VectorSnapshotConsistencyManager()
        
        for i in range(5):
            manager.create_segment([f"doc{i}"])
        
        deleted = await manager.compact_old_segments(max_versions_to_keep=2)
        
        assert len(deleted) >= 2

    def test_get_stats(self):
        """Test getting manager stats."""
        from infrastructure.retrieval.retrieval_resilience import VectorSnapshotConsistencyManager
        
        manager = VectorSnapshotConsistencyManager()
        manager.create_segment(["doc1"])
        
        stats = manager.get_stats()
        assert stats["total_segments"] == 1
        assert stats["strategy"] == "versioned_segments"


# ============================================================================
# 3. Generation Cache Invalidation Tests
# ============================================================================

class TestGenerationCacheInvalidator:
    """Tests for generation-based cache invalidation."""

    @pytest.mark.asyncio
    async def test_on_document_updated(self):
        """Test recording document update."""
        from infrastructure.retrieval.retrieval_resilience import GenerationCacheInvalidator
        
        inv = GenerationCacheInvalidator()
        gen = await inv.on_document_updated("doc1")
        
        assert gen >= 1

    def test_register_cache_entry(self):
        """Test registering cache entry."""
        from infrastructure.retrieval.retrieval_resilience import GenerationCacheInvalidator
        
        inv = GenerationCacheInvalidator()
        gen = inv.register_cache_entry("cache_key_1")
        
        assert gen == 0

    def test_is_cache_valid(self):
        """Test checking cache validity."""
        from infrastructure.retrieval.retrieval_resilience import GenerationCacheInvalidator
        
        inv = GenerationCacheInvalidator()
        inv.register_cache_entry("cache_key_1")
        
        is_valid, reason = inv.is_cache_valid("cache_key_1")
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_invalidation_after_update(self):
        """Test cache invalidation after document update."""
        from infrastructure.retrieval.retrieval_resilience import GenerationCacheInvalidator
        
        inv = GenerationCacheInvalidator()
        inv.register_cache_entry("cache_key_1")
        
        await inv.on_document_updated("doc1")
        
        is_valid, reason = inv.is_cache_valid("cache_key_1")
        assert is_valid is False
        assert "stale" in reason

    def test_get_invalidation_batch(self):
        """Test getting invalidation batch."""
        from infrastructure.retrieval.retrieval_resilience import GenerationCacheInvalidator
        
        inv = GenerationCacheInvalidator()
        inv.register_cache_entry("key1")
        inv.register_cache_entry("key2")
        
        # After document update, entries should be stale
        import asyncio
        asyncio.get_event_loop().run_until_complete(inv.on_document_updated("any_doc"))
        
        batch = inv.get_invalidation_batch()
        
        assert len(batch) >= 2

    def test_get_stats(self):
        """Test getting invalidator stats."""
        from infrastructure.retrieval.retrieval_resilience import GenerationCacheInvalidator
        
        inv = GenerationCacheInvalidator()
        inv.register_cache_entry("key1")
        
        stats = inv.get_stats()
        assert "current_generation" in stats
        assert "total_cache_entries" in stats


# ============================================================================
# 4. Distribution Shift Detector Tests
# ============================================================================

class TestDistributionShiftDetector:
    """Tests for query distribution monitoring."""

    def test_record_query(self):
        """Test recording query."""
        from infrastructure.retrieval.retrieval_resilience import DistributionShiftDetector
        
        detector = DistributionShiftDetector()
        detector.record_query("code", "How to configure UART?")
        
        stats = detector.get_stats()
        assert stats["total_queries"] == 1

    def test_set_baseline(self):
        """Test setting baseline distribution."""
        from infrastructure.retrieval.retrieval_resilience import DistributionShiftDetector
        
        detector = DistributionShiftDetector()
        detector.record_query("code", "query1")
        detector.record_query("code", "query2")
        detector.set_baseline()
        
        stats = detector.get_stats()
        assert stats["has_baseline"] is True

    def test_compute_kl_divergence(self):
        """Test computing KL divergence."""
        from infrastructure.retrieval.retrieval_resilience import DistributionShiftDetector
        
        detector = DistributionShiftDetector()
        detector.record_query("code", "q1")
        detector.set_baseline()
        detector.record_query("code", "q2")
        detector.record_query("code", "q3")
        
        kl = detector.compute_kl_divergence()
        assert kl >= 0

    def test_detect_drift(self):
        """Test drift detection."""
        from infrastructure.retrieval.retrieval_resilience import DistributionShiftDetector
        
        detector = DistributionShiftDetector(drift_threshold=10.0)
        detector.record_query("code", "q1")
        detector.record_query("reasoning", "q2")
        detector.set_baseline()
        
        for _ in range(10):
            detector.record_query("instruction", "q")
        
        drift_detected, details = detector.detect_drift()
        
        assert "kl_divergence" in details

    def test_get_alerts(self):
        """Test getting drift alerts."""
        from infrastructure.retrieval.retrieval_resilience import DistributionShiftDetector
        
        detector = DistributionShiftDetector()
        detector.set_baseline()
        
        alerts = detector.get_alerts()
        assert len(alerts) > 0


# ============================================================================
# 5. Retrieval Admission Controller Tests
# ============================================================================

class TestRetrievalAdmissionController:
    """Tests for admission control."""

    def test_get_load_factor(self):
        """Test getting load factor."""
        from infrastructure.retrieval.retrieval_resilience import RetrievalAdmissionController
        
        controller = RetrievalAdmissionController(max_queue_depth=100)
        controller._queue_depth = 50
        
        load = controller.get_load_factor()
        
        assert load == 0.5

    def test_is_overloaded(self):
        """Test overload detection."""
        from infrastructure.retrieval.retrieval_resilience import RetrievalAdmissionController
        
        controller = RetrievalAdmissionController(max_queue_depth=100, high_water_mark=0.8)
        controller._queue_depth = 85
        
        assert controller.is_overloaded() is True

    def test_is_degraded(self):
        """Test degraded mode detection."""
        from infrastructure.retrieval.retrieval_resilience import RetrievalAdmissionController
        
        controller = RetrievalAdmissionController(
            max_queue_depth=100,
            low_water_mark=0.5,
            high_water_mark=0.8,
        )
        controller._queue_depth = 60
        
        assert controller.is_degraded() is True

    @pytest.mark.asyncio
    async def test_admit_normal_priority(self):
        """Test admitting normal priority request."""
        from infrastructure.retrieval.retrieval_resilience import RetrievalAdmissionController
        
        controller = RetrievalAdmissionController(max_queue_depth=100)
        decision = await controller.check_admission("normal", "req1")
        
        assert decision.admitted is True

    @pytest.mark.asyncio
    async def test_reject_low_priority_under_load(self):
        """Test rejecting low priority under load."""
        from infrastructure.retrieval.retrieval_resilience import RetrievalAdmissionController, LoadSheddingPolicy
        
        controller = RetrievalAdmissionController(
            max_queue_depth=100,
            policy=LoadSheddingPolicy.REJECT_LOW_PRIORITY,
        )
        controller._queue_depth = 90
        
        decision = await controller.check_admission("low", "req1")
        
        assert decision.admitted is False

    @pytest.mark.asyncio
    async def test_release_slot(self):
        """Test releasing queue slot."""
        from infrastructure.retrieval.retrieval_resilience import RetrievalAdmissionController
        
        controller = RetrievalAdmissionController()
        await controller.check_admission("normal", "req1")
        await controller.release_slot("req1")
        
        assert controller._queue_depth == 0

    def test_get_stats(self):
        """Test getting controller stats."""
        from infrastructure.retrieval.retrieval_resilience import RetrievalAdmissionController
        
        controller = RetrievalAdmissionController()
        
        stats = controller.get_stats()
        assert "queue_depth" in stats
        assert "is_overloaded" in stats


# ============================================================================
# 6. Catastrophic Recovery Manager Tests
# ============================================================================

class TestCatastrophicRecoveryManager:
    """Tests for catastrophic recovery."""

    def test_record_wal_entry(self):
        """Test recording WAL entry."""
        from infrastructure.retrieval.retrieval_resilience import CatastrophicRecoveryManager
        
        manager = CatastrophicRecoveryManager(wal_enabled=True)
        manager.record_wal_entry({"operation": "index", "doc_id": "doc1"})
        
        assert len(manager._wal_entries) == 1

    @pytest.mark.asyncio
    async def test_analyze_failure(self):
        """Test analyzing failure scope."""
        from infrastructure.retrieval.retrieval_resilience import CatastrophicRecoveryManager
        
        manager = CatastrophicRecoveryManager()
        scope = await manager.analyze_failure({
            "index_corruption": True,
        })
        
        assert "vector_index" in scope.affected_components

    @pytest.mark.asyncio
    async def test_create_recovery_plan(self):
        """Test creating recovery plan."""
        from infrastructure.retrieval.retrieval_resilience import CatastrophicRecoveryManager, FailureScope
        
        manager = CatastrophicRecoveryManager()
        scope = FailureScope(
            affected_components=["vector_index"],
            affected_shards=[],
            estimated_data_loss=0.2,
            detected_at=0,
        )
        
        plan = await manager.create_recovery_plan(scope)
        
        assert plan.strategy is not None
        assert len(plan.steps) > 0

    @pytest.mark.asyncio
    async def test_execute_recovery(self):
        """Test executing recovery plan."""
        from infrastructure.retrieval.retrieval_resilience import CatastrophicRecoveryManager, RecoveryPlan, RecoveryStrategy
        
        manager = CatastrophicRecoveryManager()
        plan = RecoveryPlan(
            strategy=RecoveryStrategy.PARTIAL_SHARD_ISOLATION,
            estimated_duration_seconds=60,
            risk_level="low",
            steps=["Step 1", "Step 2"],
            prerequisites=[],
        )
        
        result = await manager.execute_recovery(plan)
        
        assert result["success"] is True
        assert len(result["steps_completed"]) == 2

    def test_get_recovery_history(self):
        """Test getting recovery history."""
        from infrastructure.retrieval.retrieval_resilience import CatastrophicRecoveryManager, RecoveryPlan, RecoveryStrategy
        
        manager = CatastrophicRecoveryManager()
        plan = RecoveryPlan(
            strategy=RecoveryStrategy.READONLY_MODE,
            estimated_duration_seconds=10,
            risk_level="low",
            steps=["Switch to readonly"],
            prerequisites=[],
        )
        
        import asyncio
        asyncio.get_event_loop().run_until_complete(manager.execute_recovery(plan))
        
        history = manager.get_recovery_history()
        assert len(history) == 1


# ============================================================================
# 7. Plugin State Migration Manager Tests
# ============================================================================

class TestPluginStateMigrationManager:
    """Tests for plugin state migration."""

    @pytest.mark.asyncio
    async def test_snapshot_plugin_state(self):
        """Test creating plugin state snapshot."""
        from infrastructure.retrieval.retrieval_resilience import PluginStateMigrationManager
        
        manager = PluginStateMigrationManager()
        snapshot = await manager.snapshot_plugin_state(
            "reranker",
            "v1.0",
            {"cache_size": 100},
            ["schema_v1"],
        )
        
        assert snapshot.plugin_name == "reranker"
        assert snapshot.version == "v1.0"

    def test_get_latest_snapshot(self):
        """Test getting latest snapshot."""
        from infrastructure.retrieval.retrieval_resilience import PluginStateMigrationManager
        
        manager = PluginStateMigrationManager()
        
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            manager.snapshot_plugin_state("plugin", "v1.0", {})
        )
        asyncio.get_event_loop().run_until_complete(
            manager.snapshot_plugin_state("plugin", "v2.0", {})
        )
        
        latest = manager.get_latest_snapshot("plugin")
        assert latest.version == "v2.0"

    def test_register_compatibility(self):
        """Test registering compatibility."""
        from infrastructure.retrieval.retrieval_resilience import PluginStateMigrationManager
        
        manager = PluginStateMigrationManager()
        manager.register_compatibility("plugin", "v1.0", "v2.0", True)
        
        compat = manager.get_compatibility("plugin", "v1.0", "v2.0")
        assert compat.compatible is True

    @pytest.mark.asyncio
    async def test_migrate_state(self):
        """Test migrating plugin state."""
        from infrastructure.retrieval.retrieval_resilience import PluginStateMigrationManager
        
        manager = PluginStateMigrationManager()
        manager.register_compatibility("plugin", "v1.0", "v2.0", True)
        
        success, state = await manager.migrate_state(
            "plugin", "v1.0", "v2.0", {"key": "value"}
        )
        
        assert success is True
        assert state["key"] == "value"

    def test_get_stats(self):
        """Test getting migration stats."""
        from infrastructure.retrieval.retrieval_resilience import PluginStateMigrationManager
        
        manager = PluginStateMigrationManager()
        
        stats = manager.get_stats()
        assert "total_plugins" in stats


# ============================================================================
# 8. LSN-Based Lag Metrics Tests
# ============================================================================

class TestLSNBasedLagMetrics:
    """Tests for LSN-based lag metrics."""

    def test_update_replica_lsn(self):
        """Test updating replica LSN."""
        from infrastructure.retrieval.retrieval_resilience import LSNBasedLagMetrics
        
        metrics = LSNBasedLagMetrics()
        metrics.update_replica_lsn("replica1", current_lsn=1000, flushed_lsn=950)
        
        state = metrics.get_lag_metrics("replica1")
        assert state["current_lsn"] == 1000
        assert state["lsn_lag"] == 50

    def test_update_vector_epoch(self):
        """Test updating vector epoch."""
        from infrastructure.retrieval.retrieval_resilience import LSNBasedLagMetrics
        
        metrics = LSNBasedLagMetrics()
        metrics.update_replica_lsn("r1", 100, 90)
        metrics.update_vector_epoch("r1", 5)
        
        state = metrics.get_lag_metrics("r1")
        assert state["vector_epoch"] == 5

    def test_update_index_freshness(self):
        """Test updating index freshness."""
        from infrastructure.retrieval.retrieval_resilience import LSNBasedLagMetrics
        
        metrics = LSNBasedLagMetrics()
        metrics.update_replica_lsn("r1", 100, 90)
        metrics.update_index_freshness("r1", docs_indexed=950, docs_total=1000)
        
        state = metrics.get_lag_metrics("r1")
        assert state["freshness_ratio"] == 0.95

    def test_is_replica_stale(self):
        """Test checking if replica is stale."""
        from infrastructure.retrieval.retrieval_resilience import LSNBasedLagMetrics
        
        metrics = LSNBasedLagMetrics(max_lag_threshold=100)
        metrics.update_replica_lsn("r1", current_lsn=200, flushed_lsn=50)
        
        is_stale, reason = metrics.is_replica_stale("r1")
        
        assert is_stale is True

    def test_is_replica_healthy(self):
        """Test checking healthy replica."""
        from infrastructure.retrieval.retrieval_resilience import LSNBasedLagMetrics
        
        metrics = LSNBasedLagMetrics(max_lag_threshold=100)
        metrics.update_replica_lsn("r1", current_lsn=100, flushed_lsn=95)
        metrics.update_index_freshness("r1", 100, 100)
        
        is_stale, reason = metrics.is_replica_stale("r1")
        
        assert is_stale is False

    def test_get_all_replica_metrics(self):
        """Test getting all replica metrics."""
        from infrastructure.retrieval.retrieval_resilience import LSNBasedLagMetrics
        
        metrics = LSNBasedLagMetrics()
        metrics.update_replica_lsn("r1", 100, 90)
        metrics.update_replica_lsn("r2", 100, 95)
        
        all_metrics = metrics.get_all_replica_metrics()
        
        assert len(all_metrics) == 2

    def test_get_stats(self):
        """Test getting LSN metrics stats."""
        from infrastructure.retrieval.retrieval_resilience import LSNBasedLagMetrics
        
        metrics = LSNBasedLagMetrics()
        metrics.update_replica_lsn("r1", 100, 90)
        metrics.update_replica_lsn("r2", 100, 95)
        
        stats = metrics.get_stats()
        
        assert "total_replicas" in stats
        assert stats["total_replicas"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
