"""NXP chip vendor plugin.

This plugin provides NXP-specific operations for LPC, Kinetis, and i.MX RT chips.
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


class NXPPlugin(ChipVendorPlugin):
    """NXP chip vendor plugin.

    Provides NXP-specific operations for LPC, Kinetis, and i.MX RT series.
    """

    VENDOR_NAME = "NXP"
    VERSION = "1.0.0"
    SUPPORTED_FAMILIES = ["NXP_LPC", "NXP_KINETIS", "NXP_IMX_RT"]

    def get_flash_address(self, chip) -> int:
        """Get flash memory base address."""
        family = getattr(chip.family, "value", str(chip.family)) if hasattr(chip, "family") else ""

        if "LPC" in family:
            return 0x00000000  # LPC flash at 0x0
        elif "KINETIS" in family:
            return 0x00000000  # Kinetis flash at 0x0
        elif "IMX_RT" in family:
            return 0x30000000  # i.MX RT flash at 0x30000000

        return 0x00000000

    def get_ram_addresses(self, chip) -> list[tuple[str, int, int]]:
        """Get RAM memory regions for NXP chips."""
        family = getattr(chip.family, "value", str(chip.family)) if hasattr(chip, "family") else ""

        if "LPC" in family:
            return [
                ("RAM", 0x10000000, 0x10000),  # 64KB SRAM
            ]
        elif "KINETIS" in family:
            return [
                ("SRAM", 0x20000000, 0x20000),  # 128KB SRAM
                ("SRAM_L", 0x20000000, 0x10000),
                ("SRAM_U", 0x20010000, 0x10000),
            ]
        elif "IMX_RT" in family:
            return [
                ("OCRAM", 0x20200000, 0x40000),  # 256KB OCRAM
                ("RAM", 0x20000000, 0x20000),   # 128KB DTCM
            ]

        return [("RAM", 0x20000000, 0x10000)]

    def get_reset_sequence(self, chip) -> ResetSequence:
        """Get NXP reset sequence."""
        return ResetSequence(
            steps=[
                {"type": "halt"},
                {"type": "reset", "mode": "system"},
                {"type": "delay", "ms": 50},
                {"type": "pc", "value": 0x00000000},
            ],
            description="Standard NXP reset sequence",
        )

    def get_gdb_init_commands(self, chip) -> list[GDBInitCommand]:
        """Get GDB initialization commands for NXP."""
        return [
            GDBInitCommand("monitor reset halt", "Reset and halt CPU", "post_reset"),
            GDBInitCommand("set mem inaccessible-by-default off", "Allow full memory access", "pre_reset"),
        ]

    def get_power_domains(self, chip) -> list[PowerDomain]:
        """Get NXP power domains."""
        return [
            PowerDomain(name="SIM", base_address=0x40048000, enable_mask=0x00000001),
            PowerDomain(name="PMC", base_address=0x40048100, enable_mask=0x00000001),
        ]

    def get_clock_tree(self, chip) -> list[ClockConfig]:
        """Get NXP clock tree configuration."""
        return [
            ClockConfig(name="CPU", frequency_hz=120_000_000, source="PLL", multiplier=1, divider=1),
            ClockConfig(name="BUS", frequency_hz=60_000_000, source="CPU", divider=2),
        ]

    def get_interrupt_map(self, chip) -> list[InterruptMapping]:
        """Get NXP interrupt mapping."""
        return [
            InterruptMapping(peripheral="DMA0", irq_number=0, priority=0),
            InterruptMapping(peripheral="UART0", irq_number=1, priority=1),
            InterruptMapping(peripheral="UART1", irq_number=2, priority=1),
        ]

    def get_nvic_info(self, chip) -> NVICInfo:
        """Get NXP NVIC configuration."""
        return NVICInfo(
            priority_bits=4,
            max_priority=15,
            max_interrupts=160,
            interrupt_table_base=0x00000000,
        )

    def get_capabilities(self) -> dict:
        """Get NXP-specific capabilities."""
        return {
            **super().get_capabilities(),
            "has_swd": True,
            "has_jtag": True,
            "has_swo": False,
        }
