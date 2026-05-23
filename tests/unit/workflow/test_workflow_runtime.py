"""Tests for Workflow Runtime - Phase 5A."""

import pytest
import asyncio
from typing import Any

# Import the workflow modules
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from src.core.runtime.workflow.types import (
    WorkflowInstance,
    WorkflowStatus,
    ActivityTask,
    ActivityStatus,
    Compensation,
    CompensationStatus,
    Signal,
    ParentClosePolicy,
    LockFenceToken,
)
from src.core.runtime.workflow.compensation import (
    CompensationStateMachine,
    InMemoryCompensationStore,
)
from src.core.runtime.workflow.signal_manager import (
    SignalManager,
    InMemorySignalStore,
)
from src.core.runtime.workflow.child_workflow import (
    ChildWorkflowManager,
    InMemoryChildWorkflowStore,
)
from src.core.runtime.workflow.lock_manager import LockManager
from src.core.runtime.workflow.fair_scheduler import FairScheduler
from src.core.runtime.workflow.admission_controller import (
    AdmissionController,
    ResourceLimits,
)


class TestCompensationStateMachine:
    """Tests for Saga compensation state machine."""

    @pytest.fixture
    async def compensation_store(self):
        return InMemoryCompensationStore()

    @pytest.fixture
    async def state_machine(self, compensation_store):
        return CompensationStateMachine(compensation_store)

    @pytest.mark.asyncio
    async def test_schedule_compensation(self, state_machine):
        """Test scheduling a compensation."""
        compensation_id = await state_machine.schedule_compensation(
            step_id="step_1",
            activity_name="transfer_funds",
            original_input={"from": "A", "to": "B", "amount": 100},
            original_output={"txn_id": "123"},
        )

        assert compensation_id is not None
        compensation = await state_machine._store.get(compensation_id)
        assert compensation.status == CompensationStatus.PENDING
        assert compensation.activity_name == "transfer_funds"

    @pytest.mark.asyncio
    async def test_compensation_idempotent(self, state_machine, compensation_store):
        """Test compensation execution is idempotent."""
        # Register compensation handler
        async def compensate(input, output):
            return {"reversed": True}

        state_machine.register_compensation("transfer_funds", compensate)

        # Schedule compensation
        compensation_id = await state_machine.schedule_compensation(
            step_id="step_1",
            activity_name="transfer_funds",
            original_input={"from": "A", "to": "B", "amount": 100},
            original_output={"txn_id": "123"},
        )

        # Execute multiple times - should be idempotent
        result1 = await state_machine.execute_compensation(compensation_id)
        result2 = await state_machine.execute_compensation(compensation_id)
        result3 = await state_machine.execute_compensation(compensation_id)

        assert result1 is True
        assert result2 is True  # Already completed
        assert result3 is True  # Already completed

        compensation = await compensation_store.get(compensation_id)
        assert compensation.status == CompensationStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_compensation_retry_on_failure(self, state_machine):
        """Test compensation retry on failure."""
        attempt_count = 0

        async def failing_compensate(input, output):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise Exception("Temporary failure")
            return {"reversed": True}

        state_machine.register_compensation("transfer_funds", failing_compensate)

        compensation_id = await state_machine.schedule_compensation(
            step_id="step_1",
            activity_name="transfer_funds",
            original_input={"from": "A", "to": "B", "amount": 100},
            original_output={"txn_id": "123"},
        )

        # First attempt fails
        result1 = await state_machine.execute_compensation(compensation_id)
        assert result1 is False

        compensation = await state_machine._store.get(compensation_id)
        assert compensation.status == CompensationStatus.FAILED
        assert compensation.retry_count == 1

        # Second attempt succeeds
        result2 = await state_machine.execute_compensation(compensation_id)
        assert result2 is True

        compensation = await state_machine._store.get(compensation_id)
        assert compensation.status == CompensationStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_skip_compensation(self, state_machine):
        """Test skipping a compensation."""
        compensation_id = await state_machine.schedule_compensation(
            step_id="step_1",
            activity_name="transfer_funds",
            original_input={"from": "A", "to": "B", "amount": 100},
            original_output={"txn_id": "123"},
        )

        success = await state_machine.skip_compensation(compensation_id)
        assert success is True

        compensation = await state_machine._store.get(compensation_id)
        assert compensation.status == CompensationStatus.SKIPPED


class TestSignalManager:
    """Tests for signal sequencing."""

    @pytest.fixture
    async def signal_store(self):
        return InMemorySignalStore()

    @pytest.fixture
    async def signal_manager(self, signal_store):
        return SignalManager(signal_store)

    @pytest.mark.asyncio
    async def test_send_and_receive_signal(self, signal_manager):
        """Test sending and receiving a signal."""
        # Send signal
        signal_id = await signal_manager.send_signal(
            workflow_id="wf_123",
            name="update",
            payload={"status": "approved"},
        )

        assert signal_id is not None

        # Get signal history
        signals = await signal_manager.get_signal_history("wf_123", name="update")
        assert len(signals) == 1
        assert signals[0].name == "update"
        assert signals[0].payload == {"status": "approved"}

    @pytest.mark.asyncio
    async def test_signal_sequencing(self, signal_manager):
        """Test signals are sequenced."""
        # Send multiple signals
        await signal_manager.send_signal("wf_123", "event", {"n": 1})
        await signal_manager.send_signal("wf_123", "event", {"n": 2})
        await signal_manager.send_signal("wf_123", "event", {"n": 3})

        signals = await signal_manager.get_signal_history("wf_123", name="event")

        # Check sequence numbers
        assert signals[0].sequence < signals[1].sequence < signals[2].sequence

    @pytest.mark.asyncio
    async def test_register_handler(self, signal_manager):
        """Test registering signal handler."""
        received = []

        async def handler(payload):
            received.append(payload)

        signal_manager.register_handler("notification", handler)

        # Send signal
        await signal_manager.send_signal(
            "wf_123", "notification", {"message": "Hello"}
        )

        # Handler should have been called
        assert len(received) == 1
        assert received[0] == {"message": "Hello"}


class TestChildWorkflowManager:
    """Tests for child workflow management."""

    @pytest.fixture
    async def child_store(self):
        return InMemoryChildWorkflowStore()

    @pytest.fixture
    async def child_manager(self, child_store):
        return ChildWorkflowManager(child_store)

    @pytest.fixture
    async def parent_workflow(self):
        return WorkflowInstance(
            workflow_id="parent_123",
            workflow_type="parent",
            status=WorkflowStatus.RUNNING,
        )

    @pytest.mark.asyncio
    async def test_start_child(self, child_manager, parent_workflow):
        """Test starting a child workflow."""
        child_id = await child_manager.start_child(
            parent=parent_workflow,
            child_workflow_type="approval",
            input={"request": "approval_request"},
            policy=ParentClosePolicy.TERMINATE,
        )

        assert child_id is not None

        child = await child_manager.get_child(child_id)
        assert child is not None
        assert child.workflow_type == "approval"
        assert child.close_policy == ParentClosePolicy.TERMINATE

    @pytest.mark.asyncio
    async def test_child_completion(self, child_manager, parent_workflow):
        """Test child workflow completion."""
        child_id = await child_manager.start_child(
            parent=parent_workflow,
            child_workflow_type="approval",
            input={"request": "test"},
        )

        # Simulate completion
        await child_manager.on_child_complete(child_id, {"approved": True})

        child = await child_manager.get_child(child_id)
        assert child.status == WorkflowStatus.COMPLETED
        assert child.result == {"approved": True}

    @pytest.mark.asyncio
    async def test_idempotent_start(self, child_manager, parent_workflow):
        """Test idempotent child workflow start."""
        idempotency_key = "unique_key_123"

        child_id_1 = await child_manager.start_child(
            parent=parent_workflow,
            child_workflow_type="approval",
            input={"request": "test"},
            idempotency_key=idempotency_key,
        )

        child_id_2 = await child_manager.start_child(
            parent=parent_workflow,
            child_workflow_type="approval",
            input={"request": "test"},
            idempotency_key=idempotency_key,
        )

        # Should return same child ID
        assert child_id_1 == child_id_2


class TestLockManager:
    """Tests for distributed lock with fencing."""

    @pytest.fixture
    async def lock_manager(self):
        return LockManager(
            redis_url=None,  # Use in-memory fallback
            lock_timeout_seconds=10.0,
            fencing_enabled=True,
        )

    @pytest.mark.asyncio
    async def test_acquire_release_lock(self, lock_manager):
        """Test basic lock acquire and release."""
        token = await lock_manager.acquire(
            key="resource_1",
            owner_id="worker_1",
        )

        assert token is not None
        assert token.token is not None
        assert token.lock_id == "resource_1"

        # Release
        released = await lock_manager.release("resource_1", token)
        assert released is True

    @pytest.mark.asyncio
    async def test_fencing_token(self, lock_manager):
        """Test fencing token prevents wrong release."""
        token = await lock_manager.acquire(
            key="resource_1",
            owner_id="worker_1",
        )

        # Create fake token
        fake_token = LockFenceToken(
            token="fake_token",
            lock_id="resource_1",
            owner_id="worker_2",
        )

        # Should not release with wrong token
        released = await lock_manager.release("resource_1", fake_token)
        assert released is False

        # Release with correct token
        released = await lock_manager.release("resource_1", token)
        assert released is True

    @pytest.mark.asyncio
    async def test_lock_extend(self, lock_manager):
        """Test lock extension."""
        token = await lock_manager.acquire(
            key="resource_1",
            owner_id="worker_1",
        )

        original_expiry = token.expires_at

        # Extend
        extended = await lock_manager.extend(
            "resource_1",
            token,
            additional_seconds=5.0,
        )

        assert extended is True
        assert token.expires_at > original_expiry

    @pytest.mark.asyncio
    async def test_concurrent_lock_acquire(self, lock_manager):
        """Test only one worker can acquire lock."""
        token1 = await lock_manager.acquire(
            key="resource_1",
            owner_id="worker_1",
        )

        token2 = await lock_manager.acquire(
            key="resource_1",
            owner_id="worker_2",
        )

        assert token1 is not None
        assert token2 is None  # Lock already held


class TestFairScheduler:
    """Tests for fair scheduling with DRR."""

    @pytest.fixture
    async def scheduler(self):
        return FairScheduler(quantum_ms=100.0)

    @pytest.mark.asyncio
    async def test_add_remove_workflow(self, scheduler):
        """Test adding and removing workflows."""
        added = await scheduler.add_workflow("wf_1", priority=5)
        assert added is True

        assert scheduler.pending_count == 1

        await scheduler.remove_workflow("wf_1")
        assert scheduler.pending_count == 0

    @pytest.mark.asyncio
    async def test_drr_scheduling(self, scheduler):
        """Test Deficit Round Robin scheduling."""
        await scheduler.add_workflow("wf_1", priority=5)
        await scheduler.add_workflow("wf_2", priority=5)
        await scheduler.add_workflow("wf_3", priority=5)

        # Get first workflow
        wf1 = await scheduler.get_next_workflow()
        assert wf1 is not None

        # Record execution
        await scheduler.record_execution(wf1, execution_time_ms=50)

        # Should get same workflow again (deficit > 0)
        wf1_again = await scheduler.get_next_workflow()
        assert wf1_again == wf1

        # Record long execution (deficit depleted)
        await scheduler.record_execution(wf1, execution_time_ms=200)

        # Should get different workflow
        wf2 = await scheduler.get_next_workflow()
        assert wf2 != wf1

    @pytest.mark.asyncio
    async def test_priority_scheduling(self, scheduler):
        """Test priority affects scheduling."""
        await scheduler.add_workflow("wf_low", priority=1)
        await scheduler.add_workflow("wf_high", priority=10)

        # High priority should be scheduled first
        first = await scheduler.get_next_workflow()
        assert first == "wf_high"

    @pytest.mark.asyncio
    async def test_block_unblock(self, scheduler):
        """Test blocking and unblocking workflows."""
        await scheduler.add_workflow("wf_1", priority=5)

        # Block
        await scheduler.block_workflow("wf_1")
        assert scheduler.pending_count == 0

        # Unblock
        await scheduler.unblock_workflow("wf_1")
        assert scheduler.pending_count == 1


class TestAdmissionController:
    """Tests for admission control."""

    @pytest.fixture
    async def controller(self):
        controller = AdmissionController(
            limits=ResourceLimits(
                max_pending_workflows=10,
                max_pending_tasks=50,
                reject_policy="fail",
            )
        )
        yield controller
        # Cleanup after test
        await controller.reset_stats()

    @pytest.mark.asyncio
    async def test_admission_limits(self, controller):
        """Test admission respects limits."""
        await controller.reset_stats()  # Ensure clean state
        # Should allow up to limit
        for i in range(10):
            can_start, reason = await controller.can_start_workflow()
            assert can_start is True

        # Should reject over limit
        can_start, reason = await controller.can_start_workflow()
        assert can_start is False
        assert "Too many" in reason

    @pytest.mark.asyncio
    async def test_complete_decrements_count(self, controller):
        """Test completing decrements pending count."""
        await controller.reset_stats()  # Ensure clean state
        await controller.can_start_workflow()
        await controller.can_start_workflow()

        assert (await controller.get_stats())["usage"]["pending_workflows"] == 2

        await controller.on_workflow_complete("wf_1")

        assert (await controller.get_stats())["usage"]["pending_workflows"] == 1

    @pytest.mark.asyncio
    async def test_backpressure_level(self, controller):
        """Test backpressure calculation."""
        await controller.reset_stats()  # Ensure clean state
        # Add workflows
        for i in range(5):
            await controller.can_start_workflow()

        # Backpressure should be 50%
        level = await controller.get_backpressure_level()
        assert level == 0.5

    @pytest.mark.asyncio
    async def test_stats_tracking(self, controller):
        """Test statistics tracking."""
        await controller.reset_stats()  # Ensure clean state
        
        # Accept up to limit (10)
        for i in range(10):
            can_start, reason = await controller.can_start_workflow()
            assert can_start is True
        
        # Continue sending requests that will be rejected
        for i in range(5):
            can_start, reason = await controller.can_start_workflow()
            assert can_start is False

        stats = await controller.get_stats()

        # Should have accepted exactly 10 (the limit)
        assert stats["stats"]["total_accepted"] == 10
        # Should have rejected exactly 5
        assert stats["stats"]["total_rejected"] == 5
        assert stats["stats"]["rejection_rate"] == 5 / 15


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
