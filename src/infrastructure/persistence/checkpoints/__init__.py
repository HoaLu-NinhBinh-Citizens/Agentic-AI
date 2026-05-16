"""Persistence checkpoints module."""

from typing import Any


class CheckpointManager:
    """Manages execution checkpoints."""
    
    def __init__(self):
        self._checkpoints: dict[str, Any] = {}
    
    def save(self, id: str, state: dict[str, Any]) -> None:
        """Save checkpoint."""
        self._checkpoints[id] = state
    
    def load(self, id: str) -> dict[str, Any] | None:
        """Load checkpoint."""
        return self._checkpoints.get(id)
