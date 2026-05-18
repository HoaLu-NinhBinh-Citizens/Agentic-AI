"""
Chaos Steady State and Secrets Audit Log.

Chaos Steady State:
- Measure baseline metrics before experiment
- Compare after experiment
- Fail if drift > threshold

Secrets Audit Log:
- Audit trail for secret access
- Track service, user, path, timestamp, action
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============== CHAOS STEADY STATE ==============

class ExperimentStatus(str, Enum):
    """Status of chaos experiment."""
    PENDING = "pending"
    BASELINE_MEASURED = "baseline_measured"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class BaselineMetrics:
    """Baseline metrics for comparison."""
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    error_rate: float
    throughput_rps: float
    cpu_percent: float
    memory_percent: float
    measured_at: datetime


@dataclass
class ExperimentResult:
    """Result of chaos experiment."""
    experiment_id: str
    status: ExperimentStatus
    baseline: Optional[BaselineMetrics]
    post_experiment: Optional[BaselineMetrics]
    deviations: Dict[str, float]
    passed: bool
    failure_reason: Optional[str]


class ChaosSteadyState:
    """
    Chaos engineering with steady-state hypothesis.
    
    Workflow:
    1. Measure baseline metrics
    2. Run experiment
    3. Measure post-experiment metrics
    4. Compare deviations
    5. Pass/fail based on threshold
    """
    
    def __init__(
        self,
        deviation_threshold: float = 0.2,
        metrics_endpoint: str = "http://localhost:9090/metrics",
    ):
        self.deviation_threshold = deviation_threshold
        self.metrics_endpoint = metrics_endpoint
        
        # Active experiments
        self._experiments: Dict[str, ExperimentResult] = {}
        
        # Metrics collectors
        self._metrics_collectors: Dict[str, Callable] = {}
        
        self._lock = asyncio.Lock()
    
    def register_metrics_collector(
        self,
        name: str,
        collector: Callable[[], Dict[str, float]],
    ) -> None:
        """Register a metrics collector."""
        self._metrics_collectors[name] = collector
    
    async def measure_baseline(self) -> BaselineMetrics:
        """
        Measure baseline metrics.
        
        In production, this would call the metrics endpoint.
        """
        # Collect from registered collectors
        all_metrics = {}
        for name, collector in self._metrics_collectors.items():
            try:
                metrics = collector()
                all_metrics.update(metrics)
            except Exception as e:
                logger.warning(f"Metrics collector {name} failed: {e}")
        
        # Simulate metrics (in production, call actual endpoint)
        metrics = await self._fetch_metrics()
        
        return BaselineMetrics(
            latency_p50_ms=metrics.get("latency_p50_ms", 100.0),
            latency_p95_ms=metrics.get("latency_p95_ms", 200.0),
            latency_p99_ms=metrics.get("latency_p99_ms", 500.0),
            error_rate=metrics.get("error_rate", 0.01),
            throughput_rps=metrics.get("throughput_rps", 1000.0),
            cpu_percent=metrics.get("cpu_percent", 50.0),
            memory_percent=metrics.get("memory_percent", 60.0),
            measured_at=datetime.now(),
        )
    
    async def _fetch_metrics(self) -> Dict[str, float]:
        """Fetch metrics from endpoint."""
        # Simulated metrics
        return {
            "latency_p50_ms": 95.0,
            "latency_p95_ms": 180.0,
            "latency_p99_ms": 450.0,
            "error_rate": 0.008,
            "throughput_rps": 1050.0,
            "cpu_percent": 48.0,
            "memory_percent": 58.0,
        }
    
    def _calculate_deviation(
        self,
        baseline: float,
        actual: float,
    ) -> float:
        """Calculate percentage deviation."""
        if baseline == 0:
            return 0.0 if actual == 0 else 1.0
        return abs(actual - baseline) / baseline
    
    async def compare_with_baseline(
        self,
        baseline: BaselineMetrics,
        post: BaselineMetrics,
    ) -> tuple[Dict[str, float], bool]:
        """
        Compare post-experiment metrics with baseline.
        
        Returns (deviations, passed).
        """
        deviations = {
            "latency_p50_ms": self._calculate_deviation(
                baseline.latency_p50_ms, post.latency_p50_ms
            ),
            "latency_p95_ms": self._calculate_deviation(
                baseline.latency_p95_ms, post.latency_p95_ms
            ),
            "latency_p99_ms": self._calculate_deviation(
                baseline.latency_p99_ms, post.latency_p99_ms
            ),
            "error_rate": self._calculate_deviation(
                baseline.error_rate, post.error_rate
            ),
            "throughput_rps": self._calculate_deviation(
                baseline.throughput_rps, post.throughput_rps
            ),
            "cpu_percent": self._calculate_deviation(
                baseline.cpu_percent, post.cpu_percent
            ),
            "memory_percent": self._calculate_deviation(
                baseline.memory_percent, post.memory_percent
            ),
        }
        
        # Check if any deviation exceeds threshold
        max_deviation = max(deviations.values())
        passed = max_deviation <= self.deviation_threshold
        
        return deviations, passed
    
    async def run_experiment(
        self,
        experiment_id: str,
        experiment_func: Callable,
    ) -> ExperimentResult:
        """
        Run chaos experiment with steady-state verification.
        
        1. Measure baseline
        2. Execute experiment
        3. Measure post metrics
        4. Compare and determine pass/fail
        """
        async with self._lock:
            result = ExperimentResult(
                experiment_id=experiment_id,
                status=ExperimentStatus.PENDING,
                baseline=None,
                post_experiment=None,
                deviations={},
                passed=False,
                failure_reason=None,
            )
            self._experiments[experiment_id] = result
        
        # Step 1: Measure baseline
        baseline = await self.measure_baseline()
        result.baseline = baseline
        result.status = ExperimentStatus.BASELINE_MEASURED
        
        logger.info(f"Baseline measured for experiment {experiment_id}: {baseline}")
        
        # Step 2: Run experiment
        try:
            result.status = ExperimentStatus.RUNNING
            experiment_result = experiment_func()
            if asyncio.iscoroutine(experiment_result):
                await experiment_result
            
            # Allow system to stabilize
            await asyncio.sleep(1)
            
        except Exception as e:
            result.status = ExperimentStatus.FAILED
            result.failure_reason = f"experiment_error: {str(e)}"
            logger.error(f"Experiment {experiment_id} failed: {e}")
            return result
        
        # Step 3: Measure post-experiment metrics
        post_metrics = await self.measure_baseline()
        result.post_experiment = post_metrics
        
        # Step 4: Compare deviations
        deviations, passed = await self.compare_with_baseline(baseline, post_metrics)
        result.deviations = deviations
        result.passed = passed
        
        if passed:
            result.status = ExperimentStatus.COMPLETED
            logger.info(f"Experiment {experiment_id} passed")
        else:
            result.status = ExperimentStatus.FAILED
            max_deviation = max(deviations.values())
            result.failure_reason = f"deviation_exceeded: {max_deviation:.2%} > {self.deviation_threshold:.2%}"
            logger.warning(f"Experiment {experiment_id} failed: {result.failure_reason}")
        
        return result
    
    async def get_experiment(self, experiment_id: str) -> Optional[ExperimentResult]:
        """Get experiment result."""
        return self._experiments.get(experiment_id)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get chaos metrics."""
        completed = sum(
            1 for r in self._experiments.values()
            if r.status == ExperimentStatus.COMPLETED
        )
        failed = sum(
            1 for r in self._experiments.values()
            if r.status == ExperimentStatus.FAILED
        )
        
        return {
            "total_experiments": len(self._experiments),
            "completed": completed,
            "failed": failed,
            "deviation_threshold": self.deviation_threshold,
        }


# ============== SECRETS AUDIT LOG ==============

class SecretAction(str, Enum):
    """Secret access actions."""
    READ = "read"
    WRITE = "write"
    ROTATE = "rotate"
    CREATE = "create"
    DELETE = "delete"
    LIST = "list"


@dataclass
class SecretsAuditRecord:
    """Audit record for secret access."""
    secret_name: str
    accessed_by: str
    timestamp: datetime
    source_ip: str
    action: SecretAction
    success: bool
    error: Optional[str] = None


class SecretsAuditLog:
    """
    Secrets audit logging.
    
    Records every secret access for compliance.
    Features:
    - Async logging (non-blocking)
    - Access tracking
    - Query by secret name, user, time range
    """
    
    def __init__(
        self,
        retention_days: int = 90,
        async_logging: bool = True,
    ):
        self.retention_days = retention_days
        self.async_logging = async_logging
        
        # Audit records
        self._records: List[SecretsAuditRecord] = []
        
        # Queue for async logging
        self._log_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._log_task: Optional[asyncio.Task] = None
        
        # Alert handlers
        self._alert_handlers: List[Callable] = []
        
        self._lock = asyncio.Lock()
    
    def register_alert_handler(self, handler: Callable) -> None:
        """Register alert handler."""
        self._alert_handlers.append(handler)
    
    async def start(self) -> None:
        """Start async logging."""
        if self.async_logging and not self._running:
            self._running = True
            self._log_task = asyncio.create_task(self._log_processor())
    
    async def stop(self) -> None:
        """Stop async logging."""
        self._running = False
        if self._log_task:
            self._log_task.cancel()
            try:
                await self._log_task
            except asyncio.CancelledError:
                pass
    
    async def _log_processor(self) -> None:
        """Process async log queue."""
        while self._running:
            try:
                record = await asyncio.wait_for(
                    self._log_queue.get(), timeout=1.0
                )
                await self._write_record(record)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Log processor error: {e}")
    
    async def _write_record(self, record: SecretsAuditRecord) -> None:
        """Write audit record."""
        async with self._lock:
            self._records.append(record)
            
            # Enforce retention
            await self._cleanup_old_records()
    
    async def log_access(
        self,
        secret_name: str,
        accessed_by: str,
        action: SecretAction,
        source_ip: str = "unknown",
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """Log secret access."""
        record = SecretsAuditRecord(
            secret_name=secret_name,
            accessed_by=accessed_by,
            timestamp=datetime.now(),
            source_ip=source_ip,
            action=action,
            success=success,
            error=error,
        )
        
        if self.async_logging:
            await self._log_queue.put(record)
        else:
            await self._write_record(record)
    
    async def _cleanup_old_records(self) -> None:
        """Remove old records beyond retention."""
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        self._records = [
            r for r in self._records
            if r.timestamp > cutoff
        ]
    
    async def get_audit_log(
        self,
        secret_name: Optional[str] = None,
        accessed_by: Optional[str] = None,
        limit: int = 100,
    ) -> List[SecretsAuditRecord]:
        """Query audit log."""
        async with self._lock:
            records = self._records
            
            if secret_name:
                records = [r for r in records if r.secret_name == secret_name]
            
            if accessed_by:
                records = [r for r in records if r.accessed_by == accessed_by]
            
            # Most recent first
            return sorted(records, key=lambda r: r.timestamp, reverse=True)[:limit]
    
    async def get_access_summary(
        self,
        secret_name: str,
        hours: int = 24,
    ) -> Dict[str, Any]:
        """Get access summary for secret."""
        async with self._lock:
            cutoff = datetime.now() - timedelta(hours=hours)
            records = [
                r for r in self._records
                if r.secret_name == secret_name and r.timestamp > cutoff
            ]
        
        by_user: Dict[str, int] = {}
        by_action: Dict[str, int] = {}
        failures = 0
        
        for record in records:
            by_user[record.accessed_by] = by_user.get(record.accessed_by, 0) + 1
            by_action[record.action.value] = by_action.get(record.action.value, 0) + 1
            if not record.success:
                failures += 1
        
        return {
            "secret_name": secret_name,
            "period_hours": hours,
            "total_accesses": len(records),
            "unique_users": len(by_user),
            "accesses_by_user": by_user,
            "accesses_by_action": by_action,
            "failure_count": failures,
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get audit log metrics."""
        return {
            "total_records": len(self._records),
            "retention_days": self.retention_days,
            "async_logging": self.async_logging,
            "queue_size": self._log_queue.qsize() if self.async_logging else 0,
        }
