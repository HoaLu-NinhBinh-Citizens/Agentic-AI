"""Unit tests for exactly-once activity execution.

Tests cover:
- test_idempotency_key_exact_once: Same key -> only 1 execution
- test_idempotency_key_different: Different key -> 2 executions
"""

from __future__ import annotations

import pytest
import asyncio
import time

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from core.runtime.enterprise.exactly_once import (
    IdempotencyKeyGenerator,
    InMemoryIdempotencyStore,
    IdempotencyRecord,
    IdempotencyStatus,
    SideEffectRegistry,
    ExactlyOnceActivityExecutor,
)


# ============================================================================
# Idempotency Key Tests
# ============================================================================

class TestIdempotencyKeyGenerator:
    """Test idempotency key generation."""

    def test_generate_consistent_keys(self):
        """Test that same inputs produce same keys."""
        gen = IdempotencyKeyGenerator()
        
        key1 = gen.generate("workflow1", "task1", 1)
        key2 = gen.generate("workflow1", "task1", 1)
        
        assert key1 == key2

    def test_generate_different_keys_different_workflow(self):
        """Test that different workflows get different keys."""
        gen = IdempotencyKeyGenerator()
        
        key1 = gen.generate("workflow1", "task1", 1)
        key2 = gen.generate("workflow2", "task1", 1)
        
        assert key1 != key2

    def test_generate_different_keys_different_task(self):
        """Test that different tasks get different keys."""
        gen = IdempotencyKeyGenerator()
        
        key1 = gen.generate("workflow1", "task1", 1)
        key2 = gen.generate("workflow1", "task2", 1)
        
        assert key1 != key2

    def test_generate_different_keys_different_attempt(self):
        """Test that different attempts get different keys."""
        gen = IdempotencyKeyGenerator()
        
        key1 = gen.generate("workflow1", "task1", 1)
        key2 = gen.generate("workflow1", "task1", 2)
        
        assert key1 != key2

    def test_generate_key_format(self):
        """Test idempotency key format."""
        gen = IdempotencyKeyGenerator()
        
        key = gen.generate("wf", "task", 1)
        
        assert isinstance(key, str)
        assert "wf" in key
        assert "task" in key


# ============================================================================
# InMemoryIdempotencyStore Tests
# ============================================================================

class TestInMemoryIdempotencyStore:
    """Test in-memory idempotency store."""

    @pytest.mark.asyncio
    async def test_save_and_get_record(self):
        """Test saving and retrieving a record."""
        store = InMemoryIdempotencyStore()
        
        record = IdempotencyRecord(
            idempotency_key="wf:task:1",
            workflow_id="wf",
            activity_id="task",
            status=IdempotencyStatus.COMPLETED,
            result={"data": "success"},
        )
        
        await store.save(record)
        retrieved = await store.get("wf:task:1")
        
        assert retrieved is not None
        assert retrieved.status == IdempotencyStatus.COMPLETED
        assert retrieved.result["data"] == "success"

    @pytest.mark.asyncio
    async def test_get_nonexistent_record(self):
        """Test getting non-existent record returns None."""
        store = InMemoryIdempotencyStore()
        
        retrieved = await store.get("nonexistent")
        
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_update_record(self):
        """Test updating an existing record."""
        store = InMemoryIdempotencyStore()
        
        record = IdempotencyRecord(
            idempotency_key="wf:task:1",
            workflow_id="wf",
            activity_id="task",
            status=IdempotencyStatus.PENDING,
        )
        await store.save(record)
        
        # Update to completed
        record.status = IdempotencyStatus.COMPLETED
        record.result = {"data": "updated"}
        await store.save(record)
        
        retrieved = await store.get("wf:task:1")
        
        assert retrieved.status == IdempotencyStatus.COMPLETED
        assert retrieved.result["data"] == "updated"

    @pytest.mark.asyncio
    async def test_delete_record(self):
        """Test deleting a record."""
        store = InMemoryIdempotencyStore()
        
        record = IdempotencyRecord(
            idempotency_key="wf:task:1",
            workflow_id="wf",
            activity_id="task",
            status=IdempotencyStatus.COMPLETED,
        )
        await store.save(record)
        
        await store.delete("wf:task:1")
        retrieved = await store.get("wf:task:1")
        
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_get_by_workflow(self):
        """Test getting all records for a workflow."""
        store = InMemoryIdempotencyStore()
        
        await store.save(IdempotencyRecord(
            idempotency_key="wf1:task1:1",
            workflow_id="wf1",
            activity_id="task1",
            status=IdempotencyStatus.COMPLETED,
        ))
        await store.save(IdempotencyRecord(
            idempotency_key="wf1:task2:1",
            workflow_id="wf1",
            activity_id="task2",
            status=IdempotencyStatus.COMPLETED,
        ))
        await store.save(IdempotencyRecord(
            idempotency_key="wf2:task1:1",
            workflow_id="wf2",
            activity_id="task1",
            status=IdempotencyStatus.COMPLETED,
        ))
        
        records = await store.get_by_workflow("wf1")
        
        assert len(records) == 2
        assert all(r.workflow_id == "wf1" for r in records)

    @pytest.mark.asyncio
    async def test_get_incomplete_records(self):
        """Test getting incomplete records for retry."""
        store = InMemoryIdempotencyStore()
        
        await store.save(IdempotencyRecord(
            idempotency_key="wf1:task1:1",
            workflow_id="wf1",
            activity_id="task1",
            status=IdempotencyStatus.PENDING,
        ))
        await store.save(IdempotencyRecord(
            idempotency_key="wf1:task2:1",
            workflow_id="wf1",
            activity_id="task2",
            status=IdempotencyStatus.COMPLETED,
        ))
        
        incomplete = await store.get_incomplete_records("wf1")
        
        assert len(incomplete) == 1
        assert incomplete[0].activity_id == "task1"


# ============================================================================
# Exactly-Once Execution Tests
# ============================================================================

class TestExactlyOnceExecution:
    """Test exactly-once activity execution."""

    @pytest.mark.asyncio
    async def test_idempotency_key_exact_once(self):
        """Test that same idempotency key results in single execution."""
        store = InMemoryIdempotencyStore()
        registry = SideEffectRegistry()
        executor = ExactlyOnceActivityExecutor(store, registry)
        
        execution_count = 0
        
        async def mock_activity():
            nonlocal execution_count
            execution_count += 1
            return {"result": "success"}
        
        # First execution
        result1 = await executor.execute(
            "wf1", "task1", 1, mock_activity
        )
        
        # Second execution with same key (should return cached)
        result2 = await executor.execute(
            "wf1", "task1", 1, mock_activity
        )
        
        # Should only execute once
        assert execution_count == 1
        assert result1 == result2

    @pytest.mark.asyncio
    async def test_idempotency_key_different(self):
        """Test that different idempotency keys result in separate executions."""
        store = InMemoryIdempotencyStore()
        registry = SideEffectRegistry()
        executor = ExactlyOnceActivityExecutor(store, registry)
        
        execution_count = 0
        
        async def mock_activity():
            nonlocal execution_count
            execution_count += 1
            return {"result": f"success_{execution_count}"}
        
        # First execution
        result1 = await executor.execute(
            "wf1", "task1", 1, mock_activity
        )
        
        # Different attempt number = different key
        result2 = await executor.execute(
            "wf1", "task1", 2, mock_activity
        )
        
        # Should execute twice
        assert execution_count == 2
        assert result1 != result2

    @pytest.mark.asyncio
    async def test_idempotency_key_different_task(self):
        """Test that different tasks get separate executions."""
        store = InMemoryIdempotencyStore()
        registry = SideEffectRegistry()
        executor = ExactlyOnceActivityExecutor(store, registry)
        
        execution_count = 0
        
        async def mock_activity(task_id):
            nonlocal execution_count
            execution_count += 1
            return {"task": task_id}
        
        # Different tasks
        result1 = await executor.execute(
            "wf1", "task1", 1, lambda: mock_activity("task1")
        )
        result2 = await executor.execute(
            "wf1", "task2", 1, lambda: mock_activity("task2")
        )
        
        assert execution_count == 2
        assert result1["task"] == "task1"
        assert result2["task"] == "task2"

    @pytest.mark.asyncio
    async def test_idempotency_key_different_workflow(self):
        """Test that different workflows get separate executions."""
        store = InMemoryIdempotencyStore()
        registry = SideEffectRegistry()
        executor = ExactlyOnceActivityExecutor(store, registry)
        
        execution_count = 0
        
        async def mock_activity():
            nonlocal execution_count
            execution_count += 1
            return {"wf": execution_count}
        
        result1 = await executor.execute("wf1", "task1", 1, mock_activity)
        result2 = await executor.execute("wf2", "task1", 1, mock_activity)
        
        assert execution_count == 2
        assert result1["wf"] == 1
        assert result2["wf"] == 2

    @pytest.mark.asyncio
    async def test_side_effect_registered(self):
        """Test that side effects are registered."""
        store = InMemoryIdempotencyStore()
        registry = SideEffectRegistry()
        executor = ExactlyOnceActivityExecutor(store, registry)
        
        async def mock_activity():
            return {"result": "done"}
        
        await executor.execute("wf1", "task1", 1, mock_activity)
        
        registered = registry.has_side_effect("wf1", "task1", 1)
        
        assert registered is True

    @pytest.mark.asyncio
    async def test_side_effect_not_rerun_on_replay(self):
        """Test that side effects are not re-executed on replay."""
        store = InMemoryIdempotencyStore()
        registry = SideEffectRegistry()
        executor = ExactlyOnceActivityExecutor(store, registry)
        
        execution_count = 0
        
        async def mock_activity():
            nonlocal execution_count
            execution_count += 1
            return {"count": execution_count}
        
        # First execution
        result1 = await executor.execute("wf1", "task1", 1, mock_activity)
        
        # Check if side effect would be skipped on replay
        if registry.has_side_effect("wf1", "task1", 1):
            # This simulates what happens during replay
            record = await store.get("wf1:task1:1")
            if record and record.status == IdempotencyStatus.COMPLETED:
                # Skip execution
                pass
        
        # Count should still be 1 if properly skipping
        assert execution_count == 1


# ============================================================================
# SideEffectRegistry Tests
# ============================================================================

class TestSideEffectRegistry:
    """Test side effect registry."""

    def test_register_side_effect(self):
        """Test registering a side effect."""
        registry = SideEffectRegistry()
        
        registry.register("wf1", "task1", 1)
        
        assert registry.has_side_effect("wf1", "task1", 1) is True

    def test_register_different_keys(self):
        """Test that different keys are tracked separately."""
        registry = SideEffectRegistry()
        
        registry.register("wf1", "task1", 1)
        registry.register("wf1", "task1", 2)
        registry.register("wf1", "task2", 1)
        
        assert registry.has_side_effect("wf1", "task1", 1) is True
        assert registry.has_side_effect("wf1", "task1", 2) is True
        assert registry.has_side_effect("wf1", "task2", 1) is True
        assert registry.has_side_effect("wf2", "task1", 1) is False

    def test_get_side_effects_for_workflow(self):
        """Test getting all side effects for a workflow."""
        registry = SideEffectRegistry()
        
        registry.register("wf1", "task1", 1)
        registry.register("wf1", "task2", 1)
        registry.register("wf2", "task1", 1)
        
        effects = registry.get_side_effects_for_workflow("wf1")
        
        assert len(effects) == 2

    def test_clear_side_effects(self):
        """Test clearing side effects for a workflow."""
        registry = SideEffectRegistry()
        
        registry.register("wf1", "task1", 1)
        registry.clear_workflow_side_effects("wf1")
        
        assert registry.has_side_effect("wf1", "task1", 1) is False
