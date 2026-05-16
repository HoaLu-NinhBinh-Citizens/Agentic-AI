"""Heartbeat background job module."""

from typing import Any
import time


class HeartbeatJob:
    """Sends periodic heartbeats."""
    
    def __init__(self, interval: float = 30.0):
        self._interval = interval
    
    async def run(self) -> None:
        """Send heartbeat."""
        pass
