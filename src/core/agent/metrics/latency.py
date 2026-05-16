"""Latency metrics stub."""

import time
from typing import Any


class LatencyTracker:
    """Tracks operation latencies."""
    
    def __init__(self):
        self._latencies: list[float] = []
    
    def record(self, duration: float) -> None:
        """Record a latency measurement."""
        self._latencies.append(duration)
    
    def get_percentile(self, percentile: float) -> float:
        """Get percentile latency."""
        if not self._latencies:
            return 0.0
        sorted_latencies = sorted(self._latencies)
        idx = int(len(sorted_latencies) * percentile / 100)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]
