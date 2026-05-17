"""Unit tests for saga/compensation pattern.

Tests cover:
- test_saga_compensation_order: Compensation runs in reverse order
- test_compensation_retry_backoff: Failed compensator retries with backoff
- test_compensation_dead_letter: Retries exhausted -> dead letter queue
"""

from __future__ import annotations

import pytest
import asyncio

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from core.runtime.enterprise.compensation_saga import (
    SagaCoordinator,
    DeadLetterQueue,
    CompensationManager,
    CompensationConfig,
    CompensationStatus,
    CompensationRetryPolicy,
    CompensationTask,
    DeadLetterReason,
    DeadLetterEntry,
    SagaState,
)


# ============================================================================
# Saga Coordinator Tests
# ============================================================================

class TestSagaCoordinator:
    """Test saga coordinator."""

    @pytest.fixture
    def coordinator(self):
        """Create saga coordinator with default config."""
        dlq = DeadLetterQueue()
        config = CompensationConfig(
            max_attempts=3,
            initial_delay_seconds=0.01,  # Short delay for tests
            backoff_multiplier=2.0,
        )
        return SagaCoordinator(dlq, config)

    @pytest.mark.asyncio
    async def test_start_saga(self, coordinator):
        """Test starting a new saga."""
        state = await coordinator.start_saga("saga1", "wf1")
        
        assert state.saga_id == "saga1"
        assert state.workflow_id == "wf1"
        assert len(state.completed_tasks) == 0
        assert state.compensation_tasks == []

    @pytest.mark.asyncio
    async def test_record_task_completion(self, coordinator):
        """Test recording task completion."""
        await coordinator.start_saga("saga1", "wf1")
        
        await coordinator.record_task_completion("saga1", "task1")
        await coordinator.record_task_completion("saga1", "task2")
        
        state = await coordinator.get_saga_state("saga1")
        
        assert len(state.completed_tasks) == 2
        assert "task1" in state.completed_tasks
        assert "task2" in state.completed_tasks

    @pytest.mark.asyncio
    async def test_fail_saga_creates_compensations(self, coordinator):
        """Test that failing saga creates compensation tasks."""
        await coordinator.start_saga("saga1", "wf1")
        
        await coordinator.record_task_completion("saga1", "task1")
        await coordinator.record_task_completion("saga1", "task2")
        
        tasks = await coordinator.fail_saga("saga1", "task3")
        
        # Should have 2 compensations (task1 and task2 in reverse)
        assert len(tasks) == 2
        assert tasks[0].original_task_id == "task2"
        assert tasks[1].original_task_id == "task1"

    @pytest.mark.asyncio
    async def test_saga_compensation_order(self, coordinator):
        """Test that compensation runs in reverse order of completion."""
        await coordinator.start_saga("saga1", "wf1")
        
        # Complete tasks in order: A, B, C
        await coordinator.record_task_completion("saga1", "taskA")
        await coordinator.record_task_completion("saga1", "taskB")
        await coordinator.record_task_completion("saga1", "taskC")
        
        tasks = await coordinator.fail_saga("saga1", "taskD")
        
        # Should be reversed: C, B, A
        assert tasks[0].original_task_id == "taskC"
        assert tasks[1].original_task_id == "taskB"
        assert tasks[2].original_task_id == "taskA"

    @pytest.mark.asyncio
    async def test_execute_compensation_success(self, coordinator):
        """Test successful compensation execution."""
        await coordinator.start_saga("saga1", "wf1")
        await coordinator.record_task_completion("saga1", "task1")
        
        comp_task = CompensationTask(
            task_id="comp_task1",
            original_task_id="task1",
            original_input={"id": 1},
            original_output={"result": "ok"},
            max_retries=3,
        )
        
        async def compensation_fn(input, output):
            return {"rolled_back": True}
        
        success = await coordinator.execute_compensation("saga1", comp_task, compensation_fn)
        
        assert success is True
        assert comp_task.status == CompensationStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_compensation_failure(self, coordinator):
        """Test compensation execution with failure."""
        await coordinator.start_saga("saga1", "wf1")
        await coordinator.record_task_completion("saga1", "task1")
        
        comp_task = CompensationTask(
            task_id="comp_task1",
            original_task_id="task1",
            original_input={},
            original_output={},
            max_retries=2,
        )
        
        async def failing_compensation(input, output):
            raise RuntimeError("Compensation failed")
        
        success = await coordinator.execute_compensation("saga1", comp_task, failing_compensation)
        
        assert success is False
        assert comp_task.status == CompensationStatus.FAILED

    @pytest.mark.asyncio
    async def test_compensation_retry_backoff(self, coordinator):
        """Test that failed compensations retry with backoff."""
        await coordinator.start_saga("saga1", "wf1")
        await coordinator.record_task_completion("saga1", "task1")
        
        comp_task = CompensationTask(
            task_id="comp_task1",
            original_task_id="task1",
            original_input={},
            original_output={},
            max_retries=3,
        )
        
        call_times = []
        
        async def flaky_compensation(input, output):
            call_times.append(asyncio.get_event_loop().time())
            if len(call_times) < 3:
                raise RuntimeError("Temporary failure")
            return {"success": True}
        
        success = await coordinator.execute_compensation("saga1", comp_task, flaky_compensation)
        
        # Should have retried until success
        assert success is True
        assert comp_task.retry_count == 2  # Failed twice before success

    @pytest.mark.asyncio
    async def test_compensation_dead_letter(self, coordinator):
        """Test that retries exhausted goes to dead letter queue."""
        await coordinator.start_saga("saga1", "wf1")
        await coordinator.record_task_completion("saga1", "task1")
        
        comp_task = CompensationTask(
            task_id="comp_task1",
            original_task_id="task1",
            original_input={},
            original_output={},
            max_retries=2,  # Only 2 retries
        )
        
        async def always_fails(input, output):
            raise RuntimeError("Permanent failure")
        
        success = await coordinator.execute_compensation("saga1", comp_task, always_fails)
        
        assert success is False
        assert comp_task.status == CompensationStatus.FAILED
        
        # Check dead letter queue
        dlq_entries = await coordinator._dlq.get_by_saga("saga1")
        
        assert len(dlq_entries) == 1
        assert dlq_entries[0].reason == DeadLetterReason.MAX_RETRIES_EXCEEDED

    @pytest.mark.asyncio
    async def test_compensate_saga_full_flow(self, coordinator):
        """Test full saga compensation flow."""
        await coordinator.start_saga("saga1", "wf1")
        await coordinator.record_task_completion("saga1", "task1")
        await coordinator.record_task_completion("saga1", "task2")
        
        compensation_registry = {
            "task1": lambda in_, out: {"comp1": True},
            "task2": lambda in_, out: {"comp2": True},
        }
        
        all_succeeded, failed = await coordinator.compensate_saga(
            "saga1", compensation_registry
        )
        
        assert all_succeeded is True
        assert len(failed) == 0

    @pytest.mark.asyncio
    async def test_compensate_saga_partial_failure(self, coordinator):
        """Test saga compensation with some failures."""
        await coordinator.start_saga("saga1", "wf1")
        await coordinator.record_task_completion("saga1", "task1")
        await coordinator.record_task_completion("saga1", "task2")
        
        # Create compensation tasks first
        await coordinator.fail_saga("saga1", "task3")
        
        async def failing_compensation(in_, out):
            raise RuntimeError("Failed")

        compensation_registry = {
            "task1": lambda in_, out: {"comp1": True},
            "task2": failing_compensation,
        }

        all_succeeded, failed = await coordinator.compensate_saga(
            "saga1", compensation_registry
        )

        assert all_succeeded is False
        assert "task2" in failed

    @pytest.mark.asyncio
    async def test_abort_saga(self, coordinator):
        """Test aborting a saga."""
        await coordinator.start_saga("saga1", "wf1")
        await coordinator.record_task_completion("saga1", "task1")
        
        await coordinator.abort_saga("saga1")
        
        state = await coordinator.get_saga_state("saga1")
        
        assert state.compensation_complete is True


# ============================================================================
# Dead Letter Queue Tests
# ============================================================================

class TestDeadLetterQueue:
    """Test dead letter queue."""

    @pytest.fixture
    def dlq(self):
        """Create dead letter queue."""
        return DeadLetterQueue()

    @pytest.mark.asyncio
    async def test_add_to_dlq(self, dlq):
        """Test adding entry to DLQ."""
        task = CompensationTask(
            task_id="comp_task1",
            original_task_id="task1",
            original_input={},
            original_output={},
        )
        
        entry = await dlq.add("saga1", task, DeadLetterReason.MAX_RETRIES_EXCEEDED)
        
        assert entry.saga_id == "saga1"
        assert entry.task.original_task_id == "task1"
        assert entry.reason == DeadLetterReason.MAX_RETRIES_EXCEEDED

    @pytest.mark.asyncio
    async def test_get_dlq_entry(self, dlq):
        """Test getting DLQ entry by ID."""
        task = CompensationTask(
            task_id="comp_task1",
            original_task_id="task1",
            original_input={},
            original_output={},
        )
        
        added = await dlq.add("saga1", task, DeadLetterReason.MAX_RETRIES_EXCEEDED)
        retrieved = await dlq.get(added.entry_id)
        
        assert retrieved is not None
        assert retrieved.entry_id == added.entry_id

    @pytest.mark.asyncio
    async def test_get_by_saga(self, dlq):
        """Test getting all DLQ entries for a saga."""
        for i in range(3):
            task = CompensationTask(
                task_id=f"comp_task{i}",
                original_task_id=f"task{i}",
                original_input={},
                original_output={},
            )
            await dlq.add("saga1", task, DeadLetterReason.MAX_RETRIES_EXCEEDED)
        
        entries = await dlq.get_by_saga("saga1")
        
        assert len(entries) == 3

    @pytest.mark.asyncio
    async def test_get_unresolved(self, dlq):
        """Test getting unresolved entries."""
        task1 = CompensationTask(task_id="c1", original_task_id="t1", original_input={}, original_output={})
        task2 = CompensationTask(task_id="c2", original_task_id="t2", original_input={}, original_output={})
        
        await dlq.add("saga1", task1, DeadLetterReason.MAX_RETRIES_EXCEEDED)
        await dlq.add("saga1", task2, DeadLetterReason.MAX_RETRIES_EXCEEDED)
        
        # Resolve one
        entries = await dlq.get_by_saga("saga1")
        await dlq.resolve(entries[0].entry_id, "manually resolved")
        
        unresolved = await dlq.get_unresolved()
        
        assert len(unresolved) == 1

    @pytest.mark.asyncio
    async def test_resolve_entry(self, dlq):
        """Test resolving a DLQ entry."""
        task = CompensationTask(
            task_id="comp_task1",
            original_task_id="task1",
            original_input={},
            original_output={},
        )
        
        entry = await dlq.add("saga1", task, DeadLetterReason.MAX_RETRIES_EXCEEDED)
        
        resolved = await dlq.resolve(entry.entry_id, "Fixed manually")
        
        assert resolved is True
        
        updated = await dlq.get(entry.entry_id)
        assert updated.resolved is True
        assert updated.resolution == "Fixed manually"

    @pytest.mark.asyncio
    async def test_retry_entry(self, dlq):
        """Test retrying a DLQ entry."""
        task = CompensationTask(
            task_id="comp_task1",
            original_task_id="task1",
            original_input={},
            original_output={},
        )
        
        entry = await dlq.add("saga1", task, DeadLetterReason.MAX_RETRIES_EXCEEDED)
        
        assert entry.retry_count == 0
        
        retried = await dlq.retry(entry.entry_id)
        
        assert retried is True
        
        updated = await dlq.get(entry.entry_id)
        assert updated.retry_count == 1

    @pytest.mark.asyncio
    async def test_discard_entry(self, dlq):
        """Test discarding a DLQ entry."""
        task = CompensationTask(
            task_id="comp_task1",
            original_task_id="task1",
            original_input={},
            original_output={},
        )
        
        entry = await dlq.add("saga1", task, DeadLetterReason.MAX_RETRIES_EXCEEDED)
        
        discarded = await dlq.discard(entry.entry_id)
        
        assert discarded is True
        
        updated = await dlq.get(entry.entry_id)
        assert updated.resolved is True
        assert updated.resolution == "discarded"


# ============================================================================
# Compensation Manager Tests
# ============================================================================

class TestCompensationManager:
    """Test compensation manager."""

    @pytest.mark.asyncio
    async def test_handle_activity_failure(self):
        """Test handling activity failure."""
        dlq = DeadLetterQueue()
        config = CompensationConfig(max_attempts=3)
        coordinator = SagaCoordinator(dlq, config)
        manager = CompensationManager(coordinator, dlq)
        
        await coordinator.start_saga("saga_wf1", "wf1")
        await coordinator.record_task_completion("saga_wf1", "task1")
        
        await manager.handle_activity_failure("wf1", "failed_task", "Task failed")
        
        state = await coordinator.get_saga_state("saga_wf1")
        assert state.failed_task_id == "failed_task"

    @pytest.mark.asyncio
    async def test_run_compensation(self):
        """Test running compensation."""
        dlq = DeadLetterQueue()
        config = CompensationConfig(max_attempts=3)
        coordinator = SagaCoordinator(dlq, config)
        manager = CompensationManager(coordinator, dlq)
        
        await coordinator.start_saga("saga_wf1", "wf1")
        await coordinator.record_task_completion("saga_wf1", "task1")
        
        registry = {"task1": lambda in_, out: {"rolled_back": True}}
        
        success, failed = await manager.run_compensation("wf1", registry)
        
        assert success is True


# ============================================================================
# Retry Policy Tests
# ============================================================================

class TestRetryPolicies:
    """Test different retry policies."""

    @pytest.mark.asyncio
    async def test_exponential_backoff(self):
        """Test exponential backoff calculation."""
        dlq = DeadLetterQueue()
        config = CompensationConfig(
            max_attempts=5,
            initial_delay_seconds=1.0,
            backoff_multiplier=2.0,
            retry_policy=CompensationRetryPolicy.EXPONENTIAL,
        )
        coordinator = SagaCoordinator(dlq, config)
        
        # Check delay calculation
        delays = []
        for i in range(1, 4):
            delay = coordinator._calculate_delay(i)
            delays.append(delay)
        
        # Exponential: 1s, 2s, 4s
        assert delays[0] == 1.0
        assert delays[1] == 2.0
        assert delays[2] == 4.0

    @pytest.mark.asyncio
    async def test_linear_backoff(self):
        """Test linear backoff calculation."""
        dlq = DeadLetterQueue()
        config = CompensationConfig(
            max_attempts=5,
            initial_delay_seconds=1.0,
            retry_policy=CompensationRetryPolicy.LINEAR,
        )
        coordinator = SagaCoordinator(dlq, config)
        
        delays = [coordinator._calculate_delay(i) for i in range(1, 4)]
        
        # Linear: 1s, 2s, 3s
        assert delays[0] == 1.0
        assert delays[1] == 2.0
        assert delays[2] == 3.0

    @pytest.mark.asyncio
    async def test_fixed_backoff(self):
        """Test fixed backoff calculation."""
        dlq = DeadLetterQueue()
        config = CompensationConfig(
            max_attempts=5,
            initial_delay_seconds=2.0,
            retry_policy=CompensationRetryPolicy.FIXED,
        )
        coordinator = SagaCoordinator(dlq, config)
        
        delays = [coordinator._calculate_delay(i) for i in range(1, 4)]
        
        # Fixed: 2s, 2s, 2s
        assert all(d == 2.0 for d in delays)

    @pytest.mark.asyncio
    async def test_max_delay_cap(self):
        """Test that delay is capped at max_delay_seconds."""
        dlq = DeadLetterQueue()
        config = CompensationConfig(
            max_attempts=10,
            initial_delay_seconds=1.0,
            backoff_multiplier=10.0,
            max_delay_seconds=5.0,
            retry_policy=CompensationRetryPolicy.EXPONENTIAL,
        )
        coordinator = SagaCoordinator(dlq, config)
        
        # At retry 10, would be 1 * 10^9 = huge, but should be capped at 5
        delay = coordinator._calculate_delay(10)
        
        assert delay == 5.0
