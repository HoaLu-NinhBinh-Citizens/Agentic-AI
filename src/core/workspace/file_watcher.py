"""File watcher module."""

from typing import Any, Callable


class FileWatcher:
    """Watches filesystem for changes."""
    
    def __init__(self):
        self._callbacks: list[Callable] = []
    
    def watch(self, path: str, callback: Callable) -> None:
        """Watch path for changes."""
        self._callbacks.append(callback)
