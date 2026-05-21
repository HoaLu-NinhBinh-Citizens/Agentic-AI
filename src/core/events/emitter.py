"""Event emitter module."""

import time
from collections import deque
from typing import Any, Callable


class EventEmitter:
    """Emits events to listeners."""
    
    # Maximum events to store (prevents unbounded memory growth)
    MAX_EVENT_HISTORY = 1000
    
    def __init__(self, max_history: int = MAX_EVENT_HISTORY):
        self._listeners: dict[str, list[Callable]] = {}
        self._event_history: deque[tuple[float, str, Any]] = deque(maxlen=max_history)
    
    def on(self, event: str, callback: Callable) -> None:
        """Register listener."""
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)
    
    async def emit(self, event: str, data: Any) -> None:
        """Emit event."""
        # FIX: Track events for cleanup
        timestamp = time.time()
        self._event_history.append((timestamp, event, data))
        
        for callback in self._listeners.get(event, []):
            await callback(data)
    
    def get_event_history(self, event: str | None = None, limit: int = 100) -> list[tuple[float, str, Any]]:
        """Get recent event history.
        
        Args:
            event: Filter by event name (None = all events)
            limit: Maximum events to return
            
        Returns:
            List of (timestamp, event_name, data) tuples
        """
        if event:
            return [(ts, e, d) for ts, e, d in self._event_history if e == event][-limit:]
        return list(self._event_history)[-limit:]
    
    def clear_event_history(self) -> int:
        """Clear event history and return number of events removed.
        
        Returns:
            Number of events cleared
        """
        count = len(self._event_history)
        self._event_history.clear()
        return count
    
    def cleanup_old_events(self, max_age_seconds: float = 3600) -> int:
        """Remove events older than max_age_seconds.
        
        This prevents unbounded memory growth while preserving recent events.
        
        Args:
            max_age_seconds: Maximum age of events to keep
            
        Returns:
            Number of events removed
        """
        cutoff_time = time.time() - max_age_seconds
        original_count = len(self._event_history)
        
        # Filter out old events
        self._event_history = deque(
            ((ts, e, d) for ts, e, d in self._event_history if ts >= cutoff_time),
            maxlen=self.MAX_EVENT_HISTORY
        )
        
        return original_count - len(self._event_history)
    
    def get_stats(self) -> dict[str, Any]:
        """Get event emitter statistics.
        
        Returns:
            Dict with listener count, history size, event types
        """
        event_types = set(e for _, e, _ in self._event_history)
        return {
            "total_listeners": sum(len(l) for l in self._listeners.values()),
            "event_types": list(self._listeners.keys()),
            "history_size": len(self._event_history),
            "max_history": self.MAX_EVENT_HISTORY,
            "distinct_events_in_history": len(event_types),
        }
    
    def off(self, event: str, callback: Callable) -> bool:
        """Unregister a listener.
        
        Args:
            event: Event name
            callback: Callback to remove
            
        Returns:
            True if callback was removed
        """
        if event in self._listeners:
            try:
                self._listeners[event].remove(callback)
                return True
            except ValueError:
                pass
        return False
    
    def remove_all_listeners(self, event: str | None = None) -> int:
        """Remove all listeners for an event or all events.
        
        Args:
            event: Event name (None = all events)
            
        Returns:
            Number of listeners removed
        """
        if event:
            count = len(self._listeners.get(event, []))
            self._listeners.pop(event, None)
            return count
        else:
            count = sum(len(l) for l in self._listeners.values())
            self._listeners.clear()
            return count
