"""Hardware domain module - Embedded target management."""

from .chips import HardwareChip
from .debug_probe import ProbeCapabilities, ProbeInfo
from .embedded_target import (
    # Enums
    BreakpointType,
    ChipFamily,
    CoreType,
    DebugInterface,
    DebugProbeType,
    FaultType,
    ResetMode,
    TargetState,
    Toolchain,
    # Data classes
    ChipDescription,
    CompatibilityResult,
    CrashInfo,
    EmbeddedTarget,
    FirmwareInfo,
    FirmwareVersion,
    GDBBreakpoint,
    GDBFrame,
    GDBRegister,
    IDCODE,
    MemoryRegion,
    StackFrame,
    # Interfaces
    ChipInterface,
    ProbeInterface,
)
from .gdb_client import GDBClient, GDBSession
from .serial_monitor import LogCapture, PatternMatch, SerialLine, SerialMonitor
from .target_registry import (
    AutoDetectResult,
    CompatibilityMatrix,
    FirmwareRegistry,
    TargetConfig,
    TargetRegistry,
    # Note: ChipDescription is in embedded_target.py
)

__all__ = [
    # Chips
    "HardwareChip",
    # Embedded Target
    "EmbeddedTarget",
    "ChipDescription",
    "ChipFamily",
    "CoreType",
    "TargetState",
    "TargetConfig",
    "TargetRegistry",
    "DebugProbeType",
    "DebugInterface",
    "ResetMode",
    "Toolchain",
    "BreakpointType",
    "FaultType",
    "IDCODE",
    "MemoryRegion",
    "FirmwareVersion",
    "FirmwareInfo",
    "FirmwareRegistry",
    "CompatibilityMatrix",
    "CompatibilityResult",
    # GDB
    "GDBClient",
    "GDBSession",
    "GDBFrame",
    "GDBBreakpoint",
    "GDBRegister",
    # Crash Analysis
    "CrashInfo",
    "StackFrame",
    # Serial Monitor
    "SerialMonitor",
    "SerialLine",
    "PatternMatch",
    "LogCapture",
    # Interfaces
    "ChipInterface",
    "ProbeInterface",
    # Probe
    "ProbeCapabilities",
    "ProbeInfo",
    # Auto-detect
    "AutoDetectResult",
]
