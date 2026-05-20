"""Testing doubles for hardware domain tests.

This module provides mock implementations for testing without real hardware:
- MockProbe: Simulates a debug probe
- MockChip: Simulates a chip/target
- FakeEventBus: In-memory event bus for testing
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from src.domain.hardware.embedded_target import (
    ChipFamily,
    CoreType,
    DebugInterface,
    DebugProbeType,
    IDCODE,
    TargetState,
)
from src.domain.hardware.target import ChipSpec, Core, Target
from src.infrastructure.hardware.event_bus import (
    DeadLetterQueue,
    DomainEvent,
    InMemoryEventBus,
)


class MockProbe:
    """Mock debug probe for testing.

    Simulates a debug probe with configurable responses.
    """

    def __init__(
        self,
        serial: str = "MOCK001",
        probe_type: DebugProbeType = DebugProbeType.JLINK,
        interface: DebugInterface = DebugInterface.SWD,
    ):
        self.serial = serial
        self.probe_type = probe_type
        self.interface = interface
        self._connected = False
        self._target_idcode: IDCODE | None = None
        self._halted = False

    @property
    def is_connected(self) -> bool:
        """Check if probe is connected."""
        return self._connected

    async def connect(self) -> IDCODE:
        """Simulate probe connection."""
        await asyncio.sleep(0.01)  # Simulate delay
        self._connected = True
        self._target_idcode = IDCODE(
            manufacturer_id=0x2B,
            part_id=0x1234,
            device_id=0x2BA01477,
            revision=0x1,
        )
        return self._target_idcode

    async def disconnect(self) -> None:
        """Simulate probe disconnection."""
        await asyncio.sleep(0.01)
        self._connected = False
        self._target_idcode = None

    async def reset(self, mode: str = "halt_after_reset") -> None:
        """Simulate target reset."""
        await asyncio.sleep(0.01)
        self._halted = mode == "halt_after_reset"

    async def halt(self) -> None:
        """Simulate halt."""
        self._halted = True

    async def resume(self) -> None:
        """Simulate resume."""
        self._halted = False

    async def read_core_register(self, name: str) -> int:
        """Simulate register read."""
        registers = {
            "r0": 0x10000000,
            "r1": 0x20000000,
            "pc": 0x08000000,
            "sp": 0x20010000,
            "lr": 0x08000004,
        }
        return registers.get(name, 0x0)

    async def write_core_register(self, name: str, value: int) -> None:
        """Simulate register write."""
        pass

    async def read_memory(self, addr: int, size: int) -> bytes:
        """Simulate memory read."""
        return bytes([0xFF] * size)

    async def write_memory(self, addr: int, data: bytes) -> None:
        """Simulate memory write."""
        pass

    async def set_breakpoint(self, addr: int) -> int:
        """Simulate breakpoint set."""
        return 0

    async def remove_breakpoint(self, bp_num: int) -> None:
        """Simulate breakpoint removal."""
        pass

    def get_idcode(self) -> IDCODE | None:
        """Get target IDCODE."""
        return self._target_idcode


class MockChip:
    """Mock chip for testing.

    Simulates a chip with configurable properties.
    """

    def __init__(
        self,
        part_number: str = "STM32F407VGT6",
        family: ChipFamily = ChipFamily.STM32F4,
        core: CoreType = CoreType.CORTEX_M4,
    ):
        self.chip_spec = ChipSpec(
            part_number=part_number,
            family=family,
            cores=[
                Core(
                    name="CPU0",
                    core_type=core,
                    frequency_hz=168_000_000,
                    core_id=0,
                    has_fpu=True,
                    has_dsp=True,
                )
            ],
            vendor="Mock Vendor",
            flash_size_kb=1024,
            sram_size_kb=192,
            has_fpu=True,
            has_mpu=True,
        )

    def get_flash_address(self) -> int:
        """Get flash address."""
        return 0x08000000

    def get_ram_address(self) -> int:
        """Get RAM address."""
        return 0x20000000


def create_mock_target(
    target_id: str = "mock-target-001",
    name: str = "Mock STM32F4",
) -> Target:
    """Create a mock target for testing.

    Args:
        target_id: Target ID
        name: Target name

    Returns:
        Mock Target instance
    """
    chip = ChipSpec(
        part_number="STM32F407VGT6",
        family=ChipFamily.STM32F4,
        cores=[
            Core(
                name="CPU0",
                core_type=CoreType.CORTEX_M4,
                frequency_hz=168_000_000,
                core_id=0,
                has_fpu=True,
            )
        ],
        vendor="STMicroelectronics",
        flash_size_kb=1024,
        sram_size_kb=192,
        has_fpu=True,
    )

    return Target(
        id=target_id,
        name=name,
        chip=chip,
        firmware_version="1.0.0",
        connected_at=datetime.now(),
    )


class FakeEventBus(InMemoryEventBus):
    """Fake event bus for testing.

    Extends InMemoryEventBus with test-specific features.
    """

    def __init__(self):
        super().__init__(dlq=DeadLetterQueue())
        self.published_events: list[DomainEvent] = []

    async def publish(self, event: DomainEvent) -> None:
        """Record published events for testing."""
        self.published_events.append(event)
        await super().publish(event)

    def get_published_events(self, event_type: str | None = None) -> list[DomainEvent]:
        """Get all published events, optionally filtered by type.

        Args:
            event_type: Optional event type filter

        Returns:
            List of published events
        """
        if event_type:
            return [e for e in self.published_events if e.event_type == event_type]
        return self.published_events.copy()

    def clear_events(self) -> None:
        """Clear recorded events."""
        self.published_events.clear()

    def assert_event_published(
        self,
        event_type: str,
        timeout: float = 0.1,
    ) -> bool:
        """Assert that an event was published.

        Args:
            event_type: Expected event type
            timeout: How long to wait

        Returns:
            True if event was published
        """
        # Simple check without actual waiting
        for event in self.published_events:
            if event.event_type == event_type:
                return True
        return False


class MockGDBClient:
    """Mock GDB client for testing."""

    def __init__(self):
        self.connected = False
        self.breakpoints: dict[int, int] = {}

    async def connect(self) -> None:
        """Simulate GDB connection."""
        await asyncio.sleep(0.01)
        self.connected = True

    async def disconnect(self) -> None:
        """Simulate GDB disconnection."""
        self.connected = False

    async def read_registers(self) -> dict[str, int]:
        """Simulate register read."""
        return {
            "r0": 0, "r1": 0, "r2": 0, "r3": 0,
            "r4": 0, "r5": 0, "r6": 0, "r7": 0,
            "r8": 0, "r9": 0, "r10": 0, "r11": 0,
            "r12": 0, "sp": 0x20010000, "lr": 0x08000000,
            "pc": 0x08000000,
        }

    async def read_register(self, name: str) -> int:
        """Simulate single register read."""
        regs = await self.read_registers()
        return regs.get(name, 0)

    async def read_memory(self, addr: int, length: int) -> bytes:
        """Simulate memory read."""
        return bytes([0] * length)

    async def set_breakpoint(self, addr: int) -> int:
        """Simulate breakpoint set."""
        bp_num = len(self.breakpoints)
        self.breakpoints[bp_num] = addr
        return bp_num

    async def remove_breakpoint(self, bp_num: int) -> None:
        """Simulate breakpoint removal."""
        self.breakpoints.pop(bp_num, None)

    async def continue_(self) -> int:
        """Simulate continue."""
        return 5  # Signal 5 = SIGTRAP

    async def step(self) -> int:
        """Simulate single step."""
        return 5

    async def halt(self) -> int:
        """Simulate halt."""
        return 5


class MockPlugin:
    """Mock plugin for testing."""

    VENDOR_NAME = "MockVendor"
    VERSION = "1.0.0"
    SUPPORTED_FAMILIES = ["STM32F4"]

    def __init__(self):
        self._initialized = False

    def get_flash_address(self, chip) -> int:
        """Return mock flash address."""
        return 0x08000000

    def get_ram_addresses(self, chip) -> list[tuple[str, int, int]]:
        """Return mock RAM regions."""
        return [("RAM", 0x20000000, 0x20000)]

    def supports_chip(self, chip) -> bool:
        """Check if chip is supported."""
        return True


def create_async_mock(return_value=None):
    """Create an async mock with return value.

    Args:
        return_value: Value to return

    Returns:
        AsyncMock instance
    """
    mock = AsyncMock()
    mock.return_value = return_value
    return mock
