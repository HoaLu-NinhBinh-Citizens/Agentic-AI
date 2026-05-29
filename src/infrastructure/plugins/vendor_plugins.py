"""Sample chip vendor plugins for ST, Espressif, NXP, and SiFive.

Phase 6.1: Complete implementations of ChipVendorPlugin for common vendors.
"""

from __future__ import annotations

from typing import Any

from .capability import CapabilitySet, Capability
from .chip_plugin import (
    ChipVendorPlugin,
    ClockInfo,
    FlashInfo,
    InterruptMapping,
    NVICInfo,
    PluginTrustLevel,
    PowerDomain,
    RAMInfo,
    ResetSequence,
)
from .extended_models import (
    ChipDescription,
    ChipFamily,
    ChipVendor,
    Core,
    CoreArchitecture,
    MemoryRegion,
    SteppingLevel,
    TemperatureRange,
)
from .provenance import Provenance, ProvenanceSource, ai_inference_provenance


# ============================================================================
# STMicroelectronics Plugin
# ============================================================================


class STPlugin(ChipVendorPlugin):
    """Plugin for STMicroelectronics STM32 microcontrollers."""

    VENDOR_NAME = "STMicroelectronics"
    PLUGIN_VERSION = "1.0.0"
    SUPPORTED_FAMILIES = [
        "STM32F0", "STM32F1", "STM32F2", "STM32F3", "STM32F4",
        "STM32F7", "STM32H7", "STM32L0", "STM32L1", "STM32L4",
        "STM32L5", "STM32U5", "STM32WB", "STM32WL", "STM32G0", "STM32G4",
    ]
    TRUST_LEVEL = PluginTrustLevel.TRUSTED

    # Chip database (part_number -> chip info)
    _CHIP_DB: dict[str, dict[str, Any]] = {
        "STM32F407VGT6": {
            "family": ChipFamily.STM32F4,
            "series": "STM32F4",
            "core": CoreArchitecture.CORTEX_M4,
            "cores": [Core(name="CPU", core_type=CoreArchitecture.CORTEX_M4, core_id=0, frequency_hz=168_000_000, has_fpu=True, has_dsp=True)],
            "flash_base": 0x08000000,
            "flash_size": 1_048_576,
            "ram_base": 0x20000000,
            "ram_size": 196_608,
            "max_frequency_hz": 168_000_000,
            "has_etm": False,
            "has_swo": True,
            "has_itm": True,
            "package": "LQFP100",
            "pin_count": 100,
        },
        "STM32F103C8T6": {
            "family": ChipFamily.STM32F1,
            "series": "STM32F1",
            "core": CoreArchitecture.CORTEX_M3,
            "cores": [Core(name="CPU", core_type=CoreArchitecture.CORTEX_M3, core_id=0, frequency_hz=72_000_000, has_fpu=False)],
            "flash_base": 0x08000000,
            "flash_size": 65_536,
            "ram_base": 0x20000000,
            "ram_size": 20_480,
            "max_frequency_hz": 72_000_000,
            "has_etm": False,
            "has_swo": False,
            "has_itm": True,
            "package": "LQFP48",
            "pin_count": 48,
        },
        "STM32H743VIT6": {
            "family": ChipFamily.STM32H7,
            "series": "STM32H7",
            "core": CoreArchitecture.CORTEX_M7,
            "cores": [Core(name="CPU", core_type=CoreArchitecture.CORTEX_M7, core_id=0, frequency_hz=480_000_000, has_fpu=True, has_dsp=True, has_mpu=True)],
            "flash_base": 0x08000000,
            "flash_size": 2_097_152,
            "ram_base": 0x20000000,
            "ram_size": 512_1024,
            "max_frequency_hz": 480_000_000,
            "has_etm": True,
            "has_swo": True,
            "has_itm": True,
            "has_trace_port": True,
            "has_trustzone": True,
            "package": "LQFP100",
            "pin_count": 100,
        },
        "STM32G474RET6": {
            "family": ChipFamily.STM32G4,
            "series": "STM32G4",
            "core": CoreArchitecture.CORTEX_M4,
            "cores": [Core(name="CPU", core_type=CoreArchitecture.CORTEX_M4, core_id=0, frequency_hz=170_000_000, has_fpu=True, has_dsp=True)],
            "flash_base": 0x08000000,
            "flash_size": 512_1024,
            "ram_base": 0x20000000,
            "ram_size": 128_1024,
            "max_frequency_hz": 170_000_000,
            "has_etm": False,
            "has_swo": True,
            "has_itm": True,
            "has_opamp": True,
            "has_comp": True,
            "has_dac": True,
            "package": "LQFP64",
            "pin_count": 64,
        },
        "STM32WB55RG": {
            "family": ChipFamily.STM32WB,
            "series": "STM32WB",
            "core": CoreArchitecture.CORTEX_M4,
            "cores": [
                Core(name="CPU1", core_type=CoreArchitecture.CORTEX_M4, core_id=0, frequency_hz=64_000_000, has_fpu=True),
                Core(name="CPU2", core_type=CoreArchitecture.CORTEX_M0PLUS, core_id=1, frequency_hz=64_000_000),
            ],
            "flash_base": 0x08000000,
            "flash_size": 1_024_1024,
            "ram_base": 0x20000000,
            "ram_size": 256_1024,
            "max_frequency_hz": 64_000_000,
            "has_dual_core": True,
            "has_ble": True,
            "has_802_15_4": True,
            "package": "UFQFPN68",
            "pin_count": 68,
        },
    }

    # JEP106 manufacturer codes for ST
    _JEP106_ST = (0x20, 0x20)  # Manufacturer ID 0x20 (STMicroelectronics)

    async def get_chip_description(self, part_number: str) -> ChipDescription:
        """Get chip description for ST microcontroller."""
        if part_number not in self._CHIP_DB:
            raise ValueError(f"Unknown ST chip: {part_number}")

        info = self._CHIP_DB[part_number]

        chip = ChipDescription(
            part_number=part_number,
            vendor=ChipVendor.ST,
            series=info["series"],
            family=info["family"],
            revision="1.0",
            stepping=SteppingLevel.PRODUCTION,
            cores=info["cores"],
            primary_core=info["cores"][0] if info["cores"] else None,
            temperature_range=TemperatureRange(min_celsius=-40, max_celsius=85),
            max_frequency_hz=info["max_frequency_hz"],
            flash_base=info["flash_base"],
            flash_size=info["flash_size"],
            ram_base=info["ram_base"],
            ram_size=info["ram_size"],
            has_fpu=info["cores"][0].has_fpu if info["cores"] else False,
            has_dsp=info["cores"][0].has_dsp if info["cores"] else False,
            has_mpu=info.get("cores", [None])[0] and info["cores"][0].has_mpu if info["cores"] else False,
            has_etm=info.get("has_etm", False),
            has_itm=info.get("has_itm", False),
            has_swo=info.get("has_swo", False),
            has_trace_port=info.get("has_trace_port", False),
            has_trustzone=info.get("has_trustzone", False),
            package=info.get("package", ""),
            pin_count=info.get("pin_count", 0),
            debug_interface="SWD",
            max_breakpoints=8,
            max_watchpoints=4,
            jep106_manufacturer_id=0x20,
        )

        # Add memory regions
        chip.memory_regions.append(MemoryRegion(
            name="Flash",
            base_address=chip.flash_base,
            size=chip.flash_size,
            region_type="FLASH",
            writable=True,
            executable=True,
        ))
        chip.memory_regions.append(MemoryRegion(
            name="SRAM",
            base_address=chip.ram_base,
            size=chip.ram_size,
            region_type="RAM",
            writable=True,
            readable=True,
        ))

        return chip

    def get_flash_info(self, chip_family: ChipFamily) -> FlashInfo:
        """Get flash information for STM32."""
        flash_base_map = {
            ChipFamily.STM32F4: 0x08000000,
            ChipFamily.STM32F1: 0x08000000,
            ChipFamily.STM32H7: 0x08000000,
            ChipFamily.STM32L4: 0x08000000,
            ChipFamily.STM32G4: 0x08000000,
        }

        base = flash_base_map.get(chip_family, 0x08000000)

        return FlashInfo(
            base_address=base,
            size=0x100000,  # 1MB default
            page_size=2048,
            sectors=[
                (base + 0x000000, 0x04000),   # Sector 0: 16KB
                (base + 0x040000, 0x04000),   # Sector 1: 16KB
                (base + 0x080000, 0x04000),   # Sector 2: 16KB
                (base + 0x0C0000, 0x04000),   # Sector 3: 16KB
                (base + 0x100000, 0x10000),   # Sector 4: 64KB
                (base + 0x200000, 0x180000),  # Sectors 5-11: 384KB x 7
            ],
        )

    def get_reset_sequence(self, chip_family: ChipFamily, mode: str = "default") -> ResetSequence:
        """Get reset sequence for STM32."""
        seq = ResetSequence()

        if mode == "system":
            seq.add_register_write(0xE000ED0C, 0x05FA0004)  # AIRCR = 0x05FA0004 (VECTKEY, SYSRESETREQ)
        elif mode == "core":
            seq.add_register_write(0xE000ED0C, 0x05FA0001)  # VECTRESET
        else:  # default/halt
            seq.add_register_write(0xE000ED0C, 0x05FA0004)  # SYSRESETREQ
            seq.add_delay(100)  # Wait 100ms

        return seq

    def get_capabilities(self, chip_family: ChipFamily) -> CapabilitySet:
        """Get capabilities for ST chips."""
        caps = CapabilitySet(
            entity_id=chip_family.value,
            entity_type="chip",
            capabilities=[
                Capability(name="swd", category=self._cat("debug"), supported=True, max_frequency_hz=10_000_000),
                Capability(name="jtag", category=self._cat("debug"), supported=True, max_frequency_hz=10_000_000),
                Capability(name="swo", category=self._cat("trace"), supported=True, bandwidth_mbps=10.0),
                Capability(name="itm", category=self._cat("trace"), supported=True),
                Capability(name="flash_patch", category=self._cat("memory"), supported=True),
                Capability(name="voltage_sense", category=self._cat("power"), supported=True),
                Capability(name="freertos", category=self._cat("rtos"), supported=True),
            ],
        )

        if chip_family == ChipFamily.STM32H7:
            caps.capabilities.extend([
                Capability(name="etm", category=self._cat("trace"), supported=True),
                Capability(name="trace_port", category=self._cat("trace"), supported=True, bandwidth_mbps=80.0),
                Capability(name="trustzone", category=self._cat("security"), supported=True),
                Capability(name="dual_core", category=self._cat("multi_core"), supported=False),
            ])
        elif chip_family == ChipFamily.STM32WB:
            caps.capabilities.extend([
                Capability(name="dual_core", category=self._cat("multi_core"), supported=True),
                Capability(name="cross_trigger", category=self._cat("multi_core"), supported=True),
            ])

        return caps

    @staticmethod
    def _cat(name: str) -> str:
        """Get category name."""
        return name

    def get_clock_tree(self, chip_family: ChipFamily) -> ClockInfo:
        """Get default clock tree for STM32."""
        if chip_family == ChipFamily.STM32F4:
            return ClockInfo(hse_frequency=8_000_000, sysclk=168_000_000, hclk=168_000_000, pclk1=42_000_000, pclk2=84_000_000)
        elif chip_family == ChipFamily.STM32H7:
            return ClockInfo(hse_frequency=25_000_000, sysclk=480_000_000, hclk=240_000_000, pclk1=120_000_000, pclk2=120_000_000)
        return ClockInfo()


# ============================================================================
# Espressif Plugin
# ============================================================================


class EspressifPlugin(ChipVendorPlugin):
    """Plugin for Espressif ESP32 series."""

    VENDOR_NAME = "Espressif"
    PLUGIN_VERSION = "1.0.0"
    SUPPORTED_FAMILIES = ["ESP32", "ESP32S2", "ESP32S3", "ESP32C3", "ESP32C6", "ESP32H2"]
    TRUST_LEVEL = PluginTrustLevel.TRUSTED

    _CHIP_DB: dict[str, dict[str, Any]] = {
        "ESP32": {
            "family": ChipFamily.ESP32,
            "core": CoreArchitecture.XTENSA,
            "cores": [
                Core(name="PRO_CPU", core_type=CoreArchitecture.XTENSA, core_id=0, frequency_hz=240_000_000),
                Core(name="APP_CPU", core_type=CoreArchitecture.XTENSA, core_id=1, frequency_hz=240_000_000),
            ],
            "flash_base": 0x00000000,
            "flash_size": 4_194_304,
            "ram_base": 0x3FF00000,
            "ram_size": 327_680,
            "max_frequency_hz": 240_000_000,
            "has_wifi": True,
            "has_bt": True,
        },
        "ESP32-S3": {
            "family": ChipFamily.ESP32S3,
            "core": CoreArchitecture.XTENSA,
            "cores": [
                Core(name="PRO_CPU", core_type=CoreArchitecture.XTENSA, core_id=0, frequency_hz=240_000_000),
                Core(name="APP_CPU", core_type=CoreArchitecture.XTENSA, core_id=1, frequency_hz=240_000_000),
            ],
            "flash_base": 0x00000000,
            "flash_size": 8_388_608,
            "ram_base": 0x3FF00000,
            "ram_size": 393_216,
            "max_frequency_hz": 240_000_000,
            "has_wifi": True,
            "has_bt": True,
            "has_usb_otg": True,
            "has_psram": True,
        },
        "ESP32-C3": {
            "family": ChipFamily.ESP32C3,
            "core": CoreArchitecture.RISC_V,
            "cores": [Core(name="CPU", core_type=CoreArchitecture.RISC_V, core_id=0, frequency_hz=160_000_000)],
            "flash_base": 0x00000000,
            "flash_size": 4_194_304,
            "ram_base": 0x3FF00000,
            "ram_size": 393_216,
            "max_frequency_hz": 160_000_000,
            "has_wifi": True,
            "has_ble_5": True,
            "has_risc_v_isa": True,
        },
    }

    async def get_chip_description(self, part_number: str) -> ChipDescription:
        """Get chip description for Espressif chip."""
        if part_number not in self._CHIP_DB:
            raise ValueError(f"Unknown Espressif chip: {part_number}")

        info = self._CHIP_DB[part_number]

        chip = ChipDescription(
            part_number=part_number,
            vendor=ChipVendor.ESPRESSIF,
            series=part_number,
            family=info["family"],
            cores=info["cores"],
            primary_core=info["cores"][0],
            temperature_range=TemperatureRange(min_celsius=-40, max_celsius=85),
            max_frequency_hz=info["max_frequency_hz"],
            flash_base=info["flash_base"],
            flash_size=info["flash_size"],
            ram_base=info["ram_base"],
            ram_size=info["ram_size"],
            has_usb=info.get("has_usb_otg", False),
            package="QFN48",
            pin_count=48,
            debug_interface="JTAG",
        )

        chip.memory_regions.append(MemoryRegion(
            name="Flash",
            base_address=chip.flash_base,
            size=chip.flash_size,
            region_type="FLASH",
            writable=True,
            executable=True,
        ))
        chip.memory_regions.append(MemoryRegion(
            name="SRAM",
            base_address=chip.ram_base,
            size=chip.ram_size,
            region_type="RAM",
            writable=True,
        ))

        return chip

    def get_capabilities(self, chip_family: ChipFamily) -> CapabilitySet:
        """Get capabilities for ESP32."""
        caps = CapabilitySet(
            entity_id=chip_family.value,
            entity_type="chip",
            capabilities=[
                Capability(name="jtag", category="debug", supported=True, max_frequency_hz=20_000_000),
                Capability(name="dual_core", category="multi_core", supported=True),
                Capability(name="flash_patch", category="memory", supported=True),
                Capability(name="voltage_sense", category="power", supported=True),
                Capability(name="reset_detect", category="power", supported=True),
            ],
        )

        if chip_family == ChipFamily.ESP32C3 or chip_family == ChipFamily.ESP32C6:
            caps.capabilities.append(
                Capability(name="riscv", category="debug", supported=True, implementation="riscv_isa"),
            )

        return caps


# ============================================================================
# NXP Plugin
# ============================================================================


class NXPPlugin(ChipVendorPlugin):
    """Plugin for NXP microcontrollers."""

    VENDOR_NAME = "NXP"
    PLUGIN_VERSION = "1.0.0"
    SUPPORTED_FAMILIES = ["NXP_LPC", "NXP_Kinetis", "NXP_iMX_RT", "NXP_S32"]
    TRUST_LEVEL = PluginTrustLevel.TRUSTED

    _CHIP_DB: dict[str, dict[str, Any]] = {
        "LPC1768": {
            "family": ChipFamily.NXP_LPC,
            "series": "LPC1700",
            "core": CoreArchitecture.CORTEX_M3,
            "cores": [Core(name="CPU", core_type=CoreArchitecture.CORTEX_M3, core_id=0, frequency_hz=100_000_000, has_fpu=False)],
            "flash_base": 0x00000000,
            "flash_size": 512_1024,
            "ram_base": 0x20000000,
            "ram_size": 64_1024,
            "max_frequency_hz": 100_000_000,
            "has_ethernet": True,
            "has_usb_host": True,
            "has_usb_device": True,
        },
        "MIMXRT1052": {
            "family": ChipFamily.NXP_IMX_RT,
            "series": "i.MX RT1050",
            "core": CoreArchitecture.CORTEX_M7,
            "cores": [Core(name="CPU", core_type=CoreArchitecture.CORTEX_M7, core_id=0, frequency_hz=600_000_000, has_fpu=True, has_dsp=True)],
            "flash_base": 0x30000000,  # FlexSPI
            "flash_size": 16_777_216,  # 16MB
            "ram_base": 0x20000000,
            "ram_size": 512_1024,
            "max_frequency_hz": 600_000_000,
            "has_flexspi": True,
            "has_eth": True,
            "has_usb_otg": True,
        },
    }

    async def get_chip_description(self, part_number: str) -> ChipDescription:
        """Get chip description for NXP microcontroller."""
        if part_number not in self._CHIP_DB:
            raise ValueError(f"Unknown NXP chip: {part_number}")

        info = self._CHIP_DB[part_number]

        chip = ChipDescription(
            part_number=part_number,
            vendor=ChipVendor.NXP,
            series=info["series"],
            family=info["family"],
            cores=info["cores"],
            primary_core=info["cores"][0],
            temperature_range=TemperatureRange(min_celsius=-40, max_celsius=105),
            max_frequency_hz=info["max_frequency_hz"],
            flash_base=info["flash_base"],
            flash_size=info["flash_size"],
            ram_base=info["ram_base"],
            ram_size=info["ram_size"],
            has_fpu=info["cores"][0].has_fpu,
            has_dsp=info["cores"][0].has_dsp,
            package="LQFP144",
            pin_count=144,
            debug_interface="SWD",
        )

        return chip

    def get_capabilities(self, chip_family: ChipFamily) -> CapabilitySet:
        """Get capabilities for NXP chips."""
        return CapabilitySet(
            entity_id=chip_family.value,
            entity_type="chip",
            capabilities=[
                Capability(name="swd", category="debug", supported=True, max_frequency_hz=20_000_000),
                Capability(name="jtag", category="debug", supported=True),
                Capability(name="flash_patch", category="memory", supported=True),
                Capability(name="trace_port", category="trace", supported=False),
                Capability(name="freertos", category="rtos", supported=True),
            ],
        )


# ============================================================================
# SiFive Plugin
# ============================================================================


class SiFivePlugin(ChipVendorPlugin):
    """Plugin for SiFive RISC-V cores."""

    VENDOR_NAME = "SiFive"
    PLUGIN_VERSION = "1.0.0"
    SUPPORTED_FAMILIES = ["RISC-V", "HiFive"]
    TRUST_LEVEL = PluginTrustLevel.TRUSTED

    _CHIP_DB: dict[str, dict[str, Any]] = {
        "FE310-G002": {
            "family": ChipFamily.RISCV_GENERIC,
            "series": "Freedom E310",
            "core": CoreArchitecture.RISC_V,
            "cores": [Core(name="CPU", core_type=CoreArchitecture.RISC_V, core_id=0, frequency_hz=320_000_000)],
            "flash_base": 0x20000000,
            "flash_size": 16_384,
            "ram_base": 0x80000000,
            "ram_size": 16_777_216,
            "max_frequency_hz": 320_000_000,
            "isa": "RV32IMAC",
            "has_pmp": True,
            "has_clic": True,
        },
        "FU740-C000": {
            "family": ChipFamily.HIFIVE_UNMATCHED,
            "series": "Freedom U740",
            "core": CoreArchitecture.RISC_V,
            "cores": [
                Core(name="U74-MC", core_type=CoreArchitecture.RISC_V, core_id=0, frequency_hz=1_500_000_000),
                Core(name="S7", core_type=CoreArchitecture.RISC_V, core_id=1, frequency_hz=1_500_000_000),
                Core(name="U54", core_type=CoreArchitecture.RISC_V, core_id=2, frequency_hz=1_500_000_000),
                Core(name="U54", core_type=CoreArchitecture.RISC_V, core_id=3, frequency_hz=1_500_000_000),
                Core(name="U54", core_type=CoreArchitecture.RISC_V, core_id=4, frequency_hz=1_500_000_000),
            ],
            "ram_base": 0x80000000,
            "ram_size": 16_777_216,
            "max_frequency_hz": 1_500_000_000,
            "isa": "RV64GC",
            "has_pmp": True,
            "has_clic": True,
            "is_64_bit": True,
        },
    }

    async def get_chip_description(self, part_number: str) -> ChipDescription:
        """Get chip description for SiFive chip."""
        if part_number not in self._CHIP_DB:
            raise ValueError(f"Unknown SiFive chip: {part_number}")

        info = self._CHIP_DB[part_number]

        chip = ChipDescription(
            part_number=part_number,
            vendor=ChipVendor.SIFIVE,
            series=info["series"],
            family=info["family"],
            cores=info["cores"],
            primary_core=info["cores"][0],
            temperature_range=TemperatureRange(min_celsius=-40, max_celsius=125),
            max_frequency_hz=info["max_frequency_hz"],
            flash_base=info.get("flash_base", 0),
            flash_size=info.get("flash_size", 0),
            ram_base=info["ram_base"],
            ram_size=info["ram_size"],
            package="QFN64",
            pin_count=64,
            debug_interface="JTAG",
        )

        return chip

    def get_capabilities(self, chip_family: ChipFamily) -> CapabilitySet:
        """Get capabilities for SiFive RISC-V cores."""
        return CapabilitySet(
            entity_id=chip_family.value,
            entity_type="chip",
            capabilities=[
                Capability(name="jtag", category="debug", supported=True, max_frequency_hz=10_000_000),
                Capability(name="riscv_debug", category="debug", supported=True, implementation="riscv_dm"),
                Capability(name="flash_patch", category="memory", supported=True),
                Capability(name="pmp", category="memory", supported=True),
                Capability(name="clic", category="debug", supported=True),
            ],
        )


# ============================================================================
# Plugin Loader Function
# ============================================================================


def load_plugin() -> ChipVendorPlugin:
    """Load the default plugin (STMicroelectronics).

    This function is used as the entry point for plugin loading.
    """
    return STPlugin()
