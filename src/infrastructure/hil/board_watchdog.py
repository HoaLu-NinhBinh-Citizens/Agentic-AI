"""Board watchdog and health monitoring (Phase 7.6).

Monitors board health and automatically recovers stuck boards:
- Watchdog timer for stuck tests
- Health check scheduling
- Automatic reset/recovery
- Alerting on failures

Metrics exposed:
- hil_watchdog_timeouts_total: Total watchdog timeouts
- hil_watchdog_recoveries_total: Total recovery attempts
- hil_alerts_created_total: Total alerts created
- hil_active_watchdogs: Current active watchdogs gauge
- hil_health_check_duration_seconds: Health check latency histogram
- hil_health_check_result: Health check result (1=healthy, 0=unhealthy)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable

from src.infrastructure.observability.metrics import MetricsRegistry
from src.infrastructure.observability.structured_logging import get_logger

logger = get_logger(__name__)

# Prometheus metrics constants
_METRICS = MetricsRegistry.get_instance()
_METRICS.set_histogram_buckets("hil_health_check_duration_seconds", [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0])

# Alert retention limits
_MAX_ALERTS = 1000
_MAX_RESOLVED_ALERTS_TO_KEEP = 500


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
    RESTART_TEST = "restart_test"
    RESET_BOARD = "reset_board"
    RELEASE_BOARD = "release_board"
    ESCALATE = "escalate"


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
    
    def _record_metric_counter(self, name: str, tags: dict[str, str] | None = None, value: int = 1) -> None:
        """Record a counter metric, handling sync/async context gracefully."""
        try:
            # Try to get running event loop
            loop = asyncio.get_running_loop()
            # If we're in an async context, schedule the metric update
            loop.call_soon_threadsafe(
                lambda: asyncio.create_task(_METRICS.inc_counter(name, tags, value))
            )
        except RuntimeError:
            # No running event loop - metric recording will be skipped
            # In production, this should use a background thread or queue
            pass

    def _emit(self, event: str, data: Any) -> None:
        """Emit event to callbacks."""
        for callback in self._callbacks.get(event, []):
            try:
                callback(data)
            except Exception as e:
                logger.error("callback_error", event=event, error=str(e))
    
    def start_watchdog(
        self,
        board_id: str,
        test_id: str,
        timeout_seconds: int | None = None,
    ) -> None:
        """Start watchdog for a test on a board."""
        if board_id in self._active_watchdogs:
            logger.warning("watchdog_already_active", board_id=board_id)
            return
        
        self._test_start_times[board_id] = datetime.now()
        self._restart_counts[board_id] = 0
        
        timeout = timeout_seconds or self._config.timeout_seconds
        coro = self._watchdog_loop(board_id, test_id, timeout)
        task = asyncio.create_task(coro)
        self._active_watchdogs[board_id] = task
        
        logger.info(
            "watchdog_started",
            board_id=board_id,
            test_id=test_id,
            timeout_seconds=timeout
        )
    
    def stop_watchdog(self, board_id: str) -> None:
        """Stop watchdog for a board."""
        if board_id in self._active_watchdogs:
            task = self._active_watchdogs[board_id]
            task.cancel()
            
            # Remove from tracking immediately to prevent duplicate starts
            del self._active_watchdogs[board_id]
            
            if board_id in self._test_start_times:
                del self._test_start_times[board_id]
            
            logger.info("watchdog_stopped", board_id=board_id)
    
    async def _watchdog_loop(
        self,
        board_id: str,
        test_id: str,
        timeout_seconds: int,
    ) -> None:
        """Watchdog monitoring loop."""
        start_time = self._test_start_times.get(board_id, datetime.now())
        timeout = timedelta(seconds=timeout_seconds)
        
        try:
            while True:
                elapsed = datetime.now() - start_time
                
                if elapsed > timeout:
                    logger.warning(
                        "watchdog_timeout",
                        board_id=board_id,
                        test_id=test_id,
                        elapsed_seconds=elapsed.total_seconds()
                    )
                    
                    # Update metrics
                    await _METRICS.inc_counter(
                        "hil_watchdog_timeouts_total",
                        tags={"board_id": board_id, "action": "timeout"}
                    )
                    
                    # Create alert
                    alert = self._create_alert(
                        board_id=board_id,
                        alert_level=AlertLevel.ERROR,
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
        except asyncio.CancelledError:
            logger.info("watchdog_cancelled", board_id=board_id, test_id=test_id)
            raise
        finally:
            # Ensure cleanup of active watchdog tracking
            if board_id in self._active_watchdogs:
                del self._active_watchdogs[board_id]
    
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
            
            logger.info(
                "recovery_attempt",
                board_id=board_id,
                test_id=test_id,
                attempt=restart_count
            )
            
            # Update metrics
            await _METRICS.inc_counter(
                "hil_watchdog_recoveries_total",
                tags={"board_id": board_id, "action": "restart"}
            )
            
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
                    alert_level=AlertLevel.CRITICAL,
                    message=f"Test {test_id} failed after {self._config.max_restarts} recovery attempts",
                )
            
            # Update metrics
            await _METRICS.inc_counter(
                "hil_watchdog_recoveries_total",
                tags={"board_id": board_id, "action": "escalate"}
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
        response_time_sec = (datetime.now() - start).total_seconds()
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
        
        # Record metrics
        await _METRICS.observe_histogram(
            "hil_health_check_duration_seconds",
            value=response_time_sec,
            tags={"board_id": board_id}
        )
        await _METRICS.inc_counter(
            "hil_health_check_result",
            tags={"board_id": board_id, "healthy": str(healthy).lower()}
        )
        
        self._emit("health_check", check)
        
        return check
    
    def _create_alert(
        self,
        board_id: str,
        alert_level: AlertLevel,
        message: str,
    ) -> BoardAlert:
        """Create a new alert."""
        import uuid
        alert = BoardAlert(
            alert_id=str(uuid.uuid4())[:8],
            board_id=board_id,
            level=alert_level,
            message=message,
        )
        self._alerts.append(alert)
        
        # Prune old alerts to prevent memory leak
        self._prune_alerts()
        
        # Update metrics (handles sync/async context)
        self._record_metric_counter(
            "hil_alerts_created_total",
            tags={"level": alert_level.value, "board_id": board_id}
        )
        
        self._emit("alert", alert)
        
        if alert_level == AlertLevel.WARNING:
            logger.warning("alert_created",
                alert_id=alert.alert_id,
                board_id=board_id,
                alert_level=alert_level.value
            )
        else:
            logger.error("alert_created",
                alert_id=alert.alert_id,
                board_id=board_id,
                alert_level=alert_level.value
            )
        
        return alert
    
    def _prune_alerts(self) -> None:
        """Prune old alerts to prevent memory leak."""
        if len(self._alerts) <= _MAX_ALERTS:
            return
        
        # Keep all unresolved alerts and most recent resolved alerts
        unresolved = [a for a in self._alerts if not a.resolved]
        resolved = [a for a in self._alerts if a.resolved][-_MAX_RESOLVED_ALERTS_TO_KEEP:]
        self._alerts = unresolved + resolved
    
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
            print(f"TIMEOUT: {data}")
        
        def on_alert(alert):
            print(f"ALERT [{alert.level.value}]: {alert.message}")
        
        def on_recovery(data):
            print(f"RECOVERY: {data['action']} for {data['board_id']}")
        
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
        print(f"\nHealth check: {'Healthy' if result.healthy else 'Unhealthy'}")
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
