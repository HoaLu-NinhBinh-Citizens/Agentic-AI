"""STMicroelectronics chip vendor plugin.

This plugin provides STMicroelectronics-specific operations for STM32 chips.
"""

from __future__ import annotations

from src.domain.hardware.chip_plugin import (
    ChipVendorPlugin,
    ClockConfig,
    GDBInitCommand,
    InterruptMapping,
    NVICInfo,
    PowerDomain,
    ResetSequence,
)
from src.domain.hardware.embedded_target import ChipFamily


class STMicroPlugin(ChipVendorPlugin):
    """STMicroelectronics chip vendor plugin.

    Provides STM32-specific operations including flash addresses,
    clock configurations, and reset sequences.
    """

    VENDOR_NAME = "STMicroelectronics"
    VERSION = "1.0.0"
    SUPPORTED_FAMILIES = [
        "STM32F0", "STM32F1", "STM32F2", "STM32F3", "STM32F4",
        "STM32F7", "STM32H7", "STM32L0", "STM32L1", "STM32L4",
        "STM32G0", "STM32G4", "STM32WB", "STM32WL",
    ]

    # Flash base addresses by family
    FLASH_ADDRESSES = {
        ChipFamily.STM32F4: 0x08000000,
        ChipFamily.STM32F7: 0x08000000,
        ChipFamily.STM32H7: 0x08000000,
        ChipFamily.STM32F0: 0x08000000,
        ChipFamily.STM32F1: 0x08000000,
        ChipFamily.STM32F2: 0x08000000,
        ChipFamily.STM32F3: 0x08000000,
        ChipFamily.STM32L0: 0x08000000,
        ChipFamily.STM32L1: 0x08000000,
        ChipFamily.STM32L4: 0x08000000,
        ChipFamily.STM32G0: 0x08000000,
        ChipFamily.STM32G4: 0x08000000,
        ChipFamily.STM32WB: 0x08000000,
        ChipFamily.STM32WL: 0x08000000,
    }

    def get_flash_address(self, chip) -> int:
        """Get flash memory base address."""
        if hasattr(chip, "family"):
            return self.FLASH_ADDRESSES.get(chip.family, 0x08000000)
        return 0x08000000

    def get_ram_addresses(self, chip) -> list[tuple[str, int, int]]:
        """Get RAM memory regions for STM32."""
        # Default STM32F4 addresses
        regions = [
            ("SRAM1", 0x20000000, 0x20000),  # 128KB
            ("SRAM2", 0x20020000, 0x10000),  # 64KB
        ]

        # Check for CCM (Core Coupled Memory) on F4
        if hasattr(chip, "memory_regions"):
            for region in chip.memory_regions:
                if region.name.upper() == "CCM":
                    regions.append(("CCM", 0x10000000, region.size))

        return regions

    def get_reset_sequence(self, chip) -> ResetSequence:
        """Get STM32 reset sequence."""
        return ResetSequence(
            steps=[
                {"type": "halt"},
                {"type": "reset", "mode": "system"},
                {"type": "delay", "ms": 100},
                {"type": "pc", "value": 0x08000000},
            ],
            description="Standard STM32 reset sequence",
        )

    def get_gdb_init_commands(self, chip) -> list[GDBInitCommand]:
        """Get GDB initialization commands for STM32."""
        return [
            GDBInitCommand("set mem inaccessible-by-default off", "Allow access to all memory", "pre_reset"),
            GDBInitCommand("monitor reset halt", "Reset and halt CPU", "post_reset"),
            GDBInitCommand("monitor semihosting enable", "Enable semihosting", "post_halt"),
        ]

    def get_power_domains(self, chip) -> list[PowerDomain]:
        """Get STM32 power domains."""
        return [
            PowerDomain(name="PWR", base_address=0x40007000, enable_mask=0x00010000),
            PowerDomain(name="RCC", base_address=0x40023800, enable_mask=0x00000001),
        ]

    def get_clock_tree(self, chip) -> list[ClockConfig]:
        """Get STM32 clock tree configuration."""
        return [
            ClockConfig(name="SYSCLK", frequency_hz=168_000_000, source="PLL", multiplier=336, divider=2),
            ClockConfig(name="HCLK", frequency_hz=168_000_000, source="SYSCLK", divider=1),
            ClockConfig(name="PCLK1", frequency_hz=42_000_000, source="APB1", divider=4),
            ClockConfig(name="PCLK2", frequency_hz=84_000_000, source="APB2", divider=2),
        ]

    def get_interrupt_map(self, chip) -> list[InterruptMapping]:
        """Get STM32 interrupt mapping."""
        return [
            InterruptMapping(peripheral="WWDG", irq_number=0, priority=0, handler_name="WWDG_IRQHandler"),
            InterruptMapping(peripheral="PVD", irq_number=1, priority=2, handler_name="PVD_IRQHandler"),
            InterruptMapping(peripheral="RCC", irq_number=5, priority=0, handler_name="RCC_IRQHandler"),
            InterruptMapping(peripheral="EXTI0", irq_number=6, priority=1, handler_name="EXTI0_IRQHandler"),
        ]

    def get_nvic_info(self, chip) -> NVICInfo:
        """Get STM32 NVIC configuration."""
        return NVICInfo(
            priority_bits=8,
            max_priority=255,
            max_interrupts=256,
            interrupt_table_base=0x00000000,
        )

    def get_capabilities(self) -> dict:
        """Get STM32-specific capabilities."""
        return {
            **super().get_capabilities(),
            "has_swd": True,
            "has_jtag": True,
            "has_swo": True,
            "has_trace": True,
            "has_rtt": True,
            "has_etm": True,
        }
