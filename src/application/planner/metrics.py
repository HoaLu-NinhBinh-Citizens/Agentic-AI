"""Planner metrics collection - Phase 5B."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class PlannerMetricsSnapshot:
    """Snapshot of planner metrics at a point in time."""
    timestamp: float = field(default_factory=time.time)
    
    branch_decision_count: int = 0
    branch_decision_cache_hits: int = 0
    semantic_retrieval_hits: int = 0
    semantic_retrieval_misses: int = 0
    plan_retry_count: int = 0
    plan_retry_success_count: int = 0
    plan_retry_failure_count: int = 0
    interrupt_resume_count: int = 0
    interrupt_expiration_count: int = 0
    interrupt_resume_latencies: list[float] = field(default_factory=list)
    schema_validation_failures: int = 0
    schema_validation_successes: int = 0
    schema_migrations_performed: int = 0
    replay_determinism_failures: int = 0
    replay_success_count: int = 0
    planner_search_states: int = 0
    planner_expansion_rejections: int = 0
    checkpoint_count: int = 0
    checkpoint_sizes: list[int] = field(default_factory=list)
    plan_count: int = 0
    plan_failure_count: int = 0
    active_sessions: int = 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "branch_decision_count": self.branch_decision_count,
            "branch_decision_cache_hit_rate": (
                self.branch_decision_cache_hits / max(self.branch_decision_count, 1)
            ),
            "semantic_retrieval_hit_rate": (
                self.semantic_retrieval_hits / 
                max(self.semantic_retrieval_hits + self.semantic_retrieval_misses, 1)
            ),
            "plan_retry_success_rate": (
                self.plan_retry_success_count / 
                max(self.plan_retry_count, 1)
            ),
            "interrupt_resume_latency_avg": (
                sum(self.interrupt_resume_latencies) / 
                max(len(self.interrupt_resume_latencies), 1)
            ),
            "schema_validation_failure_rate": (
                self.schema_validation_failures / 
                max(self.schema_validation_failures + self.schema_validation_successes, 1)
            ),
            "replay_success_rate": (
                self.replay_success_count / 
                max(self.replay_success_count + self.replay_determinism_failures, 1)
            ),
            "checkpoint_count": self.checkpoint_count,
            "checkpoint_size_avg": (
                sum(self.checkpoint_sizes) / 
                max(len(self.checkpoint_sizes), 1)
            ),
            "plan_success_rate": (
                (self.plan_count - self.plan_failure_count) / 
                max(self.plan_count, 1)
            ),
        }


class PlannerMetrics:
    """Extended metrics collection for planner monitoring.
    
    Tracks all metrics specified in Phase 5B:
    - branch_decision_count, branch_decision_cache_hit
    - semantic_retrieval_hit_rate, retrieved_plan_quality
    - plan_retry_success_rate, plan_retry_count
    - interrupt_resume_latency, interrupt_expiration_count
    - schema_validation_failures, schema_migrations_performed
    - replay_determinism_failures, replay_success_count
    - planner_search_states, planner_expansion_rejections
    - checkpoint_count
    """
    
    def __init__(self):
        self._snapshots: list[PlannerMetricsSnapshot] = []
        self._current = PlannerMetricsSnapshot()
        self._start_time = time.time()
    
    def record_branch_decision(self, cache_hit: bool = False) -> None:
        """Record a branch decision."""
        self._current.branch_decision_count += 1
        if cache_hit:
            self._current.branch_decision_cache_hits += 1
    
    def record_semantic_retrieval(self, hit: bool) -> None:
        """Record a semantic retrieval attempt."""
        if hit:
            self._current.semantic_retrieval_hits += 1
        else:
            self._current.semantic_retrieval_misses += 1
    
    def record_plan_retry(self, success: bool) -> None:
        """Record a plan retry attempt."""
        self._current.plan_retry_count += 1
        if success:
            self._current.plan_retry_success_count += 1
        else:
            self._current.plan_retry_failure_count += 1
    
    def record_interrupt_resume(self, latency_seconds: float) -> None:
        """Record an interrupt resume."""
        self._current.interrupt_resume_count += 1
        self._current.interrupt_resume_latencies.append(latency_seconds)
    
    def record_interrupt_expiration(self) -> None:
        """Record an interrupt expiration."""
        self._current.interrupt_expiration_count += 1
    
    def record_schema_validation(self, success: bool) -> None:
        """Record a schema validation."""
        if success:
            self._current.schema_validation_successes += 1
        else:
            self._current.schema_validation_failures += 1
    
    def record_schema_migration(self) -> None:
        """Record a schema migration."""
        self._current.schema_migrations_performed += 1
    
    def record_replay_determinism_failure(self) -> None:
        """Record a replay determinism failure."""
        self._current.replay_determinism_failures += 1
    
    def record_replay_success(self) -> None:
        """Record a successful replay."""
        self._current.replay_success_count += 1
    
    def record_planner_search_states(self, count: int) -> None:
        """Record the number of search states in beam search."""
        self._current.planner_search_states = max(
            self._current.planner_search_states, count
        )
    
    def record_expansion_rejection(self) -> None:
        """Record a plan rejection due to expansion limits."""
        self._current.planner_expansion_rejections += 1
    
    def record_checkpoint(self, size_bytes: int) -> None:
        """Record a checkpoint creation."""
        self._current.checkpoint_count += 1
        self._current.checkpoint_sizes.append(size_bytes)
    
    def record_plan_created(self) -> None:
        """Record a plan creation."""
        self._current.plan_count += 1
    
    def record_plan_failure(self) -> None:
        """Record a plan failure."""
        self._current.plan_failure_count += 1
    
    def record_active_session(self) -> None:
        """Increment active sessions."""
        self._current.active_sessions += 1
    
    def record_session_end(self) -> None:
        """Decrement active sessions."""
        self._current.active_sessions = max(0, self._current.active_sessions - 1)
    
    def get_snapshot(self) -> PlannerMetricsSnapshot:
        """Get current metrics snapshot."""
        return PlannerMetricsSnapshot(
            timestamp=time.time(),
            branch_decision_count=self._current.branch_decision_count,
            branch_decision_cache_hits=self._current.branch_decision_cache_hits,
            semantic_retrieval_hits=self._current.semantic_retrieval_hits,
            semantic_retrieval_misses=self._current.semantic_retrieval_misses,
            plan_retry_count=self._current.plan_retry_count,
            plan_retry_success_count=self._current.plan_retry_success_count,
            plan_retry_failure_count=self._current.plan_retry_failure_count,
            interrupt_resume_count=self._current.interrupt_resume_count,
            interrupt_expiration_count=self._current.interrupt_expiration_count,
            interrupt_resume_latencies=self._current.interrupt_resume_latencies.copy(),
            schema_validation_failures=self._current.schema_validation_failures,
            schema_validation_successes=self._current.schema_validation_successes,
            schema_migrations_performed=self._current.schema_migrations_performed,
            replay_determinism_failures=self._current.replay_determinism_failures,
            replay_success_count=self._current.replay_success_count,
            planner_search_states=self._current.planner_search_states,
            planner_expansion_rejections=self._current.planner_expansion_rejections,
            checkpoint_count=self._current.checkpoint_count,
            checkpoint_sizes=self._current.checkpoint_sizes.copy(),
            plan_count=self._current.plan_count,
            plan_failure_count=self._current.plan_failure_count,
            active_sessions=self._current.active_sessions,
        )
    
    def save_snapshot(self) -> None:
        """Save current snapshot and reset counters."""
        self._snapshots.append(self.get_snapshot())
        self._current = PlannerMetricsSnapshot()
    
    def get_summary(self) -> dict:
        """Get metrics summary."""
        current = self.get_snapshot()
        
        return {
            "uptime_seconds": time.time() - self._start_time,
            "current_session": current.to_dict(),
            "total_snapshots": len(self._snapshots),
            "cumulative": self._get_cumulative_stats(),
        }
    
    def _get_cumulative_stats(self) -> dict:
        """Get cumulative statistics across all snapshots."""
        if not self._snapshots:
            return {}
        
        return {
            "total_branch_decisions": sum(s.branch_decision_count for s in self._snapshots),
            "total_semantic_retrievals": (
                sum(s.semantic_retrieval_hits for s in self._snapshots) +
                sum(s.semantic_retrieval_misses for s in self._snapshots)
            ),
            "total_plan_retries": sum(s.plan_retry_count for s in self._snapshots),
            "total_interrupt_resumes": sum(s.interrupt_resume_count for s in self._snapshots),
            "total_checkpoints": sum(s.checkpoint_count for s in self._snapshots),
            "total_plans": sum(s.plan_count for s in self._snapshots),
        }


class MetricsCollector:
    """Context manager for collecting metrics during operations."""
    
    def __init__(self, metrics: PlannerMetrics, operation: str):
        self._metrics = metrics
        self._operation = operation
        self._start_time: Optional[float] = None
    
    def __enter__(self) -> MetricsCollector:
        """Start timing."""
        self._start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Record duration on exit."""
        if self._start_time:
            duration = time.time() - self._start_time
            if self._operation == "interrupt_resume":
                self._metrics.record_interrupt_resume(duration)
    
    def record(self, metric_name: str, **kwargs) -> None:
        """Record a specific metric."""
        if metric_name == "branch_decision":
            self._metrics.record_branch_decision(kwargs.get("cache_hit", False))
        elif metric_name == "semantic_retrieval":
            self._metrics.record_semantic_retrieval(kwargs.get("hit", False))
        elif metric_name == "plan_retry":
            self._metrics.record_plan_retry(kwargs.get("success", True))
        elif metric_name == "schema_validation":
            self._metrics.record_schema_validation(kwargs.get("success", True))
        elif metric_name == "schema_migration":
            self._metrics.record_schema_migration()
        elif metric_name == "replay_success":
            self._metrics.record_replay_success()
        elif metric_name == "replay_failure":
            self._metrics.record_replay_determinism_failure()
        elif metric_name == "expansion_rejection":
            self._metrics.record_expansion_rejection()
        elif metric_name == "checkpoint":
            self._metrics.record_checkpoint(kwargs.get("size_bytes", 0))
