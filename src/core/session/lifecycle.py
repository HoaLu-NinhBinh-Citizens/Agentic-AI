"""Session lifecycle stub."""

from typing import Callable, Any


class SessionLifecycle:
    """Manages session lifecycle hooks."""
    
    def __init__(self):
        self._on_create: list[Callable] = []
        self._on_end: list[Callable] = []
    
    def on_create(self, callback: Callable[[str], Any]) -> None:
        """Register create callback."""
        self._on_create.append(callback)
    
    def on_end(self, callback: Callable[[str], Any]) -> None:
        """Register end callback."""
        self._on_end.append(callback)
    
    def trigger_create(self, session_id: str) -> None:
        """Trigger create callbacks."""
        for cb in self._on_create:
            cb(session_id)
    
    def trigger_end(self, session_id: str) -> None:
        """Trigger end callbacks."""
        for cb in self._on_end:
            cb(session_id)
