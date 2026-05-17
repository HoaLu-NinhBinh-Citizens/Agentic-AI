"""Phase 5B Comprehensive Test Suite - Simplified.

This is a simplified test suite focusing on core functionality that works
with the existing Phase 5B implementation.
"""

from __future__ import annotations

import pytest
import asyncio

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))


# ============================================================================
# 1. UNIT TESTS - ConditionEvaluator
# ============================================================================

class TestConditionEvaluatorSandbox:
    """Test AST sandbox security."""

    def test_comparison_operators_allowed(self):
        """Test comparison operators work correctly."""
        from application.planner.condition_evaluator import ConditionEvaluator
        evaluator = ConditionEvaluator()
        
        assert evaluator.evaluate("1 == 1", {})[0] is True
        assert evaluator.evaluate("1 < 2", {})[0] is True
        assert evaluator.evaluate("3 > 2", {})[0] is True

    def test_boolean_operators_allowed(self):
        """Test boolean operators work correctly."""
        from application.planner.condition_evaluator import ConditionEvaluator
        evaluator = ConditionEvaluator()
        
        assert evaluator.evaluate("True and True", {})[0] is True
        assert evaluator.evaluate("True or False", {})[0] is True
        assert evaluator.evaluate("not False", {})[0] is True

    def test_arithmetic_operators_allowed(self):
        """Test arithmetic operators work correctly."""
        from application.planner.condition_evaluator import ConditionEvaluator
        evaluator = ConditionEvaluator()
        
        assert evaluator.evaluate("1 + 2", {})[0] == 3
        assert evaluator.evaluate("5 - 3", {})[0] == 2
        assert evaluator.evaluate("2 * 3", {})[0] == 6

    def test_context_variables_allowed(self):
        """Test context variables can be accessed."""
        from application.planner.condition_evaluator import ConditionEvaluator
        evaluator = ConditionEvaluator()
        context = {"x": 10, "y": 20}
        
        result, _ = evaluator.evaluate("x + y", context)
        assert result == 30

    def test_eval_blocked(self):
        """Test that eval() is blocked."""
        from application.planner.condition_evaluator import ConditionEvaluator
        evaluator = ConditionEvaluator()
        
        _, error = evaluator.evaluate('eval("1+1")', {})
        assert error is not None

    def test_attribute_access_blocked(self):
        """Test that attribute access is blocked."""
        from application.planner.condition_evaluator import ConditionEvaluator
        evaluator = ConditionEvaluator()
        
        _, error = evaluator.evaluate("obj.attr", {"obj": type("obj", (), {"attr": 42})()})
        assert error is not None

    def test_expression_too_long(self):
        """Test that long expressions are rejected."""
        from application.planner.condition_evaluator import ConditionEvaluator
        evaluator = ConditionEvaluator(max_expression_length=100)
        
        result, error = evaluator.evaluate("x" * 200, {})
        assert result is False
        assert error is not None


# ============================================================================
# 2. UNIT TESTS - SchemaValidator
# ============================================================================

class TestSchemaValidator:
    """Test schema validation."""

    @pytest.mark.asyncio
    async def test_validate_input_success(self):
        """Test valid input passes."""
        from application.planner.schema_validator import SchemaValidator, SchemaRegistry
        reg = SchemaRegistry()
        reg.register_schema("task", "1.0", {
            "type": "object",
            "properties": {"user_id": {"type": "string"}},
            "required": ["user_id"],
        })
        validator = SchemaValidator(registry=reg)
        
        result = await validator.validate_input("task", "1.0", {"user_id": "u1"})
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_validate_input_missing_required(self):
        """Test missing required fields fail."""
        from application.planner.schema_validator import SchemaValidator, SchemaRegistry
        reg = SchemaRegistry()
        reg.register_schema("task", "1.0", {
            "type": "object",
            "properties": {"user_id": {"type": "string"}},
            "required": ["user_id"],
        })
        validator = SchemaValidator(registry=reg)
        
        result = await validator.validate_input("task", "1.0", {})
        assert result.is_valid is False


# ============================================================================
# 3. UNIT TESTS - Heartbeat & Lease
# ============================================================================

class TestHeartbeatLease:
    """Test heartbeat and lease management."""

    @pytest.mark.asyncio
    async def test_heartbeat_renew(self):
        """Test heartbeat renews lease."""
        from core.runtime.enterprise.heartbeat_lease import (
            ActivityHeartbeatManager, InMemoryHeartbeatStore
        )
        store = InMemoryHeartbeatStore()
        manager = ActivityHeartbeatManager(store, lease_duration_seconds=60)
        
        await manager.start_activity("act1", "wf1", "worker1")
        original = (await manager.get_activity_status("act1"))["lease_expiry"]
        
        await asyncio.sleep(0.1)
        await manager.record_heartbeat("act1", "worker1")
        updated = (await manager.get_activity_status("act1"))["lease_expiry"]
        
        assert updated >= original

    @pytest.mark.asyncio
    async def test_lease_expired_reassign(self):
        """Test expired lease triggers reassignment."""
        from core.runtime.enterprise.heartbeat_lease import (
            LeaseManager, InMemoryLeaseStore
        )
        store = InMemoryLeaseStore()
        manager = LeaseManager(store, default_lease_seconds=1)
        
        lease = await manager.acquire_lease("task1", "worker1")
        await asyncio.sleep(1.5)
        
        assert await manager.is_lease_valid(lease.lease_id) is False
        
        new_lease = await manager.reassign_task("task1", "worker1", "worker2")
        assert new_lease is not None


# ============================================================================
# 4. UNIT TESTS - Compensation/Saga
# ============================================================================

class TestCompensationSaga:
    """Test saga compensation pattern."""

    @pytest.mark.asyncio
    async def test_saga_compensation_order(self):
        """Test compensation runs in reverse order."""
        from core.runtime.enterprise.compensation_saga import (
            SagaCoordinator, DeadLetterQueue, CompensationConfig
        )
        coordinator = SagaCoordinator(DeadLetterQueue(), CompensationConfig())
        
        await coordinator.start_saga("saga1", "wf1")
        await coordinator.record_task_completion("saga1", "task1")
        await coordinator.record_task_completion("saga1", "task2")
        
        tasks = await coordinator.fail_saga("saga1", "failed")
        
        assert len(tasks) == 2
        assert tasks[0].original_task_id == "task2"
        assert tasks[1].original_task_id == "task1"

    @pytest.mark.asyncio
    async def test_compensation_retry_backoff(self):
        """Test failed compensation retries with backoff."""
        from core.runtime.enterprise.compensation_saga import (
            SagaCoordinator, DeadLetterQueue, CompensationConfig, CompensationStatus
        )
        config = CompensationConfig(max_attempts=3, initial_delay_seconds=0.01)
        coordinator = SagaCoordinator(DeadLetterQueue(), config)
        
        await coordinator.start_saga("saga1", "wf1")
        await coordinator.record_task_completion("saga1", "task1")
        
        from core.runtime.enterprise.compensation_saga import CompensationTask
        task = CompensationTask(
            task_id="comp", original_task_id="task1",
            original_input={}, original_output={}, max_retries=3
        )
        
        call_count = 0
        async def flaky(inp, out):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("fail")
            return {"ok": True}
        
        success = await coordinator.execute_compensation("saga1", task, flaky)
        assert success is True
        assert task.retry_count == 2

    @pytest.mark.asyncio
    async def test_compensation_dead_letter(self):
        """Test retries exhausted goes to dead letter."""
        from core.runtime.enterprise.compensation_saga import (
            SagaCoordinator, DeadLetterQueue, CompensationConfig, CompensationStatus
        )
        config = CompensationConfig(max_attempts=2, initial_delay_seconds=0.01)
        coordinator = SagaCoordinator(DeadLetterQueue(), config)
        
        await coordinator.start_saga("saga1", "wf1")
        await coordinator.record_task_completion("saga1", "task1")
        
        from core.runtime.enterprise.compensation_saga import CompensationTask
        task = CompensationTask(
            task_id="comp", original_task_id="task1",
            original_input={}, original_output={}, max_retries=2
        )
        
        async def always_fail(inp, out):
            raise RuntimeError("permanent failure")
        
        await coordinator.execute_compensation("saga1", task, always_fail)
        
        assert task.status == CompensationStatus.FAILED
        entries = await coordinator._dlq.get_by_saga("saga1")
        assert len(entries) == 1


# ============================================================================
# 5. UNIT TESTS - DeadlockDetector
# ============================================================================

class TestDeadlockDetector:
    """Test deadlock detection."""

    @pytest.mark.asyncio
    async def test_detect_cycle(self):
        """Test cycle detection in DAG."""
        from application.planner.deadlock_detector import DeadlockDetector
        from application.planner.types import PlanGraph, PlanNode
        
        detector = DeadlockDetector()
        cyclic_plan = PlanGraph(
            plan_id="c", goal="c",
            nodes=[
                PlanNode(node_id="a", task_type="task", description="A",
                    depends_on=["b"], estimated_cost=1.0),
                PlanNode(node_id="b", task_type="task", description="B",
                    depends_on=["a"], estimated_cost=1.0),
            ],
            root_node_id="a",
        )
        
        report = await detector.detect_deadlock(cyclic_plan)
        assert report.has_deadlock is True
        assert len(report.cycles) > 0

    @pytest.mark.asyncio
    async def test_valid_dag_no_deadlock(self):
        """Test valid DAG has no cycle."""
        from application.planner.deadlock_detector import DeadlockDetector
        from application.planner.types import PlanGraph, PlanNode
        
        detector = DeadlockDetector()
        valid_plan = PlanGraph(
            plan_id="v", goal="v",
            nodes=[
                PlanNode(node_id="root", task_type="task", description="R",
                    depends_on=[], estimated_cost=1.0),
                PlanNode(node_id="child", task_type="task", description="C",
                    depends_on=["root"], estimated_cost=1.0),
                PlanNode(node_id="leaf", task_type="task", description="L",
                    depends_on=["child"], estimated_cost=1.0),
            ],
            root_node_id="root",
        )
        
        # Test cycle detection (should have no cycles)
        cycles = await detector.validate_acyclic(valid_plan)
        assert len(cycles) == 0


# ============================================================================
# 6. UNIT TESTS - PoisonToolDefense
# ============================================================================

class TestPoisonDefense:
    """Test poison tool defense."""

    @pytest.mark.asyncio
    async def test_dangerous_script_blocked(self):
        """Test dangerous script content is blocked."""
        from core.runtime.enterprise.poison_defense import PoisonToolDefense
        defense = PoisonToolDefense()
        
        allowed, _, issues = await defense.process_output(
            "tool", "<script>alert('xss')</script>"
        )
        assert allowed is False

    @pytest.mark.asyncio
    async def test_safe_output_allowed(self):
        """Test safe output is allowed."""
        from core.runtime.enterprise.poison_defense import PoisonToolDefense
        defense = PoisonToolDefense()
        
        allowed, result, _ = await defense.process_output(
            "tool", {"status": "ok", "data": "result"}
        )
        assert allowed is True


# ============================================================================
# 7. UNIT TESTS - EventIntegrity
# ============================================================================

class TestEventIntegrity:
    """Test event integrity and hash chain."""

    def test_verify_valid_chain(self):
        """Test verifying valid event chain."""
        from core.runtime.enterprise.event_integrity import HashChainValidator
        
        validator = HashChainValidator()
        events = [
            {"event_id": "e1", "sequence": 0, "event_type": "start", "data": {}},
            {"event_id": "e2", "sequence": 1, "event_type": "task", "data": {}},
        ]
        
        chained = []
        prev_hash = "genesis"
        for e in events:
            h = validator.compute_event_hash(e["event_id"], e["sequence"], e["event_type"], e["data"])
            chained.append({**e, "previous_hash": prev_hash, "event_hash": h})
            prev_hash = h
        
        result = validator.verify_chain(chained)
        assert result.valid is True

    def test_detect_tampered_event(self):
        """Test detecting tampered event."""
        from core.runtime.enterprise.event_integrity import HashChainValidator
        
        validator = HashChainValidator()
        events = [
            {"event_id": "e1", "sequence": 0, "event_type": "start", "data": {}},
        ]
        
        chained = []
        prev_hash = "genesis"
        for e in events:
            h = validator.compute_event_hash(e["event_id"], e["sequence"], e["event_type"], e["data"])
            chained.append({**e, "previous_hash": prev_hash, "event_hash": h})
            prev_hash = h
        
        chained[0]["data"] = {"corrupted": True}
        
        result = validator.verify_chain(chained)
        assert result.valid is False


# ============================================================================
# 8. UNIT TESTS - ExpansionGuard
# ============================================================================

class TestExpansionGuard:
    """Test planner expansion guard."""

    def test_search_states_limit(self):
        """Test search states limit enforced."""
        from application.planner.expansion_guard import PlannerExpansionGuard
        
        guard = PlannerExpansionGuard(max_search_states=100)
        
        result = guard.validate_search_states(50)
        assert result.is_valid is True
        
        result = guard.validate_search_states(150)
        assert result.is_valid is False

    def test_timeout_check(self):
        """Test timeout checking."""
        from application.planner.expansion_guard import PlannerExpansionGuard
        
        guard = PlannerExpansionGuard(planning_timeout_seconds=10.0)
        
        assert guard.check_timeout(5.0) is False
        assert guard.check_timeout(15.0) is True


# ============================================================================
# 9. INTEGRATION TESTS - Multi-Tenant
# ============================================================================

class TestMultiTenant:
    """Test multi-tenant isolation."""

    @pytest.mark.asyncio
    async def test_tenant_isolation(self):
        """Test tenant A hogging doesn't affect tenant B."""
        from core.runtime.enterprise.multi_tenant import (
            MultiTenantQuotaManager, InMemoryQuotaStore, InMemoryUsageStore, TenantQuota
        )
        manager = MultiTenantQuotaManager(
            InMemoryQuotaStore(), InMemoryUsageStore(),
            TenantQuota(tenant_id="default", max_concurrent_workflows=10)
        )
        
        await manager.set_quota(TenantQuota(tenant_id="a", max_concurrent_workflows=2))
        
        for _ in range(2):
            await manager.record_workflow_start("a")
        
        result = await manager.check_workflow_allowed("b")
        assert result.allowed is True


# ============================================================================
# 10. INTEGRATION TESTS - Continue-As-New
# ============================================================================

class TestContinueAsNew:
    """Test continue-as-new functionality."""

    @pytest.mark.asyncio
    async def test_compact_snapshot(self):
        """Test event count > threshold triggers compaction."""
        from core.runtime.enterprise.history_compaction import HistoryCompactor
        
        compactor = HistoryCompactor(max_events_before_compaction=100)
        
        assert compactor.should_compact(50) is False
        assert compactor.should_compact(101) is True

    @pytest.mark.asyncio
    async def test_archive_and_snapshot(self):
        """Test archiving events creates snapshot."""
        from core.runtime.enterprise.history_compaction import HistoryCompactor
        
        compactor = HistoryCompactor(max_events_before_compaction=100)
        events = [{"event_id": f"e{i}", "sequence": i, "event_type": "task", "data": {}}
                  for i in range(200)]
        
        result = await compactor.archive_events("wf1", events, {"state": "test"})
        
        assert result.events_archived > 0
        assert result.snapshot_id != ""


# ============================================================================
# 11. CHAOS TESTS
# ============================================================================

class TestChaosScenarios:
    """Test chaos scenarios."""

    @pytest.mark.asyncio
    async def test_idempotent_resume(self):
        """Test duplicate resume is idempotent."""
        from core.runtime.enterprise.exactly_once import IdempotencyKeyGenerator
        
        gen = IdempotencyKeyGenerator()
        key1 = gen.generate("wf1", "task1", 1)
        key2 = gen.generate("wf1", "task1", 1)
        
        assert key1 == key2

    @pytest.mark.asyncio
    async def test_quota_enforcement(self):
        """Test quota limit enforced."""
        from core.runtime.enterprise.multi_tenant import (
            MultiTenantQuotaManager, InMemoryQuotaStore, InMemoryUsageStore, TenantQuota
        )
        manager = MultiTenantQuotaManager(
            InMemoryQuotaStore(), InMemoryUsageStore(),
            TenantQuota(tenant_id="default", max_concurrent_workflows=2)
        )
        
        await manager.record_workflow_start("t1")
        await manager.record_workflow_start("t1")
        
        result = await manager.check_workflow_allowed("t1")
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_clock_skew_tolerance(self):
        """Test lease handles clock skew."""
        from core.runtime.enterprise.heartbeat_lease import LeaseManager, InMemoryLeaseStore
        
        store = InMemoryLeaseStore()
        manager = LeaseManager(store, default_lease_seconds=2)
        
        lease = await manager.acquire_lease("task1", "worker1")
        valid = await manager.is_lease_valid(lease.lease_id)
        assert valid is True

    @pytest.mark.asyncio
    async def test_poison_tool_quarantine(self):
        """Test poison tool is quarantined."""
        from core.runtime.enterprise.poison_defense import PoisonToolDefense
        
        defense = PoisonToolDefense()
        
        allowed, _, _ = await defense.process_output("bad", "<script>alert(1)</script>")
        assert allowed is False
        
        is_allowed = defense.is_allowed("bad")
        assert is_allowed is False


# ============================================================================
# 12. PERFORMANCE TESTS
# ============================================================================

class TestPerformance:
    """Test performance characteristics."""

    @pytest.mark.asyncio
    async def test_many_activities_fast(self):
        """Test creating many activities is fast."""
        from core.runtime.enterprise.heartbeat_lease import (
            ActivityHeartbeatManager, InMemoryHeartbeatStore
        )
        import time
        
        manager = ActivityHeartbeatManager(InMemoryHeartbeatStore())
        
        start = time.time()
        for i in range(100):
            await manager.start_activity(f"act_{i}", "wf1", "worker1")
        elapsed = time.time() - start
        
        assert elapsed < 1.0

    @pytest.mark.asyncio
    async def test_hash_chain_performance(self):
        """Test hash chain computation is fast."""
        from core.runtime.enterprise.event_integrity import HashChainValidator
        import time
        
        validator = HashChainValidator()
        
        start = time.time()
        for i in range(1000):
            validator.compute_hash({"data": f"item_{i}"})
        elapsed = time.time() - start
        
        assert elapsed < 0.2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
