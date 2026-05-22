"""Debug probe domain interface (Phase 6.1).

Abstract contract for J-Link/ST-Link adapters. Infrastructure implements backends.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .debug_probe import BaseProbe, ProbeCapabilities, ProbeInfo
from .embedded_target import DebugInterface, IDCODE, ResetMode


@dataclass(frozen=True)
class MemoryReadResult:
    """Result of a target memory read."""

    address: int
    data: bytes
    success: bool
    error: str | None = None


@dataclass(frozen=True)
class RegisterValue:
    """Single CPU register snapshot."""

    name: str
    index: int
    value: int


@runtime_checkable
class IDebugProbe(Protocol):
    """Minimal probe contract for orchestration layers."""

    @property
    def is_connected(self) -> bool: ...

    async def connect(self) -> IDCODE: ...
    async def disconnect(self) -> None: ...
    async def read_memory(self, address: int, size: int) -> MemoryReadResult: ...
    async def write_memory(self, address: int, data: bytes) -> bool: ...
    async def read_register(self, name: str) -> RegisterValue: ...
    async def write_register(self, name: str, value: int) -> bool: ...
    async def get_probe_info(self) -> ProbeInfo: ...


class ProbePort(ABC):
    """Extended probe port with memory/register access."""

    @abstractmethod
    async def read_memory(self, address: int, size: int) -> MemoryReadResult:
        """Read target memory."""

    @abstractmethod
    async def write_memory(self, address: int, data: bytes) -> bool:
        """Write target memory."""

    @abstractmethod
    async def read_register(self, name: str) -> RegisterValue:
        """Read CPU register by name."""

    @abstractmethod
    async def write_register(self, name: str, value: int) -> bool:
        """Write CPU register by name."""


def probe_supports_memory(probe: BaseProbe) -> bool:
    """Return True if probe implements ProbePort."""
    return isinstance(probe, ProbePort)


__all__ = [
    "BaseProbe",
    "DebugInterface",
    "IDCODE",
    "IDebugProbe",
    "MemoryReadResult",
    "ProbeCapabilities",
    "ProbeInfo",
    "ProbePort",
    "RegisterValue",
    "ResetMode",
    "probe_supports_memory",
]
