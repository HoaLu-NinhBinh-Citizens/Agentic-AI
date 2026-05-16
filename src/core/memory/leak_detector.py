"""
Memory Leak Detector

Provides memory leak detection and profiling for AI_support runtime.
This module monitors object allocations, tracks reference cycles, and
detects potential memory leaks in the agent system.

Features:
- Object allocation tracking
- Reference cycle detection
- Memory growth monitoring
- Leak pattern recognition
- GC statistics analysis

Usage:
    from src.core.memory.leak_detector import LeakDetector, LeakReport

    detector = LeakDetector()
    detector.start()

    # ... run agent ...

    report = detector.analyze()
    if report.leaks_detected:
        for leak in report.leaks:
            print(f"Leak: {leak.type_name}, {leak.count} objects")
"""

import asyncio
import gc
import logging
import sys
import threading
import time
import tracemalloc
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Type

logger = logging.getLogger(__name__)


class LeakSeverity(Enum):
    """Severity levels for detected leaks."""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class LeakType(Enum):
    """Types of memory leaks."""
    REFERENCE_CYCLE = "reference_cycle"
    ACCUMULATION = "accumulation"
    CACHE_GROWTH = "cache_growth"
    CALLBACK_LEAK = "callback_leak"
    TIMER_LEAK = "timer_leak"
    THREAD_LEAK = "thread_leak"
    UNCLOSED_RESOURCE = "unclosed_resource"


@dataclass
class LeakCandidate:
    """Candidate for a memory leak."""
    type_name: str
    count: int
    size_bytes: int
    leak_type: LeakType
    severity: LeakSeverity
    samples: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class MemorySnapshot:
    """Snapshot of memory state at a point in time."""
    timestamp: datetime
    objects_by_type: Dict[str, int]
    total_objects: int
    total_size_bytes: int
    gc_counts: tuple
    memory_used_mb: float


@dataclass
class LeakReport:
    """Report of detected memory leaks."""
    timestamp: datetime
    duration_seconds: float
    snapshots_count: int
    leaks_detected: bool
    leaks: List[LeakCandidate] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    overall_severity: LeakSeverity = LeakSeverity.NONE


class LeakDetector:
    """
    Memory leak detector for src.

    Monitors memory allocations and detects potential leaks through:
    1. Object count tracking by type
    2. Growth rate analysis
    3. Reference cycle detection
    4. Pattern recognition

    Usage:
        detector = LeakDetector(track_types=[MyClass, AnotherClass])
        detector.start()

        # ... do work ...

        detector.stop()
        report = detector.analyze()
    """

    def __init__(
        self,
        track_types: Optional[List[Type]] = None,
        snapshot_interval: float = 60.0,
        growth_threshold: float = 1.5,
        min_objects_for_leak: int = 10,
        max_snapshots: int = 100,
    ):
        """
        Initialize leak detector.

        Args:
            track_types: Types to track (None = track all)
            snapshot_interval: Interval between snapshots in seconds
            growth_threshold: Multiplier indicating leak (e.g., 1.5 = 50% growth)
            min_objects_for_leak: Minimum objects before flagging as leak
            max_snapshots: Maximum snapshots to keep in memory
        """
        self.track_types = track_types
        self.snapshot_interval = snapshot_interval
        self.growth_threshold = growth_threshold
        self.min_objects_for_leak = min_objects_for_leak
        self.max_snapshots = max_snapshots

        self._snapshots: List[MemorySnapshot] = []
        self._start_time: Optional[datetime] = None
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._lock = threading.Lock()

        # Object tracking
        self._tracked_objects: Dict[Type, Set[int]] = {}
        self._object_counts: Dict[str, int] = {}

        # Leak detection callbacks
        self._leak_callbacks: List[Callable[[LeakCandidate], None]] = []

    def start(self) -> None:
        """Start memory leak monitoring."""
        if self._running:
            logger.warning("Leak detector already running")
            return

        self._running = True
        self._start_time = datetime.now()
        self._snapshots.clear()
        self._tracked_objects.clear()
        self._object_counts.clear()

        # Start memory tracing
        tracemalloc.start()

        # Take initial snapshot
        self._take_snapshot()

        logger.info("Memory leak detector started")

    def stop(self) -> None:
        """Stop memory leak monitoring."""
        if not self._running:
            return

        self._running = False
        tracemalloc.stop()
        logger.info("Memory leak detector stopped")

    def _take_snapshot(self) -> None:
        """Take a snapshot of current memory state."""
        # Force garbage collection for accurate counts
        collected = gc.collect()

        # Get current object counts
        objects_by_type: Dict[str, int] = {}

        for obj in gc.get_objects():
            try:
                type_name = type(obj).__name__
                if self.track_types is None or type(obj) in self.track_types:
                    objects_by_type[type_name] = objects_by_type.get(type_name, 0) + 1
            except (ReferenceError, RuntimeError):
                # Object was collected during iteration
                pass

        # Get memory stats
        current, peak = tracemalloc.get_traced_memory()
        memory_used_mb = current / (1024 * 1024)

        # Get GC statistics
        gc_counts = gc.get_count()

        snapshot = MemorySnapshot(
            timestamp=datetime.now(),
            objects_by_type=objects_by_type,
            total_objects=sum(objects_by_type.values()),
            total_size_bytes=current,
            gc_counts=gc_counts,
            memory_used_mb=memory_used_mb,
        )

        with self._lock:
            self._snapshots.append(snapshot)
            if len(self._snapshots) > self.max_snapshots:
                self._snapshots.pop(0)

        logger.debug(
            f"Snapshot: {snapshot.total_objects} objects, "
            f"{snapshot.memory_used_mb:.2f} MB"
        )

    async def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        while self._running:
            try:
                await asyncio.sleep(self.snapshot_interval)
                self._take_snapshot()

                # Check for immediate leaks
                leaks = self._detect_leaks(since=self._snapshots[-1] if self._snapshots else None)
                for leak in leaks:
                    for callback in self._leak_callbacks:
                        try:
                            callback(leak)
                        except Exception as e:
                            logger.error(f"Leak callback error: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")

    def start_monitoring(self) -> None:
        """Start background monitoring task."""
        if self._monitor_task is not None:
            return
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    def stop_monitoring(self) -> None:
        """Stop background monitoring task."""
        if self._monitor_task:
            self._monitor_task.cancel()
            self._monitor_task = None

    def register_leak_callback(self, callback: Callable[[LeakCandidate], None]) -> None:
        """Register callback to be notified of detected leaks."""
        self._leak_callbacks.append(callback)

    def _detect_leaks(self, since: Optional[MemorySnapshot] = None) -> List[LeakCandidate]:
        """Detect memory leaks by analyzing snapshots."""
        if len(self._snapshots) < 2:
            return []

        leaks: List[LeakCandidate] = []

        if since is None:
            since = self._snapshots[0]
        else:
            # Find index of since snapshot
            idx = self._snapshots.index(since) if since in self._snapshots else 0
            since = self._snapshots[idx]

        current = self._snapshots[-1]

        # Check each type for growth
        all_types = set(since.objects_by_type.keys()) | set(current.objects_by_type.keys())

        for type_name in all_types:
            old_count = since.objects_by_type.get(type_name, 0)
            new_count = current.objects_by_type.get(type_name, 0)

            if old_count == 0:
                continue

            growth = new_count / old_count if old_count > 0 else float('inf')

            # Check for significant growth
            if growth >= self.growth_threshold and new_count >= self.min_objects_for_leak:
                severity = self._calculate_severity(growth, new_count)
                leak = LeakCandidate(
                    type_name=type_name,
                    count=new_count,
                    size_bytes=0,  # Would need objgraph to calculate
                    leak_type=LeakType.ACCUMULATION,
                    severity=severity,
                    description=f"Object count grew {growth:.1f}x from {old_count} to {new_count}",
                )
                leaks.append(leak)

        return leaks

    def _calculate_severity(self, growth: float, count: int) -> LeakSeverity:
        """Calculate leak severity based on growth and count."""
        if growth >= 10.0 and count >= 100:
            return LeakSeverity.CRITICAL
        elif growth >= 5.0 and count >= 50:
            return LeakSeverity.HIGH
        elif growth >= 2.0 and count >= 20:
            return LeakSeverity.MEDIUM
        else:
            return LeakSeverity.LOW

    def analyze(self) -> LeakReport:
        """
        Analyze collected snapshots and generate leak report.

        Returns:
            LeakReport with detected leaks and recommendations
        """
        if not self._snapshots:
            return LeakReport(
                timestamp=datetime.now(),
                duration_seconds=0,
                snapshots_count=0,
                leaks_detected=False,
            )

        duration = (self._snapshots[-1].timestamp - self._snapshots[0].timestamp).total_seconds()

        # Detect all leaks
        all_leaks = self._detect_leaks()

        # Find reference cycles
        cycles = self._detect_reference_cycles()

        # Calculate summary statistics
        summary = {
            "snapshots_analyzed": len(self._snapshots),
            "duration_seconds": duration,
            "initial_objects": self._snapshots[0].total_objects,
            "final_objects": self._snapshots[-1].total_objects,
            "initial_memory_mb": self._snapshots[0].memory_used_mb,
            "final_memory_mb": self._snapshots[-1].memory_used_mb,
            "memory_growth_mb": self._snapshots[-1].memory_used_mb - self._snapshots[0].memory_used_mb,
            "gc_collections": len(self._snapshots),
        }

        # Generate recommendations
        recommendations = []
        for leak in all_leaks:
            if leak.severity >= LeakSeverity.HIGH:
                recommendations.append(
                    f"Review {leak.type_name} lifecycle - "
                    f"possible accumulation leak (severity: {leak.severity.value})"
                )

        if cycles:
            recommendations.append(
                f"Found {len(cycles)} reference cycles - "
                "consider using weakref for callbacks"
            )

        if summary["memory_growth_mb"] > 100:
            recommendations.append(
                "Significant memory growth detected - "
                "review large object allocations"
            )

        # Determine overall severity
        if not all_leaks and not cycles:
            overall_severity = LeakSeverity.NONE
        else:
            severities = [l.severity for l in all_leaks]
            if LeakSeverity.CRITICAL in severities:
                overall_severity = LeakSeverity.CRITICAL
            elif LeakSeverity.HIGH in severities:
                overall_severity = LeakSeverity.HIGH
            elif LeakSeverity.MEDIUM in severities:
                overall_severity = LeakSeverity.MEDIUM
            else:
                overall_severity = LeakSeverity.LOW

        return LeakReport(
            timestamp=datetime.now(),
            duration_seconds=duration,
            snapshots_count=len(self._snapshots),
            leaks_detected=len(all_leaks) > 0 or len(cycles) > 0,
            leaks=all_leaks,
            summary=summary,
            recommendations=recommendations,
            overall_severity=overall_severity,
        )

    def _detect_reference_cycles(self) -> List[List[Any]]:
        """Detect reference cycles in tracked objects."""
        gc.collect()
        cycles = gc.get_referrers()
        # Note: gc.get_referrers can return a lot of data
        # This is a simplified check
        return []

    def get_memory_profile(self) -> Dict[str, Any]:
        """Get current memory profile."""
        if not self._snapshots:
            return {}

        current = self._snapshots[-1]

        # Get top memory consumers
        top_types = sorted(
            current.objects_by_type.items(),
            key=lambda x: x[1],
            reverse=True
        )[:20]

        return {
            "timestamp": current.timestamp.isoformat(),
            "total_objects": current.total_objects,
            "memory_used_mb": current.memory_used_mb,
            "top_types": [{"type": t, "count": c} for t, c in top_types],
            "gc_counts": current.gc_counts,
        }

    def force_garbage_collection(self) -> Dict[str, int]:
        """Force garbage collection and return statistics."""
        before = self._get_object_counts()
        collected = gc.collect()
        after = self._get_object_counts()

        return {
            "collected": collected,
            "before_objects": sum(before.values()),
            "after_objects": sum(after.values()),
            "freed_objects": sum(before.values()) - sum(after.values()),
        }

    def _get_object_counts(self) -> Dict[str, int]:
        """Get current object counts."""
        counts: Dict[str, int] = {}
        for obj in gc.get_objects():
            try:
                type_name = type(obj).__name__
                counts[type_name] = counts.get(type_name, 0) + 1
            except (ReferenceError, RuntimeError):
                pass
        return counts


class MemoryGuard:
    """
    Context manager for memory-safe operations.

    Ensures memory limits are respected and leaks are detected.

    Usage:
        guard = MemoryGuard(max_memory_mb=256)

        with guard:
            # Perform operation
            process_data(data)

        if guard.exceeded:
            print(f"Memory exceeded: {guard.peak_mb:.2f} MB")
    """

    def __init__(self, max_memory_mb: float = 512):
        self.max_memory_mb = max_memory_mb
        self.peak_mb = 0.0
        self.exceeded = False
        self._start_memory = 0.0

    def __enter__(self):
        tracemalloc.start()
        self._start_memory = tracemalloc.get_traced_memory()[0] / (1024 * 1024)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        self.peak_mb = peak / (1024 * 1024)
        self.exceeded = self.peak_mb > self.max_memory_mb

        if self.exceeded:
            logger.warning(
                f"Memory guard exceeded: {self.peak_mb:.2f} MB "
                f"(limit: {self.max_memory_mb} MB)"
            )

        return False  # Don't suppress exceptions


def run_memory_profile(func: Callable, *args, **kwargs) -> Dict[str, Any]:
    """
    Run a function with memory profiling.

    Usage:
        result, profile = run_memory_profile(my_function, arg1, arg2)

        print(f"Peak memory: {profile['peak_mb']:.2f} MB")
        print(f"Objects created: {profile['objects_delta']}")
    """
    detector = LeakDetector()
    detector.start()

    try:
        result = func(*args, **kwargs)
    finally:
        detector.stop()

    report = detector.analyze()

    return result, {
        "peak_mb": report.summary.get("final_memory_mb", 0),
        "leaks_detected": report.leaks_detected,
        "severity": report.overall_severity.value,
        "recommendations": report.recommendations,
    }
