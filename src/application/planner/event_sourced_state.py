"""Event-sourced planner state - Phase 5B."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from .types import PlannerEvent, PlannerEventType


class PlannerEventStore:
    """Store interface for planner events."""
    
    async def append(self, event: PlannerEvent) -> None:
        """Append an event to the store."""
        raise NotImplementedError
    
    async def get_session_events(
        self,
        session_id: str,
    ) -> list[PlannerEvent]:
        """Get all events for a session."""
        raise NotImplementedError
    
    async def get_events_by_type(
        self,
        session_id: str,
        event_type: PlannerEventType,
    ) -> list[PlannerEvent]:
        """Get events by type for a session."""
        raise NotImplementedError
    
    async def delete_before(self, session_id: str, timestamp: int) -> int:
        """Delete events before timestamp."""
        raise NotImplementedError


class InMemoryPlannerEventStore(PlannerEventStore):
    """In-memory implementation of planner event store."""
    
    def __init__(self):
        self._events: list[PlannerEvent] = []
        self._session_index: dict[str, list[int]] = {}
    
    async def append(self, event: PlannerEvent) -> None:
        """Append an event to the store."""
        idx = len(self._events)
        self._events.append(event)
        
        if event.session_id not in self._session_index:
            self._session_index[event.session_id] = []
        self._session_index[event.session_id].append(idx)
    
    async def get_session_events(
        self,
        session_id: str,
    ) -> list[PlannerEvent]:
        """Get all events for a session."""
        if session_id not in self._session_index:
            return []
        
        return [
            self._events[idx]
            for idx in self._session_index[session_id]
        ]
    
    async def get_events_by_type(
        self,
        session_id: str,
        event_type: PlannerEventType,
    ) -> list[PlannerEvent]:
        """Get events by type for a session."""
        events = await self.get_session_events(session_id)
        return [e for e in events if e.event_type == event_type]
    
    async def delete_before(self, session_id: str, timestamp: int) -> int:
        """Delete events before timestamp."""
        events = await self.get_session_events(session_id)
        
        to_delete = [
            i for i, e in zip(
                self._session_index.get(session_id, []),
                events
            )
            if e.timestamp < timestamp
        ]
        
        for idx in sorted(to_delete, reverse=True):
            del self._events[idx]
        
        self._session_index[session_id] = [
            i for i in self._session_index.get(session_id, [])
            if i not in to_delete
        ]
        
        return len(to_delete)


class EventSourcedPlannerState:
    """Event-sourced planner state management.
    
    Records all planning events and enables crash recovery
    by replaying the event log.
    """
    
    def __init__(self, event_store: PlannerEventStore):
        self._store = event_store
        self._current_session: Optional[str] = None
    
    async def create_session(self) -> str:
        """Create a new planning session.
        
        Returns:
            Session ID for the new session
        """
        session_id = str(uuid.uuid4())
        self._current_session = session_id
        return session_id
    
    async def get_current_session(self) -> Optional[str]:
        """Get the current session ID."""
        return self._current_session
    
    async def set_current_session(self, session_id: str) -> None:
        """Set the current session ID."""
        self._current_session = session_id
    
    async def emit(
        self,
        event_type: PlannerEventType,
        data: Optional[dict] = None,
        session_id: Optional[str] = None,
    ) -> PlannerEvent:
        """Emit a planning event.
        
        Args:
            event_type: Type of event
            data: Event data
            session_id: Session ID (uses current if None)
            
        Returns:
            The created event
        """
        session = session_id or self._current_session
        
        if not session:
            raise ValueError("No session ID provided and no current session")
        
        event = PlannerEvent(
            event_id=str(uuid.uuid4()),
            session_id=session,
            event_type=event_type,
            data=data or {},
            timestamp=int(datetime.utcnow().timestamp()),
        )
        
        await self._store.append(event)
        
        return event
    
    async def emit_decompose_start(
        self,
        goal: str,
        session_id: Optional[str] = None,
    ) -> PlannerEvent:
        """Emit decomposition start event."""
        return await self.emit(
            PlannerEventType.DECOMPOSE_START,
            {"goal": goal},
            session_id,
        )
    
    async def emit_decompose_complete(
        self,
        task_count: int,
        session_id: Optional[str] = None,
    ) -> PlannerEvent:
        """Emit decomposition complete event."""
        return await self.emit(
            PlannerEventType.DECOMPOSE_COMPLETE,
            {"task_count": task_count},
            session_id,
        )
    
    async def emit_beam_search_step(
        self,
        step: int,
        candidates: int,
        session_id: Optional[str] = None,
    ) -> PlannerEvent:
        """Emit beam search step event."""
        return await self.emit(
            PlannerEventType.BEAM_SEARCH_STEP,
            {"step": step, "candidates": candidates},
            session_id,
        )
    
    async def emit_candidate_evaluated(
        self,
        candidate_id: str,
        score: float,
        session_id: Optional[str] = None,
    ) -> PlannerEvent:
        """Emit candidate evaluation event."""
        return await self.emit(
            PlannerEventType.CANDIDATE_EVALUATED,
            {"candidate_id": candidate_id, "score": score},
            session_id,
        )
    
    async def emit_retrieved_template(
        self,
        template_id: str,
        quality: float,
        session_id: Optional[str] = None,
    ) -> PlannerEvent:
        """Emit template retrieval event."""
        return await self.emit(
            PlannerEventType.RETRIEVED_TEMPLATE,
            {"template_id": template_id, "quality": quality},
            session_id,
        )
    
    async def emit_plan_selected(
        self,
        plan_id: str,
        reason: str,
        session_id: Optional[str] = None,
    ) -> PlannerEvent:
        """Emit plan selection event."""
        return await self.emit(
            PlannerEventType.PLAN_SELECTED,
            {"plan_id": plan_id, "reason": reason},
            session_id,
        )
    
    async def get_session_events(
        self,
        session_id: str,
    ) -> list[PlannerEvent]:
        """Get all events for a session."""
        return await self._store.get_session_events(session_id)
    
    async def replay_session(
        self,
        session_id: str,
    ) -> list[PlannerEvent]:
        """Replay all events for a session.
        
        Used for crash recovery and debugging.
        
        Returns:
            List of events in order
        """
        return await self._store.get_session_events(session_id)
    
    async def get_event_summary(
        self,
        session_id: str,
    ) -> dict:
        """Get a summary of events for a session."""
        events = await self.get_session_events(session_id)
        
        event_counts = {}
        for event in events:
            event_type = event.event_type.value
            event_counts[event_type] = event_counts.get(event_type, 0) + 1
        
        return {
            "session_id": session_id,
            "total_events": len(events),
            "event_counts": event_counts,
            "start_time": events[0].timestamp if events else None,
            "end_time": events[-1].timestamp if events else None,
        }
    
    async def cleanup_old_events(
        self,
        session_id: str,
        retention_days: int = 30,
    ) -> int:
        """Clean up old events for a session.
        
        Args:
            session_id: Session ID
            retention_days: Number of days to retain
            
        Returns:
            Number of events deleted
        """
        cutoff = int(
            datetime.utcnow().timestamp() - (retention_days * 86400)
        )
        return await self._store.delete_before(session_id, cutoff)


class PlannerEventEmitter:
    """Convenience wrapper for emitting planner events."""
    
    def __init__(self, state: EventSourcedPlannerState):
        self._state = state
    
    async def __aenter__(self) -> PlannerEventEmitter:
        """Create a new session on context enter."""
        await self._state.create_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context exit."""
        pass
    
    async def emit(
        self,
        event_type: PlannerEventType,
        data: Optional[dict] = None,
    ) -> PlannerEvent:
        """Emit an event in the current session."""
        return await self._state.emit(event_type, data)
    
    def __getattr__(self, name: str):
        """Proxy attribute access to state."""
        if name.startswith("emit_"):
            event_type_name = name[5:].upper()
            try:
                event_type = PlannerEventType[event_type_name]
            except KeyError:
                raise AttributeError(name)
            
            async def emit_wrapper(data: Optional[dict] = None) -> PlannerEvent:
                return await self._state.emit(event_type, data)
            
            return emit_wrapper
        
        return getattr(self._state, name)
