"""Deterministic replay for debugging (Phase 13.2).

Provides deterministic replay of workspace state:
- Snapshot workspace state
- Replay I/O operations
- Deterministic execution recording
- Session replay for debugging
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Types of replayable events."""
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    NETWORK_REQUEST = "network_request"
    SHELL_COMMAND = "shell_command"
    API_CALL = "api_call"
    LLM_INFERENCE = "llm_inference"


from enum import Enum


@dataclass
class ReplayEvent:
    """Single event in replay sequence."""
    event_id: str
    event_type: EventType
    timestamp: datetime
    data: dict[str, Any]
    deterministic_hash: str = ""
    
    def compute_hash(self) -> str:
        """Compute deterministic hash."""
        content = f"{self.event_type.value}:{json.dumps(self.data, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class WorkspaceSnapshot:
    """Point-in-time workspace state."""
    snapshot_id: str
    session_id: str
    created_at: datetime
    
    # Files
    file_states: dict[str, str] = field(default_factory=dict)  # path -> content hash
    
    # Environment
    environment: dict[str, str] = field(default_factory=dict)
    working_directory: str = ""
    
    # Metadata
    checksum: str = ""
    size_bytes: int = 0


@dataclass
class ReplaySession:
    """Complete replay session."""
    session_id: str
    start_time: datetime
    end_time: datetime | None = None
    
    # Events
    events: list[ReplayEvent] = field(default_factory=list)
    
    # Snapshots
    initial_snapshot: WorkspaceSnapshot | None = None
    final_snapshot: WorkspaceSnapshot | None = None
    
    # Metadata
    deterministic: bool = True
    replay_count: int = 0


class DeterministicReplay:
    """Deterministic replay system.
    
    Phase 13.2: Deterministic replay
    """
    
    def __init__(self, storage_dir: Path | None = None) -> None:
        self._storage_dir = storage_dir or Path("data/replay")
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, ReplaySession] = {}
        self._current_session: ReplaySession | None = None
    
    def start_session(self, session_id: str) -> ReplaySession:
        """Start a new replay session."""
        session = ReplaySession(
            session_id=session_id,
            start_time=datetime.now(),
        )
        self._sessions[session_id] = session
        self._current_session = session
        logger.info("Started replay session", session_id=session_id)
        return session
    
    def end_session(self) -> ReplaySession | None:
        """End current replay session."""
        if self._current_session:
            self._current_session.end_time = datetime.now()
            session = self._current_session
            self._current_session = None
            
            # Verify determinism
            self._verify_determinism(session)
            
            # Save session
            self._save_session(session)
            
            logger.info(
                "Ended replay session",
                session_id=session.session_id,
                events=len(session.events),
                deterministic=session.deterministic,
            )
            return session
        return None
    
    def record_event(
        self,
        event_type: EventType,
        data: dict[str, Any],
    ) -> ReplayEvent:
        """Record an event in current session."""
        if not self._current_session:
            raise RuntimeError("No active replay session")
        
        event = ReplayEvent(
            event_id=self._generate_id(),
            event_type=event_type,
            timestamp=datetime.now(),
            data=data,
        )
        event.deterministic_hash = event.compute_hash()
        
        self._current_session.events.append(event)
        return event
    
    def _verify_determinism(self, session: ReplaySession) -> bool:
        """Verify session is deterministic.
        
        A session is deterministic if all event hashes are unique (no duplicate
        events with same content). This ensures replay will produce identical results.
        """
        if len(session.events) < 2:
            session.deterministic = True
            return True
        
        # Check if hashes are unique - duplicates break determinism
        hashes = [e.deterministic_hash for e in session.events]
        unique_hashes = set(hashes)
        
        # Deterministic only if all hashes are unique
        session.deterministic = len(hashes) == len(unique_hashes)
        
        if not session.deterministic:
            # Find duplicates for debugging
            from collections import Counter
            duplicates = [h for h, count in Counter(hashes).items() if count > 1]
            logger.warning(
                "session_not_deterministic",
                session_id=session.session_id,
                total_events=len(hashes),
                unique_hashes=len(unique_hashes),
                duplicate_count=len(duplicates),
                duplicate_hashes=duplicates[:5],  # Log first 5
            )
        
        return session.deterministic
    
    def replay(
        self,
        session_id: str,
        event_filter: list[EventType] | None = None,
    ) -> list[ReplayEvent]:
        """Replay a session's events."""
        session = self._sessions.get(session_id)
        if not session:
            logger.warning("Session not found", session_id=session_id)
            return []
        
        events = session.events
        if event_filter:
            events = [e for e in events if e.event_type in event_filter]
        
        session.replay_count += 1
        
        logger.info("Replaying session", session_id=session_id, events=len(events))
        return events
    
    def _save_session(self, session: ReplaySession) -> Path:
        """Save session to disk."""
        filename = f"session_{session.session_id}.json"
        filepath = self._storage_dir / filename
        
        data = {
            "session_id": session.session_id,
            "start_time": session.start_time.isoformat(),
            "end_time": session.end_time.isoformat() if session.end_time else None,
            "events": [
                {
                    "event_id": e.event_id,
                    "event_type": e.event_type.value,
                    "timestamp": e.timestamp.isoformat(),
                    "data": e.data,
                    "hash": e.deterministic_hash,
                }
                for e in session.events
            ],
            "deterministic": session.deterministic,
            "replay_count": session.replay_count,
        }
        
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        
        return filepath
    
    def get_session(self, session_id: str) -> ReplaySession | None:
        """Get session by ID."""
        return self._sessions.get(session_id)
    
    def list_sessions(self) -> list[str]:
        """List all sessions."""
        return list(self._sessions.keys())


# Global singleton
_replay: DeterministicReplay | None = None


def get_deterministic_replay() -> DeterministicReplay:
    """Get global deterministic replay."""
    global _replay
    if _replay is None:
        _replay = DeterministicReplay()
    return _replay
