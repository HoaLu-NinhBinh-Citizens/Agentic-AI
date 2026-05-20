"""Abstract base class for chip vendor plugins.

This module defines the ChipVendorPlugin protocol that all chip-specific
plugins must implement to provide vendor-specific operations.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .target import ChipSpec
    from .firmware import FirmwareMetadata


@dataclass
class ResetSequence:
    """Reset sequence for a chip."""

    steps: list[dict[str, Any]] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "steps": self.steps,
            "description": self.description,
        }


@dataclass
class GDBInitCommand:
    """GDB initialization command."""

    command: str
    description: str = ""
    when: str = "post_reset"  # pre_reset, post_reset, post_halt


@dataclass
class PowerDomain:
    """Power domain configuration."""

    name: str
    base_address: int
    enable_mask: int
    status_offset: int = 0
    status_ready_mask: int = 0


@dataclass
class ClockConfig:
    """Clock tree configuration."""

    name: str
    frequency_hz: int
    source: str
    divider: int = 1
    multiplier: int = 1


@dataclass
class InterruptMapping:
    """Interrupt mapping for a peripheral."""

    peripheral: str
    irq_number: int
    priority: int = 0
    handler_name: str = ""


@dataclass
class NVICInfo:
    """Nested Vector Interrupt Controller information."""

    priority_bits: int = 8
    max_priority: int = 255
    max_interrupts: int = 256
    interrupt_table_base: int = 0x00000000


@dataclass
class PeripheralInfo:
    """Peripheral information."""

    name: str
    base_address: int
    size: int
    clock_enable_register: str
    clock_enable_mask: int
    reset_register: str
    reset_mask: int


class ChipVendorPlugin(ABC):
    """Abstract base class for chip vendor plugins.

    Each plugin provides vendor-specific operations for a family of chips.
    Plugins must implement all abstract methods to provide complete
    chip-specific functionality.

    Example implementation:
        class STMicroPlugin(ChipVendorPlugin):
            VENDOR_NAME = "STMicroelectronics"
            SUPPORTED_FAMILIES = ["STM32F4", "STM32F7", "STM32H7"]

            def get_flash_address(self) -> int:
                return 0x08000000
            ...
    """

    # Plugin metadata - must be overridden
    VENDOR_NAME: str = "Unknown"
    VERSION: str = "1.0.0"
    SUPPORTED_FAMILIES: list[str] = []

    def __init__(self):
        """Initialize plugin."""
        self._initialized = False
        self._capabilities: dict[str, bool] = {}

    @property
    def vendor_name(self) -> str:
        """Get vendor name."""
        return self.VENDOR_NAME

    @property
    def version(self) -> str:
        """Get plugin version."""
        return self.VERSION

    @property
    def supported_families(self) -> list[str]:
        """Get list of supported chip families."""
        return self.SUPPORTED_FAMILIES

    @abstractmethod
    def get_flash_address(self, chip: "ChipSpec") -> int:
        """Get flash memory base address.

        Args:
            chip: Chip specification

        Returns:
            Flash base address
        """
        ...

    @abstractmethod
    def get_ram_addresses(self, chip: "ChipSpec") -> list[tuple[str, int, int]]:
        """Get RAM memory regions.

        Args:
            chip: Chip specification

        Returns:
            List of (name, base_address, size) tuples
        """
        ...

    @abstractmethod
    def get_reset_sequence(self, chip: "ChipSpec") -> ResetSequence:
        """Get chip-specific reset sequence.

        Args:
            chip: Chip specification

        Returns:
            ResetSequence with steps to perform
        """
        ...

    @abstractmethod
    def get_gdb_init_commands(self, chip: "ChipSpec") -> list[GDBInitCommand]:
        """Get GDB initialization commands.

        Args:
            chip: Chip specification

        Returns:
            List of GDB commands to send
        """
        ...

    @abstractmethod
    def get_power_domains(self, chip: "ChipSpec") -> list[PowerDomain]:
        """Get power domain configuration.

        Args:
            chip: Chip specification

        Returns:
            List of power domains
        """
        ...

    @abstractmethod
    def get_clock_tree(self, chip: "ChipSpec") -> list[ClockConfig]:
        """Get clock tree configuration.

        Args:
            chip: Chip specification

        Returns:
            List of clock configurations
        """
        ...

    @abstractmethod
    def get_interrupt_map(self, chip: "ChipSpec") -> list[InterruptMapping]:
        """Get interrupt mapping.

        Args:
            chip: Chip specification

        Returns:
            List of interrupt mappings
        """
        ...

    @abstractmethod
    def get_nvic_info(self, chip: "ChipSpec") -> NVICInfo:
        """Get NVIC configuration.

        Args:
            chip: Chip specification

        Returns:
            NVICInfo with controller settings
        """
        ...

    # Optional async methods
    async def async_init(self, chip: "ChipSpec") -> None:
        """Async initialization.

        Override for async initialization.

        Args:
            chip: Chip specification
        """
        pass

    async def async_cleanup(self) -> None:
        """Async cleanup.

        Override for async cleanup.
        """
        pass

    def get_capabilities(self) -> dict[str, Any]:
        """Get plugin capabilities.

        Returns:
            Dictionary of capability name to supported status
        """
        return {
            "has_async_init": True,
            "has_async_cleanup": True,
            "has_power_domains": True,
            "has_clock_tree": True,
            "has_interrupt_map": True,
        }

    def supports_chip(self, chip: "ChipSpec") -> bool:
        """Check if plugin supports this chip.

        Args:
            chip: Chip specification

        Returns:
            True if chip is supported
        """
        family_name = chip.family.value if hasattr(chip.family, "value") else str(chip.family)
        return family_name in self.supported_families

    def validate_chip(self, chip: "ChipSpec") -> list[str]:
        """Validate chip configuration.

        Args:
            chip: Chip specification

        Returns:
            List of validation warnings/errors
        """
        warnings = []

        if not self.supports_chip(chip):
            warnings.append(f"Chip {chip.part_number} may not be fully supported")

        if not chip.flash_size_kb:
            warnings.append("Flash size not specified")

        if not chip.sram_size_kb:
            warnings.append("SRAM size not specified")

        return warnings

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Plugin metadata as dictionary
        """
        return {
            "vendor": self.vendor_name,
            "version": self.version,
            "supported_families": self.supported_families,
            "capabilities": self.get_capabilities(),
        }


class PluginRegistry:
    """Registry for chip vendor plugins.

    This class manages loading and accessing chip vendor plugins.
    """

    def __init__(self):
        """Initialize registry."""
        self._plugins: dict[str, type["ChipVendorPlugin"]] = {}
        self._instances: dict[str, "ChipVendorPlugin"] = {}

    def register(self, name: str, plugin_class: type["ChipVendorPlugin"]) -> None:
        """Register a plugin class.

        Args:
            name: Plugin name/vendor name
            plugin_class: Plugin class to register
        """
        self._plugins[name] = plugin_class

    def register_instance(self, name: str, instance: "ChipVendorPlugin") -> None:
        """Register a plugin instance.

        Args:
            name: Plugin name/vendor name
            instance: Plugin instance to register
        """
        self._instances[name] = instance

    def get(self, name: str) -> "ChipVendorPlugin | None":
        """Get plugin by name.

        Args:
            name: Plugin name/vendor name

        Returns:
            Plugin instance or None
        """
        if name in self._instances:
            return self._instances[name]

        if name in self._plugins:
            instance = self._plugins[name]()
            self._instances[name] = instance
            return instance

        return None

    def get_for_chip(self, chip: "ChipSpec") -> "ChipVendorPlugin | None":
        """Get plugin that supports a chip.

        Args:
            chip: Chip specification

        Returns:
            Plugin instance or None
        """
        for instance in self._instances.values():
            if instance.supports_chip(chip):
                return instance

        for name, plugin_class in self._plugins.items():
            if name not in self._instances:
                instance = plugin_class()
                self._instances[name] = instance
                if instance.supports_chip(chip):
                    return instance

        return None

    def list_plugins(self) -> list[str]:
        """List registered plugin names.

        Returns:
            List of plugin names
        """
        return list(set(list(self._plugins.keys()) + list(self._instances.keys())))

    def list_vendors(self) -> list[str]:
        """List vendor names with registered plugins.

        Returns:
            List of vendor names
        """
        return self.list_plugins()
