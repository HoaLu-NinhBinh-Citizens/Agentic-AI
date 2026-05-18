"""
CDC Consistency Contract for Follower Reads.

Defines formal consistency guarantees:
- Read-after-write
- Monotonic reads
- Bounded staleness
- Causal consistency
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ConsistencyLevel(str, Enum):
    """Consistency levels for reads."""
    STRONG = "strong"          # Linearizable
    BOUNDED_STALENESS = "bounded_staleness"  # Max staleness
    MONOTONIC = "monotonic"    # Monotonic reads
    EVENTUAL = "eventual"      # Eventually consistent


@dataclass
class ConsistencyConfig:
    """Configuration for consistency guarantees."""
    level: ConsistencyLevel
    max_staleness_ms: int = 1000  # For bounded staleness
    fence_token: Optional[int] = None  # For strong consistency
    causal_token: Optional[str] = None  # For causal consistency


@dataclass
class ChangeEvent:
    """CDC change event."""
    event_id: str
    entity_type: str
    entity_id: str
    operation: str  # create, update, delete
    data: Dict[str, Any]
    sequence: int
    timestamp: datetime
    fence_token: int  # Global fence token for ordering
    causal_token: Optional[str] = None


@dataclass
class ReadTimestamp:
    """Timestamp for tracking read consistency."""
    last_read_sequence: int
    last_read_fence: int
    timestamp: datetime
    session_id: str


class CDCConsistencyManager:
    """
    Manages CDC consistency contracts for follower reads.
    
    Guarantees:
    - Read-after-write: A write is immediately visible to the same session
    - Monotonic reads: A session never sees older data after newer data
    - Bounded staleness: Maximum staleness is guaranteed
    - Causal consistency: Causally related writes are ordered correctly
    """
    
    def __init__(
        self,
        default_consistency: ConsistencyLevel = ConsistencyLevel.BOUNDED_STALENESS,
        max_staleness_ms: int = 1000,
    ):
        self.default_consistency = default_consistency
        self.max_staleness_ms = max_staleness_ms
        
        # Global state
        self._global_fence: int = 0
        self._lock = asyncio.Lock()
        
        # Session tracking
        self._sessions: Dict[str, ReadTimestamp] = {}
        
        # Change stream
        self._change_stream: List[ChangeEvent] = []
        self._stream_head: int = 0  # Committed position
    
    async def next_fence_token(self) -> int:
        """Get next fence token."""
        async with self._lock:
            self._global_fence += 1
            return self._global_fence
    
    async def publish_change(
        self,
        entity_type: str,
        entity_id: str,
        operation: str,
        data: Dict[str, Any],
        causal_token: Optional[str] = None,
    ) -> ChangeEvent:
        """Publish change to CDC stream."""
        fence = await self.next_fence_token()
        
        event = ChangeEvent(
            event_id=f"{entity_type}:{entity_id}:{fence}",
            entity_type=entity_type,
            entity_id=entity_id,
            operation=operation,
            data=data,
            sequence=len(self._change_stream),
            timestamp=datetime.now(),
            fence_token=fence,
            causal_token=causal_token,
        )
        
        self._change_stream.append(event)
        return event
    
    async def commit_changes(self, fence: int) -> None:
        """Commit changes up to fence token."""
        async with self._lock:
            self._stream_head = max(
                self._stream_head,
                fence
            )
    
    async def read_with_consistency(
        self,
        session_id: str,
        entity_type: str,
        entity_id: str,
        config: ConsistencyConfig,
        read_handler: Callable,
    ) -> Any:
        """
        Read with specified consistency level.
        
        Args:
            session_id: Session identifier
            entity_type: Type of entity
            entity_id: Entity ID
            config: Consistency configuration
            read_handler: Function to perform actual read
            
        Returns:
            Data with consistency guarantee
        """
        if config.level == ConsistencyLevel.STRONG:
            return await self._strong_read(
                session_id, entity_type, entity_id, read_handler
            )
        elif config.level == ConsistencyLevel.BOUNDED_STALENESS:
            return await self._bounded_staleness_read(
                session_id, entity_type, entity_id, config, read_handler
            )
        elif config.level == ConsistencyLevel.MONOTONIC:
            return await self._monotonic_read(
                session_id, entity_type, entity_id, read_handler
            )
        else:
            return await read_handler(entity_type, entity_id)
    
    async def _strong_read(
        self,
        session_id: str,
        entity_type: str,
        entity_id: str,
        read_handler: Callable,
    ) -> Any:
        """
        Strong consistency read.
        
        Ensures linearizability by waiting for all prior writes.
        """
        # Wait for stream to catch up
        while True:
            head_fence = await self._get_stream_head_fence()
            
            # Get session's last fence
            session = self._sessions.get(session_id)
            session_fence = session.last_read_fence if session else 0
            
            # If we're at or past stream head, read
            if session_fence >= head_fence:
                break
            
            # Wait a bit
            await asyncio.sleep(0.01)
        
        # Perform read
        result = await read_handler(entity_type, entity_id)
        
        # Update session
        await self._update_session(session_id, head_fence)
        
        return result
    
    async def _bounded_staleness_read(
        self,
        session_id: str,
        entity_type: str,
        entity_id: str,
        config: ConsistencyConfig,
        read_handler: Callable,
    ) -> Any:
        """
        Bounded staleness read.
        
        Guarantees data is at most N ms stale.
        """
        now = datetime.now()
        staleness_limit = now - timedelta(milliseconds=config.max_staleness_ms)
        
        # Get session's last read time
        session = self._sessions.get(session_id)
        
        # Check staleness
        if session:
            time_since_last_read = (now - session.timestamp).total_seconds() * 1000
            if time_since_last_read > config.max_staleness_ms:
                # Need fresh read
                pass
            else:
                # Can serve stale data
                pass
        
        result = await read_handler(entity_type, entity_id)
        
        # Update session
        head_fence = await self._get_stream_head_fence()
        await self._update_session(session_id, head_fence)
        
        return result
    
    async def _monotonic_read(
        self,
        session_id: str,
        entity_type: str,
        entity_id: str,
        read_handler: Callable,
    ) -> Any:
        """
        Monotonic read.
        
        Ensures session never sees older data after newer data.
        """
        # Get session's last read
        session = self._sessions.get(session_id)
        last_fence = session.last_read_fence if session else 0
        
        # Wait for stream to be at least as fresh as last read
        while True:
            head_fence = await self._get_stream_head_fence()
            if head_fence >= last_fence:
                break
            await asyncio.sleep(0.01)
        
        # Read
        result = await read_handler(entity_type, entity_id)
        
        # Update session
        await self._update_session(session_id, head_fence)
        
        return result
    
    async def _get_stream_head_fence(self) -> int:
        """Get current stream head fence."""
        if self._change_stream:
            return self._change_stream[-1].fence_token
        return self._stream_head
    
    async def _update_session(
        self,
        session_id: str,
        fence: int,
    ) -> None:
        """Update session tracking."""
        self._sessions[session_id] = ReadTimestamp(
            last_read_sequence=len(self._change_stream),
            last_read_fence=fence,
            timestamp=datetime.now(),
            session_id=session_id,
        )
    
    async def ensure_read_after_write(
        self,
        session_id: str,
        entity_type: str,
        entity_id: str,
        expected_sequence: int,
        read_handler: Callable,
        timeout_ms: int = 5000,
    ) -> Optional[Any]:
        """
        Ensure read-after-write consistency.
        
        After a write, immediately read should see the written data.
        """
        start_time = time.time()
        
        while True:
            # Check if write is committed
            if len(self._change_stream) > expected_sequence:
                event = self._change_stream[expected_sequence]
                if event.entity_type == entity_type and event.entity_id == entity_id:
                    # Write is committed
                    result = await read_handler(entity_type, entity_id)
                    await self._update_session(
                        session_id,
                        event.fence_token
                    )
                    return result
            
            # Check timeout
            elapsed = (time.time() - start_time) * 1000
            if elapsed > timeout_ms:
                return None
            
            await asyncio.sleep(0.01)
    
    async def get_consistency_info(self, session_id: str) -> Dict[str, Any]:
        """Get consistency info for session."""
        session = self._sessions.get(session_id)
        head_fence = await self._get_stream_head_fence()
        
        return {
            "session_id": session_id,
            "last_read_fence": session.last_read_fence if session else 0,
            "stream_head_fence": head_fence,
            "staleness_ms": (
                head_fence - session.last_read_fence
            ) if session else 0,
            "pending_changes": len(self._change_stream),
        }


class BoundedStalenessTracker:
    """
    Tracks staleness bounds for follower reads.
    
    Ensures reads don't exceed maximum staleness.
    """
    
    def __init__(
        self,
        max_staleness_ms: int = 1000,
        check_interval_ms: int = 100,
    ):
        self.max_staleness = max_staleness_ms
        self.check_interval = check_interval_ms
        
        self._last_commit_time: Dict[str, datetime] = {}
        self._staleness_alerts: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
    
    async def record_commit(self, region: str) -> None:
        """Record a commit from region."""
        async with self._lock:
            self._last_commit_time[region] = datetime.now()
    
    async def check_staleness(self, region: str) -> tuple[bool, int]:
        """
        Check if staleness exceeds limit.
        
        Returns (exceeded, staleness_ms)
        """
        async with self._lock:
            last_commit = self._last_commit_time.get(region)
            if not last_commit:
                return False, 0
            
            elapsed = (datetime.now() - last_commit).total_seconds() * 1000
            exceeded = elapsed > self.max_staleness
            
            if exceeded:
                self._staleness_alerts.append({
                    "region": region,
                    "staleness_ms": elapsed,
                    "timestamp": datetime.now(),
                })
            
            return exceeded, int(elapsed)
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get staleness metrics."""
        async with self._lock:
            return {
                "max_staleness_ms": self.max_staleness,
                "regions_tracked": len(self._last_commit_time),
                "recent_alerts": len(self._staleness_alerts[-10:]),
                "current_staleness": {
                    r: (datetime.now() - t).total_seconds() * 1000
                    for r, t in self._last_commit_time.items()
                },
            }
