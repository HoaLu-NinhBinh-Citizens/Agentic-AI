"""Auto fine-tune scheduler (Phase 16.4d).

Provides automatic model fine-tuning on schedule:
- Monthly training triggers
- Dataset accumulation
- Quality gates
- Model promotion
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SchedulerStatus(Enum):
    """Scheduler status."""
    IDLE = "idle"
    COLLECTING = "collecting"
    TRAINING = "training"
    EVALUATING = "evaluating"
    PROMOTING = "promoting"


@dataclass
class FineTuneConfig:
    """Fine-tune configuration."""
    schedule: str = "monthly"  # monthly, weekly, daily
    min_samples: int = 1000
    min_quality_score: float = 0.8
    
    # Training
    base_model: str = "llama3"
    epochs: int = 3
    batch_size: int = 4
    
    # Promotion
    require_approval: bool = True
    canary_percentage: int = 5


@dataclass
class FineTuneSchedule:
    """Fine-tune schedule entry."""
    schedule_id: str
    scheduled_at: datetime
    status: SchedulerStatus
    
    # Data collection
    samples_collected: int = 0
    quality_score: float = 0.0
    
    # Training
    training_started_at: datetime | None = None
    training_completed_at: datetime | None = None
    model_version: str = ""
    
    # Promotion
    promoted_at: datetime | None = None
    promoted_by: str = ""


class DatasetAccumulator:
    """Accumulates training data."""
    
    def __init__(self) -> None:
        self._samples: list[dict] = []
        self._quality_scores: list[float] = []
    
    def add_sample(self, sample: dict, quality_score: float) -> None:
        """Add training sample."""
        self._samples.append(sample)
        self._quality_scores.append(quality_score)
        
        logger.debug("Sample added", quality=quality_score)
    
    def get_dataset(self) -> dict[str, Any]:
        """Get accumulated dataset."""
        if not self._samples:
            return {"samples": [], "count": 0, "quality_score": 0.0}
        
        avg_quality = sum(self._quality_scores) / len(self._quality_scores)
        
        return {
            "samples": self._samples.copy(),
            "count": len(self._samples),
            "quality_score": avg_quality,
        }
    
    def clear(self) -> None:
        """Clear accumulated data."""
        self._samples.clear()
        self._quality_scores.clear()


class AutoFineTuner:
    """Automatic fine-tuning scheduler.
    
    Phase 16.4d: Auto fine-tune hàng tháng
    """
    
    def __init__(self, config: FineTuneConfig | None = None) -> None:
        self._config = config or FineTuneConfig()
        self._accumulator = DatasetAccumulator()
        self._schedules: list[FineTuneSchedule] = []
        self._current_schedule: FineTuneSchedule | None = None
        self._status = SchedulerStatus.IDLE
    
    @property
    def status(self) -> SchedulerStatus:
        """Get scheduler status."""
        return self._status
    
    def start_collection(self) -> FineTuneSchedule:
        """Start data collection period."""
        import hashlib
        schedule_id = hashlib.md5(f"{datetime.now().isoformat()}".encode()).hexdigest()[:12]
        
        schedule = FineTuneSchedule(
            schedule_id=schedule_id,
            scheduled_at=datetime.now(),
            status=SchedulerStatus.COLLECTING,
        )
        
        self._current_schedule = schedule
        self._status = SchedulerStatus.COLLECTING
        self._schedules.append(schedule)
        
        logger.info("Collection started", schedule_id=schedule_id)
        return schedule
    
    def add_training_data(self, sample: dict, quality_score: float) -> None:
        """Add training data sample."""
        if self._status != SchedulerStatus.COLLECTING:
            logger.warning("Not in collection mode")
            return
        
        self._accumulator.add_sample(sample, quality_score)
        
        if self._current_schedule:
            self._current_schedule.samples_collected = len(self._accumulator._samples)
            self._current_schedule.quality_score = self._accumulator.get_dataset()["quality_score"]
    
    def should_trigger_training(self) -> tuple[bool, str]:
        """Check if training should be triggered."""
        if not self._current_schedule:
            return False, "No active schedule"
        
        dataset = self._accumulator.get_dataset()
        
        # Check minimum samples
        if dataset["count"] < self._config.min_samples:
            return False, f"Not enough samples ({dataset['count']}/{self._config.min_samples})"
        
        # Check quality
        if dataset["quality_score"] < self._config.min_quality_score:
            return False, f"Quality too low ({dataset['quality_score']:.2f}/{self._config.min_quality_score})"
        
        return True, "Ready for training"
    
    def trigger_training(self) -> bool:
        """Trigger fine-tuning."""
        should_train, reason = self.should_trigger_training()
        
        if not should_train:
            logger.warning("Cannot trigger training", reason=reason)
            return False
        
        if self._current_schedule:
            self._current_schedule.status = SchedulerStatus.TRAINING
            self._status = SchedulerStatus.TRAINING
            self._current_schedule.training_started_at = datetime.now()
        
        logger.info("Training triggered")
        
        # In real implementation, would call training pipeline
        # Simulate training
        self._simulate_training()
        
        return True
    
    def _simulate_training(self) -> None:
        """Simulate training process."""
        if self._current_schedule:
            self._current_schedule.status = SchedulerStatus.EVALUATING
            self._status = SchedulerStatus.EVALUATING
            
            # Simulate evaluation
            self._current_schedule.model_version = f"v{datetime.now().strftime('%Y%m%d')}"
            
            self._current_schedule.status = SchedulerStatus.PROMOTING
            self._status = SchedulerStatus.PROMOTING
    
    def promote_model(self, approved_by: str) -> bool:
        """Promote trained model."""
        if not self._current_schedule:
            return False
        
        if self._config.require_approval and not approved_by:
            logger.warning("Approval required")
            return False
        
        self._current_schedule.status = SchedulerStatus.IDLE
        self._current_schedule.promoted_at = datetime.now()
        self._current_schedule.promoted_by = approved_by or "automatic"
        self._status = SchedulerStatus.IDLE
        
        # Clear accumulator
        self._accumulator.clear()
        
        logger.info("Model promoted", version=self._current_schedule.model_version)
        return True
    
    def get_next_schedule_time(self) -> datetime:
        """Get next scheduled training time."""
        if self._config.schedule == "monthly":
            # First day of next month
            now = datetime.now()
            next_month = now.replace(day=1) + timedelta(days=32)
            return next_month.replace(day=1, hour=2)  # 2 AM
        elif self._config.schedule == "weekly":
            return datetime.now() + timedelta(days=7)
        else:
            return datetime.now() + timedelta(days=1)
    
    def get_status(self) -> dict[str, Any]:
        """Get scheduler status."""
        return {
            "status": self._status.value,
            "schedule": self._config.schedule,
            "next_run": self.get_next_schedule_time().isoformat(),
            "current_schedule": {
                "samples": self._current_schedule.samples_collected if self._current_schedule else 0,
                "quality": self._current_schedule.quality_score if self._current_schedule else 0.0,
                "model_version": self._current_schedule.model_version if self._current_schedule else "",
            } if self._current_schedule else None,
            "config": {
                "min_samples": self._config.min_samples,
                "min_quality": self._config.min_quality_score,
            },
        }


# Global scheduler
_auto_tuner: AutoFineTuner | None = None


def get_auto_fine_tuner(config: FineTuneConfig | None = None) -> AutoFineTuner:
    """Get global auto fine-tuner."""
    global _auto_tuner
    if _auto_tuner is None:
        _auto_tuner = AutoFineTuner(config)
    return _auto_tuner


if __name__ == "__main__":
    tuner = get_auto_fine_tuner(FineTuneConfig(
        schedule="monthly",
        min_samples=100,
    ))
    
    print("Auto Fine-Tune Scheduler")
    print("=" * 40)
    
    # Start collection
    tuner.start_collection()
    
    # Add samples
    for i in range(150):
        sample = {"input": f"debug issue {i}", "output": f"fix {i}"}
        quality = 0.7 + (i % 30) / 100
        tuner.add_training_data(sample, quality)
    
    # Check status
    status = tuner.get_status()
    print(f"Status: {status['status']}")
    print(f"Samples: {status['current_schedule']['samples']}")
    print(f"Quality: {status['current_schedule']['quality']:.2f}")
    
    # Trigger training
    should_train, reason = tuner.should_trigger_training()
    print(f"\nShould train: {should_train} ({reason})")
    
    if should_train:
        tuner.trigger_training()
        tuner.promote_model("system")
        print("Model promoted!")
