"""Checkpoint module."""

from typing import Any


class Checkpoint:
    """Execution checkpoint."""
    
    def __init__(self, id: str, data: dict[str, Any]):
        self.id = id
        self.data = data
