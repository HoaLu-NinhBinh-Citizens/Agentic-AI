"""Counter metrics stub."""

from typing import Any


class Counter:
    """Simple counter metric."""
    
    def __init__(self, name: str):
        self.name = name
        self._value = 0
    
    def increment(self, value: int = 1) -> None:
        """Increment counter."""
        self._value += value
    
    def get(self) -> int:
        """Get current value."""
        return self._value
