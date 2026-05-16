"""
Hardware-in-the-Loop (HIL) Agent

Integrates UART/CAN hardware monitoring with AI Agent for firmware testing.
Provides:
- Automated hardware test sequences
- Real-time log analysis
- Error pattern detection
- Test result reporting
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.infrastructure.hardware.uart_monitor import UartMonitor, UartConfig, UartMessage
from src.infrastructure.hardware.can_analyzer import CanAnalyzer, CanConfig, CanMessage

logger = logging.getLogger(__name__)


class HilPhase(Enum):
    """HIL test phases."""
    SETUP = "setup"
    FLASH = "flash"
    MONITOR = "monitor"
    VALIDATE = "validate"
    REPORT = "report"
    COMPLETE = "complete"
    FAILED = "failed"


class HilStatus(Enum):
    """HIL session status."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class HilResult:
    """Result of a HIL test session."""
    success: bool
    phase: HilPhase
    message: str
    duration_ms: int
    messages_captured: int = 0
    errors_detected: int = 0
    warnings_detected: int = 0
    can_messages: int = 0
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HilSession:
    """Represents a HIL test session."""
    id: str
    project: str
    status: HilStatus = HilStatus.IDLE
    phase: HilPhase = HilPhase.SETUP
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    current_test: str = ""
    results: List[HilResult] = field(default_factory=list)
    uart_logs: List[str] = field(default_factory=list)
    error_patterns: List[str] = field(default_factory=list)
    validation_rules: Dict[str, Any] = field(default_factory=dict)


class HilAgent:
    """
    Hardware-in-the-Loop Agent for automated firmware testing.

    Integrates with AI Agent to:
    - Flash firmware to target device
    - Monitor UART output in real-time
    - Parse CAN bus messages
    - Detect error patterns
    - Validate firmware behavior
    - Generate test reports

    Supports both mock mode (for testing) and real hardware mode.
    """

    def __init__(
        self,
        uart_config: Optional[UartConfig] = None,
        can_config: Optional[CanConfig] = None,
        software_root: Optional[Path] = None,
        use_mock: bool = False,
        mock_uart: bool = True,
    ):
        """
        Initialize HIL Agent.

        Args:
            uart_config: UART configuration (port, baudrate, etc.)
            can_config: CAN configuration
            software_root: Path to software directory for firmware builds
            use_mock: If True, use mock mode for all hardware (testing)
            mock_uart: If True, simulate UART input instead of real serial
        """
        self.uart_config = uart_config or UartConfig()
        self.can_config = can_config or CanConfig()
        self.software_root = software_root or Path("main/software")
        self.use_mock = use_mock
        self.mock_uart = mock_uart and use_mock

        # Mock data for testing
        self._mock_messages = [
            "[0.001] System initializing...",
            "[0.005] Clock configuration: HSE=8MHz, PLL=168MHz",
            "[0.010] GPIO initialized",
            "[0.015] UART1 configured: 115200 8N1",
            "[0.020] CAN1 initialized: 500kbps",
            "[0.025] System initialized successfully",
            "[0.030] Task scheduler started",
            "[0.100] Motor driver: ready",
            "[0.150] Sensor fusion: running",
            "[0.200] Communication: OK",
        ]
        self._mock_index = 0

        if self.mock_uart:
            self._uart = MockUartMonitor(self.uart_config)
        else:
            self._uart = UartMonitor(self.uart_config)
        self._can = CanAnalyzer(self.can_config)

        self._sessions: Dict[str, HilSession] = {}
        self._current_session: Optional[HilSession] = None

        # Validation callbacks
        self._validators: List[Callable[[UartMessage], Optional[str]]] = []

        # Setup default validators
        self._setup_default_validators()

        logger.info(
            "HilAgent initialized (mock=%s, mock_uart=%s)",
            use_mock,
            self.mock_uart
        )

    def _setup_default_validators(self) -> None:
        """Setup default error pattern validators."""

        def assert_no_hardfault(msg: UartMessage) -> Optional[str]:
            """Detect HardFault."""
            if "hardfault" in msg.data.lower() or "hard fault" in msg.data.lower():
                return f"HARD FAULT detected: {msg.data[:100]}"
            return None

        def assert_no_memmanage(msg: UartMessage) -> Optional[str]:
            """Detect MemManage fault."""
            if "memmanage" in msg.data.lower() or "mem manage" in msg.data.lower():
                return f"MemManage fault: {msg.data[:100]}"
            return None

        def assert_no_busfault(msg: UartMessage) -> Optional[str]:
            """Detect BusFault."""
            if "busfault" in msg.data.lower() or "bus fault" in msg.data.lower():
                return f"BusFault detected: {msg.data[:100]}"
            return None

        def assert_no_usagefault(msg: UartMessage) -> Optional[str]:
            """Detect UsageFault."""
            if "usagefault" in msg.data.lower() or "usage fault" in msg.data.lower():
                return f"UsageFault detected: {msg.data[:100]}"
            return None

        def assert_init_success(msg: UartMessage) -> Optional[str]:
            """Verify system initialization."""
            if "init" in msg.data.lower() and "fail" in msg.data.lower():
                return f"Initialization failure: {msg.data[:100]}"
            return None

        def assert_can_init(msg: UartMessage) -> Optional[str]:
            """Verify CAN initialization."""
            if "can" in msg.data.lower():
                if "init fail" in msg.data.lower() or "error" in msg.data.lower():
                    return f"CAN initialization failure: {msg.data[:100]}"
            return None

        self._validators = [
            assert_no_hardfault,
            assert_no_memmanage,
            assert_no_busfault,
            assert_no_usagefault,
            assert_init_success,
            assert_can_init,
        ]

    # -------------------------------------------------------------------------
    # Session Management
    # -------------------------------------------------------------------------

    def create_session(self, project: str) -> HilSession:
        """Create a new HIL test session."""
        import uuid
        session_id = str(uuid.uuid4())[:8]

        session = HilSession(
            id=session_id,
            project=project,
            status=HilStatus.IDLE,
            phase=HilPhase.SETUP,
        )

        self._sessions[session_id] = session
        self._current_session = session

        logger.info("Created HIL session %s for project %s", session_id, project)
        return session

    def get_session(self, session_id: str) -> Optional[HilSession]:
        """Get session by ID."""
        return self._sessions.get(session_id)

    def get_current_session(self) -> Optional[HilSession]:
        """Get current session."""
        return self._current_session

    async def close_session(self, session_id: str) -> bool:
        """Close and cleanup a session."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        if session.status == HilStatus.RUNNING:
            await self.stop_session(session_id)

        self._sessions.pop(session_id, None)
        if self._current_session and self._current_session.id == session_id:
            self._current_session = None

        logger.info("Closed HIL session %s", session_id)
        return True

    # -------------------------------------------------------------------------
    # Session Execution
    # -------------------------------------------------------------------------

    async def run_session(
        self,
        project: str,
        flash: bool = True,
        duration_seconds: float = 10.0,
        wait_for_pattern: Optional[str] = None,
        expected_patterns: Optional[List[str]] = None,
    ) -> HilResult:
        """
        Run a complete HIL test session.

        Args:
            project: Project name (EngineCar, RemoteControl)
            flash: Whether to flash firmware before testing
            duration_seconds: How long to monitor
            wait_for_pattern: Wait for this pattern before starting timer
            expected_patterns: List of patterns that must appear

        Returns:
            HilResult with test outcome
        """
        import time

        session = self.create_session(project)
        session.started_at = datetime.now()
        session.status = HilStatus.RUNNING

        start_time = time.time()
        errors: List[str] = []
        warnings: List[str] = []
        expected_found: Dict[str, bool] = {p: False for p in (expected_patterns or [])}

        try:
            # Phase 1: Flash (optional)
            if flash:
                session.phase = HilPhase.FLASH
                session.current_test = "Flashing firmware"
                flash_result = await self._flash_firmware(project)
                if not flash_result.success:
                    return await self._fail_session(session, "Flash failed", errors)
                await asyncio.sleep(1)  # Wait for device reset

            # Phase 2: Connect and Monitor
            session.phase = HilPhase.MONITOR
            session.current_test = "Connecting to UART"

            if not await self._uart.connect():
                return await self._fail_session(session, "UART connection failed", errors)

            # Setup message handler
            message_log: List[str] = []

            def handle_message(msg: UartMessage) -> None:
                message_log.append(msg.data)
                session.uart_logs.append(msg.data)

                # Check validators
                for validator in self._validators:
                    result = validator(msg)
                    if result:
                        errors.append(result)

                # Check expected patterns
                for pattern in expected_patterns or []:
                    if pattern.lower() in msg.data.lower():
                        expected_found[pattern] = True

            self._uart.on_message(handle_message)
            self._uart.on_error(lambda m: errors.append(f"ERROR: {m.data[:100]}"))
            self._uart.on_warning(lambda m: warnings.append(f"WARNING: {m.data[:100]}"))

            # Start monitoring
            await self._uart.start_monitoring()

            # Phase 3: Wait for initialization
            session.current_test = "Waiting for initialization"
            init_timeout = 5.0
            init_start = time.time()

            if wait_for_pattern:
                while time.time() - init_start < init_timeout:
                    if any(wait_for_pattern.lower() in log.lower() for log in message_log):
                        break
                    await asyncio.sleep(0.1)

            # Phase 4: Monitor for duration
            session.current_test = f"Monitoring for {duration_seconds}s"
            monitor_start = time.time()

            while time.time() - monitor_start < duration_seconds:
                session.current_test = f"Monitoring ({int(duration_seconds - (time.time() - monitor_start))}s remaining)"
                await asyncio.sleep(0.5)

                # Check if too many errors
                if len(errors) > 10:
                    errors.append("Too many errors detected, stopping test")
                    break

            # Phase 5: Validate
            session.phase = HilPhase.VALIDATE
            session.current_test = "Validating results"

            # Check expected patterns
            missing_patterns = [p for p, found in expected_found.items() if not found]
            if missing_patterns:
                errors.append(f"Missing expected patterns: {', '.join(missing_patterns)}")

            # Phase 6: Complete
            session.phase = HilPhase.COMPLETE
            session.status = HilStatus.COMPLETED
            session.ended_at = datetime.now()

            duration_ms = int((time.time() - start_time) * 1000)

            result = HilResult(
                success=len(errors) == 0,
                phase=HilPhase.COMPLETE,
                message="Test completed successfully" if len(errors) == 0 else f"Test failed with {len(errors)} errors",
                duration_ms=duration_ms,
                messages_captured=len(message_log),
                errors_detected=len(errors),
                warnings_detected=len(warnings),
                details={
                    "session_id": session.id,
                    "project": project,
                    "error_list": errors,
                    "warning_list": warnings,
                    "expected_patterns": expected_found,
                    "message_log": message_log[-100:],  # Last 100 messages
                },
            )

            session.results.append(result)
            logger.info("HIL session %s completed: %s", session.id, result.message)

            return result

        except Exception as exc:
            logger.exception("HIL session failed")
            return await self._fail_session(session, str(exc), errors)

        finally:
            await self._uart.stop_monitoring()
            await self._uart.disconnect()

    async def stop_session(self, session_id: str) -> bool:
        """Stop a running session."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        session.status = HilStatus.IDLE
        session.phase = HilPhase.FAILED
        session.ended_at = datetime.now()

        await self._uart.stop_monitoring()
        await self._uart.disconnect()

        logger.info("Stopped HIL session %s", session_id)
        return True

    async def _flash_firmware(self, project: str) -> HilResult:
        """Flash firmware to target device."""
        import subprocess

        session = self._current_session
        if not session:
            return HilResult(False, HilPhase.FLASH, "No active session", 0)

        flash_py = self.software_root / "flash.py"

        try:
            result = subprocess.run(
                [str(subprocess.sys.executable), str(flash_py), project, "--dry-run"],
                cwd=str(self.software_root),
                capture_output=True,
                text=True,
                timeout=60,
            )

            success = result.returncode == 0

            return HilResult(
                success=success,
                phase=HilPhase.FLASH,
                message=f"Flash {'successful' if success else 'failed'}",
                duration_ms=0,
                details={"stdout": result.stdout, "stderr": result.stderr},
            )

        except subprocess.TimeoutExpired:
            return HilResult(False, HilPhase.FLASH, "Flash timeout", 0)
        except Exception as exc:
            return HilResult(False, HilPhase.FLASH, f"Flash error: {exc}", 0)

    async def _fail_session(self, session: HilSession, message: str, errors: List[str]) -> HilResult:
        """Mark session as failed."""
        import time

        session.phase = HilPhase.FAILED
        session.status = HilStatus.FAILED
        session.ended_at = datetime.now()

        if session.started_at:
            duration_ms = int((datetime.now() - session.started_at).total_seconds() * 1000)
        else:
            duration_ms = 0

        result = HilResult(
            success=False,
            phase=HilPhase.FAILED,
            message=message,
            duration_ms=duration_ms,
            errors_detected=len(errors),
            details={"errors": errors},
        )

        session.results.append(result)
        logger.error("HIL session %s failed: %s", session.id, message)

        return result

    # -------------------------------------------------------------------------
    # Validators
    # -------------------------------------------------------------------------

    def add_validator(self, validator: Callable[[UartMessage], Optional[str]]) -> None:
        """Add a custom validation function."""
        self._validators.append(validator)

    def clear_validators(self) -> None:
        """Clear all validators."""
        self._validators.clear()
        self._setup_default_validators()

    # -------------------------------------------------------------------------
    # UART Access
    # -------------------------------------------------------------------------

    def get_uart(self) -> UartMonitor:
        """Get UART monitor instance."""
        return self._uart

    def get_can(self) -> CanAnalyzer:
        """Get CAN analyzer instance."""
        return self._can

    async def get_session_messages(self, session_id: str, limit: int = 100) -> List[str]:
        """Get messages from a session."""
        session = self._sessions.get(session_id)
        if not session:
            return []
        return session.uart_logs[-limit:]

    # -------------------------------------------------------------------------
    # Reporting
    # -------------------------------------------------------------------------

    async def generate_report(self, session_id: str) -> Dict[str, Any]:
        """Generate a test report for a session."""
        session = self._sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}

        stats = await self._uart.get_stats()
        can_stats = await self._can.get_stats()

        report = {
            "session_id": session.id,
            "project": session.project,
            "status": session.status.value,
            "duration_seconds": (
                (session.ended_at - session.started_at).total_seconds()
                if session.started_at and session.ended_at
                else 0
            ),
            "phases": {
                "setup": session.phase.value if session.phase == HilPhase.SETUP else "skipped",
                "flash": HilPhase.FLASH.value if session.phase in [HilPhase.FLASH, HilPhase.MONITOR, HilPhase.VALIDATE, HilPhase.COMPLETE] else "skipped",
                "monitor": HilPhase.MONITOR.value if session.phase in [HilPhase.MONITOR, HilPhase.VALIDATE, HilPhase.COMPLETE] else "skipped",
            },
            "uart_stats": stats,
            "can_stats": can_stats,
            "results": [
                {
                    "success": r.success,
                    "phase": r.phase.value,
                    "message": r.message,
                    "duration_ms": r.duration_ms,
                    "errors_detected": r.errors_detected,
                    "warnings_detected": r.warnings_detected,
                }
                for r in session.results
            ],
            "errors": [e for r in session.results for e in r.details.get("error_list", [])],
            "warnings": [w for r in session.results for w in r.details.get("warning_list", [])],
            "message_count": len(session.uart_logs),
            "recent_messages": session.uart_logs[-50:],
        }

        return report

    async def export_report(self, session_id: str, filepath: Path, format: str = "json") -> bool:
        """Export session report to file."""
        report = await self.generate_report(session_id)

        try:
            import json

            if format == "json":
                filepath.write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
            elif format == "txt":
                lines = ["=" * 60]
                lines.append("HIL TEST REPORT")
                lines.append("=" * 60)
                lines.append(f"Session: {report.get('session_id')}")
                lines.append(f"Project: {report.get('project')}")
                lines.append(f"Status: {report.get('status')}")
                lines.append(f"Duration: {report.get('duration_seconds', 0):.1f}s")
                lines.append(f"Messages: {report.get('message_count', 0)}")
                lines.append("")

                if report.get('errors'):
                    lines.append(f"ERRORS ({len(report['errors'])}):")
                    for e in report['errors'][:20]:
                        lines.append(f"  - {e}")
                    lines.append("")

                if report.get('warnings'):
                    lines.append(f"WARNINGS ({len(report['warnings'])}):")
                    for w in report['warnings'][:20]:
                        lines.append(f"  - {w}")
                    lines.append("")

                if report.get('recent_messages'):
                    lines.append("RECENT LOG OUTPUT:")
                    for m in report['recent_messages'][:30]:
                        lines.append(f"  {m}")

                filepath.write_text("\n".join(lines), encoding='utf-8')
            else:
                logger.error("Unknown export format: %s", format)
                return False

            logger.info("Exported HIL report to %s", filepath)
            return True

        except Exception as exc:
            logger.error("Export failed: %s", exc)
            return False


class MockUartMonitor:
    """
    Mock UART monitor for testing without real hardware.

    Simulates UART output with predefined messages or patterns.
    """

    def __init__(self, config: UartConfig):
        self.config = config
        self._running = False
        self._buffer: List[UartMessage] = []
        self._mock_index = 0

        # Default mock messages
        self._mock_messages = [
            "[0.001] System initializing...",
            "[0.005] Clock: HSE=8MHz, SYSCLK=168MHz",
            "[0.010] GPIO initialized",
            "[0.015] UART1: 115200 8N1 configured",
            "[0.020] CAN1: 500kbps initialized",
            "[0.025] System initialized successfully",
            "[0.030] Task scheduler started",
            "[0.100] Motor driver: ready",
            "[0.150] Sensor fusion: running",
            "[0.200] Communication: OK",
            "[0.250] LED blink: started",
            "[0.300] Heartbeat: 1Hz",
        ]

        # Callbacks
        self._on_message: List[Callable[[UartMessage], None]] = []
        self._on_error: List[Callable[[UartMessage], None]] = []
        self._on_warning: List[Callable[[UartMessage], None]] = []

        # Statistics
        self._stats = {
            "bytes_received": 0,
            "lines_received": 0,
            "errors_detected": 0,
            "warnings_detected": 0,
        }

    def set_mock_messages(self, messages: List[str]) -> None:
        """Set custom mock messages."""
        self._mock_messages = messages
        self._mock_index = 0

    async def connect(self) -> bool:
        """Mock connect always succeeds."""
        logger.info("Mock UART connected to %s", self.config.port)
        return True

    async def disconnect(self) -> None:
        """Mock disconnect."""
        self._running = False
        logger.info("Mock UART disconnected")

    async def is_connected(self) -> bool:
        """Always connected in mock mode."""
        return True

    async def start_monitoring(self) -> None:
        """Start mock monitoring."""
        if self._running:
            return
        self._running = True
        logger.info("Mock UART monitoring started")

    async def stop_monitoring(self) -> None:
        """Stop mock monitoring."""
        self._running = False
        logger.info("Mock UART monitoring stopped")

    async def _mock_read_loop(self) -> None:
        """Simulate reading mock messages."""
        import asyncio

        while self._running:
            if self._mock_index < len(self._mock_messages):
                msg_text = self._mock_messages[self._mock_index]
                self._mock_index += 1

                # Create message
                msg = UartMessage.from_line(
                    msg_text,
                    msg_text.encode('utf-8'),
                    f"MOCK:{self.config.port}"
                )

                # Process message
                self._process_message(msg)

            await asyncio.sleep(0.5)  # Simulate timing

    def _process_message(self, msg: UartMessage) -> None:
        """Process a mock message."""
        self._stats["lines_received"] += 1
        self._stats["bytes_received"] += len(msg.raw_bytes)

        if msg.is_error:
            self._stats["errors_detected"] += 1
            for cb in self._on_error:
                cb(msg)
        elif msg.is_warning:
            self._stats["warnings_detected"] += 1
            for cb in self._on_warning:
                cb(msg)

        for cb in self._on_message:
            cb(msg)

        self._buffer.append(msg)
        if len(self._buffer) > 10000:
            self._buffer.pop(0)

    def on_message(self, callback: Callable[[UartMessage], None]) -> None:
        """Register message callback."""
        self._on_message.append(callback)

    def on_error(self, callback: Callable[[UartMessage], None]) -> None:
        """Register error callback."""
        self._on_error.append(callback)

    def on_warning(self, callback: Callable[[UartMessage], None]) -> None:
        """Register warning callback."""
        self._on_warning.append(callback)

    async def get_messages(
        self,
        since: Optional[datetime] = None,
        severity: Optional[str] = None,
        pattern: Optional[str] = None,
        limit: int = 100,
    ) -> List[UartMessage]:
        """Get messages from buffer."""
        messages = list(self._buffer)

        if since:
            messages = [m for m in messages if m.timestamp >= since]
        if severity:
            messages = [m for m in messages if m.severity == severity.upper()]

        return messages[-limit:]

    async def get_errors(self, limit: int = 50) -> List[UartMessage]:
        """Get error messages."""
        return await self.get_messages(severity="ERROR", limit=limit)

    async def get_warnings(self, limit: int = 50) -> List[UartMessage]:
        """Get warning messages."""
        return await self.get_messages(severity="WARNING", limit=limit)

    async def get_stats(self) -> Dict[str, Any]:
        """Get monitoring statistics."""
        return dict(self._stats)

    async def clear_buffer(self) -> None:
        """Clear message buffer."""
        self._buffer.clear()

    async def export(self, filepath: Path, format: str = "txt") -> bool:
        """Export messages to file."""
        messages = await self.get_messages(limit=10000)

        try:
            if format == "json":
                import json
                data = [
                    {
                        "timestamp": m.timestamp.isoformat(),
                        "severity": m.severity,
                        "data": m.data,
                        "source": m.source,
                    }
                    for m in messages
                ]
                filepath.write_text(json.dumps(data, indent=2), encoding='utf-8')
            else:
                lines = []
                for m in messages:
                    ts = m.timestamp.strftime("%H:%M:%S.%f")[:-3]
                    lines.append(f"[{ts}] [{m.severity:7s}] {m.data}")
                filepath.write_text("\n".join(lines), encoding='utf-8')

            logger.info("Exported %d mock messages to %s", len(messages), filepath)
            return True

        except Exception as exc:
            logger.error("Export failed: %s", exc)
            return False
