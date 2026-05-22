"""J-Link probe adapter with memory/register access (Phase 6.1)."""

from __future__ import annotations

import logging
from typing import Any

from src.domain.hardware.debug_probe import JLinkProbe
from src.domain.hardware.embedded_target import DebugInterface, IDCODE
from src.domain.hardware.probe import MemoryReadResult, ProbePort, RegisterValue

from .config import DEFAULT_JLINK_INTERFACE, DEFAULT_JLINK_SPEED_KHZ

logger = logging.getLogger(__name__)

CORTEX_M_REGISTER_INDEX: dict[str, int] = {
    "r0": 0,
    "r1": 1,
    "r2": 2,
    "r3": 3,
    "r12": 12,
    "lr": 14,
    "pc": 15,
    "xpsr": 16,
    "sp": 13,
}


class MockJLinkBackend:
    """In-memory backend for unit tests and dry-run."""

    def __init__(self) -> None:
        self._memory: dict[int, int] = {}
        self._registers: dict[str, int] = {name: 0 for name in CORTEX_M_REGISTER_INDEX}

    def read_bytes(self, address: int, size: int) -> bytes:
        return bytes(self._memory.get(address + i, 0) for i in range(size))

    def write_bytes(self, address: int, data: bytes) -> None:
        for i, byte in enumerate(data):
            self._memory[address + i] = byte

    def read_register(self, name: str) -> int:
        key = name.lower()
        if key not in CORTEX_M_REGISTER_INDEX:
            raise KeyError(f"Unknown register: {name}")
        return self._registers[key]

    def write_register(self, name: str, value: int) -> None:
        key = name.lower()
        if key not in CORTEX_M_REGISTER_INDEX:
            raise KeyError(f"Unknown register: {name}")
        self._registers[key] = value & 0xFFFFFFFF


class JLinkProbeAdapter(JLinkProbe, ProbePort):
    """J-Link probe with mock or future pylink backend."""

    def __init__(
        self,
        serial: str | None = None,
        interface: DebugInterface = DebugInterface.SWD,
        speed_khz: int = DEFAULT_JLINK_SPEED_KHZ,
        backend: MockJLinkBackend | None = None,
        use_mock: bool = True,
    ) -> None:
        if interface == DebugInterface.SWD:
            iface = DebugInterface.SWD
        else:
            iface = interface
        super().__init__(serial=serial, interface=iface, speed_khz=speed_khz)
        self._backend = backend or MockJLinkBackend()
        self._use_mock = use_mock

    async def read_memory(self, address: int, size: int) -> MemoryReadResult:
        if not self.is_connected:
            return MemoryReadResult(address, b"", False, "probe not connected")
        if size <= 0:
            return MemoryReadResult(address, b"", False, "invalid size")
        try:
            data = self._backend.read_bytes(address, size)
            return MemoryReadResult(address, data, True, None)
        except Exception as exc:
            logger.warning("read_memory failed at 0x%x: %s", address, exc)
            return MemoryReadResult(address, b"", False, str(exc))

    async def write_memory(self, address: int, data: bytes) -> bool:
        if not self.is_connected:
            return False
        try:
            self._backend.write_bytes(address, data)
            self._emit_event("memory_write", {"address": address, "size": len(data)})
            return True
        except Exception as exc:
            logger.warning("write_memory failed: %s", exc)
            return False

    async def read_register(self, name: str) -> RegisterValue:
        if not self.is_connected:
            raise RuntimeError("probe not connected")
        key = name.lower()
        if key not in CORTEX_M_REGISTER_INDEX:
            raise KeyError(f"Unknown register: {name}")
        value = self._backend.read_register(key)
        return RegisterValue(name=key, index=CORTEX_M_REGISTER_INDEX[key], value=value)

    async def write_register(self, name: str, value: int) -> bool:
        if not self.is_connected:
            return False
        try:
            self._backend.write_register(name, value)
            self._emit_event("register_write", {"name": name, "value": value})
            return True
        except KeyError:
            return False

    def get_backend(self) -> MockJLinkBackend:
        """Expose backend for tests."""
        return self._backend
