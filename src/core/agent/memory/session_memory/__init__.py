"""Memory module."""

from typing import Any


class SessionMemory:
    """Session memory storage."""
    
    def __init__(self):
        self._memory: list[dict[str, Any]] = []
    
    def add(self, item: dict[str, Any]) -> None:
        """Add to memory."""
        self._memory.append(item)
    
    def get_all(self) -> list[dict[str, Any]]:
        """Get all memory."""
        return self._memory.copy()
