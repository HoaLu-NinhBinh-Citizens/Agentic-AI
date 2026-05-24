"""AI_SUPPORT CARV Tools - High-level tools for AI to interact with CARV.

These tools provide AI-powered access to CARV firmware engineering tasks.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog

from src.infrastructure.carv.carv_integration import (
    CARVRepository,
    CARVBuilder,
    CARVFlashing,
    CarProject,
    BuildTarget,
)

logger = structlog.get_logger(__name__)


@dataclass
class FirmwareAnalysis:
    """Result of firmware analysis."""
    project: str
    target: str
    mcu: str
    components: list[str]
    tasks: list[str]
    gpio_pins: list[str]
    clock_config: dict[str, Any]
    errors: list[str] = field(default_factory=list)


@dataclass
class EngineeringTask:
    """An engineering task for CARV."""
    id: str
    type: str  # "analysis", "build", "flash", "debug"
    project: str
    target: str
    status: str = "pending"
    result: Any = None
    created_at: datetime = field(default_factory=datetime.now)


class CARVTools:
    """High-level tools for AI-powered CARV engineering.
    
    Usage:
    ```python
    tools = CARVTools()
    
    # Analyze firmware
    analysis = await tools.analyze_firmware(
        project=CarProject.ENGINE_CAR,
        target=BuildTarget.CAR_ENGINE,
    )
    
    # Build firmware
    result = await tools.build_firmware(
        project=CarProject.ENGINE_CAR,
        target=BuildTarget.CAR_ENGINE,
    )
    
    # Flash to hardware
    result = await tools.flash_firmware(
        project=CarProject.ENGINE_CAR,
        target=BuildTarget.CAR_ENGINE,
        elf_file="path/to/firmware.elf",
    )
    ```
    """
    
    def __init__(self):
        self.repo = CARVRepository()
        self.builder = CARVBuilder(self.repo)
        self.flasher = CARVFlashing()
    
    async def analyze_firmware(
        self,
        project: CarProject,
        target: BuildTarget,
    ) -> FirmwareAnalysis:
        """Analyze firmware and extract key information.
        
        Args:
            project: Project to analyze
            target: Target within project
        
        Returns:
            FirmwareAnalysis with components, tasks, and configuration
        """
        logger.info("analyzing_firmware", project=project.value, target=target.value)
        
        # Get firmware info
        info = self.repo.get_firmware_info(project)
        
        # Read main source
        main_c = self.repo.read_source(project.value, "main.c") or ""
        
        # Extract components
        components = []
        if "HAL_Init" in main_c:
            components.append("HAL")
        if "osKernelStart" in main_c:
            components.append("CMSIS-RTOS")
        if "xTaskCreate" in main_c:
            components.append("FreeRTOS Tasks")
        if "HAL_GPIO" in main_c:
            components.append("GPIO")
        if "HAL_TIM" in main_c:
            components.append("Timer")
        if "HAL_UART" in main_c:
            components.append("UART")
        if "HAL_I2C" in main_c:
            components.append("I2C")
        if "HAL_SPI" in main_c:
            components.append("SPI")
        
        # Extract tasks
        tasks = []
        import re
        task_pattern = r"void\s+(vTask\w+)"
        for match in re.finditer(task_pattern, main_c):
            tasks.append(match.group(1))
        
        # Extract GPIO pins
        gpio_pins = []
        gpio_pattern = r"(LED_\w+)"
        for match in re.finditer(gpio_pattern, main_c):
            pin = match.group(1)
            if pin not in gpio_pins:
                gpio_pins.append(pin)
        
        # Extract clock config
        clock_config = {}
        if "HSI" in main_c:
            clock_config["oscillator"] = "HSI"
            clock_config["frequency"] = "8MHz"
        if "PLL" in main_c:
            clock_config["pll"] = "enabled"
        
        return FirmwareAnalysis(
            project=project.value,
            target=target.value,
            mcu=info.mcu,
            components=components,
            tasks=tasks,
            gpio_pins=gpio_pins,
            clock_config=clock_config,
        )
    
    async def build_firmware(
        self,
        project: CarProject,
        target: BuildTarget,
        clean: bool = False,
    ) -> dict[str, Any]:
        """Build firmware for target.
        
        Args:
            project: Project to build
            target: Target within project
            clean: Whether to clean before build
        
        Returns:
            Dict with build result
        """
        logger.info("building_firmware", project=project.value, target=target.value)
        
        result = await self.builder.build(project, target, clean)
        
        return {
            "success": result.success,
            "project": result.project,
            "target": result.target,
            "elf_file": str(result.elf_file) if result.elf_file else None,
            "errors": result.errors,
            "duration_ms": result.duration_ms,
        }
    
    async def flash_firmware(
        self,
        project: CarProject,
        target: BuildTarget,
        elf_file: str,
        verify: bool = True,
    ) -> dict[str, Any]:
        """Flash firmware to device.
        
        Args:
            project: Project name
            target: Target name
            elf_file: Path to ELF file
            verify: Whether to verify after flash
        
        Returns:
            Dict with flash result
        """
        logger.info("flashing_firmware", project=project.value, elf=elf_file)
        
        from pathlib import Path
        
        result = await self.flasher.flash(
            project=project,
            target=target,
            elf_file=Path(elf_file),
            verify=verify,
        )
        
        return {
            "success": result.success,
            "project": result.project,
            "address": hex(result.address),
            "bytes_written": result.bytes_written,
            "error": result.error,
            "duration_ms": result.duration_ms,
        }
    
    async def get_project_status(self) -> dict[str, Any]:
        """Get status of all CARV projects.
        
        Returns:
            Dict with project statuses
        """
        status = {
            "repository": str(self.repo.root),
            "exists": self.repo.exists(),
            "projects": {},
        }
        
        for project in CarProject:
            project_path = self.repo.get_project_path(project)
            structure = self.repo.get_project_structure(project)
            
            status["projects"][project.value] = {
                "path": str(project_path),
                "exists": project_path.exists(),
                "file_count": len(structure.get("projects", [])),
                "targets": [
                    t.value for t in BuildTarget
                ],
            }
        
        return status
    
    async def search_code(
        self,
        project: CarProject,
        pattern: str,
    ) -> list[dict[str, str]]:
        """Search for pattern in project source code.
        
        Args:
            project: Project to search
            pattern: Search pattern (regex supported)
        
        Returns:
            List of matches with file and line info
        """
        import re
        
        matches = []
        project_path = self.repo.get_project_path(project)
        
        # Search all C files
        for c_file in project_path.glob("**/*.c"):
            try:
                content = c_file.read_text(encoding='utf-8', errors='ignore')
                for i, line in enumerate(content.split('\n'), 1):
                    if re.search(pattern, line):
                        matches.append({
                            "file": str(c_file.relative_to(project_path)),
                            "line": i,
                            "content": line.strip(),
                        })
            except Exception:
                pass
        
        return matches
    
    async def compare_projects(
        self,
        project1: CarProject,
        project2: CarProject,
    ) -> dict[str, Any]:
        """Compare two CARV projects.
        
        Args:
            project1: First project
            project2: Second project
        
        Returns:
            Dict with comparison results
        """
        analysis1 = await self.analyze_firmware(
            project1,
            BuildTarget.CAR_ENGINE if "Engine" in project1.value else BuildTarget.BOOTLOADER,
        )
        
        analysis2 = await self.analyze_firmware(
            project2,
            BuildTarget.CAR_ENGINE if "Engine" in project2.value else BuildTarget.BOOTLOADER,
        )
        
        return {
            "project1": {
                "name": analysis1.project,
                "components": analysis1.components,
                "tasks": analysis1.tasks,
            },
            "project2": {
                "name": analysis2.project,
                "components": analysis2.components,
                "tasks": analysis2.tasks,
            },
            "differences": {
                "unique_to_1": list(set(analysis1.components) - set(analysis2.components)),
                "unique_to_2": list(set(analysis2.components) - set(analysis1.components)),
                "common": list(set(analysis1.components) & set(analysis2.components)),
            },
        }


# Global instance
_tools: CARVTools | None = None


def get_crv_tools() -> CARVTools:
    """Get global CARV tools instance."""
    global _tools
    if _tools is None:
        _tools = CARVTools()
    return _tools
