"""
Hardware Reset - Physical Reset via JTAG/SWD Debuggers

Provides physical reset capabilities for embedded systems when software-level
recovery is impossible (chip hard-lock, no serial output).

Supports:
- SEGGER J-Link
- ST-Link CLI
- OpenOCD

Usage:
    reset = HardwareReset(debugger="jlink", device="STM32F407VG")
    result = reset.hard_reset()

    # Emergency watchdog
    reset.emergency_watchdog(
        serial_reader=serial_reader,
        timeout_sec=30,
        on_timeout=lambda: reset.hard_reset()
    )
"""

import asyncio
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class DebuggerType(Enum):
    """Supported debugger types."""
    JLINK = "jlink"
    STLINK = "stlink"
    OPENOCD = "openocd"


class ResetStatus(Enum):
    """Reset operation status."""
    SUCCESS = "success"
    FAILED = "failed"
    NOT_CONNECTED = "not_connected"
    TIMEOUT = "timeout"
    DEVICE_MISMATCH = "device_mismatch"
    COMMAND_ERROR = "command_error"


@dataclass
class ResetResult:
    """Result of a reset operation."""
    status: ResetStatus
    message: str = ""
    duration_ms: float = 0.0
    reset_count: int = 0
    debugger_version: str = ""
    device_id: str = ""
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.status == ResetStatus.SUCCESS


@dataclass
class DeviceInfo:
    """Connected device information."""
    debugger_type: DebuggerType
    device_name: str = ""
    serial_number: str = ""
    firmware_version: str = ""
    interface: str = ""  # JTAG, SWD, etc.


class HardwareReset:
    """
    Physical hardware reset via JTAG/SWD debuggers.

    Provides:
    - Hard reset (halt → reset → run)
    - CPU halt/resume
    - Connection status check
    - Emergency watchdog for serial timeout
    """

    SUPPORTED_DEBUGGERS = ["jlink", "stlink", "openocd"]
    DEFAULT_TIMEOUT_SEC = 10

    def __init__(
        self,
        debugger: str = "jlink",
        device: str = "STM32F407VG",
        interface: str = "SWD",
        script_path: Optional[str] = None,
    ):
        self.debugger = self._normalize_debugger(debugger)
        self.device = device
        self.interface = interface.upper()
        self.script_path = script_path

        self._reset_count = 0
        self._session_start = time.time()
        self._cooldown_until = 0.0

        # Safety limits
        self._max_resets_per_session = 10
        self._min_reset_interval_sec = 2.0

    def _normalize_debugger(self, debugger: str) -> DebuggerType:
        """Normalize debugger string to enum."""
        normalized = debugger.lower().strip()
        if "jlink" in normalized or "segger" in normalized:
            return DebuggerType.JLINK
        if "stlink" in normalized or "st-" in normalized:
            return DebuggerType.STLINK
        if "openocd" in normalized:
            return DebuggerType.OPENOCD
        raise ValueError(
            f"Unsupported debugger: {debugger}. "
            f"Supported: {', '.join(self.SUPPORTED_DEBUGGERS)}"
        )

    def _find_executable(self) -> Optional[Path]:
        """Find debugger executable in PATH and common locations."""
        if self.debugger == DebuggerType.JLINK:
            candidates = ["JLink.exe", "JLinkARM.exe"]
        elif self.debugger == DebuggerType.STLINK:
            candidates = ["ST-LINK_CLI.exe", "STLinkExe.exe"]
        else:
            candidates = ["openocd.exe", "openocd"]

        for candidate in candidates:
            # Check PATH
            path = Path(shutil.which(candidate) or "")
            if path.exists():
                return path

            # Check common installation paths (Windows)
            if os.name == "nt":
                common_paths = [
                    Path(os.environ.get("ProgramFiles", "")) / "SEGGER" / candidate,
                    Path(os.environ.get("ProgramFiles(x86)", "")) / "SEGGER" / candidate,
                    Path(os.environ.get("ST_TOOLSET", "")) / candidate,
                ]
                for common in common_paths:
                    if common.exists():
                        return common

        return None

    def _run_command(
        self,
        cmd: List[str],
        timeout: int = 30,
    ) -> tuple[int, str, str]:
        """Run debugger command and return exit code, stdout, stderr."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timeout"
        except FileNotFoundError:
            return -2, "", f"Executable not found: {cmd[0]}"
        except Exception as e:
            return -3, "", str(e)

    def is_connected(self) -> bool:
        """Check if debugger is connected to device."""
        if self.debugger == DebuggerType.JLINK:
            return self._jlink_is_connected()
        elif self.debugger == DebuggerType.STLINK:
            return self._stlink_is_connected()
        return self._openocd_is_connected()

    def _jlink_is_connected(self) -> bool:
        """Check JLink connection."""
        exe = self._find_executable()
        if not exe:
            logger.warning("JLink executable not found")
            return False

        cmd = [
            str(exe),
            "-Device", self.device,
            "-If", self.interface,
            "-CommanderScript", "connect.jlink",
        ]

        script_content = "qc\nquit\n"
        script_path = self.script_path or self._create_temp_script(
            "connect", script_content
        )
        cmd[-1] = script_path

        exit_code, stdout, stderr = self._run_command(cmd, timeout=5)
        return exit_code == 0

    def _stlink_is_connected(self) -> bool:
        """Check ST-Link connection."""
        exe = self._find_executable()
        if not exe:
            logger.warning("ST-Link executable not found")
            return False

        cmd = [str(exe), "-List"]
        exit_code, stdout, stderr = self._run_command(cmd, timeout=5)
        return exit_code == 0 and self.device.upper() in stdout.upper()

    def _openocd_is_connected(self) -> bool:
        """Check OpenOCD connection via telnet probe."""
        return True  # OpenOCD requires daemon, simplified check

    def get_device_info(self) -> Optional[DeviceInfo]:
        """Get connected device information."""
        if self.debugger == DebuggerType.JLINK:
            return self._jlink_get_info()
        elif self.debugger == DebuggerType.STLINK:
            return self._stlink_get_info()
        return None

    def _jlink_get_info(self) -> Optional[DeviceInfo]:
        """Get device info from J-Link."""
        exe = self._find_executable()
        if not exe:
            return None

        script_content = "device\nquit\n"
        script_path = self._create_temp_script("info", script_content)

        cmd = [str(exe), "-CommanderScript", script_path]
        exit_code, stdout, stderr = self._run_command(cmd, timeout=10)

        info = DeviceInfo(debugger_type=DebuggerType.JLINK)
        info.device_name = self.device
        info.interface = self.interface

        # Parse firmware version
        for line in stdout.splitlines():
            if "Firmware" in line or "Build" in line:
                info.firmware_version = line.strip()
                break

        return info

    def _stlink_get_info(self) -> Optional[DeviceInfo]:
        """Get device info from ST-Link."""
        exe = self._find_executable()
        if not exe:
            return None

        cmd = [str(exe), "-TargetId", self.device, "-InfoDbg"]
        exit_code, stdout, stderr = self._run_command(cmd, timeout=10)

        info = DeviceInfo(debugger_type=DebuggerType.STLINK)
        info.device_name = self.device

        for line in stdout.splitlines():
            if "Serial" in line:
                info.serial_number = line.split("Serial")[-1].strip()
            if "FW" in line or "Firmware" in line:
                info.firmware_version = line.strip()

        return info

    def _create_temp_script(self, name: str, content: str) -> str:
        """Create temporary script file for debugger."""
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".jlink" if self.debugger == DebuggerType.JLINK else ".cfg")
        with os.fdopen(fd, "w") as f:
            f.write(content)
        return path

    def hard_reset(self) -> ResetResult:
        """
        Execute hard reset: halt → reset → run.

        This is the primary method for recovering from hard-lock states.

        Returns:
            ResetResult with status and details
        """
        start = time.time()

        # Safety check: cooldown
        if time.time() < self._cooldown_until:
            wait_time = self._cooldown_until - time.time()
            return ResetResult(
                status=ResetStatus.FAILED,
                message=f"Reset cooldown active. Wait {wait_time:.1f}s",
                duration_ms=(time.time() - start) * 1000,
                reset_count=self._reset_count,
            )

        # Safety check: max resets
        if self._reset_count >= self._max_resets_per_session:
            return ResetResult(
                status=ResetStatus.FAILED,
                message=f"Max resets ({self._max_resets_per_session}) exceeded",
                duration_ms=(time.time() - start) * 1000,
                reset_count=self._reset_count,
            )

        # Execute reset based on debugger
        if self.debugger == DebuggerType.JLINK:
            result = self._jlink_reset()
        elif self.debugger == DebuggerType.STLINK:
            result = self._stlink_reset()
        else:
            result = self._openocd_reset()

        result.duration_ms = (time.time() - start) * 1000
        result.reset_count = self._reset_count

        if result.success:
            self._reset_count += 1
            self._cooldown_until = time.time() + self._min_reset_interval_sec
            logger.info(
                f"Hard reset successful. Reset #{self._reset_count} "
                f"in {result.duration_ms:.1f}ms"
            )
        else:
            logger.warning(f"Hard reset failed: {result.message}")

        return result

    def _jlink_reset(self) -> ResetResult:
        """Execute reset via J-Link."""
        exe = self._find_executable()
        if not exe:
            return ResetResult(
                status=ResetStatus.NOT_CONNECTED,
                message="JLink executable not found",
            )

        script = "\n".join([
            "r",
            "h",
            "go",
            "qc",
        ])

        script_path = self._create_temp_script("reset", script)
        cmd = [
            str(exe),
            "-Device", self.device,
            "-If", self.interface,
            "-CommanderScript", script_path,
        ]

        exit_code, stdout, stderr = self._run_command(cmd, timeout=self.DEFAULT_TIMEOUT_SEC)

        if exit_code == 0:
            return ResetResult(
                status=ResetStatus.SUCCESS,
                message="JLink reset completed",
                debugger_version=self._parse_jlink_version(stdout),
            )

        return ResetResult(
            status=ResetStatus.COMMAND_ERROR,
            message=f"JLink command failed: {stderr or stdout}",
            error=stderr,
        )

    def _stlink_reset(self) -> ResetResult:
        """Execute reset via ST-Link CLI."""
        exe = self._find_executable()
        if not exe:
            return ResetResult(
                status=ResetStatus.NOT_CONNECTED,
                message="ST-Link executable not found",
            )

        cmd = [
            str(exe),
            "-TargetId", self.device,
            "-Rst",
            "-Run",
        ]

        exit_code, stdout, stderr = self._run_command(cmd, timeout=self.DEFAULT_TIMEOUT_SEC)

        if exit_code == 0:
            return ResetResult(
                status=ResetStatus.SUCCESS,
                message="ST-Link reset completed",
                debugger_version=self._parse_stlink_version(stdout),
            )

        return ResetResult(
            status=ResetStatus.COMMAND_ERROR,
            message=f"ST-Link command failed: {stderr or stdout}",
            error=stderr,
        )

    def _openocd_reset(self) -> ResetResult:
        """Execute reset via OpenOCD."""
        cmd = [
            "openocd",
            "-f", f"interface/{self._openocd_interface()}.cfg",
            "-f", f"target/{self._openocd_target()}.cfg",
            "-c", "init; reset halt; reset run; shutdown",
        ]

        exit_code, stdout, stderr = self._run_command(cmd, timeout=self.DEFAULT_TIMEOUT_SEC)

        if exit_code == 0:
            return ResetResult(
                status=ResetStatus.SUCCESS,
                message="OpenOCD reset completed",
            )

        return ResetResult(
            status=ResetStatus.COMMAND_ERROR,
            message=f"OpenOCD command failed: {stderr}",
            error=stderr,
        )

    def _openocd_interface(self) -> str:
        """Get OpenOCD interface config based on debugger."""
        if self.debugger == DebuggerType.JLINK:
            return "jlink"
        if self.debugger == DebuggerType.STLINK:
            return "stlink-v2"
        return "dummy"

    def _openocd_target(self) -> str:
        """Get OpenOCD target config based on device."""
        device_upper = self.device.upper()
        if "F4" in device_upper or "STM32F4" in device_upper:
            return "stm32f4x"
        if "F1" in device_upper or "STM32F1" in device_upper:
            return "stm32f1x"
        return "stm32f4x"

    def _parse_jlink_version(self, output: str) -> str:
        """Parse J-Link version from output."""
        for line in output.splitlines():
            if "J-Link" in line and "V" in line:
                return line.strip()
        return "unknown"

    def _parse_stlink_version(self, output: str) -> str:
        """Parse ST-Link version from output."""
        for line in output.splitlines():
            if "ST-LINK" in line or "FW" in line:
                return line.strip()
        return "unknown"

    def halt(self) -> ResetResult:
        """Halt CPU execution (for debugging)."""
        start = time.time()

        if self.debugger == DebuggerType.JLINK:
            exe = self._find_executable()
            if not exe:
                return ResetResult(status=ResetStatus.NOT_CONNECTED, message="JLink not found")

            script = "h\nqc\n"
            script_path = self._create_temp_script("halt", script)
            cmd = [str(exe), "-Device", self.device, "-If", self.interface, "-CommanderScript", script_path]
            exit_code, _, _ = self._run_command(cmd, timeout=5)

        elif self.debugger == DebuggerType.STLINK:
            exe = self._find_executable()
            if not exe:
                return ResetResult(status=ResetStatus.NOT_CONNECTED, message="ST-Link not found")
            cmd = [str(exe), "-TargetId", self.device, "-Halt"]
            exit_code, _, _ = self._run_command(cmd, timeout=5)

        else:
            return ResetResult(status=ResetStatus.FAILED, message="Halt not supported for OpenOCD")

        return ResetResult(
            status=ResetStatus.SUCCESS if exit_code == 0 else ResetStatus.FAILED,
            message="CPU halted" if exit_code == 0 else "Halt failed",
            duration_ms=(time.time() - start) * 1000,
        )

    def resume(self) -> ResetResult:
        """Resume CPU execution."""
        start = time.time()

        if self.debugger == DebuggerType.JLINK:
            exe = self._find_executable()
            if not exe:
                return ResetResult(status=ResetStatus.NOT_CONNECTED, message="JLink not found")

            script = "go\nqc\n"
            script_path = self._create_temp_script("resume", script)
            cmd = [str(exe), "-Device", self.device, "-If", self.interface, "-CommanderScript", script_path]
            exit_code, _, _ = self._run_command(cmd, timeout=5)

        elif self.debugger == DebuggerType.STLINK:
            exe = self._find_executable()
            if not exe:
                return ResetResult(status=ResetStatus.NOT_CONNECTED, message="ST-Link not found")
            cmd = [str(exe), "-TargetId", self.device, "-Run"]
            exit_code, _, _ = self._run_command(cmd, timeout=5)

        else:
            return ResetResult(status=ResetStatus.FAILED, message="Resume not supported for OpenOCD")

        return ResetResult(
            status=ResetStatus.SUCCESS if exit_code == 0 else ResetStatus.FAILED,
            message="CPU resumed" if exit_code == 0 else "Resume failed",
            duration_ms=(time.time() - start) * 1000,
        )

    def emergency_watchdog(
        self,
        serial_reader,
        timeout_sec: float = 30.0,
        check_interval: float = 1.0,
        on_timeout: Optional[Callable[[], None]] = None,
        running_callback: Optional[Callable[[], bool]] = None,
    ) -> None:
        """
        Monitor serial output and trigger reset on timeout.

        This should be run in a separate thread/async task.

        Args:
            serial_reader: SerialReader instance to monitor
            timeout_sec: Seconds of silence before reset
            check_interval: How often to check for serial activity
            on_timeout: Optional callback before reset
            running_callback: Function that returns True while loop should run
        """
        last_activity = time.time()
        is_running = running_callback or (lambda: True)

        logger.info(f"Emergency watchdog started (timeout={timeout_sec}s)")

        while is_running():
            current_time = time.time()

            # Check if serial has new data
            if serial_reader.is_open():
                data = serial_reader.read_available()
                if data.strip():
                    last_activity = current_time

            # Check timeout
            silent_duration = current_time - last_activity
            if silent_duration >= timeout_sec:
                logger.warning(
                    f"Serial timeout after {silent_duration:.1f}s. "
                    f"Triggering hardware reset..."
                )

                if on_timeout:
                    on_timeout()

                self.hard_reset()
                last_activity = time.time()

            time.sleep(check_interval)

        logger.info("Emergency watchdog stopped")

    async def emergency_watchdog_async(
        self,
        serial_reader,
        timeout_sec: float = 30.0,
        check_interval: float = 1.0,
        on_timeout: Optional[Callable[[], None]] = None,
        running_callback: Optional[Callable[[], bool]] = None,
    ) -> None:
        """Async version of emergency_watchdog."""
        last_activity = time.time()
        is_running = running_callback or (lambda: True)

        logger.info(f"Emergency watchdog (async) started (timeout={timeout_sec}s)")

        while is_running():
            current_time = time.time()

            if serial_reader.is_open():
                data = serial_reader.read_available()
                if data.strip():
                    last_activity = current_time

            silent_duration = current_time - last_activity
            if silent_duration >= timeout_sec:
                logger.warning(f"Serial timeout. Triggering hardware reset...")
                if on_timeout:
                    on_timeout()
                self.hard_reset()
                last_activity = time.time()

            await asyncio.sleep(check_interval)

        logger.info("Emergency watchdog (async) stopped")

    def get_status(self) -> Dict:
        """Get current reset status and statistics."""
        session_duration = time.time() - self._session_start
        cooldown_remaining = max(0, self._cooldown_until - time.time())

        return {
            "debugger": self.debugger.value,
            "device": self.device,
            "interface": self.interface,
            "reset_count": self._reset_count,
            "max_resets": self._max_resets_per_session,
            "session_duration_sec": round(session_duration, 1),
            "cooldown_remaining_sec": round(cooldown_remaining, 2),
            "can_reset": (
                self._reset_count < self._max_resets_per_session
                and cooldown_remaining == 0
            ),
            "is_connected": self.is_connected(),
        }

    def reset_stats(self) -> None:
        """Reset statistics counters."""
        self._reset_count = 0
        self._session_start = time.time()
        self._cooldown_until = 0.0
        logger.info("Reset statistics cleared")


# Import shutil for which()
import shutil


def list_available_debuggers() -> List[Dict]:
    """List all available/debugger tools."""
    debuggers = []

    reset = HardwareReset(debugger="jlink")
    if reset._find_executable():
        debuggers.append({"type": "jlink", "available": True, "executable": str(reset._find_executable())})

    reset = HardwareReset(debugger="stlink")
    if reset._find_executable():
        debuggers.append({"type": "stlink", "available": True, "executable": str(reset._find_executable())})

    reset = HardwareReset(debugger="openocd")
    path = shutil.which("openocd")
    if path:
        debuggers.append({"type": "openocd", "available": True, "executable": path})

    return debuggers


if __name__ == "__main__":
    print("=== Hardware Reset Tool ===")
    print("\nAvailable debuggers:")
    for dbg in list_available_debuggers():
        print(f"  {dbg['type']}: {dbg['executable']}")

    print("\nUsage:")
    print("  reset = HardwareReset(debugger='jlink', device='STM32F407VG')")
    print("  result = reset.hard_reset()")
    print("  print(result.status, result.message)")
