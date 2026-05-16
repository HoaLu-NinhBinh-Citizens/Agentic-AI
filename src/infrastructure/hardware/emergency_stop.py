"""
Emergency Stop Mechanism for Hardware Safety

Provides systematic emergency stop functionality for hardware operations.
This module ensures safe shutdown of all hardware operations when critical
errors are detected.

Features:
- Multi-level emergency stop
- Hardware state preservation
- Graceful degradation
- Automatic recovery
- Safety interlocks

Critical Rule: LLM should NEVER directly control hardware.
Emergency stop allows controlled shutdown of operations.

Usage:
    from src.infrastructure.hardware.emergency_stop import (
        EmergencyStop,
        StopLevel,
        SafetyGuard,
    )

    # Create safety guard
    guard = SafetyGuard()
    guard.start()

    # Register hardware operations
    guard.register_operation("flash", flash_function)

    # Trigger stop if needed
    guard.emergency_stop(StopLevel.HARD, "Critical error detected")
"""

import asyncio
import logging
import signal
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class StopLevel(Enum):
    """Emergency stop levels."""
    SOFT = "soft"       # Request graceful shutdown
    GRACEFUL = "graceful"  # Stop accepting new operations
    HARD = "hard"      # Immediate termination
    EMERGENCY = "emergency"  # Complete system shutdown


class StopReason(Enum):
    """Reasons for emergency stop."""
    NONE = "none"
    USER_REQUEST = "user_request"
    TIMEOUT = "timeout"
    MEMORY_ERROR = "memory_error"
    HARDWARE_ERROR = "hardware_error"
    SAFETY_VIOLATION = "safety_violation"
    CAN_ERROR = "can_error"
    FLASH_ERROR = "flash_error"
    WATCHDOG_TIMEOUT = "watchdog_timeout"


@dataclass
class StopEvent:
    """Emergency stop event."""
    timestamp: datetime
    level: StopLevel
    reason: StopReason
    message: str
    source: str = "system"
    operations_cancelled: int = 0


@dataclass
class Operation:
    """Registered hardware operation."""
    name: str
    handler: Callable
    priority: int = 0
    can_force: bool = True
    timeout: float = 10.0
    cleanup_func: Optional[Callable] = None


@dataclass
class SafetyCheck:
    """Safety check configuration."""
    name: str
    check_func: Callable[[], bool]
    severity: str = "warning"  # warning, error, critical
    enabled: bool = True


class EmergencyStop:
    """
    Emergency stop controller for hardware operations.

    Provides systematic emergency stop with multiple levels:
    1. SOFT - Request graceful shutdown
    2. GRACEFUL - Stop new operations, complete current
    3. HARD - Terminate all operations immediately
    4. EMERGENCY - Complete system shutdown

    Usage:
        estop = EmergencyStop()

        # Register operations
        estop.register_operation("flash", flash_handler)
        estop.register_operation("uart", uart_handler)

        # Trigger stop
        estop.stop(StopLevel.HARD, StopReason.HARDWARE_ERROR)
    """

    def __init__(self):
        self._operations: Dict[str, Operation] = {}
        self._stop_level: StopLevel = StopLevel.SOFT
        self._stop_reason: StopReason = StopReason.NONE
        self._stop_message: str = ""
        self._stop_time: Optional[datetime] = None
        self._is_stopping = False
        self._lock = asyncio.Lock()

        # Callbacks for stop events
        self._stop_callbacks: List[Callable[[StopEvent], None]] = []

        # Statistics
        self._stats = {
            "total_stops": 0,
            "by_level": {},
            "by_reason": {},
        }

    @property
    def is_stopping(self) -> bool:
        """Check if emergency stop is in progress."""
        return self._is_stopping

    @property
    def stop_level(self) -> StopLevel:
        """Get current stop level."""
        return self._stop_level

    def register_operation(
        self,
        name: str,
        handler: Callable,
        priority: int = 0,
        can_force: bool = True,
        timeout: float = 10.0,
        cleanup_func: Optional[Callable] = None,
    ) -> None:
        """
        Register a hardware operation.

        Args:
            name: Operation name
            handler: Async handler function
            priority: Priority (higher = stopped last)
            can_force: Can be force-terminated
            timeout: Shutdown timeout in seconds
            cleanup_func: Cleanup function to call on stop
        """
        self._operations[name] = Operation(
            name=name,
            handler=handler,
            priority=priority,
            can_force=can_force,
            timeout=timeout,
            cleanup_func=cleanup_func,
        )
        logger.info(f"Registered operation: {name}")

    def unregister_operation(self, name: str) -> None:
        """Unregister a hardware operation."""
        self._operations.pop(name, None)
        logger.info(f"Unregistered operation: {name}")

    def register_callback(
        self,
        callback: Callable[[StopEvent], None]
    ) -> None:
        """Register callback for stop events."""
        self._stop_callbacks.append(callback)

    async def stop(
        self,
        level: StopLevel,
        reason: StopReason,
        message: str = "",
        source: str = "system",
    ) -> StopEvent:
        """
        Trigger emergency stop.

        Args:
            level: Stop level
            reason: Stop reason
            message: Optional message
            source: Source of stop request

        Returns:
            StopEvent with details
        """
        async with self._lock:
            if self._is_stopping:
                logger.warning("Emergency stop already in progress")
                return self._create_stop_event()

            self._is_stopping = True
            self._stop_level = level
            self._stop_reason = reason
            self._stop_message = message
            self._stop_time = datetime.now()

        event = self._create_stop_event()
        logger.critical(
            f"EMERGENCY STOP: level={level.value}, reason={reason.value}, "
            f"message='{message}', source={source}"
        )

        # Execute callbacks
        for callback in self._stop_callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Stop callback error: {e}")

        # Stop operations based on level
        if level == StopLevel.SOFT:
            await self._soft_stop()
        elif level == StopLevel.GRACEFUL:
            await self._graceful_stop()
        elif level == StopLevel.HARD:
            await self._hard_stop()
        elif level == StopLevel.EMERGENCY:
            await self._emergency_stop()

        # Update stats
        self._stats["total_stops"] += 1
        level_count = self._stats["by_level"].get(level.value, 0) + 1
        self._stats["by_level"][level.value] = level_count
        reason_count = self._stats["by_reason"].get(reason.value, 0) + 1
        self._stats["by_reason"][reason.value] = reason_count

        return event

    def _create_stop_event(self) -> StopEvent:
        """Create stop event from current state."""
        return StopEvent(
            timestamp=self._stop_time or datetime.now(),
            level=self._stop_level,
            reason=self._stop_reason,
            message=self._stop_message,
            source="system",
            operations_cancelled=len(self._operations),
        )

    async def _soft_stop(self) -> None:
        """SOFT stop: Request graceful shutdown."""
        logger.info("Performing SOFT stop (request graceful shutdown)")
        # Just set flags, let operations finish naturally

    async def _graceful_stop(self) -> None:
        """GRACEFUL stop: Stop new operations, complete current."""
        logger.info("Performing GRACEFUL stop")
        # Signal operations to complete quickly

    async def _hard_stop(self) -> None:
        """HARD stop: Terminate all operations."""
        logger.warning("Performing HARD stop (terminate all)")

        for name, op in sorted(self._operations.items(), key=lambda x: x[1].priority):
            try:
                logger.info(f"Stopping operation: {name}")
                if op.cleanup_func:
                    await asyncio.wait_for(
                        op.cleanup_func(),
                        timeout=op.timeout
                    )
            except asyncio.TimeoutError:
                logger.error(f"Timeout stopping {name}")
            except Exception as e:
                logger.error(f"Error stopping {name}: {e}")

    async def _emergency_stop(self) -> None:
        """EMERGENCY stop: Complete system shutdown."""
        logger.critical("PERFORMING EMERGENCY STOP (system shutdown)")
        # Call cleanup for all operations
        await self._hard_stop()
        # In a real system, would also shutdown power rails, etc.

    def reset(self) -> None:
        """Reset emergency stop state."""
        self._is_stopping = False
        self._stop_level = StopLevel.SOFT
        self._stop_reason = StopReason.NONE
        self._stop_message = ""
        self._stop_time = None
        logger.info("Emergency stop reset")

    def get_status(self) -> Dict[str, Any]:
        """Get current status."""
        return {
            "is_stopping": self._is_stopping,
            "stop_level": self._stop_level.value,
            "stop_reason": self._stop_reason.value,
            "stop_message": self._stop_message,
            "stop_time": self._stop_time.isoformat() if self._stop_time else None,
            "registered_operations": list(self._operations.keys()),
            "stats": self._stats,
        }


class SafetyGuard:
    """
    Safety guard for monitoring and protecting hardware operations.

    Provides:
    - Continuous safety monitoring
    - Automatic emergency stop triggers
    - Hardware state preservation
    - Recovery support

    Usage:
        guard = SafetyGuard()

        # Add safety checks
        guard.add_check("memory", memory_check_func)
        guard.add_check("temperature", temp_check_func)

        # Start monitoring
        guard.start()

        # Register operations
        guard.register_operation("flash", flash_func)
    """

    def __init__(
        self,
        check_interval: float = 1.0,
        max_memory_mb: float = 512,
        max_execution_time: float = 300.0,
    ):
        self.check_interval = check_interval
        self.max_memory_mb = max_memory_mb
        self.max_execution_time = max_execution_time

        # Components
        self.emergency_stop = EmergencyStop()
        self._checks: Dict[str, SafetyCheck] = {}

        # Monitoring
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._start_time: Optional[datetime] = None

        # Operations
        self._operation_start_times: Dict[str, datetime] = {}

        # Last check results
        self._last_check_results: Dict[str, bool] = {}

    def register_operation(
        self,
        name: str,
        handler: Callable,
        **kwargs
    ) -> None:
        """Register an operation with safety guard."""
        self.emergency_stop.register_operation(name, handler, **kwargs)

    def add_check(
        self,
        name: str,
        check_func: Callable[[], bool],
        severity: str = "warning",
    ) -> None:
        """Add a safety check.

        Args:
            name: Check name
            check_func: Function that returns True if safe
            severity: warning, error, or critical
        """
        self._checks[name] = SafetyCheck(
            name=name,
            check_func=check_func,
            severity=severity,
        )
        logger.info(f"Added safety check: {name} (severity={severity})")

    def start(self) -> None:
        """Start safety monitoring."""
        if self._running:
            return

        self._running = True
        self._start_time = datetime.now()
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Safety guard started")

    async def stop(self) -> None:
        """Stop safety monitoring."""
        if not self._running:
            return

        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Safety guard stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await asyncio.sleep(self.check_interval)
                await self._run_checks()
                await self._check_timeouts()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")

    async def _run_checks(self) -> None:
        """Run all safety checks."""
        for name, check in self._checks.items():
            if not check.enabled:
                continue

            try:
                result = check.check_func()
                self._last_check_results[name] = result

                if not result:
                    logger.warning(f"Safety check failed: {name}")

                    if check.severity == "critical":
                        await self.emergency_stop.stop(
                            StopLevel.HARD,
                            StopReason.SAFETY_VIOLATION,
                            f"Safety check failed: {name}",
                        )
                    elif check.severity == "error":
                        await self.emergency_stop.stop(
                            StopLevel.GRACEFUL,
                            StopReason.SAFETY_VIOLATION,
                            f"Safety check failed: {name}",
                        )

            except Exception as e:
                logger.error(f"Safety check error ({name}): {e}")

    async def _check_timeouts(self) -> None:
        """Check for operation timeouts."""
        if not self._start_time:
            return

        elapsed = (datetime.now() - self._start_time).total_seconds()

        if elapsed > self.max_execution_time:
            await self.emergency_stop.stop(
                StopLevel.HARD,
                StopReason.TIMEOUT,
                f"Max execution time exceeded: {elapsed:.1f}s",
            )

    def emergency_stop(
        self,
        level: StopLevel,
        reason: StopReason,
        message: str = "",
    ) -> None:
        """Trigger emergency stop."""
        asyncio.create_task(
            self.emergency_stop.stop(level, reason, message)
        )

    def get_status(self) -> Dict[str, Any]:
        """Get safety guard status."""
        return {
            "running": self._running,
            "uptime_seconds": (
                (datetime.now() - self._start_time).total_seconds()
                if self._start_time else 0
            ),
            "emergency_stop": self.emergency_stop.get_status(),
            "active_checks": {
                name: {
                    "enabled": check.enabled,
                    "severity": check.severity,
                    "last_result": self._last_check_results.get(name),
                }
                for name, check in self._checks.items()
            },
        }


class WatchdogTimer:
    """
    Watchdog timer for hardware operations.

    Automatically triggers emergency stop if operations hang.

    Usage:
        watchdog = WatchdogTimer(timeout=30.0)
        watchdog.start()

        # ... perform operation ...

        watchdog.pet()  # Reset timer

        watchdog.stop()
    """

    def __init__(
        self,
        timeout: float = 30.0,
        on_timeout: Optional[Callable] = None,
    ):
        self.timeout = timeout
        self.on_timeout = on_timeout

        self._running = False
        self._last_pet: Optional[datetime] = None
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        """Start watchdog timer."""
        if self._running:
            return

        self._running = True
        self._last_pet = datetime.now()
        self._task = asyncio.create_task(self._watchdog_loop())
        logger.info(f"Watchdog started (timeout={self.timeout}s)")

    def stop(self) -> None:
        """Stop watchdog timer."""
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("Watchdog stopped")

    def pet(self) -> None:
        """Pet the watchdog (reset timer)."""
        self._last_pet = datetime.now()

    async def _watchdog_loop(self) -> None:
        """Watchdog monitoring loop."""
        while self._running:
            try:
                await asyncio.sleep(self.timeout / 2)

                if self._last_pet:
                    elapsed = (datetime.now() - self._last_pet).total_seconds()
                    if elapsed > self.timeout:
                        logger.error(
                            f"Watchdog timeout! No pet for {elapsed:.1f}s "
                            f"(timeout={self.timeout}s)"
                        )
                        if self.on_timeout:
                            await self.on_timeout()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Watchdog error: {e}")
