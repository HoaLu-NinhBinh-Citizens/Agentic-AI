"""
Tests for Phase 5E Distributed Execution & Scaling Components.

Tests for:
- ShardedExactlyOnceLog
- ArchivableGlobalDLQ
- ReadOnlyCoordinatorFollower
- QuorumFailoverManager
- NetworkLoadReporter
- ResourceTimeoutHandler
- Snapshotter
- VersionedTaskClaim
- CrossRegionRetry
"""

import asyncio
import pytest
from datetime import datetime

from src.core.multi_agent.coordination.sharded_log import (
    ShardedExactlyOnceLog,
    ShardRouter,
)
from src.core.multi_agent.coordination.archivable_dlq import (
    ArchivableGlobalDLQ,
    DLQItem,
)
from src.core.multi_agent.coordination.readonly_follower import (
    ReadOnlyCoordinatorFollower,
    CoordinatorMode,
)
from src.core.multi_agent.coordination.quorum_failover import (
    QuorumFailoverManager,
    RegionState,
)
from src.core.multi_agent.coordination.network_load import (
    NetworkLoadReporter,
)
from src.core.multi_agent.coordination.resource_scheduling import (
    ResourceTimeoutHandler,
    ResourceRequirement,
    ResourceAvailability,
)
from src.core.multi_agent.coordination.snapshotter import (
    Snapshotter,
    Event,
)
from src.core.multi_agent.coordination.versioned_claim import (
    VersionedTaskClaim,
    ClaimStatus,
)
from src.core.multi_agent.coordination.cross_region_retry import (
    CrossRegionRetry,
)


# =============================================================================
# ShardedExactlyOnceLog Tests
# =============================================================================

class TestShardedLog:
    """Tests for ShardedExactlyOnceLog."""

    @pytest.mark.asyncio
    async def test_consistent_sharding(self):
        """Same key always routes to same shard."""
        router = ShardRouter(shard_count=16, shard_by="tenant_id")
        
        shard1 = router.get_shard("entry-1", "tenant-1", "task-1")
        shard2 = router.get_shard("entry-2", "tenant-1", "task-2")
        
        # Same tenant should route consistently
        assert router.get_shard("entry-3", "tenant-1", "task-3") == shard1
        assert router.get_shard("entry-4", "tenant-1", "task-4") == shard2

    @pytest.mark.asyncio
    async def test_exactly_once_write(self):
        """Duplicate writes are idempotent."""
        log = ShardedExactlyOnceLog(shard_count=8)
        
        entry = await log.write(
            entry_id="entry-1",
            task_id="task-1",
            tenant_id="tenant-1",
            payload={"data": "test"},
            idempotency_key="idempotent-key",
        )
        
        # Write again with same idempotency key
        entry2 = await log.write(
            entry_id="entry-2",
            task_id="task-1",
            tenant_id="tenant-1",
            payload={"data": "different"},
            idempotency_key="idempotent-key",
        )
        
        # Should return original entry
        assert entry.entry_id == entry2.entry_id
        assert entry2.payload["data"] == "test"

    @pytest.mark.asyncio
    async def test_read_range(self):
        """Can read entries by sequence range."""
        log = ShardedExactlyOnceLog(shard_count=4)
        
        # Write multiple entries
        for i in range(5):
            await log.write(
                entry_id=f"entry-{i}",
                task_id="task-1",
                tenant_id="tenant-1",
                payload={"index": i},
            )
        
        # Get shard for tenant
        shard = await log.get_shard_for("tenant-1", "task-1")
        
        # Read range
        entries = await log.read_range(shard, start_seq=1, limit=3)
        
        assert len(entries) == 3
        assert entries[0].sequence == 1
        assert entries[1].sequence == 2


# =============================================================================
# ArchivableGlobalDLQ Tests
# =============================================================================

class TestArchivableDLQ:
    """Tests for ArchivableGlobalDLQ."""

    @pytest.mark.asyncio
    async def test_add_item(self):
        """Can add items to DLQ."""
        dlq = ArchivableGlobalDLQ(max_items=100)
        
        item = await dlq.add(
            item_id="item-1",
            tenant_id="tenant-1",
            task_id="task-1",
            payload={"error": "test"},
            error="Timeout",
        )
        
        assert item.item_id == "item-1"
        assert item.storage_tier.value == "hot"

    @pytest.mark.asyncio
    async def test_search(self):
        """Can search DLQ items."""
        dlq = ArchivableGlobalDLQ()
        
        await dlq.add(
            item_id="item-1",
            tenant_id="tenant-1",
            task_id="task-1",
            payload={"command": "SELECT"},
            error="Database error",
        )
        
        results = await dlq.search("SELECT")
        
        assert len(results) == 1
        assert results[0].item_id == "item-1"

    @pytest.mark.asyncio
    async def test_archive(self):
        """Can archive DLQ items."""
        dlq = ArchivableGlobalDLQ()
        
        await dlq.add(
            item_id="item-1",
            tenant_id="tenant-1",
            task_id="task-1",
            payload={"data": "old"},
            error="Failed",
        )
        
        archive_id = await dlq.archive(force=True)
        
        assert archive_id is not None
        
        stats = await dlq.get_stats()
        assert stats["hot_items"] == 0


# =============================================================================
# ReadOnlyFollower Tests
# =============================================================================

class TestReadOnlyFollower:
    """Tests for ReadOnlyCoordinatorFollower."""

    @pytest.mark.asyncio
    async def test_follower_mode(self):
        """Follower reports correct mode."""
        follower = ReadOnlyCoordinatorFollower(
            follower_id="follower-1",
            leader_url="grpc://leader:50051",
        )
        
        assert follower.mode == CoordinatorMode.STANDBY
        
        await follower.connect()
        assert follower.mode == CoordinatorMode.FOLLOWER

    @pytest.mark.asyncio
    async def test_read_only_write_rejected(self):
        """Write operations are rejected on follower."""
        follower = ReadOnlyCoordinatorFollower(
            follower_id="follower-1",
        )
        await follower.connect()
        
        with pytest.raises(Exception):  # WriteModeError
            await follower.create_task({"task": "data"})


# =============================================================================
# QuorumFailover Tests
# =============================================================================

class TestQuorumFailover:
    """Tests for QuorumFailoverManager."""

    @pytest.mark.asyncio
    async def test_register_region(self):
        """Can register regions."""
        manager = QuorumFailoverManager(
            regions=["us-east", "eu-west", "ap-south"],
            quorum_size=2,
        )
        
        await manager.register_region("us-east", is_primary=True)
        await manager.register_region("eu-west")
        
        metrics = await manager.get_metrics()
        
        assert "us-east" in metrics["regions"]
        assert "eu-west" in metrics["regions"]

    @pytest.mark.asyncio
    async def test_become_active_requires_quorum(self):
        """Region needs quorum to become active."""
        manager = QuorumFailoverManager(
            regions=["us-east", "eu-west"],
            quorum_size=2,  # Need both regions
        )
        
        await manager.register_region("us-east")
        await manager.register_region("eu-west")
        
        # US-East tries to become active but only has 1 vote
        success = await manager.become_active("us-east")
        
        # Should fail (needs quorum)
        assert success is False

    @pytest.mark.asyncio
    async def test_fencing_token(self):
        """Fencing tokens are issued."""
        manager = QuorumFailoverManager(
            regions=["us-east", "eu-west"],
            quorum_size=1,
        )
        
        await manager.register_region("us-east")
        await manager.become_active("us-east")
        
        token = await manager.get_fencing_token("us-east")
        
        assert token is not None
        assert token.region_id == "us-east"


# =============================================================================
# NetworkLoadReporter Tests
# =============================================================================

class TestNetworkLoadReporter:
    """Tests for NetworkLoadReporter."""

    @pytest.mark.asyncio
    async def test_report_metrics(self):
        """Can report network metrics."""
        reporter = NetworkLoadReporter()
        
        profile = await reporter.report_metrics(
            worker_id="worker-1",
            rtt_ms=50.0,
            bandwidth_mbps=100.0,
            packet_loss_rate=0.01,
        )
        
        assert profile.worker_id == "worker-1"
        assert profile.avg_rtt_ms == 50.0
        assert profile.score < float('inf')

    @pytest.mark.asyncio
    async def test_get_best_worker(self):
        """Can find best worker by load."""
        reporter = NetworkLoadReporter()
        
        # Good worker
        await reporter.report_metrics(
            worker_id="worker-good",
            rtt_ms=10.0,
            bandwidth_mbps=1000.0,
            packet_loss_rate=0.0,
        )
        
        # Bad worker
        await reporter.report_metrics(
            worker_id="worker-bad",
            rtt_ms=500.0,
            bandwidth_mbps=10.0,
            packet_loss_rate=0.1,
        )
        
        best = await reporter.get_best_worker(["worker-good", "worker-bad"])
        
        assert best == "worker-good"


# =============================================================================
# ResourceTimeoutHandler Tests
# =============================================================================

class TestResourceTimeoutHandler:
    """Tests for ResourceTimeoutHandler."""

    @pytest.mark.asyncio
    async def test_submit_task(self):
        """Can submit task for scheduling."""
        handler = ResourceTimeoutHandler(default_timeout_seconds=30.0)
        
        # Register worker
        await handler.register_worker(
            worker_id="worker-1",
            resources=ResourceAvailability(
                worker_id="worker-1",
                cpu_cores=4,
                memory_mb=8192,
                gpu_count=0,
                disk_mb=100000,
            ),
        )
        
        result = await handler.submit_task(
            task_id="task-1",
            requirements=ResourceRequirement(
                cpu_cores=1,
                memory_mb=512,
            ),
        )
        
        assert result.success is True
        assert result.worker_id == "worker-1"

    @pytest.mark.asyncio
    async def test_complete_task(self):
        """Can complete scheduled task."""
        handler = ResourceTimeoutHandler()
        
        await handler.register_worker(
            worker_id="worker-1",
            resources=ResourceAvailability(
                worker_id="worker-1",
                cpu_cores=4,
                memory_mb=8192,
                gpu_count=0,
                disk_mb=100000,
            ),
        )
        
        await handler.submit_task(
            task_id="task-1",
            requirements=ResourceRequirement(cpu_cores=1),
        )
        
        await handler.complete_task("task-1")
        
        metrics = await handler.get_metrics()
        assert metrics["running_tasks"] == 0


# =============================================================================
# Snapshotter Tests
# =============================================================================

class TestSnapshotter:
    """Tests for Snapshotter."""

    @pytest.mark.asyncio
    async def test_record_event(self):
        """Can record events."""
        snapshotter = Snapshotter(snapshot_interval=10)
        
        event = await snapshotter.record_event(
            aggregate_id="task-1",
            event_type="task_created",
            payload={"task_id": "task-1"},
        )
        
        assert event.event_type == "task_created"
        assert event.sequence == 1

    @pytest.mark.asyncio
    async def test_snapshot_interval(self):
        """Creates snapshot at interval."""
        snapshotter = Snapshotter(snapshot_interval=3)
        
        # Record events
        for i in range(5):
            await snapshotter.record_event(
                aggregate_id="task-1",
                event_type="task_updated",
                payload={"index": i},
            )
        
        info = await snapshotter.get_snapshot_info("task-1")
        
        assert info["has_snapshot"] is True
        assert info["snapshot_sequence"] == 3  # First snapshot at seq 3


# =============================================================================
# VersionedTaskClaim Tests
# =============================================================================

class TestVersionedTaskClaim:
    """Tests for VersionedTaskClaim."""

    @pytest.mark.asyncio
    async def test_claim_task(self):
        """Can claim a task."""
        claimer = VersionedTaskClaim(claim_ttl_seconds=60)
        
        result = await claimer.claim("task-1", "worker-1")
        
        assert result.success is True
        assert result.version == 1
        assert result.claim.worker_id == "worker-1"

    @pytest.mark.asyncio
    async def test_version_conflict(self):
        """Detects version conflicts."""
        claimer = VersionedTaskClaim()
        
        # Worker 1 claims task
        result1 = await claimer.claim("task-1", "worker-1")
        assert result1.success is True
        
        # Worker 2 tries with old version
        result2 = await claimer.claim("task-1", "worker-2", expected_version=0)
        
        assert result2.success is False
        assert result2.reason == "VERSION_MISMATCH"

    @pytest.mark.asyncio
    async def test_complete_task(self):
        """Can complete claimed task."""
        claimer = VersionedTaskClaim()
        
        # Claim
        result = await claimer.claim("task-1", "worker-1")
        version = result.version
        
        # Complete
        complete = await claimer.complete("task-1", "worker-1", version)
        
        assert complete.success is True
        assert complete.reason == "COMPLETED"


# =============================================================================
# CrossRegionRetry Tests
# =============================================================================

class TestCrossRegionRetry:
    """Tests for CrossRegionRetry."""

    @pytest.mark.asyncio
    async def test_register_region(self):
        """Can register regions."""
        retry = CrossRegionRetry(max_attempts=3)
        
        retry.register_region("us-east", "https://us-east.example.com")
        retry.register_region("eu-west", "https://eu-west.example.com")
        
        metrics = await retry.get_metrics()
        
        assert "us-east" in metrics["regions"]
        assert "eu-west" in metrics["regions"]

    @pytest.mark.asyncio
    async def test_region_dlq(self):
        """Tasks fail to region DLQ."""
        retry = CrossRegionRetry(max_attempts=2)
        
        retry.register_region("us-east", "https://us-east.example.com")
        
        # Mock submit handler that always fails
        async def failing_handler(region, payload):
            raise ConnectionError("Region unreachable")
        
        result = await retry.submit_cross_region(
            task_id="task-1",
            source_region="eu-west",
            target_region="us-east",
            payload={"data": "test"},
            submit_handler=failing_handler,
        )
        
        assert result.success is False
        assert result.attempts_used == 2
        
        status = await retry.get_region_dlq_status("us-east")
        assert status["item_count"] == 1

    @pytest.mark.asyncio
    async def test_replay_region_dlq(self):
        """Can replay region DLQ."""
        retry = CrossRegionRetry(max_attempts=1)
        
        retry.register_region("us-east", "https://us-east.example.com")
        
        # Mock failing handler
        async def fail_once(region, payload):
            raise ConnectionError("Failed")
        
        await retry.submit_cross_region(
            task_id="task-replay",
            source_region="eu-west",
            target_region="us-east",
            payload={"data": "replay-test"},
            submit_handler=fail_once,
        )
        
        # Count before replay
        status1 = await retry.get_region_dlq_status("us-east")
        count_before = status1["item_count"]
        
        # Mock successful replay
        async def success_handler(region, payload):
            pass
        
        replayed = await retry.replay_region_dlq(
            "us-east",
            replay_handler=success_handler,
        )
        
        assert replayed == count_before


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
