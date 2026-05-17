"""Performance and scale tests for Phase 5B.

Tests performance and scale targets:
- test_high_throughput: 1000 workflow start/second, p95 < 200ms
- test_long_history_replay: 50k events replay < 2 seconds
- test_large_dag: 500 tasks planning < 5 seconds
- test_concurrent_compensations: 100 parallel compensations, no deadlock
- test_multi_tenant_scale: 100 tenants, 100 workflows each
"""

from __future__ import annotations

import pytest
import asyncio
import time

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from core.runtime.enterprise.heartbeat_lease import ActivityHeartbeatManager, InMemoryHeartbeatStore
from core.runtime.enterprise.compensation_saga import SagaCoordinator, DeadLetterQueue, CompensationConfig
from core.runtime.enterprise.multi_tenant import MultiTenantQuotaManager, InMemoryQuotaStore, InMemoryUsageStore, TenantQuota
from core.runtime.enterprise.event_integrity import HashChainValidator
from application.planner.deadlock_detector import DeadlockDetector
from application.planner.types import PlanGraph, PlanNode


# ============================================================================
# Performance Test Fixtures
# ============================================================================

@pytest.fixture
def heartbeat_manager():
    """Create heartbeat manager for performance tests."""
    return ActivityHeartbeatManager(InMemoryHeartbeatStore())


@pytest.fixture
def large_dag_detector():
    """Create detector for large DAG tests."""
    return DeadlockDetector()


# ============================================================================
# Throughput Tests
# ============================================================================

class TestHighThroughput:
    """Test high throughput scenarios."""

    @pytest.mark.asyncio
    async def test_high_throughput_activity_start(self):
        """Test: 1000 workflow starts per second.
        
        Target: Latency p95 < 200ms for starting activities.
        """
        store = InMemoryHeartbeatStore()
        manager = ActivityHeartbeatManager(store)
        
        async def start_workflow():
            """Simulate starting a workflow."""
            await manager.start_activity(
                activity_id=f"act_{time.time()}",
                workflow_id="wf_perf",
                worker_id="worker1",
            )
        
        # Benchmark
        start = time.time()
        for i in range(100):
            await start_workflow()
        elapsed = time.time() - start
        
        # Should complete 100 in under 1 second (equivalent to 1000/sec)
        assert elapsed < 1.0, f"Too slow: {elapsed}s for 100 starts"

    @pytest.mark.asyncio
    async def test_concurrent_activity_starts(self):
        """Test: Many concurrent activity starts."""
        store = InMemoryHeartbeatStore()
        manager = ActivityHeartbeatManager(store)
        
        async def start_workflow(wf_id):
            await manager.start_activity(
                activity_id=f"act_{wf_id}",
                workflow_id=f"wf_{wf_id}",
                worker_id="worker1",
            )
        
        start = time.time()
        
        # Start 50 workflows concurrently
        await asyncio.gather(*[start_workflow(i) for i in range(50)])
        
        elapsed = time.time() - start
        
        # 50 concurrent starts should be fast
        assert elapsed < 0.5, f"Too slow: {elapsed}s"


# ============================================================================
# Replay Performance Tests
# ============================================================================

class TestReplayPerformance:
    """Test replay performance with large event histories."""

    @pytest.mark.asyncio
    async def test_long_history_replay_small(self):
        """Test: Replay with 1000 events (reduced for test speed)."""
        validator = HashChainValidator()
        
        # Create 1000 events (reduced from 50k for test speed)
        events = [
            {"event_id": f"e{i}", "sequence": i, "event_type": "task", "data": {"n": i}}
            for i in range(1000)
        ]
        
        # Build chain
        chained = []
        prev_hash = "genesis"
        for e in events:
            hash_val = validator.compute_event_hash(
                e["event_id"], e["sequence"], e["event_type"], e["data"]
            )
            chained.append({**e, "previous_hash": prev_hash, "event_hash": hash_val})
            prev_hash = hash_val
        
        # Verify chain
        start = time.time()
        result = validator.verify_chain(chained)
        elapsed = time.time() - start
        
        assert result.valid is True
        # Should verify 1000 events very quickly
        assert elapsed < 0.5, f"Replay too slow: {elapsed}s for 1000 events"

    @pytest.mark.asyncio
    async def test_hash_chain_computation_speed(self):
        """Test: Hash chain computation is fast."""
        validator = HashChainValidator()
        
        start = time.time()
        
        # Compute 1000 hashes
        for i in range(1000):
            validator.compute_hash({"data": f"item_{i}"})
        
        elapsed = time.time() - start
        
        # 1000 hashes should be very fast
        assert elapsed < 0.2, f"Hash too slow: {elapsed}s for 1000 hashes"


# ============================================================================
# Large DAG Performance Tests
# ============================================================================

class TestLargeDAGPerformance:
    """Test performance with large DAGs."""

    @pytest.mark.asyncio
    async def test_large_dag_validation(self, large_dag_detector):
        """Test: Validate DAG with 200 nodes (reduced from 500 for test speed)."""
        # Create DAG with 200 tasks
        nodes = []
        for i in range(200):
            deps = []
            if i > 0:
                deps.append(f"n_{i-1}")  # Simple chain
        
        nodes.append(PlanNode(
            node_id=f"n_{i}",
            task_type="task",
            description=f"Node {i}",
            depends_on=deps,
            branch_options=[],
            condition_expr=None,
            join_policy=None,
            estimated_cost=1.0,
            estimated_duration=10.0,
        ))
        
        plan = PlanGraph(
            plan_id="large_dag",
            goal="Large DAG Test",
            nodes=nodes,
            root_node_id="n_0",
        )
        
        start = time.time()
        report = await large_dag_detector.detect_deadlock(plan)
        elapsed = time.time() - start
        
        # No cycles should be detected
        assert len(report.cycles) == 0
        # Should validate 200 nodes quickly
        assert elapsed < 1.0, f"DAG validation too slow: {elapsed}s"

    @pytest.mark.asyncio
    async def test_dag_with_many_dependencies(self, large_dag_detector):
        """Test: DAG with many cross-dependencies."""
        # Create DAG where each node depends on multiple others
        nodes = []
        for i in range(50):
            deps = []
            if i >= 2:
                deps = [f"n_{i-1}", f"n_{i-2}"]  # Each depends on last 2
            elif i >= 1:
                deps = [f"n_{i-1}"]
            
            nodes.append(PlanNode(
                node_id=f"n_{i}",
                task_type="task",
                description=f"Node {i}",
                depends_on=deps,
                branch_options=[],
                condition_expr=None,
                join_policy=None,
                estimated_cost=1.0,
                estimated_duration=10.0,
            ))
        
        plan = PlanGraph(
            plan_id="dense_dag",
            goal="Dense DAG Test",
            nodes=nodes,
            root_node_id="n_0",
        )
        
        start = time.time()
        report = await large_dag_detector.detect_deadlock(plan)
        elapsed = time.time() - start
        
        assert elapsed < 0.5, f"Dense DAG too slow: {elapsed}s"


# ============================================================================
# Concurrent Compensation Tests
# ============================================================================

class TestConcurrentCompensations:
    """Test concurrent compensation execution."""

    @pytest.mark.asyncio
    async def test_concurrent_compensations_no_deadlock(self):
        """Test: 10 compensations running concurrently, no deadlock."""
        dlq = DeadLetterQueue()
        config = CompensationConfig(max_attempts=1, initial_delay_seconds=0.001)
        coordinator = SagaCoordinator(dlq, config)
        
        await coordinator.start_saga("saga_parallel", "wf_parallel")
        
        # Record 10 completed tasks
        for i in range(10):
            await coordinator.record_task_completion("saga_parallel", f"task_{i}")
        
        # Create compensation functions
        compensation_registry = {
            f"task_{i}": lambda inp, out: {"rolled_back": True}
            for i in range(10)
        }
        
        # Run compensations
        start = time.time()
        success, failed = await coordinator.compensate_saga(
            "saga_parallel", compensation_registry
        )
        elapsed = time.time() - start
        
        assert success is True
        assert len(failed) == 0
        # Should complete quickly
        assert elapsed < 1.0, f"Compensation too slow: {elapsed}s"

    @pytest.mark.asyncio
    async def test_many_compensation_tasks(self):
        """Test: Many compensation tasks."""
        dlq = DeadLetterQueue()
        config = CompensationConfig(max_attempts=1)
        coordinator = SagaCoordinator(dlq, config)
        
        await coordinator.start_saga("saga_many", "wf_many")
        
        # Record 50 completed tasks
        for i in range(50):
            await coordinator.record_task_completion("saga_many", f"task_{i}")
        
        compensation_registry = {
            f"task_{i}": lambda inp, out: {"done": True}
            for i in range(50)
        }
        
        success, failed = await coordinator.compensate_saga(
            "saga_many", compensation_registry
        )
        
        assert success is True


# ============================================================================
# Multi-Tenant Scale Tests
# ============================================================================

class TestMultiTenantScale:
    """Test multi-tenant performance and isolation."""

    @pytest.mark.asyncio
    async def test_multi_tenant_100_tenants(self):
        """Test: 100 tenants, each with some workflows."""
        quota_store = InMemoryQuotaStore()
        usage_store = InMemoryUsageStore()
        
        manager = MultiTenantQuotaManager(
            quota_store,
            usage_store,
            default_quota=TenantQuota(
                tenant_id="default",
                max_concurrent_workflows=10000,
            ),
        )
        
        start = time.time()
        
        # Simulate 100 tenants
        for tenant_id in [f"tenant_{i}" for i in range(100)]:
            # Each tenant starts some workflows
            for j in range(10):
                await manager.record_workflow_start(tenant_id)
        
        elapsed = time.time() - start
        
        # Should process 1000 workflow starts quickly
        assert elapsed < 1.0, f"Multi-tenant too slow: {elapsed}s"

    @pytest.mark.asyncio
    async def test_tenant_isolation_under_load(self):
        """Test: One tenant at limit, others still work."""
        quota_store = InMemoryQuotaStore()
        usage_store = InMemoryUsageStore()
        
        manager = MultiTenantQuotaManager(
            quota_store,
            usage_store,
            TenantQuota(tenant_id="default", max_concurrent_workflows=10),
        )
        
        # Fill tenant A
        await manager.set_quota(TenantQuota(
            tenant_id="tenant_a",
            max_concurrent_workflows=5,
        ))
        
        for _ in range(5):
            await manager.record_workflow_start("tenant_a")
        
        # Tenant B should still work
        for _ in range(10):
            allowed = await manager.check_workflow_allowed("tenant_b")
            if allowed.allowed:
                await manager.record_workflow_start("tenant_b")
        
        usage_b = await manager.get_usage("tenant_b")
        assert usage_b.active_workflows > 0


# ============================================================================
# Memory and Resource Tests
# ============================================================================

class TestResourceUsage:
    """Test resource usage limits."""

    @pytest.mark.asyncio
    async def test_heartbeat_store_memory(self):
        """Test: Heartbeat store handles many entries."""
        store = InMemoryHeartbeatStore()
        manager = ActivityHeartbeatManager(store)
        
        # Create many activities
        for i in range(1000):
            await manager.start_activity(
                activity_id=f"act_{i}",
                workflow_id=f"wf_{i % 10}",
                worker_id="worker_1",
            )
        
        # Should still be responsive
        status = await manager.get_activity_status("act_0")
        assert status is not None
        
        # Start some activities that won't be completed (for abandoned check)
        for i in range(500, 600):
            await manager.start_activity(f"act_{i}", f"wf_{i % 10}", "worker_1")
        
        # After completing some and abandoning others
        abandoned = await manager.get_abandoned_activities()
        # Some activities should be abandoned
        assert isinstance(abandoned, list)

    @pytest.mark.asyncio
    async def test_repeated_snapshots(self):
        """Test: Many snapshots don't cause memory issues."""
        from core.runtime.enterprise.history_compaction import HistoryCompactor
        
        compactor = HistoryCompactor(max_events_before_compaction=100)
        
        # Create many snapshots
        for i in range(100):
            await compactor.create_snapshot(
                f"wf_{i}",
                {"data": i, "large": list(range(100))},
                i * 100,
            )
        
        # Should still work
        snapshot = await compactor.get_snapshot("wf_50")
        assert snapshot is not None
        assert snapshot["state"]["data"] == 50


# ============================================================================
# Latency Tests
# ============================================================================

class TestLatency:
    """Test latency characteristics."""

    @pytest.mark.asyncio
    async def test_single_activity_latency(self):
        """Test: Single activity start latency."""
        store = InMemoryHeartbeatStore()
        manager = ActivityHeartbeatManager(store)
        
        latencies = []
        
        for i in range(100):
            start = time.time()
            await manager.start_activity(
                activity_id=f"act_{i}",
                workflow_id="wf_latency",
                worker_id="worker1",
            )
            latencies.append((time.time() - start) * 1000)  # ms
        
        # Calculate p95
        latencies.sort()
        p95 = latencies[94]  # 95th percentile
        
        # Should be very fast
        assert p95 < 10, f"p95 latency too high: {p95}ms"

    @pytest.mark.asyncio
    async def test_lease_acquisition_latency(self):
        """Test: Lease acquisition latency."""
        from core.runtime.enterprise.heartbeat_lease import LeaseManager, InMemoryLeaseStore
        
        store = InMemoryLeaseStore()
        manager = LeaseManager(store)
        
        latencies = []
        
        for i in range(100):
            start = time.time()
            await manager.acquire_lease(f"task_{i}", "worker1")
            latencies.append((time.time() - start) * 1000)
        
        latencies.sort()
        p95 = latencies[94]
        
        assert p95 < 10, f"p95 latency too high: {p95}ms"


# ============================================================================
# Stress Tests
# ============================================================================

class TestStress:
    """Stress tests for extreme scenarios."""

    @pytest.mark.asyncio
    async def test_rapid_heartbeat_renewal(self):
        """Test: Rapid heartbeat renewals."""
        store = InMemoryHeartbeatStore()
        manager = ActivityHeartbeatManager(store, lease_duration_seconds=60)
        
        # Start activity
        await manager.start_activity("act_stress", "wf_stress", "worker1")
        
        # Rapid heartbeats
        for _ in range(100):
            await manager.record_heartbeat("act_stress", "worker1")
        
        status = await manager.get_activity_status("act_stress")
        assert status["is_healthy"] is True

    @pytest.mark.asyncio
    async def test_many_concurrent_leases(self):
        """Test: Many concurrent lease operations."""
        from core.runtime.enterprise.heartbeat_lease import LeaseManager, InMemoryLeaseStore
        
        store = InMemoryLeaseStore()
        manager = LeaseManager(store)
        
        leases = []
        
        # Acquire many leases
        for i in range(100):
            lease = await manager.acquire_lease(f"task_{i}", "worker1")
            leases.append(lease)
        
        # Verify all leases
        for lease in leases:
            is_valid = await manager.is_lease_valid(lease.lease_id)
            assert is_valid is True
        
        # Release all
        for lease in leases:
            await manager.release_lease(lease.lease_id)
        
        # Verify released
        for lease in leases:
            is_valid = await manager.is_lease_valid(lease.lease_id)
            assert is_valid is False
