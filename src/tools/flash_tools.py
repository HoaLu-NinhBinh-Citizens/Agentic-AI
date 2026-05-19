"""Legacy alias for src.tools.flash_tools module."""

from src.core.tools.flash_tools import (
    FlashTool,
    FlashConfig,
    FlashResult,
    FlashStatus,
    execute_flash_firmware,
)

__all__ = ["FlashTool", "FlashConfig", "FlashResult", "FlashStatus", "execute_flash_firmware"]
