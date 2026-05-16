"""Episodic memory module."""

from typing import Any
from datetime import datetime


class EpisodicMemory:
    """Episodic memory for experiences."""
    
    def __init__(self):
        self._episodes: list[dict[str, Any]] = []
    
    def add_episode(self, episode: dict[str, Any]) -> None:
        """Add episode."""
        episode["timestamp"] = datetime.now()
        self._episodes.append(episode)
    
    def get_recent(self, n: int = 10) -> list[dict[str, Any]]:
        """Get recent episodes."""
        return self._episodes[-n:]
