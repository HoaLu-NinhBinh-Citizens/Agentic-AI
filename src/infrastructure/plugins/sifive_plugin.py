"""SiFive RISC-V chip vendor plugin.

This plugin provides SiFive-specific operations for RISC-V chips including HiFive boards.
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


class SiFivePlugin(ChipVendorPlugin):
    """SiFive RISC-V chip vendor plugin.

    Provides SiFive/HiFive-specific operations for RISC-V cores.
    """

    VENDOR_NAME = "SiFive"
    VERSION = "1.0.0"
    SUPPORTED_FAMILIES = ["RISCV", "HIFIVE_UNmatched"]

    def get_flash_address(self, chip) -> int:
        """Get flash memory base address."""
        family = getattr(chip.family, "value", str(chip.family)) if hasattr(chip, "family") else ""

        if "HIFIVE" in family:
            return 0x20000000  # HiFive-specific flash address

        return 0x20000000  # Default RISC-V flash

    def get_ram_addresses(self, chip) -> list[tuple[str, int, int]]:
        """Get RAM memory regions for RISC-V."""
        return [
            ("RAM", 0x80000000, 0x40000),   # 256KB RAM
            ("CLINT", 0x02000000, 0x10000),  # Core Local Interruptor
            ("PLIC", 0x0C000000, 0x400000),  # Platform Level Interrupt Controller
        ]

    def get_reset_sequence(self, chip) -> ResetSequence:
        """Get RISC-V reset sequence."""
        return ResetSequence(
            steps=[
                {"type": "halt"},
                {"type": "reset", "mode": "system"},
                {"type": "delay", "ms": 100},
                {"type": "pc", "value": 0x80000000},
                {"type": "reg", "name": "mstatus", "value": 0x0},  # Clear mstatus
            ],
            description="RISC-V reset sequence",
        )

    def get_gdb_init_commands(self, chip) -> list[GDBInitCommand]:
        """Get GDB initialization commands for RISC-V."""
        return [
            GDBInitCommand("set arch riscv:rv32", "Set RISC-V 32-bit architecture", "pre_reset"),
            GDBInitCommand("set riscv use_compressed_breakpoints on", "Enable compressed breakpoints", "pre_reset"),
            GDBInitCommand("monitor reset halt", "Reset and halt CPU", "post_reset"),
            GDBInitCommand("thb _start", "Hardware break at _start", "post_halt"),
        ]

    def get_power_domains(self, chip) -> list[PowerDomain]:
        """Get RISC-V power domains."""
        return [
            PowerDomain(name="CPU", base_address=0x10000000, enable_mask=0x00000001),
            PowerDomain(name="CLINT", base_address=0x02000000, enable_mask=0x00000001),
        ]

    def get_clock_tree(self, chip) -> list[ClockConfig]:
        """Get RISC-V clock tree configuration."""
        return [
            ClockConfig(name="CPU", frequency_hz=320_000_000, source="PLL", multiplier=1, divider=1),
            ClockConfig(name="PLIC", frequency_hz=32_000_000, source="APB", divider=10),
        ]

    def get_interrupt_map(self, chip) -> list[InterruptMapping]:
        """Get RISC-V interrupt mapping (PLIC)."""
        return [
            InterruptMapping(peripheral="UART0", irq_number=3, priority=1),
            InterruptMapping(peripheral="UART1", irq_number=4, priority=1),
            InterruptMapping(peripheral="GPIO", irq_number=8, priority=1),
            InterruptMapping(peripheral="PWM0", irq_number=20, priority=2),
        ]

    def get_nvic_info(self) -> NVICInfo:
        """Get RISC-V PLIC configuration."""
        return NVICInfo(
            priority_bits=2,  # RISC-V PLIC priority bits
            max_priority=7,
            max_interrupts=53,
            interrupt_table_base=0x00000000,
        )

    def get_capabilities(self) -> dict:
        """Get RISC-V-specific capabilities."""
        return {
            **super().get_capabilities(),
            "has_jtag": True,
            "has_riscv": True,
            "has_plic": True,
            "has_clint": True,
            "has_swd": False,
        }
