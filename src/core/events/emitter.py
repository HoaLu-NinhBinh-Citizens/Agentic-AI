"""Event emitter module."""

from typing import Any, Callable


class EventEmitter:
    """Emits events to listeners."""
    
    def __init__(self):
        self._listeners: dict[str, list[Callable]] = {}
    
    def on(self, event: str, callback: Callable) -> None:
        """Register listener."""
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)
    
    async def emit(self, event: str, data: Any) -> None:
        """Emit event."""
        for callback in self._listeners.get(event, []):
            await callback(data)
