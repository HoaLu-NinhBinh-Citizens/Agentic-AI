"""History compaction and Continue-As-New - Phase 5B v10.

Implements history compaction to prevent event log explosion:
- ContinueAsNewManager: Handles workflow continuation
- HistoryCompactor: Compacts event history
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CompactionResult:
    """Result of history compaction."""
    original_workflow_id: str
    new_workflow_id: str
    events_archived: int
    snapshot_id: str
    archived_at: int = field(default_factory=lambda: int(time.time()))


@dataclass
class ArchivedHistory:
    """Archived event history."""
    workflow_id: str
    sequence_start: int
    sequence_end: int
    events: list[dict]
    snapshot_state: dict
    archived_at: int = field(default_factory=lambda: int(time.time()))


class HistoryCompactor:
    """Compacts workflow event history.
    
    When a workflow exceeds max_events, old events are
    archived and replaced with a snapshot.
    """
    
    def __init__(
        self,
        max_events_before_compaction: int = 2000,
        archive_storage: Optional[str] = None,
    ):
        self._max_events = max_events_before_compaction
        self._archive_storage = archive_storage
        self._snapshots: dict[str, dict] = {}
        self._archived: list[ArchivedHistory] = []
    
    def should_compact(self, event_count: int) -> bool:
        """Check if history should be compacted.
        
        Args:
            event_count: Number of events
            
        Returns:
            True if compaction is needed
        """
        return event_count >= self._max_events
    
    async def create_snapshot(
        self,
        workflow_id: str,
        state: dict,
        current_sequence: int,
    ) -> str:
        """Create a snapshot of current state.
        
        Args:
            workflow_id: Workflow identifier
            state: Current workflow state
            current_sequence: Current event sequence number
            
        Returns:
            Snapshot ID
        """
        import uuid
        
        snapshot_id = str(uuid.uuid4())
        snapshot = {
            "snapshot_id": snapshot_id,
            "workflow_id": workflow_id,
            "state": state,
            "snapshot_sequence": current_sequence,
            "created_at": int(time.time()),
        }
        
        self._snapshots[workflow_id] = snapshot
        
        return snapshot_id
    
    async def archive_events(
        self,
        workflow_id: str,
        events: list[dict],
        state: dict,
    ) -> CompactionResult:
        """Archive old events and create snapshot.
        
        Args:
            workflow_id: Workflow identifier
            events: Events to archive
            state: Current workflow state
            
        Returns:
            Compaction result
        """
        import uuid
        
        if len(events) <= self._max_events:
            return CompactionResult(
                original_workflow_id=workflow_id,
                new_workflow_id=workflow_id,
                events_archived=0,
                snapshot_id="",
            )
        
        events_to_archive = events[:-self._max_events]
        remaining_events = events[-self._max_events:]
        
        sequence_start = remaining_events[0].get("sequence", 0) if remaining_events else 0
        sequence_end = events[-1].get("sequence", 0) if events else 0
        
        archived = ArchivedHistory(
            workflow_id=workflow_id,
            sequence_start=sequence_start,
            sequence_end=sequence_end,
            events=events_to_archive,
            snapshot_state=state,
        )
        self._archived.append(archived)
        
        snapshot_id = await self.create_snapshot(
            workflow_id, state, sequence_end
        )
        
        new_workflow_id = f"{workflow_id}_continue"
        
        return CompactionResult(
            original_workflow_id=workflow_id,
            new_workflow_id=new_workflow_id,
            events_archived=len(events_to_archive),
            snapshot_id=snapshot_id,
        )
    
    async def get_snapshot(self, workflow_id: str) -> Optional[dict]:
        """Get the latest snapshot for a workflow.
        
        Args:
            workflow_id: Workflow identifier
            
        Returns:
            Snapshot or None
        """
        return self._snapshots.get(workflow_id)
    
    async def get_archived_history(
        self,
        workflow_id: str,
        from_sequence: int = 0,
    ) -> list[dict]:
        """Get archived events for a workflow.
        
        Args:
            workflow_id: Workflow identifier
            from_sequence: Start from sequence
            
        Returns:
            List of archived events
        """
        result = []
        
        for archived in self._archived:
            if archived.workflow_id != workflow_id:
                continue
            
            if archived.sequence_end < from_sequence:
                continue
            
            result.extend(archived.events)
        
        return result


class ContinueAsNewManager:
    """Manages workflow continuation (Continue-As-New).
    
    Creates a new workflow execution with the same ID
    but fresh event history, carrying forward the state.
    """
    
    def __init__(
        self,
        compactor: HistoryCompactor,
        continue_as_new_enabled: bool = True,
    ):
        self._compactor = compactor
        self._enabled = continue_as_new_enabled
        self._continuations: dict[str, str] = {}
    
    async def should_continue(
        self,
        workflow_id: str,
        event_count: int,
    ) -> bool:
        """Check if workflow should continue-as-new.
        
        Args:
            workflow_id: Workflow identifier
            event_count: Current event count
            
        Returns:
            True if continue-as-new should happen
        """
        if not self._enabled:
            return False
        
        return self._compactor.should_compact(event_count)
    
    async def continue_workflow(
        self,
        workflow_id: str,
        current_state: dict,
        events: list[dict],
        input: Optional[dict] = None,
    ) -> CompactionResult:
        """Continue a workflow with a new execution.
        
        This:
        1. Archives old events
        2. Creates a snapshot
        3. Returns info for starting new execution
        
        Args:
            workflow_id: Current workflow ID
            current_state: Current workflow state
            events: All events
            input: Optional new input
            
        Returns:
            Compaction result with new workflow info
        """
        result = await self._compactor.archive_events(
            workflow_id, events, current_state
        )
        
        self._continuations[workflow_id] = result.new_workflow_id
        self._continuations[result.new_workflow_id] = workflow_id
        
        return result
    
    def get_original_workflow_id(
        self,
        workflow_id: str,
    ) -> str:
        """Get the original workflow ID for a continued workflow.
        
        Args:
            workflow_id: Workflow ID
            
        Returns:
            Original workflow ID
        """
        return self._continuations.get(workflow_id, workflow_id)
    
    def is_continuation(self, workflow_id: str) -> bool:
        """Check if this workflow is a continuation.
        
        Args:
            workflow_id: Workflow ID
            
        Returns:
            True if this is a continued workflow
        """
        return workflow_id in self._continuations
    
    async def restore_state(
        self,
        workflow_id: str,
    ) -> Optional[dict]:
        """Restore workflow state from snapshot.
        
        Args:
            workflow_id: Workflow identifier
            
        Returns:
            Restored state or None
        """
        snapshot = await self._compactor.get_snapshot(workflow_id)
        
        if not snapshot:
            original_id = self.get_original_workflow_id(workflow_id)
            snapshot = await self._compactor.get_snapshot(original_id)
        
        if snapshot:
            return snapshot.get("state")
        
        return None


class WorkflowHistoryManager:
    """Manages workflow history with compaction support."""
    
    def __init__(
        self,
        continue_manager: ContinueAsNewManager,
        compactor: HistoryCompactor,
    ):
        self._continue_manager = continue_manager
        self._compactor = compactor
    
    async def record_event(
        self,
        workflow_id: str,
        event: dict,
    ) -> bool:
        """Record an event, triggering compaction if needed.
        
        Args:
            workflow_id: Workflow identifier
            event: Event data
            
        Returns:
            True if compaction was triggered
        """
        compacted = await self._compactor.should_compact(
            event.get("sequence", 0) + 1
        )
        
        return compacted
    
    async def compact_if_needed(
        self,
        workflow_id: str,
        events: list[dict],
        state: dict,
    ) -> Optional[CompactionResult]:
        """Compact history if needed.
        
        Args:
            workflow_id: Workflow identifier
            events: All events
            state: Current state
            
        Returns:
            Compaction result if compacted
        """
        should = await self._continue_manager.should_continue(
            workflow_id, len(events)
        )
        
        if should:
            return await self._continue_manager.continue_workflow(
                workflow_id, state, events
            )
        
        return None
