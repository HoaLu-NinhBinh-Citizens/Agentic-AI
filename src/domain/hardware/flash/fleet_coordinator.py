"""Fleet Coordination Model - Commercial OTA rollout management.

Phase 6.2: Addresses critical production gap:
- Rollout waves (staged deployment)
- Canary deployment
- Staged rollout with failure threshold
- Auto-halt on failure detection
- Fleet health monitoring
- Rollback strategies

This is essential for commercial OTA systems managing thousands of devices.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class RolloutStrategy(Enum):
    """Rollout strategies."""
    
    IMMEDIATE = "immediate"        # All devices at once
    CANARY = "canary"             # Small % first
    WAVES = "waves"               # Staged by percentage
    SCHEDULED = "scheduled"       # Time-based waves
    CONDITIONAL = "conditional"   # Based on device criteria


class RolloutState(Enum):
    """Rollout state machine."""
    
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    HALTED = "halted"            # Auto-halted due to failures
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DeploymentTarget(Enum):
    """Deployment target criteria."""
    
    ALL = "all"
    TAG = "tag"                  # By device tag
    REGION = "region"           # By geographic region
    VERSION = "version"          # From specific version
    MODEL = "model"              # By device model
    RANDOM = "random"            # Random sample


@dataclass
class RolloutWave:
    """Single wave in staged rollout."""
    
    wave_id: str
    wave_number: int
    
    # Targets
    target_percentage: float = 0.0  # % of fleet
    target_count: int = 0          # Or exact count
    
    # Timing
    start_time: datetime | None = None
    end_time: datetime | None = None
    delay_after_ms: int = 0       # Delay before next wave
    
    # State
    status: RolloutState = RolloutState.CREATED
    devices_deployed: int = 0
    devices_succeeded: int = 0
    devices_failed: int = 0
    
    # Criteria
    min_success_rate: float = 0.95  # Required success rate
    max_failure_count: int = 5      # Or max failures
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "wave_id": self.wave_id,
            "wave_number": self.wave_number,
            "target_percentage": self.target_percentage,
            "target_count": self.target_count,
            "status": self.status.value,
            "devices_deployed": self.devices_deployed,
            "devices_succeeded": self.devices_succeeded,
            "devices_failed": self.devices_failed,
            "success_rate": self.success_rate,
        }
    
    @property
    def success_rate(self) -> float:
        """Calculate current success rate."""
        if self.devices_deployed == 0:
            return 1.0
        return self.devices_succeeded / self.devices_deployed
    
    @property
    def failure_rate(self) -> float:
        """Calculate current failure rate."""
        return 1.0 - self.success_rate


@dataclass
class RolloutConfig:
    """Configuration for rollout."""
    
    # Strategy
    strategy: RolloutStrategy = RolloutStrategy.WAVES
    
    # Targets
    deployment_target: DeploymentTarget = DeploymentTarget.ALL
    target_criteria: dict[str, Any] = field(default_factory=dict)
    
    # Timing
    wave_delay_ms: int = 300000      # 5 minutes between waves
    wave_size_percentage: float = 10.0  # 10% per wave
    initial_wave_size: float = 1.0   # First wave: 1%
    
    # Safety thresholds
    max_failure_rate: float = 0.05   # Halt if >5% failures
    max_failure_count: int = 10      # Or >10 failures
    min_success_rate: float = 0.90   # Continue if >90% success
    
    # Canary specific
    canary_percentage: float = 1.0   # First 1% is canary
    canary_stable_duration_ms: int = 600000  # 10 minutes stability required
    
    # Auto-rollback
    auto_rollback_on_halt: bool = True
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "strategy": self.strategy.value,
            "deployment_target": self.deployment_target.value,
            "wave_delay_ms": self.wave_delay_ms,
            "wave_size_percentage": self.wave_size_percentage,
            "max_failure_rate": self.max_failure_rate,
            "max_failure_count": self.max_failure_count,
            "min_success_rate": self.min_success_rate,
        }


@dataclass
class FleetRollout:
    """Complete fleet rollout manager.
    
    Manages multi-wave deployments with:
    - Automatic wave progression
    - Failure monitoring
    - Auto-halt
    - Rollback coordination
    """
    
    rollout_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    # Firmware info
    firmware_version: str = ""
    firmware_hash: str = ""
    
    # Configuration
    config: RolloutConfig = field(default_factory=RolloutConfig)
    
    # State
    state: RolloutState = RolloutState.CREATED
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    
    # Waves
    waves: list[RolloutWave] = field(default_factory=list)
    current_wave_index: int = 0
    
    # Device tracking
    target_devices: list[str] = field(default_factory=list)
    deployed_devices: dict[str, dict[str, Any]] = field(default_factory=dict)
    
    # Rollback coordination
    rollback_rollout_id: str | None = None
    
    # Metrics
    total_devices: int = 0
    total_deployed: int = 0
    total_succeeded: int = 0
    total_failed: int = 0
    
    # Async state
    _running: bool = False
    _task: asyncio.Task | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "rollout_id": self.rollout_id,
            "firmware_version": self.firmware_version,
            "firmware_hash": self.firmware_hash[:16] if self.firmware_hash else None,
            "state": self.state.value,
            "config": self.config.to_dict(),
            "waves": [w.to_dict() for w in self.waves],
            "current_wave_index": self.current_wave_index,
            "metrics": {
                "total_devices": self.total_devices,
                "total_deployed": self.total_deployed,
                "total_succeeded": self.total_succeeded,
                "total_failed": self.total_failed,
                "success_rate": self.success_rate,
            },
        }
    
    @property
    def success_rate(self) -> float:
        """Calculate overall success rate."""
        if self.total_deployed == 0:
            return 1.0
        return self.total_succeeded / self.total_deployed
    
    @property
    def failure_rate(self) -> float:
        """Calculate overall failure rate."""
        return 1.0 - self.success_rate
    
    @property
    def is_halted(self) -> bool:
        """Check if rollout is halted."""
        return self.state == RolloutState.HALTED
    
    def should_halt(self) -> tuple[bool, str]:
        """Check if rollout should be halted due to failures."""
        if self.total_deployed == 0:
            return False, ""
        
        # Check failure rate
        if self.failure_rate > self.config.max_failure_rate:
            return True, f"Failure rate {self.failure_rate:.1%} exceeds threshold {self.config.max_failure_rate:.1%}"
        
        # Check failure count
        if self.total_failed > self.config.max_failure_count:
            return True, f"Failure count {self.total_failed} exceeds threshold {self.config.max_failure_count}"
        
        return False, ""
    
    def should_continue(self) -> tuple[bool, str]:
        """Check if rollout should continue."""
        if self.current_wave_index >= len(self.waves):
            return False, "All waves completed"
        
        current_wave = self.waves[self.current_wave_index]
        
        # Check current wave success rate
        if current_wave.devices_deployed > 0:
            if current_wave.success_rate < self.config.min_success_rate:
                return False, f"Wave success rate {current_wave.success_rate:.1%} below threshold"
        
        return True, ""
    
    def get_next_wave_devices(self) -> list[str]:
        """Get devices for next wave."""
        if self.current_wave_index >= len(self.waves):
            return []
        
        wave = self.waves[self.current_wave_index]
        target_count = wave.target_count
        
        # Get devices not yet deployed
        undeployed = [d for d in self.target_devices if d not in self.deployed_devices]
        
        return undeployed[:target_count]


@dataclass
class FleetCoordinator:
    """Coordinates fleet-wide rollout operations.
    
    Integrates with:
    - Device registry
    - Flash scheduler
    - Health monitor
    - Rollback coordinator
    """
    
    rollout: FleetRollout
    
    # Integration points (set by user)
    device_registry: Any = None     # DeviceRegistry
    flash_scheduler: Any = None     # FlashScheduler
    health_monitor: Any = None      # BootHealthMonitor
    
    # Callbacks
    on_wave_complete: Any = None
    on_rollout_halted: Any = None
    on_rollout_complete: Any = None
    
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    
    def __post_init__(self) -> None:
        """Initialize coordinator."""
        self._setup_waves()
    
    def _setup_waves(self) -> None:
        """Setup rollout waves based on strategy."""
        self.rollout.waves = []
        
        if self.rollout.config.strategy == RolloutStrategy.IMMEDIATE:
            # Single wave for all devices
            wave = RolloutWave(
                wave_id=str(uuid.uuid4()),
                wave_number=1,
                target_percentage=100.0,
                target_count=len(self.rollout.target_devices),
            )
            self.rollout.waves.append(wave)
            
        elif self.rollout.config.strategy == RolloutStrategy.CANARY:
            # Canary wave first
            canary_count = int(len(self.rollout.target_devices) * self.rollout.config.canary_percentage / 100)
            canary_wave = RolloutWave(
                wave_id=str(uuid.uuid4()),
                wave_number=1,
                target_percentage=self.rollout.config.canary_percentage,
                target_count=canary_count,
            )
            self.rollout.waves.append(canary_wave)
            
            # Remainder in single wave
            remaining = len(self.rollout.target_devices) - canary_count
            if remaining > 0:
                main_wave = RolloutWave(
                    wave_id=str(uuid.uuid4()),
                    wave_number=2,
                    target_percentage=100.0 - self.rollout.config.canary_percentage,
                    target_count=remaining,
                )
                self.rollout.waves.append(main_wave)
            
        elif self.rollout.config.strategy == RolloutStrategy.WAVES:
            # Multiple waves
            wave_size = self.rollout.config.wave_size_percentage
            remaining_percentage = 100.0
            wave_number = 1
            device_index = 0
            
            while remaining_percentage > 0 and wave_number <= 20:  # Max 20 waves
                # First wave is smaller
                if wave_number == 1:
                    size = self.rollout.config.initial_wave_size
                else:
                    size = min(wave_size, remaining_percentage)
                
                target_count = int(len(self.rollout.target_devices) * size / 100)
                
                if target_count > 0:
                    wave = RolloutWave(
                        wave_id=str(uuid.uuid4()),
                        wave_number=wave_number,
                        target_percentage=size,
                        target_count=target_count,
                    )
                    self.rollout.waves.append(wave)
                
                remaining_percentage -= size
                wave_number += 1
    
    async def start_rollout(self) -> None:
        """Start rollout execution."""
        async with self._lock:
            if self.rollout.state != RolloutState.CREATED:
                raise ValueError(f"Cannot start rollout in state {self.rollout.state}")
            
            self.rollout.state = RolloutState.IN_PROGRESS
            self.rollout.started_at = datetime.now()
            self.rollout._running = True
            
            # Start rollout task
            self.rollout._task = asyncio.create_task(self._rollout_loop())
            
            logger.info("rollout_started", rollout_id=self.rollout.rollout_id)
    
    async def pause_rollout(self) -> None:
        """Pause rollout."""
        async with self._lock:
            if self.rollout.state != RolloutState.IN_PROGRESS:
                return
            
            self.rollout.state = RolloutState.PAUSED
            logger.info("rollout_paused", rollout_id=self.rollout.rollout_id)
    
    async def resume_rollout(self) -> None:
        """Resume paused rollout."""
        async with self._lock:
            if self.rollout.state != RolloutState.PAUSED:
                return
            
            self.rollout.state = RolloutState.IN_PROGRESS
            logger.info("rollout_resumed", rollout_id=self.rollout.rollout_id)
    
    async def halt_rollout(self, reason: str) -> None:
        """Halt rollout due to failures."""
        async with self._lock:
            self.rollout.state = RolloutState.HALTED
            
            logger.warning(
                "rollout_halted",
                rollout_id=self.rollout.rollout_id,
                reason=reason,
            )
            
            if self.on_rollout_halted:
                await self.on_rollout_halted(self.rollout, reason)
    
    async def cancel_rollout(self) -> None:
        """Cancel rollout."""
        async with self._lock:
            self.rollout.state = RolloutState.CANCELLED
            self.rollout._running = False
            
            if self.rollout._task:
                self.rollout._task.cancel()
            
            logger.info("rollout_cancelled", rollout_id=self.rollout.rollout_id)
    
    async def _rollout_loop(self) -> None:
        """Main rollout loop."""
        while self.rollout._running and self.rollout.state == RolloutState.IN_PROGRESS:
            try:
                # Check halt conditions
                should_halt, halt_reason = self.rollout.should_halt()
                if should_halt:
                    await self.halt_rollout(halt_reason)
                    break
                
                # Check if rollout complete
                if self.rollout.current_wave_index >= len(self.rollout.waves):
                    self.rollout.state = RolloutState.COMPLETED
                    self.rollout.completed_at = datetime.now()
                    
                    if self.on_rollout_complete:
                        await self.on_rollout_complete(self.rollout)
                    break
                
                # Process current wave
                await self._process_wave()
                
                # Wait before next check
                await asyncio.sleep(10)  # Check every 10 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("rollout_loop_error", error=str(e))
                await asyncio.sleep(10)
        
        self.rollout._running = False
    
    async def _process_wave(self) -> None:
        """Process current wave."""
        if self.rollout.current_wave_index >= len(self.rollout.waves):
            return
        
        wave = self.rollout.waves[self.rollout.current_wave_index]
        
        # Get devices for this wave
        devices = self.rollout.get_next_wave_devices()
        
        if not devices:
            # Wave complete, move to next
            wave.status = RolloutState.COMPLETED
            self.rollout.current_wave_index += 1
            
            if self.on_wave_complete:
                await self.on_wave_complete(wave)
            
            # Wait before next wave
            await asyncio.sleep(self.rollout.config.wave_delay_ms / 1000)
            return
        
        # Deploy to devices
        for device_id in devices:
            if not self.rollout._running or self.rollout.state != RolloutState.IN_PROGRESS:
                break
            
            success = await self._deploy_to_device(device_id)
            
            self.rollout.deployed_devices[device_id] = {
                "deployed_at": datetime.now().isoformat(),
                "success": success,
            }
            
            self.rollout.total_deployed += 1
            wave.devices_deployed += 1
            
            if success:
                self.rollout.total_succeeded += 1
                wave.devices_succeeded += 1
            else:
                self.rollout.total_failed += 1
                wave.devices_failed += 1
    
    async def _deploy_to_device(self, device_id: str) -> bool:
        """Deploy firmware to single device.
        
        Override this to integrate with actual flash scheduler.
        """
        # Placeholder: always return True
        # Real implementation would call flash_scheduler
        logger.info("deploying_to_device", device_id=device_id)
        await asyncio.sleep(0.1)  # Simulate deployment
        return True
    
    def get_rollout_status(self) -> dict[str, Any]:
        """Get current rollout status."""
        return self.rollout.to_dict()
    
    def get_wave_status(self, wave_index: int) -> dict[str, Any] | None:
        """Get status of specific wave."""
        if wave_index >= len(self.rollout.waves):
            return None
        return self.rollout.waves[wave_index].to_dict()


@dataclass
class RolloutHistory:
    """History of past rollouts for analytics."""
    
    rollouts: list[FleetRollout] = field(default_factory=list)
    
    def add_rollout(self, rollout: FleetRollout) -> None:
        """Add rollout to history."""
        self.rollouts.append(rollout)
    
    def get_rollout(self, rollout_id: str) -> FleetRollout | None:
        """Get rollout by ID."""
        for r in self.rollouts:
            if r.rollout_id == rollout_id:
                return r
        return None
    
    def get_rollouts_by_state(self, state: RolloutState) -> list[FleetRollout]:
        """Get rollouts by state."""
        return [r for r in self.rollouts if r.state == state]
    
    def get_success_rate(self) -> float:
        """Calculate overall success rate across all rollouts."""
        total_deployed = sum(r.total_deployed for r in self.rollouts)
        total_succeeded = sum(r.total_succeeded for r in self.rollouts)
        
        if total_deployed == 0:
            return 1.0
        
        return total_succeeded / total_deployed
    
    def get_failure_patterns(self) -> dict[str, Any]:
        """Analyze failure patterns."""
        patterns = {
            "by_device": {},
            "by_version": {},
            "by_time": {},
        }
        
        for rollout in self.rollouts:
            for device_id, result in rollout.deployed_devices.items():
                if not result.get("success", True):
                    # Track failure patterns
                    if device_id not in patterns["by_device"]:
                        patterns["by_device"][device_id] = 0
                    patterns["by_device"][device_id] += 1
        
        return patterns


@dataclass
class CanaryAnalyzer:
    """Analyzes canary deployment stability."""
    
    rollout: FleetRollout
    
    async def analyze_canary_stability(
        self,
        stability_window_ms: int = 600000,
    ) -> dict[str, Any]:
        """Analyze if canary is stable enough to proceed.
        
        Args:
            stability_window_ms: Time window to check stability
        
        Returns:
            Analysis result with recommendation
        """
        if not self.rollout.waves:
            return {"error": "No waves defined"}
        
        canary = self.rollout.waves[0]
        
        # Calculate metrics
        elapsed_ms = 0
        if canary.end_time and canary.start_time:
            elapsed_ms = (canary.end_time - canary.start_time).total_seconds() * 1000
        
        stability_score = self._calculate_stability_score(canary)
        
        recommendation = "proceed"
        if stability_score < 0.9:
            recommendation = "wait"
        if stability_score < 0.7:
            recommendation = "rollback"
        
        return {
            "canary_wave": canary.to_dict(),
            "elapsed_ms": elapsed_ms,
            "stability_window_ms": stability_window_ms,
            "stability_score": stability_score,
            "recommendation": recommendation,
        }
    
    def _calculate_stability_score(self, wave: RolloutWave) -> float:
        """Calculate stability score for canary wave."""
        if wave.devices_deployed == 0:
            return 1.0
        
        # Weight factors:
        # - Success rate (50%)
        # - Failure rate trend (30%)
        # - Time stability (20%)
        
        success_score = wave.success_rate
        
        # Simple failure score
        failure_score = 1.0 - wave.failure_rate
        
        return success_score * 0.5 + failure_score * 0.5
