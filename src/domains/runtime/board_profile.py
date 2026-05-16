"""
Board Profile Management for Runtime

Real implementation for board profile management with validation,
serial communication, and runtime signal detection.
"""

import importlib.util
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class BoardProfile:
    """Board profile configuration."""
    name: str
    target: str
    board_id: str = ""
    mcu: str = ""
    flash_address: int = 0x08000000
    ram_size: int = 0
    flash_size: int = 0
    serial_port: str = ""
    baudrate: int = 115200
    programmer: str = ""
    openocd_config: str = ""
    reset_method: str = "srst"
    runtime_read_seconds: float = 5.0
    serial_timeout_sec: float = 1.0
    expected_runtime_signals: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BoardProfile":
        return cls(
            name=data.get("name", "Unknown"),
            target=data.get("target", "unknown"),
            board_id=data.get("board_id", ""),
            mcu=data.get("mcu", ""),
            flash_address=data.get("flash_address", 0x08000000),
            ram_size=data.get("ram_size", 0),
            flash_size=data.get("flash_size", 0),
            serial_port=data.get("serial_port", ""),
            baudrate=data.get("baudrate", 115200),
            programmer=data.get("programmer", ""),
            openocd_config=data.get("openocd_config", ""),
            reset_method=data.get("reset_method", "srst"),
            runtime_read_seconds=data.get("runtime_read_seconds", 5.0),
            serial_timeout_sec=data.get("serial_timeout_sec", 1.0),
            expected_runtime_signals=data.get("expected_runtime_signals", []),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "target": self.target,
            "board_id": self.board_id,
            "mcu": self.mcu,
            "flash_address": f"0x{self.flash_address:08X}",
            "ram_size": self.ram_size,
            "flash_size": self.flash_size,
            "serial_port": self.serial_port,
            "baudrate": self.baudrate,
            "programmer": self.programmer,
            "openocd_config": self.openocd_config,
            "reset_method": self.reset_method,
            "runtime_read_seconds": self.runtime_read_seconds,
            "serial_timeout_sec": self.serial_timeout_sec,
            "expected_runtime_signals": self.expected_runtime_signals,
        }


MISSING_BOARD_PROFILE = BoardProfile(
    name="UNKNOWN",
    target="unknown",
)


# Required fields for validation
REQUIRED_RUNTIME_FIELDS = ["serial_port", "openocd_config"]


class BoardProfileManager:
    """Manages board profiles with validation and runtime detection."""

    def __init__(self, profiles_dir: Optional[str] = None):
        self.profiles_dir = Path(profiles_dir) if profiles_dir else Path("board_profiles")
        self._profiles: Dict[str, BoardProfile] = {}
        self._load_profiles()

    def _load_profiles(self) -> None:
        """Load all profiles from profiles directory."""
        if not self.profiles_dir.exists():
            return

        for json_file in self.profiles_dir.glob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                profile = BoardProfile.from_dict(data)
                self._profiles[profile.name] = profile
            except (json.JSONDecodeError, KeyError):
                continue

    def get_profile(self, name: str) -> BoardProfile:
        """Get board profile by name."""
        if name in self._profiles:
            return self._profiles[name]
        return MISSING_BOARD_PROFILE

    def register_profile(self, profile: BoardProfile) -> None:
        """Register a board profile."""
        self._profiles[profile.name] = profile

    def list_profiles(self) -> List[str]:
        """List all registered profile names."""
        return list(self._profiles.keys())

    def validate_profile(self, profile_path: str) -> Dict[str, Any]:
        """
        Validate a board profile file.

        Returns:
            {"valid": bool, "errors": List[str], "warnings": List[str]}
        """
        errors: List[str] = []
        warnings: List[str] = []

        try:
            path = Path(profile_path)
            if not path.exists():
                return {"valid": False, "errors": [f"File not found: {profile_path}"], "warnings": []}

            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return {"valid": False, "errors": [f"Invalid JSON: {e}"], "warnings": []}

        # Check required runtime fields
        for field in REQUIRED_RUNTIME_FIELDS:
            if not data.get(field):
                errors.append(f"Missing required field: {field}")

        # Check MCU
        if not data.get("mcu"):
            warnings.append("MCU not specified")

        # Check programmer
        if data.get("programmer") not in ["openocd", "jlink", "stlink"]:
            if data.get("programmer"):
                warnings.append(f"Unknown programmer: {data.get('programmer')}")

        # Check baudrate
        baudrate = data.get("baudrate", 0)
        valid_baudrates = [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]
        if baudrate not in valid_baudrates:
            warnings.append(f"Unusual baudrate: {baudrate}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    def parse_runtime_log(self, config: Dict[str, Any], stdout: str) -> Dict[str, Any]:
        """
        Parse runtime log output for expected signals.

        Args:
            config: Board config with expected_runtime_signals
            stdout: Standard output string to parse

        Returns:
            {"status": "pass"|"failed", "detected_signals": List[str], "missing_signals": List[str]}
        """
        expected_signals = config.get("expected_runtime_signals", [])
        detected: List[str] = []
        missing: List[str] = []

        for signal in expected_signals:
            label = signal.get("label", "")
            patterns = signal.get("patterns", [])

            found = False
            for pattern in patterns:
                if pattern in stdout:
                    found = True
                    break

            if found:
                detected.append(label)
            else:
                missing.append(label)

        return {
            "status": "pass" if not missing else "failed",
            "detected_signals": detected,
            "missing_signals": missing,
            "stdout_preview": stdout[:200] if stdout else "",
        }

    def read_serial_runtime(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Read runtime signals from serial port.

        Args:
            config: Board config with serial_port, baudrate, expected_runtime_signals

        Returns:
            {"status": "success"|"error"|"tool_missing", "observation": {...}, "stderr": str}
        """
        # Check if pyserial is available
        if importlib.util.find_spec("serial") is None:
            return {
                "status": "tool_missing",
                "observation": None,
                "stderr": "pyserial not installed. Install with: pip install pyserial",
            }

        try:
            import serial
        except ImportError:
            return {
                "status": "tool_missing",
                "observation": None,
                "stderr": "Failed to import pyserial",
            }

        serial_port = config.get("serial_port", "")
        baudrate = config.get("baudrate", 115200)
        timeout = config.get("serial_timeout_sec", 1.0)
        read_duration = config.get("runtime_read_seconds", 5.0)

        if not serial_port:
            return {
                "status": "error",
                "observation": None,
                "stderr": "No serial_port specified",
            }

        try:
            with serial.Serial(serial_port, baudrate, timeout=timeout) as ser:
                import time
                output_lines: List[str] = []
                start_time = time.time()

                while time.time() - start_time < read_duration:
                    if ser.in_waiting:
                        line = ser.readline().decode("utf-8", errors="ignore").strip()
                        if line:
                            output_lines.append(line)
                    time.sleep(0.01)

                stdout = "\n".join(output_lines)
                observation = self.parse_runtime_log(config, stdout)

                return {
                    "status": "success",
                    "observation": observation,
                    "stderr": "",
                }

        except serial.SerialException as e:
            return {
                "status": "error",
                "observation": None,
                "stderr": f"Serial error: {e}",
            }
        except Exception as e:
            return {
                "status": "error",
                "observation": None,
                "stderr": f"Unexpected error: {e}",
            }

    def save_profile(self, profile: BoardProfile, path: Optional[str] = None) -> bool:
        """Save a board profile to file."""
        try:
            if path is None:
                path = self.profiles_dir / f"{profile.name}.json"
            else:
                path = Path(path)

            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")
            return True
        except Exception:
            return False


__all__ = ["BoardProfile", "BoardProfileManager", "MISSING_BOARD_PROFILE"]
