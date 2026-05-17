"""Plan retry manager with snapshot isolation - Phase 5B."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Set

from .types import PlanRetrySnapshot, PlanState


class PlanRetryStore:
    """Store interface for plan retry snapshots."""
    
    async def save(self, snapshot: PlanRetrySnapshot) -> None:
        """Save a retry snapshot."""
        raise NotImplementedError
    
    async def get_latest(self, plan_id: str) -> Optional[PlanRetrySnapshot]:
        """Get the latest snapshot for a plan."""
        raise NotImplementedError
    
    async def get_all(self, plan_id: str) -> list[PlanRetrySnapshot]:
        """Get all snapshots for a plan."""
        raise NotImplementedError
    
    async def delete_before(self, plan_id: str, timestamp: int) -> int:
        """Delete snapshots before a timestamp."""
        raise NotImplementedError


class InMemoryPlanRetryStore(PlanRetryStore):
    """In-memory implementation of plan retry store."""
    
    def __init__(self):
        self._snapshots: dict[str, list[PlanRetrySnapshot]] = {}
    
    async def save(self, snapshot: PlanRetrySnapshot) -> None:
        """Save a retry snapshot."""
        if snapshot.plan_id not in self._snapshots:
            self._snapshots[snapshot.plan_id] = []
        self._snapshots[snapshot.plan_id].append(snapshot)
    
    async def get_latest(self, plan_id: str) -> Optional[PlanRetrySnapshot]:
        """Get the latest snapshot for a plan."""
        snapshots = self._snapshots.get(plan_id, [])
        if not snapshots:
            return None
        return max(snapshots, key=lambda s: s.created_at)
    
    async def get_all(self, plan_id: str) -> list[PlanRetrySnapshot]:
        """Get all snapshots for a plan."""
        return sorted(
            self._snapshots.get(plan_id, []),
            key=lambda s: s.created_at,
        )
    
    async def delete_before(self, plan_id: str, timestamp: int) -> int:
        """Delete snapshots before a timestamp."""
        snapshots = self._snapshots.get(plan_id, [])
        original_count = len(snapshots)
        self._snapshots[plan_id] = [
            s for s in snapshots if s.created_at >= timestamp
        ]
        return original_count - len(self._snapshots[plan_id])


class PlanRetryManager:
    """Manages plan retry with snapshot isolation.
    
    Creates snapshots before first execution and restores
    state during retry to ensure idempotent retry behavior.
    """
    
    def __init__(
        self,
        store: PlanRetryStore,
        snapshot_before_first_run: bool = True,
    ):
        self._store = store
        self._snapshot_before_first_run = snapshot_before_first_run
        self._snapshot_created: set[str] = set()

    async def create_snapshot(
        self,
        plan_id: str,
        state: PlanState,
    ) -> PlanRetrySnapshot:
        """Create a snapshot of plan state before first run.
        
        This captures the complete state including:
        - Plan graph
        - Branch decisions
        - Task completion status
        - Context
        
        Args:
            plan_id: Plan identifier
            state: Current plan state
            
        Returns:
            The created snapshot
        """
        snapshot_data = state.to_dict()
        
        snapshot = PlanRetrySnapshot(
            plan_id=plan_id,
            snapshot=snapshot_data,
            created_at=int(datetime.utcnow().timestamp()),
        )
        
        await self._store.save(snapshot)
        self._snapshot_created.add(plan_id)
        
        return snapshot

    async def restore_snapshot(
        self,
        plan_id: str,
    ) -> Optional[PlanState]:
        """Restore plan state from snapshot.
        
        Args:
            plan_id: Plan identifier
            
        Returns:
            Restored PlanState or None if no snapshot exists
        """
        snapshot = await self._store.get_latest(plan_id)
        
        if not snapshot:
            return None
        
        return PlanState.from_dict(snapshot.snapshot)

    async def should_skip_activity(
        self,
        activity_id: str,
        completed_activities: Set[str],
        is_retry: bool = False,
    ) -> bool:
        """Determine if an activity should be skipped on retry.
        
        Activities that completed successfully in a previous run
        should be skipped during retry.
        
        Args:
            activity_id: Activity identifier
            completed_activities: Set of completed activity IDs
            is_retry: Whether this is a retry run
            
        Returns:
            True if activity should be skipped
        """
        if not is_retry:
            return False
        
        return activity_id in completed_activities

    async def prepare_retry(
        self,
        plan_id: str,
        state: PlanState,
    ) -> tuple[PlanState, bool]:
        """Prepare plan state for retry.
        
        This method:
        1. Creates a new snapshot before retry
        2. Restores from previous snapshot if available
        3. Marks activities that should be skipped
        
        Args:
            plan_id: Plan identifier
            state: Current plan state
            
        Returns:
            Tuple of (restored_state, was_restored)
        """
        snapshot = await self._store.get_latest(plan_id)
        
        if snapshot:
            restored_state = PlanState.from_dict(snapshot.snapshot)
            
            await self._store.save(PlanRetrySnapshot(
                plan_id=plan_id,
                snapshot=state.to_dict(),
                created_at=int(datetime.utcnow().timestamp()),
            ))
            
            return restored_state, True
        
        await self.create_snapshot(plan_id, state)
        
        return state, False

    async def get_retry_count(self, plan_id: str) -> int:
        """Get the number of retries for a plan.
        
        Args:
            plan_id: Plan identifier
            
        Returns:
            Number of snapshots (first run + retries)
        """
        snapshots = await self._store.get_all(plan_id)
        return len(snapshots)

    async def cleanup_old_snapshots(
        self,
        plan_id: str,
        retain_count: int = 5,
    ) -> int:
        """Clean up old snapshots, retaining recent ones.
        
        Args:
            plan_id: Plan identifier
            retain_count: Number of recent snapshots to retain
            
        Returns:
            Number of snapshots deleted
        """
        snapshots = await self._store.get_all(plan_id)
        
        if len(snapshots) <= retain_count:
            return 0
        
        cutoff_timestamp = snapshots[-retain_count].created_at
        
        return await self._store.delete_before(plan_id, cutoff_timestamp)

    async def has_snapshot(self, plan_id: str) -> bool:
        """Check if a plan has any snapshots.
        
        Args:
            plan_id: Plan identifier
            
        Returns:
            True if snapshots exist
        """
        snapshot = await self._store.get_latest(plan_id)
        return snapshot is not None

    async def get_snapshot_history(
        self,
        plan_id: str,
    ) -> list[PlanRetrySnapshot]:
        """Get complete snapshot history for a plan.
        
        Useful for debugging and audit.
        
        Args:
            plan_id: Plan identifier
            
        Returns:
            List of snapshots in chronological order
        """
        return await self._store.get_all(plan_id)


class SkipActivityTracker:
    """Tracks which activities should be skipped during retry."""
    
    def __init__(self):
        self._skip_set: set[str] = set()
    
    def add_skip(self, activity_id: str) -> None:
        """Mark an activity for skipping."""
        self._skip_set.add(activity_id)
    
    def should_skip(self, activity_id: str) -> bool:
        """Check if an activity should be skipped."""
        return activity_id in self._skip_set
    
    def clear(self) -> None:
        """Clear all skip marks."""
        self._skip_set.clear()
    
    def get_skipped(self) -> set[str]:
        """Get all marked activities."""
        return self._skip_set.copy()
