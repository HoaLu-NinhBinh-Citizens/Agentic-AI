"""OTA Orchestrator for firmware updates (Phase 14.1).

Provides over-the-air firmware update orchestration:
- Rollout management
- Fleet targeting
- Progress tracking
- Rollback support
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class OTAStatus(Enum):
    """OTA rollout status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OTAEventType(Enum):
    """OTA event types."""
    STARTED = "started"
    PROGRESS = "progress"
    DEVICE_UPDATED = "device_updated"
    DEVICE_FAILED = "device_failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"


@dataclass
class OTAConfig:
    """OTA rollout configuration."""
    rollout_id: str
    firmware_version: str
    target_version: str
    
    # Targeting
    target_boards: list[str] = field(default_factory=list)  # Empty = all boards
    exclude_boards: list[str] = field(default_factory=list)
    
    # Strategy
    strategy: str = "rolling"  # rolling, canary, immediate
    batch_size: int = 10
    batch_delay_minutes: int = 5
    
    # Safety
    auto_rollback_on_failure: bool = True
    failure_threshold_percent: float = 10.0
    require_acknowledgment: bool = False
    
    # Timing
    start_after: datetime | None = None
    deadline: datetime | None = None
    timeout_minutes: int = 60


@dataclass
class DeviceOTAStatus:
    """Status of OTA on individual device."""
    device_id: str
    rollout_id: str
    
    status: OTAStatus = OTAStatus.PENDING
    progress_percent: float = 0.0
    
    # Timing
    queued_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    
    # Result
    success: bool | None = None
    error_message: str = ""
    logs: list[str] = field(default_factory=list)


@dataclass
class OTASnapshot:
    """Point-in-time rollout snapshot."""
    timestamp: datetime
    total_devices: int
    pending: int
    in_progress: int
    completed: int
    failed: int
    success_rate: float


class OTARollout:
    """Represents an OTA rollout."""
    
    def __init__(self, config: OTAConfig) -> None:
        self.config = config
        self.status = OTAStatus.PENDING
        
        # Device statuses
        self._devices: dict[str, DeviceOTAStatus] = {}
        for device_id in config.target_boards:
            self._devices[device_id] = DeviceOTAStatus(
                device_id=device_id,
                rollout_id=config.rollout_id,
                queued_at=datetime.now(),
            )
        
        # Events
        self._events: list[dict] = []
        
        # Statistics
        self._started_at: datetime | None = None
        self._completed_at: datetime | None = None
    
    @property
    def total_devices(self) -> int:
        return len(self._devices)
    
    @property
    def pending_count(self) -> int:
        return sum(1 for d in self._devices.values() if d.status == OTAStatus.PENDING)
    
    @property
    def in_progress_count(self) -> int:
        return sum(1 for d in self._devices.values() if d.status == OTAStatus.IN_PROGRESS)
    
    @property
    def completed_count(self) -> int:
        return sum(1 for d in self._devices.values() if d.status == OTAStatus.COMPLETED)
    
    @property
    def failed_count(self) -> int:
        return sum(1 for d in self._devices.values() if d.status == OTAStatus.FAILED)
    
    @property
    def success_rate(self) -> float:
        completed = self.completed_count + self.failed_count
        if completed == 0:
            return 0.0
        return self.completed_count / completed
    
    @property
    def progress_percent(self) -> float:
        if self.total_devices == 0:
            return 0.0
        return (self.completed_count + self.failed_count) / self.total_devices * 100
    
    def get_snapshot(self) -> OTASnapshot:
        """Get current snapshot."""
        return OTASnapshot(
            timestamp=datetime.now(),
            total_devices=self.total_devices,
            pending=self.pending_count,
            in_progress=self.in_progress_count,
            completed=self.completed_count,
            failed=self.failed_count,
            success_rate=self.success_rate,
        )
    
    def get_device_status(self, device_id: str) -> DeviceOTAStatus | None:
        """Get device status."""
        return self._devices.get(device_id)
    
    def update_device(
        self,
        device_id: str,
        status: OTAStatus,
        success: bool | None = None,
        error: str = "",
        progress: float | None = None,
    ) -> None:
        """Update device status."""
        device = self._devices.get(device_id)
        if not device:
            return
        
        device.status = status
        
        if status == OTAStatus.IN_PROGRESS and device.started_at is None:
            device.started_at = datetime.now()
        
        if success is not None:
            device.success = success
            device.completed_at = datetime.now()
        
        if error:
            device.error_message = error
        
        if progress is not None:
            device.progress_percent = progress
        
        # Add event
        self._events.append({
            "timestamp": datetime.now().isoformat(),
            "device_id": device_id,
            "status": status.value,
            "success": success,
        })


class OTAOrchestrator:
    """OTA orchestrator for firmware updates.
    
    Phase 14.1: OTA orchestrator (already exists)
    """
    
    def __init__(self) -> None:
        self._rollouts: dict[str, OTARollout] = {}
        self._device_registry: dict[str, dict] = {}
    
    def create_rollout(self, config: OTAConfig) -> str:
        """Create new OTA rollout."""
        rollout = OTARollout(config)
        self._rollouts[config.rollout_id] = rollout
        
        logger.info("OTA rollout created", rollout_id=config.rollout_id)
        return config.rollout_id
    
    def start_rollout(self, rollout_id: str) -> bool:
        """Start OTA rollout."""
        rollout = self._rollouts.get(rollout_id)
        if not rollout:
            return False
        
        rollout.status = OTAStatus.IN_PROGRESS
        rollout._started_at = datetime.now()
        
        # Start first batch
        self._process_batch(rollout_id)
        
        logger.info("OTA rollout started", rollout_id=rollout_id)
        return True
    
    def _process_batch(self, rollout_id: str) -> None:
        """Process next batch of devices."""
        rollout = self._rollouts.get(rollout_id)
        if not rollout:
            return
        
        # Find pending devices
        pending = [
            d for d in rollout._devices.values()
            if d.status == OTAStatus.PENDING
        ]
        
        # Process batch
        for device in pending[:rollout.config.batch_size]:
            device.status = OTAStatus.IN_PROGRESS
            device.started_at = datetime.now()
    
    def update_device_status(
        self,
        rollout_id: str,
        device_id: str,
        status: OTAStatus,
        success: bool | None = None,
        error: str = "",
        progress: float | None = None,
    ) -> None:
        """Update device OTA status."""
        rollout = self._rollouts.get(rollout_id)
        if not rollout:
            return
        
        rollout.update_device(device_id, status, success, error, progress)
        
        # Check for rollout completion or failure
        if rollout.failed_count / max(1, rollout.total_devices) > rollout.config.failure_threshold_percent / 100:
            rollout.status = OTAStatus.PAUSED
            logger.warning(
                "OTA rollout paused due to high failure rate",
                rollout_id=rollout_id,
                failure_rate=rollout.failed_count / rollout.total_devices,
            )
        
        if rollout.pending_count == 0 and rollout.in_progress_count == 0:
            rollout.status = OTAStatus.COMPLETED if rollout.failed_count == 0 else OTAStatus.FAILED
            rollout._completed_at = datetime.now()
    
    def pause_rollout(self, rollout_id: str) -> bool:
        """Pause OTA rollout."""
        rollout = self._rollouts.get(rollout_id)
        if not rollout:
            return False
        
        rollout.status = OTAStatus.PAUSED
        logger.info("OTA rollout paused", rollout_id=rollout_id)
        return True
    
    def resume_rollout(self, rollout_id: str) -> bool:
        """Resume paused rollout."""
        rollout = self._rollouts.get(rollout_id)
        if not rollout or rollout.status != OTAStatus.PAUSED:
            return False
        
        rollout.status = OTAStatus.IN_PROGRESS
        self._process_batch(rollout_id)
        
        logger.info("OTA rollout resumed", rollout_id=rollout_id)
        return True
    
    def cancel_rollout(self, rollout_id: str) -> bool:
        """Cancel OTA rollout."""
        rollout = self._rollouts.get(rollout_id)
        if not rollout:
            return False
        
        rollout.status = OTAStatus.CANCELLED
        
        # Mark pending/in-progress as cancelled
        for device in rollout._devices.values():
            if device.status in [OTAStatus.PENDING, OTAStatus.IN_PROGRESS]:
                device.status = OTAStatus.CANCELLED
        
        logger.info("OTA rollout cancelled", rollout_id=rollout_id)
        return True
    
    def rollback_rollout(self, rollout_id: str) -> bool:
        """Rollback OTA rollout to previous firmware."""
        rollout = self._rollouts.get(rollout_id)
        if not rollout:
            return False
        
        rollout.status = OTAStatus.IN_PROGRESS
        
        # Queue all devices for rollback
        for device in rollout._devices.values():
            if device.status == OTAStatus.COMPLETED:
                device.status = OTAStatus.PENDING
                device.success = None
        
        self._process_batch(rollout_id)
        
        logger.info("OTA rollout rollback initiated", rollout_id=rollout_id)
        return True
    
    def get_rollout_status(self, rollout_id: str) -> OTASnapshot | None:
        """Get rollout status snapshot."""
        rollout = self._rollouts.get(rollout_id)
        return rollout.get_snapshot() if rollout else None
    
    def list_active_rollouts(self) -> list[str]:
        """List active rollouts."""
        return [
            rid for rid, r in self._rollouts.items()
            if r.status in [OTAStatus.IN_PROGRESS, OTAStatus.PAUSED]
        ]
    
    def register_device(self, device_id: str, metadata: dict) -> None:
        """Register device for OTA."""
        self._device_registry[device_id] = metadata


# Global orchestrator
_orchestrator: OTAOrchestrator | None = None


def get_ota_orchestrator() -> OTAOrchestrator:
    """Get global OTA orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = OTAOrchestrator()
    return _orchestrator


if __name__ == "__main__":
    orchestrator = get_ota_orchestrator()
    
    # Create rollout
    config = OTAConfig(
        rollout_id="rollout_001",
        firmware_version="1.0.0",
        target_version="1.1.0",
        target_boards=[f"board_{i:03d}" for i in range(20)],
        batch_size=5,
        batch_delay_minutes=2,
    )
    orchestrator.create_rollout(config)
    
    # Start
    orchestrator.start_rollout("rollout_001")
    
    print("OTA Orchestrator")
    print("=" * 40)
    
    # Simulate progress
    rollout = orchestrator._rollouts["rollout_001"]
    for device_id in list(rollout._devices.keys())[:5]:
        orchestrator.update_device_status(
            "rollout_001",
            device_id,
            OTAStatus.COMPLETED,
            success=True,
        )
    
    # Status
    status = orchestrator.get_rollout_status("rollout_001")
    if status:
        print(f"Progress: {status.completed}/{status.total_devices} ({status.progress_percent:.1f}%)")
        print(f"Success rate: {status.success_rate:.1%}")
        print(f"Status: {rollout.status.value}")
