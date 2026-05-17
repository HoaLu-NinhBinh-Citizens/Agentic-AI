"""Activity heartbeat and lease management - Phase 5B v10.

Manages heartbeat tracking and lease expiration:
- ActivityHeartbeatManager: Tracks heartbeats
- LeaseManager: Manages task leases
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class LeaseStatus(Enum):
    """Status of a task lease."""
    ACTIVE = "active"
    EXPIRED = "expired"
    RELEASED = "released"
    REASSIGNED = "reassigned"


@dataclass
class ActivityHeartbeat:
    """Activity heartbeat record."""
    activity_id: str
    workflow_id: str
    last_heartbeat: int
    lease_expiry: int
    owner_worker: str
    max_missed_heartbeats: int = 3


@dataclass
class TaskLease:
    """Task lease information."""
    lease_id: str
    task_id: str
    worker_id: str
    acquired_at: int
    expires_at: int
    status: LeaseStatus


class HeartbeatStore:
    """Store interface for heartbeat records."""
    
    async def upsert(self, heartbeat: ActivityHeartbeat) -> None:
        """Insert or update heartbeat."""
        raise NotImplementedError
    
    async def get(self, activity_id: str) -> Optional[ActivityHeartbeat]:
        """Get heartbeat by activity ID."""
        raise NotImplementedError
    
    async def delete(self, activity_id: str) -> None:
        """Delete heartbeat."""
        raise NotImplementedError
    
    async def get_expired(self) -> list[ActivityHeartbeat]:
        """Get all expired heartbeats."""
        raise NotImplementedError


class InMemoryHeartbeatStore(HeartbeatStore):
    """In-memory implementation of heartbeat store."""
    
    def __init__(self):
        self._heartbeats: dict[str, ActivityHeartbeat] = {}
    
    async def upsert(self, heartbeat: ActivityHeartbeat) -> None:
        self._heartbeats[heartbeat.activity_id] = heartbeat
    
    async def get(self, activity_id: str) -> Optional[ActivityHeartbeat]:
        return self._heartbeats.get(activity_id)
    
    async def delete(self, activity_id: str) -> None:
        self._heartbeats.pop(activity_id, None)
    
    async def get_expired(self) -> list[ActivityHeartbeat]:
        now = int(time.time())
        return [
            hb for hb in self._heartbeats.values()
            if hb.lease_expiry <= now
        ]


class LeaseStore:
    """Store interface for task leases."""
    
    async def acquire(
        self,
        lease_id: str,
        task_id: str,
        worker_id: str,
        duration_seconds: int,
    ) -> Optional[TaskLease]:
        """Acquire a lease on a task."""
        raise NotImplementedError
    
    async def release(self, lease_id: str) -> bool:
        """Release a lease."""
        raise NotImplementedError
    
    async def extend(self, lease_id: str, additional_seconds: int) -> bool:
        """Extend a lease."""
        raise NotImplementedError
    
    async def get(self, lease_id: str) -> Optional[TaskLease]:
        """Get lease by ID."""
        raise NotImplementedError
    
    async def get_expired(self) -> list[TaskLease]:
        """Get all expired leases."""
        raise NotImplementedError


class InMemoryLeaseStore(LeaseStore):
    """In-memory implementation of lease store."""
    
    def __init__(self):
        self._leases: dict[str, TaskLease] = {}
    
    async def acquire(
        self,
        lease_id: str,
        task_id: str,
        worker_id: str,
        duration_seconds: int,
    ) -> Optional[TaskLease]:
        now = int(time.time())
        lease = TaskLease(
            lease_id=lease_id,
            task_id=task_id,
            worker_id=worker_id,
            acquired_at=now,
            expires_at=now + duration_seconds,
            status=LeaseStatus.ACTIVE,
        )
        self._leases[lease_id] = lease
        return lease
    
    async def release(self, lease_id: str) -> bool:
        lease = self._leases.get(lease_id)
        if not lease:
            return False
        lease.status = LeaseStatus.RELEASED
        return True
    
    async def extend(self, lease_id: str, additional_seconds: int) -> bool:
        lease = self._leases.get(lease_id)
        if not lease or lease.status != LeaseStatus.ACTIVE:
            return False
        lease.expires_at += additional_seconds
        return True
    
    async def get(self, lease_id: str) -> Optional[TaskLease]:
        return self._leases.get(lease_id)
    
    async def get_expired(self) -> list[TaskLease]:
        now = int(time.time())
        return [
            lease for lease in self._leases.values()
            if lease.status == LeaseStatus.ACTIVE and lease.expires_at < now
        ]


class ActivityHeartbeatManager:
    """Manages activity heartbeats.
    
    Workers send heartbeats to extend their lease on tasks.
    If heartbeats stop, the task is considered abandoned.
    """
    
    def __init__(
        self,
        store: HeartbeatStore,
        heartbeat_interval_seconds: float = 10.0,
        lease_duration_seconds: int = 30,
        max_missed_heartbeats: int = 3,
    ):
        self._store = store
        self._interval = heartbeat_interval_seconds
        self._lease_duration = lease_duration_seconds
        self._max_missed = max_missed_heartbeats
    
    async def start_activity(
        self,
        activity_id: str,
        workflow_id: str,
        worker_id: str,
    ) -> ActivityHeartbeat:
        """Start tracking an activity.
        
        Args:
            activity_id: Activity identifier
            workflow_id: Workflow identifier
            worker_id: Worker identifier
            
        Returns:
            Heartbeat record
        """
        now = int(time.time())
        heartbeat = ActivityHeartbeat(
            activity_id=activity_id,
            workflow_id=workflow_id,
            last_heartbeat=now,
            lease_expiry=now + self._lease_duration,
            owner_worker=worker_id,
            max_missed_heartbeats=self._max_missed,
        )
        await self._store.upsert(heartbeat)
        return heartbeat
    
    async def record_heartbeat(
        self,
        activity_id: str,
        worker_id: str,
    ) -> bool:
        """Record a heartbeat from a worker.
        
        Args:
            activity_id: Activity identifier
            worker_id: Worker identifier
            
        Returns:
            True if heartbeat recorded, False if activity not found
        """
        heartbeat = await self._store.get(activity_id)
        if not heartbeat:
            return False
        
        if heartbeat.owner_worker != worker_id:
            return False
        
        now = int(time.time())
        heartbeat.last_heartbeat = now
        heartbeat.lease_expiry = now + self._lease_duration
        await self._store.upsert(heartbeat)
        return True
    
    async def complete_activity(self, activity_id: str) -> None:
        """Mark activity as completed (stop tracking)."""
        await self._store.delete(activity_id)
    
    async def get_activity_status(
        self,
        activity_id: str,
    ) -> Optional[dict]:
        """Get status of an activity.
        
        Returns:
            Status dict with lease info, or None if not found
        """
        heartbeat = await self._store.get(activity_id)
        if not heartbeat:
            return None
        
        now = int(time.time())
        time_since_heartbeat = now - heartbeat.last_heartbeat
        
        return {
            "activity_id": activity_id,
            "workflow_id": heartbeat.workflow_id,
            "owner_worker": heartbeat.owner_worker,
            "last_heartbeat": heartbeat.last_heartbeat,
            "lease_expiry": heartbeat.lease_expiry,
            "is_healthy": heartbeat.lease_expiry > now,
            "time_since_heartbeat": time_since_heartbeat,
        }
    
    async def get_abandoned_activities(self) -> list[str]:
        """Get list of abandoned activities.
        
        An activity is abandoned if its lease has expired.
        """
        expired = await self._store.get_expired()
        return [hb.activity_id for hb in expired]


class LeaseManager:
    """Manages task leases for workers.
    
    Workers acquire leases before processing tasks.
    Leases expire if the worker fails or goes silent.
    """
    
    def __init__(
        self,
        store: LeaseStore,
        default_lease_seconds: int = 60,
    ):
        self._store = store
        self._default_lease = default_lease_seconds
    
    async def acquire_lease(
        self,
        task_id: str,
        worker_id: str,
        duration_seconds: Optional[int] = None,
    ) -> TaskLease:
        """Acquire a lease on a task.
        
        Args:
            task_id: Task identifier
            worker_id: Worker identifier
            duration_seconds: Optional lease duration
            
        Returns:
            Acquired lease
        """
        lease_id = f"{task_id}:{worker_id}:{int(time.time())}"
        duration = duration_seconds or self._default_lease
        
        lease = await self._store.acquire(
            lease_id, task_id, worker_id, duration
        )
        
        if not lease:
            raise RuntimeError(f"Failed to acquire lease for task {task_id}")
        
        return lease
    
    async def release_lease(self, lease_id: str) -> bool:
        """Release a lease."""
        return await self._store.release(lease_id)
    
    async def extend_lease(
        self,
        lease_id: str,
        additional_seconds: int,
    ) -> bool:
        """Extend a lease."""
        return await self._store.extend(lease_id, additional_seconds)
    
    async def is_lease_valid(self, lease_id: str) -> bool:
        """Check if a lease is still valid."""
        lease = await self._store.get(lease_id)
        if not lease:
            return False
        
        if lease.status != LeaseStatus.ACTIVE:
            return False
        
        return lease.expires_at > int(time.time())
    
    async def get_expired_leases(self) -> list[TaskLease]:
        """Get all expired leases for reassignment."""
        return await self._store.get_expired()
    
    async def reassign_task(
        self,
        task_id: str,
        from_worker: str,
        to_worker: str,
    ) -> Optional[TaskLease]:
        """Reassign a task to a new worker.
        
        Args:
            task_id: Task identifier
            from_worker: Original worker
            to_worker: New worker
            
        Returns:
            New lease for the task
        """
        return await self.acquire_lease(task_id, to_worker)
