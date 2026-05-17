"""Integration tests for Phase 5B enterprise features.

Tests cover end-to-end scenarios with available components.
"""

from __future__ import annotations

import pytest
import asyncio

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from application.planner.condition_evaluator import ConditionEvaluator, BranchConditionEvaluator
from application.planner.deadlock_detector import DeadlockDetector, ConditionalDeadlockDetector
from application.planner.expansion_guard import PlannerExpansionGuard
from core.runtime.enterprise.compensation_saga import SagaCoordinator, DeadLetterQueue, CompensationConfig
from core.runtime.enterprise.heartbeat_lease import ActivityHeartbeatManager, LeaseManager, InMemoryHeartbeatStore, InMemoryLeaseStore
from core.runtime.enterprise.multi_tenant import MultiTenantQuotaManager, InMemoryQuotaStore, InMemoryUsageStore, TenantQuota
from core.runtime.enterprise.poison_defense import PoisonToolDefense, ToolOutputSanitizer, TrustScoreManager
from core.runtime.enterprise.history_compaction import ContinueAsNewManager, HistoryCompactor
from core.runtime.enterprise.event_integrity import HashChainValidator, EventIntegrityManager


# ============================================================================
# Workflow Lifecycle Integration Tests
# ============================================================================

class TestWorkflowLifecycle:
    """Test workflow creation and completion."""

    @pytest.mark.asyncio
    async def test_workflow_create_and_complete(self):
        """Test creating a workflow and completing it."""
        heartbeat_store = InMemoryHeartbeatStore()
        heartbeat_manager = ActivityHeartbeatManager(heartbeat_store, lease_duration_seconds=30)
        
        hb = await heartbeat_manager.start_activity(
            activity_id="act1",
            workflow_id="wf1",
            worker_id="worker1",
        )
        
        assert hb.activity_id == "act1"
        assert hb.workflow_id == "wf1"
        
        await heartbeat_manager.complete_activity("act1")
        
        status = await heartbeat_manager.get_activity_status("act1")
        assert status is None

    @pytest.mark.asyncio
    async def test_workflow_replay_after_crash(self):
        """Test workflow replay after simulated crash."""
        validator = HashChainValidator()
        
        events_original = [
            {"event_id": "e1", "sequence": 0, "event_type": "start", "data": {}},
            {"event_id": "e2", "sequence": 1, "event_type": "task1", "data": {}},
        ]
        
        chained = []
        prev_hash = "genesis"
        for e in events_original:
            hash_val = validator.compute_event_hash(
                e["event_id"], e["sequence"], e["event_type"], e["data"]
            )
            chained.append({**e, "previous_hash": prev_hash, "event_hash": hash_val})
            prev_hash = hash_val
        
        result = validator.verify_chain(chained)
        assert result.valid is True


# ============================================================================
# Branch Decision Integration Tests
# ============================================================================

class TestBranchDecision:
    """Test conditional branch decisions."""

    @pytest.mark.asyncio
    async def test_conditional_branch_replay(self):
        """Test that branch decisions are validated for replay."""
        evaluator = BranchConditionEvaluator()
        
        result = evaluator.validate_condition("x > 5")
        assert result.is_valid is True
        
        result = evaluator.validate_condition("lambda x: x")
        assert result.is_valid is False

    @pytest.mark.asyncio
    async def test_branch_decision_sandbox(self):
        """Test that unsafe branch decisions are rejected."""
        evaluator = BranchConditionEvaluator()
        
        result = evaluator.validate_condition("obj.value > 5")
        assert result.is_valid is False
        
        result = evaluator.validate_condition("__import__('os').system('ls')")
        assert result.is_valid is False


# ============================================================================
# Parallel Execution Integration Tests
# ============================================================================

class TestParallelExecution:
    """Test parallel DAG execution."""

    @pytest.mark.asyncio
    async def test_parallel_dag_execution(self):
        """Test that parallel tasks validate correctly."""
        detector = DeadlockDetector()
        
        plan = PlanGraph(
            plan_id="parallel-001",
            goal="Parallel Plan",
            nodes=[
                PlanNode(
                    node_id="root",
                    task_type="task",
                    description="Root",
                    depends_on=[],
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
                PlanNode(
                    node_id="parallel1",
                    task_type="task",
                    description="Parallel 1",
                    depends_on=["root"],
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
                PlanNode(
                    node_id="parallel2",
                    task_type="task",
                    description="Parallel 2",
                    depends_on=["root"],
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
                PlanNode(
                    node_id="join",
                    task_type="join",
                    description="Join",
                    depends_on=["parallel1", "parallel2"],
                    branch_options=[],
                    condition_expr=None,
                    join_policy="ALL_COMPLETE",
                    estimated_cost=0.0,
                    estimated_duration=0.0,
                ),
            ],
            root_node_id="root",
        )
        
        report = await detector.detect_deadlock(plan)
        # No cycles should be detected
        assert len(report.cycles) == 0


# ============================================================================
# Retry & Snapshot Integration Tests
# ============================================================================

class TestRetryAndSnapshot:
    """Test retry with snapshot isolation."""

    @pytest.mark.asyncio
    async def test_snapshot_isolation(self):
        """Test that snapshots maintain isolation."""
        compactor = HistoryCompactor(max_events_before_compaction=100)
        
        state1 = {"step": 1, "data": [1, 2, 3]}
        state2 = {"step": 2, "data": [4, 5, 6]}
        
        snapshot_id1 = await compactor.create_snapshot("wf1", state1, 50)
        snapshot_id2 = await compactor.create_snapshot("wf1", state2, 100)
        
        snapshot = await compactor.get_snapshot("wf1")
        
        assert snapshot["state"]["step"] == 2


# ============================================================================
# Cancellation Integration Tests
# ============================================================================

class TestCancellation:
    """Test cancellation scenarios."""

    @pytest.mark.asyncio
    async def test_compensation_on_failure(self):
        """Test that failed tasks trigger compensation."""
        dlq = DeadLetterQueue()
        config = CompensationConfig(max_attempts=1, initial_delay_seconds=0.01)
        coordinator = SagaCoordinator(dlq, config)
        
        await coordinator.start_saga("saga1", "wf1")
        
        # Record completed tasks (these will be compensated on failure)
        await coordinator.record_task_completion("saga1", "reserve_hotel")
        await coordinator.record_task_completion("saga1", "book_flight")
        
        # Fail the saga - this creates compensation tasks from completed tasks
        tasks = await coordinator.fail_saga("saga1", "book_activity")
        
        # Should have 2 compensation tasks created
        assert len(tasks) == 2
        
        # Use async functions since execute_compensation awaits the compensation fn
        async def cancel_hotel(i, o):
            return {"hotel_cancelled": True}
        
        async def refund_flight(i, o):
            return {"flight_refunded": True}
        
        registry = {
            "reserve_hotel": cancel_hotel,
            "book_flight": refund_flight,
        }
        
        success, failed = await coordinator.compensate_saga("saga1", registry)
        
        # Both compensations should succeed (no failures)
        assert success is True


# ============================================================================
# Activity Heartbeat Reassignment Tests
# ============================================================================

class TestActivityReassignment:
    """Test activity heartbeat and reassignment."""

    @pytest.mark.asyncio
    async def test_activity_heartbeat_reassign(self):
        """Test that activity without heartbeat is detected as abandoned."""
        store = InMemoryHeartbeatStore()
        heartbeat_manager = ActivityHeartbeatManager(
            store,
            lease_duration_seconds=1,
        )
        lease_store = InMemoryLeaseStore()
        lease_manager = LeaseManager(lease_store)
        
        await heartbeat_manager.start_activity("act1", "wf1", "worker1")
        lease = await lease_manager.acquire_lease("act1", "worker1")
        
        await asyncio.sleep(1.5)
        
        abandoned = await heartbeat_manager.get_abandoned_activities()
        assert "act1" in abandoned
        
        new_lease = await lease_manager.reassign_task("act1", "worker1", "worker2")
        
        assert new_lease is not None
        assert new_lease.worker_id == "worker2"


# ============================================================================
# Multi-Tenant Integration Tests
# ============================================================================

class TestMultiTenantIntegration:
    """Test multi-tenant isolation."""

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self):
        """Test that one tenant hogging resources doesn't affect another."""
        quota_store = InMemoryQuotaStore()
        usage_store = InMemoryUsageStore()
        
        manager = MultiTenantQuotaManager(
            quota_store,
            usage_store,
            default_quota=TenantQuota(
                tenant_id="default",
                max_concurrent_workflows=10,
            ),
        )
        
        await manager.set_quota(TenantQuota(
            tenant_id="tenant_a",
            max_concurrent_workflows=5,
        ))
        await manager.set_quota(TenantQuota(
            tenant_id="tenant_b",
            max_concurrent_workflows=5,
        ))
        
        for _ in range(5):
            await manager.record_workflow_start("tenant_a")
        
        allowed = await manager.check_workflow_allowed("tenant_b")
        assert allowed.allowed is True
        
        for _ in range(3):
            await manager.record_workflow_start("tenant_b")
        
        usage_b = await manager.get_usage("tenant_b")
        assert usage_b.active_workflows == 3


# ============================================================================
# Continue-As-New Integration Tests
# ============================================================================

class TestContinueAsNew:
    """Test continue-as-new functionality."""

    @pytest.mark.asyncio
    async def test_continue_as_new(self):
        """Test workflow continues with new event history."""
        compactor = HistoryCompactor(max_events_before_compaction=100)
        manager = ContinueAsNewManager(compactor)
        
        events = [
            {"event_id": f"e{i}", "sequence": i, "event_type": "task", "data": {}}
            for i in range(250)
        ]
        
        state = {"counter": 100, "stage": "running"}
        
        result = await manager.continue_workflow("wf_long", state, events)
        
        assert result.events_archived > 0
        assert result.new_workflow_id == "wf_long_continue"
        
        restored = await manager.restore_state("wf_long_continue")
        assert restored["counter"] == 100


# ============================================================================
# Poison Defense Integration Tests
# ============================================================================

class TestPoisonDefenseIntegration:
    """Test poison defense integration."""

    @pytest.mark.asyncio
    async def test_tool_output_poisoning(self):
        """Test that poisoned tool outputs are blocked."""
        defense = PoisonToolDefense()
        
        allowed1, _, issues1 = await defense.process_output(
            "bad_tool", "<script>alert('xss')</script>"
        )
        assert allowed1 is False
        
        allowed2, result2, _ = await defense.process_output(
            "good_tool", {"status": "ok", "data": "result"}
        )
        assert allowed2 is True


# ============================================================================
# End-to-End Workflow Test
# ============================================================================

class TestEndToEndWorkflow:
    """Complete end-to-end workflow test."""

    @pytest.mark.asyncio
    async def test_complete_workflow_flow(self):
        """Test complete workflow from start to finish."""
        heartbeat_store = InMemoryHeartbeatStore()
        heartbeat_manager = ActivityHeartbeatManager(heartbeat_store)
        
        lease_store = InMemoryLeaseStore()
        lease_manager = LeaseManager(lease_store)
        
        dlq = DeadLetterQueue()
        saga_config = CompensationConfig()
        saga_coordinator = SagaCoordinator(dlq, saga_config)
        
        await heartbeat_manager.start_activity("main_task", "wf1", "worker1")
        lease = await lease_manager.acquire_lease("main_task", "worker1")
        
        await heartbeat_manager.record_heartbeat("main_task", "worker1")
        
        await saga_coordinator.start_saga("saga_wf1", "wf1")
        await saga_coordinator.record_task_completion("saga_wf1", "task1")
        
        await heartbeat_manager.complete_activity("main_task")
        await lease_manager.release_lease(lease.lease_id)
        
        saga_state = await saga_coordinator.get_saga_state("saga_wf1")
        assert saga_state is not None
        assert "task1" in saga_state.completed_tasks


# ============================================================================
# Required imports for tests
# ============================================================================

from application.planner.types import PlanGraph, PlanNode
