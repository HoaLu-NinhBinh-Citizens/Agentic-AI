"""Board watchdog and health monitoring (Phase 7.6).

Monitors board health and automatically recovers stuck boards:
- Watchdog timer for stuck tests
- Health check scheduling
- Automatic reset/recovery
- Alerting on failures
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class HealthCheck:
    """Health check result."""
    board_id: str
    timestamp: datetime
    healthy: bool
    response_time_ms: float = 0.0
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)
    error_message: str = ""


@dataclass
class BoardAlert:
    """Alert for board issues."""
    alert_id: str
    board_id: str
    level: AlertLevel
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False
    resolved: bool = False
    resolved_at: datetime | None = None


class WatchdogPolicy(Enum):
    """Watchdog recovery policies."""
    RESTART_TEST = "restart_test"      # Restart the test
    RESET_BOARD = "reset_board"        # Reset the board
    RELEASE_BOARD = "release_board"     # Release board back to pool
    ESCALATE = "escalate"            # Escalate to human


@dataclass
class WatchdogConfig:
    """Watchdog configuration."""
    timeout_seconds: int = 300  # 5 minutes
    max_restarts: int = 2
    health_check_interval_seconds: int = 60
    reset_on_timeout: bool = True
    notify_on_failure: bool = True
    auto_recovery: bool = True


class BoardWatchdog:
    """Watchdog for monitoring and recovering stuck boards.
    
    Phase 7.6: Board watchdog & health
    """
    
    def __init__(self, config: WatchdogConfig | None = None) -> None:
        self._config = config or WatchdogConfig()
        self._active_watchdogs: dict[str, asyncio.Task] = {}
        self._test_start_times: dict[str, datetime] = {}
        self._restart_counts: dict[str, int] = {}
        self._health_checks: dict[str, list[HealthCheck]] = {}
        self._alerts: list[BoardAlert] = []
        self._callbacks: dict[str, list[Callable]] = {
            "timeout": [],
            "health_check": [],
            "alert": [],
            "recovery": [],
        }
    
    def register_callback(
        self,
        event: str,
        callback: Callable,
    ) -> None:
        """Register callback for events."""
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    def _emit(self, event: str, data: Any) -> None:
        """Emit event to callbacks."""
        for callback in self._callbacks.get(event, []):
            try:
                callback(data)
            except Exception as e:
                logger.error(f"Callback error: event={event}, error={e}")
    
    def start_watchdog(
        self,
        board_id: str,
        test_id: str,
        timeout_seconds: int | None = None,
    ) -> None:
        """Start watchdog for a test on a board."""
        if board_id in self._active_watchdogs:
            logger.warning("Watchdog already active", board_id=board_id)
            return
        
        self._test_start_times[board_id] = datetime.now()
        self._restart_counts[board_id] = 0
        
        timeout = timeout_seconds or self._config.timeout_seconds
        coro = self._watchdog_loop(board_id, test_id, timeout)
        task = asyncio.create_task(coro)
        self._active_watchdogs[board_id] = task
        
        logger.info("Watchdog started", board_id=board_id, test_id=test_id, timeout=timeout)
    
    def stop_watchdog(self, board_id: str) -> None:
        """Stop watchdog for a board."""
        if board_id in self._active_watchdogs:
            self._active_watchdogs[board_id].cancel()
            del self._active_watchdogs[board_id]
            
            if board_id in self._test_start_times:
                del self._test_start_times[board_id]
            
            logger.info("Watchdog stopped", board_id=board_id)
    
    async def _watchdog_loop(
        self,
        board_id: str,
        test_id: str,
        timeout_seconds: int,
    ) -> None:
        """Watchdog monitoring loop."""
        start_time = self._test_start_times.get(board_id, datetime.now())
        timeout = timedelta(seconds=timeout_seconds)
        
        while True:
            elapsed = datetime.now() - start_time
            
            if elapsed > timeout:
                logger.warning("Watchdog timeout", board_id=board_id, test_id=test_id, elapsed=elapsed)
                
                # Create alert
                alert = self._create_alert(
                    board_id=board_id,
                    level=AlertLevel.ERROR,
                    message=f"Test {test_id} timed out after {elapsed}",
                )
                
                self._emit("timeout", {
                    "board_id": board_id,
                    "test_id": test_id,
                    "elapsed": elapsed,
                    "alert": alert,
                })
                
                # Handle recovery
                await self._handle_timeout(board_id, test_id)
                return
            
            # Wait before next check
            await asyncio.sleep(10)
    
    async def _handle_timeout(
        self,
        board_id: str,
        test_id: str,
    ) -> None:
        """Handle watchdog timeout."""
        restart_count = self._restart_counts.get(board_id, 0)
        
        if restart_count < self._config.max_restarts and self._config.auto_recovery:
            # Try to restart the test
            restart_count += 1
            self._restart_counts[board_id] = restart_count
            
            logger.info("Attempting recovery", board_id=board_id, attempt=restart_count)
            
            self._emit("recovery", {
                "board_id": board_id,
                "test_id": test_id,
                "action": "restart",
                "attempt": restart_count,
            })
            
            # Reset watchdog timer
            self._test_start_times[board_id] = datetime.now()
        else:
            # Max restarts reached or auto recovery disabled
            if self._config.notify_on_failure:
                self._create_alert(
                    board_id=board_id,
                    level=AlertLevel.CRITICAL,
                    message=f"Test {test_id} failed after {self._config.max_restarts} recovery attempts",
                )
            
            self._emit("recovery", {
                "board_id": board_id,
                "test_id": test_id,
                "action": "escalate",
            })
    
    async def check_health(
        self,
        board_id: str,
        check_functions: list[Callable[[], bool]],
    ) -> HealthCheck:
        """Perform health check on a board."""
        start = datetime.now()
        checks_passed = []
        checks_failed = []
        error_message = ""
        
        for i, check_fn in enumerate(check_functions):
            try:
                if asyncio.iscoroutinefunction(check_fn):
                    result = await check_fn()
                else:
                    result = check_fn()
                
                if result:
                    checks_passed.append(f"check_{i}")
                else:
                    checks_failed.append(f"check_{i}")
            except Exception as e:
                checks_failed.append(f"check_{i}")
                error_message = str(e)
        
        response_time = (datetime.now() - start).total_seconds() * 1000
        healthy = len(checks_failed) == 0
        
        check = HealthCheck(
            board_id=board_id,
            timestamp=datetime.now(),
            healthy=healthy,
            response_time_ms=response_time,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            error_message=error_message,
        )
        
        # Store check
        if board_id not in self._health_checks:
            self._health_checks[board_id] = []
        self._health_checks[board_id].append(check)
        
        # Keep only last 100 checks
        if len(self._health_checks[board_id]) > 100:
            self._health_checks[board_id] = self._health_checks[board_id][-100:]
        
        self._emit("health_check", check)
        
        return check
    
    def _create_alert(
        self,
        board_id: str,
        level: AlertLevel,
        message: str,
    ) -> BoardAlert:
        """Create a new alert."""
        import uuid
        alert = BoardAlert(
            alert_id=str(uuid.uuid4())[:8],
            board_id=board_id,
            level=level,
            message=message,
        )
        self._alerts.append(alert)
        
        self._emit("alert", alert)
        log_level = logging.WARNING if level == AlertLevel.WARNING else logging.ERROR
        logger.log(
            log_level,
            f"Alert created: alert_id={alert.alert_id}, board_id={board_id}, level={level.value}"
        )
        
        return alert
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                return True
        return False
    
    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an alert."""
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.resolved = True
                alert.resolved_at = datetime.now()
                return True
        return False
    
    def get_active_alerts(
        self,
        board_id: str | None = None,
        level: AlertLevel | None = None,
    ) -> list[BoardAlert]:
        """Get active (unresolved) alerts."""
        alerts = [a for a in self._alerts if not a.resolved]
        
        if board_id:
            alerts = [a for a in alerts if a.board_id == board_id]
        
        if level:
            alerts = [a for a in alerts if a.level == level]
        
        return alerts
    
    def get_health_history(
        self,
        board_id: str,
        limit: int = 100,
    ) -> list[HealthCheck]:
        """Get health check history for a board."""
        return self._health_checks.get(board_id, [])[-limit:]
    
    def get_statistics(self) -> dict[str, Any]:
        """Get watchdog statistics."""
        return {
            "active_watchdogs": len(self._active_watchdogs),
            "total_alerts": len(self._alerts),
            "active_alerts": len([a for a in self._alerts if not a.resolved]),
            "critical_alerts": len([a for a in self._alerts if a.level == AlertLevel.CRITICAL and not a.resolved]),
            "alerts_by_level": {
                level.value: len([a for a in self._alerts if a.level == level])
                for level in AlertLevel
            },
            "boards_monitored": len(self._health_checks),
        }


# Global singleton
_watchdog: BoardWatchdog | None = None


def get_board_watchdog(config: WatchdogConfig | None = None) -> BoardWatchdog:
    """Get global board watchdog."""
    global _watchdog
    if _watchdog is None:
        _watchdog = BoardWatchdog(config)
    return _watchdog


if __name__ == "__main__":
    async def main():
        watchdog = get_board_watchdog(WatchdogConfig(
            timeout_seconds=30,
            max_restarts=2,
            auto_recovery=True,
        ))
        
        # Register callbacks
        def on_timeout(data):
            print(f"⏰ TIMEOUT: {data}")
        
        def on_alert(alert):
            print(f"🚨 ALERT [{alert.level.value}]: {alert.message}")
        
        def on_recovery(data):
            print(f"🔧 RECOVERY: {data['action']} for {data['board_id']}")
        
        watchdog.register_callback("timeout", on_timeout)
        watchdog.register_callback("alert", on_alert)
        watchdog.register_callback("recovery", on_recovery)
        
        # Simulate watchdog
        print("Starting watchdog...")
        watchdog.start_watchdog("board_001", "test_001", timeout_seconds=5)
        
        # Simulate health check
        def check_board():
            return True
        
        result = await watchdog.check_health("board_001", [check_board, check_board])
        print(f"\nHealth check: {'✓ Healthy' if result.healthy else '✗ Unhealthy'}")
        print(f"  Response time: {result.response_time_ms:.2f}ms")
        print(f"  Checks passed: {result.checks_passed}")
        print(f"  Checks failed: {result.checks_failed}")
        
        # Wait for timeout (or cancel)
        await asyncio.sleep(6)
        
        watchdog.stop_watchdog("board_001")
        
        # Statistics
        stats = watchdog.get_statistics()
        print(f"\nStatistics: {stats}")
    
    asyncio.run(main())
