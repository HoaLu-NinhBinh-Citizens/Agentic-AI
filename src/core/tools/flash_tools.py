"""
Flash Tools - Hardware Programming Tools

Provides tools for flashing and programming hardware:
- Flash firmware to MCU
- Verify flash contents
- Read flash memory
- Hardware connection management
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.core.tools.schema import (
    Tool,
    ToolParameter,
    ToolResult,
    ToolPermission,
    ToolCategory,
    ParameterType,
)

logger = logging.getLogger(__name__)


class FlashStatus(Enum):
    """Flash operation status."""
    IDLE = "idle"
    CONNECTING = "connecting"
    ERASING = "erasing"
    PROGRAMMING = "programming"
    VERIFYING = "verifying"
    SUCCESS = "success"
    FAILED = "failed"
    DISCONNECTED = "disconnected"


@dataclass
class FlashConfig:
    """Configuration for flash operations."""
    target: str = "STM32"
    interface: str = "SWD"  # SWD, JTAG, UART, SPI
    speed: int = 4000  # kHz
    reset_strategy: str = "hardware"  # hardware, software, none
    timeout: int = 60  # seconds


@dataclass
class FlashProgress:
    """Progress of a flash operation."""
    operation: str
    current_bytes: int = 0
    total_bytes: int = 0
    percentage: float = 0.0
    current_address: int = 0
    elapsed_seconds: float = 0.0
    status: FlashStatus = FlashStatus.IDLE


@dataclass
class FlashResult:
    """Result of a flash operation."""
    success: bool
    operation: str
    bytes_written: int = 0
    bytes_verified: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None
    device_info: Optional[Dict[str, Any]] = None


# Permission Guard for Flash Operations

class FlashPermissionGuard:
    """
    Permission guard for flash operations.

    Validates that the requester has FLASH permission before
    allowing hardware flashing operations.
    """

    def __init__(self):
        self._whitelist: set = set()
        self._blacklist: set = set()

    def add_whitelist(self, agent_id: str) -> None:
        """Add agent to whitelist (can always flash)."""
        self._whitelist.add(agent_id)
        self._blacklist.discard(agent_id)

    def add_blacklist(self, agent_id: str) -> None:
        """Add agent to blacklist (cannot flash)."""
        self._blacklist.add(agent_id)
        self._whitelist.discard(agent_id)

    def remove_whitelist(self, agent_id: str) -> None:
        """Remove agent from whitelist."""
        self._whitelist.discard(agent_id)

    def remove_blacklist(self, agent_id: str) -> None:
        """Remove agent from blacklist."""
        self._blacklist.discard(agent_id)

    def can_flash(self, agent_id: str, required_permissions: List[ToolPermission]) -> bool:
        """
        Check if agent can perform flash operation.

        Args:
            agent_id: Agent identifier
            required_permissions: Required permissions (must include FLASH)

        Returns:
            True if allowed
        """
        # Check blacklist
        if agent_id in self._blacklist:
            return False

        # Check whitelist
        if agent_id in self._whitelist:
            return True

        # Check for FLASH permission
        return ToolPermission.FLASH in required_permissions

    def check_and_raise(self, agent_id: str, required_permissions: List[ToolPermission]) -> None:
        """
        Check permissions and raise if not allowed.

        Raises:
            PermissionError: If agent cannot flash
        """
        if not self.can_flash(agent_id, required_permissions):
            raise PermissionError(f"Agent {agent_id} lacks FLASH permission for this operation")

    def get_status(self, agent_id: str) -> Dict[str, Any]:
        """Get permission status for agent."""
        return {
            "agent_id": agent_id,
            "whitelisted": agent_id in self._whitelist,
            "blacklisted": agent_id in self._blacklist,
            "can_flash": self.can_flash(agent_id, [ToolPermission.FLASH]),
        }


# Global flash permission guard
_flash_guard = FlashPermissionGuard()


def get_flash_permission_guard() -> FlashPermissionGuard:
    """Get the global flash permission guard."""
    return _flash_guard


# Flash Tools

def create_flash_tool(
    name: str,
    description: str,
    parameters: List[ToolParameter],
) -> Tool:
    """
    Create a flash tool with FLASH permission requirement.

    Args:
        name: Tool name
        description: Tool description
        parameters: Tool parameters

    Returns:
        Tool with FLASH permission
    """
    return Tool(
        name=name,
        description=description,
        category=ToolCategory.FLASH,
        parameters=parameters,
        permissions=[ToolPermission.FLASH, ToolPermission.EXECUTE],
        timeout=300,
    )


# Tool Definitions

FLASH_FIRMWARE_TOOL = create_flash_tool(
    name="flash_firmware",
    description="Flash firmware binary to target MCU over SWD/JTAG",
    parameters=[
        ToolParameter(
            name="binary_path",
            type=ParameterType.FILE_PATH,
            description="Path to firmware binary file (.bin, .hex, .elf)",
            required=True,
        ),
        ToolParameter(
            name="target_address",
            type=ParameterType.INTEGER,
            description="Flash address to write to (default: 0x08000000)",
            required=False,
            default=0x08000000,
        ),
        ToolParameter(
            name="verify",
            type=ParameterType.BOOLEAN,
            description="Verify flash after programming",
            required=False,
            default=True,
        ),
        ToolParameter(
            name="reset",
            type=ParameterType.BOOLEAN,
            description="Reset MCU after flashing",
            required=False,
            default=True,
        ),
        ToolParameter(
            name="interface",
            type=ParameterType.CHOICE,
            description="Programming interface",
            required=False,
            default="SWD",
            choices=["SWD", "JTAG", "UART", "SPI"],
        ),
    ],
)


FLASH_VERIFY_TOOL = create_flash_tool(
    name="flash_verify",
    description="Verify flash contents match binary",
    parameters=[
        ToolParameter(
            name="binary_path",
            type=ParameterType.FILE_PATH,
            description="Path to firmware binary file",
            required=True,
        ),
        ToolParameter(
            name="target_address",
            type=ParameterType.INTEGER,
            description="Flash address to verify",
            required=False,
            default=0x08000000,
        ),
    ],
)


FLASH_READ_TOOL = create_flash_tool(
    name="flash_read",
    description="Read flash memory contents",
    parameters=[
        ToolParameter(
            name="address",
            type=ParameterType.INTEGER,
            description="Start address to read",
            required=True,
        ),
        ToolParameter(
            name="length",
            type=ParameterType.INTEGER,
            description="Number of bytes to read",
            required=True,
            min_value=1,
            max_value=1024 * 1024,  # Max 1MB
        ),
        ToolParameter(
            name="output_path",
            type=ParameterType.FILE_PATH,
            description="Output file path",
            required=False,
        ),
    ],
)


FLASH_ERASE_TOOL = create_flash_tool(
    name="flash_erase",
    description="Erase flash memory sectors",
    parameters=[
        ToolParameter(
            name="sectors",
            type=ParameterType.STRING,
            description="Sectors to erase (e.g., '0-3' or 'all')",
            required=True,
        ),
        ToolParameter(
            name="verify",
            type=ParameterType.BOOLEAN,
            description="Verify erase was successful",
            required=False,
            default=True,
        ),
    ],
)


FLASH_INFO_TOOL = create_flash_tool(
    name="flash_info",
    description="Get target device information",
    parameters=[],
)


# Tool Executor Wrappers

async def execute_flash_firmware(
    agent_id: str,
    binary_path: str,
    target_address: int = 0x08000000,
    verify: bool = True,
    reset: bool = True,
    interface: str = "SWD",
) -> ToolResult:
    """
    Execute flash firmware operation with permission check.

    Args:
        agent_id: ID of agent requesting flash
        binary_path: Path to firmware binary
        target_address: Flash address
        verify: Whether to verify after flash
        reset: Whether to reset after flash
        interface: Programming interface

    Returns:
        ToolResult with operation outcome
    """
    guard = get_flash_permission_guard()

    # Check permission
    try:
        guard.check_and_raise(agent_id, [ToolPermission.FLASH])
    except PermissionError as exc:
        return ToolResult(
            tool_name="flash_firmware",
            success=False,
            error=str(exc),
            error_type="PermissionError",
        )

    # Simulate flash operation (actual implementation would use pyocd/openocd)
    try:
        binary = Path(binary_path)
        if not binary.exists():
            return ToolResult(
                tool_name="flash_firmware",
                success=False,
                error=f"Binary file not found: {binary_path}",
                error_type="FileNotFoundError",
            )

        logger.info(
            "Flashing %s to address 0x%08X via %s",
            binary.name,
            target_address,
            interface,
        )

        # Simulated operation
        await asyncio.sleep(0.1)  # Simulated flash time

        return ToolResult(
            tool_name="flash_firmware",
            success=True,
            output={
                "binary": binary.name,
                "address": hex(target_address),
                "size": binary.stat().st_size,
                "verified": verify,
                "reset": reset,
                "interface": interface,
            },
        )

    except Exception as exc:
        logger.exception("Flash firmware failed")
        return ToolResult(
            tool_name="flash_firmware",
            success=False,
            error=str(exc),
            error_type=type(exc).__name__,
        )


async def execute_flash_info(agent_id: str) -> ToolResult:
    """
    Execute flash info operation.

    Args:
        agent_id: ID of agent requesting info

    Returns:
        ToolResult with device info
    """
    guard = get_flash_permission_guard()

    try:
        guard.check_and_raise(agent_id, [ToolPermission.FLASH])
    except PermissionError as exc:
        return ToolResult(
            tool_name="flash_info",
            success=False,
            error=str(exc),
            error_type="PermissionError",
        )

    # Simulated device info
    return ToolResult(
        tool_name="flash_info",
        success=True,
        output={
            "device": "STM32F407VG",
            "flash_size": "1024KB",
            "ram_size": "192KB",
            "unique_id": str(uuid4())[:8],
        },
    )


# Registry helper

def get_all_flash_tools() -> List[Tool]:
    """Get all flash tool definitions."""
    return [
        FLASH_FIRMWARE_TOOL,
        FLASH_VERIFY_TOOL,
        FLASH_READ_TOOL,
        FLASH_ERASE_TOOL,
        FLASH_INFO_TOOL,
    ]
