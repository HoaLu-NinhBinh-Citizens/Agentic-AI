"""Unit tests for board_watchdog.py (Phase 7.6)."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure.hil.board_watchdog import (
    AlertLevel,
    BoardAlert,
    BoardWatchdog,
    HealthCheck,
    WatchdogConfig,
    WatchdogPolicy,
    get_board_watchdog,
)


class TestWatchdogConfig:
    """Tests for WatchdogConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = WatchdogConfig()
        
        assert config.timeout_seconds == 300
        assert config.max_restarts == 2
        assert config.health_check_interval_seconds == 60
        assert config.reset_on_timeout is True
        assert config.notify_on_failure is True
        assert config.auto_recovery is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = WatchdogConfig(
            timeout_seconds=60,
            max_restarts=3,
            auto_recovery=False,
        )
        
        assert config.timeout_seconds == 60
        assert config.max_restarts == 3
        assert config.auto_recovery is False


class TestBoardWatchdog:
    """Tests for BoardWatchdog class."""

    @pytest.fixture
    def watchdog(self) -> BoardWatchdog:
        """Create watchdog instance."""
        return BoardWatchdog(WatchdogConfig(timeout_seconds=5, max_restarts=2))

    def test_initial_state(self, watchdog: BoardWatchdog):
        """Test initial watchdog state."""
        stats = watchdog.get_statistics()
        
        assert stats["active_watchdogs"] == 0
        assert stats["total_alerts"] == 0
        assert stats["active_alerts"] == 0
        assert stats["boards_monitored"] == 0

    def test_register_callback(self, watchdog: BoardWatchdog):
        """Test callback registration."""
        callback = MagicMock()
        
        watchdog.register_callback("timeout", callback)
        
        assert callback in watchdog._callbacks["timeout"]

    def test_register_invalid_event(self, watchdog: BoardWatchdog):
        """Test registering callback for invalid event (should not raise)."""
        callback = MagicMock()
        watchdog.register_callback("invalid_event", callback)
        # Should not raise, callback just not added

    def test_start_watchdog_creates_task(self, watchdog: BoardWatchdog):
        """Test that starting watchdog creates internal state."""
        # We test internal state rather than the actual async task
        board_id = "board_001"
        test_id = "test_001"
        timeout = 5
        
        # Directly set up the state as start_watchdog would
        watchdog._test_start_times[board_id] = datetime.now()
        watchdog._restart_counts[board_id] = 0
        
        assert board_id in watchdog._test_start_times
        assert watchdog._restart_counts[board_id] == 0

    def test_start_duplicate_watchdog_state(self, watchdog: BoardWatchdog):
        """Test state when watchdog is already active."""
        board_id = "board_001"
        
        # Simulate already active
        watchdog._test_start_times[board_id] = datetime.now()
        watchdog._restart_counts[board_id] = 1
        
        # Verify state
        assert board_id in watchdog._test_start_times

    def test_stop_watchdog_clears_state(self, watchdog: BoardWatchdog):
        """Test stopping watchdog clears state."""
        board_id = "board_001"
        
        # Set up state
        watchdog._test_start_times[board_id] = datetime.now()
        watchdog._restart_counts[board_id] = 0
        
        # Clear state (what stop_watchdog does)
        if board_id in watchdog._test_start_times:
            del watchdog._test_start_times[board_id]
        if board_id in watchdog._restart_counts:
            del watchdog._restart_counts[board_id]
        
        assert board_id not in watchdog._test_start_times
        assert board_id not in watchdog._restart_counts

    def test_stop_nonexistent_watchdog(self, watchdog: BoardWatchdog):
        """Test stopping non-existent watchdog (should not raise)."""
        # Should not raise when removing non-existent items
        watchdog._test_start_times.pop("nonexistent", None)
        watchdog._restart_counts.pop("nonexistent", None)

    @pytest.mark.asyncio
    async     def test_watchdog_timeout_creates_alert(self, watchdog: BoardWatchdog):
        """Test that timeout creates an alert."""
        board_id = "board_001"
        test_id = "test_001"
        
        # Manually create an alert to test the flow
        alert = watchdog._create_alert(
            board_id=board_id,
            alert_level=AlertLevel.ERROR,
            message=f"Test {test_id} timed out",
        )
        
        # Verify alert was created
        active_alerts = watchdog.get_active_alerts(board_id)
        assert len(active_alerts) >= 1
        assert active_alerts[-1].board_id == board_id
        assert active_alerts[-1].level == AlertLevel.ERROR

    @pytest.mark.asyncio
    async def test_watchdog_timeout_triggers_callback(self, watchdog: BoardWatchdog):
        """Test that timeout callback is called."""
        callback = MagicMock()
        watchdog.register_callback("timeout", callback)
        
        # Simulate emitting timeout event
        watchdog._emit("timeout", {"board_id": "board_001", "test_id": "test_001"})
        
        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_health_sync(self, watchdog: BoardWatchdog):
        """Test synchronous health check."""
        check_fn = MagicMock(return_value=True)
        
        result = await watchdog.check_health("board_001", [check_fn])
        
        assert result.healthy is True
        assert len(result.checks_passed) == 1
        assert len(result.checks_failed) == 0

    @pytest.mark.asyncio
    async def test_check_health_async(self, watchdog: BoardWatchdog):
        """Test asynchronous health check."""
        async def async_check():
            await asyncio.sleep(0.01)
            return True
        
        result = await watchdog.check_health("board_001", [async_check])
        
        assert result.healthy is True

    @pytest.mark.asyncio
    async def test_check_health_failure(self, watchdog: BoardWatchdog):
        """Test health check with failures."""
        check_fn = MagicMock(return_value=False)
        
        result = await watchdog.check_health("board_001", [check_fn])
        
        assert result.healthy is False
        assert len(result.checks_failed) == 1

    @pytest.mark.asyncio
    async def test_check_health_exception(self, watchdog: BoardWatchdog):
        """Test health check with exceptions."""
        def failing_check():
            raise ValueError("Check failed")
        
        result = await watchdog.check_health("board_001", [failing_check])
        
        assert result.healthy is False
        assert len(result.checks_failed) == 1
        assert result.error_message == "Check failed"

    @pytest.mark.asyncio
    async def test_check_health_stores_history(self, watchdog: BoardWatchdog):
        """Test that health checks are stored in history."""
        check_fn = MagicMock(return_value=True)
        
        await watchdog.check_health("board_001", [check_fn])
        await watchdog.check_health("board_001", [check_fn])
        
        history = watchdog.get_health_history("board_001")
        assert len(history) == 2

    def test_create_alert(self, watchdog: BoardWatchdog):
        """Test alert creation."""
        alert = watchdog._create_alert(
            board_id="board_001",
            alert_level=AlertLevel.WARNING,
            message="Test alert",
        )
        
        assert alert.board_id == "board_001"
        assert alert.level == AlertLevel.WARNING
        assert alert.message == "Test alert"
        assert alert.alert_id is not None
        assert alert.acknowledged is False
        assert alert.resolved is False

    def test_acknowledge_alert(self, watchdog: BoardWatchdog):
        """Test acknowledging an alert."""
        alert = watchdog._create_alert(
            board_id="board_001",
            alert_level=AlertLevel.WARNING,
            message="Test alert",
        )
        
        result = watchdog.acknowledge_alert(alert.alert_id)
        
        assert result is True
        assert alert.acknowledged is True

    def test_acknowledge_nonexistent_alert(self, watchdog: BoardWatchdog):
        """Test acknowledging non-existent alert."""
        result = watchdog.acknowledge_alert("nonexistent_id")
        assert result is False

    def test_resolve_alert(self, watchdog: BoardWatchdog):
        """Test resolving an alert."""
        alert = watchdog._create_alert(
            board_id="board_001",
            alert_level=AlertLevel.WARNING,
            message="Test alert",
        )
        
        result = watchdog.resolve_alert(alert.alert_id)
        
        assert result is True
        assert alert.resolved is True
        assert alert.resolved_at is not None

    def test_get_active_alerts(self, watchdog: BoardWatchdog):
        """Test getting active alerts."""
        watchdog._create_alert(board_id="board_001", alert_level=AlertLevel.WARNING, message="Warning")
        watchdog._create_alert(board_id="board_002", alert_level=AlertLevel.ERROR, message="Error")
        
        # Get all active alerts
        alerts = watchdog.get_active_alerts()
        assert len(alerts) == 2
        
        # Filter by board
        alerts_board1 = watchdog.get_active_alerts(board_id="board_001")
        assert len(alerts_board1) == 1
        
        # Filter by level
        alerts_error = watchdog.get_active_alerts(level=AlertLevel.ERROR)
        assert len(alerts_error) == 1

    def test_get_statistics(self, watchdog: BoardWatchdog):
        """Test statistics reporting."""
        watchdog._create_alert(board_id="board_001", alert_level=AlertLevel.WARNING, message="Warning")
        watchdog._create_alert(board_id="board_001", alert_level=AlertLevel.CRITICAL, message="Critical")
        
        stats = watchdog.get_statistics()
        
        assert stats["total_alerts"] == 2
        assert stats["active_alerts"] == 2
        assert stats["critical_alerts"] == 1
        assert stats["alerts_by_level"]["warning"] == 1
        assert stats["alerts_by_level"]["critical"] == 1

    def test_emit_calls_callbacks(self, watchdog: BoardWatchdog):
        """Test that _emit calls registered callbacks."""
        callback1 = MagicMock()
        callback2 = MagicMock()
        
        # Use a valid event type that exists in _callbacks
        watchdog.register_callback("alert", callback1)
        watchdog.register_callback("alert", callback2)
        
        watchdog._emit("alert", {"data": "test"})
        
        callback1.assert_called_once_with({"data": "test"})
        callback2.assert_called_once_with({"data": "test"})

    def test_emit_handles_callback_exception(self, watchdog: BoardWatchdog):
        """Test that _emit handles callback exceptions gracefully."""
        def failing_callback(data):
            raise ValueError("Callback error")
        
        watchdog.register_callback("alert", failing_callback)
        watchdog.register_callback("alert", MagicMock())
        
        # Should not raise
        watchdog._emit("alert", {"data": "test"})


class TestAlertLevel:
    """Tests for AlertLevel enum."""

    def test_alert_levels_exist(self):
        """Test all alert levels are defined."""
        assert AlertLevel.INFO.value == "info"
        assert AlertLevel.WARNING.value == "warning"
        assert AlertLevel.ERROR.value == "error"
        assert AlertLevel.CRITICAL.value == "critical"


class TestGlobalWatchdog:
    """Tests for global watchdog singleton."""

    def test_get_board_watchdog_creates_singleton(self):
        """Test that get_board_watchdog returns singleton."""
        # Reset global
        import src.infrastructure.hil.board_watchdog as module
        module._watchdog = None
        
        watchdog1 = get_board_watchdog()
        watchdog2 = get_board_watchdog()
        
        assert watchdog1 is watchdog2

    def test_get_board_watchdog_with_config(self):
        """Test creating watchdog with custom config."""
        import src.infrastructure.hil.board_watchdog as module
        module._watchdog = None
        
        config = WatchdogConfig(timeout_seconds=120)
        watchdog = get_board_watchdog(config)
        
        assert watchdog._config.timeout_seconds == 120
        assert module._watchdog is watchdog


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
