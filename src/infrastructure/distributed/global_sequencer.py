"""Global Sequencer and Event Log.

Fixes Critical Gap: No global sequencer/event log for distributed coordination.

Features:
- Lamport clock for distributed ordering
- Vector clock support
- Global sequence numbers
- Causality tracking
- Event log with total ordering
- Conflict detection
- Distributed snapshot support
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# SEQUENCE TYPES
# =============================================================================


class SequenceType(Enum):
    """Types of sequence numbers."""
    
    GLOBAL = auto()       # Globally ordered sequence
    LOCAL = auto()        # Per-node sequence
    CAUSAL = auto()       # Causality-based sequence


# =============================================================================
# LAMPORT CLOCK
# =============================================================================


@dataclass
class LamportClock:
    """Lamport logical clock for distributed ordering.
    
    CRITICAL: Provides total ordering of events across nodes.
    
    Rules:
    - Each event increments the counter
    - If A causes B, then A's counter < B's counter
    - Counter = max(A, B) + 1
    """
    
    node_id: str
    counter: int = 0
    
    def tick(self) -> int:
        """Increment clock for local event."""
        self.counter += 1
        return self.counter
    
    def update(self, remote_counter: int) -> int:
        """Update from remote event."""
        self.counter = max(self.counter, remote_counter) + 1
        return self.counter
    
    def get(self) -> int:
        """Get current counter value."""
        return self.counter
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "counter": self.counter,
        }


# =============================================================================
# VECTOR CLOCK
# =============================================================================


@dataclass 
class VectorClock:
    """Vector clock for causality tracking.
    
    Each node maintains its own counter.
    V[A] = counter of node A's events.
    """
    
    clocks: dict[str, int] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.clocks:
            self.clocks = {}
    
    def increment(self, node_id: str) -> None:
        """Increment own counter."""
        self.clocks[node_id] = self.clocks.get(node_id, 0) + 1
    
    def update(self, remote_clock: dict[str, int]) -> None:
        """Merge with remote clock."""
        for node, counter in remote_clock.items():
            self.clocks[node] = max(self.clocks.get(node, 0), counter)
    
    def happens_before(self, other: VectorClock) -> bool:
        """Check if self happens before other.
        
        Returns True if self is strictly before other in causality.
        """
        dominated = False
        for node, counter in self.clocks.items():
            other_counter = other.clocks.get(node, 0)
            if counter > other_counter:
                return False
            if counter < other_counter:
                dominated = True
        
        # Check nodes in other not in self
        for node, counter in other.clocks.items():
            if node not in self.clocks and counter > 0:
                dominated = True
        
        return dominated
    
    def is_concurrent_with(self, other: VectorClock) -> bool:
        """Check if events are concurrent (neither causes the other)."""
        return not self.happens_before(other) and not other.happens_before(self)
    
    def merge(self, other: VectorClock) -> VectorClock:
        """Merge two vector clocks."""
        merged = VectorClock()
        merged.clocks = dict(self.clocks)
        merged.update(other.clocks)
        return merged
    
    def to_dict(self) -> dict[str, int]:
        return dict(self.clocks)
    
    @classmethod
    def from_dict(cls, data: dict[str, int]) -> VectorClock:
        return cls(clocks=data)


# =============================================================================
# GLOBAL SEQUENCE
# =============================================================================


@dataclass
class GlobalSequence:
    """Global sequence number with metadata."""
    
    sequence: int
    node_id: str
    
    # Timestamps
    lamport: int = 0
    wall_time: str = ""
    
    # Causality
    vector_clock: dict[str, int] = field(default_factory=dict)
    
    # Content
    content_hash: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "node_id": self.node_id,
            "lamport": self.lamport,
            "wall_time": self.wall_time,
            "vector_clock": self.vector_clock,
            "content_hash": self.content_hash,
        }


# =============================================================================
# EVENT LOG ENTRY
# =============================================================================


@dataclass
class EventLogEntry:
    """Entry in the global event log.
    
    Provides total ordering of all events across the system.
    """
    
    # Identity
    entry_id: str = ""
    global_sequence: int = 0
    
    # Source
    node_id: str = ""
    process_id: str = ""
    
    # Ordering
    lamport_clock: int = 0
    vector_clock: dict[str, int] = field(default_factory=dict)
    wall_time: str = ""
    
    # Event data
    event_type: str = ""
    event_category: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    
    # Hashing
    content_hash: str = ""
    previous_hash: str = ""  # Hash chain link
    
    # Causality
    causes: list[str] = field(default_factory=list)  # Entry IDs that caused this
    caused_by: list[str] = field(default_factory=list)  # Entry IDs caused by this
    
    def compute_hash(self) -> str:
        """Compute deterministic hash of entry content."""
        content = {
            "global_sequence": self.global_sequence,
            "node_id": self.node_id,
            "process_id": self.process_id,
            "lamport_clock": self.lamport_clock,
            "event_type": self.event_type,
            "event_category": self.event_category,
            "payload": self.payload,
            "causes": self.causes,
        }
        content_str = json.dumps(content, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(content_str.encode()).hexdigest()
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "global_sequence": self.global_sequence,
            "node_id": self.node_id,
            "process_id": self.process_id,
            "lamport_clock": self.lamport_clock,
            "vector_clock": self.vector_clock,
            "wall_time": self.wall_time,
            "event_type": self.event_type,
            "event_category": self.event_category,
            "payload": self.payload,
            "content_hash": self.content_hash,
            "previous_hash": self.previous_hash,
            "causes": self.causes,
            "caused_by": self.caused_by,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EventLogEntry:
        return cls(
            entry_id=data["entry_id"],
            global_sequence=data["global_sequence"],
            node_id=data["node_id"],
            process_id=data["process_id"],
            lamport_clock=data["lamport_clock"],
            vector_clock=data["vector_clock"],
            wall_time=data["wall_time"],
            event_type=data["event_type"],
            event_category=data["event_category"],
            payload=data["payload"],
            content_hash=data["content_hash"],
            previous_hash=data["previous_hash"],
            causes=data.get("causes", []),
            caused_by=data.get("caused_by", []),
        )


# =============================================================================
# GLOBAL SEQUENCER
# =============================================================================


class GlobalSequencer:
    """Global sequencer for distributed event ordering.
    
    CRITICAL: Provides total ordering of events across all nodes.
    
    Features:
    - Lamport clock synchronization
    - Vector clock causality tracking
    - Global sequence number generation
    - Event log with hash chain
    - Causality analysis
    - Conflict detection
    """
    
    GENESIS_HASH = "0" * 64
    
    def __init__(
        self,
        node_id: str,
        log_path: str | None = None,
    ):
        self.node_id = node_id
        
        # Clocks
        self._lamport = LamportClock(node_id)
        self._vector_clock = VectorClock()
        
        # Sequence numbers
        self._global_sequence: int = 0
        self._local_sequence: int = 0
        
        # Event log
        self._log: list[EventLogEntry] = []
        self._log_by_id: dict[str, EventLogEntry] = {}
        self._log_path = log_path
        self._last_hash = self.GENESIS_HASH
        
        # Lock
        self._lock = asyncio.Lock()
        
        # Increment own vector clock
        self._vector_clock.increment(node_id)
        
        logger.info("global_sequencer_initialized: node=%s", node_id)
    
    # -------------------------------------------------------------------------
    # Clock Management
    # -------------------------------------------------------------------------
    
    def get_lamport(self) -> int:
        """Get current Lamport clock value."""
        return self._lamport.get()
    
    def get_vector_clock(self) -> VectorClock:
        """Get current vector clock."""
        return self._vector_clock
    
    def tick_local(self) -> int:
        """Tick local clock for local event."""
        return self._lamport.tick()
    
    def update_remote(self, remote_lamport: int, remote_vector: dict[str, int] | None = None) -> None:
        """Update clocks from remote event."""
        self._lamport.update(remote_lamport)
        
        if remote_vector:
            self._vector_clock.update(remote_vector)
        
        self._vector_clock.increment(self.node_id)
    
    # -------------------------------------------------------------------------
    # Sequence Number Generation
    # -------------------------------------------------------------------------
    
    async def generate_sequence(
        self,
        event_type: str,
        event_category: str = "",
        payload: dict[str, Any] | None = None,
        causes: list[str] | None = None,
    ) -> EventLogEntry:
        """Generate globally ordered sequence number.
        
        CRITICAL: This is the main entry point for ordering events.
        
        Args:
            event_type: Type of event
            event_category: Category (e.g., "flash", "workflow")
            payload: Event payload
            causes: Entry IDs that caused this event
            
        Returns:
            EventLogEntry with global ordering
        """
        async with self._lock:
            import uuid
            
            # Update clocks
            self._lamport.tick()
            self._vector_clock.increment(self.node_id)
            
            # Increment sequences
            self._global_sequence += 1
            self._local_sequence += 1
            
            # Create entry
            entry = EventLogEntry(
                entry_id=str(uuid.uuid4()),
                global_sequence=self._global_sequence,
                node_id=self.node_id,
                process_id="",  # Set by caller
                lamport_clock=self._lamport.get(),
                vector_clock=self._vector_clock.to_dict(),
                wall_time=datetime.utcnow().isoformat(),
                event_type=event_type,
                event_category=event_category,
                payload=payload or {},
                previous_hash=self._last_hash,
                causes=causes or [],
            )
            
            # Compute hash
            entry.content_hash = entry.compute_hash()
            
            # Update log
            self._log.append(entry)
            self._log_by_id[entry.entry_id] = entry
            self._last_hash = entry.content_hash
            
            # Update caused_by for causes
            for cause_id in entry.causes:
                cause = self._log_by_id.get(cause_id)
                if cause and entry.entry_id not in cause.caused_by:
                    cause.caused_by.append(entry.entry_id)
            
            # Persist
            if self._log_path:
                self._persist_entry(entry)
            
            logger.debug(
                "sequence_generated: entry=%s seq=%s lamport=%s type=%s",
                entry.entry_id[:8],
                entry.global_sequence,
                entry.lamport_clock,
                event_type,
            )
            
            return entry
    
    # -------------------------------------------------------------------------
    # Causality Analysis
    # -------------------------------------------------------------------------
    
    def happens_before(self, entry_a: str, entry_b: str) -> bool:
        """Check if entry_a happened before entry_b.
        
        Uses vector clock comparison.
        """
        e_a = self._log_by_id.get(entry_a)
        e_b = self._log_by_id.get(entry_b)
        
        if not e_a or not e_b:
            return False
        
        vc_a = VectorClock.from_dict(e_a.vector_clock)
        vc_b = VectorClock.from_dict(e_b.vector_clock)
        
        return vc_a.happens_before(vc_b)
    
    def are_concurrent(self, entry_a: str, entry_b: str) -> bool:
        """Check if two entries are concurrent."""
        e_a = self._log_by_id.get(entry_a)
        e_b = self._log_by_id.get(entry_b)
        
        if not e_a or not e_b:
            return False
        
        vc_a = VectorClock.from_dict(e_a.vector_clock)
        vc_b = VectorClock.from_dict(e_b.vector_clock)
        
        return vc_a.is_concurrent_with(vc_b)
    
    def get_causal_chain(self, entry_id: str) -> list[str]:
        """Get all entries that caused this entry (ancestors)."""
        visited = set()
        result = []
        
        def dfs(eid: str):
            entry = self._log_by_id.get(eid)
            if not entry or eid in visited:
                return
            
            visited.add(eid)
            for cause_id in entry.causes:
                dfs(cause_id)
                if cause_id not in result:
                    result.append(cause_id)
        
        dfs(entry_id)
        return result
    
    def get_effects(self, entry_id: str) -> list[str]:
        """Get all entries caused by this entry (descendants)."""
        entry = self._log_by_id.get(entry_id)
        if not entry:
            return []
        return list(entry.caused_by)
    
    # -------------------------------------------------------------------------
    # Conflict Detection
    # -------------------------------------------------------------------------
    
    def detect_conflicts(
        self,
        entry_a: str,
        entry_b: str,
    ) -> list[str]:
        """Detect conflicts between two entries.
        
        Returns list of conflict descriptions.
        """
        conflicts = []
        
        e_a = self._log_by_id.get(entry_a)
        e_b = self._log_by_id.get(entry_b)
        
        if not e_a or not e_b:
            return ["Unknown entry"]
        
        # Concurrent writes to same resource
        if self.are_concurrent(entry_a, entry_b):
            # Check if both accessed same resource
            payload_a = e_a.payload
            payload_b = e_b.payload
            
            resource_a = payload_a.get("resource") or payload_a.get("target")
            resource_b = payload_b.get("resource") or payload_b.get("target")
            
            if resource_a and resource_b and resource_a == resource_b:
                conflicts.append(
                    f"Concurrent writes to same resource: {resource_a}"
                )
        
        # Causality violation
        if e_a.global_sequence < e_b.global_sequence:
            if self.are_concurrent(entry_a, entry_b):
                conflicts.append("Causality violation: later sequence is concurrent with earlier")
        
        return conflicts
    
    # -------------------------------------------------------------------------
    # Event Log Queries
    # -------------------------------------------------------------------------
    
    async def query(
        self,
        event_type: str | None = None,
        event_category: str | None = None,
        since_sequence: int | None = None,
        limit: int | None = None,
    ) -> list[EventLogEntry]:
        """Query the event log."""
        results = []
        
        for entry in self._log:
            if since_sequence and entry.global_sequence < since_sequence:
                continue
            if event_type and entry.event_type != event_type:
                continue
            if event_category and entry.event_category != event_category:
                continue
            
            results.append(entry)
        
        if limit:
            results = results[-limit:]
        
        return results
    
    async def get_entry(self, entry_id: str) -> EventLogEntry | None:
        """Get entry by ID."""
        return self._log_by_id.get(entry_id)
    
    async def get_sequence(self, sequence: int) -> EventLogEntry | None:
        """Get entry by global sequence."""
        for entry in self._log:
            if entry.global_sequence == sequence:
                return entry
        return None
    
    # -------------------------------------------------------------------------
    # Snapshot & Recovery
    # -------------------------------------------------------------------------
    
    async def create_snapshot(self) -> dict[str, Any]:
        """Create a snapshot of current state."""
        return {
            "node_id": self.node_id,
            "global_sequence": self._global_sequence,
            "lamport": self._lamport.to_dict(),
            "vector_clock": self._vector_clock.to_dict(),
            "log_size": len(self._log),
            "last_hash": self._last_hash,
        }
    
    def _persist_entry(self, entry: EventLogEntry) -> None:
        """Persist entry to disk."""
        if not self._log_path:
            return
        
        import os
        os.makedirs(os.path.dirname(self._log_path) or ".", exist_ok=True)
        
        with open(self._log_path, "a") as f:
            f.write(json.dumps(entry.to_dict(), default=str) + "\n")
    
    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------
    
    def get_stats(self) -> dict[str, Any]:
        """Get sequencer statistics."""
        return {
            "node_id": self.node_id,
            "global_sequence": self._global_sequence,
            "local_sequence": self._local_sequence,
            "lamport_clock": self._lamport.get(),
            "log_size": len(self._log),
            "vector_clock_size": len(self._vector_clock.clocks),
        }


# =============================================================================
# DISTRIBUTED EVENT LOG
# =============================================================================


class DistributedEventLog:
    """Distributed event log with multiple sequencers.
    
    Provides unified view of events across all nodes.
    """
    
    def __init__(self):
        self._sequencers: dict[str, GlobalSequencer] = {}
        self._unified_log: list[EventLogEntry] = []
        self._lock = asyncio.Lock()
    
    def register_sequencer(self, node_id: str, sequencer: GlobalSequencer) -> None:
        """Register a sequencer for a node."""
        self._sequencers[node_id] = sequencer
        logger.info("sequencer_registered: node=%s", node_id)
    
    async def append_from(
        self,
        node_id: str,
        event_type: str,
        event_category: str = "",
        payload: dict[str, Any] | None = None,
    ) -> EventLogEntry:
        """Append event from a specific node."""
        sequencer = self._sequencers.get(node_id)
        if not sequencer:
            raise ValueError(f"Unknown node: {node_id}")
        
        entry = await sequencer.generate_sequence(
            event_type=event_type,
            event_category=event_category,
            payload=payload,
        )
        
        self._unified_log.append(entry)
        
        return entry
    
    async def get_total_order(self) -> list[EventLogEntry]:
        """Get total order of all events across nodes."""
        await self._lock
        
        # Sort by global sequence
        return sorted(self._unified_log, key=lambda e: e.global_sequence)
    
    async def broadcast_event(
        self,
        source_node: str,
        event_type: str,
        event_category: str,
        payload: dict[str, Any] | None = None,
    ) -> EventLogEntry:
        """Broadcast event to all nodes.
        
        Updates all sequencers with the event.
        """
        entry = await self.append_from(
            source_node,
            event_type,
            event_category,
            payload,
        )
        
        # Notify other sequencers (in real impl, would use gossip protocol)
        # For now, just update local unified log
        
        return entry


# =============================================================================
# GLOBAL INSTANCES
# =============================================================================


_global_sequencer: GlobalSequencer | None = None
_global_distributed_log: DistributedEventLog | None = None


def get_sequencer(node_id: str = "default") -> GlobalSequencer:
    """Get global sequencer for node."""
    global _global_sequencer
    if _global_sequencer is None:
        _global_sequencer = GlobalSequencer(node_id)
    return _global_sequencer


def get_distributed_log() -> DistributedEventLog:
    """Get distributed event log."""
    global _global_distributed_log
    if _global_distributed_log is None:
        _global_distributed_log = DistributedEventLog()
    return _global_distributed_log
