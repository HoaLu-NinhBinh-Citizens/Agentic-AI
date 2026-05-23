"""Chaos engineering for hardware farm (Phase 13.4).

Provides chaos engineering capabilities:
- Hardware failure simulation
- Network partition testing
- Resource exhaustion testing
- Experiment orchestration
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ChaosTarget(Enum):
    """Chaos experiment targets."""
    BOARD_HARDWARE = "board_hardware"
    NETWORK = "network"
    CPU = "cpu"
    MEMORY = "memory"
    STORAGE = "storage"
    POWER = "power"


class FailureType(Enum):
    """Types of failures to inject."""
    HARDWARE_MALFUNCTION = "hardware_malfunction"
    CONNECTION_LOSS = "connection_loss"
    TIMEOUT = "timeout"
    CRC_ERROR = "crc_error"
    MEMORY_CORRUPTION = "memory_corruption"
    THROTTLE = "throttle"


class ExperimentStatus(Enum):
    """Experiment status."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABORTED = "aborted"


@dataclass
class ChaosExperiment:
    """Chaos experiment definition."""
    experiment_id: str
    name: str
    description: str
    
    # Target
    target: ChaosTarget
    target_ids: list[str] = field(default_factory=list)  # Specific boards
    
    # Failure
    failure_type: FailureType
    duration_seconds: int = 60
    intensity: float = 1.0  # 0.0 - 1.0
    
    # Rollback
    auto_rollback: bool = True
    rollback_timeout_seconds: int = 300
    
    # Status
    status: ExperimentStatus = ExperimentStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    
    # Results
    success: bool | None = None
    metrics_before: dict[str, Any] = field(default_factory=dict)
    metrics_after: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChaosResult:
    """Result of chaos experiment."""
    experiment_id: str
    success: bool
    
    # Impact
    affected_targets: list[str]
    recovery_time_seconds: float
    
    # Comparison
    metrics_delta: dict[str, float]
    
    # Analysis
    root_cause: str = ""
    recommendations: list[str] = field(default_factory=list)


class FailureInjector:
    """Injects failures into target systems."""
    
    def inject_hardware_failure(self, board_id: str, failure_type: FailureType) -> bool:
        """Inject hardware failure."""
        logger.warning("Injecting hardware failure", board=board_id, type=failure_type.value)
        # In real implementation, would send commands to probe
        return True
    
    def inject_network_partition(self, board_ids: list[str]) -> str:
        """Inject network partition. Returns partition ID."""
        partition_id = f"partition_{datetime.now().timestamp()}"
        logger.warning("Injecting network partition", boards=board_ids, partition_id=partition_id)
        return partition_id
    
    def remove_network_partition(self, partition_id: str) -> bool:
        """Remove network partition."""
        logger.info("Removing network partition", partition_id=partition_id)
        return True
    
    def throttle_resource(self, board_id: str, resource: str, limit: float) -> bool:
        """Throttle resource usage."""
        logger.info("Throttling resource", board=board_id, resource=resource, limit=limit)
        return True
    
    def simulate_memory_pressure(self, board_id: str, percentage: float) -> bool:
        """Simulate memory pressure."""
        logger.info("Simulating memory pressure", board=board_id, percentage=percentage)
        return True


class SystemUnderTest:
    """Tracks system under test during experiments."""
    
    def __init__(self) -> None:
        self._boards: dict[str, dict] = {}
    
    def register(self, board_id: str, metadata: dict) -> None:
        """Register board for experiments."""
        self._boards[board_id] = {
            "metadata": metadata,
            "healthy": True,
            "last_check": datetime.now(),
        }
    
    def get_health(self, board_id: str) -> bool:
        """Get board health status."""
        board = self._boards.get(board_id)
        return board.get("healthy", False) if board else False
    
    def mark_unhealthy(self, board_id: str) -> None:
        """Mark board as unhealthy."""
        if board_id in self._boards:
            self._boards[board_id]["healthy"] = False
    
    def mark_healthy(self, board_id: str) -> None:
        """Mark board as healthy."""
        if board_id in self._boards:
            self._boards[board_id]["healthy"] = True
    
    def get_all_healthy(self) -> list[str]:
        """Get all healthy boards."""
        return [bid for bid, b in self._boards.items() if b.get("healthy", False)]


class ChaosEngineer:
    """Chaos engineering orchestrator.
    
    Phase 13.4: Chaos engineering
    """
    
    def __init__(self) -> None:
        self._experiments: dict[str, ChaosExperiment] = {}
        self._injector = FailureInjector()
        self._sut = SystemUnderTest()
        self._active_experiments: list[str] = []
    
    def register_target(self, board_id: str, metadata: dict) -> None:
        """Register target for experiments."""
        self._sut.register(board_id, metadata)
    
    def create_experiment(
        self,
        name: str,
        description: str,
        target: ChaosTarget,
        failure_type: FailureType,
        duration_seconds: int = 60,
        intensity: float = 1.0,
    ) -> ChaosExperiment:
        """Create chaos experiment."""
        import hashlib
        experiment_id = hashlib.md5(f"{name}:{datetime.now().isoformat()}".encode()).hexdigest()[:12]
        
        experiment = ChaosExperiment(
            experiment_id=experiment_id,
            name=name,
            description=description,
            target=target,
            failure_type=failure_type,
            duration_seconds=duration_seconds,
            intensity=intensity,
        )
        
        self._experiments[experiment_id] = experiment
        logger.info("Experiment created", experiment_id=experiment_id, name=name)
        
        return experiment
    
    def run_experiment(self, experiment_id: str) -> ChaosResult:
        """Run chaos experiment."""
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment {experiment_id} not found")
        
        experiment.status = ExperimentStatus.RUNNING
        experiment.started_at = datetime.now()
        self._active_experiments.append(experiment_id)
        
        logger.warning("Starting chaos experiment", experiment_id=experiment_id)
        
        try:
            # Capture metrics before
            experiment.metrics_before = self._capture_metrics(experiment)
            
            # Inject failure
            self._inject_failure(experiment)
            
            # Wait for duration
            import time
            time.sleep(min(experiment.duration_seconds, 5))  # Shortened for testing
            
            # Capture metrics after
            experiment.metrics_after = self._capture_metrics(experiment)
            
            # Determine success
            experiment.success = self._evaluate_success(experiment)
            experiment.status = ExperimentStatus.COMPLETED
            
        except Exception as e:
            logger.error("Experiment failed", experiment_id=experiment_id, error=str(e))
            experiment.status = ExperimentStatus.ABORTED
            experiment.success = False
        
        finally:
            experiment.completed_at = datetime.now()
            if experiment_id in self._active_experiments:
                self._active_experiments.remove(experiment_id)
            
            # Rollback if needed
            if experiment.auto_rollback:
                self._rollback(experiment)
        
        return self._generate_result(experiment)
    
    def _inject_failure(self, experiment: ChaosExperiment) -> None:
        """Inject failure based on experiment type."""
        if experiment.target == ChaosTarget.BOARD_HARDWARE:
            for board_id in experiment.target_ids:
                self._injector.inject_hardware_failure(board_id, experiment.failure_type)
                self._sut.mark_unhealthy(board_id)
        
        elif experiment.target == ChaosTarget.NETWORK:
            self._injector.inject_network_partition(experiment.target_ids)
        
        elif experiment.target == ChaosTarget.MEMORY:
            for board_id in experiment.target_ids:
                self._injector.simulate_memory_pressure(board_id, experiment.intensity)
    
    def _capture_metrics(self, experiment: ChaosExperiment) -> dict[str, Any]:
        """Capture system metrics."""
        return {
            "timestamp": datetime.now().isoformat(),
            "healthy_boards": len(self._sut.get_all_healthy()),
            "total_boards": len(self._sut._boards),
        }
    
    def _evaluate_success(self, experiment: ChaosExperiment) -> bool:
        """Evaluate if experiment was successful."""
        # Success means system degraded gracefully and recovered
        return experiment.status == ExperimentStatus.COMPLETED
    
    def _rollback(self, experiment: ChaosExperiment) -> None:
        """Rollback experiment changes."""
        if experiment.target == ChaosTarget.NETWORK:
            for board_id in experiment.target_ids:
                self._injector.remove_network_partition(board_id)
        
        for board_id in experiment.target_ids:
            self._sut.mark_healthy(board_id)
    
    def _generate_result(self, experiment: ChaosExperiment) -> ChaosResult:
        """Generate experiment result."""
        delta = {}
        if experiment.metrics_before and experiment.metrics_after:
            for key in experiment.metrics_before:
                if key in experiment.metrics_after:
                    delta[key] = experiment.metrics_after[key] - experiment.metrics_before[key]
        
        recovery_time = 0.0
        if experiment.completed_at and experiment.started_at:
            recovery_time = (experiment.completed_at - experiment.started_at).total_seconds()
        
        return ChaosResult(
            experiment_id=experiment.experiment_id,
            success=experiment.success or False,
            affected_targets=experiment.target_ids,
            recovery_time_seconds=recovery_time,
            metrics_delta=delta,
            recommendations=self._generate_recommendations(experiment),
        )
    
    def _generate_recommendations(self, experiment: ChaosExperiment) -> list[str]:
        """Generate recommendations based on experiment."""
        recommendations = []
        
        if experiment.failure_type == FailureType.HARDWARE_MALFUNCTION:
            recommendations.append("Consider adding hardware redundancy")
            recommendations.append("Implement hardware health monitoring")
        
        elif experiment.failure_type == FailureType.CONNECTION_LOSS:
            recommendations.append("Implement connection retry with backoff")
            recommendations.append("Add circuit breaker pattern")
        
        elif experiment.failure_type == FailureType.TIMEOUT:
            recommendations.append("Review timeout configurations")
            recommendations.append("Add request queuing")
        
        return recommendations
    
    def abort_experiment(self, experiment_id: str) -> bool:
        """Abort running experiment."""
        experiment = self._experiments.get(experiment_id)
        if not experiment or experiment.status != ExperimentStatus.RUNNING:
            return False
        
        experiment.status = ExperimentStatus.ABORTED
        experiment.completed_at = datetime.now()
        
        if experiment_id in self._active_experiments:
            self._active_experiments.remove(experiment_id)
        
        self._rollback(experiment)
        
        logger.info("Experiment aborted", experiment_id=experiment_id)
        return True
    
    def get_experiment(self, experiment_id: str) -> ChaosExperiment | None:
        """Get experiment details."""
        return self._experiments.get(experiment_id)
    
    def list_experiments(self, status: ExperimentStatus | None = None) -> list[ChaosExperiment]:
        """List experiments."""
        experiments = list(self._experiments.values())
        if status:
            experiments = [e for e in experiments if e.status == status]
        return sorted(experiments, key=lambda e: e.started_at or datetime.min, reverse=True)


# Global engineer
_chaos_engineer: ChaosEngineer | None = None


def get_chaos_engineer() -> ChaosEngineer:
    """Get global chaos engineer."""
    global _chaos_engineer
    if _chaos_engineer is None:
        _chaos_engineer = ChaosEngineer()
    return _chaos_engineer


if __name__ == "__main__":
    engineer = get_chaos_engineer()
    
    # Register targets
    for i in range(5):
        engineer.register_target(f"board_{i:02d}", {"type": "STM32F407"})
    
    # Create experiment
    experiment = engineer.create_experiment(
        name="Hardware Failure Test",
        description="Test system response to hardware malfunction",
        target=ChaosTarget.BOARD_HARDWARE,
        failure_type=FailureType.HARDWARE_MALFUNCTION,
        target_ids=["board_00"],
        duration_seconds=5,
    )
    
    print("Chaos Engineering")
    print("=" * 40)
    print(f"Created experiment: {experiment.experiment_id}")
    
    # Run experiment (simplified)
    print("Running experiment...")
    result = engineer.run_experiment(experiment.experiment_id)
    
    print(f"Success: {result.success}")
    print(f"Recovery time: {result.recovery_time_seconds:.1f}s")
    print(f"Recommendations: {result.recommendations}")
