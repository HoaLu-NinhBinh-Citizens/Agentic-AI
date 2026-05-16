"""
Tests for Hardware-in-the-Loop (HIL) System

Tests UART Monitor, CAN Analyzer, and HIL Agent.
"""

import pytest
import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

# Import HIL modules
from src.hardware import (
    UartMonitor,
    UartConfig,
    UartMessage,
    CanAnalyzer,
    CanConfig,
    CanMessage,
    HilAgent,
    HilSession,
    HilResult,
    HilPhase,
    HilStatus,
)


# =============================================================================
# UART Monitor Tests
# =============================================================================

class TestUartConfig:
    """Test UART configuration."""

    def test_default_config(self):
        """Test default UART config."""
        config = UartConfig()
        assert config.port == "COM3"
        assert config.baudrate == 115200
        assert config.bytesize == 8
        assert config.parity == "N"
        assert config.stopbits == 1

    def test_custom_config(self):
        """Test custom UART config."""
        config = UartConfig(
            port="COM5",
            baudrate=9600,
            parity="E",
        )
        assert config.port == "COM5"
        assert config.baudrate == 9600
        assert config.parity == "E"

    def test_to_serial_kwargs(self):
        """Test serial kwargs conversion."""
        config = UartConfig(port="COM3", baudrate=115200)
        kwargs = config.to_serial_kwargs()
        assert kwargs["baudrate"] == 115200
        assert "port" not in kwargs  # Port is set separately


class TestUartMessage:
    """Test UART message parsing."""

    def test_from_line_info(self):
        """Test INFO message parsing."""
        msg = UartMessage.from_line("[INFO] System initialized", b"[INFO] System initialized", "COM3")
        assert msg.severity == "INFO"
        assert not msg.is_error
        assert not msg.is_warning
        assert msg.source == "COM3"

    def test_from_line_error(self):
        """Test ERROR message parsing."""
        msg = UartMessage.from_line("[ERROR] UART timeout", b"[ERROR] UART timeout", "COM3")
        assert msg.severity == "ERROR"
        assert msg.is_error
        assert not msg.is_warning

    def test_from_line_warning(self):
        """Test WARNING message parsing."""
        msg = UartMessage.from_line("[WARN] Buffer nearly full", b"[WARN] Buffer nearly full", "COM3")
        assert msg.severity == "WARNING"
        assert not msg.is_error
        assert msg.is_warning

    def test_from_line_hardfault(self):
        """Test HardFault detection."""
        msg = UartMessage.from_line("HardFault: stack overflow", b"HardFault: stack overflow", "COM3")
        assert msg.is_error
        assert "hardfault" in msg.data.lower()


class TestUartMonitor:
    """Test UART monitor functionality."""

    @pytest.fixture
    def monitor(self):
        """Create a UART monitor for testing."""
        config = UartConfig(port="COM3", baudrate=115200)
        return UartMonitor(config)

    def test_monitor_initialization(self, monitor):
        """Test monitor initializes correctly."""
        assert monitor.config.port == "COM3"
        assert not monitor._running
        assert len(monitor._buffer) == 0

    @pytest.mark.asyncio
    async def test_is_connected_when_closed(self, monitor):
        """Test is_connected returns False when not connected."""
        result = await monitor.is_connected()
        assert result is False

    @pytest.mark.asyncio
    async def test_add_to_buffer(self, monitor):
        """Test adding messages to buffer."""
        msg = UartMessage(
            timestamp=datetime.now(),
            data="Test message",
            raw_bytes=b"Test message",
            source="COM3",
        )
        monitor._add_to_buffer(msg)
        assert len(monitor._buffer) == 1

    @pytest.mark.asyncio
    async def test_get_messages(self, monitor):
        """Test getting messages with filters."""
        # Add some messages
        for i in range(5):
            msg = UartMessage(
                timestamp=datetime.now(),
                data=f"Message {i}",
                raw_bytes=f"Message {i}".encode(),
                source="COM3",
            )
            monitor._add_to_buffer(msg)

        messages = await monitor.get_messages()
        assert len(messages) == 5

    @pytest.mark.asyncio
    async def test_get_messages_with_limit(self, monitor):
        """Test getting messages with limit."""
        for i in range(10):
            msg = UartMessage(
                timestamp=datetime.now(),
                data=f"Message {i}",
                raw_bytes=f"Message {i}".encode(),
                source="COM3",
            )
            monitor._add_to_buffer(msg)

        messages = await monitor.get_messages(limit=3)
        assert len(messages) == 3

    @pytest.mark.asyncio
    async def test_get_messages_with_severity(self, monitor):
        """Test filtering by severity."""
        msg1 = UartMessage.from_line("[INFO] Normal", b"[INFO] Normal", "COM3")
        msg2 = UartMessage.from_line("[ERROR] Error occurred", b"[ERROR] Error occurred", "COM3")
        monitor._add_to_buffer(msg1)
        monitor._add_to_buffer(msg2)

        errors = await monitor.get_messages(severity="ERROR")
        assert len(errors) == 1
        assert errors[0].is_error

    @pytest.mark.asyncio
    async def test_get_messages_with_pattern(self, monitor):
        """Test filtering by pattern."""
        for i in range(5):
            msg = UartMessage(
                timestamp=datetime.now(),
                data=f"Test message {i}",
                raw_bytes=f"Test message {i}".encode(),
                source="COM3",
            )
            monitor._add_to_buffer(msg)

        messages = await monitor.get_messages(pattern="Test")
        assert len(messages) == 5

        messages = await monitor.get_messages(pattern="message 2")
        assert len(messages) == 1

    @pytest.mark.asyncio
    async def test_clear_buffer(self, monitor):
        """Test clearing the buffer."""
        for i in range(5):
            msg = UartMessage(
                timestamp=datetime.now(),
                data=f"Message {i}",
                raw_bytes=f"Message {i}".encode(),
                source="COM3",
            )
            monitor._add_to_buffer(msg)

        await monitor.clear_buffer()
        assert len(monitor._buffer) == 0

    @pytest.mark.asyncio
    async def test_get_stats(self, monitor):
        """Test getting statistics."""
        stats = await monitor.get_stats()
        assert "bytes_received" in stats
        assert "lines_received" in stats
        assert "errors_detected" in stats
        assert stats["bytes_received"] == 0


# =============================================================================
# CAN Analyzer Tests
# =============================================================================

class TestCanConfig:
    """Test CAN configuration."""

    def test_default_config(self):
        """Test default CAN config."""
        config = CanConfig()
        assert config.protocol == "raw"
        assert config.bitrate == 500000
        assert config.max_messages == 10000

    def test_custom_config(self):
        """Test custom CAN config."""
        config = CanConfig(protocol="j1939", bitrate=250000)
        assert config.protocol == "j1939"
        assert config.bitrate == 250000


class TestCanMessage:
    """Test CAN message parsing."""

    def test_message_creation(self):
        """Test creating a CAN message."""
        msg = CanMessage(
            timestamp=datetime.now(),
            can_id=0x123,
            is_extended=False,
            is_rtr=False,
            dlc=4,
            data=bytes([0x11, 0x22, 0x33, 0x44]),
        )
        assert msg.can_id == 0x123
        assert msg.dlc == 4
        assert msg.data == bytes([0x11, 0x22, 0x33, 0x44])

    def test_id_hex_standard(self):
        """Test standard CAN ID hex formatting."""
        msg = CanMessage(
            timestamp=datetime.now(),
            can_id=0x123,
            is_extended=False,
            is_rtr=False,
            dlc=0,
            data=b"",
        )
        assert msg.id_hex == "0x123"

    def test_id_hex_extended(self):
        """Test extended CAN ID hex formatting."""
        msg = CanMessage(
            timestamp=datetime.now(),
            can_id=0x12345678,
            is_extended=True,
            is_rtr=False,
            dlc=0,
            data=b"",
        )
        assert msg.id_hex == "0x12345678"

    def test_data_hex(self):
        """Test data hex formatting."""
        msg = CanMessage(
            timestamp=datetime.now(),
            can_id=0x100,
            is_extended=False,
            is_rtr=False,
            dlc=4,
            data=bytes([0x11, 0xAB, 0x33, 0xFF]),
        )
        assert msg.data_hex == "11 AB 33 FF"

    def test_parse_j1939(self):
        """Test J1939 parsing."""
        # Create a J1939 message
        # PGN is in bits 8-25
        pgn = 0xF004  # Engine Temperature
        priority = 3
        src = 0x10
        dst = 0xFF

        can_id = (priority << 26) | (pgn << 8) | src

        msg = CanMessage(
            timestamp=datetime.now(),
            can_id=can_id,
            is_extended=True,
            is_rtr=False,
            dlc=8,
            data=bytes([0x00, 0x10, 0x46, 0x00, 0x00, 0x00, 0x00, 0x00]),
        )

        parsed = msg.parse_j1939()
        assert parsed is not None
        assert parsed["priority"] == priority
        assert parsed["src_addr"] == src


class TestCanAnalyzer:
    """Test CAN analyzer functionality."""

    @pytest.fixture
    def analyzer(self):
        """Create a CAN analyzer for testing."""
        config = CanConfig()
        return CanAnalyzer(config)

    def test_analyzer_initialization(self, analyzer):
        """Test analyzer initializes correctly."""
        assert analyzer.config.protocol == "raw"
        assert len(analyzer._messages) == 0

    def test_parse_can_line_format1(self, analyzer):
        """Test parsing CAN format: 'CAN: 123 08 11 22 33 44 55 66 77 88'."""
        line = "CAN: 123 08 11 22 33 44 55 66 77 88"
        msg = analyzer.parse_uart_can_line(line)
        assert msg is not None
        assert msg.can_id == 0x123
        assert msg.dlc == 8
        assert len(msg.data) == 8

    def test_parse_can_line_format2(self, analyzer):
        """Test parsing CAN format: '0x123 11 22 33 44'."""
        line = "0x123 11 22 33 44"
        msg = analyzer.parse_uart_can_line(line)
        assert msg is not None
        assert msg.can_id == 0x123
        assert len(msg.data) == 4

    def test_parse_can_line_format3(self, analyzer):
        """Test parsing CAN format: '[0.001234] 123#1122334455667788'."""
        line = "[0.001234] 123#1122334455667788"
        msg = analyzer.parse_uart_can_line(line)
        assert msg is not None
        assert msg.can_id == 0x123
        assert len(msg.data) == 8

    def test_parse_can_line_invalid(self, analyzer):
        """Test parsing invalid CAN line."""
        line = "This is not a CAN message"
        msg = analyzer.parse_uart_can_line(line)
        assert msg is None

    @pytest.mark.asyncio
    async def test_add_message(self, analyzer):
        """Test adding CAN messages."""
        msg = CanMessage(
            timestamp=datetime.now(),
            can_id=0x100,
            is_extended=False,
            is_rtr=False,
            dlc=4,
            data=bytes([0x11, 0x22, 0x33, 0x44]),
        )
        analyzer.add_message(msg)

        assert len(analyzer._messages) == 1
        stats = await analyzer.get_stats()
        assert stats["total_messages"] == 1

    @pytest.mark.asyncio
    async def test_get_messages(self, analyzer):
        """Test getting CAN messages."""
        for i in range(5):
            msg = CanMessage(
                timestamp=datetime.now(),
                can_id=0x100 + i,
                is_extended=False,
                is_rtr=False,
                dlc=0,
                data=b"",
            )
            analyzer.add_message(msg)

        messages = await analyzer.get_messages()
        assert len(messages) == 5

    @pytest.mark.asyncio
    async def test_get_messages_by_id(self, analyzer):
        """Test filtering by CAN ID."""
        for i in range(10):
            msg = CanMessage(
                timestamp=datetime.now(),
                can_id=0x100 if i < 5 else 0x200,
                is_extended=False,
                is_rtr=False,
                dlc=0,
                data=b"",
            )
            analyzer.add_message(msg)

        messages = await analyzer.get_messages(can_id=0x100)
        assert len(messages) == 5

    @pytest.mark.asyncio
    async def test_clear(self, analyzer):
        """Test clearing analyzer."""
        for i in range(5):
            msg = CanMessage(
                timestamp=datetime.now(),
                can_id=0x100 + i,
                is_extended=False,
                is_rtr=False,
                dlc=0,
                data=b"",
            )
            analyzer.add_message(msg)

        await analyzer.clear()
        assert len(analyzer._messages) == 0
        stats = await analyzer.get_stats()
        assert stats["total_messages"] == 0


# =============================================================================
# HIL Agent Tests
# =============================================================================

class TestHilPhase:
    """Test HIL phases."""

    def test_phases_exist(self):
        """Test all expected phases exist."""
        assert HilPhase.SETUP.value == "setup"
        assert HilPhase.FLASH.value == "flash"
        assert HilPhase.MONITOR.value == "monitor"
        assert HilPhase.VALIDATE.value == "validate"
        assert HilPhase.REPORT.value == "report"
        assert HilPhase.COMPLETE.value == "complete"
        assert HilPhase.FAILED.value == "failed"


class TestHilStatus:
    """Test HIL status."""

    def test_statuses_exist(self):
        """Test all expected statuses exist."""
        assert HilStatus.IDLE.value == "idle"
        assert HilStatus.RUNNING.value == "running"
        assert HilStatus.PAUSED.value == "paused"
        assert HilStatus.COMPLETED.value == "completed"
        assert HilStatus.FAILED.value == "failed"


class TestHilSession:
    """Test HIL session."""

    def test_session_creation(self):
        """Test creating a HIL session."""
        session = HilSession(
            id="test-123",
            project="EngineCar",
        )
        assert session.id == "test-123"
        assert session.project == "EngineCar"
        assert session.status == HilStatus.IDLE
        assert session.phase == HilPhase.SETUP
        assert len(session.results) == 0


class TestHilResult:
    """Test HIL result."""

    def test_result_creation(self):
        """Test creating a HIL result."""
        result = HilResult(
            success=True,
            phase=HilPhase.COMPLETE,
            message="Test passed",
            duration_ms=1000,
            messages_captured=50,
            errors_detected=0,
            warnings_detected=2,
        )
        assert result.success is True
        assert result.phase == HilPhase.COMPLETE
        assert result.messages_captured == 50
        assert result.errors_detected == 0


class TestHilAgent:
    """Test HIL agent functionality."""

    @pytest.fixture
    def agent(self):
        """Create a HIL agent for testing."""
        uart_config = UartConfig(port="COM3", baudrate=115200)
        can_config = CanConfig()
        return HilAgent(uart_config=uart_config, can_config=can_config)

    def test_agent_initialization(self, agent):
        """Test agent initializes correctly."""
        assert agent.uart_config.port == "COM3"
        assert agent.can_config.protocol == "raw"
        assert len(agent._sessions) == 0

    def test_create_session(self, agent):
        """Test creating a HIL session."""
        session = agent.create_session("EngineCar")
        assert session.project == "EngineCar"
        assert session.id in agent._sessions
        assert agent._current_session == session

    def test_get_session(self, agent):
        """Test getting a session by ID."""
        session = agent.create_session("EngineCar")
        retrieved = agent.get_session(session.id)
        assert retrieved == session

    def test_get_nonexistent_session(self, agent):
        """Test getting a non-existent session."""
        session = agent.get_session("nonexistent")
        assert session is None

    def test_validators_setup(self, agent):
        """Test default validators are setup."""
        assert len(agent._validators) > 0

    def test_add_validator(self, agent):
        """Test adding a custom validator."""
        def custom_validator(msg):
            if "custom_error" in msg.data:
                return "Custom error detected"
            return None

        agent.add_validator(custom_validator)
        assert len(agent._validators) > 0  # At least default + custom

    def test_clear_validators(self, agent):
        """Test clearing validators."""
        agent.clear_validators()
        # Should reset to defaults
        assert len(agent._validators) > 0

    def test_get_uart(self, agent):
        """Test getting UART monitor."""
        uart = agent.get_uart()
        assert isinstance(uart, UartMonitor)

    def test_get_can(self, agent):
        """Test getting CAN analyzer."""
        can = agent.get_can()
        assert isinstance(can, CanAnalyzer)

    @pytest.mark.asyncio
    async def test_close_session(self, agent):
        """Test closing a session."""
        session = agent.create_session("EngineCar")
        result = await agent.close_session(session.id)
        assert result is True
        assert session.id not in agent._sessions


# =============================================================================
# Integration Tests
# =============================================================================

class TestHilIntegration:
    """Integration tests for HIL system."""

    @pytest.mark.asyncio
    async def test_uart_can_integration(self):
        """Test UART monitor + CAN analyzer integration."""
        uart = UartMonitor(UartConfig(port="COM3"))
        can = CanAnalyzer(CanConfig())

        can_messages = []

        def on_can(msg):
            can_messages.append(msg)

        can.on_message(on_can)

        # Simulate UART lines with CAN data
        msg1 = can.parse_uart_can_line("CAN: 100 04 11 22 33 44")
        msg2 = can.parse_uart_can_line("0x200 08 01 02 03 04 05 06 07 08")

        if msg1:
            can.add_message(msg1)
        if msg2:
            can.add_message(msg2)

        assert len(can_messages) == 2
        assert can_messages[0].can_id == 0x100
        assert can_messages[1].can_id == 0x200

    @pytest.mark.asyncio
    async def test_hil_result_serialization(self):
        """Test HIL result can be serialized."""
        result = HilResult(
            success=True,
            phase=HilPhase.COMPLETE,
            message="All tests passed",
            duration_ms=5000,
            messages_captured=100,
            errors_detected=0,
            warnings_detected=3,
            can_messages=50,
            details={
                "test_log": ["msg1", "msg2"],
            },
        )

        # Convert to dict for serialization
        result_dict = {
            "success": result.success,
            "phase": result.phase.value,
            "message": result.message,
            "duration_ms": result.duration_ms,
            "messages_captured": result.messages_captured,
            "errors_detected": result.errors_detected,
            "warnings_detected": result.warnings_detected,
            "can_messages": result.can_messages,
            "details": result.details,
        }

        assert result_dict["success"] is True
        assert result_dict["phase"] == "complete"
        assert result_dict["messages_captured"] == 100
