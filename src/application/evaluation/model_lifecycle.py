"""Model lifecycle management with auto-rollback (Phase 12.3).

Provides model version management and automatic rollback:
- Model versioning
- Rollback triggers
- Canary deployment
- Performance monitoring
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ModelStatus(Enum):
    """Model deployment status."""
    STAGING = "staging"
    CANARY = "canary"
    PRODUCTION = "production"
    ROLLBACK = "rollback"
    DEPRECATED = "deprecated"


class RollbackTrigger(Enum):
    """Reasons for automatic rollback."""
    ACCURACY_DROP = "accuracy_drop"
    LATENCY_SPIKE = "latency_spike"
    ERROR_RATE = "error_rate"
    USER_FEEDBACK = "user_feedback"
    MANUAL = "manual"


@dataclass
class ModelVersion:
    """Model version information."""
    version_id: str
    model_name: str
    version: str
    
    # Metadata
    created_at: datetime
    created_by: str
    description: str = ""
    
    # Performance
    accuracy: float = 0.0
    latency_ms: float = 0.0
    error_rate: float = 0.0
    
    # Usage
    request_count: int = 0
    status: ModelStatus = ModelStatus.STAGING
    
    # Deployment
    traffic_percentage: int = 0
    rollout_started: datetime | None = None


@dataclass
class RollbackConfig:
    """Rollback configuration."""
    # Thresholds
    accuracy_drop_threshold: float = 0.05  # 5% drop triggers rollback
    latency_spike_threshold_ms: float = 100.0  # 100ms spike
    error_rate_threshold: float = 0.10  # 10% error rate
    
    # Timing
    evaluation_window_minutes: int = 60
    rollback_cooldown_minutes: int = 30
    
    # Canary
    canary_duration_minutes: int = 60
    canary_traffic_percentage: int = 5
    
    # Safety
    require_approval: bool = True
    max_rollbacks_per_day: int = 3


@dataclass
class RollbackEvent:
    """Rollback event record."""
    event_id: str
    from_version: str
    to_version: str
    trigger: RollbackTrigger
    triggered_at: datetime
    completed_at: datetime | None = None
    
    # Details
    accuracy_before: float = 0.0
    accuracy_after: float = 0.0
    reason: str = ""


class CanaryDeployer:
    """Canary deployment manager."""
    
    def __init__(self, config: RollbackConfig) -> None:
        self._config = config
    
    def start_canary(
        self,
        version: ModelVersion,
        current_prod: ModelVersion,
    ) -> bool:
        """Start canary deployment."""
        version.status = ModelStatus.CANARY
        version.traffic_percentage = self._config.canary_traffic_percentage
        version.rollout_started = datetime.now()
        
        logger.info(
            "Canary started",
            version=version.version,
            traffic=self._config.canary_traffic_percentage,
        )
        return True
    
    def promote_canary(self, version: ModelVersion) -> bool:
        """Promote canary to production."""
        version.status = ModelStatus.PRODUCTION
        version.traffic_percentage = 100
        logger.info("Canary promoted", version=version.version)
        return True
    
    def rollback_canary(self, version: ModelVersion) -> bool:
        """Rollback canary."""
        version.status = ModelStatus.DEPRECATED
        version.traffic_percentage = 0
        logger.info("Canary rolled back", version=version.version)
        return True


class RollbackMonitor:
    """Monitors for rollback triggers."""
    
    def __init__(self, config: RollbackConfig) -> None:
        self._config = config
        self._rollbacks_today: list[datetime] = []
    
    def check_triggers(
        self,
        version: ModelVersion,
        baseline: ModelVersion,
    ) -> RollbackTrigger | None:
        """Check if any rollback trigger is met."""
        # Reset daily count
        self._reset_daily_count()
        
        # Check max rollbacks
        if len(self._rollbacks_today) >= self._config.max_rollbacks_per_day:
            logger.warning("Max rollbacks reached for today")
            return None
        
        # Check accuracy drop
        if baseline.accuracy > 0 and version.accuracy < baseline.accuracy:
            drop = baseline.accuracy - version.accuracy
            if drop >= self._config.accuracy_drop_threshold:
                return RollbackTrigger.ACCURACY_DROP
        
        # Check latency spike
        if version.latency_ms > baseline.latency_ms + self._config.latency_spike_threshold_ms:
            return RollbackTrigger.LATENCY_SPIKE
        
        # Check error rate
        if version.error_rate >= self._config.error_rate_threshold:
            return RollbackTrigger.ERROR_RATE
        
        return None
    
    def _reset_daily_count(self) -> None:
        """Reset daily rollback count."""
        today = datetime.now().date()
        self._rollbacks_today = [
            dt for dt in self._rollbacks_today
            if dt.date() == today
        ]


class ModelLifecycleManager:
    """Manages model lifecycle with auto-rollback.
    
    Phase 12.3: Model rollback + Canary deployment
    """
    
    def __init__(self, config: RollbackConfig | None = None) -> None:
        self._config = config or RollbackConfig()
        self._versions: dict[str, ModelVersion] = {}
        self._events: list[RollbackEvent] = []
        self._canary = CanaryDeployer(self._config)
        self._monitor = RollbackMonitor(self._config)
    
    def register_model(
        self,
        version_id: str,
        model_name: str,
        version: str,
        created_by: str,
        description: str = "",
    ) -> ModelVersion:
        """Register new model version."""
        model = ModelVersion(
            version_id=version_id,
            model_name=model_name,
            version=version,
            created_at=datetime.now(),
            created_by=created_by,
            description=description,
        )
        self._versions[version_id] = model
        logger.info("Model registered", version_id=version_id, version=version)
        return model
    
    def get_current_production(self, model_name: str) -> ModelVersion | None:
        """Get current production model."""
        for v in self._versions.values():
            if v.model_name == model_name and v.status == ModelStatus.PRODUCTION:
                return v
        return None
    
    def start_canary(
        self,
        version_id: str,
        auto_approve: bool = False,
    ) -> bool:
        """Start canary deployment."""
        version = self._versions.get(version_id)
        if not version:
            return False
        
        current_prod = self.get_current_production(version.model_name)
        return self._canary.start_canary(version, current_prod)
    
    def evaluate_canary(
        self,
        version_id: str,
        evaluation_window_minutes: int | None = None,
    ) -> tuple[bool, RollbackTrigger | None]:
        """Evaluate canary deployment."""
        version = self._versions.get(version_id)
        if not version or version.status != ModelStatus.CANARY:
            return True, None
        
        # Check if enough time has passed
        window = evaluation_window_minutes or self._config.evaluation_window_minutes
        if version.rollout_started:
            elapsed = datetime.now() - version.rollout_started
            if elapsed < timedelta(minutes=window):
                return False, None
        
        # Get baseline
        baseline = self.get_current_production(version.model_name)
        if not baseline:
            # No baseline, auto-promote
            self._canary.promote_canary(version)
            return True, None
        
        # Check triggers
        trigger = self._monitor.check_triggers(version, baseline)
        
        if trigger:
            self._canary.rollback_canary(version)
            return False, trigger
        
        # Check canary duration
        if elapsed >= timedelta(minutes=self._config.canary_duration_minutes):
            self._canary.promote_canary(version)
            return True, None
        
        return False, None
    
    def rollback(
        self,
        version_id: str,
        trigger: RollbackTrigger,
        reason: str = "",
    ) -> bool:
        """Rollback to previous version."""
        version = self._versions.get(version_id)
        if not version:
            return False
        
        # Find previous production version
        previous = self.get_current_production(version.model_name)
        if not previous:
            logger.error("No previous version to rollback to")
            return False
        
        # Record event
        event = RollbackEvent(
            event_id=f"rb_{version_id}_{datetime.now().timestamp()}",
            from_version=version.version,
            to_version=previous.version,
            trigger=trigger,
            triggered_at=datetime.now(),
            accuracy_before=version.accuracy,
            accuracy_after=previous.accuracy,
            reason=reason,
        )
        self._events.append(event)
        
        # Update status
        version.status = ModelStatus.ROLLBACK
        previous.status = ModelStatus.PRODUCTION
        previous.traffic_percentage = 100
        
        logger.info(
            "Model rolled back",
            from_version=event.from_version,
            to_version=event.to_version,
            trigger=trigger.value,
        )
        
        return True
    
    def update_metrics(
        self,
        version_id: str,
        accuracy: float | None = None,
        latency_ms: float | None = None,
        error_rate: float | None = None,
    ) -> None:
        """Update version metrics."""
        version = self._versions.get(version_id)
        if not version:
            return
        
        if accuracy is not None:
            version.accuracy = accuracy
        if latency_ms is not None:
            version.latency_ms = latency_ms
        if error_rate is not None:
            version.error_rate = error_rate
    
    def get_rollback_history(self, model_name: str | None = None) -> list[RollbackEvent]:
        """Get rollback history."""
        events = self._events
        if model_name:
            # Filter by model (would need model info in event)
            pass
        return events
    
    def get_version(self, version_id: str) -> ModelVersion | None:
        """Get version info."""
        return self._versions.get(version_id)
    
    def list_versions(self, model_name: str | None = None) -> list[ModelVersion]:
        """List model versions."""
        versions = list(self._versions.values())
        if model_name:
            versions = [v for v in versions if v.model_name == model_name]
        return sorted(versions, key=lambda v: v.created_at, reverse=True)


# Global manager
_lifecycle_manager: ModelLifecycleManager | None = None


def get_lifecycle_manager(config: RollbackConfig | None = None) -> ModelLifecycleManager:
    """Get global lifecycle manager."""
    global _lifecycle_manager
    if _lifecycle_manager is None:
        _lifecycle_manager = ModelLifecycleManager(config)
    return _lifecycle_manager


if __name__ == "__main__":
    manager = get_lifecycle_manager()
    
    # Register versions
    v1 = manager.register_model("model_v1", "debug_assistant", "1.0.0", "engineer1", "Initial release")
    v1.accuracy = 0.80
    v1.status = ModelStatus.PRODUCTION
    
    v2 = manager.register_model("model_v2", "debug_assistant", "1.1.0", "engineer2", "Improved accuracy")
    v2.accuracy = 0.75  # Lower accuracy
    
    print("Model Lifecycle Manager")
    print("=" * 40)
    print(f"Current production: {manager.get_current_production('debug_assistant')}")
    
    # Start canary
    manager.start_canary("model_v2")
    print(f"Canary started: {manager.get_version('model_v2').status.value}")
    
    # Simulate metrics update
    manager.update_metrics("model_v2", accuracy=0.75, latency_ms=350, error_rate=0.12)
    
    # Evaluate
    passed, trigger = manager.evaluate_canary("model_v2")
    print(f"Canary evaluation: passed={passed}, trigger={trigger}")
    
    # Rollback history
    history = manager.get_rollback_history()
    print(f"\nRollback events: {len(history)}")
