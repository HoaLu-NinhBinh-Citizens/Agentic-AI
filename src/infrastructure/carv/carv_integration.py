"""CARV Firmware Integration - AI_SUPPORT tooling for CARV.

This module provides AI_SUPPORT with tools to:
1. Read/analyze CARV firmware
2. Build CARV firmware
3. Flash to hardware
4. Debug and verify

CARV Structure:
- EngineCar: Main application (LED Red/Green)
- RemoteControl: Remote control application
- BootLoader: Bootloader for OTA updates
- Target: STM32F407VGT6 (1MB Flash, 192KB RAM)
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


# CARV Repository Path
CARV_ROOT = Path(r"C:\Users\thang\Desktop\carv")
CARV_SOFTWARE = CARV_ROOT / "software"
CARV_HARDWARE = CARV_ROOT / "hardware"
CARV_MECHANICAL = CARV_ROOT / "mechanical"


class CarProject(Enum):
    """CARV project variants."""
    ENGINE_CAR = "EngineCar"
    REMOTE_CONTROL = "RemoteControl"


class BuildTarget(Enum):
    """Build target configurations."""
    BOOTLOADER = "BootLoader"
    CAR_ENGINE = "CarEngine"


@dataclass
class CARVFirmwareInfo:
    """Information about CARV firmware."""
    project: CarProject
    target: BuildTarget
    mcu: str = "STM32F407VGT6"
    flash_size_kb: int = 1024
    ram_size_kb: int = 192
    clock_hz: int = 8_000_000  # HSI
    has_freertos: bool = True
    has_bootloader: bool = True


@dataclass
class BuildResult:
    """Result of firmware build."""
    success: bool
    project: str
    target: str
    output_file: Optional[Path] = None
    elf_file: Optional[Path] = None
    map_file: Optional[Path] = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
    built_at: datetime = field(default_factory=datetime.now)


@dataclass
class FlashResult:
    """Result of firmware flash."""
    success: bool
    project: str
    address: int
    bytes_written: int = 0
    error: Optional[str] = None
    duration_ms: float = 0.0


class CARVRepository:
    """Access CARV firmware repository.
    
    Usage:
    ```python
    repo = CARVRepository()
    
    # Get firmware info
    info = repo.get_firmware_info(CarProject.ENGINE_CAR)
    
    # Read source files
    main_c = repo.read_source("EngineCar", "main.c")
    
    # Analyze project structure
    structure = repo.get_project_structure(CarProject.ENGINE_CAR)
    ```
    """
    
    def __init__(self, root: Path | None = None):
        self.root = root or CARV_ROOT
        self.software = self.root / "software"
        
        if not self.root.exists():
            raise ValueError(f"CARV root not found: {self.root}")
    
    def exists(self) -> bool:
        """Check if CARV repository exists."""
        return self.root.exists() and self.software.exists()
    
    def get_project_path(self, project: CarProject) -> Path:
        """Get path to project folder."""
        return self.software / project.value
    
    def get_target_path(self, project: CarProject, target: BuildTarget) -> Path:
        """Get path to target folder."""
        return self.get_project_path(project) / "Project" / "Chip" / "Stm32F407" / target.value
    
    def get_firmware_info(self, project: CarProject) -> CARVFirmwareInfo:
        """Get firmware information for project."""
        return CARVFirmwareInfo(
            project=project,
            target=BuildTarget.CAR_ENGINE if project == CarProject.ENGINE_CAR else BuildTarget.BOOTLOADER,
        )
    
    def read_source(self, project: str, filename: str) -> str | None:
        """Read a source file from project.
        
        Args:
            project: Project name (e.g., "EngineCar")
            filename: Source filename (e.g., "main.c")
        
        Returns:
            File contents or None if not found
        """
        project_path = self.software / project
        
        # Search for file in common locations
        search_patterns = [
            project_path / "Project" / "Chip" / "Stm32F407" / "**" / filename,
            project_path / "Driver" / "**" / filename,
            project_path / "Middleware" / "**" / filename,
        ]
        
        for pattern in search_patterns:
            matches = list(project_path.glob(str(pattern.relative_to(project_path)))
                          if project_path in pattern.parents else [])
            if not matches:
                continue
            
            for match in matches:
                if match.name == filename and match.is_file():
                    return match.read_text()
        
        return None
    
    def get_project_structure(self, project: CarProject) -> dict[str, Any]:
        """Get project file structure.
        
        Returns:
            Dictionary with file categories and paths
        """
        project_path = self.get_project_path(project)
        
        structure = {
            "root": str(project_path),
            "projects": [],
            "drivers": [],
            "middleware": [],
            "kernel": [],
            "common": [],
        }
        
        # Walk through project
        for root, dirs, files in os.walk(project_path):
            root_path = Path(root)
            rel_path = root_path.relative_to(project_path)
            
            # Categorize by path
            if "Project" in rel_path.parts:
                structure["projects"].append(str(rel_path))
            elif "Driver" in rel_path.parts:
                structure["drivers"].append(str(rel_path))
            elif "Middleware" in rel_path.parts:
                structure["middleware"].append(str(rel_path))
            elif "Kernel" in rel_path.parts:
                structure["kernel"].append(str(rel_path))
            elif "Common" in rel_path.parts:
                structure["common"].append(str(rel_path))
        
        return structure
    
    def find_files(self, project: CarProject, pattern: str) -> list[Path]:
        """Find files matching pattern in project.
        
        Args:
            project: Project to search
            pattern: Glob pattern (e.g., "*.c", "**/main.c")
        
        Returns:
            List of matching file paths
        """
        project_path = self.get_project_path(project)
        return list(project_path.glob(pattern))
    
    def get_main_files(self, project: CarProject, target: BuildTarget) -> dict[str, str]:
        """Get main source files for a target.
        
        Returns:
            Dict with filenames and paths
        """
        target_path = self.get_target_path(project, target)
        
        files = {}
        for pattern in ["**/main.c", "**/main.h", "**/startup_*.s"]:
            for f in target_path.glob(pattern):
                files[f.name] = str(f)
        
        return files


class CARVBuilder:
    """Build CARV firmware.
    
    Usage:
    ```python
    builder = CARVBuilder()
    
    # Build EngineCar
    result = await builder.build(CarProject.ENGINE_CAR, BuildTarget.CAR_ENGINE)
    
    if result.success:
        print(f"Built: {result.elf_file}")
    ```
    """
    
    def __init__(self, repo: CARVRepository | None = None):
        self.repo = repo or CARVRepository()
        self._lock = asyncio.Lock()
    
    async def build(
        self,
        project: CarProject,
        target: BuildTarget,
        clean: bool = False,
    ) -> BuildResult:
        """Build firmware for target.
        
        Args:
            project: Project to build
            target: Target within project
            clean: Whether to clean before build
        
        Returns:
            BuildResult with success status and output paths
        """
        async with self._lock:
            start_time = datetime.now()
            
            # Find build script
            build_script = self.repo.software / "Build.bat"
            if not build_script.exists():
                return BuildResult(
                    success=False,
                    project=project.value,
                    target=target.value,
                    errors=["Build.bat not found"],
                    duration_ms=0,
                )
            
            # Build command
            cmd = [str(build_script), project.value, target.value]
            if clean:
                cmd.append("clean")
            
            try:
                logger.info("building_carfirmware", project=project.value, target=target.value)
                
                process = await asyncio.create_subprocess_exec(
                    "cmd", "/c", *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(self.repo.software),
                )
                
                stdout, stderr = await process.communicate()
                
                duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                
                if process.returncode != 0:
                    return BuildResult(
                        success=False,
                        project=project.value,
                        target=target.value,
                        errors=[stderr.decode() if stderr else "Unknown error"],
                        duration_ms=duration_ms,
                    )
                
                # Find output files
                output_dir = self.repo.get_target_path(project, target) / "Output"
                elf_file = output_dir / f"{target.value}.elf"
                
                return BuildResult(
                    success=True,
                    project=project.value,
                    target=target.value,
                    elf_file=elf_file if elf_file.exists() else None,
                    duration_ms=duration_ms,
                )
                
            except Exception as e:
                return BuildResult(
                    success=False,
                    project=project.value,
                    target=target.value,
                    errors=[str(e)],
                    duration_ms=0,
                )


class CARVFlashing:
    """Flash firmware to CARV hardware.
    
    Usage:
    ```python
    flasher = CARVFlashing()
    
    # Flash EngineCar to STM32F407
    result = await flasher.flash(
        project=CarProject.ENGINE_CAR,
        target=BuildTarget.CAR_ENGINE,
        elf_file="path/to/firmware.elf",
    )
    ```
    """
    
    def __init__(self, jlink_path: str = "JLink.exe"):
        self.jlink_path = jlink_path
        self._lock = asyncio.Lock()
    
    async def flash(
        self,
        project: CarProject,
        target: BuildTarget,
        elf_file: Path,
        address: int = 0x08000000,
        verify: bool = True,
    ) -> FlashResult:
        """Flash firmware to device.
        
        Args:
            project: Project name
            target: Target name
            elf_file: Path to ELF file
            address: Flash address
            verify: Whether to verify after flash
        
        Returns:
            FlashResult with success status
        """
        async with self._lock:
            start_time = datetime.now()
            
            if not elf_file.exists():
                return FlashResult(
                    success=False,
                    project=project.value,
                    address=address,
                    error=f"ELF file not found: {elf_file}",
                )
            
            try:
                logger.info("flashing_carfirmware", project=project.value, elf=str(elf_file))
                
                # JLink commands for flashing
                jlink_cmds = [
                    f"device STM32F407VG",
                    f"loadfile {elf_file} {address:#010x}",
                ]
                
                if verify:
                    jlink_cmds.append("verify")
                
                jlink_cmds.append("r")  # Reset
                jlink_cmds.append("q")   # Quit
                
                # Execute JLink
                cmd_str = "\n".join(jlink_cmds)
                
                process = await asyncio.create_subprocess_exec(
                    self.jlink_path,
                    "-CommandFile", "/dev/stdin",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                
                stdout, stderr = await process.communicate(input=cmd_str.encode())
                
                duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                
                if process.returncode != 0:
                    return FlashResult(
                        success=False,
                        project=project.value,
                        address=address,
                        error=stderr.decode() if stderr else "Flash failed",
                        duration_ms=duration_ms,
                    )
                
                return FlashResult(
                    success=True,
                    project=project.value,
                    address=address,
                    bytes_written=elf_file.stat().st_size,
                    duration_ms=duration_ms,
                )
                
            except Exception as e:
                return FlashResult(
                    success=False,
                    project=project.value,
                    address=address,
                    error=str(e),
                    duration_ms=0,
                )
    
    async def read_memory(self, address: int, size: int) -> bytes | None:
        """Read memory from device.
        
        Args:
            address: Memory address
            size: Number of bytes to read
        
        Returns:
            Memory contents or None on error
        """
        try:
            jlink_cmds = [
                f"device STM32F407VG",
                f"mem {address:#010x} {size}",
                "q",
            ]
            
            cmd_str = "\n".join(jlink_cmds)
            
            process = await asyncio.create_subprocess_exec(
                self.jlink_path,
                "-CommandFile", "/dev/stdin",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, _ = await process.communicate(input=cmd_str.encode())
            
            # Parse output (simplified)
            return stdout
            
        except Exception as e:
            logger.error("memory_read_failed", address=hex(address), error=str(e))
            return None


# Global instances
_repo: Optional[CARVRepository] = None
_builder: Optional[CARVBuilder] = None
_flasher: Optional[CARVFlashing] = None


def get_crv_repository() -> CARVRepository:
    """Get global CARV repository instance."""
    global _repo
    if _repo is None:
        _repo = CARVRepository()
    return _repo


def get_crv_builder() -> CARVBuilder:
    """Get global CARV builder instance."""
    global _builder
    if _builder is None:
        _builder = CARVBuilder()
    return _builder


def get_crv_flasher() -> CARVFlashing:
    """Get global CARV flasher instance."""
    global _flasher
    if _flasher is None:
        _flasher = CARVFlashing()
    return _flasher
