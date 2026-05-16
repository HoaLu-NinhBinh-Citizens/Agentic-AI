"""Working memory module."""

from typing import Any


class WorkingMemory:
    """Working memory for current task."""
    
    def __init__(self):
        self._data: dict[str, Any] = {}
    
    def set(self, key: str, value: Any) -> None:
        """Set value."""
        self._data[key] = value
    
    def get(self, key: str) -> Any | None:
        """Get value."""
        return self._data.get(key)
