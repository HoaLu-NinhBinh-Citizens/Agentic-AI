"""
⚠️  EXPERIMENTAL MODULE

Autonomous Development Loop - AI Self-Directed Firmware Development

The core engine that enables AI to:
1. Generate code autonomously
2. Build firmware
3. Flash to real hardware
4. Read serial output
5. Analyze errors
6. Fix and retry

This is the "AI-First Development" loop where AI is the primary developer.

⚠️  WARNING: This module is EXPERIMENTAL and NOT tested on real hardware.
    Do NOT use for production firmware development without validation.

Usage:
    loop = AutonomousLoop(agent)
    result = await loop.run("Implement LED blink on PC13")
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any

from src.core.tools.serial_reader import SerialReader, SerialConfig, ReadResult, ReadStatus, CrashLog
from src.core.tools.hardware_reset import HardwareReset, ResetResult, ResetStatus

logger = logging.getLogger(__name__)


class LoopState(Enum):
    """State of the autonomous loop."""
    IDLE = "idle"
    GENERATING = "generating"
    BUILDING = "building"
    FLASHING = "flashing"
    READING = "reading"
    ANALYZING = "analyzing"
    FIXING = "fixing"
    SUCCESS = "success"
    FAILED = "failed"
    MAX_RETRIES = "max_retries"
    PAUSED = "paused"


class ErrorSeverity(Enum):
    """Severity of detected errors."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class LoopConfig:
    """Configuration for autonomous loop."""
    max_retries: int = 5
    build_timeout: int = 180
    flash_timeout: int = 120
    read_timeout: int = 10
    read_duration: float = 3.0
    serial_port: str = "auto"
    serial_baudrate: int = 115200
    auto_reset_on_crash: bool = True
    pause_on_max_retries: bool = True
    verbose: bool = True
    # Circuit Breaker: Flash protection
    max_flash_per_error: int = 3
    max_total_flashes: int = 10
    alert_on_exceed: bool = True
    alert_callback: Optional[Callable[[str, str], None]] = None
    # Physical Reset: Hardware watchdog
    enable_hardware_reset: bool = False
    hardware_reset_timeout: float = 30.0
    hardware_reset_debugger: str = "jlink"
    hardware_reset_device: str = "STM32F407VG"


@dataclass
class LoopStep:
    """One step in the autonomous loop."""
    step: str
    state: LoopState
    start_time: float = 0
    duration: float = 0
    success: bool = False
    message: str = ""
    data: Optional[Dict] = None


@dataclass
class ErrorInfo:
    """Information about an detected error."""
    severity: ErrorSeverity
    pattern: str
    message: str
    source: str = ""
    line_hint: Optional[int] = None


@dataclass
class ErrorFingerprint:
    """Unique fingerprint for an error pattern (for circuit breaker tracking)."""
    category: str  # "crash", "uart", "build", "flash"
    signature: str  # Normalized error signature
    first_seen: float = 0
    last_seen: float = 0
    flash_count: int = 0
    total_occurrences: int = 0

    def __hash__(self) -> int:
        return hash((self.category, self.signature))


@dataclass
class CircuitBreakerAlert:
    """Alert when circuit breaker triggers."""
    timestamp: str = ""
    alert_type: str = ""  # "error_pattern_limit", "total_flash_limit"
    fingerprint: Optional[ErrorFingerprint] = None
    message: str = ""
    flash_count: int = 0
    limit: int = 0


@dataclass
class LoopResult:
    """Result of autonomous loop execution."""
    success: bool
    final_state: LoopState
    total_attempts: int = 0
    total_duration: float = 0
    steps: List[LoopStep] = field(default_factory=list)
    errors: List[ErrorInfo] = field(default_factory=list)
    generated_files: List[str] = field(default_factory=list)
    fix_history: List[str] = field(default_factory=list)
    message: str = ""
    crash_log: Optional[CrashLog] = None
    circuit_breaker_alerts: List[CircuitBreakerAlert] = field(default_factory=list)
    total_flashes: int = 0
    error_fingerprints: Dict[str, ErrorFingerprint] = field(default_factory=dict)


class AutonomousLoop:
    """
    Autonomous Development Loop - AI controls the entire development cycle.

    The AI agent:
    1. Generates code based on task
    2. Builds the firmware
    3. Flashes to hardware
    4. Reads serial output
    5. Analyzes results
    6. Fixes issues if needed
    7. Retries until success or max retries

    Human only intervenes:
    - To provide initial task/requirement
    - To review final result
    - When AI requests help (stuck)
    """

    def __init__(
        self,
        agent: Any,
        config: Optional[LoopConfig] = None,
        project_root: str = "main/software",
        build_tools: Optional[Any] = None,
    ):
        self.agent = agent
        self.config = config or LoopConfig()
        self.project_root = Path(project_root)

        # Shared build_tools instance (injected) or create new one
        self._build_tools = build_tools

        self._state = LoopState.IDLE
        self._steps: List[LoopStep] = []
        self._errors: List[ErrorInfo] = []
        self._fix_history: List[str] = []
        self._start_time: float = 0
        self._serial: Optional[SerialReader] = None
        self._current_task: str = ""

        # Circuit Breaker state
        self._error_fingerprints: Dict[str, ErrorFingerprint] = {}
        self._total_flashes: int = 0
        self._alerts: List[CircuitBreakerAlert] = []
        self._current_error_fp: Optional[str] = None

        # Physical Reset state
        self._hardware_reset: Optional[HardwareReset] = None
        self._watchdog_running: bool = False

        # Callbacks
        self.on_state_change: Optional[Callable[[LoopState, str], None]] = None
        self.on_step_complete: Optional[Callable[[LoopStep], None]] = None
        self.on_error: Optional[Callable[[ErrorInfo], None]] = None
        self.on_circuit_breaker: Optional[Callable[[CircuitBreakerAlert], None]] = None

    def _set_state(self, state: LoopState, message: str = "") -> None:
        """Update loop state with optional message."""
        self._state = state
        if self.config.verbose:
            state_str = f"[{state.value.upper()}]"
            if message:
                state_str += f" {message}"
            logger.info(state_str)
        if self.on_state_change:
            self.on_state_change(state, message)

    def _add_step(self, step: LoopStep) -> None:
        """Record a completed step."""
        self._steps.append(step)
        if self.on_step_complete:
            self.on_step_complete(step)

    def _log_error(self, error: ErrorInfo) -> None:
        """Log a detected error."""
        self._errors.append(error)
        if self.config.verbose:
            logger.warning(f"Error detected [{error.severity.value}]: {error.message}")
        if self.on_error:
            self.on_error(error)

    def _compute_error_fingerprint(self, output: str, crash: Optional[CrashLog], errors: List[ErrorInfo]) -> str:
        """
        Compute a unique fingerprint for the current error pattern.
        Different errors = different fingerprints = separate retry counters.
        """
        parts = []

        # Crash type is the primary differentiator
        if crash and crash.crash_type:
            parts.append(f"crash:{crash.crash_type}")
            if crash.pc_address:
                parts.append(f"pc:0x{crash.pc_address:08X}")

        # UART/serial errors
        if not crash:
            uart_patterns = [
                (r"timeout", "uart_timeout"),
                (r"uart.*error", "uart_error"),
                (r"framing", "uart_framing"),
                (r"overrun", "uart_overrun"),
            ]
            for pattern, name in uart_patterns:
                if re.search(pattern, output, re.IGNORECASE):
                    parts.append(name)
                    break

        # Build/flash errors
        for err in errors:
            if err.source in ("build", "flash"):
                parts.append(f"{err.source}:{err.pattern}")
            elif err.source.startswith("analysis"):
                parts.append(f"runtime:{err.pattern}")

        # Fallback: use error count as category
        if not parts:
            parts.append(f"generic:{len(errors)}")

        return "|".join(sorted(set(parts)))

    def is_new_error_pattern(self, fp_key: str) -> bool:
        """Check if this is a new error pattern (different from last attempt)."""
        return self._current_error_fp is None or self._current_error_fp != fp_key

    def reset_fingerprint_count(self, fp_key: str) -> None:
        """Reset flash count when encountering a new error pattern."""
        if fp_key in self._error_fingerprints:
            logger.info(f"New error pattern detected, resetting counter for: {fp_key}")
        self._current_error_fp = fp_key

    def _get_or_create_fingerprint(self, fp_key: str, category: str) -> ErrorFingerprint:
        """Get existing fingerprint or create new one."""
        if fp_key not in self._error_fingerprints:
            self._error_fingerprints[fp_key] = ErrorFingerprint(
                category=category,
                signature=fp_key,
                first_seen=time.time(),
            )
        return self._error_fingerprints[fp_key]

    def _check_circuit_breaker(self, fp_key: str) -> tuple[bool, Optional[CircuitBreakerAlert]]:
        """
        Check if circuit breaker should trigger.
        Returns (should_stop, alert_info).
        """
        fp = self._error_fingerprints.get(fp_key)
        if not fp:
            return False, None

        # Check total flash limit
        if self._total_flashes >= self.config.max_total_flashes:
            alert = CircuitBreakerAlert(
                timestamp=datetime.now().isoformat(),
                alert_type="total_flash_limit",
                message=f"Total flash limit reached: {self._total_flashes}/{self.config.max_total_flashes}",
                flash_count=self._total_flashes,
                limit=self.config.max_total_flashes,
            )
            self._alerts.append(alert)
            return True, alert

        # Check per-error fingerprint limit
        if fp.flash_count >= self.config.max_flash_per_error:
            alert = CircuitBreakerAlert(
                timestamp=datetime.now().isoformat(),
                alert_type="error_pattern_limit",
                fingerprint=fp,
                message=f"Same error pattern repeated {fp.flash_count} times: {fp.signature}",
                flash_count=fp.flash_count,
                limit=self.config.max_flash_per_error,
            )
            self._alerts.append(alert)
            return True, alert

        return False, None

    def _send_alert(self, alert: CircuitBreakerAlert) -> None:
        """Send circuit breaker alert via configured callback."""
        logger.warning(f"CIRCUIT BREAKER ALERT: {alert.message}")

        # Call registered callback
        if self.config.alert_callback:
            try:
                self.config.alert_callback(alert.alert_type, alert.message)
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")

        # Call event handler if registered
        if self.on_circuit_breaker:
            try:
                self.on_circuit_breaker(alert)
            except Exception as e:
                logger.error(f"Circuit breaker callback failed: {e}")

    def _get_serial(self) -> SerialReader:
        """Get or create serial reader."""
        if self._serial is None:
            self._serial = SerialReader(
                SerialConfig(
                    port=self.config.serial_port,
                    baudrate=self.config.serial_baudrate,
                )
            )
        return self._serial

    def _get_hardware_reset(self) -> Optional[HardwareReset]:
        """Get or create hardware reset instance."""
        if not self.config.enable_hardware_reset:
            return None
        if self._hardware_reset is None:
            self._hardware_reset = HardwareReset(
                debugger=self.config.hardware_reset_debugger,
                device=self.config.hardware_reset_device,
            )
        return self._hardware_reset

    async def _generate_code(self, task: str) -> bool:
        """Step 1: Generate code using AI agent."""
        self._set_state(LoopState.GENERATING, f"Generating code for: {task[:50]}...")

        step = LoopStep(step="generate", state=LoopState.GENERATING, start_time=time.time())

        try:
            result = await self.agent.execute_task(task)

            step.success = result.success
            step.message = result.message
            step.data = {
                "files_created": result.files_created,
                "attempts": result.attempts,
            }

            if result.success and result.files_created:
                self._fix_history.append("Initial generation successful")

            step.duration = time.time() - step.start_time
            self._add_step(step)

            self._set_state(LoopState.GENERATING,
                          f"Code generation {'successful' if result.success else 'failed'}")
            return result.success

        except Exception as e:
            step.success = False
            step.message = str(e)
            step.duration = time.time() - step.start_time
            self._add_step(step)

            self._log_error(ErrorInfo(
                severity=ErrorSeverity.ERROR,
                pattern="generation_exception",
                message=f"Code generation failed: {e}",
                source="generate",
            ))

            return False

    async def _build(self) -> bool:
        """Step 2: Build the firmware."""
        self._set_state(LoopState.BUILDING, "Building firmware...")

        step = LoopStep(step="build", state=LoopState.BUILDING, start_time=time.time())

        try:
            if self._build_tools is None:
                from src.core.tools.build_tools import BuildTools
                self._build_tools = BuildTools(project_root=str(self.project_root))

            result = await self._build_tools.run_build()

            step.success = (result.status == "success")
            step.message = result.stderr or result.stdout
            step.data = {
                "returncode": result.returncode,
                "errors": [e.message for e in result.errors] if result.errors else [],
            }

            if not step.success and result.errors:
                for err in result.errors[:5]:
                    self._log_error(ErrorInfo(
                        severity=ErrorSeverity.ERROR,
                        pattern=f"line_{err.line}",
                        message=err.message,
                        source=f"{err.file}:{err.line}",
                        line_hint=err.line,
                    ))

            step.duration = time.time() - step.start_time
            self._add_step(step)

            self._set_state(LoopState.BUILDING,
                          f"Build {'successful' if step.success else 'failed'}")
            return step.success

        except Exception as e:
            step.success = False
            step.message = str(e)
            step.duration = time.time() - step.start_time
            self._add_step(step)

            self._log_error(ErrorInfo(
                severity=ErrorSeverity.ERROR,
                pattern="build_exception",
                message=f"Build failed: {e}",
                source="build",
            ))

            return False

    async def _fix_build_errors(self, errors: List[str]) -> bool:
        """Fix build errors based on error messages."""
        self._set_state(LoopState.FIXING, "Fixing build errors...")

        step = LoopStep(step="fix_build", state=LoopState.FIXING, start_time=time.time())

        try:
            error_summary = "\n".join(errors)
            fix_task = f"Fix the following build errors:\n{error_summary}"

            result = await self.agent.execute_task(fix_task)

            step.success = result.success
            step.message = result.message
            step.data = {"files_modified": result.files_created}

            if result.success:
                self._fix_history.append(f"Fixed build errors: {errors[:2]}")

            step.duration = time.time() - step.start_time
            self._add_step(step)

            return result.success

        except Exception as e:
            step.success = False
            step.message = str(e)
            step.duration = time.time() - step.start_time
            self._add_step(step)
            return False

    async def _flash(self, project: str = "EngineCar") -> bool:
        """Step 3: Flash firmware to hardware."""
        self._set_state(LoopState.FLASHING, "Flashing to hardware...")

        step = LoopStep(step="flash", state=LoopState.FLASHING, start_time=time.time())

        try:
            if self._build_tools is None:
                from src.core.tools.build_tools import BuildTools
                self._build_tools = BuildTools(project_root=str(self.project_root))

            result = await self._build_tools.run_flash(project)

            step.success = (result.status == "success")
            step.message = result.stderr or result.stdout
            step.data = {
                "returncode": result.returncode,
                "project": project,
            }

            if not step.success:
                self._log_error(ErrorInfo(
                    severity=ErrorSeverity.ERROR,
                    pattern="flash_failed",
                    message=f"Flash failed: {step.message}",
                    source="flash",
                ))

            step.duration = time.time() - step.start_time
            self._add_step(step)

            self._set_state(LoopState.FLASHING,
                          f"Flash {'successful' if step.success else 'failed'}")
            return step.success

        except Exception as e:
            step.success = False
            step.message = str(e)
            step.duration = time.time() - step.start_time
            self._add_step(step)

            self._log_error(ErrorInfo(
                severity=ErrorSeverity.ERROR,
                pattern="flash_exception",
                message=f"Flash exception: {e}",
                source="flash",
            ))

            return False

    async def _read_serial(self) -> tuple[bool, str, Optional[CrashLog]]:
        """Step 4: Read serial output from src.infrastructure.hardware."""
        self._set_state(LoopState.READING, "Reading serial output...")

        step = LoopStep(step="read_serial", state=LoopState.READING, start_time=time.time())

        try:
            serial = self._get_serial()

            if not serial.open():
                step.success = False
                step.message = "Failed to open serial port"
                step.duration = time.time() - step.start_time
                self._add_step(step)
                return False, "", None

            serial.flush_input()
            await asyncio.sleep(0.5)

            # Start hardware watchdog if enabled
            watchdog_task = None
            reset = self._get_hardware_reset()
            if reset and self.config.enable_hardware_reset:
                logger.info(f"Starting hardware watchdog (timeout={self.config.hardware_reset_timeout}s)")
                self._watchdog_running = True

                async def watchdog_with_reset():
                    last_activity = time.time()
                    while self._watchdog_running:
                        await asyncio.sleep(1.0)
                        if time.time() - last_activity >= self.config.hardware_reset_timeout:
                            logger.warning("Hardware watchdog: Serial timeout, triggering reset...")
                            result = reset.hard_reset()
                            if result.success:
                                logger.info("Hardware reset successful, continuing...")
                            else:
                                logger.error(f"Hardware reset failed: {result.message}")
                            last_activity = time.time()
                        # Check for serial activity
                        data = serial.read_available()
                        if data.strip():
                            last_activity = time.time()

                watchdog_task = asyncio.create_task(watchdog_with_reset())

            result = serial.read_for(duration=self.config.read_duration)

            # Stop watchdog
            if watchdog_task:
                self._watchdog_running = False
                watchdog_task.cancel()
                try:
                    await watchdog_task
                except asyncio.CancelledError:
                    pass

            serial.close()

            step.success = (result.status == ReadStatus.SUCCESS)
            step.data = {
                "bytes_read": result.bytes_read,
                "duration": result.duration_seconds,
            }

            crash_log = None
            if result.data:
                crash_log = serial.parse_crash_log(result.data)
                if crash_log:
                    self._log_error(ErrorInfo(
                        severity=ErrorSeverity.CRITICAL if crash_log.crash_type == "HardFault" else ErrorSeverity.ERROR,
                        pattern="crash_detected",
                        message=f"Crash detected: {crash_log.crash_type}",
                        source="serial",
                    ))

            step.duration = time.time() - step.start_time
            self._add_step(step)

            self._set_state(LoopState.READING, f"Read {result.bytes_read} bytes")

            return True, result.data, crash_log

        except Exception as e:
            step.success = False
            step.message = str(e)
            step.duration = time.time() - step.start_time
            self._add_step(step)
            return False, "", None

    def _analyze_output(self, output: str, crash: Optional[CrashLog]) -> tuple[bool, List[ErrorInfo]]:
        """Step 5: Analyze serial output for success/failure."""
        self._set_state(LoopState.ANALYZING, "Analyzing output...")

        step = LoopStep(step="analyze", state=LoopState.ANALYZING, start_time=time.time())

        detected_errors: List[ErrorInfo] = []
        is_success = False

        if crash and crash.crash_type:
            detected_errors.append(ErrorInfo(
                severity=ErrorSeverity.CRITICAL,
                pattern="crash",
                message=f"Hardware crash: {crash.crash_type}",
                source="analysis",
            ))

        serial = self._get_serial()
        if serial.detect_success_pattern(output):
            is_success = True
            step.message = "Success pattern detected"
        else:
            error_patterns = [
                (r"ERROR[:\s]", ErrorSeverity.ERROR),
                (r"FAULT[:\s]", ErrorSeverity.ERROR),
                (r"FAILED[:\s]", ErrorSeverity.ERROR),
                (r"Assert(?:ion)? fail", ErrorSeverity.CRITICAL),
                (r"Hang", ErrorSeverity.ERROR),
                (r"Timeout", ErrorSeverity.WARNING),
            ]

            for pattern, severity in error_patterns:
                if re.search(pattern, output, re.IGNORECASE):
                    match = re.search(pattern, output, re.IGNORECASE)
                    detected_errors.append(ErrorInfo(
                        severity=severity,
                        pattern=pattern,
                        message=f"Error pattern matched: {match.group() if match else pattern}",
                        source="analysis",
                    ))

            if not detected_errors and output:
                is_success = True
                step.message = "No errors detected, output received"
            elif not output:
                is_success = False
                step.message = "No output received"

        step.success = True
        step.duration = time.time() - step.start_time
        self._add_step(step)

        for err in detected_errors:
            self._log_error(err)

        self._set_state(LoopState.ANALYZING,
                        f"Analysis complete: {'SUCCESS' if is_success else f'{len(detected_errors)} errors'}")

        return is_success, detected_errors

    async def _fix_runtime_error(self, output: str, errors: List[ErrorInfo], crash: Optional[CrashLog]) -> bool:
        """Step 6: Fix runtime errors based on analysis."""
        self._set_state(LoopState.FIXING, "Analyzing and fixing runtime errors...")

        step = LoopStep(step="fix_runtime", state=LoopState.FIXING, start_time=time.time())

        try:
            error_desc = []
            for err in errors:
                error_desc.append(f"- [{err.severity.value}] {err.message}")

            crash_desc = ""
            if crash:
                crash_desc = f"\nCrash Info:\n- Type: {crash.crash_type}\n"
                if crash.pc_address:
                    crash_desc += f"- PC: 0x{crash.pc_address:08X}\n"
                if crash.lr_address:
                    crash_desc += f"- LR: 0x{crash.lr_address:08X}\n"

            fix_task = f"""Fix the following runtime errors based on serial output:

Serial Output:
{output[:2000]}
{crash_desc}

Detected Errors:
{chr(10).join(error_desc)}

Please analyze the output and fix the code to resolve these issues."""

            result = await self.agent.execute_task(fix_task)

            step.success = result.success
            step.message = result.message

            if result.success:
                self._fix_history.append("Fixed runtime errors")

            step.duration = time.time() - step.start_time
            self._add_step(step)

            return result.success

        except Exception as e:
            step.success = False
            step.message = str(e)
            step.duration = time.time() - step.start_time
            self._add_step(step)
            return False

    def _build_result(self, success: bool, final_state: LoopState, message: str = "") -> LoopResult:
        """Build final result from loop execution."""
        return LoopResult(
            success=success,
            final_state=final_state,
            total_attempts=len([s for s in self._steps if s.step in ("generate", "fix_build", "fix_runtime")]),
            total_duration=time.time() - self._start_time,
            steps=self._steps.copy(),
            errors=self._errors.copy(),
            generated_files=self._fix_history.copy(),
            fix_history=self._fix_history.copy(),
            message=message or ("Task completed successfully" if success else "Task failed after max retries"),
            circuit_breaker_alerts=self._alerts.copy(),
            total_flashes=self._total_flashes,
            error_fingerprints={k: v for k, v in self._error_fingerprints.items()},
        )

    async def run(self, task: str, project: str = "EngineCar") -> LoopResult:
        """
        Run the autonomous development loop.

        Args:
            task: The task/requirement to implement
            project: Project name (EngineCar or RemoteControl)

        Returns:
            LoopResult with execution details
        """
        self._start_time = time.time()
        self._current_task = task
        self._steps = []
        self._errors = []
        self._fix_history = []

        # Reset Circuit Breaker state
        self._error_fingerprints = {}
        self._total_flashes = 0
        self._alerts = []
        self._current_error_fp = None

        logger.info("=" * 60)
        logger.info(f"AUTONOMOUS LOOP STARTED: {task[:80]}")
        logger.info("=" * 60)

        self._set_state(LoopState.GENERATING)

        for attempt in range(self.config.max_retries):
            logger.info(f"\n--- Attempt {attempt + 1}/{self.config.max_retries} ---")

            if attempt > 0:
                logger.info("Previous attempt failed, retrying...")

            # Step 1: Generate code
            gen_success = await self._generate_code(task)
            if not gen_success:
                if attempt < self.config.max_retries - 1:
                    continue
                return self._build_result(False, LoopState.FAILED, "Code generation failed")

            # Step 2: Build
            build_success = await self._build()

            if not build_success:
                build_errors = [s.data.get("errors", []) for s in self._steps if s.step == "build"]
                error_list = build_errors[0] if build_errors else []

                if attempt < self.config.max_retries - 1:
                    fix_success = await self._fix_build_errors(error_list)
                    if fix_success:
                        continue
                return self._build_result(False, LoopState.FAILED, "Build failed after fixes")

            # Step 3: Flash
            flash_success = await self._flash(project)

            if not flash_success:
                if attempt < self.config.max_retries - 1:
                    continue
                return self._build_result(False, LoopState.FAILED, "Flash failed")

            # Track flash count for circuit breaker
            self._total_flashes += 1
            logger.info(f"Flash #{self._total_flashes} completed")

            # Step 4: Read serial
            read_success, output, crash = await self._read_serial()

            if not read_success:
                logger.warning("Serial read failed, continuing...")

            # Step 5: Analyze
            is_success, detected_errors = self._analyze_output(output, crash)

            if is_success:
                logger.info("=" * 60)
                logger.info("AUTONOMOUS LOOP SUCCESS!")
                logger.info("=" * 60)
                return self._build_result(True, LoopState.SUCCESS, "Task completed successfully on hardware")

            # Compute error fingerprint for circuit breaker tracking
            fp_key = self._compute_error_fingerprint(output, crash, detected_errors)
            fp = self._get_or_create_fingerprint(fp_key, "runtime")
            fp.last_seen = time.time()
            fp.total_occurrences += 1
            fp.flash_count += 1
            self._current_error_fp = fp_key

            logger.info(f"Error fingerprint: {fp_key} (count: {fp.flash_count})")

            # Check circuit breaker BEFORE retry
            should_stop, alert = self._check_circuit_breaker(fp_key)
            if should_stop and alert:
                self._send_alert(alert)
                logger.error(f"CIRCUIT BREAKER TRIGGERED: {alert.message}")
                self._set_state(LoopState.MAX_RETRIES, alert.message)
                return self._build_result(
                    False, LoopState.MAX_RETRIES,
                    f"Circuit breaker: {alert.message}"
                )

            # Step 6: Fix and retry
            if attempt < self.config.max_retries - 1:
                fix_success = await self._fix_runtime_error(output, detected_errors, crash)
                if fix_success:
                    continue

        # Max retries reached
        logger.warning("=" * 60)
        logger.warning(f"AUTONOMOUS LOOP: Max retries ({self.config.max_retries}) reached")
        logger.warning("=" * 60)

        if self.config.pause_on_max_retries:
            self._set_state(LoopState.PAUSED, "Waiting for human intervention")
        else:
            self._set_state(LoopState.MAX_RETRIES, "Max retries exceeded")

        return self._build_result(False, LoopState.MAX_RETRIES,
                                  f"Failed after {self.config.max_retries} attempts")

    def pause(self) -> None:
        """Pause the loop."""
        self._set_state(LoopState.PAUSED, "Paused by user")

    def resume(self) -> None:
        """Resume paused loop."""
        if self._state == LoopState.PAUSED:
            self._set_state(LoopState.IDLE, "Resumed")

    def get_status(self) -> Dict[str, Any]:
        """Get current loop status."""
        return {
            "state": self._state.value,
            "total_steps": len(self._steps),
            "total_errors": len(self._errors),
            "attempts": len([s for s in self._steps if s.step == "generate"]),
            "duration": time.time() - self._start_time if self._start_time else 0,
            "current_task": self._current_task,
            # Circuit Breaker status
            "total_flashes": self._total_flashes,
            "flash_limit": self.config.max_flash_per_error,
            "error_fingerprints": {
                k: {"count": v.flash_count, "signature": v.signature}
                for k, v in self._error_fingerprints.items()
            },
            "alerts_count": len(self._alerts),
        }

    def get_error_summary(self) -> List[Dict[str, str]]:
        """Get summary of all detected errors."""
        return [
            {
                "severity": e.severity.value,
                "message": e.message,
                "source": e.source,
            }
            for e in self._errors
        ]

    def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """Get detailed circuit breaker status."""
        return {
            "total_flashes": self._total_flashes,
            "total_flashes_limit": self.config.max_total_flashes,
            "per_error_limit": self.config.max_flash_per_error,
            "error_fingerprints": {
                key: {
                    "signature": fp.signature,
                    "category": fp.category,
                    "flash_count": fp.flash_count,
                    "total_occurrences": fp.total_occurrences,
                    "first_seen": datetime.fromtimestamp(fp.first_seen).isoformat() if fp.first_seen else None,
                    "last_seen": datetime.fromtimestamp(fp.last_seen).isoformat() if fp.last_seen else None,
                }
                for key, fp in self._error_fingerprints.items()
            },
            "alerts": [
                {
                    "timestamp": a.timestamp,
                    "type": a.alert_type,
                    "message": a.message,
                    "flash_count": a.flash_count,
                    "limit": a.limit,
                }
                for a in self._alerts
            ],
        }


async def run_autonomous_task(
    agent: Any,
    task: str,
    project: str = "EngineCar",
    config: Optional[LoopConfig] = None,
    verbose: bool = True,
) -> LoopResult:
    """
    Convenience function to run an autonomous task.

    Usage:
        result = await run_autonomous_task(
            agent=my_agent,
            task="Implement LED blink on PC13",
            project="EngineCar",
        )

        if result.success:
            print("Task completed!")
        else:
            print(f"Failed: {result.message}")
            for error in result.errors:
                print(f"  - {error.message}")
    """
    loop = AutonomousLoop(
        agent=agent,
        config=config,
        project_root="main/software",
    )
    loop.config.verbose = verbose

    return await loop.run(task, project)


if __name__ == "__main__":
    print("""
    Autonomous Development Loop - Quick Test
    ========================================

    This module provides AI-controlled firmware development.

    Example usage:

    ```python
    from src.application.api.app.embedded_agent import EmbeddedCAgent
    from src.core.agent.autonomous_loop import run_autonomous_task

    agent = EmbeddedCAgent(project_root="main/software")

    result = await run_autonomous_task(
        agent=agent,
        task="Implement LED blink on PC13",
        project="EngineCar",
    )

    print(f"Success: {result.success}")
    print(f"Attempts: {result.total_attempts}")
    print(f"Duration: {result.total_duration:.1f}s")
    ```
    """)
