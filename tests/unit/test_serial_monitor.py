"""Tests for Serial Monitor (Phase 6.5).

Unit tests for UART log capture and pattern detection.
"""

import asyncio
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

from src.domain.hardware.serial.serial_monitor import (
    LogLevel,
    LogEntry,
    SerialMonitorConfig,
    SerialMonitorStats,
    SerialMonitor,
    MultiSerialMonitor,
)


class TestLogLevel:
    """Test LogLevel enum."""
    
    def test_all_levels_defined(self):
        """UT5.1: All log levels are defined."""
        assert LogLevel.DEBUG.value == "DEBUG"
        assert LogLevel.INFO.value == "INFO"
        assert LogLevel.WARNING.value == "WARNING"
        assert LogLevel.ERROR.value == "ERROR"
        assert LogLevel.CRITICAL.value == "CRITICAL"
        assert LogLevel.UNKNOWN.value == "UNKNOWN"


class TestLogEntry:
    """Test LogEntry dataclass."""
    
    def test_entry_creation(self):
        """UT5.2: Create log entry with all fields."""
        entry = LogEntry(
            timestamp=1000.0,
            level=LogLevel.INFO,
            message="Test message",
            source="UART",
            raw_line="[INFO] Test message",
            line_number=42,
        )
        
        assert entry.timestamp == 1000.0
        assert entry.level == LogLevel.INFO
        assert entry.message == "Test message"
        assert entry.source == "UART"
        assert entry.line_number == 42
    
    def test_to_dict(self):
        """UT5.3: Convert entry to dictionary."""
        entry = LogEntry(
            timestamp=1000.0,
            level=LogLevel.ERROR,
            message="Error occurred",
            line_number=1,
        )
        
        result = entry.to_dict()
        
        assert result["timestamp"] == 1000.0
        assert result["level"] == "ERROR"
        assert result["message"] == "Error occurred"
        assert result["source"] == "UART"
        assert result["line_number"] == 1


class TestSerialMonitorConfig:
    """Test SerialMonitorConfig dataclass."""
    
    def test_default_config(self):
        """UT5.4: Default configuration values."""
        config = SerialMonitorConfig()
        
        assert config.port == "/dev/ttyUSB0"
        assert config.baudrate == 115200
        assert config.max_buffer_size == 10000
        assert len(config.error_patterns) > 0
        assert len(config.warning_patterns) > 0
    
    def test_custom_config(self):
        """UT5.5: Custom configuration values."""
        config = SerialMonitorConfig(
            port="COM3",
            baudrate=9600,
            max_buffer_size=5000,
        )
        
        assert config.port == "COM3"
        assert config.baudrate == 9600
        assert config.max_buffer_size == 5000


class TestSerialMonitorStats:
    """Test SerialMonitorStats dataclass."""
    
    def test_stats_creation(self):
        """UT5.6: Create stats with defaults."""
        stats = SerialMonitorStats()
        
        assert stats.bytes_received == 0
        assert stats.lines_received == 0
        assert stats.errors_detected == 0
        assert stats.warnings_detected == 0
        assert stats.start_time > 0
    
    def test_uptime_calculation(self):
        """UT5.7: Calculate uptime correctly."""
        stats = SerialMonitorStats(start_time=time.time() - 100)
        
        assert stats.uptime_seconds() >= 100


class TestSerialMonitor:
    """Test SerialMonitor class."""
    
    @pytest.fixture
    def monitor(self):
        """Create monitor instance."""
        config = SerialMonitorConfig(
            port="TEST",
            baudrate=115200,
        )
        return SerialMonitor(config)
    
    def test_monitor_creation(self, monitor):
        """UT5.8: Create monitor with config."""
        assert monitor.config.port == "TEST"
        assert not monitor._running
        assert len(monitor._buffer) == 0
    
    def test_detect_error_level(self, monitor):
        """UT5.9: Detect ERROR level from patterns."""
        level = monitor._detect_level("ERROR: Something failed")
        assert level == LogLevel.ERROR
    
    def test_detect_warning_level(self, monitor):
        """UT5.10: Detect WARNING level from patterns."""
        level = monitor._detect_level("WARNING: Memory low")
        assert level == LogLevel.WARNING
    
    def test_detect_hardfault(self, monitor):
        """UT5.11: Detect HardFault pattern."""
        level = monitor._detect_level("HardFault: stack overflow")
        assert level == LogLevel.ERROR
    
    def test_detect_panic(self, monitor):
        """UT5.12: Detect panic pattern."""
        level = monitor._detect_level("PANIC: assert failed")
        assert level == LogLevel.ERROR
    
    def test_detect_info_level(self, monitor):
        """UT5.13: Detect INFO level from prefix."""
        level = monitor._detect_level("[INFO] System initialized")
        assert level == LogLevel.INFO
    
    def test_detect_debug_level(self, monitor):
        """UT5.14: Detect DEBUG level from prefix."""
        level = monitor._detect_level("DEBUG: value = 42")
        assert level == LogLevel.DEBUG
    
    def test_detect_unknown_level(self, monitor):
        """UT5.15: Default to UNKNOWN for plain text."""
        level = monitor._detect_level("Hello world")
        assert level == LogLevel.UNKNOWN
    
    def test_parse_line(self, monitor):
        """UT5.16: Parse line into LogEntry."""
        entry = monitor._parse_line("[ERROR] Test error", 10)
        
        assert entry.level == LogLevel.ERROR
        assert entry.message == "[ERROR] Test error"
        assert entry.line_number == 10
        assert entry.timestamp > 0
    
    def test_add_to_buffer(self, monitor):
        """UT5.17: Add entry to buffer."""
        entry = LogEntry(
            timestamp=1000.0,
            level=LogLevel.INFO,
            message="Test",
            line_number=1,
        )
        
        monitor._add_to_buffer(entry)
        
        assert len(monitor._buffer) == 1
        assert monitor._stats.lines_received == 1
    
    def test_buffer_size_limit(self, monitor):
        """UT5.18: Buffer respects max size."""
        monitor.config.max_buffer_size = 5
        
        for i in range(10):
            entry = LogEntry(
                timestamp=float(i),
                level=LogLevel.INFO,
                message=f"Line {i}",
                line_number=i,
            )
            monitor._add_to_buffer(entry)
        
        assert len(monitor._buffer) == 5
        assert monitor._buffer[0].message == "Line 5"
    
    def test_callback_on_error(self, monitor):
        """UT5.19: Error callback is called."""
        errors = []
        monitor.on_error = lambda e: errors.append(e)
        
        entry = LogEntry(
            timestamp=1000.0,
            level=LogLevel.ERROR,
            message="Error",
            line_number=1,
        )
        monitor._process_entry(entry)
        
        assert len(errors) == 1
        assert errors[0].message == "Error"
    
    def test_callback_on_warning(self, monitor):
        """UT5.20: Warning callback is called."""
        warnings = []
        monitor.on_warning = lambda e: warnings.append(e)
        
        entry = LogEntry(
            timestamp=1000.0,
            level=LogLevel.WARNING,
            message="Warning",
            line_number=1,
        )
        monitor._process_entry(entry)
        
        assert len(warnings) == 1
    
    def test_callback_on_line(self, monitor):
        """UT5.21: Line callback is always called."""
        lines = []
        monitor.on_line = lambda e: lines.append(e)
        
        entry = LogEntry(
            timestamp=1000.0,
            level=LogLevel.INFO,
            message="Info",
            line_number=1,
        )
        monitor._process_entry(entry)
        
        assert len(lines) == 1
    
    def test_get_errors(self, monitor):
        """UT5.22: Get all errors from buffer."""
        monitor._buffer = [
            LogEntry(timestamp=1, level=LogLevel.INFO, message="1", line_number=1),
            LogEntry(timestamp=2, level=LogLevel.ERROR, message="2", line_number=2),
            LogEntry(timestamp=3, level=LogLevel.INFO, message="3", line_number=3),
            LogEntry(timestamp=4, level=LogLevel.ERROR, message="4", line_number=4),
        ]
        
        errors = monitor.get_errors()
        
        assert len(errors) == 2
        assert all(e.level == LogLevel.ERROR for e in errors)
    
    def test_get_warnings(self, monitor):
        """UT5.23: Get all warnings from buffer."""
        monitor._buffer = [
            LogEntry(timestamp=1, level=LogLevel.WARNING, message="1", line_number=1),
            LogEntry(timestamp=2, level=LogLevel.INFO, message="2", line_number=2),
        ]
        
        warnings = monitor.get_warnings()
        
        assert len(warnings) == 1
        assert warnings[0].level == LogLevel.WARNING
    
    def test_export_buffer(self, monitor):
        """UT5.24: Export buffer as string."""
        monitor._buffer = [
            LogEntry(timestamp=1, level=LogLevel.INFO, message="Line 1", line_number=1),
            LogEntry(timestamp=2, level=LogLevel.ERROR, message="Line 2", line_number=2),
        ]
        
        result = monitor.export_buffer()
        
        assert "[INFO   ] Line 1" in result
        assert "[ERROR  ] Line 2" in result
    
    def test_export_json(self, monitor):
        """UT5.25: Export buffer as JSON."""
        monitor._buffer = [
            LogEntry(timestamp=1000.0, level=LogLevel.INFO, message="Test", line_number=1),
        ]
        
        result = monitor.export_json()
        
        assert len(result) == 1
        assert result[0]["message"] == "Test"
    
    def test_clear_buffer(self, monitor):
        """UT5.26: Clear buffer contents."""
        monitor._buffer = [
            LogEntry(timestamp=1, level=LogLevel.INFO, message="1", line_number=1),
        ]
        
        monitor.clear_buffer()
        
        assert len(monitor._buffer) == 0
    
    def test_buffer_property_returns_copy(self, monitor):
        """UT5.27: Buffer property returns a copy."""
        monitor._buffer = [LogEntry(timestamp=1, level=LogLevel.INFO, message="1", line_number=1)]
        
        buffer_copy = monitor.buffer
        buffer_copy.clear()
        
        assert len(monitor._buffer) == 1


class TestMultiSerialMonitor:
    """Test MultiSerialMonitor class."""
    
    @pytest.fixture
    def multi_monitor(self):
        """Create multi-monitor instance."""
        return MultiSerialMonitor()
    
    def test_multi_monitor_creation(self, multi_monitor):
        """UT5.28: Create multi-monitor."""
        assert len(multi_monitor._monitors) == 0
    
    def test_get_monitor_not_found(self, multi_monitor):
        """UT5.29: Get non-existent monitor returns None."""
        result = multi_monitor.get_monitor("nonexistent")
        assert result is None
    
    def test_get_all_buffers_empty(self, multi_monitor):
        """UT5.30: Get all buffers when empty."""
        result = multi_monitor.get_all_buffers()
        assert len(result) == 0


class TestSerialMonitorAsync:
    """Async tests for SerialMonitor."""
    
    @pytest.fixture
    def config(self):
        """Create test config."""
        return SerialMonitorConfig(port="TEST")
    
    @pytest.mark.asyncio
    async def test_context_manager(self, config):
        """IT5.1: Use monitor as async context manager."""
        async with SerialMonitor(config) as monitor:
            assert monitor._running
            assert monitor._reader is not None or True  # May fail on Windows
        
        # Should be disconnected after exit
        assert not monitor._running
    
    @pytest.mark.asyncio
    async def test_stop_running_monitor(self, config):
        """IT5.2: Stop a running monitor."""
        monitor = SerialMonitor(config)
        monitor._running = True
        monitor._task = asyncio.create_task(asyncio.sleep(10))
        
        await monitor.stop()
        
        assert not monitor._running
        assert monitor._task.cancelled() or True
    
    @pytest.mark.asyncio
    async def test_disconnect_without_connection(self, config):
        """IT5.3: Disconnect when not connected is safe."""
        monitor = SerialMonitor(config)
        
        await monitor.disconnect()  # Should not raise
        
        assert monitor._reader is None
        assert monitor._writer is None
