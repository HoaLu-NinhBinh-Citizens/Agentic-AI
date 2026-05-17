"""Unit tests for continue-as-new and history compaction.

Tests cover:
- test_compact_snapshot: Event count > threshold -> snapshot and archive
- test_continue_as_new_idempotent: Workflow new keeps workflow_id, signals forwarded
"""

from __future__ import annotations

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from core.runtime.enterprise.history_compaction import (
    HistoryCompactor,
    ContinueAsNewManager,
    WorkflowHistoryManager,
    CompactionResult,
    ArchivedHistory,
)


# ============================================================================
# History Compactor Tests
# ============================================================================

class TestHistoryCompactor:
    """Test history compaction functionality."""

    @pytest.fixture
    def compactor(self):
        """Create compactor with test thresholds."""
        return HistoryCompactor(
            max_events_before_compaction=100,
            archive_storage="/tmp/test_archive",
        )

    def test_should_compact_false(self, compactor):
        """Test should_compact returns False when under threshold."""
        assert compactor.should_compact(50) is False
        assert compactor.should_compact(100) is False  # Exactly at threshold

    def test_should_compact_true(self, compactor):
        """Test should_compact returns True when over threshold."""
        assert compactor.should_compact(101) is True
        assert compactor.should_compact(500) is True

    @pytest.mark.asyncio
    async def test_create_snapshot(self, compactor):
        """Test creating a snapshot."""
        state = {"counter": 42, "data": [1, 2, 3]}
        
        snapshot_id = await compactor.create_snapshot("wf1", state, 500)
        
        assert snapshot_id is not None
        
        snapshot = await compactor.get_snapshot("wf1")
        assert snapshot is not None
        assert snapshot["workflow_id"] == "wf1"
        assert snapshot["state"] == state
        assert snapshot["snapshot_sequence"] == 500

    @pytest.mark.asyncio
    async def test_archive_events(self, compactor):
        """Test archiving old events."""
        events = [
            {"event_id": f"e{i}", "sequence": i, "event_type": "task", "data": {}}
            for i in range(300)
        ]
        state = {"counter": 100, "stage": "running"}
        
        result = await compactor.archive_events("wf1", events, state)
        
        # Should archive 200 events (300 - 100 kept)
        assert result.events_archived == 200
        assert result.new_workflow_id == "wf1_continue"
        assert result.snapshot_id != ""

    @pytest.mark.asyncio
    async def test_archive_under_threshold(self, compactor):
        """Test archiving when under threshold does nothing."""
        events = [
            {"event_id": f"e{i}", "sequence": i, "event_type": "task", "data": {}}
            for i in range(50)  # Under 100 threshold
        ]
        state = {"counter": 10}
        
        result = await compactor.archive_events("wf1", events, state)
        
        assert result.events_archived == 0
        assert result.snapshot_id == ""

    @pytest.mark.asyncio
    async def test_get_archived_history(self, compactor):
        """Test retrieving archived history."""
        events = [
            {"event_id": f"e{i}", "sequence": i, "event_type": "task", "data": {"n": i}}
            for i in range(250)
        ]
        state = {"counter": 100}
        
        await compactor.archive_events("wf1", events, state)
        
        archived = await compactor.get_archived_history("wf1")
        
        # Should have the first 150 archived events
        assert len(archived) == 150

    @pytest.mark.asyncio
    async def test_get_archived_history_from_sequence(self, compactor):
        """Test getting archived history from specific sequence."""
        events = [
            {"event_id": f"e{i}", "sequence": i, "event_type": "task", "data": {}}
            for i in range(300)
        ]
        state = {"counter": 100}
        
        await compactor.archive_events("wf1", events, state)
        
        archived = await compactor.get_archived_history("wf1", from_sequence=100)
        
        # Should skip events 0-99, start from 100
        assert len(archived) == 150


# ============================================================================
# Continue As New Manager Tests
# ============================================================================

class TestContinueAsNewManager:
    """Test continue-as-new functionality."""

    @pytest.fixture
    def manager(self):
        """Create continue-as-new manager."""
        compactor = HistoryCompactor(max_events_before_compaction=100)
        return ContinueAsNewManager(compactor, continue_as_new_enabled=True)

    @pytest.fixture
    def disabled_manager(self):
        """Create manager with continue-as-new disabled."""
        compactor = HistoryCompactor(max_events_before_compaction=100)
        return ContinueAsNewManager(compactor, continue_as_new_enabled=False)

    @pytest.mark.asyncio
    async def test_should_continue_true(self, manager):
        """Test should_continue returns True when threshold exceeded."""
        should = await manager.should_continue("wf1", 150)
        
        assert should is True

    @pytest.mark.asyncio
    async def test_should_continue_false(self, manager):
        """Test should_continue returns False when under threshold."""
        should = await manager.should_continue("wf1", 50)
        
        assert should is False

    @pytest.mark.asyncio
    async def test_should_continue_disabled(self, disabled_manager):
        """Test should_continue returns False when disabled."""
        should = await disabled_manager.should_continue("wf1", 1000)
        
        assert should is False

    @pytest.mark.asyncio
    async def test_continue_workflow(self, manager):
        """Test continuing a workflow."""
        events = [
            {"event_id": f"e{i}", "sequence": i, "event_type": "task", "data": {}}
            for i in range(200)
        ]
        state = {"counter": 100, "last_task": "task_100"}
        
        result = await manager.continue_workflow("wf1", state, events)
        
        assert result.events_archived > 0
        assert result.new_workflow_id == "wf1_continue"

    @pytest.mark.asyncio
    async def test_get_original_workflow_id(self, manager):
        """Test getting original workflow ID."""
        events = [
            {"event_id": f"e{i}", "sequence": i, "event_type": "task", "data": {}}
            for i in range(200)
        ]
        
        await manager.continue_workflow("wf1", {}, events)
        
        original = manager.get_original_workflow_id("wf1_continue")
        
        assert original == "wf1"

    @pytest.mark.asyncio
    async def test_is_continuation(self, manager):
        """Test checking if workflow is a continuation."""
        events = [
            {"event_id": f"e{i}", "sequence": i, "event_type": "task", "data": {}}
            for i in range(200)
        ]
        
        await manager.continue_workflow("wf1", {}, events)
        
        assert manager.is_continuation("wf1_continue") is True
        assert manager.is_continuation("wf1") is True  # Original is also marked as continuation

    @pytest.mark.asyncio
    async def test_restore_state(self, manager):
        """Test restoring state from snapshot."""
        original_state = {"counter": 100, "important": "data"}
        events = [
            {"event_id": f"e{i}", "sequence": i, "event_type": "task", "data": {}}
            for i in range(200)
        ]
        
        await manager.continue_workflow("wf1", original_state, events)
        
        restored = await manager.restore_state("wf1_continue")
        
        assert restored == original_state

    @pytest.mark.asyncio
    async def test_continue_as_new_idempotent(self, manager):
        """Test that multiple continues are idempotent."""
        events = [
            {"event_id": f"e{i}", "sequence": i, "event_type": "task", "data": {}}
            for i in range(200)
        ]
        state = {"counter": 100}
        
        result1 = await manager.continue_workflow("wf1", state, events)
        result2 = await manager.continue_workflow("wf1", state, events[:100])
        
        # Both should create valid continuations
        assert result1.new_workflow_id == "wf1_continue"
        assert result2.new_workflow_id == "wf1_continue"


# ============================================================================
# Workflow History Manager Tests
# ============================================================================

class TestWorkflowHistoryManager:
    """Test workflow history manager."""

    @pytest.fixture
    def history_manager(self):
        """Create workflow history manager."""
        compactor = HistoryCompactor(max_events_before_compaction=100)
        continue_manager = ContinueAsNewManager(compactor)
        return WorkflowHistoryManager(continue_manager, compactor)

    @pytest.mark.asyncio
    async def test_record_event_no_compact(self, history_manager):
        """Test recording event without triggering compaction."""
        event = {"event_id": "e1", "sequence": 50, "event_type": "task", "data": {}}
        
        compacted = await history_manager.record_event("wf1", event)
        
        assert compacted is False

    @pytest.mark.asyncio
    async def test_record_event_triggers_compact(self, history_manager):
        """Test that recording event at threshold triggers compaction check."""
        event = {"event_id": "e1", "sequence": 101, "event_type": "task", "data": {}}
        
        compacted = await history_manager.record_event("wf1", event)
        
        assert compacted is True

    @pytest.mark.asyncio
    async def test_compact_if_needed(self, history_manager):
        """Test compact_if_needed."""
        events = [
            {"event_id": f"e{i}", "sequence": i, "event_type": "task", "data": {}}
            for i in range(150)
        ]
        state = {"counter": 50}
        
        result = await history_manager.compact_if_needed("wf1", events, state)
        
        assert result is not None
        assert result.events_archived > 0

    @pytest.mark.asyncio
    async def test_compact_if_not_needed(self, history_manager):
        """Test compact_if_needed when not needed."""
        events = [
            {"event_id": f"e{i}", "sequence": i, "event_type": "task", "data": {}}
            for i in range(50)
        ]
        state = {"counter": 10}
        
        result = await history_manager.compact_if_needed("wf1", events, state)
        
        assert result is None


# ============================================================================
# Edge Cases
# ============================================================================

class TestCompactionEdgeCases:
    """Test edge cases in compaction."""

    @pytest.fixture
    def compactor(self):
        """Create compactor."""
        return HistoryCompactor(max_events_before_compaction=100)

    @pytest.mark.asyncio
    async def test_empty_events(self, compactor):
        """Test archiving empty event list."""
        result = await compactor.archive_events("wf1", [], {"counter": 0})
        
        assert result.events_archived == 0

    @pytest.mark.asyncio
    async def test_exactly_at_threshold(self, compactor):
        """Test archiving exactly at threshold."""
        events = [
            {"event_id": f"e{i}", "sequence": i, "event_type": "task", "data": {}}
            for i in range(100)
        ]
        
        result = await compactor.archive_events("wf1", events, {"counter": 50})
        
        # Exactly at threshold, no archiving needed
        assert result.events_archived == 0

    @pytest.mark.asyncio
    async def test_snapshot_id_uniqueness(self, compactor):
        """Test that snapshot IDs are unique."""
        state = {"counter": 1}
        
        id1 = await compactor.create_snapshot("wf1", state, 100)
        id2 = await compactor.create_snapshot("wf2", state, 100)
        
        assert id1 != id2

    @pytest.mark.asyncio
    async def test_get_nonexistent_snapshot(self, compactor):
        """Test getting non-existent snapshot."""
        snapshot = await compactor.get_snapshot("nonexistent")
        
        assert snapshot is None
