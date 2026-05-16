"""Snapshot module."""

from typing import Any


class Snapshot:
    """State snapshot."""
    
    def __init__(self):
        self._data: dict[str, Any] = {}
    
    def capture(self) -> dict[str, Any]:
        """Capture current state."""
        return self._data.copy()
    
    def restore(self, data: dict[str, Any]) -> None:
        """Restore from snapshot."""
        self._data = data.copy()
