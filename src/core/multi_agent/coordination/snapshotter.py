"""
Event Sourcing with Snapshots.

Provides:
- Event storage with snapshots
- Snapshot-based replay
- Snapshot compaction
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """Single event in the event store."""
    event_id: str
    aggregate_id: str
    event_type: str
    payload: Dict[str, Any]
    sequence: int
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Snapshot:
    """Event store snapshot."""
    aggregate_id: str
    snapshot_id: str
    sequence: int
    state: Dict[str, Any]
    created_at: datetime
    compressed_size: int = 0


class InMemorySnapshotStore:
    """In-memory snapshot store for testing."""
    
    def __init__(self):
        self._snapshots: Dict[str, Snapshot] = {}  # aggregate_id -> latest snapshot
        self._all_snapshots: List[Snapshot] = []
    
    async def save(self, snapshot: Snapshot) -> None:
        """Save snapshot."""
        self._snapshots[snapshot.aggregate_id] = snapshot
        self._all_snapshots.append(snapshot)
    
    async def get_latest(self, aggregate_id: str) -> Optional[Snapshot]:
        """Get latest snapshot for aggregate."""
        return self._snapshots.get(aggregate_id)
    
    async def get_range(
        self,
        aggregate_id: str,
        start_seq: int,
        end_seq: int,
    ) -> List[Snapshot]:
        """Get snapshots in sequence range."""
        return [
            s for s in self._all_snapshots
            if s.aggregate_id == aggregate_id
            and start_seq <= s.sequence <= end_seq
        ]
    
    async def delete_before(self, sequence: int) -> int:
        """Delete snapshots before sequence."""
        to_delete = [
            s for s in self._all_snapshots
            if s.sequence < sequence
        ]
        
        for s in to_delete:
            if s.aggregate_id in self._snapshots:
                del self._snapshots[s.aggregate_id]
            self._all_snapshots.remove(s)
        
        return len(to_delete)


class InMemoryEventStore:
    """In-memory event store for testing."""
    
    def __init__(self):
        self._events: Dict[str, List[Event]] = {}  # aggregate_id -> events
        self._sequences: Dict[str, int] = {}  # aggregate_id -> last sequence
    
    async def append(
        self,
        aggregate_id: str,
        event: Event,
    ) -> Event:
        """Append event to aggregate."""
        if aggregate_id not in self._events:
            self._events[aggregate_id] = []
            self._sequences[aggregate_id] = 0
        
        self._sequences[aggregate_id] += 1
        event.sequence = self._sequences[aggregate_id]
        self._events[aggregate_id].append(event)
        
        return event
    
    async def get_events(
        self,
        aggregate_id: str,
        start_sequence: int = 1,
    ) -> List[Event]:
        """Get events from sequence."""
        events = self._events.get(aggregate_id, [])
        return [e for e in events if e.sequence >= start_sequence]
    
    async def get_sequence(self, aggregate_id: str) -> int:
        """Get current sequence for aggregate."""
        return self._sequences.get(aggregate_id, 0)


class Snapshotter:
    """
    Event sourcing snapshot manager.
    
    Features:
    - Periodic snapshots based on event count
    - State compaction
    - Efficient replay from snapshots
    
    Snapshot Strategy:
    - Create snapshot every N events (default: 50)
    - Keep at least 2 snapshots for safety
    - Delete old snapshots periodically
    """
    
    def __init__(
        self,
        snapshot_interval: int = 50,
        snapshot_store: Optional[InMemorySnapshotStore] = None,
        event_store: Optional[InMemoryEventStore] = None,
        compression_enabled: bool = True,
    ):
        self.snapshot_interval = snapshot_interval
        self.snapshot_store = snapshot_store or InMemorySnapshotStore()
        self.event_store = event_store or InMemoryEventStore()
        self.compression_enabled = compression_enabled
        
        self._event_counts: Dict[str, int] = {}  # aggregate_id -> count since last snapshot
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def record_event(
        self,
        aggregate_id: str,
        event_type: str,
        payload: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Event:
        """Record an event and check if snapshot needed."""
        import uuid
        
        event = Event(
            event_id=str(uuid.uuid4()),
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            sequence=0,  # Will be set by store
            timestamp=datetime.now(),
            metadata=metadata or {},
        )
        
        # Append to event store
        result = await self.event_store.append(aggregate_id, event)
        
        # Check if snapshot needed
        count = self._event_counts.get(aggregate_id, 0) + 1
        self._event_counts[aggregate_id] = count
        
        if count >= self.snapshot_interval:
            await self.create_snapshot(aggregate_id)
            self._event_counts[aggregate_id] = 0
        
        return result
    
    async def create_snapshot(
        self,
        aggregate_id: str,
        state_provider: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> Optional[Snapshot]:
        """
        Create snapshot for aggregate.
        
        Args:
            aggregate_id: Aggregate ID
            state_provider: Function to get current state (if not using replay)
        """
        import uuid
        
        current_sequence = await self.event_store.get_sequence(aggregate_id)
        
        if state_provider:
            state = state_provider()
        else:
            # Reconstruct state from events
            events = await self.event_store.get_events(aggregate_id)
            state = self._replay_events(events)
        
        snapshot = Snapshot(
            aggregate_id=aggregate_id,
            snapshot_id=str(uuid.uuid4()),
            sequence=current_sequence,
            state=state,
            created_at=datetime.now(),
        )
        
        # Compress if enabled
        if self.compression_enabled:
            state_json = json.dumps(state)
            compressed = gzip.compress(state_json.encode())
            snapshot.compressed_size = len(compressed)
        
        await self.snapshot_store.save(snapshot)
        logger.info(f"Created snapshot for {aggregate_id} at sequence {current_sequence}")
        
        return snapshot
    
    def _replay_events(self, events: List[Event]) -> Dict[str, Any]:
        """
        Replay events to reconstruct state.
        
        This is a simplified version. Real implementation would
        apply events to a state object using event handlers.
        """
        state = {}
        
        for event in events:
            # Apply event to state (simplified)
            if event.event_type == "task_created":
                state["task_id"] = event.payload.get("task_id")
                state["status"] = "created"
            elif event.event_type == "task_started":
                state["status"] = "running"
            elif event.event_type == "task_completed":
                state["status"] = "completed"
            elif event.event_type == "task_failed":
                state["status"] = "failed"
                state["error"] = event.payload.get("error")
        
        return state
    
    async def replay_from_snapshot(
        self,
        aggregate_id: str,
        event_handler: Callable[[Event], None],
    ) -> Dict[str, Any]:
        """
        Replay events from snapshot.
        
        Loads snapshot state and applies events after snapshot sequence.
        
        Args:
            aggregate_id: Aggregate ID
            event_handler: Handler function to apply events
            
        Returns:
            Final reconstructed state
        """
        # Load latest snapshot
        snapshot = await self.snapshot_store.get_latest(aggregate_id)
        
        if snapshot:
            state = snapshot.state.copy()
            start_sequence = snapshot.sequence + 1
        else:
            state = {}
            start_sequence = 1
        
        # Get events after snapshot
        events = await self.event_store.get_events(aggregate_id, start_sequence)
        
        # Apply events
        for event in events:
            await event_handler(event)
        
        return state
    
    async def compact(self, aggregate_id: str, keep_snapshots: int = 2) -> int:
        """
        Compact snapshots for aggregate.
        
        Keeps only the N most recent snapshots.
        
        Returns number of snapshots deleted.
        """
        snapshots = await self.snapshot_store.get_range(
            aggregate_id,
            0,
            await self.event_store.get_sequence(aggregate_id),
        )
        
        # Sort by sequence descending
        snapshots.sort(key=lambda s: s.sequence, reverse=True)
        
        # Delete old snapshots
        snapshots_to_delete = snapshots[keep_snapshots:]
        
        count = await self.snapshot_store.delete_before(
            snapshots_to_delete[0].sequence if snapshots_to_delete else 0
        )
        
        logger.info(f"Compacted {count} old snapshots for {aggregate_id}")
        return count
    
    async def get_snapshot_info(self, aggregate_id: str) -> Dict[str, Any]:
        """Get snapshot information for aggregate."""
        snapshot = await self.snapshot_store.get_latest(aggregate_id)
        sequence = await self.event_store.get_sequence(aggregate_id)
        
        if not snapshot:
            return {
                "aggregate_id": aggregate_id,
                "has_snapshot": False,
                "current_sequence": sequence,
            }
        
        return {
            "aggregate_id": aggregate_id,
            "has_snapshot": True,
            "snapshot_sequence": snapshot.sequence,
            "current_sequence": sequence,
            "events_since_snapshot": sequence - snapshot.sequence,
            "snapshot_age": (datetime.now() - snapshot.created_at).total_seconds(),
        }
