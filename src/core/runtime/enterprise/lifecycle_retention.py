"""Lifecycle retention and archival - Phase 5B v10.

Implements workflow lifecycle management:
- WorkflowLifecycle: Lifecycle states
- LifecycleManager: Manages retention policies
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class WorkflowLifecycle(Enum):
    """Lifecycle states for workflows."""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"
    PURGED = "purged"


@dataclass
class RetentionPolicy:
    """Retention policy configuration."""
    completed_retention_days: int = 7
    archived_retention_days: int = 90
    failed_retention_days: int = 30
    cancelled_retention_days: int = 7
    archive_before_delete: bool = True


@dataclass
class LifecycleTransition:
    """Record of a lifecycle transition."""
    workflow_id: str
    from_state: WorkflowLifecycle
    to_state: WorkflowLifecycle
    timestamp: int = field(default_factory=lambda: int(time.time()))
    reason: Optional[str] = None


@dataclass
class WorkflowLifecycleState:
    """Current lifecycle state of a workflow."""
    workflow_id: str
    current_state: WorkflowLifecycle
    state_since: int = field(default_factory=lambda: int(time.time()))
    archived_at: Optional[int] = None
    purged_at: Optional[int] = None


class LifecycleStore:
    """Store interface for lifecycle states."""
    
    async def save(self, state: WorkflowLifecycleState) -> None:
        """Save lifecycle state."""
        raise NotImplementedError
    
    async def get(self, workflow_id: str) -> Optional[WorkflowLifecycleState]:
        """Get lifecycle state."""
        raise NotImplementedError
    
    async def get_by_state(
        self,
        state: WorkflowLifecycle,
    ) -> list[WorkflowLifecycleState]:
        """Get workflows by state."""
        raise NotImplementedError
    
    async def get_ready_for_archive(
        self,
        retention_days: int,
    ) -> list[str]:
        """Get workflow IDs ready for archival."""
        raise NotImplementedError
    
    async def get_ready_for_purge(
        self,
        retention_days: int,
    ) -> list[str]:
        """Get workflow IDs ready for purge."""
        raise NotImplementedError


class InMemoryLifecycleStore(LifecycleStore):
    """In-memory implementation of lifecycle store."""
    
    def __init__(self):
        self._states: dict[str, WorkflowLifecycleState] = {}
        self._transitions: list[LifecycleTransition] = []
    
    async def save(self, state: WorkflowLifecycleState) -> None:
        self._states[state.workflow_id] = state
    
    async def get(self, workflow_id: str) -> Optional[WorkflowLifecycleState]:
        return self._states.get(workflow_id)
    
    async def get_by_state(
        self,
        state: WorkflowLifecycle,
    ) -> list[WorkflowLifecycleState]:
        return [s for s in self._states.values() if s.current_state == state]
    
    async def get_ready_for_archive(
        self,
        retention_days: int,
    ) -> list[str]:
        cutoff = int(time.time()) - (retention_days * 86400)
        
        return [
            wf_id for wf_id, state in self._states.items()
            if state.current_state in (
                WorkflowLifecycle.COMPLETED,
                WorkflowLifecycle.FAILED,
                WorkflowLifecycle.CANCELLED,
            )
            and state.state_since < cutoff
            and state.archived_at is None
        ]
    
    async def get_ready_for_purge(
        self,
        retention_days: int,
    ) -> list[str]:
        cutoff = int(time.time()) - (retention_days * 86400)
        
        return [
            wf_id for wf_id, state in self._states.items()
            if state.current_state == WorkflowLifecycle.ARCHIVED
            and state.archived_at is not None
            and state.archived_at < cutoff
            and state.purged_at is None
        ]


class LifecycleManager:
    """Manages workflow lifecycle and retention.
    
    Handles transitions between lifecycle states and
    enforces retention policies.
    """
    
    def __init__(
        self,
        store: LifecycleStore,
        policy: Optional[RetentionPolicy] = None,
    ):
        self._store = store
        self._policy = policy or RetentionPolicy()
        self._transitions: list[LifecycleTransition] = []
    
    async def set_state(
        self,
        workflow_id: str,
        new_state: WorkflowLifecycle,
        reason: Optional[str] = None,
    ) -> WorkflowLifecycleState:
        """Transition a workflow to a new state.
        
        Args:
            workflow_id: Workflow identifier
            new_state: New lifecycle state
            reason: Optional reason for transition
            
        Returns:
            Updated lifecycle state
        """
        current = await self._store.get(workflow_id)
        
        if current:
            from_state = current.current_state
        else:
            from_state = WorkflowLifecycle.RUNNING
        
        if new_state == WorkflowLifecycle.ARCHIVED:
            archived_at = int(time.time())
        else:
            archived_at = current.archived_at if current else None
        
        if new_state == WorkflowLifecycle.PURGED:
            purged_at = int(time.time())
        else:
            purged_at = current.purged_at if current else None
        
        state = WorkflowLifecycleState(
            workflow_id=workflow_id,
            current_state=new_state,
            state_since=int(time.time()),
            archived_at=archived_at,
            purged_at=purged_at,
        )
        
        await self._store.save(state)
        
        transition = LifecycleTransition(
            workflow_id=workflow_id,
            from_state=from_state,
            to_state=new_state,
            reason=reason,
        )
        self._transitions.append(transition)
        
        return state
    
    async def get_state(
        self,
        workflow_id: str,
    ) -> Optional[WorkflowLifecycleState]:
        """Get current lifecycle state."""
        return await self._store.get(workflow_id)
    
    async def complete(self, workflow_id: str) -> WorkflowLifecycleState:
        """Mark workflow as completed."""
        return await self.set_state(
            workflow_id,
            WorkflowLifecycle.COMPLETED,
            "Workflow completed successfully",
        )
    
    async def fail(self, workflow_id: str, reason: str) -> WorkflowLifecycleState:
        """Mark workflow as failed."""
        return await self.set_state(
            workflow_id,
            WorkflowLifecycle.FAILED,
            reason,
        )
    
    async def cancel(self, workflow_id: str, reason: str) -> WorkflowLifecycleState:
        """Mark workflow as cancelled."""
        return await self.set_state(
            workflow_id,
            WorkflowLifecycle.CANCELLED,
            reason,
        )
    
    async def archive(self, workflow_id: str) -> WorkflowLifecycleState:
        """Archive a workflow."""
        current = await self._store.get(workflow_id)
        
        if not current:
            raise ValueError(f"Workflow not found: {workflow_id}")
        
        return await self.set_state(
            workflow_id,
            WorkflowLifecycle.ARCHIVED,
            "Archived per retention policy",
        )
    
    async def purge(self, workflow_id: str) -> WorkflowLifecycleState:
        """Purge a workflow."""
        current = await self._store.get(workflow_id)
        
        if not current:
            raise ValueError(f"Workflow not found: {workflow_id}")
        
        if current.current_state != WorkflowLifecycle.ARCHIVED:
            raise ValueError(
                f"Can only purge archived workflows, "
                f"current state: {current.current_state}"
            )
        
        return await self.set_state(
            workflow_id,
            WorkflowLifecycle.PURGED,
            "Purged per retention policy",
        )
    
    async def process_retention(self) -> dict[str, int]:
        """Process retention policies.
        
        Archives completed workflows and purges old archives.
        
        Returns:
            Dict with counts of processed workflows
        """
        results = {
            "archived": 0,
            "purged": 0,
            "errors": 0,
        }
        
        to_archive = await self._store.get_ready_for_archive(
            self._policy.completed_retention_days
        )
        for workflow_id in to_archive:
            try:
                await self.archive(workflow_id)
                results["archived"] += 1
            except Exception:
                results["errors"] += 1
        
        to_purge = await self._store.get_ready_for_purge(
            self._policy.archived_retention_days
        )
        for workflow_id in to_purge:
            try:
                await self.purge(workflow_id)
                results["purged"] += 1
            except Exception:
                results["errors"] += 1
        
        return results
    
    async def get_transition_history(
        self,
        workflow_id: str,
    ) -> list[LifecycleTransition]:
        """Get transition history for a workflow."""
        return [
            t for t in self._transitions
            if t.workflow_id == workflow_id
        ]


class LifecycleEnforcer:
    """Enforces lifecycle state transitions.
    
    Validates that transitions are allowed and
    prevents invalid state changes.
    """
    
    ALLOWED_TRANSITIONS = {
        WorkflowLifecycle.RUNNING: {
            WorkflowLifecycle.COMPLETED,
            WorkflowLifecycle.FAILED,
            WorkflowLifecycle.CANCELLED,
            WorkflowLifecycle.ARCHIVED,
        },
        WorkflowLifecycle.COMPLETED: {
            WorkflowLifecycle.ARCHIVED,
            WorkflowLifecycle.PURGED,
        },
        WorkflowLifecycle.FAILED: {
            WorkflowLifecycle.ARCHIVED,
            WorkflowLifecycle.PURGED,
        },
        WorkflowLifecycle.CANCELLED: {
            WorkflowLifecycle.ARCHIVED,
        },
        WorkflowLifecycle.ARCHIVED: {
            WorkflowLifecycle.PURGED,
        },
        WorkflowLifecycle.PURGED: set(),
    }
    
    def can_transition(
        self,
        from_state: WorkflowLifecycle,
        to_state: WorkflowLifecycle,
    ) -> bool:
        """Check if transition is allowed."""
        allowed = self.ALLOWED_TRANSITIONS.get(from_state, set())
        return to_state in allowed
    
    def get_allowed_transitions(
        self,
        from_state: WorkflowLifecycle,
    ) -> set[WorkflowLifecycle]:
        """Get allowed transitions from a state."""
        return self.ALLOWED_TRANSITIONS.get(from_state, set())
