"""Target registry and configuration management."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from .embedded_target import (
    ChipFamily,
    CoreType,
    DebugInterface,
    DebugProbeConfig,
    DebugProbeType,
    FirmwareInfo,
    FirmwareVersion,
    SerialConfig,
    TargetConfig,
    Toolchain,
    ToolchainConfig,
)

# Re-export these from embedded_target for backward compatibility
ChipDescription = ChipFamily  # Placeholder - actual ChipDescription is in embedded_target

if TYPE_CHECKING:
    from .embedded_target import ChipDescription


@dataclass
class TargetRegistryConfig:
    """Configuration for target registry."""
    
    config_dir: Path = field(default_factory=lambda: Path("configs/targets"))
    auto_detect_enabled: bool = True
    cache_loaded: bool = True
    svd_cache_dir: Path | None = None


@dataclass
class AutoDetectResult:
    """Result of auto-detection."""
    
    probe_serial: str | None
    probe_type: DebugProbeType
    idcode: int | None
    suggested_chip: ChipFamily | None
    suggested_target_id: str | None
    confidence: float = 0.0


class TargetRegistry:
    """Registry for managing embedded targets."""
    
    def __init__(self, config: TargetRegistryConfig | None = None):
        self.config = config or TargetRegistryConfig()
        self._targets: dict[str, TargetConfig] = {}
        self._chip_database: dict[str, ChipDescription] = {}
        self._loaded = False
    
    async def load(self) -> None:
        """Load all targets from config directory."""
        if self._loaded and self.config.cache_loaded:
            return
        
        self._targets.clear()
        self._chip_database.clear()
        
        config_dir = self.config.config_dir
        if not config_dir.exists():
            config_dir.mkdir(parents=True, exist_ok=True)
            await self._create_example_configs(config_dir)
            return
        
        for yaml_file in config_dir.glob("*.yaml"):
            try:
                targets = await self._load_yaml_file(yaml_file)
                for target in targets:
                    self._targets[target.id] = target
            except Exception as e:
                print(f"Error loading {yaml_file}: {e}")
        
        await self._load_chip_database()
        self._loaded = True
    
    async def _load_yaml_file(self, path: Path) -> list[TargetConfig]:
        """Load targets from YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        
        targets = []
        yaml_targets = data.get("targets", [data.get("target")])
        
        for t in yaml_targets:
            if t is None:
                continue
            target = self._parse_target_config(t)
            targets.append(target)
        
        return targets
    
    def _parse_target_config(self, data: dict[str, Any]) -> TargetConfig:
        """Parse target configuration from dict."""
        chip_data = data.get("chip", {})
        chip = ChipDescription(
            family=ChipFamily(chip_data.get("family", "UNKNOWN")),
            part_number=chip_data.get("part_number", "Unknown"),
            core=CoreType(chip_data.get("core", "Cortex-M4")),
            svd_file=chip_data.get("svd_file"),
            has_fpu=chip_data.get("fpu", False),
            has_dsp=chip_data.get("dsp", False),
            has_mpu=chip_data.get("mpu", False),
            manufacturer=chip_data.get("manufacturer", "Unknown"),
            description=chip_data.get("description", ""),
        )
        
        # Parse memory regions
        memory_data = data.get("memory", {})
        for mem_type, mem_info in memory_data.items():
            if isinstance(mem_info, dict):
                chip.memory_regions.append(
                    type("MemoryRegion", (), {
                        "name": mem_type,
                        "base_address": int(mem_info.get("base", 0), 0) if isinstance(mem_info.get("base"), str) else mem_info.get("base", 0),
                        "size": int(mem_info.get("size", 0), 0) if isinstance(mem_info.get("size"), str) else mem_info.get("size", 0),
                        "region_type": mem_type.upper(),
                    })()
                )
        
        probe_data = data.get("debug_probe", {})
        probe = DebugProbeConfig(
            probe_type=DebugProbeType(probe_data.get("type", "CMSIS-DAP")),
            interface=DebugInterface(probe_data.get("interface", "SWD")),
            speed_khz=probe_data.get("speed", 4000),
            serial=probe_data.get("serial"),
            jtag_chain_position=probe_data.get("jtag_chain_position", 0),
        )
        
        toolchain_data = data.get("toolchain", {})
        toolchain = ToolchainConfig(
            name=Toolchain(toolchain_data.get("name", "GCC_ARM")),
            prefix=toolchain_data.get("prefix", "arm-none-eabi-"),
            objcopy=toolchain_data.get("objcopy", "arm-none-eabi-objcopy"),
            gdb=toolchain_data.get("gdb", "arm-none-eabi-gdb"),
            openocd_config=toolchain_data.get("openocd_config"),
        )
        
        serial_data = data.get("serial", {})
        serial = SerialConfig(
            enabled=serial_data.get("enabled", False),
            port=serial_data.get("port"),
            baudrate=serial_data.get("baudrate", 115200),
            parity=serial_data.get("parity", "none"),
            stopbits=serial_data.get("stopbits", 1),
        )
        
        firmware_data = data.get("firmware", {})
        firmware = None
        if firmware_data:
            firmware = FirmwareInfo(
                version=FirmwareVersion(
                    version=firmware_data.get("version", "0.0.0"),
                    git_hash=firmware_data.get("git_hash", ""),
                    target_chip=chip.family,
                ),
                elf_path=firmware_data.get("elf_file"),
                binary_path=firmware_data.get("binary_file"),
                flash_address=int(firmware_data.get("flash_address", "0x08000000"), 0) if isinstance(firmware_data.get("flash_address"), str) else firmware_data.get("flash_address", 0x08000000),
            )
        
        return TargetConfig(
            id=data.get("id", "unknown"),
            name=data.get("name", "Unknown Target"),
            chip=chip,
            debug_probe=probe,
            toolchain=toolchain,
            serial=serial,
            firmware=firmware,
        )
    
    async def _load_chip_database(self) -> None:
        """Load chip database."""
        chip_db: dict[str, dict[str, Any]] = {
            "STM32F407VGT6": {
                "family": ChipFamily.STM32F4,
                "core": CoreType.CORTEX_M4,
                "has_fpu": True,
                "has_dsp": True,
                "svd_file": "STM32F407.svd",
            },
            "STM32F103C8T6": {
                "family": ChipFamily.STM32F1,
                "core": CoreType.CORTEX_M3,
                "has_fpu": False,
                "has_dsp": False,
                "svd_file": "STM32F103.svd",
            },
            "STM32H743VIT6": {
                "family": ChipFamily.STM32H7,
                "core": CoreType.CORTEX_M7,
                "has_fpu": True,
                "has_dsp": True,
                "has_mpu": True,
                "svd_file": "STM32H743.svd",
            },
        }
        
        for part_number, info in chip_db.items():
            self._chip_database[part_number] = ChipDescription(
                part_number=part_number,
                family=info["family"],
                core=info["core"],
                svd_file=info.get("svd_file"),
                has_fpu=info.get("has_fpu", False),
                has_dsp=info.get("has_dsp", False),
                has_mpu=info.get("has_mpu", False),
            )
    
    async def _create_example_configs(self, config_dir: Path) -> None:
        """Create example target configurations."""
        stm32f4_config = {
            "targets": [
                {
                    "id": "stm32f4-discovery",
                    "name": "STM32F4 Discovery Kit",
                    "chip": {
                        "family": "STM32F4",
                        "part_number": "STM32F407VGT6",
                        "core": "Cortex-M4",
                        "fpu": True,
                        "dsp": True,
                    },
                    "memory": {
                        "FLASH": {"base": "0x08000000", "size": "0x100000"},
                        "SRAM1": {"base": "0x20000000", "size": "0x20000"},
                        "SRAM2": {"base": "0x20020000", "size": "0x10000"},
                    },
                    "debug_probe": {
                        "type": "STLINK",
                        "interface": "SWD",
                        "speed": 4000,
                    },
                    "toolchain": {
                        "name": "GCC_ARM",
                        "prefix": "arm-none-eabi-",
                    },
                    "serial": {
                        "enabled": True,
                        "port": "COM3",
                        "baudrate": 115200,
                    },
                }
            ]
        }
        
        esp32_config = {
            "targets": [
                {
                    "id": "esp32-devkit",
                    "name": "ESP32 DevKit",
                    "chip": {
                        "family": "ESP32",
                        "part_number": "ESP32-WROOM-32",
                        "core": "Xtensa",
                    },
                    "memory": {
                        "FLASH": {"base": "0x00000000", "size": "0x400000"},
                        "SRAM": {"base": "0x3FF00000", "size": "0x50000"},
                    },
                    "debug_probe": {
                        "type": "ESP_PROG",
                        "interface": "JTAG",
                        "speed": 5000,
                    },
                    "toolchain": {
                        "name": "ESP_IDF",
                        "prefix": "xtensa-esp32-elf-",
                    },
                }
            ]
        }
        
        with open(config_dir / "stm32f4-discovery.yaml", "w") as f:
            yaml.dump(stm32f4_config, f, default_flow_style=False)
        
        with open(config_dir / "esp32-devkit.yaml", "w") as f:
            yaml.dump(esp32_config, f, default_flow_style=False)
    
    async def list_targets(self) -> list[TargetConfig]:
        """List all registered targets."""
        if not self._loaded:
            await self.load()
        return list(self._targets.values())
    
    async def get_target(self, target_id: str) -> TargetConfig | None:
        """Get target by ID."""
        if not self._loaded:
            await self.load()
        return self._targets.get(target_id)
    
    async def add_target(self, target: TargetConfig) -> None:
        """Add or update a target."""
        self._targets[target.id] = target
    
    async def remove_target(self, target_id: str) -> bool:
        """Remove a target."""
        if target_id in self._targets:
            del self._targets[target_id]
            return True
        return False
    
    async def save_target(self, target: TargetConfig) -> Path:
        """Save target to YAML file."""
        if not self._loaded:
            await self.load()
        
        config_dir = self.config.config_dir
        config_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = config_dir / f"{target.id}.yaml"
        
        data = {
            "targets": [
                {
                    "id": target.id,
                    "name": target.name,
                    "chip": {
                        "family": target.chip.family.value,
                        "part_number": target.chip.part_number,
                        "core": target.chip.core.value,
                        "fpu": target.chip.has_fpu,
                        "dsp": target.chip.has_dsp,
                        "svd_file": target.chip.svd_file,
                    },
                    "debug_probe": {
                        "type": target.debug_probe.probe_type.value,
                        "interface": target.debug_probe.interface.value,
                        "speed": target.debug_probe.speed_khz,
                        "serial": target.debug_probe.serial,
                    },
                    "toolchain": {
                        "name": target.toolchain.name.value,
                        "prefix": target.toolchain.prefix,
                    },
                }
            ]
        }
        
        with open(file_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)
        
        self._targets[target.id] = target
        return file_path
    
    async def auto_detect(self) -> list[AutoDetectResult]:
        """Auto-detect connected probes and targets."""
        results: list[AutoDetectResult] = []
        
        # TODO: Implement actual probe detection
        # This would use pyocd or pylink to scan for probes
        
        return results
    
    async def get_chip_info(self, part_number: str) -> ChipDescription | None:
        """Get chip information."""
        if not self._loaded:
            await self.load()
        return self._chip_database.get(part_number)
    
    async def find_targets_by_family(self, family: ChipFamily) -> list[TargetConfig]:
        """Find targets by chip family."""
        if not self._loaded:
            await self.load()
        return [t for t in self._targets.values() if t.chip.family == family]


class FirmwareRegistry:
    """Registry for firmware versions."""
    
    def __init__(self, storage_path: Path | None = None):
        self.storage_path = storage_path or Path("data/firmware")
        self._versions: dict[str, list[FirmwareVersion]] = {}
    
    async def register_version(
        self,
        target_id: str,
        version: FirmwareVersion,
    ) -> None:
        """Register a firmware version."""
        if target_id not in self._versions:
            self._versions[target_id] = []
        self._versions[target_id].append(version)
    
    async def get_versions(self, target_id: str) -> list[FirmwareVersion]:
        """Get all versions for a target."""
        return self._versions.get(target_id, [])
    
    async def get_latest_version(self, target_id: str) -> FirmwareVersion | None:
        """Get latest version for a target."""
        versions = await self.get_versions(target_id)
        if not versions:
            return None
        return max(versions, key=lambda v: v.build_timestamp)
    
    async def check_compatibility(
        self,
        version: FirmwareVersion,
        target_family: ChipFamily,
    ) -> bool:
        """Check if firmware is compatible with target."""
        return version.target_chip == target_family


class CompatibilityMatrix:
    """Matrix of target ↔ firmware compatibility."""
    
    def __init__(self):
        self._matrix: dict[str, set[str]] = {}  # target_family -> set of compatible versions
    
    def add_compatibility(self, target_family: str, version_constraint: str) -> None:
        """Add compatibility entry."""
        if target_family not in self._matrix:
            self._matrix[target_family] = set()
        self._matrix[target_family].add(version_constraint)
    
    def is_compatible(
        self,
        target_family: ChipFamily,
        version: FirmwareVersion,
    ) -> tuple[bool, list[str]]:
        """Check compatibility with detailed results."""
        family_str = target_family.value
        warnings: list[str] = []
        
        if family_str not in self._matrix:
            warnings.append(f"Unknown target family: {family_str}")
            return True, warnings
        
        # Check toolchain version
        if version.min_toolchain_version:
            warnings.append(
                f"Requires toolchain >= {version.min_toolchain_version}"
            )
        
        return True, warnings
