"""Espressif chip vendor plugin.

This plugin provides Espressif-specific operations for ESP32 and related chips.
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


class EspressifPlugin(ChipVendorPlugin):
    """Espressif chip vendor plugin.

    Provides ESP32-specific operations including flash mapping,
    WiFi/BT peripherals, and Xtensa configuration.
    """

    VENDOR_NAME = "Espressif"
    VERSION = "1.0.0"
    SUPPORTED_FAMILIES = [
        "ESP32", "ESP32S2", "ESP32S3", "ESP32C3", "ESP32C6",
    ]

    # ESP32 flash addresses
    FLASH_ADDRESSES = {
        ChipFamily.ESPRESSIF_ESP32: 0x40000000,
        ChipFamily.ESPRESSIF_ESP32S2: 0x40000000,
        ChipFamily.ESPRESSIF_ESP32S3: 0x40000000,
        ChipFamily.ESPRESSIF_ESP32C3: 0x40000000,
        ChipFamily.ESPRESSIF_ESP32C6: 0x40000000,
    }

    def get_flash_address(self, chip) -> int:
        """Get flash memory base address."""
        if hasattr(chip, "family"):
            return self.FLASH_ADDRESSES.get(chip.family, 0x3F400000)
        return 0x3F400000

    def get_ram_addresses(self, chip) -> list[tuple[str, int, int]]:
        """Get RAM memory regions for ESP32."""
        return [
            ("DRAM", 0x3FF80000, 0x20000),    # 128KB Data RAM
            ("IRAM", 0x40000000, 0x20000),    # 128KB Instruction RAM
            ("RTCiram", 0x50000000, 0x8000),   # 32KB RTC Fast Memory
        ]

    def get_reset_sequence(self, chip) -> ResetSequence:
        """Get ESP32 reset sequence."""
        return ResetSequence(
            steps=[
                {"type": "halt"},
                {"type": "reset", "mode": "cpu"},
                {"type": "delay", "ms": 100},
                {"type": "pc", "value": 0x40000400},  # ROM entry
            ],
            description="ESP32 reset sequence",
        )

    def get_gdb_init_commands(self, chip) -> list[GDBInitCommand]:
        """Get GDB initialization commands for ESP32."""
        return [
            GDBInitCommand("set arch xtensa", "Set Xtensa architecture", "pre_reset"),
            GDBInitCommand("set cpu features single-float", "Set floating point mode", "pre_reset"),
            GDBInitCommand("monitor reset halt", "Reset and halt", "post_reset"),
            GDBInitCommand("thb app_main", "Hardware break at app_main", "post_halt"),
        ]

    def get_power_domains(self, chip) -> list[PowerDomain]:
        """Get ESP32 power domains."""
        return [
            PowerDomain(name="RTC", base_address=0x60008000, enable_mask=0x00000001),
            PowerDomain(name="WIFI", base_address=0x60013000, enable_mask=0x00000001),
            PowerDomain(name="BT", base_address=0x60024000, enable_mask=0x00000001),
        ]

    def get_clock_tree(self, chip) -> list[ClockConfig]:
        """Get ESP32 clock tree configuration."""
        return [
            ClockConfig(name="CPU", frequency_hz=160_000_000, source="APB PLL", multiplier=1, divider=1),
            ClockConfig(name="APB", frequency_hz=80_000_000, source="CPU", divider=2),
            ClockConfig(name="XTAL", frequency_hz=40_000_000, source="Crystal", divider=1),
            ClockConfig(name="RTC", frequency_hz=32_768, source="RTCXO", divider=1),
        ]

    def get_interrupt_map(self, chip) -> list[InterruptMapping]:
        """Get ESP32 interrupt mapping."""
        return [
            InterruptMapping(peripheral="WIFI_MAC", irq_number=0, priority=1),
            InterruptMapping(peripheral="WIFI_BB", irq_number=1, priority=1),
            InterruptMapping(peripheral="BT_BB", irq_number=2, priority=1),
            InterruptMapping(peripheral="RWBT", irq_number=3, priority=1),
        ]

    def get_nvic_info(self) -> NVICInfo:
        """Get ESP32 NVIC configuration (Xtensa)."""
        return NVICInfo(
            priority_bits=3,  # Xtensa has 3 priority bits
            max_priority=7,
            max_interrupts=32,
            interrupt_table_base=0x40000000,
        )

    def get_capabilities(self) -> dict:
        """Get ESP32-specific capabilities."""
        return {
            **super().get_capabilities(),
            "has_jtag": True,
            "has_wifi": True,
            "has_bluetooth": True,
            "has_ble": True,
            "has_riscv": False,  # ESP32 is Xtensa
            "has_wifi_6": False,
        }
