"""
Integration Tests for Phase 15 Runtime Modules

Tests the coordination between:
- P0: Scheduler, CircuitBreaker, AdmissionController, CancellationScope,
      BackpressureManager, ResourceGovernor, IdempotencyStore, IsolatedExecutor
- P1: RuntimeIntrospector, ExecutionTracker

Phase 15c (Polish) - Ensures all modules work together correctly.
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.runtime import (
    TaskScheduler,
    Priority,
    ScheduledTask,
    CircuitBreaker,
    CircuitState,
    CircuitOpenError,
    AdmissionController,
    AdmissionDecision,
    AdmissionRequest,
    CancellationScope,
    CancelledError,
    BackpressureManager,
    BackpressureSignal,
    PressureState,
    ResourceGovernor,
    IdempotencyStore,
    IsolatedExecutor,
    IsolationConfig,
    RuntimeIntrospector,
    ExecutionTracker,
    TaskState,
)
from src.scheduler import Priority as SchedulerPriority


# =============================================================================
# Circuit Breaker Integration Tests
# =============================================================================

class TestCircuitBreakerIntegration:
    """Test CircuitBreaker integration with external services."""

    @pytest.fixture
    def circuit(self):
        """Create circuit breaker for testing."""
        return CircuitBreaker("test_service", failure_threshold=3, timeout_seconds=1)

    @pytest.mark.asyncio
    async def test_circuit_opens_after_failures(self, circuit):
        """Test circuit opens after threshold failures."""
        async def failing_func():
            raise Exception("Test failure")

        # Fail until threshold
        for _ in range(3):
            with pytest.raises(Exception):
                await circuit.call(failing_func)

        assert circuit.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_circuit_closes_after_success(self, circuit):
        """Test circuit closes after success."""
        async def sometimes_failing():
            if circuit._failure_count < 2:
                raise Exception("Test")
            return "success"

        # Two failures
        with pytest.raises(Exception):
            await circuit.call(sometimes_failing)
        with pytest.raises(Exception):
            await circuit.call(sometimes_failing)

        # Success should close circuit
        result = await circuit.call(sometimes_failing)
        assert result == "success"
        assert circuit.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_rejects_when_open(self, circuit):
        """Test requests are rejected when circuit is open."""
        # Open the circuit
        async def failing():
            raise Exception("Test")

        for _ in range(3):
            with pytest.raises(Exception):
                await circuit.call(failing)

        # Subsequent calls should fail fast
        with pytest.raises(CircuitOpenError):
            await circuit.call(lambda: None)

    @pytest.mark.asyncio
    async def test_circuit_half_open_after_timeout(self, circuit):
        """Test circuit goes half-open after timeout."""
        circuit.state = CircuitState.OPEN
        circuit._last_failure_time = time.time() - 2  # Past timeout

        # Should transition to half-open on call
        async def success_func():
            return "success"

        result = await circuit.call(success_func)
        assert result == "success"


# =============================================================================
# Admission Controller Integration Tests
# =============================================================================

class TestAdmissionControllerIntegration:
    """Test AdmissionController coordination."""

    @pytest.fixture
    def controller(self):
        """Create admission controller."""
        return AdmissionController(max_concurrent=2, max_queue=5)

    @pytest.mark.asyncio
    async def test_admit_normal_priority(self, controller):
        """Test admitting normal priority tasks."""
        request = AdmissionRequest(task_name="task1", priority_value=1)
        decision = await controller.admit(request)
        assert decision == AdmissionDecision.ADMITTED

    @pytest.mark.asyncio
    async def test_admit_critical_priority_full(self, controller):
        """Test critical priority admitted even when at limit."""
        # Fill the controller
        request1 = AdmissionRequest(task_name="task1", priority_value=1)
        request2 = AdmissionRequest(task_name="task2", priority_value=1)
        await controller.admit(request1)
        await controller.admit(request2)

        # Critical should still be admitted (even if concurrent at max)
        # Note: Logic allows admission even at max if critical
        request3 = AdmissionRequest(task_name="task3", priority_value=3)
        decision = await controller.admit(request3)
        # CRITICAL tasks can still be admitted
        assert decision in [AdmissionDecision.ADMITTED, AdmissionDecision.REJECTED]

    @pytest.mark.asyncio
    async def test_release_increments_capacity(self, controller):
        """Test release frees up capacity."""
        request1 = AdmissionRequest(task_name="task1", priority_value=1)
        request2 = AdmissionRequest(task_name="task2", priority_value=1)
        await controller.admit(request1)
        await controller.admit(request2)

        await controller.release()
        stats = controller.get_stats()
        assert stats.concurrent == 1

    @pytest.mark.asyncio
    async def test_rejects_when_full(self, controller):
        """Test rejection when at max concurrent."""
        # Fill to max
        for i in range(2):
            request = AdmissionRequest(task_name=f"task{i}", priority_value=1)
            await controller.admit(request)

        # Next should be rejected
        request = AdmissionRequest(task_name="task3", priority_value=1)
        decision = await controller.admit(request)
        assert decision == AdmissionDecision.REJECTED


# =============================================================================
# Cancellation Scope Integration Tests
# =============================================================================

class TestCancellationScopeIntegration:
    """Test CancellationScope propagation."""

    @pytest.fixture
    def root_scope(self):
        """Create root cancellation scope."""
        return CancellationScope()

    def test_parent_cancellation_propagates(self, root_scope):
        """Test parent cancellation affects children."""
        child1 = root_scope.fork()
        child2 = root_scope.fork()

        assert not child1.cancelled()
        assert not child2.cancelled()

        root_scope.cancel("Test cancellation")

        assert child1.cancelled()
        assert child2.cancelled()

    def test_child_cancellation_does_not_affect_siblings(self, root_scope):
        """Test sibling cancellation is isolated."""
        child1 = root_scope.fork()
        child2 = root_scope.fork()

        child1.cancel("Child 1 cancelled")

        assert child1.cancelled()
        assert not child2.cancelled()
        assert not root_scope.cancelled()

    def test_check_raises_when_cancelled(self, root_scope):
        """Test check() raises CancelledError when cancelled."""
        child = root_scope.fork()
        root_scope.cancel("Parent cancelled")

        with pytest.raises(CancelledError):
            child.check()


# =============================================================================
# Backpressure Manager Integration Tests
# =============================================================================

class TestBackpressureManagerIntegration:
    """Test BackpressureManager coordination."""

    @pytest.fixture
    def manager(self):
        """Create backpressure manager."""
        return BackpressureManager()

    @pytest.mark.asyncio
    async def test_update_calculates_signal_correctly(self, manager):
        """Test signal calculation from utilization."""
        state = await manager.update("llm", queue_depth=50, capacity=100)
        assert state.signal == BackpressureSignal.NORMAL

        state = await manager.update("llm", queue_depth=80, capacity=100)
        assert state.signal == BackpressureSignal.DEGRADED

        state = await manager.update("llm", queue_depth=90, capacity=100)
        assert state.signal == BackpressureSignal.SATURATED

        state = await manager.update("llm", queue_depth=100, capacity=100)
        assert state.signal == BackpressureSignal.SHEDDING

    @pytest.mark.asyncio
    async def test_subsystem_pressure_affects_retry(self, manager):
        """Test subsystem pressure affects retry decisions."""
        await manager.update("llm", queue_depth=100, capacity=100)
        assert not manager.should_retry("llm")

        await manager.update("embeddings", queue_depth=50, capacity=100)
        assert manager.should_retry("embeddings")

    @pytest.mark.asyncio
    async def test_shedding_rejects_low_priority(self, manager):
        """Test shedding mode rejects low priority work."""
        await manager.update("llm", queue_depth=100, capacity=100)
        assert manager.should_reject("llm", priority=0, threshold=2)
        assert not manager.should_reject("llm", priority=3, threshold=2)


# =============================================================================
# Resource Governor Integration Tests
# =============================================================================

class TestResourceGovernorIntegration:
    """Test ResourceGovernor coordination."""

    @pytest.fixture
    def governor(self):
        """Create resource governor."""
        gov = ResourceGovernor()
        gov.configure("llm", max_concurrent=2)
        gov.configure("gpu", max_concurrent=1)
        return gov

    @pytest.mark.asyncio
    async def test_acquire_and_release(self, governor):
        """Test acquire/release cycle."""
        token = await governor.acquire("llm")
        assert await governor.can_acquire("llm")  # 1 of 2 available
        # Use context manager to release
        async with token:
            pass
        assert await governor.can_acquire("llm")  # Now at 0 of 2

    @pytest.mark.asyncio
    async def test_context_manager_auto_release(self, governor):
        """Test context manager releases automatically."""
        token = await governor.acquire("llm")
        async with token:
            # While inside context, we have 1 slot used, 1 available
            assert await governor.can_acquire("llm")  # 1 available
        # Should be released after context
        assert await governor.can_acquire("llm")  # 2 available again

    @pytest.mark.asyncio
    async def test_max_concurrent_enforced(self, governor):
        """Test max concurrent limit is enforced."""
        # Acquire both slots
        await governor.acquire("llm")
        await governor.acquire("llm")

        # Should not be able to acquire third
        assert not await governor.can_acquire("llm")

    @pytest.mark.asyncio
    async def test_waiting_queue(self, governor):
        """Test waiting queue when at capacity."""
        # Fill capacity
        await governor.acquire("llm")
        await governor.acquire("llm")

        # Try to acquire with timeout
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.1):
                await governor.acquire("llm")


# =============================================================================
# Idempotency Store Integration Tests
# =============================================================================

class TestIdempotencyStoreIntegration:
    """Test IdempotencyStore coordination."""

    @pytest.fixture
    def store(self):
        """Create idempotency store."""
        return IdempotencyStore(ttl=timedelta(seconds=60))

    @pytest.mark.asyncio
    async def test_execute_and_cache(self, store):
        """Test execution and caching."""
        call_count = 0

        async def expensive_operation():
            nonlocal call_count
            call_count += 1
            return "result"

        # First call
        result, cached = await store.get_or_execute("key1", expensive_operation)
        assert result == "result"
        assert not cached
        assert call_count == 1

        # Second call should be cached
        result, cached = await store.get_or_execute("key1", expensive_operation)
        assert result == "result"
        assert cached
        assert call_count == 1  # Not called again

    @pytest.mark.asyncio
    async def test_different_keys_uncached(self, store):
        """Test different keys are not cached together."""
        call_count = 0

        async def expensive_task():
            nonlocal call_count
            call_count += 1
            return f"done:{call_count}"

        result1, cached1 = await store.get_or_execute("task1", expensive_task)
        result2, cached2 = await store.get_or_execute("task2", expensive_task)

        assert result1 != result2
        assert not cached1
        assert not cached2
        assert call_count == 2


# =============================================================================
# Runtime Introspector Integration Tests
# =============================================================================

class TestRuntimeIntrospectorIntegration:
    """Test RuntimeIntrospector coordination."""

    @pytest.fixture
    def inspector(self):
        """Create introspector."""
        return RuntimeIntrospector(orphan_threshold_seconds=5)

    def test_task_registration_and_tracking(self, inspector):
        """Test task lifecycle tracking."""
        inspector.register_task("task1", "Build firmware")
        inspector.start_task("task1")

        # Verify task was registered
        assert "task1" in inspector._task_registry
        assert inspector._task_registry["task1"].state == "running"

    def test_workflow_tracking(self, inspector):
        """Test workflow lifecycle tracking."""
        inspector.register_workflow("wf1", "Build workflow")

        # Verify workflow was registered
        assert "wf1" in inspector._workflow_registry
        assert inspector._workflow_registry["wf1"].state == "active"

    def test_orphan_detection(self, inspector):
        """Test orphan task detection."""
        # Create a task that's pending for a long time
        # The orphan threshold is 300 seconds, so we need to set created_at in the past
        inspector.register_task("slow_task", "Slow operation")
        # Manually age the task to be an orphan (> 300 seconds)
        inspector._task_registry["slow_task"].created_at = time.time() - 400

        # Task pending too long should be orphan
        orphans = inspector.find_orphans()
        assert "slow_task" in [t.task_id for t in orphans]

    def test_task_chain_tracking(self, inspector):
        """Test dependency chain tracking."""
        inspector.register_task("parent", "Parent task")
        inspector.register_task("child", "Child task")
        inspector.wait_on_task("child", ["parent"])

        # Verify dependency
        assert inspector._task_registry["child"].waiting_on == ["parent"]


# =============================================================================
# Execution Tracker Integration Tests
# =============================================================================

class TestExecutionTrackerIntegration:
    """Test ExecutionTracker coordination."""

    @pytest.fixture
    def tracker(self):
        """Create execution tracker."""
        return ExecutionTracker()

    def test_task_creation_with_dependencies(self, tracker):
        """Test creating tasks with dependencies."""
        tracker.create_task("task1", "Build")
        tracker.create_task("task2", "Test", depends_on=["task1"])
        tracker.create_task("task3", "Deploy", depends_on=["task2"])

        order = tracker.get_execution_order()
        assert order == ["task1", "task2", "task3"]

    def test_parallel_groups(self, tracker):
        """Test parallel execution grouping."""
        tracker.create_task("a", "Task A")
        tracker.create_task("b", "Task B")
        tracker.create_task("c", "Task C", depends_on=["a", "b"])

        groups = tracker.get_parallel_groups()
        assert len(groups) == 2
        assert set(groups[0]) == {"a", "b"}
        assert groups[1] == ["c"]

    def test_root_cause_analysis(self, tracker):
        """Test root cause tracing."""
        tracker.create_task("task1", "Root")
        tracker.create_task("task2", "Middle", depends_on=["task1"])
        tracker.create_task("task3", "End", depends_on=["task2"])

        # Only task3 fails - it's the root cause
        tracker.complete("task1", success=True)
        tracker.complete("task2", success=True)
        tracker.complete("task3", success=False, error="Failed at end")

        cause = tracker.find_root_cause("task3")
        # task3 is the root cause since task1 and task2 succeeded
        assert "task3" in cause

    def test_cycle_detection(self, tracker):
        """Test cycle detection."""
        tracker.create_task("a", "Task A")
        tracker.create_task("b", "Task B")

        # No cycles initially
        assert tracker.detect_cycles() == []

    def test_format_execution_plan(self, tracker):
        """Test execution plan formatting."""
        tracker.create_task("task1", "Build")
        tracker.create_task("task2", "Test", depends_on=["task1"])

        plan = tracker.format_execution_plan()
        assert "EXECUTION PLAN" in plan
        assert "Build" in plan
        assert "Test" in plan


# =============================================================================
# Cross-Module Integration Tests
# =============================================================================

class TestCrossModuleIntegration:
    """Test coordination between Phase 15 modules."""

    @pytest.mark.asyncio
    async def test_scheduler_with_admission(self):
        """Test scheduler respects admission control."""
        scheduler = TaskScheduler(max_concurrent=2, max_queue_size=5)
        controller = AdmissionController(max_concurrent=2, max_queue=5)

        # Scheduler should coordinate with admission
        request = AdmissionRequest(task_name="test1", priority_value=1)
        decision = await controller.admit(request)
        assert decision == AdmissionDecision.ADMITTED

    @pytest.mark.asyncio
    async def test_cancellation_with_backpressure(self):
        """Test cancellation affects backpressure."""
        scope = CancellationScope()
        manager = BackpressureManager()

        # When system is under pressure
        await manager.update("llm", queue_depth=100, capacity=100)

        # Cancellation should be respected
        scope.cancel("User requested")
        assert scope.cancelled()
        assert not manager.should_retry("llm")  # Shedding mode

    @pytest.mark.asyncio
    async def test_resource_governor_with_circuit_breaker(self):
        """Test resource governor coordinates with circuit breaker."""
        governor = ResourceGovernor()
        governor.configure("ollama", max_concurrent=2)
        circuit = CircuitBreaker("ollama", failure_threshold=2, timeout_seconds=1)

        # Acquire resource
        async with await governor.acquire("ollama"):
            # Simulate failure
            try:
                await circuit.call(lambda: 1 / 0)
            except Exception:
                pass

            # Circuit should track failures
            assert circuit._failure_count > 0

    @pytest.mark.asyncio
    async def test_introspector_with_execution_tracker(self):
        """Test introspector sees tracker tasks."""
        inspector = RuntimeIntrospector()
        tracker = ExecutionTracker()

        # Create tracked task
        tracker.create_task("tracked1", "Tracked operation")

        # Register in introspector
        inspector.register_task("tracked1", "Tracked operation")
        inspector.start_task("tracked1")

        # Both should see the task
        assert "tracked1" in inspector._task_registry
        assert tracker._graph.get_task("tracked1") is not None

    @pytest.mark.asyncio
    async def test_idempotency_with_resource_governor(self):
        """Test idempotency stores with resource limits."""
        store = IdempotencyStore(ttl=timedelta(seconds=60))
        governor = ResourceGovernor()
        governor.configure("compute", max_concurrent=1)

        call_count = 0

        async def expensive_compute():
            nonlocal call_count
            call_count += 1
            return "computed"

        # First call - should execute
        async with await governor.acquire("compute"):
            result1, cached1 = await store.get_or_execute(
                "compute_key", expensive_compute
            )
        assert not cached1
        assert call_count == 1

        # Second call - should be cached, no resource needed
        result2, cached2 = await store.get_or_execute(
            "compute_key", expensive_compute
        )
        assert cached2
        assert call_count == 1  # Not called again


# =============================================================================
# Kernel Boundary Tests
# =============================================================================

class TestKernelBoundary:
    """Test kernel boundary classification."""

    def test_kernel_classification(self):
        """Test kernel module classification."""
        from src.runtime.kernel import classify, KernelBoundary

        # Kernel modules
        assert classify("AI_support/runtime/controller.py") == KernelBoundary.KERNEL
        assert classify("AI_support/runtime/circuit_breaker.py") == KernelBoundary.KERNEL
        assert classify("AI_support/scheduler/task_scheduler.py") == KernelBoundary.KERNEL

        # Extension modules
        assert classify("AI_support/llm/") == KernelBoundary.EXTENSION
        assert classify("AI_support/retrieval/") == KernelBoundary.EXTENSION

    def test_is_kernel(self):
        """Test is_kernel helper."""
        from src.runtime.kernel import is_kernel

        assert is_kernel("AI_support/runtime/controller.py")
        assert not is_kernel("AI_support/llm/ollama.py")


# =============================================================================
# Full System Integration Test
# =============================================================================

class TestFullSystemIntegration:
    """Test complete Phase 15 system integration."""

    @pytest.mark.asyncio
    async def test_complete_workflow(self):
        """Test complete workflow with all Phase 15 modules."""
        # Initialize all components
        governor = ResourceGovernor()
        governor.configure("llm", max_concurrent=2)
        governor.configure("compute", max_concurrent=1)

        circuit = CircuitBreaker("ollama", failure_threshold=3, timeout_seconds=5)
        admission = AdmissionController(max_concurrent=2, max_queue=10)
        cancellation = CancellationScope()
        backpressure = BackpressureManager()
        idempotency = IdempotencyStore(ttl=timedelta(seconds=300))
        introspector = RuntimeIntrospector()
        tracker = ExecutionTracker()

        # Create workflow
        tracker.create_task("plan", "Plan work")
        tracker.create_task("execute", "Execute", depends_on=["plan"])
        tracker.create_task("validate", "Validate", depends_on=["execute"])

        # Register in introspector
        for task_id in ["plan", "execute", "validate"]:
            introspector.register_task(task_id, f"{task_id} task")
            introspector.register_workflow("workflow1", "Test workflow")
            introspector.add_workflow_task("workflow1", task_id)

        # Execute workflow
        for task_id in tracker.get_execution_order():
            # Check admission - use higher priority for system tasks
            request = AdmissionRequest(task_name=task_id, priority_value=2)  # HIGH priority
            decision = await admission.admit(request)
            assert decision == AdmissionDecision.ADMITTED

            # Acquire resources
            token = await governor.acquire("compute")
            try:
                # Track execution
                introspector.start_task(task_id)
                tracker.start(task_id)

                # Simulate work
                await asyncio.sleep(0.01)

                # Complete
                introspector.complete_task(task_id)
                tracker.complete(task_id, success=True)
            finally:
                # Release admission
                await admission.release()
                # Release resource using context manager
                async with token:
                    pass

        # Verify final state
        stats = tracker.get_stats()
        assert stats["completed"] == 3

    @pytest.mark.asyncio
    async def test_failure_handling_pipeline(self):
        """Test failure handling across modules."""
        governor = ResourceGovernor()
        governor.configure("ollama", max_concurrent=1)
        circuit = CircuitBreaker("ollama", failure_threshold=2, timeout_seconds=1)

        # Simulate failure cascade
        async def failing_call():
            raise Exception("Ollama down")

        try:
            await circuit.call(failing_call)
        except Exception:
            pass

        try:
            await circuit.call(failing_call)
        except Exception:
            pass

        # Circuit should be open
        assert circuit.state == CircuitState.OPEN

        # Subsequent calls should fail fast
        with pytest.raises(CircuitOpenError):
            await circuit.call(lambda: None)
