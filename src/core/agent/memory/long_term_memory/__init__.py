"""LTM module."""

from typing import Any


class LongTermMemory:
    """Long-term memory storage."""
    
    def __init__(self):
        self._memories: dict[str, Any] = {}
    
    def store(self, key: str, value: Any) -> None:
        """Store memory."""
        self._memories[key] = value
    
    def retrieve(self, key: str) -> Any | None:
        """Retrieve memory."""
        return self._memories.get(key)
