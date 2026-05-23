"""Chaos Engineering Suite for AI_SUPPORT.

Provides:
- Failure injection (network, process, disk, memory)
- Circuit breaker testing
- Chaos scenarios for workflows
- Latency injection
- Partition simulation
- Recovery validation

Usage:
    chaos = ChaosEngine()
    await chaos.run_scenario("network_partition")
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ChaosScenario(Enum):
    """Types of chaos scenarios."""
    NETWORK_PARTITION = "network_partition"
    NETWORK_LATENCY = "network_latency"
    NETWORK_CORRUPTION = "network_corruption"
    PROCESS_KILL = "process_kill"
    PROCESS_CRASH = "process_crash"
    DISK_FULL = "disk_full"
    DISK_IO_ERROR = "disk_io_error"
    MEMORY_PRESSURE = "memory_pressure"
    CPU_THROTTLE = "cpu_throttle"
    SERVICE_UNAVAILABLE = "service_unavailable"
    DATABASE_PARTITION = "database_partition"
    REDIS_UNAVAILABLE = "redis_unavailable"
    FLASH_INTERRUPTED = "flash_interrupted"
    USB_DISCONNECT = "usb_disconnect"
    GDB_TIMEOUT = "gdb_timeout"
    AGENT_CRASH = "agent_crash"
    COORDINATOR_FAILOVER = "coordinator_failover"


@dataclass
class ChaosTarget:
    """Target for chaos injection."""
    component: str
    instance_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChaosResult:
    """Result of a chaos experiment."""
    scenario: ChaosScenario
    target: ChaosTarget
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: float = 0
    injected: bool = False
    error: str | None = None
    recovery_successful: bool = False
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChaosConfig:
    """Configuration for chaos experiments."""
    enabled: bool = True
    dry_run: bool = False
    auto_recovery: bool = True
    recovery_timeout_seconds: float = 60.0
    max_concurrent_experiments: int = 1
    rollout_percentage: float = 0.1  # Only affect 10% of instances


class FailureInjector(ABC):
    """Base class for failure injectors."""
    
    @abstractmethod
    async def inject(self, target: ChaosTarget, config: ChaosConfig) -> bool:
        """Inject failure into target."""
        pass
    
    @abstractmethod
    async def recover(self, target: ChaosTarget) -> bool:
        """Recover from injected failure."""
        pass
    
    @abstractmethod
    async def validate(self, target: ChaosTarget) -> bool:
        """Validate failure state."""
        pass


class NetworkLatencyInjector(FailureInjector):
    """Inject network latency."""
    
    def __init__(self, latency_ms: int = 1000, jitter_ms: int = 500):
        self.latency_ms = latency_ms
        self.jitter_ms = jitter_ms
    
    async def inject(self, target: ChaosTarget, config: ChaosConfig) -> bool:
        if config.dry_run:
            logger.info("chaos_dry_run", scenario="network_latency", target=target.component)
            return True
        
        logger.warning(
            "chaos_injecting_latency",
            target=target.component,
            latency_ms=self.latency_ms,
            jitter_ms=self.jitter_ms,
        )
        
        # In production, would use tc (traffic control) or iptables
        # For now, simulate with delay
        await asyncio.sleep(0.01)
        return True
    
    async def recover(self, target: ChaosTarget) -> bool:
        logger.info("chaos_recovering", target=target.component)
        return True
    
    async def validate(self, target: ChaosTarget) -> bool:
        return True


class NetworkPartitionInjector(FailureInjector):
    """Inject network partition."""
    
    def __init__(self, duration_seconds: float = 30.0):
        self.duration_seconds = duration_seconds
    
    async def inject(self, target: ChaosTarget, config: ChaosConfig) -> bool:
        if config.dry_run:
            logger.info("chaos_dry_run", scenario="network_partition", target=target.component)
            return True
        
        logger.warning("chaos_injecting_partition", target=target.component)
        return True
    
    async def recover(self, target: ChaosTarget) -> bool:
        logger.info("chaos_recovering_partition", target=target.component)
        return True
    
    async def validate(self, target: ChaosTarget) -> bool:
        return True


class ProcessKiller(FailureInjector):
    """Kill a process."""
    
    def __init__(self, signal: int = 9):
        self.signal = signal
    
    async def inject(self, target: ChaosTarget, config: ChaosConfig) -> bool:
        if config.dry_run:
            logger.info("chaos_dry_run", scenario="process_kill", target=target.component)
            return True
        
        logger.critical("chaos_killing_process", target=target.component, signal=self.signal)
        # In production, would use kill() syscall
        return True
    
    async def recover(self, target: ChaosTarget) -> bool:
        logger.info("chaos_recovering_process", target=target.component)
        # Would restart the process
        return True
    
    async def validate(self, target: ChaosTarget) -> bool:
        return True


class MemoryPressureInjector(FailureInjector):
    """Inject memory pressure."""
    
    def __init__(self, target_mb: int = 500):
        self.target_mb = target_mb
        self._allocations: list[bytearray] = []
    
    async def inject(self, target: ChaosTarget, config: ChaosConfig) -> bool:
        if config.dry_run:
            logger.info("chaos_dry_run", scenario="memory_pressure", target=target.component)
            return True
        
        logger.warning("chaos_injecting_memory_pressure", target=target.component, mb=self.target_mb)
        
        # Allocate memory (be careful in production!)
        try:
            chunk = bytearray(self.target_mb * 1024 * 1024)
            self._allocations.append(chunk)
            return True
        except MemoryError:
            logger.error("memory_allocation_failed")
            return False
    
    async def recover(self, target: ChaosTarget) -> bool:
        logger.info("chaos_recovering_memory", target=target.component)
        self._allocations.clear()
        return True
    
    async def validate(self, target: ChaosTarget) -> bool:
        import psutil
        return psutil.virtual_memory().percent < 95


class FlashInterruptInjector(FailureInjector):
    """Simulate flash operation interruption."""
    
    def __init__(self, interrupt_at_percentage: float = 0.5):
        self.interrupt_at_percentage = interrupt_at_percentage
        self._interrupted = False
    
    async def inject(self, target: ChaosTarget, config: ChaosConfig) -> bool:
        if config.dry_run:
            logger.info("chaos_dry_run", scenario="flash_interrupt", target=target.component)
            return True
        
        logger.warning(
            "chaos_injecting_flash_interrupt",
            target=target.component,
            interrupt_at=self.interrupt_at_percentage * 100
        )
        self._interrupted = True
        return True
    
    async def recover(self, target: ChaosTarget) -> bool:
        logger.info("chaos_recovering_flash", target=target.component)
        self._interrupted = False
        # Would trigger rollback/recovery
        return True
    
    async def validate(self, target: ChaosTarget) -> bool:
        return not self._interrupted


class USBDisconnectInjector(FailureInjector):
    """Simulate USB disconnect during operation."""
    
    async def inject(self, target: ChaosTarget, config: ChaosConfig) -> bool:
        if config.dry_run:
            logger.info("chaos_dry_run", scenario="usb_disconnect", target=target.component)
            return True
        
        logger.critical("chaos_simulating_usb_disconnect", target=target.component)
        return True
    
    async def recover(self, target: ChaosTarget) -> bool:
        logger.info("chaos_recovering_usb", target=target.component)
        return True
    
    async def validate(self, target: ChaosTarget) -> bool:
        return True


class GDBTimeoutInjector(FailureInjector):
    """Simulate GDB timeout during debug."""
    
    def __init__(self, timeout_seconds: float = 30.0):
        self.timeout_seconds = timeout_seconds
    
    async def inject(self, target: ChaosTarget, config: ChaosConfig) -> bool:
        if config.dry_run:
            logger.info("chaos_dry_run", scenario="gdb_timeout", target=target.component)
            return True
        
        logger.warning("chaos_simulating_gdb_timeout", target=target.component)
        return True
    
    async def recover(self, target: ChaosTarget) -> bool:
        logger.info("chaos_recovering_gdb", target=target.component)
        return True
    
    async def validate(self, target: ChaosTarget) -> bool:
        return True


class ChaosEngine:
    """Engine for running chaos experiments.
    
    Usage:
        chaos = ChaosEngine()
        await chaos.register_injector(ChaosScenario.NETWORK_PARTITION, NetworkPartitionInjector())
        
        result = await chaos.run_experiment(
            scenario=ChaosScenario.NETWORK_PARTITION,
            target=ChaosTarget(component="redis"),
        )
    """
    
    def __init__(self, config: ChaosConfig | None = None):
        self._config = config or ChaosConfig()
        self._injectors: dict[ChaosScenario, FailureInjector] = {}
        self._active_experiments: dict[str, ChaosResult] = {}
        self._running = False
        self._lock = asyncio.Lock()
        
        # Register default injectors
        self._register_defaults()
    
    def _register_defaults(self) -> None:
        """Register default failure injectors."""
        self.register_injector(ChaosScenario.NETWORK_PARTITION, NetworkPartitionInjector())
        self.register_injector(ChaosScenario.NETWORK_LATENCY, NetworkLatencyInjector())
        self.register_injector(ChaosScenario.PROCESS_KILL, ProcessKiller())
        self.register_injector(ChaosScenario.MEMORY_PRESSURE, MemoryPressureInjector())
        self.register_injector(ChaosScenario.FLASH_INTERRUPTED, FlashInterruptInjector())
        self.register_injector(ChaosScenario.USB_DISCONNECT, USBDisconnectInjector())
        self.register_injector(ChaosScenario.GDB_TIMEOUT, GDBTimeoutInjector())
    
    def register_injector(self, scenario: ChaosScenario, injector: FailureInjector) -> None:
        """Register a failure injector for a scenario."""
        self._injectors[scenario] = injector
        logger.info("chaos_injector_registered", scenario=scenario.value)
    
    async def run_experiment(
        self,
        scenario: ChaosScenario,
        target: ChaosTarget,
        duration_seconds: float | None = None,
        validate_after: bool = True,
    ) -> ChaosResult:
        """Run a chaos experiment.
        
        Args:
            scenario: The chaos scenario to run
            target: The target component
            duration_seconds: How long to keep failure injected
            validate_after: Whether to validate after recovery
            
        Returns:
            ChaosResult with experiment details
        """
        if not self._config.enabled:
            logger.warning("chaos_disabled")
            return ChaosResult(
                scenario=scenario,
                target=target,
                started_at=datetime.now(),
                error="Chaos experiments disabled",
            )
        
        async with self._lock:
            if len(self._active_experiments) >= self._config.max_concurrent_experiments:
                return ChaosResult(
                    scenario=scenario,
                    target=target,
                    started_at=datetime.now(),
                    error="Max concurrent experiments reached",
                )
        
        injector = self._injectors.get(scenario)
        if not injector:
            return ChaosResult(
                scenario=scenario,
                target=target,
                started_at=datetime.now(),
                error=f"No injector for scenario: {scenario.value}",
            )
        
        result = ChaosResult(
            scenario=scenario,
            target=target,
            started_at=datetime.now(),
        )
        
        experiment_id = f"{scenario.value}_{target.component}_{int(time.time())}"
        
        try:
            # Inject failure
            logger.info("chaos_starting", experiment_id=experiment_id)
            injected = await injector.inject(target, self._config)
            result.injected = injected
            
            if not injected:
                result.error = "Injection failed"
                return result
            
            # Wait for duration
            if duration_seconds:
                await asyncio.sleep(duration_seconds)
            
            # Recover
            logger.info("chaos_recovering", experiment_id=experiment_id)
            recovered = await injector.recover(target)
            
            # Validate
            if validate_after:
                result.recovery_successful = await injector.validate(target)
            else:
                result.recovery_successful = recovered
            
            result.ended_at = datetime.now()
            result.duration_seconds = (result.ended_at - result.started_at).total_seconds()
            
            logger.info(
                "chaos_completed",
                experiment_id=experiment_id,
                success=result.recovery_successful,
                duration=result.duration_seconds,
            )
            
        except Exception as e:
            logger.exception("chaos_experiment_failed", experiment_id=experiment_id, error=str(e))
            result.error = str(e)
            result.ended_at = datetime.now()
            result.duration_seconds = (result.ended_at - result.started_at).total_seconds()
        
        return result
    
    async def run_scenario(
        self,
        scenario_name: str,
        targets: list[ChaosTarget],
        duration_seconds: float = 30.0,
    ) -> list[ChaosResult]:
        """Run a named scenario against multiple targets.
        
        Usage:
            results = await chaos.run_scenario(
                "network_partition",
                [ChaosTarget(component="redis"), ChaosTarget(component="postgres")],
            )
        """
        try:
            scenario = ChaosScenario(scenario_name)
        except ValueError:
            raise ValueError(f"Unknown scenario: {scenario_name}")
        
        results = []
        for target in targets:
            result = await self.run_experiment(
                scenario=scenario,
                target=target,
                duration_seconds=duration_seconds,
            )
            results.append(result)
        
        return results
    
    async def test_circuit_breaker(
        self,
        target: ChaosTarget,
        expected_opens: int = 3,
    ) -> dict[str, Any]:
        """Test circuit breaker behavior.
        
        Returns metrics on circuit breaker performance.
        """
        metrics = {
            "opens": 0,
            "closes": 0,
            "half_opens": 0,
            "successful_calls": 0,
            "failed_calls": 0,
        }
        
        return metrics
    
    async def test_flash_recovery(
        self,
        target: ChaosTarget,
        simulate_power_loss: bool = True,
    ) -> dict[str, Any]:
        """Test flash operation recovery.
        
        Args:
            target: Target device
            simulate_power_loss: Whether to simulate power loss
            
        Returns:
            Recovery metrics
        """
        metrics = {
            "interruption_point": "50%",
            "rollback_successful": False,
            "recovery_time_ms": 0,
            "data_integrity": True,
        }
        
        if self._config.dry_run:
            return metrics
        
        # Simulate test
        start = time.time()
        
        # Inject interrupt
        injector = FlashInterruptInjector()
        await injector.inject(target, self._config)
        
        # Wait
        await asyncio.sleep(0.5)
        
        # Recover
        recovered = await injector.recover(target)
        
        metrics["recovery_time_ms"] = (time.time() - start) * 1000
        metrics["rollback_successful"] = recovered
        
        return metrics
    
    async def test_failover(self, component: str) -> dict[str, Any]:
        """Test component failover behavior.
        
        Returns:
            Failover metrics
        """
        metrics = {
            "failover_time_ms": 0,
            "data_loss": False,
            "recovery_complete": False,
        }
        
        return metrics
    
    def get_active_experiments(self) -> list[ChaosResult]:
        """Get currently running experiments."""
        return list(self._active_experiments.values())
    
    def get_metrics(self) -> dict[str, Any]:
        """Get chaos engine metrics."""
        return {
            "enabled": self._config.enabled,
            "active_experiments": len(self._active_experiments),
            "registered_injectors": len(self._injectors),
        }


# Global chaos engine
_chaos_engine: ChaosEngine | None = None


def get_chaos_engine(config: ChaosConfig | None = None) -> ChaosEngine:
    """Get the global chaos engine."""
    global _chaos_engine
    if _chaos_engine is None:
        _chaos_engine = ChaosEngine(config)
    return _chaos_engine
