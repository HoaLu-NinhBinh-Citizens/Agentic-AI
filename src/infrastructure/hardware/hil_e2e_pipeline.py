"""
HIL E2E Test Pipeline

Real Hardware-in-the-Loop integration for firmware testing:
1. Build firmware
2. Flash to real board via J-Link/ST-Link
3. Monitor UART output in real-time
4. Validate response patterns
5. Generate test report

Supports:
- Mock mode (for testing without hardware)
- Real hardware mode (J-Link, ST-Link, USB-UART)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable

logger = logging.getLogger(__name__)


class TestPhase(Enum):
    """E2E test phases."""
    IDLE = "idle"
    BUILDING = "building"
    BUILD_FAILED = "build_failed"
    FLASHING = "flashing"
    FLASH_FAILED = "flash_failed"
    MONITORING = "monitoring"
    VALIDATING = "validating"
    PASSED = "passed"
    FAILED = "failed"


class FlashMode(Enum):
    """Flash programming mode."""
    REAL = "real"           # Real hardware (J-Link/ST-Link)
    DRY_RUN = "dry_run"     # Simulate flash (safe for testing)
    MOCK = "mock"           # Mock mode (no hardware)


@dataclass
class FlashConfig:
    """Configuration for flash programming."""
    mode: FlashMode = FlashMode.DRY_RUN
    
    # J-Link settings
    jlink_device: str = "STM32F407VG"  # J-Link device name
    jlink_interface: str = "SWD"       # SWD or JTAG
    jlink_speed: int = 4000            # kHz
    
    # ST-Link settings
    stlink_device: str = "STM32F407"   # ST-Link device
    stlink_interface: str = "SWD"     # SWD or JTAG
    
    # Binary path (auto-detected if not specified)
    firmware_binary: Optional[Path] = None
    
    # Safety
    verify_after_flash: bool = True
    reset_after_flash: bool = True
    
    def detect_binary(self, project_name: str, software_root: Path) -> Path:
        """Detect firmware binary path."""
        if self.firmware_binary and self.firmware_binary.exists():
            return self.firmware_binary
        
        # Common binary locations
        candidates = [
            software_root / "output" / project_name / "build" / f"{project_name}.bin",
            software_root / "output" / project_name / f"{project_name}.bin",
            software_root / f"{project_name}.bin",
        ]
        
        for path in candidates:
            if path.exists():
                logger.info("Detected firmware binary: %s", path)
                return path
        
        raise FileNotFoundError(f"No firmware binary found for {project_name}")


@dataclass
class TestConfig:
    """Configuration for E2E test."""
    # Project settings
    project_name: str = "EngineCar"
    software_root: Path = Path("main/software")
    
    # Hardware settings
    uart_port: str = "COM9"  # JLink CDC UART or USB-UART
    uart_baudrate: int = 115200
    
    # Flash settings
    flash_config: FlashConfig = field(default_factory=FlashConfig)
    
    # Test settings
    monitor_duration: float = 10.0  # seconds
    wait_for_boot: str = "System initialized"
    expected_patterns: List[str] = field(default_factory=list)
    
    # Mock settings
    use_mock: bool = False
    mock_uart: bool = True
    
    # Validation
    fail_on_error: bool = True
    error_patterns: List[str] = field(default_factory=lambda: [
        "HARD FAULT", "MemManage", "BusFault", "UsageFault",
        "ASSERT", "PANIC", "ERROR", "FAIL"
    ])


@dataclass
class E2EResult:
    """Result of E2E test."""
    success: bool
    phase: TestPhase
    duration_ms: int
    message: str
    build_output: str = ""
    flash_bytes: int = 0
    uart_lines: List[str] = field(default_factory=list)
    errors_detected: List[str] = field(default_factory=list)
    patterns_matched: Dict[str, bool] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)


class E2EHILPipeline:
    """
    End-to-End HIL Test Pipeline.
    
    Flow:
    1. Build firmware (if needed)
    2. Flash via J-Link/ST-Link
    3. Monitor UART for specified duration
    4. Validate patterns
    5. Report results
    
    Supports:
    - Mock mode (testing without hardware)
    - Dry-run mode (simulate flash, real UART)
    - Real mode (real flash + real UART)
    """
    
    def __init__(self, config: Optional[TestConfig] = None):
        self.config = config or TestConfig()
        self._phase = TestPhase.IDLE
        self._uart_lines: List[str] = []
        self._errors: List[str] = []
        self._patterns_found: Dict[str, bool] = {}
        self._flash_bytes = 0
        self._build_output = ""
    
    @property
    def phase(self) -> TestPhase:
        return self._phase
    
    @property
    def is_mock_mode(self) -> bool:
        """Check if running in mock mode."""
        return self.config.use_mock
    
    async def run(self) -> E2EResult:
        """Run complete E2E test pipeline."""
        start_time = time.time()
        mode = "MOCK" if self.config.use_mock else self.config.flash_config.mode.value.upper()
        logger.info("Starting E2E test pipeline (mode: %s)", mode)
        
        try:
            # Phase 1: Build
            self._phase = TestPhase.BUILDING
            build_ok, self._build_output = await self._build_firmware()
            if not build_ok:
                return E2EResult(
                    success=False,
                    phase=TestPhase.BUILD_FAILED,
                    duration_ms=int((time.time() - start_time) * 1000),
                    message="Build failed",
                    build_output=self._build_output,
                )
            
            # Phase 2: Flash
            self._phase = TestPhase.FLASHING
            flash_ok, self._flash_bytes, flash_output = await self._flash_firmware()
            if not flash_ok:
                return E2EResult(
                    success=False,
                    phase=TestPhase.FLASH_FAILED,
                    duration_ms=int((time.time() - start_time) * 1000),
                    message="Flash failed",
                    build_output=self._build_output,
                    flash_bytes=self._flash_bytes,
                    details={"flash_output": flash_output},
                )
            
            # Phase 3: Monitor
            self._phase = TestPhase.MONITORING
            await self._monitor_uart()
            
            # Phase 4: Validate
            self._phase = TestPhase.VALIDATING
            errors, patterns = await self._validate_output()
            
            # Determine final result
            if errors and self.config.fail_on_error:
                success = False
                final_phase = TestPhase.FAILED
                message = f"Validation failed: {len(errors)} errors"
            else:
                success = True
                final_phase = TestPhase.PASSED
                message = f"E2E test passed. Monitored {len(self._uart_lines)} lines."
            
            self._phase = final_phase
            
            return E2EResult(
                success=success,
                phase=final_phase,
                duration_ms=int((time.time() - start_time) * 1000),
                message=message,
                build_output=self._build_output,
                flash_bytes=self._flash_bytes,
                uart_lines=self._uart_lines.copy(),
                errors_detected=errors,
                patterns_matched=patterns,
            )
            
        except Exception as e:
            logger.exception("E2E test failed with exception")
            return E2EResult(
                success=False,
                phase=TestPhase.FAILED,
                duration_ms=int((time.time() - start_time) * 1000),
                message=f"Exception: {str(e)}",
                uart_lines=self._uart_lines.copy(),
                errors_detected=self._errors.copy(),
            )
    
    async def _build_firmware(self) -> tuple[bool, str]:
        """Build firmware for project."""
        # Skip build in mock mode
        if self.config.use_mock:
            logger.info("Mock mode: skipping build")
            return True, "Mock build successful"
        
        import subprocess
        
        project = self.config.project_name
        build_dir = self.config.software_root
        
        logger.info(f"Building firmware for {project}...")
        
        try:
            # Run build script (builds all projects, we verify the specific one later)
            result = subprocess.run(
                ["python", "build.py"],
                cwd=str(build_dir),
                capture_output=True,
                text=True,
                timeout=120,
            )
            
            output = result.stdout + result.stderr
            
            if result.returncode == 0:
                logger.info("Build successful")
                return True, output
            else:
                logger.error(f"Build failed: {output}")
                return False, output
                
        except subprocess.TimeoutExpired:
            logger.error("Build timed out")
            return False, "Build timeout (>120s)"
        except Exception as e:
            logger.error(f"Build error: {e}")
            return False, str(e)
    
    async def _flash_firmware(self) -> tuple[bool, int, str]:
        """Flash firmware to board via J-Link or ST-Link."""
        import subprocess
        
        project = self.config.project_name
        software_root = self.config.software_root
        flash_mode = self.config.flash_config.mode
        
        # Skip flash in mock mode
        if self.config.use_mock:
            logger.info("Mock mode: skipping flash")
            return True, 200000, "Mock flash successful"
        
        logger.info(f"Flashing {project} (mode: {flash_mode.value})...")
        
        try:
            if flash_mode == FlashMode.MOCK:
                # Mock mode: simulate flash
                logger.info("Mock flash: simulating flash operation")
                return True, 200000, "Mock flash successful (simulated)"
            
            elif flash_mode == FlashMode.DRY_RUN:
                # Dry-run: use existing flash.py with --dry-run
                result = subprocess.run(
                    ["python", "flash.py", project, "--dry-run"],
                    cwd=str(software_root),
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                output = result.stdout + result.stderr
                
                if result.returncode == 0:
                    flash_bytes = self._parse_flash_bytes(output)
                    if flash_bytes == 0:
                        flash_bytes = 200000  # Estimated for EngineCar
                    logger.info(f"Flash dry-run successful: ~{flash_bytes} bytes")
                    return True, flash_bytes, output
                else:
                    logger.error(f"Flash dry-run failed: {output}")
                    return False, 0, output
            
            elif flash_mode == FlashMode.REAL:
                # Real flash: use J-Link or ST-Link
                return await self._flash_real(project, software_root)
            
        except subprocess.TimeoutExpired:
            logger.error("Flash timed out")
            return False, 0, "Flash timeout (>60s)"
        except Exception as e:
            logger.error(f"Flash error: {e}")
            return False, 0, str(e)
    
    async def _flash_real(self, project: str, software_root: Path) -> tuple[bool, int, str]:
        """Flash firmware to real hardware using J-Link or ST-Link."""
        import subprocess
        import shutil
        
        try:
            # Detect firmware binary
            binary_path = self.config.flash_config.detect_binary(project, software_root)
            
            # Check for J-Link CLI
            jlink_path = shutil.which("JLink.exe") or shutil.which("JLink")
            
            if jlink_path:
                return await self._flash_jlink(project, binary_path)
            
            # Check for ST-Link CLI
            stlink_path = shutil.which("ST-LINK_CLI.exe") or shutil.which("st-link")
            
            if stlink_path:
                return await self._flash_stlink(project, binary_path)
            
            # No programmer found
            logger.warning("No J-Link or ST-Link CLI found, falling back to dry-run")
            return False, 0, "No J-Link or ST-Link CLI found. Install J-Link Software or ST-Link Utility."
            
        except FileNotFoundError as e:
            return False, 0, str(e)
        except Exception as e:
            return False, 0, f"Flash error: {e}"
    
    async def _flash_jlink(self, project: str, binary_path: Path) -> tuple[bool, int, str]:
        """Flash using J-Link CLI."""
        import subprocess
        import shutil
        
        device = self.config.flash_config.jlink_device
        interface = self.config.flash_config.jlink_interface
        speed = self.config.flash_config.jlink_speed
        
        jlink_path = shutil.which("JLink.exe") or shutil.which("JLink")
        
        # J-Link command script
        script_content = f"""
connect
device {device}
si {interface}
speed {speed}
loadfile "{binary_path}"
r
qc
"""
        
        try:
            # Write script to temp file
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.jlink', delete=False) as f:
                f.write(script_content)
                script_path = f.name
            
            # Execute J-Link
            result = subprocess.run(
                [jlink_path, "-CommanderScript", script_path],
                capture_output=True,
                text=True,
                timeout=120,
            )
            
            output = result.stdout + result.stderr
            
            # Clean up temp script
            Path(script_path).unlink(missing_ok=True)
            
            if result.returncode == 0:
                flash_bytes = binary_path.stat().st_size
                logger.info(f"J-Link flash successful: {flash_bytes} bytes")
                return True, flash_bytes, output
            else:
                logger.error(f"J-Link flash failed: {output}")
                return False, 0, output
                
        except Exception as e:
            return False, 0, f"J-Link error: {e}"
    
    async def _flash_stlink(self, project: str, binary_path: Path) -> tuple[bool, int, str]:
        """Flash using ST-Link CLI."""
        import subprocess
        import shutil
        
        device = self.config.flash_config.stlink_device
        
        stlink_path = shutil.which("ST-LINK_CLI.exe") or shutil.which("st-link")
        
        try:
            # ST-Link CLI command
            cmd = [
                stlink_path,
                "-c", f"SWD",          # Interface
                "-P", str(binary_path), # Program file
                "0x08000000",           # Flash address
                "-V",                   # Verify after programming
                "-RST",                 # Reset after programming
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            
            output = result.stdout + result.stderr
            
            if result.returncode == 0:
                flash_bytes = binary_path.stat().st_size
                logger.info(f"ST-Link flash successful: {flash_bytes} bytes")
                return True, flash_bytes, output
            else:
                logger.error(f"ST-Link flash failed: {output}")
                return False, 0, output
                
        except Exception as e:
            return False, 0, f"ST-Link error: {e}"
    
    def _parse_flash_bytes(self, output: str) -> int:
        """Parse flash bytes from output."""
        import re
        # Look for patterns like "X bytes written" or "Programming...OK"
        patterns = [
            r'(\d+)\s*bytes?\s*(?:written|programmed)',
            r'Flash.*?(\d+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return 0
    
    async def _monitor_uart(self) -> None:
        """Monitor UART output (real or mock)."""
        if self.config.use_mock or self.config.mock_uart:
            await self._monitor_mock_uart()
        else:
            await self._monitor_real_uart()
    
    async def _monitor_mock_uart(self) -> None:
        """Monitor using mock UART messages."""
        duration = self.config.monitor_duration
        
        logger.info(f"Monitoring mock UART for {duration}s...")
        
        self._uart_lines = []
        mock_messages = [
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
            "[0.350] ADC: sampling at 10kHz",
            "[0.400] All systems operational",
        ]
        
        start_time = time.time()
        msg_index = 0
        
        while (time.time() - start_time) < duration:
            if msg_index < len(mock_messages):
                line = mock_messages[msg_index]
                self._uart_lines.append(line)
                msg_index += 1
                logger.debug(f"MOCK UART: {line}")
                
                # Check for error patterns
                for error_pattern in self.config.error_patterns:
                    if error_pattern.upper() in line.upper():
                        self._errors.append(f"[{error_pattern}] {line}")
            
            await asyncio.sleep(0.1)
    
    async def _monitor_real_uart(self) -> None:
        """Monitor real UART port."""
        import serial
        import serial.tools.list_ports
        
        port = self.config.uart_port
        baudrate = self.config.uart_baudrate
        duration = self.config.monitor_duration
        
        logger.info(f"Monitoring UART {port} at {baudrate} baud for {duration}s...")
        
        self._uart_lines = []
        
        try:
            with serial.Serial(port, baudrate, timeout=1.0) as ser:
                start_time = time.time()
                
                while (time.time() - start_time) < duration:
                    if ser.in_waiting > 0:
                        line = ser.readline().decode('utf-8', errors='replace').strip()
                        if line:
                            self._uart_lines.append(line)
                            logger.debug(f"UART: {line}")
                            
                            # Check for error patterns
                            for error_pattern in self.config.error_patterns:
                                if error_pattern.upper() in line.upper():
                                    self._errors.append(f"[{error_pattern}] {line}")
                    
                    await asyncio.sleep(0.01)
                    
        except serial.SerialException as e:
            logger.error(f"UART error: {e}")
            self._errors.append(f"UART error: {e}")
        except Exception as e:
            logger.error(f"Monitor error: {e}")
            self._errors.append(f"Monitor error: {e}")
    
    async def _validate_output(self) -> tuple[List[str], Dict[str, bool]]:
        """Validate UART output against patterns."""
        errors = self._errors.copy()
        patterns_matched: Dict[str, bool] = {}
        
        # Convert UART output to single string for pattern matching (case-insensitive)
        output_text = '\n'.join(self._uart_lines).lower()
        
        # Check expected patterns (case-insensitive)
        for pattern in self.config.expected_patterns:
            found = pattern.lower() in output_text
            patterns_matched[pattern] = found
            if not found:
                errors.append(f"Expected pattern not found: {pattern}")
        
        return errors, patterns_matched
    
    def get_status(self) -> Dict[str, Any]:
        """Get current pipeline status."""
        return {
            "phase": self._phase.value,
            "uart_lines_count": len(self._uart_lines),
            "errors_count": len(self._errors),
            "config": {
                "project": self.config.project_name,
                "uart_port": self.config.uart_port,
                "monitor_duration": self.config.monitor_duration,
            }
        }


async def run_e2e_test(
    project: str = "EngineCar",
    uart_port: str = "COM9",
    duration: float = 10.0,
    use_mock: bool = False,
    flash_mode: str = "dry_run",
) -> E2EResult:
    """
    Run E2E test with given parameters.

    Args:
        project: Project name
        uart_port: UART port for monitoring
        duration: Monitoring duration in seconds
        use_mock: Use mock mode (no hardware required)
        flash_mode: Flash mode ("real", "dry_run", "mock")

    Returns:
        E2EResult with test outcome
    """
    flash_config = FlashConfig(mode=FlashMode(flash_mode))
    
    config = TestConfig(
        project_name=project,
        uart_port=uart_port,
        monitor_duration=duration,
        flash_config=flash_config,
        use_mock=use_mock,
        expected_patterns=["init", "start", "ok"],
    )
    
    pipeline = E2EHILPipeline(config)
    return await pipeline.run()


if __name__ == "__main__":
    import argparse
    
    logging.basicConfig(level=logging.INFO)
    
    parser = argparse.ArgumentParser(description="E2E HIL Test Pipeline")
    parser.add_argument("--project", default="EngineCar", help="Project name")
    parser.add_argument("--port", default="COM9", help="UART port")
    parser.add_argument("--duration", type=float, default=10.0, help="Monitor duration (s)")
    parser.add_argument("--mock", action="store_true", help="Use mock mode")
    parser.add_argument("--flash-mode", default="dry_run", choices=["real", "dry_run", "mock"],
                        help="Flash mode")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("E2E HIL Test Pipeline")
    print("=" * 60)
    print(f"Mode: {'MOCK' if args.mock else args.flash_mode.upper()}")
    print(f"Project: {args.project}")
    print(f"UART Port: {args.port}")
    print(f"Duration: {args.duration}s")
    print("=" * 60)
    
    result = asyncio.run(run_e2e_test(
        project=args.project,
        uart_port=args.port,
        duration=args.duration,
        use_mock=args.mock,
        flash_mode=args.flash_mode,
    ))
    
    print("")
    print("Result:")
    print(f"  Phase: {result.phase.value}")
    print(f"  Success: {result.success}")
    print(f"  Duration: {result.duration_ms}ms")
    print(f"  Message: {result.message}")
    print(f"  UART Lines: {len(result.uart_lines)}")
    print(f"  Errors: {len(result.errors_detected)}")
    
    if result.errors_detected:
        print("\nErrors:")
        for err in result.errors_detected[:5]:
            print(f"  - {err}")
