# Phase 6 - Embedded Target & Basic Debug

**Era 1 - Core Debug Loop**

## Overview

Phase 6 implements the foundation for embedded target management, enabling AI_SUPPORT to connect to, debug, and analyze ARM Cortex-M, RISC-V, ESP32, and other embedded targets.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    AI_SUPPORT Embedded Layer                         │
├─────────────────────────────────────────────────────────────────┤
│  EmbeddedTarget │ ChipFamily │ DebugProbe │ Toolchain            │
├─────────────────────────────────────────────────────────────────┤
│  TargetRegistry │ FirmwareVersion │ SVDParser │ GDBClient       │
├─────────────────────────────────────────────────────────────────┤
│  SerialMonitor │ CoreDumpParser │ HALQuery │ MemoryMap          │
├─────────────────────────────────────────────────────────────────┤
│                    Phase 5B Enterprise Runtime                      │
└─────────────────────────────────────────────────────────────────┘
```

## Core Models

### 1. EmbeddedTarget

Central model representing a debug target:

```python
from src.domain.hardware.embedded_target import (
    EmbeddedTarget,
    ChipFamily,
    DebugProbe,
    Toolchain,
    TargetState,
)

# STM32F407VG example
target = EmbeddedTarget(
    id="target-001",
    name="STM32F4 Discovery",
    chip_family=ChipFamily.STM32F4,
    debug_probe=DebugProbe.JLINK,
    toolchain=Toolchain.GCC_ARM,
    firmware=FirmwareVersion(
        version="1.2.3",
        git_hash="abc1234",
        build_timestamp="2024-01-15T10:30:00Z",
    ),
)
```

**States:** UNKNOWN → CONNECTED → HALTED → RUNNING → FAULT

### 2. ChipFamily Abstraction

Multi-chip support via protocol pattern:

```python
from src.domain.hardware.embedded_target import ChipFamily, ChipInterface

class ChipInterface(Protocol):
    """Protocol for chip-specific operations."""
    
    async def read_core_register(self, reg: str) -> int: ...
    async def write_core_register(self, reg: str, value: int) -> None: ...
    async def halt(self) -> None: ...
    async def resume(self) -> None: ...
    async def step(self) -> None: ...
    async def set_breakpoint(self, addr: int, bp_type: BreakpointType) -> int: ...
    async def read_memory(self, addr: int, size: int) -> bytes: ...
    async def write_memory(self, addr: int, data: bytes) -> None: ...

# Supported families
class STM32F4Chip:
    implements ChipInterface
    
    async def read_core_register(self, reg: str) -> int:
        # STM32F4 specific implementation
        ...
```

### 3. DebugProbe Interface

Unified interface for debug probes:

```python
from src.domain.hardware.embedded_target import (
    DebugProbe,
    ProbeInterface,
    IDCODE,
)

class ProbeInterface(Protocol):
    """Protocol for debug probe operations."""
    
    async def connect(self) -> IDCODE: ...
    async def disconnect(self) -> None: ...
    async def reset(self, mode: ResetMode) -> None: ...
    async def read_dp(self, addr: int) -> int: ...
    async def write_dp(self, addr: int, value: int) -> None: ...
    async def read_ap(self, addr: int) -> int: ...
    async def write_ap(self, addr: int, value: int) -> None: ...
    async def halt(self) -> None: ...
    async def resume(self) -> None: ...

# Supported probes
class JLinkProbe:
    implements ProbeInterface
    # SEGGER J-Link specific

class STLinkProbe:
    implements ProbeInterface
    # ST-Link/V2/V3 specific

class CMSISDAPProbe:
    implements ProbeInterface
    # CMSIS-DAP compatible
```

### 4. Target Registry

YAML-based configuration and auto-detection:

```yaml
# configs/targets/stm32f4-discovery.yaml
targets:
  - id: stm32f4-disc
    name: STM32F4 Discovery Kit
    chip:
      family: STM32F4
      part_number: STM32F407VGT6
      svd_file: STM32F407.svd
      memory_map:
        flash: 0x08000000-0x081FFFFF
        sram1: 0x20000000-0x2001FFFF
        sram2: 0x20020000-0x2003FFFF
    debug_probe:
      type: JLINK
      serial: "*"  # Auto-detect
      speed: 4000  # kHz
    toolchain:
      name: GCC_ARM
      prefix: arm-none-eabi-
      target: armv7em-none-eabihf
    probes:
      swd:
        io: PA13  # SWDIO
        clk: PA14  # SWCLK
      uart:
        tx: PA9
        rx: PA10
        baud: 115200
```

```python
from src.domain.hardware.target_registry import TargetRegistry

registry = TargetRegistry(config_dir="configs/targets")

# List all targets
targets = await registry.list_targets()

# Load by ID
target = await registry.load_target("stm32f4-disc")

# Auto-detect from connected probe
detected = await registry.auto_detect()
```

### 5. Firmware Versioning

Track firmware versions and compatibility:

```python
from src.domain.hardware.embedded_target import FirmwareVersion, CompatibilityMatrix

class CompatibilityMatrix:
    """Matrix of target ↔ firmware compatibility."""
    
    def check_compatible(
        self,
        target: ChipFamily,
        firmware_version: FirmwareVersion,
    ) -> CompatibilityResult:
        """Check if firmware is compatible with target."""
        ...

# Version schema
firmware = FirmwareVersion(
    version="1.2.3",           # Semantic version
    git_hash="abc1234",        # Git commit
    build_timestamp=datetime.now(),
    build_id="BUILD-2024-001",
    target_chip=ChipFamily.STM32F4,
    min_toolchain_version="10.3.1",
)
```

### 6. SVD Parser

ARM CMSIS-SVD file parser:

```python
from src.domain.hardware.svd_parser import SVDParser, SVDPeripheral, SVDRegister

class SVDParser:
    """Parse ARM CMSIS-SVD files."""
    
    def parse_file(self, path: Path) -> SVDDevice:
        """Parse SVD XML file."""
        ...
    
    def get_peripheral(self, name: str) -> SVDPeripheral:
        """Get peripheral by name."""
        ...
    
    def get_register(self, peripheral: str, register: str) -> SVDRegister:
        """Get register definition."""
        ...

# Usage
parser = SVDParser()
device = parser.parse_file("STM32F407.svd")

# Access parsed data
for peripheral in device.peripherals:
    print(f"{peripheral.name} @ 0x{peripheral.base_address:08X}")
    for reg in peripheral.registers:
        print(f"  {reg.name}: [{reg.offset:#06x}] {reg.width}bit")
```

### 7. GDB Client

GDB Remote Serial Protocol client:

```python
from src.domain.hardware.gdb_client import GDBClient, GDBBreakpoint, GDBRegister

class GDBClient:
    """GDB Remote Serial Protocol client."""
    
    async def connect(self, host: str, port: int) -> None:
        """Connect to GDB server."""
        ...
    
    async def read_registers(self) -> dict[str, int]:
        """Read all core registers."""
        ...
    
    async def read_register(self, name: str) -> int:
        """Read specific register."""
        ...
    
    async def write_register(self, name: str, value: int) -> None:
        """Write register."""
        ...
    
    async def read_memory(self, addr: int, length: int) -> bytes:
        """Read memory."""
        ...
    
    async def write_memory(self, addr: int, data: bytes) -> None:
        """Write memory."""
        ...
    
    async def set_breakpoint(self, addr: int, bp_type: str = "software") -> int:
        """Set breakpoint, returns breakpoint number."""
        ...
    
    async def remove_breakpoint(self, bp_num: int) -> None:
        """Remove breakpoint."""
        ...
    
    async def continue_(self) -> None:
        """Continue execution."""
        ...
    
    async def step(self) -> None:
        """Single step."""
        ...
    
    async def halt(self) -> None:
        """Halt execution."""
        ...
    
    async def backtrace(self) -> list[GDBFrame]:
        """Get backtrace."""
        ...
```

### 8. Serial Monitor

UART/serial port monitor:

```python
from src.domain.hardware.serial_monitor import SerialMonitor, SerialConfig

class SerialMonitor:
    """UART serial monitor."""
    
    async def connect(self, config: SerialConfig) -> None:
        """Connect to serial port."""
        ...
    
    async def disconnect(self) -> None:
        """Disconnect."""
        ...
    
    async def read_line(self, timeout: float = 1.0) -> str:
        """Read one line."""
        ...
    
    async def write(self, data: str) -> None:
        """Write to serial."""
        ...
    
    async def detect_baudrate(self) -> int:
        """Auto-detect baudrate."""
        ...
    
    def add_pattern_handler(
        self,
        pattern: str,
        callback: Callable[[str], None],
    ) -> None:
        """Add pattern match handler."""
        ...

# Usage
monitor = SerialMonitor()
await monitor.connect(SerialConfig(port="COM3", baudrate=115200))

# Pattern detection
monitor.add_pattern_handler(
    r"ERROR: (\w+)",
    lambda match: handle_error(match.group(1))
)
```

### 9. Core Dump Parser

ELF/Core dump analyzer:

```python
from src.domain.hardware.core_dump import CoreDumpParser, CrashInfo

class CoreDumpParser:
    """Parse ELF coredump files."""
    
    def parse_file(self, elf_path: Path) -> CrashInfo:
        """Parse ELF/core dump file."""
        ...
    
    def get_registers(self) -> dict[str, int]:
        """Get saved registers."""
        ...
    
    def get_stack_trace(self) -> list[StackFrame]:
        """Get stack trace."""
        ...
    
    def get_fault_address(self) -> int | None:
        """Get faulting address."""
        ...
    
    def get_fault_type(self) -> FaultType:
        """Determine fault type."""
        ...
```

### 10. HAL Query Tool

Query Hardware Abstraction Layer information:

```python
from src.domain.hardware.hal_query import HALQuery, PeripheralInfo

class HALQuery:
    """Query HAL information for target."""
    
    def __init__(self, target: EmbeddedTarget):
        self.target = target
        self.svd_cache: dict[str, SVDDevice] = {}
    
    async def get_peripheral_info(
        self,
        peripheral_name: str,
    ) -> PeripheralInfo:
        """Get peripheral information from SVD."""
        ...
    
    async def get_clock_config(self) -> ClockConfig:
        """Get clock configuration."""
        ...
    
    async def get_gpio_config(self, port: str) -> GPIOConfig:
        """Get GPIO configuration."""
        ...
    
    async def get_interrupt_vector(
        self,
        irq_number: int,
    ) -> InterruptInfo:
        """Get interrupt handler info."""
        ...
```

## File Structure

```
src/
├── domain/
│   └── hardware/
│       ├── embedded_target.py      # Core target models
│       ├── chip_family.py          # Chip abstraction
│       ├── debug_probe.py          # Probe interfaces
│       ├── target_registry.py      # YAML config loader
│       ├── firmware_version.py     # Version tracking
│       ├── svd_parser.py           # SVD parser (enhanced)
│       ├── gdb_client.py           # GDB RSP client
│       ├── serial_monitor.py       # UART monitor
│       ├── core_dump.py            # ELF/core parser
│       ├── hal_query.py            # HAL information
│       ├── memory_map.py           # Memory layout
│       └── __init__.py
│
├── infrastructure/
│   └── hardware/
│       ├── probes/                 # Probe implementations
│       │   ├── __init__.py
│       │   ├── jlink.py           # SEGGER J-Link
│       │   ├── stlink.py          # ST-Link
│       │   └── cmsis_dap.py       # CMSIS-DAP
│       ├── gdb/
│       │   ├── __init__.py
│       │   ├── rsp_client.py      # GDB Remote Serial Protocol
│       │   └── mi_parser.py       # GDB/MI output parser
│       └── serial/
│           ├── __init__.py
│           └── pyserial_adapter.py
│
└── application/
    └── workflows/
        └── debugging/
            ├── debug_session.py    # Debug workflow
            └── fault_analyzer.py   # Fault analysis

configs/
└── targets/
    ├── stm32f4-discovery.yaml
    ├── stm32h7-evb.yaml
    ├── esp32-devkit.yaml
    └── riscv-hifive1.yaml

tests/
├── unit/
│   ├── test_embedded_target.py
│   ├── test_target_registry.py
│   ├── test_svd_parser.py
│   ├── test_gdb_client.py
│   └── test_core_dump.py
└── integration/
    └── test_hardware_integration.py
```

## Configuration Schema

### Target Config (YAML)

```yaml
# configs/targets/template.yaml
target:
  id: unique-target-id
  name: Human readable name
  
  chip:
    family: STM32F4          # Chip family enum
    part_number: STM32F407VGT6
    svd_file: STM32F407.svd
    core: Cortex-M4         # ARM core type
    fpu: present             # FPU present
    dsp: present             # DSP present
    
  memory:
    flash:
      base: 0x08000000
      size: 0x100000         # 1MB
    sram:
      - base: 0x20000000
        size: 0x20000        # 128KB
        type: SRAM
      - base: 0x20020000
        size: 0x10000        # 64KB
        type: SRAM2
        
  debug_probe:
    type: JLINK             # JLINK, STLINK, CMSIS_DAP, OPENOCD
    interface: SWD          # SWD, JTAG
    speed: 4000             # kHz
    serial: "*"             # Serial number or * for any
    
  toolchain:
    name: GCC_ARM
    prefix: arm-none-eabi-
    objcopy: arm-none-eabi-objcopy
    gdb: arm-none-eabi-gdb
    
  serial:
    enabled: true
    port: COM3
    baudrate: 115200
    parity: none
    stopbits: 1
    
  firmware:
    elf_file: firmware.elf
    binary_file: firmware.bin
    flash_address: 0x08000000
```

## API Design

### REST Endpoints (Future Phase 10)

```
GET    /api/v1/targets                    # List all targets
GET    /api/v1/targets/{id}              # Get target info
POST   /api/v1/targets/auto-detect       # Auto-detect connected probe
POST   /api/v1/targets/{id}/connect      # Connect to target
POST   /api/v1/targets/{id}/disconnect   # Disconnect
POST   /api/v1/targets/{id}/reset        # Reset target

GET    /api/v1/targets/{id}/memory      # Read memory
POST   /api/v1/targets/{id}/memory      # Write memory
GET    /api/v1/targets/{id}/registers    # Read registers
GET    /api/v1/targets/{id}/backtrace    # Get backtrace
POST   /api/v1/targets/{id}/halt        # Halt execution
POST   /api/v1/targets/{id}/resume      # Resume execution

GET    /api/v1/targets/{id}/svd         # Get SVD info
GET    /api/v1/targets/{id}/hal/peripherals  # List peripherals
GET    /api/v1/targets/{id}/hal/peripherals/{name}

POST   /api/v1/targets/{id}/flash       # Flash firmware
GET    /api/v1/targets/{id}/flash/status # Flash status
```

### WebSocket Events

```python
# Debug session events
class DebugEvent(Enum):
    TARGET_CONNECTED = "target_connected"
    TARGET_DISCONNECTED = "target_disconnected"
    TARGET_HALTED = "target_halted"
    TARGET_RESUMED = "target_resumed"
    BREAKPOINT_HIT = "breakpoint_hit"
    WATCHPOINT_HIT = "watchpoint_hit"
    FAULT = "fault"
    SERIAL_OUTPUT = "serial_output"

# Event payload
{
    "event": "breakpoint_hit",
    "target_id": "stm32f4-disc",
    "data": {
        "breakpoint_id": 0,
        "address": 0x08000100,
        "reason": "breakpoint",
    }
}
```

## Dependencies

```toml
# pyproject.toml additions
dependencies = [
    # Hardware connectivity
    "pyocd>=0.35.0",           # CMSIS-DAP Python library
    "python-dotenv>=1.0.0",    # Config loading
    "pyyaml>=6.0",             # YAML parsing
    
    # Serial communication
    "pyserial>=3.5",           # Serial port access
    
    # ELF parsing
    "pyelftools>=0.29",        # ELF file parsing
    
    # SVD parsing
    "cmsis-svd>=0.5.1",        # ARM SVD file parser
]
```

## Done Criteria

- [x] EmbeddedTarget model with state machine
- [x] ChipFamily abstraction (protocol-based)
- [x] DebugProbe interface (JLink, STLink, CMSIS-DAP)
- [x] TargetRegistry with YAML config
- [x] FirmwareVersion tracking
- [x] SVD parser for ARM peripherals
- [x] GDB RSP client (basic operations)
- [x] Serial monitor with pattern detection
- [x] Core dump parser (ELF)
- [x] HAL query tool
- [x] Unit tests for core components
- [x] Integration tests (mock hardware)
- [x] Configuration examples for STM32F4

## Phase 6.1 - Enterprise Features

This section documents the enterprise-grade features required for multi-agent runtime, distributed workflows, and CI parallelism.

---

### 1. Target Lifecycle State Machine

**Status**: CRITICAL GAP

The current `TargetState` enum in `embedded_target.py` is incomplete. A proper state machine with guard validation is required.

```python
from enum import Enum, auto
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable


class TargetState(Enum):
    """Complete target lifecycle states."""
    
    # Discovery
    DISCOVERED = auto()      # Probe detected, awaiting connection
    CONNECTING = auto()      # Connection in progress
    
    # Connection lifecycle
    CONNECTED = auto()       # Debug probe connected
    HALTED = auto()          # CPU halted, debuggable
    RUNNING = auto()         # CPU running
    
    # Operation states
    FLASHING = auto()        # Flash programming in progress
    SNAPSHOTTING = auto()    # Snapshot capture in progress
    RESTORING = auto()       # Snapshot restore in progress
    
    # Terminal states
    DISCONNECTED = auto()    # Clean disconnection
    ERROR = auto()           # Error state


@dataclass
class IllegalTransitionError(Exception):
    """Raised when an illegal state transition is attempted."""
    
    current_state: TargetState
    attempted_state: TargetState
    allowed_states: list[TargetState]
    timestamp: datetime = field(default_factory=datetime.now)
    
    def __str__(self) -> str:
        return (
            f"Illegal transition: {self.current_state.name} -> {self.attempted_state.name}. "
            f"Allowed: {[s.name for s in self.allowed_states]}"
        )


@dataclass
class StateTransition:
    """Represents a state transition."""
    
    from_state: TargetState
    to_state: TargetState
    timestamp: datetime
    triggered_by: str  # user, system, workflow
    correlation_id: str | None = None


class TransitionGuard:
    """Guards state transitions with validation hooks.
    
    Prevents orchestration race conditions by ensuring:
    1. Valid transitions only
    2. Pre-transition hooks execute
    3. Post-transition hooks execute
    4. Transition logging for audit
    """
    
    def __init__(self) -> None:
        self._transitions: list[StateTransition] = []
        self._pre_hooks: dict[TargetState, list[Callable]] = {}
        self._post_hooks: dict[TargetState, list[Callable]] = {}
        self._lock = asyncio.Lock()
    
    def add_pre_hook(self, state: TargetState, hook: Callable) -> None:
        """Add pre-transition hook."""
        if state not in self._pre_hooks:
            self._pre_hooks[state] = []
        self._pre_hooks[state].append(hook)
    
    def add_post_hook(self, state: TargetState, hook: Callable) -> None:
        """Add post-transition hook."""
        if state not in self._post_hooks:
            self._post_hooks[state] = []
        self._post_hooks[state].append(hook)
    
    # State transition matrix
    TRANSITION_MATRIX: dict[TargetState, set[TargetState]] = {
        TargetState.DISCOVERED: {TargetState.CONNECTING, TargetState.DISCONNECTED},
        TargetState.CONNECTING: {TargetState.CONNECTED, TargetState.ERROR, TargetState.DISCONNECTED},
        TargetState.CONNECTED: {TargetState.HALTED, TargetState.RUNNING, TargetState.FLASHING, TargetState.ERROR, TargetState.DISCONNECTED},
        TargetState.HALTED: {TargetState.RUNNING, TargetState.CONNECTED, TargetState.FLASHING, TargetState.SNAPSHOTTING, TargetState.ERROR, TargetState.DISCONNECTED},
        TargetState.RUNNING: {TargetState.HALTED, TargetState.FAULT, TargetState.DISCONNECTED},
        TargetState.FLASHING: {TargetState.HALTED, TargetState.CONNECTED, TargetState.ERROR},
        TargetState.SNAPSHOTTING: {TargetState.HALTED, TargetState.CONNECTED, TargetState.ERROR},
        TargetState.RESTORING: {TargetState.HALTED, TargetState.CONNECTED, TargetState.ERROR},
        TargetState.ERROR: {TargetState.DISCONNECTED, TargetState.CONNECTING},
        TargetState.DISCONNECTED: {TargetState.DISCOVERED},
    }
    
    async def validate_and_transition(
        self,
        current: TargetState,
        target: TargetState,
        triggered_by: str = "system",
    ) -> TargetState:
        """Validate and execute state transition.
        
        Raises:
            IllegalTransitionError: If transition is not allowed
        """
        allowed = self.TRANSITION_MATRIX.get(current, set())
        
        if target not in allowed:
            raise IllegalTransitionError(
                current_state=current,
                attempted_state=target,
                allowed_states=list(allowed),
            )
        
        async with self._lock:
            # Execute pre-hooks
            for hook in self._pre_hooks.get(target, []):
                await hook(current, target)
            
            # Record transition
            self._transitions.append(StateTransition(
                from_state=current,
                to_state=target,
                timestamp=datetime.now(),
                triggered_by=triggered_by,
            ))
            
            # Execute post-hooks
            for hook in self._post_hooks.get(target, []):
                await hook(current, target)
        
        return target
    
    def get_transition_history(self) -> list[StateTransition]:
        """Get transition history for debugging."""
        return self._transitions.copy()
    
    def get_last_transition(self) -> StateTransition | None:
        """Get most recent transition."""
        return self._transitions[-1] if self._transitions else None
```

**Why this matters**: Without this, distributed runtime will have race conditions where multiple agents attempt conflicting operations (one trying to flash while another tries to snapshot).

---

### 2. Resource Ownership / Lease System

**Status**: REQUIRED for distributed runtime

Current implementation has basic locks, but distributed runtime needs lease-based resource management.

```python
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any
import uuid


class LeaseType(Enum):
    """Types of resource leases."""
    PROBE_LEASE = "probe"
    SESSION_LEASE = "session"
    TARGET_LEASE = "target"
    WORKFLOW_LEASE = "workflow"


@dataclass
class FencingToken:
    """Fencing token to prevent split-brain in distributed systems.
    
    When a resource owner fails and another node acquires the lease,
    the fencing token ensures the old owner cannot perform operations
    after its lease expires.
    """
    
    token_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    owner_id: str = ""
    sequence_number: int = 0
    issued_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=datetime.now)
    
    def is_valid(self) -> bool:
        """Check if token is still valid."""
        return datetime.now() < self.expires_at
    
    def increment_sequence(self) -> None:
        """Increment sequence for next fencing operation."""
        self.sequence_number += 1


@dataclass
class ProbeLease:
    """Lease for debug probe access.
    
    Ensures exclusive probe access in multi-agent/multi-node scenarios.
    """
    
    lease_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    probe_id: str = ""
    owner_id: str = ""  # agent_id or node_id
    session_id: str = ""
    
    acquired_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=datetime.now)
    last_renewed: datetime = field(default_factory=datetime.now)
    
    fencing_token: FencingToken | None = None
    
    max_lease_duration: timedelta = timedelta(minutes=30)
    auto_renew: bool = True
    renew_interval: timedelta = timedelta(minutes=5)
    
    def is_valid(self) -> bool:
        """Check if lease is still valid."""
        return datetime.now() < self.expires_at
    
    def renew(self, extend_by: timedelta | None = None) -> bool:
        """Renew the lease.
        
        Args:
            extend_by: Duration to extend (defaults to max_lease_duration)
        
        Returns:
            True if renewed successfully
        """
        if not self.is_valid():
            return False
        
        self.last_renewed = datetime.now()
        duration = extend_by or self.max_lease_duration
        self.expires_at = datetime.now() + duration
        
        if self.fencing_token:
            self.fencing_token.expires_at = self.expires_at
            self.fencing_token.increment_sequence()
        
        return True
    
    def revoke(self) -> None:
        """Revoke the lease immediately."""
        self.expires_at = datetime.now()


@dataclass
class SessionLease:
    """Lease for debug session access."""
    
    lease_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    owner_id: str = ""
    target_id: str = ""
    
    acquired_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    
    probe_lease: ProbeLease | None = None
    fencing_token: FencingToken | None = None
    
    max_idle_duration: timedelta = timedelta(minutes=10)
    
    def touch(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.now()
    
    def is_idle(self) -> bool:
        """Check if session is idle beyond threshold."""
        return datetime.now() - self.last_activity > self.max_idle_duration


@dataclass
class LeaseExpiration:
    """Event published when a lease expires."""
    
    lease_id: str
    lease_type: LeaseType
    owner_id: str
    expired_at: datetime = field(default_factory=datetime.now)
    reason: str = "expired"  # expired, revoked, released


class LeaseManager:
    """Manages resource leases with fencing tokens.
    
    Key features:
    - Atomic lease acquisition
    - Automatic renewal
    - Fencing token generation
    - Lease expiration handling
    """
    
    def __init__(self) -> None:
        self._probe_leases: dict[str, ProbeLease] = {}
        self._session_leases: dict[str, SessionLease] = {}
        self._lock = asyncio.Lock()
    
    async def acquire_probe_lease(
        self,
        probe_id: str,
        owner_id: str,
        session_id: str,
        duration: timedelta | None = None,
    ) -> ProbeLease | None:
        """Acquire exclusive probe lease.
        
        Returns:
            ProbeLease if acquired, None if probe already leased
        """
        async with self._lock:
            # Check if already leased
            existing = self._probe_leases.get(probe_id)
            if existing and existing.is_valid() and existing.owner_id != owner_id:
                return None  # Already leased by another owner
            
            lease = ProbeLease(
                probe_id=probe_id,
                owner_id=owner_id,
                session_id=session_id,
                expires_at=datetime.now() + (duration or ProbeLease().max_lease_duration),
                fencing_token=FencingToken(owner_id=owner_id),
            )
            self._probe_leases[probe_id] = lease
            return lease
    
    async def release_probe_lease(self, probe_id: str, owner_id: str) -> bool:
        """Release probe lease.
        
        Returns:
            True if released successfully
        """
        async with self._lock:
            lease = self._probe_leases.get(probe_id)
            if not lease:
                return False
            if lease.owner_id != owner_id:
                return False  # Not the owner
            
            lease.revoke()
            return True
    
    async def get_active_leases(self, lease_type: LeaseType) -> list[Any]:
        """Get all active leases of a type."""
        async with self._lock:
            if lease_type == LeaseType.PROBE_LEASE:
                return [l for l in self._probe_leases.values() if l.is_valid()]
            elif lease_type == LeaseType.SESSION_LEASE:
                return [l for l in self._session_leases.values() if l.is_valid()]
            return []
    
    async def cleanup_expired_leases(self) -> list[LeaseExpiration]:
        """Clean up expired leases and return expiration events."""
        expirations: list[LeaseExpiration] = []
        now = datetime.now()
        
        async with self._lock:
            for probe_id, lease in list(self._probe_leases.items()):
                if not lease.is_valid():
                    expirations.append(LeaseExpiration(
                        lease_id=lease.lease_id,
                        lease_type=LeaseType.PROBE_LEASE,
                        owner_id=lease.owner_id,
                    ))
                    del self._probe_leases[probe_id]
        
        return expirations
```

**Why this matters**: Multi-agent runtime, distributed workflows, and CI parallelism will corrupt state without proper lease management.

---

### 3. Temporal Replay System

**Status**: Missing timeline replay capability

Current snapshot system has capture/restore/diff, but lacks temporal replay functionality.

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ReplayMode(Enum):
    """Replay execution modes."""
    FORWARD = "forward"           # Play forward from A to B
    BACKWARD = "backward"        # Play backward (rarely used)
    STEP_FORWARD = "step_forward" # Single event forward
    STEP_BACKWARD = "step_backward"  # Single event backward
    TO_SNAPSHOT = "to_snapshot"  # Jump to specific snapshot


@dataclass
class ReplayCursor:
    """Cursor for navigating replay timeline.
    
    Tracks current position in the replay chain.
    """
    
    timeline_id: str
    current_snapshot_id: str | None = None
    current_event_index: int = 0
    
    mode: ReplayMode = ReplayMode.FORWARD
    speed: float = 1.0  # 1.0 = real-time, 2.0 = 2x speed
    
    is_playing: bool = False
    is_paused: bool = False
    
    loop_enabled: bool = False
    loop_start: int = 0
    loop_end: int = -1
    
    def step_forward(self, total_events: int) -> bool:
        """Move cursor forward one event."""
        if self.current_event_index < total_events - 1:
            self.current_event_index += 1
            return True
        elif self.loop_enabled and self.loop_end > self.loop_start:
            self.current_event_index = self.loop_start
            return True
        return False
    
    def step_backward(self) -> bool:
        """Move cursor backward one event."""
        if self.current_event_index > 0:
            self.current_event_index -= 1
            return True
        elif self.loop_enabled:
            self.current_event_index = self.loop_end if self.loop_end > 0 else 0
            return True
        return False
    
    def jump_to_snapshot(self, snapshot_id: str) -> None:
        """Jump to specific snapshot."""
        self.current_snapshot_id = snapshot_id
        self.current_event_index = 0


@dataclass
class TemporalEvent:
    """An event in the temporal replay sequence."""
    
    event_id: str
    event_index: int
    timestamp: datetime
    event_type: str  # register_change, memory_write, interrupt, etc.
    
    before_state: dict[str, Any]  # State before event
    after_state: dict[str, Any]   # State after event
    
    # Causality
    causes: list[str] = field(default_factory=list)   # Event IDs that caused this
    effects: list[str] = field(default_factory=list)  # Event IDs caused by this
    
    # Metadata
    duration_ns: int = 0  # Execution duration in nanoseconds
    is_deterministic: bool = True


@dataclass
class TemporalSnapshotChain:
    """Chain of snapshots with temporal ordering.
    
    Enables time-travel debugging by maintaining a linked list
    of snapshots with their temporal relationships.
    """
    
    chain_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    target_id: str = ""
    
    snapshots: list[str] = field(default_factory=list)  # Snapshot IDs in order
    events: list[TemporalEvent] = field(default_factory=list)  # Events between snapshots
    
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    
    # Metadata
    total_duration_ns: int = 0
    event_count: int = 0
    
    def get_snapshot_at_index(self, index: int) -> str | None:
        """Get snapshot ID at index."""
        if 0 <= index < len(self.snapshots):
            return self.snapshots[index]
        return None
    
    def get_events_between(
        self,
        start_index: int,
        end_index: int,
    ) -> list[TemporalEvent]:
        """Get all events between two snapshot indices."""
        return [
            e for e in self.events
            if start_index <= e.event_index < end_index
        ]
    
    def get_snapshot_index(self, snapshot_id: str) -> int | None:
        """Get index of snapshot in chain."""
        try:
            return self.snapshots.index(snapshot_id)
        except ValueError:
            return None
    
    def split_chain(self, at_index: int) -> tuple[TemporalSnapshotChain, TemporalSnapshotChain]:
        """Split chain at index, returning two sub-chains."""
        # First half
        chain1 = TemporalSnapshotChain(
            target_id=self.target_id,
            snapshots=self.snapshots[:at_index + 1],
            events=[e for e in self.events if e.event_index < at_index],
        )
        
        # Second half
        chain2 = TemporalSnapshotChain(
            target_id=self.target_id,
            snapshots=self.snapshots[at_index:],
            events=[e for e in self.events if e.event_index >= at_index],
        )
        
        return chain1, chain2


@dataclass
class ReplayTimeline:
    """Timeline for temporal replay.
    
    Manages replay sessions, cursor state, and playback control.
    """
    
    timeline_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    target_id: str = ""
    name: str = ""
    
    # Snapshot chain
    chain: TemporalSnapshotChain | None = None
    
    # Cursor state
    cursor: ReplayCursor | None = None
    
    # Playback state
    started_at: datetime | None = None
    ended_at: datetime | None = None
    
    # Replay configuration
    break_on_events: list[str] = field(default_factory=list)  # Event types to break on
    break_on_conditions: list[str] = field(default_factory=list)  # Python conditions
    
    # Annotations
    annotations: dict[int, str] = field(default_factory=dict)  # index -> annotation
    
    def play(self) -> None:
        """Start playback."""
        if self.cursor:
            self.cursor.is_playing = True
            self.cursor.is_paused = False
        self.started_at = datetime.now()
    
    def pause(self) -> None:
        """Pause playback."""
        if self.cursor:
            self.cursor.is_playing = False
            self.cursor.is_paused = True
    
    def stop(self) -> None:
        """Stop playback and reset cursor."""
        if self.cursor:
            self.cursor.is_playing = False
            self.cursor.is_paused = False
            self.cursor.current_event_index = 0
        self.ended_at = datetime.now()
    
    def seek_to_snapshot(self, snapshot_id: str) -> bool:
        """Seek to specific snapshot.
        
        Returns:
            True if snapshot found
        """
        if not self.chain or not self.cursor:
            return False
        
        index = self.chain.get_snapshot_index(snapshot_id)
        if index is not None:
            self.cursor.current_snapshot_id = snapshot_id
            self.cursor.current_event_index = index
            return True
        return False
    
    def get_current_state(self) -> dict[str, Any] | None:
        """Get current replay state."""
        if not self.chain or not self.cursor:
            return None
        
        current_snapshot = self.chain.get_snapshot_at_index(
            self.cursor.current_event_index
        )
        if not current_snapshot:
            return None
        
        # Reconstruct state by applying events up to cursor
        # This would load the snapshot and apply events
        return {"snapshot_id": current_snapshot}
    
    def add_annotation(self, event_index: int, annotation: str) -> None:
        """Add human-readable annotation at event index."""
        self.annotations[event_index] = annotation
    
    def export_annotations(self) -> dict[str, str]:
        """Export all annotations for display."""
        return {
            f"event_{idx}": ann
            for idx, ann in self.annotations.items()
        }


class ReplayController:
    """Controller for managing replay timelines.
    
    Provides high-level API for:
    - Creating replay sessions
    - Controlling playback
    - Managing breakpoints
    - Time-travel debugging
    """
    
    def __init__(self, snapshot_manager: Any) -> None:
        self._snapshot_manager = snapshot_manager
        self._timelines: dict[str, ReplayTimeline] = {}
        self._active_timeline: ReplayTimeline | None = None
    
    async def create_timeline(
        self,
        target_id: str,
        start_snapshot_id: str,
        end_snapshot_id: str,
        name: str = "",
    ) -> ReplayTimeline:
        """Create replay timeline between two snapshots.
        
        Args:
            target_id: Target ID
            start_snapshot_id: Starting snapshot
            end_snapshot_id: Ending snapshot
            name: Optional timeline name
        
        Returns:
            ReplayTimeline instance
        """
        # Load snapshots
        start_snap = await self._snapshot_manager.storage.load(start_snapshot_id)
        end_snap = await self._snapshot_manager.storage.load(end_snapshot_id)
        
        # Build chain
        chain = TemporalSnapshotChain(
            target_id=target_id,
            snapshots=[start_snapshot_id, end_snapshot_id],
        )
        
        # Create timeline
        timeline = ReplayTimeline(
            target_id=target_id,
            name=name,
            chain=chain,
            cursor=ReplayCursor(
                timeline_id=chain.chain_id,
                current_snapshot_id=start_snapshot_id,
            ),
        )
        
        self._timelines[timeline.timeline_id] = timeline
        return timeline
    
    async def replay_to(
        self,
        timeline_id: str,
        target_snapshot_id: str,
    ) -> bool:
        """Replay timeline to target snapshot.
        
        Returns:
            True if replay succeeded
        """
        timeline = self._timelines.get(timeline_id)
        if not timeline:
            return False
        
        return timeline.seek_to_snapshot(target_snapshot_id)
    
    def set_breakpoint(
        self,
        timeline_id: str,
        event_type: str | None = None,
        condition: str | None = None,
    ) -> None:
        """Set breakpoint in timeline."""
        timeline = self._timelines.get(timeline_id)
        if not timeline:
            return
        
        if event_type:
            timeline.break_on_events.append(event_type)
        if condition:
            timeline.break_on_conditions.append(condition)
    
    def get_active_timeline(self) -> ReplayTimeline | None:
        """Get currently active timeline."""
        return self._active_timeline
```

**Why this matters**: Time-travel debugging and replay semantics are essential for root-cause analysis in complex embedded systems.

---

### 4. Event Bus Delivery Semantics

**Status**: Contract undefined

Event bus needs explicit delivery guarantees for each event type.

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import Any


class DeliverySemantics(Enum):
    """Event delivery semantics.
    
    Defines guarantees for event delivery in the bus.
    """
    
    AT_LEAST_ONCE = "at_least_once"
    """Event may be delivered multiple times, but never lost.
    
    Use for: HardFaultDetected, CriticalError, SafetyEvent
    """
    
    EXACTLY_ONCE = "exactly_once"
    """Event delivered exactly once, with deduplication.
    
    Use for: SnapshotCaptured, SessionStarted, ConfigurationChanged
    """
    
    BEST_EFFORT = "best_effort"
    """Event delivered if possible, may be lost under load.
    
    Use for: MetricsUpdated, DebugLog, SerialOutput
    """


@dataclass
class DeliveryContract:
    """Contract defining delivery semantics for an event type."""
    
    event_type: str
    semantics: DeliverySemantics
    
    # Retry configuration (for at-least-once)
    max_retries: int = 3
    retry_delay_ms: int = 100
    
    # Deduplication (for exactly-once)
    deduplication_window_ms: int = 5000
    dedup_idempotency_key: str | None = None  # Field to use as key
    
    # Queue configuration
    queue_size: int = 1000
    overflow_policy: str = "drop_oldest"  # drop_oldest, drop_newest, block


# Event type to delivery contract mapping
STANDARD_DELIVERY_CONTRACTS: dict[str, DeliveryContract] = {
    # Critical events - at least once
    "target.fault": DeliveryContract(
        event_type="target.fault",
        semantics=DeliverySemantics.AT_LEAST_ONCE,
        max_retries=5,
        retry_delay_ms=200,
        queue_size=100,
    ),
    "hardfault.detected": DeliveryContract(
        event_type="hardfault.detected",
        semantics=DeliverySemantics.AT_LEAST_ONCE,
        max_retries=10,
        retry_delay_ms=100,
        queue_size=50,
    ),
    "watchdog.reset": DeliveryContract(
        event_type="watchdog.reset",
        semantics=DeliverySemantics.AT_LEAST_ONCE,
        max_retries=5,
        queue_size=100,
    ),
    
    # State events - exactly once
    "target.connected": DeliveryContract(
        event_type="target.connected",
        semantics=DeliverySemantics.EXACTLY_ONCE,
        deduplication_window_ms=10000,
        dedup_idempotency_key="correlation_id",
    ),
    "snapshot.captured": DeliveryContract(
        event_type="snapshot.captured",
        semantics=DeliverySemantics.EXACTLY_ONCE,
        deduplication_window_ms=5000,
        dedup_idempotency_key="snapshot_id",
    ),
    "session.started": DeliveryContract(
        event_type="session.started",
        semantics=DeliverySemantics.EXACTLY_ONCE,
        deduplication_window_ms=30000,
        dedup_idempotency_key="session_id",
    ),
    "capability.negotiated": DeliveryContract(
        event_type="capability.negotiated",
        semantics=DeliverySemantics.EXACTLY_ONCE,
        deduplication_window_ms=10000,
    ),
    
    # Best effort events
    "metrics.updated": DeliveryContract(
        event_type="metrics.updated",
        semantics=DeliverySemantics.BEST_EFFORT,
        queue_size=5000,
        overflow_policy="drop_oldest",
    ),
    "serial.output": DeliveryContract(
        event_type="serial.output",
        semantics=DeliverySemantics.BEST_EFFORT,
        queue_size=10000,
        overflow_policy="drop_oldest",
    ),
    "debug.log": DeliveryContract(
        event_type="debug.log",
        semantics=DeliverySemantics.BEST_EFFORT,
        queue_size=10000,
        overflow_policy="drop_oldest",
    ),
    "target.resumed": DeliveryContract(
        event_type="target.resumed",
        semantics=DeliverySemantics.BEST_EFFORT,
        queue_size=500,
    ),
}


@dataclass
class DeliveryStatus:
    """Status of event delivery attempt."""
    
    event_id: str
    delivery_semantics: DeliverySemantics
    
    attempts: int = 0
    delivered: bool = False
    delivered_at: datetime | None = None
    
    dedup_checked: bool = False
    was_duplicate: bool = False
    
    retries_exhausted: bool = False
    final_error: str | None = None
    
    # Latency tracking
    publish_latency_ms: float = 0.0
    total_latency_ms: float = 0.0


class DeliveryAwareEventBus:
    """Event bus with explicit delivery semantics.
    
    Extends AsyncEventBus with:
    - Delivery contract enforcement
    - Deduplication
    - Retry logic
    - Latency tracking
    """
    
    def __init__(
        self,
        base_bus: AsyncEventBus,
        contracts: dict[str, DeliveryContract] | None = None,
    ) -> None:
        self._base_bus = base_bus
        self._contracts = contracts or STANDARD_DELIVERY_CONTRACTS
        self._dedup_cache: dict[str, datetime] = {}
        self._delivery_history: dict[str, DeliveryStatus] = {}
    
    def _get_contract(self, event_type: str) -> DeliveryContract:
        """Get delivery contract for event type."""
        return self._contracts.get(
            event_type,
            DeliveryContract(
                event_type=event_type,
                semantics=DeliverySemantics.BEST_EFFORT,
            ),
        )
    
    def _is_duplicate(self, event: DomainEvent, contract: DeliveryContract) -> bool:
        """Check if event is a duplicate."""
        if contract.dedup_idempotency_key:
            key = getattr(event, contract.dedup_idempotency_key, None)
            if key:
                dedup_key = f"{event.event_type}:{key}"
                
                if dedup_key in self._dedup_cache:
                    age = datetime.now() - self._dedup_cache[dedup_key]
                    if age.total_seconds() * 1000 < contract.deduplication_window_ms:
                        return True
                
                self._dedup_cache[dedup_key] = datetime.now()
        
        return False
    
    async def publish(
        self,
        event: DomainEvent,
        override_semantics: DeliverySemantics | None = None,
    ) -> DeliveryStatus:
        """Publish event with delivery semantics.
        
        Returns:
            DeliveryStatus with delivery result
        """
        contract = self._get_contract(event.event_type)
        if override_semantics:
            contract.semantics = override_semantics
        
        status = DeliveryStatus(
            event_id=event.event_id,
            delivery_semantics=contract.semantics,
        )
        
        publish_start = datetime.now()
        
        # Handle exactly-once with deduplication
        if contract.semantics == DeliverySemantics.EXACTLY_ONCE:
            if self._is_duplicate(event, contract):
                status.dedup_checked = True
                status.was_duplicate = True
                status.delivered = True
                status.delivered_at = datetime.now()
                self._delivery_history[event.event_id] = status
                return status
        
        # Publish with retries for at-least-once
        if contract.semantics == DeliverySemantics.AT_LEAST_ONCE:
            for attempt in range(contract.max_retries):
                status.attempts = attempt + 1
                try:
                    await self._base_bus.publish(event)
                    status.delivered = True
                    status.delivered_at = datetime.now()
                    break
                except Exception as e:
                    if attempt == contract.max_retries - 1:
                        status.retries_exhausted = True
                        status.final_error = str(e)
                    else:
                        await asyncio.sleep(contract.retry_delay_ms / 1000)
        else:
            # Best effort or exactly-once without dedup
            try:
                await self._base_bus.publish(event)
                status.delivered = True
                status.delivered_at = datetime.now()
            except Exception as e:
                status.final_error = str(e)
        
        status.publish_latency_ms = (
            datetime.now() - publish_start
        ).total_seconds() * 1000
        status.total_latency_ms = status.publish_latency_ms
        
        self._delivery_history[event.event_id] = status
        return status
    
    def get_delivery_status(self, event_id: str) -> DeliveryStatus | None:
        """Get delivery status for an event."""
        return self._delivery_history.get(event_id)
    
    def get_delivery_metrics(self) -> dict[str, Any]:
        """Get delivery metrics."""
        total = len(self._delivery_history)
        delivered = sum(1 for s in self._delivery_history.values() if s.delivered)
        duplicates = sum(1 for s in self._delivery_history.values() if s.was_duplicate)
        retries_exhausted = sum(
            1 for s in self._delivery_history.values() if s.retries_exhausted
        )
        
        return {
            "total_events": total,
            "delivered": delivered,
            "failed": total - delivered,
            "duplicates": duplicates,
            "retries_exhausted": retries_exhausted,
            "delivery_rate": delivered / total if total > 0 else 0,
        }
```

---

### 5. Runtime Coordinator

**Status**: Missing for multi-probe/multi-target scenarios

Required for coordinating multiple probes, targets, workflows, and agents.

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
import asyncio


class CoordinatorState(Enum):
    """Coordinator operational states."""
    IDLE = "idle"
    COORDINATING = "coordinating"
    DEGRADED = "degraded"
    ERROR = "error"


@dataclass
class ResourcePoolConfig:
    """Configuration for resource pools."""
    
    min_size: int = 1
    max_size: int = 10
    idle_timeout_seconds: int = 300
    health_check_interval_seconds: int = 60
    auto_scale: bool = True


@dataclass
class ProbeResource:
    """Represents a probe resource in the pool."""
    
    probe_id: str
    probe_type: str
    state: str = "available"  # available, allocated, error, offline
    
    current_owner: str | None = None  # session_id or agent_id
    allocated_at: datetime | None = None
    
    # Health metrics
    last_health_check: datetime = field(default_factory=datetime.now)
    health_score: float = 1.0
    error_count: int = 0
    
    # Capabilities
    supports_swd: bool = True
    supports_jtag: bool = False
    max_speed_khz: int = 10000


@dataclass
class ProbePool:
    """Pool of debug probe resources.
    
    Manages probe allocation, health, and scaling.
    """
    
    config: ResourcePoolConfig
    resources: dict[str, ProbeResource] = field(default_factory=dict)
    
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    
    async def acquire(
        self,
        required_capabilities: dict[str, bool] | None = None,
        preferred_owner: str | None = None,
    ) -> ProbeResource | None:
        """Acquire a probe from the pool.
        
        Args:
            required_capabilities: Required probe capabilities
            preferred_owner: Prefer probes previously used by this owner
        
        Returns:
            ProbeResource if available, None otherwise
        """
        async with self._lock:
            # Find available probes
            candidates = [
                r for r in self.resources.values()
                if r.state == "available"
            ]
            
            if not candidates:
                # Try to scale up
                if len(self.resources) < self.config.max_size:
                    # Would need to initialize new probe
                    pass
                return None
            
            # Filter by capabilities
            if required_capabilities:
                candidates = [
                    r for r in candidates
                    if all(getattr(r, k, False) == v for k, v in required_capabilities.items())
                ]
            
            # Prefer previously used probes
            if preferred_owner:
                candidates.sort(
                    key=lambda r: r.current_owner == preferred_owner,
                    reverse=True,
                )
            
            if candidates:
                probe = candidates[0]
                probe.state = "allocated"
                probe.current_owner = preferred_owner
                probe.allocated_at = datetime.now()
                return probe
            
            return None
    
    async def release(self, probe_id: str) -> bool:
        """Release a probe back to the pool."""
        async with self._lock:
            probe = self.resources.get(probe_id)
            if not probe:
                return False
            
            probe.state = "available"
            probe.current_owner = None
            probe.allocated_at = None
            return True
    
    async def mark_unhealthy(self, probe_id: str, error: str) -> None:
        """Mark probe as unhealthy."""
        async with self._lock:
            probe = self.resources.get(probe_id)
            if probe:
                probe.state = "error"
                probe.error_count += 1
                probe.health_score = max(0, probe.health_score - 0.2)
    
    def get_pool_status(self) -> dict[str, Any]:
        """Get pool status metrics."""
        total = len(self.resources)
        available = sum(1 for r in self.resources.values() if r.state == "available")
        allocated = sum(1 for r in self.resources.values() if r.state == "allocated")
        error = sum(1 for r in self.resources.values() if r.state == "error")
        
        avg_health = (
            sum(r.health_score for r in self.resources.values()) / total
            if total > 0 else 0
        )
        
        return {
            "total_probes": total,
            "available": available,
            "allocated": allocated,
            "error": error,
            "average_health": avg_health,
        }


@dataclass
class TargetScheduler:
    """Scheduler for target operations.
    
    Coordinates target access across multiple agents and workflows.
    """
    
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _scheduled_tasks: dict[str, dict[str, Any]] = field(default_factory=dict)
    
    async def schedule_operation(
        self,
        target_id: str,
        operation: str,
        requested_by: str,  # agent_id
        priority: int = 0,  # Higher = more priority
        estimated_duration_ms: int = 1000,
    ) -> str | None:
        """Schedule an operation on a target.
        
        Returns:
            Task ID if scheduled, None if conflict
        """
        async with self._lock:
            # Check for conflicts
            existing = self._get_active_operations(target_id)
            if existing:
                # Check priority
                if existing["priority"] >= priority:
                    return None  # Blocked by higher/equal priority
            
            task_id = str(uuid.uuid4())
            self._scheduled_tasks[task_id] = {
                "target_id": target_id,
                "operation": operation,
                "requested_by": requested_by,
                "priority": priority,
                "estimated_duration_ms": estimated_duration_ms,
                "scheduled_at": datetime.now(),
                "started_at": None,
                "completed_at": None,
                "state": "pending",
            }
            return task_id
    
    def _get_active_operations(self, target_id: str) -> dict[str, Any] | None:
        """Get active operation for target."""
        for task in self._scheduled_tasks.values():
            if task["target_id"] == target_id and task["state"] in ("pending", "running"):
                return task
        return None
    
    async def start_operation(self, task_id: str) -> bool:
        """Mark operation as started."""
        async with self._lock:
            task = self._scheduled_tasks.get(task_id)
            if task and task["state"] == "pending":
                task["state"] = "running"
                task["started_at"] = datetime.now()
                return True
            return False
    
    async def complete_operation(self, task_id: str) -> bool:
        """Mark operation as completed."""
        async with self._lock:
            task = self._scheduled_tasks.get(task_id)
            if task and task["state"] == "running":
                task["state"] = "completed"
                task["completed_at"] = datetime.now()
                return True
            return False
    
    def get_target_schedule(self, target_id: str) -> list[dict[str, Any]]:
        """Get schedule for a target."""
        return [
            t for t in self._scheduled_tasks.values()
            if t["target_id"] == target_id
        ]


@dataclass
class ExecutionCoordinator:
    """Coordinates execution across multiple probes, targets, and agents.
    
    Top-level coordinator that manages:
    - Probe pools
    - Target schedulers
    - Agent session coordination
    - Distributed lock management
    """
    
    coordinator_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: CoordinatorState = CoordinatorState.IDLE
    
    probe_pools: dict[str, ProbePool] = field(default_factory=dict)
    target_schedulers: dict[str, TargetScheduler] = field(default_factory=dict)
    
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    
    async def register_probe_pool(
        self,
        pool_id: str,
        config: ResourcePoolConfig,
    ) -> ProbePool:
        """Register a probe pool."""
        pool = ProbePool(config=config)
        self.probe_pools[pool_id] = pool
        return pool
    
    async def get_probe(
        self,
        pool_id: str,
        required_capabilities: dict[str, bool] | None = None,
        owner: str | None = None,
    ) -> ProbeResource | None:
        """Get a probe from specified pool."""
        pool = self.probe_pools.get(pool_id)
        if not pool:
            return None
        return await pool.acquire(required_capabilities, owner)
    
    async def release_probe(self, pool_id: str, probe_id: str) -> bool:
        """Release probe back to pool."""
        pool = self.probe_pools.get(pool_id)
        if not pool:
            return False
        return await pool.release(probe_id)
    
    def get_coordinator_status(self) -> dict[str, Any]:
        """Get overall coordinator status."""
        pool_statuses = {
            pid: pool.get_pool_status()
            for pid, pool in self.probe_pools.items()
        }
        
        return {
            "coordinator_id": self.coordinator_id,
            "state": self.state.value,
            "probe_pools": pool_statuses,
            "target_schedulers_count": len(self.target_schedulers),
        }
```

---

### 6. Hardened Plugin Sandbox

**Status**: Timeout + subprocess insufficient

Production-grade sandboxing requires additional hardening.

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import resource
import os


class SyscallPolicy(Enum):
    """Allowed syscall policies."""
    
    MINIMAL = "minimal"       # Only essential syscalls
    STANDARD = "standard"     # Standard operations
    RELAXED = "relaxed"       # More permissive


@dataclass
class SandboxPolicy:
    """Production-grade sandbox policy.
    
    Defines security boundaries for plugin execution.
    """
    
    # Timeout
    timeout_seconds: float = 5.0
    hard_timeout_seconds: float = 30.0  # Force kill after this
    
    # Memory limits
    memory_limit_mb: int = 256
    memory_swap_mb: int = 0  # Disable swap
    memory_stack_mb: int = 8
    
    # CPU limits
    cpu_time_limit_seconds: float = 10.0
    cpu_affinity: list[int] | None = None  # Pin to specific cores
    
    # Process isolation
    enable_process_isolation: bool = True
    isolate_network: bool = True
    isolate_filesystem: bool = True
    readonly_filesystem_paths: list[str] = field(default_factory=list)
    
    # Syscall restrictions
    syscall_policy: SyscallPolicy = SyscallPolicy.MINIMAL
    allowed_syscalls: list[str] = field(default_factory=list)
    denied_syscalls: list[str] = field(default_factory=list)
    
    # Seccomp (Linux)
    enable_seccomp: bool = True
    seccomp_profile: str | None = None  # Path to seccomp profile
    
    # cgroup (Linux)
    enable_cgroup: bool = True
    cgroup_memory_limit_mb: int = 256
    cgroup_cpu_quota_percent: int = 50  # 50% CPU limit
    cgroup_tasks_limit: int = 10
    
    # IPC restrictions
    disable_sysv_ipc: bool = True
    disable_posix_mq: bool = True
    disable_shm: bool = True
    
    # Environment
    clear_environment: bool = True
    allowed_env_vars: list[str] = field(default_factory=list)
    
    # Capabilities (Linux)
    drop_capabilities: bool = True
    keep_capabilities: list[str] = field(default_factory=list)  # CAP_NET_RAW, etc.
    
    # File descriptor limits
    max_open_files: int = 64
    max_file_size_mb: int = 10
    
    # Network
    allowed_networks: list[str] = field(default_factory=list)  # IPs or CIDRs
    allowed_ports: list[int] = field(default_factory=list)  # e.g., [80, 443]


class HardenedSandbox:
    """Hardened sandbox for plugin execution.
    
    Applies multiple layers of security:
    1. Linux namespaces (process isolation)
    2. seccomp (syscall filtering)
    3. cgroup (resource limits)
    4. AppArmor/SELinux (optional)
    5. Capability dropping
    """
    
    def __init__(self, policy: SandboxPolicy | None = None) -> None:
        self._policy = policy or SandboxPolicy()
    
    def _get_minimal_syscalls(self) -> list[str]:
        """Get minimal allowed syscalls for embedded plugins."""
        return [
            # Process
            "exit", "exit_group", "brk", "mmap", "munmap", "mprotect",
            # Thread
            "clone", "wait4", "prctl", "prlimit64",
            # Memory
            "read", "write", "readlink", "dup", "dup2",
            # Time
            "clock_gettime", "gettimeofday", "nanosleep",
            # Futex (for async operations)
            "futex",
            # Signal
            "rt_sigaction", "rt_sigreturn", "rt_sigprocmask",
        ]
    
    def _get_standard_syscalls(self) -> list[str]:
        """Get standard allowed syscalls."""
        minimal = set(self._get_minimal_syscalls())
        standard = minimal | {
            # File
            "open", "openat", "close", "fstat", "stat", "lseek",
            "ftruncate", "fsync", "fdatasync",
            # Network (if allowed)
            "socket", "connect", "accept", "bind", "listen",
            "send", "recv", "sendto", "recvfrom",
            # Memory mapped files
            "msync", "madvise",
            # Info
            "uname", "getuid", "getgid", "geteuid", "getegid",
            "getpid", "getppid", "gettid",
        }
        return list(standard)
    
    def _apply_resource_limits(self) -> None:
        """Apply resource limits using resource module."""
        limits = self._policy
        
        # Memory limits
        if limits.memory_limit_mb:
            resource.setrlimit(
                resource.RLIMIT_AS,
                (limits.memory_limit_mb * 1024 * 1024, limits.memory_limit_mb * 1024 * 1024),
            )
        
        # Stack size
        if limits.memory_stack_mb:
            resource.setrlimit(
                resource.RLIMIT_STACK,
                (limits.memory_stack_mb * 1024 * 1024, limits.memory_stack_mb * 1024 * 1024),
            )
        
        # CPU time
        if limits.cpu_time_limit_seconds:
            resource.setrlimit(
                resource.RLIMIT_CPU,
                (int(limits.cpu_time_limit_seconds), int(limits.cpu_time_limit_seconds) + 1),
            )
        
        # File size
        if limits.max_file_size_mb:
            resource.setrlimit(
                resource.RLIMIT_FSIZE,
                (limits.max_file_size_mb * 1024 * 1024, limits.max_file_size_mb * 1024 * 1024),
            )
        
        # Open files
        if limits.max_open_files:
            resource.setrlimit(
                resource.RLIMIT_NOFILE,
                (limits.max_open_files, limits.max_open_files),
            )
    
    def _generate_seccomp_filter(self) -> list[dict[str, Any]]:
        """Generate seccomp filter rules."""
        policy = self._policy
        
        if policy.syscall_policy == SyscallPolicy.MINIMAL:
            allowed = set(self._get_minimal_syscalls())
        else:
            allowed = set(self._get_standard_syscalls())
        
        # Add explicit allows
        for syscall in policy.allowed_syscalls:
            allowed.add(syscall)
        
        # Remove explicit denials
        for syscall in policy.denied_syscalls:
            allowed.discard(syscall)
        
        # Convert to seccomp format
        rules = [{"syscall": s, "action": "ALLOW"} for s in sorted(allowed)]
        rules.append({"action": "KILL"})  # Default deny
        
        return rules
    
    async def execute_in_sandbox(
        self,
        plugin_name: str,
        func: Callable[..., Awaitable[Any]],
        *args,
        **kwargs,
    ) -> Any:
        """Execute function in hardened sandbox.
        
        On Linux, applies full security stack.
        On other platforms, falls back to resource limits.
        """
        # Apply resource limits (cross-platform)
        self._apply_resource_limits()
        
        # On Linux, would use prctl + seccomp
        if os.uname().sysname == "Linux" and self._policy.enable_seccomp:
            # Would load seccomp filter here
            # Using libseccomp or plain seccomp syscall
            pass
        
        # Execute with timeout
        try:
            return await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=self._policy.timeout_seconds,
            )
        except asyncio.TimeoutError:
            raise PluginTimeoutError(
                plugin_name=plugin_name,
                operation=func.__name__,
                timeout_seconds=self._policy.timeout_seconds,
            )
```

---

### 7. Enhanced Fault Propagation

**Status**: Static propagation, needs probabilistic reasoning

Current implementation uses static rules. AI runtime needs probabilistic propagation.

```python
from dataclasses import dataclass, field
from typing import Any
import random


@dataclass
class PropagationEdge:
    """Edge in fault propagation graph with probabilistic properties.
    
    Represents a causal relationship with:
    - Probability of propagation
    - Confidence score (based on evidence)
    - Latency (time for fault to propagate)
    """
    
    source_id: str
    target_id: str
    
    # Propagation probability (0.0 - 1.0)
    probability: float = 1.0
    
    # Confidence in this edge (0.0 - 1.0)
    confidence: float = 1.0
    
    # Propagation latency in ms
    latency_ms: float = 0.0
    
    # Conditions for propagation
    required_conditions: list[str] = field(default_factory=list)
    
    # Evidence supporting this edge
    evidence: list[str] = field(default_factory=list)
    
    # Statistical data
    observed_count: int = 0
    propagation_count: int = 0
    
    @property
    def empirical_probability(self) -> float:
        """Calculate empirical probability from observations."""
        if self.observed_count == 0:
            return self.probability  # Use prior
        return self.propagation_count / self.observed_count
    
    @property
    def bayesian_confidence(self) -> float:
        """Calculate Bayesian confidence score."""
        # Beta distribution posterior mean with uniform prior
        alpha = self.propagation_count + 1
        beta = self.observed_count - self.propagation_count + 1
        return alpha / (alpha + beta)
    
    def record_observation(self, propagated: bool) -> None:
        """Record observation to update statistics."""
        self.observed_count += 1
        if propagated:
            self.propagation_count += 1
        # Update confidence using running average
        self.confidence = (
            self.confidence * 0.9 +
            (self.bayesian_confidence if propagated else 1 - self.bayesian_confidence) * 0.1
        )


@dataclass
class FaultHypothesis:
    """A hypothesis about fault causality.
    
    Generated by inference algorithms.
    """
    
    hypothesis_id: str
    root_cause_id: str
    
    # Probability this is the root cause
    probability: float
    
    # Confidence in this hypothesis
    confidence: float
    
    # Supporting evidence
    supporting_evidence: list[str] = field(default_factory=list)
    
    # Explains these observed symptoms
    explains_symptoms: list[str] = field(default_factory=list)
    
    # Path through propagation graph
    propagation_path: list[str] = field(default_factory=list)
    
    # Likelihood given evidence
    likelihood: float = 1.0
    
    def posterior_probability(self) -> float:
        """Calculate posterior probability using Bayes theorem."""
        prior = self.probability
        return prior * self.likelihood


class ProbabilisticFaultPropagationGraph:
    """Fault propagation graph with probabilistic inference.
    
    Extends FaultPropagationGraph with:
    - Probabilistic edge weights
    - Bayesian confidence scoring
    - Causal inference
    - Evidence-based reasoning
    """
    
    def __init__(self) -> None:
        super().__init__()
        self._probabilistic_edges: dict[str, list[PropagationEdge]] = {}
    
    def add_probabilistic_edge(
        self,
        source_id: str,
        target_id: str,
        probability: float = 1.0,
        confidence: float = 1.0,
        latency_ms: float = 0.0,
    ) -> PropagationEdge:
        """Add edge with probability."""
        edge = PropagationEdge(
            source_id=source_id,
            target_id=target_id,
            probability=probability,
            confidence=confidence,
            latency_ms=latency_ms,
        )
        
        if source_id not in self._probabilistic_edges:
            self._probabilistic_edges[source_id] = []
        self._probabilistic_edges[source_id].append(edge)
        
        return edge
    
    def get_propagation_probability(
        self,
        source_id: str,
        target_id: str,
        evidence: dict[str, Any] | None = None,
    ) -> float:
        """Calculate probability of propagation from source to target.
        
        Args:
            source_id: Source node
            target_id: Target node
            evidence: Observed evidence to condition on
        
        Returns:
            Probability of propagation
        """
        edges = self._probabilistic_edges.get(source_id, [])
        for edge in edges:
            if edge.target_id == target_id:
                # Adjust probability based on conditions
                if evidence:
                    prob = self._adjust_probability_for_evidence(edge, evidence)
                else:
                    prob = edge.empirical_probability
                return prob * edge.confidence
        return 0.0
    
    def _adjust_probability_for_evidence(
        self,
        edge: PropagationEdge,
        evidence: dict[str, Any],
    ) -> float:
        """Adjust edge probability based on evidence."""
        prob = edge.empirical_probability
        
        # Check required conditions
        for condition in edge.required_conditions:
            if condition in evidence:
                if not evidence[condition]:
                    prob *= 0.1  # Condition not met
        
        return min(1.0, prob)
    
    def infer_root_cause(
        self,
        observed_symptoms: list[str],
        max_hypotheses: int = 10,
    ) -> list[FaultHypothesis]:
        """Infer most likely root causes given symptoms.
        
        Uses causal inference to generate hypotheses.
        
        Args:
            observed_symptoms: List of observed symptoms
            max_hypotheses: Maximum hypotheses to return
        
        Returns:
            List of hypotheses sorted by posterior probability
        """
        hypotheses: list[FaultHypothesis] = []
        
        # Find nodes that could explain symptoms
        for node_id, node in self._nodes.items():
            symptom_matches = sum(1 for s in observed_symptoms if s in node.symptoms)
            
            if symptom_matches == 0:
                continue
            
            # Find root causes that could lead to this node
            root_causes = self.get_root_causes(node_id)
            
            for root in root_causes:
                # Calculate probability
                path = self.get_propagation_path(root.node_id, node_id)
                if not path:
                    continue
                
                # Multiply probabilities along path
                prob = 1.0
                for i in range(len(path) - 1):
                    prob *= self.get_propagation_probability(path[i], path[i + 1])
                
                hypothesis = FaultHypothesis(
                    hypothesis_id=str(uuid.uuid4()),
                    root_cause_id=root.node_id,
                    probability=prob,
                    confidence=self._calculate_path_confidence(path),
                    explains_symptoms=observed_symptoms,
                    propagation_path=path,
                )
                hypotheses.append(hypothesis)
        
        # Sort by posterior probability
        hypotheses.sort(key=lambda h: h.posterior_probability(), reverse=True)
        return hypotheses[:max_hypotheses]
    
    def _calculate_path_confidence(self, path: list[str]) -> float:
        """Calculate confidence in a propagation path."""
        if len(path) < 2:
            return 1.0
        
        confidences = []
        for i in range(len(path) - 1):
            edges = self._probabilistic_edges.get(path[i], [])
            for edge in edges:
                if edge.target_id == path[i + 1]:
                    confidences.append(edge.confidence)
                    break
        
        if not confidences:
            return 0.5
        
        # Geometric mean of confidences
        product = 1.0
        for c in confidences:
            product *= c
        return product ** (1.0 / len(confidences))
    
    def update_from_observation(
        self,
        source_id: str,
        target_id: str,
        propagated: bool,
    ) -> None:
        """Update edge statistics from observation."""
        edges = self._probabilistic_edges.get(source_id, [])
        for edge in edges:
            if edge.target_id == target_id:
                edge.record_observation(propagated)
                break
```

---

### 8. Policy Engine

**Status**: Missing - critical for security

Determines what operations are allowed based on policies.

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class PolicyEffect(Enum):
    """Policy evaluation effects."""
    
    ALLOW = "allow"
    DENY = "deny"
    CONDITIONAL = "conditional"  # Depends on conditions
    AUDIT = "audit"  # Log but don't block


@dataclass
class PolicyContext:
    """Context for policy evaluation."""
    
    # Subject (who)
    subject_id: str = ""  # user_id or agent_id
    subject_type: str = "agent"  # user, agent, system
    subject_roles: list[str] = field(default_factory=list)
    subject_trust_level: float = 1.0  # 0.0 - 1.0
    
    # Resource (what)
    resource_type: str = ""  # target, probe, snapshot, firmware
    resource_id: str = ""
    resource_owner: str = ""
    
    # Action (what operation)
    action: str = ""  # flash, read_memory, restore_snapshot, etc.
    action_parameters: dict[str, Any] = field(default_factory=dict)
    
    # Environment (where/when)
    environment: str = "production"  # production, development, ci
    session_id: str = ""
    workflow_id: str = ""
    
    # Time
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Additional metadata
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyRule:
    """A policy rule for evaluation."""
    
    rule_id: str
    name: str
    description: str = ""
    
    # Matching
    subjects: list[str] = field(default_factory=list)  # Subject patterns
    resources: list[str] = field(default_factory=list)  # Resource patterns
    actions: list[str] = field(default_factory=list)   # Action patterns
    
    # Effect
    effect: PolicyEffect = PolicyEffect.DENY
    
    # Conditions (Python expression evaluated with context)
    conditions: list[str] = field(default_factory=list)
    
    # Priority (higher = evaluated first)
    priority: int = 0
    
    # Audit
    audit_enabled: bool = True
    audit_message: str = ""
    
    def evaluate(self, context: PolicyContext) -> PolicyEffect:
        """Evaluate policy against context.
        
        Returns:
            PolicyEffect for this rule
        """
        # Check subject match
        if self.subjects and context.subject_id not in self.subjects:
            if not any(context.subject_id.startswith(p.rstrip("*")) for p in self.subjects):
                return PolicyEffect.AUDIT  # Not applicable
        
        # Check resource match
        if self.resources and context.resource_type not in self.resources:
            return PolicyEffect.AUDIT  # Not applicable
        
        # Check action match
        if self.actions and context.action not in self.actions:
            return PolicyEffect.AUDIT  # Not applicable
        
        # Check conditions
        for condition in self.conditions:
            if not self._evaluate_condition(condition, context):
                return PolicyEffect.AUDIT  # Conditions not met
        
        return self.effect
    
    def _evaluate_condition(self, condition: str, context: PolicyContext) -> bool:
        """Evaluate Python condition against context."""
        # Build evaluation namespace
        ns = {
            "subject_id": context.subject_id,
            "subject_type": context.subject_type,
            "subject_roles": context.subject_roles,
            "subject_trust_level": context.subject_trust_level,
            "resource_type": context.resource_type,
            "resource_id": context.resource_id,
            "resource_owner": context.resource_owner,
            "action": context.action,
            "environment": context.environment,
            "timestamp": context.timestamp,
            **context.metadata,
        }
        
        try:
            return bool(eval(condition, {"__builtins__": {}}, ns))
        except Exception:
            return False


@dataclass
class PolicyDecision:
    """Result of policy evaluation."""
    
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    allowed: bool = True
    effect: PolicyEffect = PolicyEffect.ALLOW
    
    # Decision details
    matched_rules: list[str] = field(default_factory=list)
    denied_by_rules: list[str] = field(default_factory=list)
    
    # Reasoning
    reason: str = ""
    explanation: str = ""
    
    # Conditions for conditional allow
    conditions: list[str] = field(default_factory=list)
    unfulfilled_conditions: list[str] = field(default_factory=list)
    
    # Audit
    audit_entries: list[dict[str, Any]] = field(default_factory=list)
    
    timestamp: datetime = field(default_factory=datetime.now)


class PolicyEngine:
    """Policy engine for authorization decisions.
    
    Evaluates requests against policy rules and returns decisions.
    """
    
    def __init__(self) -> None:
        self._rules: list[PolicyRule] = []
        self._default_effect = PolicyEffect.DENY
        self._audit_log: list[dict[str, Any]] = []
    
    def add_rule(self, rule: PolicyRule) -> None:
        """Add a policy rule."""
        self._rules.append(rule)
        # Sort by priority (descending)
        self._rules.sort(key=lambda r: r.priority, reverse=True)
    
    def load_default_rules(self) -> None:
        """Load default security policies."""
        # Firmware flashing requires high trust
        self.add_rule(PolicyRule(
            rule_id="firmware-flash-trust",
            name="Firmware Flash Trust Requirement",
            actions=["flash", "flash_firmware"],
            effect=PolicyEffect.CONDITIONAL,
            conditions=["subject_trust_level >= 0.8"],
            priority=100,
        ))
        
        # Snapshot restore requires ownership or admin
        self.add_rule(PolicyRule(
            rule_id="snapshot-restore-ownership",
            name="Snapshot Restore Ownership",
            actions=["restore_snapshot"],
            effect=PolicyEffect.CONDITIONAL,
            conditions=[
                "resource_owner == subject_id",
                "'admin' in subject_roles",
            ],
            priority=90,
        ))
        
        # Production modifications require explicit approval
        self.add_rule(PolicyRule(
            rule_id="production-modify",
            name="Production Modification Control",
            actions=["flash", "write_memory", "restore_snapshot"],
            effect=PolicyEffect.CONDITIONAL,
            conditions=["environment != 'production' or 'production_approved' in subject_roles"],
            priority=80,
        ))
        
        # Plugin loading requires admin role
        self.add_rule(PolicyRule(
            rule_id="plugin-load-admin",
            name="Plugin Loading Admin Only",
            actions=["load_plugin", "install_plugin"],
            effect=PolicyEffect.DENY,
            conditions=["'admin' not in subject_roles"],
            priority=70,
        ))
        
        # Read operations generally allowed
        self.add_rule(PolicyRule(
            rule_id="read-allowed",
            name="Read Operations Allowed",
            actions=["read_memory", "read_register", "read_flash", "get_backtrace"],
            effect=PolicyEffect.ALLOW,
            priority=1,
        ))
    
    async def evaluate(self, context: PolicyContext) -> PolicyDecision:
        """Evaluate context against policies.
        
        Returns:
            PolicyDecision with result
        """
        decision = PolicyDecision()
        
        for rule in self._rules:
            effect = rule.evaluate(context)
            
            if effect == PolicyEffect.AUDIT:
                if rule.audit_enabled:
                    decision.audit_entries.append({
                        "rule_id": rule.rule_id,
                        "rule_name": rule.name,
                        "timestamp": datetime.now(),
                    })
                continue
            
            decision.matched_rules.append(rule.rule_id)
            
            if effect == PolicyEffect.DENY:
                decision.allowed = False
                decision.effect = PolicyEffect.DENY
                decision.denied_by_rules.append(rule.rule_id)
                decision.reason = rule.name
                decision.explanation = rule.description
                break
            
            elif effect == PolicyEffect.CONDITIONAL:
                # Check if conditions are met
                conditions_met = True
                for condition in rule.conditions:
                    if not rule._evaluate_condition(condition, context):
                        conditions_met = False
                        decision.unfulfilled_conditions.append(condition)
                
                if not conditions_met:
                    decision.allowed = False
                    decision.effect = PolicyEffect.CONDITIONAL
                    decision.conditions = rule.conditions
                else:
                    decision.allowed = True
                    decision.effect = PolicyEffect.CONDITIONAL
            
            elif effect == PolicyEffect.ALLOW:
                decision.allowed = True
                decision.effect = PolicyEffect.ALLOW
        
        # Default deny if no matching rules
        if not decision.matched_rules:
            decision.allowed = self._default_effect == PolicyEffect.ALLOW
            decision.effect = self._default_effect
        
        # Log audit entries
        if decision.audit_entries:
            self._audit_log.extend(decision.audit_entries)
        
        return decision
    
    def can_flash_firmware(self, context: PolicyContext) -> PolicyDecision:
        """Check if firmware flashing is allowed."""
        context.action = "flash"
        return asyncio.run(self.evaluate(context))
    
    def can_restore_snapshot(self, context: PolicyContext) -> PolicyDecision:
        """Check if snapshot restore is allowed."""
        context.action = "restore_snapshot"
        return asyncio.run(self.evaluate(context))
    
    def can_load_plugin(self, context: PolicyContext) -> PolicyDecision:
        """Check if plugin loading is allowed."""
        context.action = "load_plugin"
        return asyncio.run(self.evaluate(context))
    
    def get_audit_log(
        self,
        limit: int = 100,
        since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Get audit log entries."""
        entries = self._audit_log
        if since:
            entries = [e for e in entries if e.get("timestamp", datetime.min) >= since]
        return entries[-limit:]
```

---

### 9. Distributed Coordination

**Status**: Required for multi-node hardware lab

```python
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any
import asyncio


class NodeState(Enum):
    """Distributed node states."""
    UNKNOWN = "unknown"
    STARTING = "starting"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    SHUTTING_DOWN = "shutting_down"
    OFFLINE = "offline"


@dataclass
class NodeInfo:
    """Information about a distributed node."""
    
    node_id: str
    node_type: str = "worker"  # worker, coordinator, storage
    endpoint: str = ""  # gRPC/HTTP endpoint
    
    state: NodeState = NodeState.UNKNOWN
    started_at: datetime = field(default_factory=datetime.now)
    last_heartbeat: datetime = field(default_factory=datetime.now)
    
    # Capabilities
    capabilities: list[str] = field(default_factory=list)
    available_probes: list[str] = field(default_factory=list)
    
    # Health
    health_score: float = 1.0
    error_count: int = 0


@dataclass
class DistributedLock:
    """Distributed lock implementation.
    
    Uses Redis-like semantics with fencing tokens.
    """
    
    lock_id: str
    owner_id: str
    
    acquired_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=datetime.now)
    
    version: int = 1
    fencing_token: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    def is_valid(self) -> bool:
        """Check if lock is still valid."""
        return datetime.now() < self.expires_at


@dataclass
class LeaderElection:
    """Leader election for coordinator role.
    
    Implements Raft-like leader election.
    """
    
    election_id: str
    term: int = 0
    voted_for: str | None = None
    
    last_heartbeat: datetime = field(default_factory=datetime.now)
    election_timeout: timedelta = field(default_factory=lambda: timedelta(seconds=5))
    
    # For candidates
    is_candidate: bool = False
    vote_count: int = 0
    granted_votes: set[str] = field(default_factory=set)


class NodeRegistry:
    """Registry of nodes in distributed system."""
    
    def __init__(self) -> None:
        self._nodes: dict[str, NodeInfo] = {}
        self._locks: dict[str, DistributedLock] = {}
        self._leader: LeaderElection | None = None
        self._lock = asyncio.Lock()
    
    async def register_node(self, node: NodeInfo) -> None:
        """Register a node in the cluster."""
        async with self._lock:
            self._nodes[node.node_id] = node
    
    async def unregister_node(self, node_id: str) -> None:
        """Unregister a node."""
        async with self._lock:
            if node_id in self._nodes:
                self._nodes[node_id].state = NodeState.OFFLINE
                del self._nodes[node_id]
    
    async def update_heartbeat(self, node_id: str) -> bool:
        """Update node heartbeat.
        
        Returns:
            True if node exists and updated
        """
        async with self._lock:
            node = self._nodes.get(node_id)
            if not node:
                return False
            node.last_heartbeat = datetime.now()
            return True
    
    async def get_healthy_nodes(self) -> list[NodeInfo]:
        """Get all healthy nodes."""
        async with self._lock:
            return [
                n for n in self._nodes.values()
                if n.state == NodeState.HEALTHY
            ]
    
    async def acquire_lock(
        self,
        lock_id: str,
        owner_id: str,
        ttl: timedelta = timedelta(minutes=5),
    ) -> DistributedLock | None:
        """Acquire distributed lock.
        
        Returns:
            DistributedLock if acquired, None if already locked
        """
        async with self._lock:
            existing = self._locks.get(lock_id)
            if existing and existing.is_valid() and existing.owner_id != owner_id:
                return None  # Already locked
            
            lock = DistributedLock(
                lock_id=lock_id,
                owner_id=owner_id,
                expires_at=datetime.now() + ttl,
            )
            self._locks[lock_id] = lock
            return lock
    
    async def release_lock(self, lock_id: str, owner_id: str) -> bool:
        """Release distributed lock."""
        async with self._lock:
            lock = self._locks.get(lock_id)
            if not lock or lock.owner_id != owner_id:
                return False
            lock.expires_at = datetime.now()
            return True
    
    async def start_election(self, node_id: str) -> bool:
        """Start leader election.
        
        Returns:
            True if this node becomes leader
        """
        async with self._lock:
            if not self._leader:
                self._leader = LeaderElection(election_id="coordinator")
            
            self._leader.term += 1
            self._leader.is_candidate = True
            self._leader.vote_count = 1
            self._leader.granted_votes = {node_id}
            
            # Simulate vote collection
            healthy = await self.get_healthy_nodes()
            quorum = len(healthy) // 2 + 1
            
            # In real implementation, would send vote requests
            # and collect responses
            
            if self._leader.vote_count >= quorum:
                self._leader.is_candidate = False
                return True
            
            return False


class HeartbeatMonitor:
    """Monitors node heartbeats and detects failures."""
    
    def __init__(
        self,
        node_registry: NodeRegistry,
        heartbeat_interval: timedelta = timedelta(seconds=5),
        failure_threshold: int = 3,
    ) -> None:
        self._registry = node_registry
        self._heartbeat_interval = heartbeat_interval
        self._failure_threshold = failure_threshold
        self._missed_heartbeats: dict[str, int] = {}
        self._running = False
        self._task: asyncio.Task | None = None
    
    async def start(self) -> None:
        """Start heartbeat monitoring."""
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
    
    async def stop(self) -> None:
        """Stop heartbeat monitoring."""
        self._running = False
        if self._task:
            self._task.cancel()
    
    async def _monitor_loop(self) -> None:
        """Monitor loop."""
        while self._running:
            try:
                await self._check_heartbeats()
                await asyncio.sleep(self._heartbeat_interval.total_seconds())
            except asyncio.CancelledError:
                break
            except Exception:
                pass
    
    async def _check_heartbeats(self) -> None:
        """Check all node heartbeats."""
        nodes = await self._registry.get_healthy_nodes()
        now = datetime.now()
        
        for node in nodes:
            missed = self._missed_heartbeats.get(node.node_id, 0)
            
            if now - node.last_heartbeat > self._heartbeat_interval:
                missed += 1
                self._missed_heartbeats[node.node_id] = missed
                
                if missed >= self._failure_threshold:
                    node.state = NodeState.UNHEALTHY
            else:
                self._missed_heartbeats[node.node_id] = 0
```

---

### 10. AI Reasoning Primitives

**Status**: Structural ontology exists, needs reasoning graphs

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DependencyNode:
    """Node in dependency graph."""
    
    node_id: str
    node_type: str  # function, variable, register, peripheral
    name: str
    
    # Dependencies
    depends_on: list[str] = field(default_factory=list)  # Node IDs this depends on
    depended_by: list[str] = field(default_factory=list)  # Node IDs depending on this
    
    # Metadata
    file_path: str = ""
    line_number: int = 0
    symbol_type: str = ""  # function, global, struct, enum


@dataclass
class DependencyGraph:
    """Graph of code dependencies.
    
    Tracks:
    - Function call dependencies
    - Variable/struct dependencies
    - Register access patterns
    - Peripheral ownership
    """
    
    nodes: dict[str, DependencyNode] = field(default_factory=dict)
    adjacency_list: dict[str, list[str]] = field(default_factory=dict)
    
    def add_node(self, node: DependencyNode) -> None:
        """Add node to graph."""
        self.nodes[node.node_id] = node
        if node.node_id not in self.adjacency_list:
            self.adjacency_list[node.node_id] = []
    
    def add_dependency(self, from_id: str, to_id: str) -> None:
        """Add dependency edge (from depends on to)."""
        if from_id not in self.nodes or to_id not in self.nodes:
            return
        
        self.nodes[from_id].depends_on.append(to_id)
        self.nodes[to_id].depended_by.append(from_id)
        self.adjacency_list[from_id].append(to_id)
    
    def get_call_chain(self, from_id: str, to_id: str) -> list[str] | None:
        """Find call chain between two nodes."""
        if from_id not in self.nodes or to_id not in self.nodes:
            return None
        
        # BFS to find path
        queue = [(from_id, [from_id])]
        visited = {from_id}
        
        while queue:
            current, path = queue.pop(0)
            
            for neighbor in self.nodes[current].depends_on:
                if neighbor == to_id:
                    return path + [to_id]
                
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        
        return None
    
    def get_impacted_nodes(self, node_id: str) -> list[str]:
        """Get all nodes impacted by changes to this node."""
        impacted = []
        visited = set()
        queue = [node_id]
        
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            
            for dependent in self.nodes[current].depended_by:
                impacted.append(dependent)
                queue.append(dependent)
        
        return impacted


@dataclass
class TimingConstraint:
    """Timing constraint between operations."""
    
    constraint_id: str
    from_operation: str
    to_operation: str
    
    # Constraints
    min_latency_ns: int = 0
    max_latency_ns: int = 0
    typical_latency_ns: int = 0
    
    # Criticality
    is_hard_real_time: bool = False
    is_critical: bool = False
    
    # Analysis
    slack_ns: int | None = None
    worst_case_ns: int | None = None


@dataclass
class TimingGraph:
    """Graph of timing relationships.
    
    Tracks:
    - Operation latencies
    - Path delays
    - Slack analysis
    - Critical path identification
    """
    
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)  # operation -> properties
    constraints: dict[str, TimingConstraint] = field(default_factory=dict)
    
    def add_operation(
        self,
        operation_id: str,
        typical_ns: int,
        worst_case_ns: int | None = None,
    ) -> None:
        """Add timing node for operation."""
        self.nodes[operation_id] = {
            "typical_ns": typical_ns,
            "worst_case_ns": worst_case_ns or typical_ns * 2,
        }
    
    def add_constraint(self, constraint: TimingConstraint) -> None:
        """Add timing constraint."""
        self.constraints[constraint.constraint_id] = constraint
    
    def get_critical_path(
        self,
        start_ops: list[str],
        end_ops: list[str],
    ) -> tuple[list[str], int]:
        """Find critical path (longest path) from start to end.
        
        Returns:
            (path, total_latency_ns)
        """
        # Find all paths and return longest
        best_path = []
        best_latency = 0
        
        def dfs(current: str, path: list[str], latency: int) -> None:
            nonlocal best_path, best_latency
            
            if current in end_ops:
                if latency > best_latency:
                    best_latency = latency
                    best_path = path.copy()
                return
            
            for neighbor, props in self.nodes.items():
                if neighbor not in path:
                    dfs(neighbor, path + [neighbor], latency + props["typical_ns"])
        
        for start in start_ops:
            dfs(start, [start], 0)
        
        return best_path, best_latency
    
    def check_timing_violation(
        self,
        from_op: str,
        to_op: str,
        measured_ns: int,
    ) -> tuple[bool, str]:
        """Check if timing constraint is violated.
        
        Returns:
            (is_violated, reason)
        """
        for constraint in self.constraints.values():
            if (constraint.from_operation == from_op and 
                constraint.to_operation == to_op):
                
                if measured_ns > constraint.max_latency_ns:
                    return True, f"Exceeded max latency: {measured_ns}ns > {constraint.max_latency_ns}ns"
                
                if constraint.is_hard_real_time and measured_ns > constraint.max_latency_ns:
                    return True, f"Hard real-time constraint violated"
        
        return False, ""


@dataclass
class IRQContentionEntry:
    """IRQ contention entry."""
    
    irq_number: int
    irq_name: str
    
    # Priority
    priority: int = 0
    priority_level: str = "configurable"  # fixed, configurable
    
    # Timing
    max_isr_duration_ns: int = 0
    average_isr_duration_ns: int = 0
    
    # Nesting
    can_nest: bool = False
    nesting_priority_mask: int = 0
    
    # Dependencies
    shares_resource_with: list[int] = field(default_factory=list)  # IRQ numbers
    blocks_lower_priority: bool = True
    
    # Statistics
    invocation_count: int = 0
    total_execution_ns: int = 0
    
    @property
    def current_avg_duration_ns(self) -> int:
        """Calculate current average duration."""
        if self.invocation_count == 0:
            return 0
        return self.total_execution_ns // self.invocation_count


class IRQContentionGraph:
    """Graph for IRQ contention analysis.
    
    Tracks:
    - IRQ priorities
    - ISR durations
    - Resource sharing
    - Contention analysis
    """
    
    def __init__(self) -> None:
        self._irqs: dict[int, IRQContentionEntry] = {}
        self._contention_edges: list[tuple[int, int, int]] = []  # (irq_a, irq_b, contention_score)
    
    def add_irq(self, entry: IRQContentionEntry) -> None:
        """Add IRQ entry."""
        self._irqs[entry.irq_number] = entry
    
    def analyze_contention(self) -> list[tuple[int, int, int]]:
        """Analyze IRQ contention.
        
        Returns:
            List of (irq_a, irq_b, contention_score) sorted by contention
        """
        contention: list[tuple[int, int, int]] = []
        
        for irq_a, entry_a in self._irqs.items():
            for irq_b, entry_b in self._irqs.items():
                if irq_a >= irq_b:
                    continue
                
                # Check resource sharing
                shared = set(entry_a.shares_resource_with) & set(entry_b.shares_resource_with)
                if not shared:
                    continue
                
                # Calculate contention score
                # Higher priority IRQ blocking lower priority
                score = 0
                
                if entry_a.priority < entry_b.priority:
                    score += entry_b.current_avg_duration_ns // 1000  # Duration impact
                
                if entry_a.can_nest and entry_b.can_nest:
                    score += 50  # Nesting complexity
                
                contention.append((irq_a, irq_b, score))
        
        # Sort by contention score
        contention.sort(key=lambda x: x[2], reverse=True)
        return contention
    
    def get_isr_chain(self, irq_number: int) -> list[int]:
        """Get chain of ISRs that might be affected by this IRQ.
        
        Returns:
            List of IRQ numbers that could be affected
        """
        entry = self._irqs.get(irq_number)
        if not entry:
            return []
        
        affected = [irq_number]
        
        # Lower priority IRQs blocked by this one
        for irq, other in self._irqs.items():
            if irq != irq_number:
                if other.priority > entry.priority:  # Lower priority number = higher priority
                    if other.blocks_lower_priority:
                        affected.append(irq)
        
        return affected
    
    def suggest_priority_adjustment(
        self,
        irq_number: int,
        current_priority: int,
    ) -> list[dict[str, Any]]:
        """Suggest priority adjustments to reduce contention.
        
        Returns:
            List of suggestions
        """
        entry = self._irqs.get(irq_number)
        if not entry:
            return []
        
        suggestions = []
        
        # Check if high-priority IRQ has long ISR
        if entry.current_avg_duration_ns > 10000:  # > 10us
            suggestions.append({
                "type": "duration_warning",
                "message": f"ISR {entry.irq_name} average duration ({entry.current_avg_duration_ns}ns) may cause priority inversion",
                "severity": "warning",
            })
        
        # Check resource sharing conflicts
        for shared_irq in entry.shares_resource_with:
            shared_entry = self._irqs.get(shared_irq)
            if shared_entry:
                if entry.priority != shared_entry.priority:
                    suggestions.append({
                        "type": "priority_mismatch",
                        "message": f"IRQ {irq_number} and {shared_irq} share resources but have different priorities",
                        "severity": "info",
                        "suggestion": f"Consider equal priority or atomic sections",
                    })
        
        return suggestions


@dataclass
class DMAConflictEntry:
    """DMA channel conflict entry."""
    
    channel: int
    request_line: int
    
    # Configuration
    direction: str = "memory_to_memory"  # memory_to_memory, peripheral_to_memory, memory_to_peripheral
    priority: str = "medium"  # low, medium, high, very_high
    
    # Resource usage
    peripheral: str = ""
    memory_regions: list[str] = field(default_factory=list)
    
    # Timing
    burst_size: int = 0
    data_width: int = 0
    
    # Conflicts
    shares_bus_with: list[int] = field(default_factory=list)
    can_stall_other: bool = True


class DMAConflictGraph:
    """Graph for DMA conflict analysis.
    
    Tracks:
    - DMA channel configurations
    - Bus contention
    - Memory access patterns
    - Conflict detection
    """
    
    def __init__(self) -> None:
        self._channels: dict[int, DMAConflictEntry] = {}
    
    def add_channel(self, entry: DMAConflictEntry) -> None:
        """Add DMA channel."""
        self._channels[entry.channel] = entry
    
    def detect_conflicts(self) -> list[dict[str, Any]]:
        """Detect DMA conflicts.
        
        Returns:
            List of conflict descriptions
        """
        conflicts = []
        
        for channel_a, entry_a in self._channels.items():
            for channel_b, entry_b in self._channels.items():
                if channel_a >= channel_b:
                    continue
                
                # Check bus sharing
                if channel_b in entry_a.shares_bus_with:
                    conflict = {
                        "type": "bus_contention",
                        "channel_a": channel_a,
                        "channel_b": channel_b,
                        "channels": [channel_a, channel_b],
                        "priority_a": entry_a.priority,
                        "priority_b": entry_b.priority,
                        "direction_a": entry_a.direction,
                        "direction_b": entry_b.direction,
                    }
                    
                    # Calculate impact
                    if entry_a.can_stall_other or entry_b.can_stall_other:
                        conflict["impact"] = "high"
                    else:
                        conflict["impact"] = "medium"
                    
                    conflicts.append(conflict)
                
                # Check memory region overlap
                overlap = set(entry_a.memory_regions) & set(entry_b.memory_regions)
                if overlap:
                    conflicts.append({
                        "type": "memory_overlap",
                        "channel_a": channel_a,
                        "channel_b": channel_b,
                        "shared_regions": list(overlap),
                        "impact": "critical" if entry_a.direction != entry_b.direction else "medium",
                    })
        
        return conflicts
```

---

## Phase 6.1 Done Criteria

- [ ] TargetLifecycleStateMachine with TransitionGuard
- [ ] Resource Ownership / Lease System
- [ ] Temporal Replay System
- [ ] Event Bus Delivery Semantics
- [ ] Runtime Coordinator
- [ ] Hardened Plugin Sandbox
- [ ] Probabilistic Fault Propagation
- [ ] Policy Engine
- [ ] Distributed Coordination
- [ ] AI Reasoning Primitives

## Future Phases

| Phase | Focus |
|-------|-------|
| Phase 6.2 | Probe Runtime & Execution Engine |
| Phase 6.3 | RTOS Semantic Introspection |
| Phase 6.4 | Deterministic Replay Runtime |
| Phase 6.5 | AI Root-Cause Reasoning Engine |
| Phase 6.6 | Autonomous Repair Planner |
| Phase 6.7 | Distributed Hardware Lab |
| Phase 6.8 | Firmware Time-Travel Debugger |
| Phase 7 | Hardware-in-the-Loop (HIL) & Simulation |
| Phase 8 | Static Analysis & Intelligence |
| Phase 9 | Patch Suggestion & Trust Model |
| Phase 10 | Tooling, UX & CI/CD Integration |
