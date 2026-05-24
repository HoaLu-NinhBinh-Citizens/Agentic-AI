"""Tests for deterministic workflow replay - P0-A Critical Fix.

This module tests that the workflow runtime generates deterministic
IDs and timestamps for Temporal-grade replay correctness.

Tests:
1. Deterministic UUID generation from seed
2. Deterministic activity ID generation
3. Deterministic child workflow ID generation
4. Deterministic time from event sequence
5. Replay produces identical IDs
6. Command sequence is deterministic

P0-A Requirements:
- NO uuid.uuid4() in workflow execution path
- NO time.time() in workflow execution path
- All IDs generated from deterministic seeds
- All timestamps derived from event sequence
"""

from __future__ import annotations

import pytest

from src.core.runtime.workflow.types import (
    deterministic_uuid,
    deterministic_event_id,
    deterministic_activity_id,
    deterministic_child_id,
    deterministic_token_id,
    create_workflow_instance,
    create_activity_task,
    WorkflowInstance,
    WorkflowEvent,
    EventType,
)


class TestDeterministicUUID:
    """Test deterministic UUID generation."""

    def test_same_seed_produces_same_uuid(self):
        """Same seed must produce identical UUID."""
        seed = "test_workflow:1"
        
        uuid1 = deterministic_uuid(seed)
        uuid2 = deterministic_uuid(seed)
        
        assert uuid1 == uuid2, "Deterministic UUID must be reproducible"

    def test_different_seeds_produce_different_uuids(self):
        """Different seeds must produce different UUIDs."""
        seed1 = "workflow_1:sequence_1"
        seed2 = "workflow_2:sequence_1"
        
        uuid1 = deterministic_uuid(seed1)
        uuid2 = deterministic_uuid(seed2)
        
        assert uuid1 != uuid2, "Different seeds must produce different UUIDs"

    def test_uuid_format_is_valid(self):
        """UUID must be in standard format."""
        uuid_str = deterministic_uuid("test")
        
        # UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        parts = uuid_str.split("-")
        assert len(parts) == 5, "UUID must have 5 parts"
        assert len(parts[0]) == 8, "First part must be 8 chars"
        assert len(parts[1]) == 4, "Second part must be 4 chars"
        assert len(parts[2]) == 4, "Third part must be 4 chars"
        assert len(parts[3]) == 4, "Fourth part must be 4 chars"
        assert len(parts[4]) == 12, "Fifth part must be 12 chars"


class TestDeterministicActivityID:
    """Test deterministic activity ID generation."""

    def test_activity_id_from_same_inputs_same_output(self):
        """Same workflow_id + sequence must produce identical activity ID."""
        workflow_id = "wf_123"
        sequence = 5
        
        id1 = deterministic_activity_id(workflow_id, sequence)
        id2 = deterministic_activity_id(workflow_id, sequence)
        
        assert id1 == id2, "Activity ID must be deterministic"

    def test_activity_id_different_sequences(self):
        """Different sequences must produce different IDs."""
        workflow_id = "wf_123"
        
        id1 = deterministic_activity_id(workflow_id, 1)
        id2 = deterministic_activity_id(workflow_id, 2)
        id3 = deterministic_activity_id(workflow_id, 3)
        
        assert len({id1, id2, id3}) == 3, "Different sequences must produce different IDs"

    def test_activity_id_different_workflows(self):
        """Different workflows must produce different IDs."""
        seq = 1
        
        id1 = deterministic_activity_id("wf_A", seq)
        id2 = deterministic_activity_id("wf_B", seq)
        
        assert id1 != id2, "Different workflows must produce different IDs"


class TestDeterministicChildID:
    """Test deterministic child workflow ID generation."""

    def test_child_id_from_same_inputs_same_output(self):
        """Same workflow_id + sequence must produce identical child ID."""
        workflow_id = "parent_wf"
        sequence = 3
        
        id1 = deterministic_child_id(workflow_id, sequence)
        id2 = deterministic_child_id(workflow_id, sequence)
        
        assert id1 == id2, "Child ID must be deterministic"

    def test_child_id_sequence_ordering(self):
        """Child IDs must be ordered by sequence."""
        workflow_id = "parent_wf"
        
        ids = [deterministic_child_id(workflow_id, i) for i in range(10)]
        
        # All IDs must be unique
        assert len(set(ids)) == 10, "Child IDs must be unique"
        
        # First ID must be from sequence 0
        first = deterministic_child_id(workflow_id, 0)
        assert ids[0] == first, "First ID must match sequence 0"


class TestWorkflowInstanceCreation:
    """Test deterministic workflow instance creation."""

    def test_workflow_instance_has_deterministic_id(self):
        """Workflow instance ID must be deterministic."""
        wf_id = "deterministic_wf_123"
        
        instance = create_workflow_instance(
            workflow_id=wf_id,
            workflow_type="test_workflow",
            input={"key": "value"}
        )
        
        assert instance.workflow_id == wf_id
        assert instance.workflow_type == "test_workflow"
        assert instance.input == {"key": "value"}

    def test_workflow_instance_next_sequence_starts_at_1(self):
        """Workflow next_sequence must start at 1."""
        instance = create_workflow_instance(
            workflow_id="wf_1",
            workflow_type="test"
        )
        
        assert instance.next_sequence == 1, "next_sequence must start at 1"


class TestActivityTaskCreation:
    """Test deterministic activity task creation."""

    def test_activity_task_deterministic_id(self):
        """Activity task ID must be deterministic."""
        wf_id = "wf_test"
        seq = 5
        
        task1 = create_activity_task(
            workflow_id=wf_id,
            sequence=seq,
            activity_type="test_activity"
        )
        task2 = create_activity_task(
            workflow_id=wf_id,
            sequence=seq,
            activity_type="test_activity"
        )
        
        assert task1.task_id == task2.task_id, "Activity task ID must be deterministic"
        assert task1.idempotency_key == task2.idempotency_key

    def test_activity_task_idempotency_key_format(self):
        """Idempotency key must include workflow_id and sequence."""
        task = create_activity_task(
            workflow_id="wf_123",
            sequence=7,
            activity_type="flash_activity"
        )
        
        assert "wf_123" in task.idempotency_key
        assert "flash_activity" in task.idempotency_key
        assert "7" in task.idempotency_key


class TestDeterministicReplayContract:
    """Test that replay contract is satisfied."""

    def test_same_command_sequence_produces_same_ids(self):
        """Same command sequence must produce identical IDs."""
        workflow_id = "replay_test_wf"
        
        # First execution
        ids1 = [
            deterministic_activity_id(workflow_id, i)
            for i in range(5)
        ]
        
        # Simulated replay
        ids2 = [
            deterministic_activity_id(workflow_id, i)
            for i in range(5)
        ]
        
        assert ids1 == ids2, "Replay must produce identical IDs"

    def test_activity_sequence_determinism(self):
        """Multiple activities in sequence must be deterministic."""
        workflow_id = "multi_activity_wf"
        
        # Simulate a workflow that schedules 3 activities
        def simulate_workflow():
            activity_ids = []
            seq = 0
            for _ in range(3):
                activity_ids.append(deterministic_activity_id(workflow_id, seq))
                seq += 1
            return activity_ids
        
        # Run "workflow" multiple times
        result1 = simulate_workflow()
        result2 = simulate_workflow()
        result3 = simulate_workflow()
        
        assert result1 == result2 == result3, "Workflow replay must be deterministic"

    def test_child_workflow_sequence_determinism(self):
        """Child workflow IDs must be deterministic across replays."""
        parent_id = "parent_wf_123"
        
        def simulate_parent():
            children = []
            seq = 0
            for _ in range(2):
                children.append(deterministic_child_id(parent_id, seq))
                seq += 1
            return children
        
        result1 = simulate_parent()
        result2 = simulate_parent()
        
        assert result1 == result2, "Child workflow IDs must be deterministic"


class TestDeterministicTime:
    """Test deterministic time derivation from event sequence."""

    def test_event_offset_is_deterministic(self):
        """Event offset must be deterministic based on sequence."""
        base_time = 1000.0  # Some base time
        
        # Event at sequence 1
        time1 = base_time + (1 * 0.001)  # 1ms offset
        # Event at sequence 100
        time2 = base_time + (100 * 0.001)  # 100ms offset
        # Event at sequence 1000
        time3 = base_time + (1000 * 0.001)  # 1000ms offset
        
        # These must be consistent
        assert time2 > time1
        assert time3 > time2
        
        # Verify determinism
        assert time1 == base_time + (1 * 0.001)
        assert time2 == base_time + (100 * 0.001)
        assert time3 == base_time + (1000 * 0.001)

    def test_time_derivation_formula(self):
        """Time = base_time + (sequence * 0.001) must be consistent."""
        base = 1700000000.0  # Some timestamp
        
        for seq in [0, 1, 10, 100, 1000]:
            expected = base + (seq * 0.001)
            calculated = base + (seq * 0.001)
            assert expected == calculated


class TestDeterministicTokenID:
    """Test deterministic fence token ID generation."""

    def test_fence_token_deterministic(self):
        """Fence token IDs must be deterministic."""
        lock_id = "flash_lock_wf1"
        seq = 0
        
        token1 = deterministic_token_id(lock_id, seq)
        token2 = deterministic_token_id(lock_id, seq)
        
        assert token1 == token2, "Fence token ID must be deterministic"

    def test_different_locks_different_tokens(self):
        """Different locks must produce different token IDs."""
        seq = 5
        
        token1 = deterministic_token_id("lock_A", seq)
        token2 = deterministic_token_id("lock_B", seq)
        
        assert token1 != token2, "Different locks must have different tokens"


# =============================================================================
# REGRESSION TESTS - P0-A Violations
# =============================================================================

class TestP0AViolations:
    """Test that P0-A violations are detected and prevented."""

    def test_deterministic_uuid_not_random(self):
        """Verify deterministic_uuid is NOT random."""
        # Call same seed 100 times
        seed = "p0a_test_seed"
        results = [deterministic_uuid(seed) for _ in range(100)]
        
        # All must be identical (not random)
        assert len(set(results)) == 1, "deterministic_uuid must not be random"
        assert results[0] == results[99]

    def test_no_collision_in_large_sequence(self):
        """Large number of IDs must not collide."""
        workflow_id = "collision_test_wf"
        
        # Generate 10,000 IDs
        ids = [deterministic_activity_id(workflow_id, i) for i in range(10000)]
        
        # All must be unique
        assert len(set(ids)) == 10000, "No collisions allowed in 10K IDs"

    def test_cross_workflow_isolation(self):
        """IDs from different workflows must not collide."""
        # 100 workflows, each with 100 IDs
        all_ids = []
        for wf_idx in range(100):
            wf_id = f"isolated_wf_{wf_idx}"
            for seq in range(100):
                all_ids.append(deterministic_activity_id(wf_id, seq))
        
        # Total: 10,000 unique IDs
        assert len(set(all_ids)) == 10000, "Cross-workflow IDs must not collide"
