"""Phase 5C v12 Extended - Advanced Resilience & Production Features.

Implements missing enterprise features:
1. SnapshotReferenceCounter & SnapshotGCManager - Snapshot lifecycle management
2. VectorSnapshotConsistencyModel - Vector ANN consistency strategies
3. GenerationBasedCacheInvalidator - Scalable cache invalidation
4. QueryDistributionMonitor - Distribution shift detection
5. RetrievalAdmissionController - Overload protection
6. CatastrophicRecoveryStrategy - Recovery planning
7. PluginStateMigration - Stateful plugin rollback
8. LSNBasedLagMetrics - Lag measurement beyond time
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from .retrieval_types import (
    RetrievalSnapshot,
    SnapshotStatus,
)


logger = logging.getLogger(__name__)


# ============================================================================
# 1. Snapshot Reference Counter & GC Manager
# ============================================================================

class SnapshotReferenceCounter:
    """Tracks references to snapshots for safe garbage collection.
    
    Prevents GC of snapshots that are still being read by active
    long-running retrievals.
    """
    
    def __init__(self):
        self._refs: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()
    
    async def acquire(self, snapshot_id: str) -> int:
        """Acquire a reference to a snapshot."""
        async with self._lock:
            self._refs[snapshot_id] += 1
            return self._refs[snapshot_id]
    
    async def release(self, snapshot_id: str) -> int:
        """Release a reference to a snapshot."""
        async with self._lock:
            if self._refs[snapshot_id] > 0:
                self._refs[snapshot_id] -= 1
            return self._refs[snapshot_id]
    
    def get_ref_count(self, snapshot_id: str) -> int:
        """Get current reference count."""
        return self._refs.get(snapshot_id, 0)
    
    def is_referenced(self, snapshot_id: str) -> bool:
        """Check if snapshot has any references."""
        return self._refs.get(snapshot_id, 0) > 0


class SnapshotGCManager:
    """Manages snapshot lifecycle with automatic garbage collection.
    
    Tracks:
    - Snapshot creation time
    - Reference counts
    - Max snapshot age
    - Incremental compaction
    """
    
    def __init__(
        self,
        max_snapshot_age_seconds: int = 3600,
        max_snapshots: int = 100,
        gc_interval_seconds: int = 300,
    ):
        self._max_age = max_snapshot_age_seconds
        self._max_snapshots = max_snapshots
        self._gc_interval = gc_interval_seconds
        self._snapshots: dict[str, dict] = {}
        self._ref_counter = SnapshotReferenceCounter()
        self._lock = asyncio.Lock()
        self._gc_task: Optional[asyncio.Task] = None
    
    def register_snapshot(
        self,
        snapshot_id: str,
        metadata: Optional[dict] = None,
    ) -> None:
        """Register a new snapshot."""
        self._snapshots[snapshot_id] = {
            "created_at": int(time.time()),
            "metadata": metadata or {},
            "last_accessed": int(time.time()),
            "size_bytes": metadata.get("size_bytes", 0) if metadata else 0,
        }
    
    def touch_snapshot(self, snapshot_id: str) -> None:
        """Update last accessed time."""
        if snapshot_id in self._snapshots:
            self._snapshots[snapshot_id]["last_accessed"] = int(time.time())
    
    async def acquire_reference(self, snapshot_id: str) -> int:
        """Acquire reference to snapshot."""
        self.touch_snapshot(snapshot_id)
        return await self._ref_counter.acquire(snapshot_id)
    
    async def release_reference(self, snapshot_id: str) -> int:
        """Release reference to snapshot."""
        return await self._ref_counter.release(snapshot_id)
    
    def get_safe_to_gc(self) -> list[str]:
        """Get list of snapshots safe to garbage collect."""
        safe = []
        now = int(time.time())
        
        for snap_id, info in self._snapshots.items():
            if self._ref_counter.is_referenced(snap_id):
                continue
            
            age = now - info["created_at"]
            if age > self._max_age:
                safe.append(snap_id)
        
        if len(self._snapshots) - len(safe) > self._max_snapshots:
            sorted_snaps = sorted(
                self._snapshots.items(),
                key=lambda x: x[1]["last_accessed"]
            )
            for snap_id, _ in sorted_snaps[:len(self._snapshots) - self._max_snapshots]:
                if snap_id not in safe and not self._ref_counter.is_referenced(snap_id):
                    safe.append(snap_id)
        
        return safe
    
    async def gc_snapshots(
        self,
        delete_fn: Optional[Callable] = None,
    ) -> list[str]:
        """Run garbage collection on safe snapshots."""
        async with self._lock:
            safe = self.get_safe_to_gc()
            deleted = []
            
            for snap_id in safe:
                if delete_fn:
                    try:
                        await delete_fn(snap_id)
                    except Exception as e:
                        logger.warning(f"Failed to delete snapshot {snap_id}: {e}")
                        continue
                
                del self._snapshots[snap_id]
                deleted.append(snap_id)
            
            return deleted
    
    async def start_gc_loop(self) -> None:
        """Start background GC loop."""
        if self._gc_task is not None:
            return
        
        async def gc_loop():
            while True:
                await asyncio.sleep(self._gc_interval)
                deleted = await self.gc_snapshots()
                if deleted:
                    logger.info(f"GC deleted {len(deleted)} snapshots")
        
        self._gc_task = asyncio.create_task(gc_loop())
    
    async def stop_gc_loop(self) -> None:
        """Stop background GC loop."""
        if self._gc_task:
            self._gc_task.cancel()
            try:
                await self._gc_task
            except asyncio.CancelledError:
                pass
            self._gc_task = None
    
    def get_stats(self) -> dict:
        """Get GC statistics."""
        return {
            "total_snapshots": len(self._snapshots),
            "referenced_snapshots": sum(
                1 for s in self._snapshots if self._ref_counter.is_referenced(s)
            ),
            "safe_to_gc": len(self.get_safe_to_gc()),
            "max_age_seconds": self._max_age,
            "max_snapshots": self._max_snapshots,
        }


# ============================================================================
# 2. Vector Snapshot Consistency Model
# ============================================================================

class VectorConsistencyStrategy(Enum):
    """Vector index consistency strategies."""
    FULL_COW = "full_cow"           # Copy-on-write, expensive but consistent
    SEGMENT_PINNING = "segment_pinning"  # Pin old segments during reads
    BEST_EFFORT = "best_effort"      # Accept approximate consistency
    VERSIONED_SEGMENTS = "versioned_segments"  # Immutable segments with versions


@dataclass
class VectorSegment:
    """Immutable vector segment with version."""
    segment_id: str
    version: int
    created_at: int
    doc_ids: list[str]
    is_immutable: bool = True


class VectorSnapshotConsistencyManager:
    """Manages vector index consistency for snapshot isolation.
    
    Supports multiple consistency strategies based on performance/cost tradeoff.
    """
    
    def __init__(
        self,
        strategy: VectorConsistencyStrategy = VectorConsistencyStrategy.VERSIONED_SEGMENTS,
    ):
        self._strategy = strategy
        self._segments: dict[str, VectorSegment] = {}
        self._current_version: int = 0
        self._pinned_segments: set[str] = set()
        self._lock = asyncio.Lock()
    
    def create_segment(
        self,
        doc_ids: list[str],
    ) -> VectorSegment:
        """Create a new immutable vector segment."""
        self._current_version += 1
        segment = VectorSegment(
            segment_id=f"seg_{uuid.uuid4().hex[:8]}",
            version=self._current_version,
            created_at=int(time.time()),
            doc_ids=list(doc_ids),
            is_immutable=True,
        )
        self._segments[segment.segment_id] = segment
        return segment
    
    def pin_segment(self, segment_id: str) -> None:
        """Pin segment for snapshot reading."""
        self._pinned_segments.add(segment_id)
    
    def unpin_segment(self, segment_id: str) -> None:
        """Unpin segment for potential compaction."""
        self._pinned_segments.discard(segment_id)
    
    def get_segments_for_snapshot(self, snapshot_version: int) -> list[VectorSegment]:
        """Get all segments visible at a given version."""
        return [
            seg for seg in self._segments.values()
            if seg.version <= snapshot_version
        ]
    
    def is_segment_safe_to_compact(self, segment_id: str) -> bool:
        """Check if segment can be safely compacted."""
        if segment_id in self._pinned_segments:
            return False
        
        if self._strategy == VectorConsistencyStrategy.VERSIONED_SEGMENTS:
            return True
        
        return False
    
    async def compact_old_segments(
        self,
        max_versions_to_keep: int = 3,
    ) -> list[str]:
        """Compact old immutable segments."""
        async with self._lock:
            deleted = []
            
            versions_to_keep = set(
                range(self._current_version - max_versions_to_keep, self._current_version + 1)
            )
            
            for seg_id, seg in list(self._segments.items()):
                if seg.version < self._current_version - max_versions_to_keep:
                    if self.is_segment_safe_to_compact(seg_id):
                        del self._segments[seg_id]
                        deleted.append(seg_id)
            
            return deleted
    
    def get_stats(self) -> dict:
        """Get consistency manager stats."""
        return {
            "strategy": self._strategy.value,
            "total_segments": len(self._segments),
            "pinned_segments": len(self._pinned_segments),
            "current_version": self._current_version,
        }


# ============================================================================
# 3. Generation-Based Cache Invalidation
# ============================================================================

class GenerationCacheInvalidator:
    """Scalable cache invalidation using generations.
    
    Instead of tracking exact doc_id -> cache_keys mapping,
    uses generation numbers for O(1) invalidation.
    """
    
    def __init__(
        self,
        max_generations: int = 10,
        generation_ttl_seconds: int = 86400,
    ):
        self._max_generations = max_generations
        self._generation_ttl = generation_ttl_seconds
        self._current_generation: int = 0
        self._doc_generations: dict[str, int] = {}
        self._cache_generations: dict[str, int] = {}
        self._generation_created: dict[int, int] = {}
        self._lock = asyncio.Lock()
    
    async def on_document_updated(self, doc_id: str) -> int:
        """Record document update, increment generation."""
        async with self._lock:
            self._current_generation += 1
            self._doc_generations[doc_id] = self._current_generation
            self._generation_created[self._current_generation] = int(time.time())
            
            await self._cleanup_old_generations()
            
            return self._current_generation
    
    def register_cache_entry(self, cache_key: str) -> int:
        """Register cache entry with current generation."""
        self._cache_generations[cache_key] = self._current_generation
        return self._current_generation
    
    def is_cache_valid(self, cache_key: str) -> tuple[bool, Optional[str]]:
        """Check if cache entry is valid.
        
        Returns:
            Tuple of (is_valid, reason_if_invalid)
        """
        if cache_key not in self._cache_generations:
            return False, "cache_key_not_registered"
        
        cache_gen = self._cache_generations[cache_key]
        
        if cache_gen < self._current_generation:
            return False, f"stale_generation_{cache_gen}_vs_{self._current_generation}"
        
        return True, None
    
    def get_invalidation_batch(
        self,
        batch_size: int = 100,
    ) -> list[str]:
        """Get batch of cache keys to invalidate."""
        to_invalidate = [
            key for key, gen in self._cache_generations.items()
            if gen < self._current_generation
        ]
        return to_invalidate[:batch_size]
    
    async def _cleanup_old_generations(self) -> None:
        """Remove data for old generations."""
        now = int(time.time())
        
        old_gens = [
            gen for gen, created in self._generation_created.items()
            if now - created > self._generation_ttl
        ]
        
        for gen in old_gens:
            del self._generation_created[gen]
            
            docs_to_remove = [
                doc for doc, g in self._doc_generations.items()
                if g == gen
            ]
            for doc in docs_to_remove:
                del self._doc_generations[doc]
    
    def get_stats(self) -> dict:
        """Get invalidator stats."""
        return {
            "current_generation": self._current_generation,
            "total_documents": len(self._doc_generations),
            "total_cache_entries": len(self._cache_generations),
            "stale_entries": sum(
                1 for g in self._cache_generations.values()
                if g < self._current_generation
            ),
        }


# ============================================================================
# 4. Query Distribution Monitor
# ============================================================================

class DistributionShiftDetector:
    """Detects shifts in query distribution.
    
    Monitors:
    - Intent frequency shift
    - Embedding centroid drift
    - KL divergence from baseline
    """
    
    def __init__(
        self,
        baseline_window: int = 1000,
        drift_threshold: float = 0.1,
        check_interval: int = 3600,
    ):
        self._baseline_window = baseline_window
        self._drift_threshold = drift_threshold
        self._check_interval = check_interval
        
        self._intent_counts: dict[str, int] = defaultdict(int)
        self._baseline_distribution: dict[str, float] = {}
        self._current_distribution: dict[str, float] = {}
        self._query_history: list[dict] = []
        self._alerts: list[dict] = []
        self._lock = asyncio.Lock()
    
    def record_query(self, intent: str, query_text: str) -> None:
        """Record a query for distribution analysis."""
        self._intent_counts[intent] += 1
        self._query_history.append({
            "intent": intent,
            "query": query_text,
            "timestamp": int(time.time()),
        })
        
        if len(self._query_history) > self._baseline_window:
            self._query_history.pop(0)
        
        self._update_distribution()
    
    def _update_distribution(self) -> None:
        """Update current distribution from counts."""
        total = sum(self._intent_counts.values())
        if total == 0:
            return
        
        self._current_distribution = {
            intent: count / total
            for intent, count in self._intent_counts.items()
        }
    
    def set_baseline(self) -> None:
        """Set current distribution as baseline."""
        self._baseline_distribution = dict(self._current_distribution)
        self._alerts.append({
            "type": "baseline_set",
            "timestamp": int(time.time()),
            "distribution": self._baseline_distribution,
        })
    
    def compute_kl_divergence(self) -> float:
        """Compute KL divergence from baseline."""
        if not self._baseline_distribution:
            return 0.0
        
        divergence = 0.0
        all_intents = set(self._baseline_distribution.keys()) | set(self._current_distribution.keys())
        
        for intent in all_intents:
            p = self._baseline_distribution.get(intent, 1e-10)
            q = self._current_distribution.get(intent, 1e-10)
            divergence += p * (p / q if q > 0 else 0)
        
        return divergence
    
    def detect_drift(self) -> tuple[bool, dict]:
        """Detect if distribution has drifted from baseline.
        
        Returns:
            Tuple of (drift_detected, details)
        """
        if not self._baseline_distribution:
            return False, {"reason": "no_baseline"}
        
        kl_div = self.compute_kl_divergence()
        
        drift_detected = kl_div > self._drift_threshold
        
        details = {
            "kl_divergence": kl_div,
            "threshold": self._drift_threshold,
            "drift_detected": drift_detected,
            "baseline": self._baseline_distribution,
            "current": self._current_distribution,
        }
        
        if drift_detected:
            self._alerts.append({
                "type": "distribution_drift",
                "timestamp": int(time.time()),
                "details": details,
            })
        
        return drift_detected, details
    
    def get_alerts(self) -> list[dict]:
        """Get all distribution shift alerts."""
        return list(self._alerts)
    
    def get_stats(self) -> dict:
        """Get monitor stats."""
        return {
            "total_queries": sum(self._intent_counts.values()),
            "unique_intents": len(self._intent_counts),
            "has_baseline": len(self._baseline_distribution) > 0,
            "total_alerts": len(self._alerts),
            "current_distribution": self._current_distribution,
        }


# ============================================================================
# 5. Retrieval Admission Controller
# ============================================================================

class LoadSheddingPolicy(Enum):
    """Load shedding policies."""
    REJECT_LOW_PRIORITY = "reject_low_priority"
    REJECT_NEWEST = "reject_newest"
    QUEUE_TIMEOUT = "queue_timeout"
    DEGRADE_QUALITY = "degrade_quality"


@dataclass
class AdmissionDecision:
    """Result of admission check."""
    admitted: bool
    reason: str
    queue_position: Optional[int] = None
    estimated_wait_seconds: Optional[float] = None
    degradation_level: Optional[int] = None


class RetrievalAdmissionController:
    """Controls admission to prevent system overload.
    
    Implements:
    - Queue depth monitoring
    - Priority-based shedding
    - Backpressure signaling
    """
    
    def __init__(
        self,
        max_queue_depth: int = 1000,
        high_water_mark: float = 0.8,
        low_water_mark: float = 0.5,
        policy: LoadSheddingPolicy = LoadSheddingPolicy.REJECT_LOW_PRIORITY,
    ):
        self._max_queue = max_queue_depth
        self._high_water = high_water_mark
        self._low_water = low_water_mark
        self._policy = policy
        
        self._queue_depth: int = 0
        self._priority_queue: dict[str, list] = defaultdict(list)
        self._request_count: int = 0
        self._rejected_count: int = 0
        self._admission_history: list[dict] = []
        self._lock = asyncio.Lock()
    
    def get_load_factor(self) -> float:
        """Get current load as fraction of max capacity."""
        return self._queue_depth / self._max_queue if self._max_queue > 0 else 0.0
    
    def is_overloaded(self) -> bool:
        """Check if system is overloaded."""
        return self.get_load_factor() >= self._high_water
    
    def is_degraded(self) -> bool:
        """Check if system is in degraded mode."""
        load = self.get_load_factor()
        return load >= self._low_water and load < self._high_water
    
    async def check_admission(
        self,
        priority: str = "normal",
        request_id: Optional[str] = None,
    ) -> AdmissionDecision:
        """Check if request should be admitted.
        
        Args:
            priority: Request priority (low, normal, high, critical)
            request_id: Optional request ID for tracking
            
        Returns:
            AdmissionDecision with admission status and metadata
        """
        async with self._lock:
            self._request_count += 1
            load = self.get_load_factor()
            
            if load < self._low_water:
                self._queue_depth += 1
                self._priority_queue[priority].append(request_id)
                return AdmissionDecision(
                    admitted=True,
                    reason="capacity_available",
                    queue_position=self._queue_depth,
                )
            
            if load >= self._high_water:
                if self._policy == LoadSheddingPolicy.REJECT_LOW_PRIORITY:
                    if priority == "low":
                        self._rejected_count += 1
                        self._admission_history.append({
                            "request_id": request_id,
                            "admitted": False,
                            "reason": "low_priority_shed",
                            "load": load,
                        })
                        return AdmissionDecision(
                            admitted=False,
                            reason="low_priority_shed",
                        )
                
                self._queue_depth += 1
                self._priority_queue[priority].append(request_id)
                return AdmissionDecision(
                    admitted=True,
                    reason="forced_admission_under_load",
                    degradation_level=self._compute_degradation_level(load),
                )
            
            self._queue_depth += 1
            self._priority_queue[priority].append(request_id)
            return AdmissionDecision(
                admitted=True,
                reason="degraded_service",
                degradation_level=self._compute_degradation_level(load),
            )
    
    def _compute_degradation_level(self, load: float) -> int:
        """Compute degradation level based on load."""
        if load >= 0.9:
            return 3
        if load >= 0.8:
            return 2
        if load >= 0.7:
            return 1
        return 0
    
    async def release_slot(self, request_id: str) -> None:
        """Release a queue slot when request completes."""
        async with self._lock:
            if self._queue_depth > 0:
                self._queue_depth -= 1
            
            for priority in ["low", "normal", "high", "critical"]:
                if request_id in self._priority_queue[priority]:
                    self._priority_queue[priority].remove(request_id)
                    break
    
    def get_stats(self) -> dict:
        """Get admission controller stats."""
        return {
            "queue_depth": self._queue_depth,
            "max_queue": self._max_queue,
            "load_factor": self.get_load_factor(),
            "is_overloaded": self.is_overloaded(),
            "is_degraded": self.is_degraded(),
            "total_requests": self._request_count,
            "rejected_requests": self._rejected_count,
            "rejection_rate": self._rejected_count / self._request_count if self._request_count > 0 else 0,
            "queue_by_priority": {p: len(q) for p, q in self._priority_queue.items()},
        }


# ============================================================================
# 6. Catastrophic Recovery Strategy
# ============================================================================

class RecoveryStrategy(Enum):
    """Recovery strategies for different failure modes."""
    COLD_REBUILD = "cold_rebuild"
    REPLAY_WAL = "replay_wal"
    RESTORE_SNAPSHOT = "restore_snapshot"
    PARTIAL_SHARD_ISOLATION = "partial_shard_isolation"
    READONLY_MODE = "readonly_mode"


@dataclass
class FailureScope:
    """Scope of detected failure."""
    affected_components: list[str]
    affected_shards: list[str]
    estimated_data_loss: float
    detected_at: int


@dataclass
class RecoveryPlan:
    """Planned recovery action."""
    strategy: RecoveryStrategy
    estimated_duration_seconds: float
    risk_level: str
    steps: list[str]
    prerequisites: list[str]


class CatastrophicRecoveryManager:
    """Manages recovery from catastrophic failures.
    
    Failure modes:
    - Vector index corruption
    - Snapshot corruption
    - Cache poisoning
    - Data inconsistency
    """
    
    def __init__(
        self,
        wal_enabled: bool = True,
        snapshot_retention: int = 3,
    ):
        self._wal_enabled = wal_enabled
        self._snapshot_retention = snapshot_retention
        self._wal_entries: list[dict] = []
        self._recovery_history: list[dict] = []
        self._lock = asyncio.Lock()
    
    def record_wal_entry(self, operation: dict) -> None:
        """Record WAL entry for replay."""
        if not self._wal_enabled:
            return
        
        self._wal_entries.append({
            "entry_id": len(self._wal_entries),
            "operation": operation,
            "timestamp": int(time.time()),
        })
    
    async def analyze_failure(
        self,
        failure_indicators: dict,
    ) -> FailureScope:
        """Analyze failure scope from indicators."""
        affected_components = []
        affected_shards = []
        estimated_data_loss = 0.0
        
        if failure_indicators.get("index_corruption"):
            affected_components.append("vector_index")
            estimated_data_loss += 0.1
        
        if failure_indicators.get("snapshot_corruption"):
            affected_components.append("snapshot_store")
            estimated_data_loss += 0.2
        
        if failure_indicators.get("cache_poisoning"):
            affected_components.append("cache")
            estimated_data_loss += 0.05
        
        if failure_indicators.get("shard_failures"):
            affected_shards = failure_indicators.get("shard_failures", [])
        
        return FailureScope(
            affected_components=affected_components,
            affected_shards=affected_shards,
            estimated_data_loss=estimated_data_loss,
            detected_at=int(time.time()),
        )
    
    async def create_recovery_plan(
        self,
        scope: FailureScope,
    ) -> RecoveryPlan:
        """Create recovery plan based on failure scope."""
        steps = []
        prerequisites = []
        
        if "vector_index" in scope.affected_components:
            if scope.estimated_data_loss < 0.15:
                strategy = RecoveryStrategy.REPLAY_WAL
                steps.append("1. Stop all writes")
                steps.append("2. Replay WAL entries from last consistent checkpoint")
                steps.append("3. Verify index integrity")
                steps.append("4. Resume writes")
            else:
                strategy = RecoveryStrategy.COLD_REBUILD
                steps.append("1. Isolate corrupted shards")
                steps.append("2. Trigger full index rebuild from source")
                steps.append("3. Rebuild from documents")
                steps.append("4. Verify new index")
                steps.append("5. Switch traffic")
                prerequisites.append("backup_of_source_documents")
        
        elif "snapshot_store" in scope.affected_components:
            strategy = RecoveryStrategy.RESTORE_SNAPSHOT
            steps.append("1. Identify last valid snapshot")
            steps.append("2. Restore from snapshot backup")
            steps.append("3. Replay WAL on top")
            steps.append("4. Verify consistency")
        
        elif "cache" in scope.affected_components:
            strategy = RecoveryStrategy.PARTIAL_SHARD_ISOLATION
            steps.append("1. Flush poisoned cache entries")
            steps.append("2. Rebuild cache from index")
            steps.append("3. Monitor for re-poisoning")
        
        else:
            strategy = RecoveryStrategy.READONLY_MODE
            steps.append("1. Switch to read-only mode")
            steps.append("2. Investigate root cause")
            steps.append("3. Plan full recovery")
        
        duration_estimates = {
            RecoveryStrategy.COLD_REBUILD: 3600,
            RecoveryStrategy.REPLAY_WAL: 300,
            RecoveryStrategy.RESTORE_SNAPSHOT: 600,
            RecoveryStrategy.PARTIAL_SHARD_ISOLATION: 180,
            RecoveryStrategy.READONLY_MODE: 60,
        }
        
        risk_levels = {
            RecoveryStrategy.COLD_REBUILD: "high",
            RecoveryStrategy.REPLAY_WAL: "medium",
            RecoveryStrategy.RESTORE_SNAPSHOT: "medium",
            RecoveryStrategy.PARTIAL_SHARD_ISOLATION: "low",
            RecoveryStrategy.READONLY_MODE: "low",
        }
        
        return RecoveryPlan(
            strategy=strategy,
            estimated_duration_seconds=duration_estimates.get(strategy, 600),
            risk_level=risk_levels.get(strategy, "unknown"),
            steps=steps,
            prerequisites=prerequisites,
        )
    
    async def execute_recovery(
        self,
        plan: RecoveryPlan,
        execution_fn: Optional[Callable] = None,
    ) -> dict:
        """Execute recovery plan."""
        result = {
            "strategy": plan.strategy.value,
            "started_at": int(time.time()),
            "steps_completed": [],
            "success": False,
        }
        
        for step in plan.steps:
            result["steps_completed"].append(step)
            
            if execution_fn:
                try:
                    await execution_fn(step)
                except Exception as e:
                    result["error"] = str(e)
                    result["failed_at"] = step
                    break
        
        result["completed_at"] = int(time.time())
        result["success"] = len(result["steps_completed"]) == len(plan.steps)
        
        self._recovery_history.append(result)
        
        return result
    
    def get_recovery_history(self) -> list[dict]:
        """Get recovery history."""
        return list(self._recovery_history)


# ============================================================================
# 7. Plugin State Migration
# ============================================================================

@dataclass
class PluginStateSnapshot:
    """Snapshot of plugin state for migration."""
    plugin_name: str
    version: str
    state: dict
    schema_versions: list[str]
    created_at: int


@dataclass
class PluginCompatibility:
    """Plugin compatibility matrix entry."""
    from_version: str
    to_version: str
    compatible: bool
    migration_required: bool
    migration_steps: list[str]


class PluginStateMigrationManager:
    """Manages stateful plugin migration.
    
    Handles:
    - State snapshotting
    - Version compatibility
    - State transformation
    """
    
    def __init__(
        self,
        max_snapshots_per_plugin: int = 5,
    ):
        self._max_snapshots = max_snapshots_per_plugin
        self._state_snapshots: dict[str, list[PluginStateSnapshot]] = defaultdict(list)
        self._compatibility_matrix: dict[str, dict[str, PluginCompatibility]] = defaultdict(dict)
        self._lock = asyncio.Lock()
    
    async def snapshot_plugin_state(
        self,
        plugin_name: str,
        version: str,
        state: dict,
        schema_versions: Optional[list[str]] = None,
    ) -> PluginStateSnapshot:
        """Create state snapshot for plugin."""
        snapshot = PluginStateSnapshot(
            plugin_name=plugin_name,
            version=version,
            state=dict(state),
            schema_versions=schema_versions or [],
            created_at=int(time.time()),
        )
        
        self._state_snapshots[plugin_name].append(snapshot)
        
        if len(self._state_snapshots[plugin_name]) > self._max_snapshots:
            self._state_snapshots[plugin_name].pop(0)
        
        return snapshot
    
    def get_latest_snapshot(self, plugin_name: str) -> Optional[PluginStateSnapshot]:
        """Get latest state snapshot."""
        snapshots = self._state_snapshots.get(plugin_name, [])
        return snapshots[-1] if snapshots else None
    
    def register_compatibility(
        self,
        plugin_name: str,
        from_version: str,
        to_version: str,
        compatible: bool,
        migration_steps: Optional[list[str]] = None,
    ) -> None:
        """Register compatibility between versions."""
        self._compatibility_matrix[plugin_name][f"{from_version}->{to_version}"] = PluginCompatibility(
            from_version=from_version,
            to_version=to_version,
            compatible=compatible,
            migration_required=not compatible,
            migration_steps=migration_steps or [],
        )
    
    def get_compatibility(
        self,
        plugin_name: str,
        from_version: str,
        to_version: str,
    ) -> Optional[PluginCompatibility]:
        """Get compatibility info between versions."""
        key = f"{from_version}->{to_version}"
        return self._compatibility_matrix.get(plugin_name, {}).get(key)
    
    async def migrate_state(
        self,
        plugin_name: str,
        from_version: str,
        to_version: str,
        state: dict,
        migration_fn: Optional[Callable] = None,
    ) -> tuple[bool, dict]:
        """Migrate plugin state between versions.
        
        Returns:
            Tuple of (success, migrated_state)
        """
        compatibility = self.get_compatibility(plugin_name, from_version, to_version)
        
        if compatibility and not compatibility.migration_required:
            return True, state
        
        if migration_fn:
            try:
                migrated = await migration_fn(state, from_version, to_version)
                return True, migrated
            except Exception as e:
                logger.error(f"Plugin state migration failed: {e}")
                return False, state
        
        return False, state
    
    def get_stats(self) -> dict:
        """Get migration manager stats."""
        return {
            "total_plugins": len(self._state_snapshots),
            "total_snapshots": sum(len(s) for s in self._state_snapshots.values()),
            "compatibility_entries": sum(
                len(m) for m in self._compatibility_matrix.values()
            ),
        }


# ============================================================================
# 8. LSN-Based Lag Metrics
# ============================================================================

class LSNBasedLagMetrics:
    """Lag metrics beyond time-based measurement.
    
    Tracks:
    - LSN (Log Sequence Number) lag
    - Index freshness
    - WAL replay progress
    - Vector epoch
    """
    
    def __init__(
        self,
        max_lag_threshold: int = 10000,
    ):
        self._max_lag_threshold = max_lag_threshold
        self._replicas: dict[str, dict] = {}
        self._lock = asyncio.Lock()
    
    def update_replica_lsn(
        self,
        replica_id: str,
        current_lsn: int,
        flushed_lsn: int,
    ) -> None:
        """Update replica's LSN state."""
        if replica_id not in self._replicas:
            self._replicas[replica_id] = {
                "registered_at": int(time.time()),
                "last_update": int(time.time()),
            }
        
        self._replicas[replica_id].update({
            "current_lsn": current_lsn,
            "flushed_lsn": flushed_lsn,
            "lsn_lag": current_lsn - flushed_lsn,
            "last_update": int(time.time()),
        })
    
    def update_vector_epoch(
        self,
        replica_id: str,
        vector_epoch: int,
    ) -> None:
        """Update replica's vector epoch."""
        if replica_id in self._replicas:
            self._replicas[replica_id]["vector_epoch"] = vector_epoch
    
    def update_index_freshness(
        self,
        replica_id: str,
        docs_indexed: int,
        docs_total: int,
    ) -> None:
        """Update replica's index freshness."""
        if replica_id in self._replicas:
            self._replicas[replica_id].update({
                "docs_indexed": docs_indexed,
                "docs_total": docs_total,
                "freshness_ratio": docs_indexed / docs_total if docs_total > 0 else 1.0,
            })
    
    def is_replica_stale(self, replica_id: str) -> tuple[bool, str]:
        """Check if replica is stale based on LSN.
        
        Returns:
            Tuple of (is_stale, reason)
        """
        if replica_id not in self._replicas:
            return True, "replica_not_registered"
        
        state = self._replicas[replica_id]
        
        lsn_lag = state.get("lsn_lag", float('inf'))
        if lsn_lag > self._max_lag_threshold:
            return True, f"lsn_lag_exceeded_{lsn_lag}"
        
        freshness = state.get("freshness_ratio", 1.0)
        if freshness < 0.95:
            return True, f"freshness_below_threshold_{freshness}"
        
        return False, ""
    
    def get_lag_metrics(self, replica_id: str) -> dict:
        """Get comprehensive lag metrics for replica."""
        if replica_id not in self._replicas:
            return {"error": "replica_not_found"}
        
        state = self._replicas[replica_id]
        is_stale, reason = self.is_replica_stale(replica_id)
        
        return {
            "replica_id": replica_id,
            "current_lsn": state.get("current_lsn"),
            "flushed_lsn": state.get("flushed_lsn"),
            "lsn_lag": state.get("lsn_lag"),
            "vector_epoch": state.get("vector_epoch"),
            "freshness_ratio": state.get("freshness_ratio"),
            "is_stale": is_stale,
            "stale_reason": reason,
            "last_update": state.get("last_update"),
        }
    
    def get_all_replica_metrics(self) -> dict[str, dict]:
        """Get metrics for all replicas."""
        return {
            rid: self.get_lag_metrics(rid)
            for rid in self._replicas
        }
    
    def get_stats(self) -> dict:
        """Get overall LSN metrics stats."""
        stale_count = sum(
            1 for rid in self._replicas
            if self.is_replica_stale(rid)[0]
        )
        
        return {
            "total_replicas": len(self._replicas),
            "stale_replicas": stale_count,
            "healthy_replicas": len(self._replicas) - stale_count,
            "max_lsn_lag": max(
                (r.get("lsn_lag", 0) for r in self._replicas.values()),
                default=0
            ),
        }
