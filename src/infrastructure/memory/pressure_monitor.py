"""Memory pressure monitoring for agent memory system.

Provides:
- Memory leak detection
- Resource usage tracking
- Pressure-based compaction triggers
"""
from __future__ import annotations

import gc
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MemoryPressureStats:
    """Memory pressure statistics."""
    rss_mb: float = 0.0
    vms_mb: float = 0.0
    percent: float = 0.0
    available_mb: float = 0.0
    last_compact: datetime = field(default_factory=datetime.now)
    pressure_level: str = "normal"  # normal, elevated, critical


class MemoryPressureMonitor:
    """Monitor system memory pressure and trigger compaction."""
    
    PRESSURE_THRESHOLDS = {
        "normal": 70.0,
        "elevated": 85.0,
        "critical": 95.0,
    }
    
    def __init__(self, project_root: Path | str = "."):
        self.project_root = Path(project_root)
        self._stats = MemoryPressureStats()
        self._pressure_callbacks: list[callable] = []
    
    def add_pressure_callback(self, callback: callable) -> None:
        """Add callback for pressure events."""
        self._pressure_callbacks.append(callback)
    
    def check_pressure(self) -> MemoryPressureStats:
        """Check current memory pressure."""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            mem = process.memory_info()
            self._stats.rss_mb = mem.rss / (1024 * 1024)
            self._stats.vms_mb = mem.vms / (1024 * 1024)
            self._stats.percent = process.memory_percent()
            self._stats.available_mb = psutil.virtual_memory().available / (1024 * 1024)
        except ImportError:
            # Fallback to gc stats
            gc.collect()
            self._stats.rss_mb = 0.0
            self._stats.percent = 0.0
        
        self._stats.pressure_level = self._calculate_pressure_level()
        return self._stats
    
    def _calculate_pressure_level(self) -> str:
        """Calculate pressure level from stats."""
        if self._stats.percent >= self.PRESSURE_THRESHOLDS["critical"]:
            return "critical"
        if self._stats.percent >= self.PRESSURE_THRESHOLDS["elevated"]:
            return "elevated"
        return "normal"
    
    def should_compact(self, item_count: int) -> bool:
        """Check if memory compaction is needed."""
        self.check_pressure()
        
        threshold = 1000
        if self._stats.pressure_level == "elevated":
            threshold = 500
        elif self._stats.pressure_level == "critical":
            threshold = 100
        
        return item_count > threshold
    
    def notify_pressure(self) -> None:
        """Notify callbacks of pressure event."""
        for callback in self._pressure_callbacks:
            try:
                callback(self._stats)
            except Exception as e:
                logger.warning("Pressure callback failed: %s", e)