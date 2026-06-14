"""
Tests for Flash Tools and FLASH Permission

Tests FlashPermissionGuard, flash tools, and permission enforcement.
"""

import pytest
from pathlib import Path

from src.core.tools.schema import ToolPermission, ToolCategory
from src.core.tools.flash_tools import (
    FlashPermissionGuard,
    FlashConfig,
    FlashProgress,
    FlashResult,
    FlashStatus,
    get_flash_permission_guard,
    get_all_flash_tools,
    FLASH_FIRMWARE_TOOL,
    FLASH_VERIFY_TOOL,
    FLASH_READ_TOOL,
    FLASH_ERASE_TOOL,
    FLASH_INFO_TOOL,
    execute_flash_firmware,
    execute_flash_info,
)


# =============================================================================
# FlashPermissionGuard Tests
# =============================================================================

class TestFlashPermissionGuard:
    """Test FlashPermissionGuard functionality."""

    @pytest.fixture
    def guard(self):
        """Create a test permission guard."""
        return FlashPermissionGuard()

    def test_guard_initialization(self, guard):
        """Test guard initializes correctly."""
        assert guard._whitelist == set()
        assert guard._blacklist == set()

    def test_add_whitelist(self, guard):
        """Test adding to whitelist."""
        guard.add_whitelist("agent_1")
        assert "agent_1" in guard._whitelist
        assert "agent_1" not in guard._blacklist

    def test_add_blacklist(self, guard):
        """Test adding to blacklist."""
        guard.add_blacklist("agent_1")
        assert "agent_1" in guard._blacklist
        assert "agent_1" not in guard._whitelist

    def test_remove_whitelist(self, guard):
        """Test removing from whitelist."""
        guard.add_whitelist("agent_1")
        guard.remove_whitelist("agent_1")
        assert "agent_1" not in guard._whitelist

    def test_remove_blacklist(self, guard):
        """Test removing from blacklist."""
        guard.add_blacklist("agent_1")
        guard.remove_blacklist("agent_1")
        assert "agent_1" not in guard._blacklist

    def test_can_flash_with_flash_permission(self, guard):
        """Test can_flash with FLASH permission."""
        result = guard.can_flash("agent_1", [ToolPermission.FLASH])
        assert result is True

    def test_cannot_flash_without_permission(self, guard):
        """Test can_flash without FLASH permission."""
        result = guard.can_flash("agent_1", [ToolPermission.READ])
        assert result is False

    def test_blacklisted_agent_cannot_flash(self, guard):
        """Test blacklisted agent cannot flash."""
        guard.add_blacklist("agent_1")
        result = guard.can_flash("agent_1", [ToolPermission.FLASH])
        assert result is False

    def test_whitelisted_agent_can_flash(self, guard):
        """Test whitelisted agent can flash."""
        guard.add_whitelist("agent_1")
        result = guard.can_flash("agent_1", [ToolPermission.READ])
        assert result is True

    def test_check_and_raise_passes(self, guard):
        """Test check_and_raise passes with permission."""
        guard.check_and_raise("agent_1", [ToolPermission.FLASH])
        # No exception raised

    def test_check_and_raise_raises(self, guard):
        """Test check_and_raise raises without permission."""
        with pytest.raises(PermissionError):
            guard.check_and_raise("agent_1", [ToolPermission.READ])

    def test_get_status(self, guard):
        """Test getting permission status."""
        guard.add_whitelist("agent_1")
        status = guard.get_status("agent_1")

        assert status["agent_id"] == "agent_1"
        assert status["whitelisted"] is True
        assert status["blacklisted"] is False
        assert status["can_flash"] is True


# =============================================================================
# get_flash_permission_guard Tests
# =============================================================================

class TestGetFlashPermissionGuard:
    """Test global flash permission guard."""

    def test_returns_guard(self):
        """Test returns FlashPermissionGuard instance."""
        guard = get_flash_permission_guard()
        assert isinstance(guard, FlashPermissionGuard)

    def test_returns_same_instance(self):
        """Test returns same instance on multiple calls."""
        guard1 = get_flash_permission_guard()
        guard2 = get_flash_permission_guard()
        assert guard1 is guard2


# =============================================================================
# Flash Tool Definitions Tests
# =============================================================================

class TestFlashToolDefinitions:
    """Test flash tool definitions."""

    def test_flash_firmware_tool(self):
        """Test flash firmware tool."""
        assert FLASH_FIRMWARE_TOOL.name == "flash_firmware"
        assert FLASH_FIRMWARE_TOOL.category == ToolCategory.FLASH
        assert ToolPermission.FLASH in FLASH_FIRMWARE_TOOL.permissions

    def test_flash_verify_tool(self):
        """Test flash verify tool."""
        assert FLASH_VERIFY_TOOL.name == "flash_verify"
        assert FLASH_VERIFY_TOOL.category == ToolCategory.FLASH

    def test_flash_read_tool(self):
        """Test flash read tool."""
        assert FLASH_READ_TOOL.name == "flash_read"
        assert FLASH_READ_TOOL.category == ToolCategory.FLASH

    def test_flash_erase_tool(self):
        """Test flash erase tool."""
        assert FLASH_ERASE_TOOL.name == "flash_erase"
        assert FLASH_ERASE_TOOL.category == ToolCategory.FLASH

    def test_flash_info_tool(self):
        """Test flash info tool."""
        assert FLASH_INFO_TOOL.name == "flash_info"
        assert FLASH_INFO_TOOL.category == ToolCategory.FLASH

    def test_get_all_flash_tools(self):
        """Test getting all flash tools."""
        tools = get_all_flash_tools()
        assert len(tools) == 5
        assert FLASH_FIRMWARE_TOOL in tools
        assert FLASH_VERIFY_TOOL in tools


# =============================================================================
# Execute Flash Firmware Tests
# =============================================================================

class TestExecuteFlashFirmware:
    """Test execute_flash_firmware function."""

    @pytest.mark.asyncio
    async def test_permission_denied(self):
        """Test flash firmware without permission."""
        # Clear guard and add blacklist
        guard = get_flash_permission_guard()
        guard._blacklist = {"test_agent"}

        result = await execute_flash_firmware(
            agent_id="test_agent",
            binary_path="test.bin",
        )

        assert result.success is False
        assert "lacks FLASH permission" in result.error
        assert result.error_type == "PermissionError"

    @pytest.mark.asyncio
    async def test_file_not_found(self):
        """Test flash firmware with missing file."""
        guard = get_flash_permission_guard()
        guard._blacklist = set()

        result = await execute_flash_firmware(
            agent_id="test_agent",
            binary_path="nonexistent/path/test.bin",
        )

        assert result.success is False
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_whitelisted_agent(self, tmp_path):
        """Test flash firmware with whitelisted agent."""
        guard = get_flash_permission_guard()
        guard._blacklist = set()
        guard.add_whitelist("whitelist_agent")

        # Create a dummy binary file in the test directory
        binary_path = tmp_path / "test.bin"
        binary_path.write_bytes(b"\x00" * 100)

        result = await execute_flash_firmware(
            agent_id="whitelist_agent",
            binary_path=str(binary_path),
        )

        # Whitelisted agent can flash without FLASH permission
        assert result.success is True


# =============================================================================
# Execute Flash Info Tests
# =============================================================================

class TestExecuteFlashInfo:
    """Test execute_flash_info function."""

    @pytest.mark.asyncio
    async def test_permission_denied(self):
        """Test flash info without permission."""
        guard = get_flash_permission_guard()
        guard._blacklist = {"test_agent"}

        result = await execute_flash_info("test_agent")

        assert result.success is False
        assert "lacks FLASH permission" in result.error

    @pytest.mark.asyncio
    async def test_flash_info_success(self):
        """Test flash info with permission."""
        guard = get_flash_permission_guard()
        guard._blacklist = set()
        guard.add_whitelist("test_agent")

        result = await execute_flash_info("test_agent")

        # Whitelisted agent can access flash info
        assert result.success is True


# =============================================================================
# Flash Config and Status Tests
# =============================================================================

class TestFlashConfig:
    """Test FlashConfig dataclass."""

    def test_default_config(self):
        """Test default flash config."""
        config = FlashConfig()

        assert config.target == "STM32"
        assert config.interface == "SWD"
        assert config.speed == 4000
        assert config.reset_strategy == "hardware"

    def test_custom_config(self):
        """Test custom flash config."""
        config = FlashConfig(
            target="STM32F407",
            interface="JTAG",
            speed=8000,
        )

        assert config.target == "STM32F407"
        assert config.interface == "JTAG"
        assert config.speed == 8000


class TestFlashStatus:
    """Test FlashStatus enum."""

    def test_all_statuses_exist(self):
        """Test all flash statuses exist."""
        assert FlashStatus.IDLE.value == "idle"
        assert FlashStatus.CONNECTING.value == "connecting"
        assert FlashStatus.ERASING.value == "erasing"
        assert FlashStatus.PROGRAMMING.value == "programming"
        assert FlashStatus.VERIFYING.value == "verifying"
        assert FlashStatus.SUCCESS.value == "success"
        assert FlashStatus.FAILED.value == "failed"


class TestFlashProgress:
    """Test FlashProgress dataclass."""

    def test_progress_creation(self):
        """Test creating flash progress."""
        progress = FlashProgress(
            operation="flash",
            total_bytes=1024,
            status=FlashStatus.PROGRAMMING,
        )

        assert progress.operation == "flash"
        assert progress.total_bytes == 1024
        assert progress.status == FlashStatus.PROGRAMMING


class TestFlashResult:
    """Test FlashResult dataclass."""

    def test_success_result(self):
        """Test successful flash result."""
        result = FlashResult(
            success=True,
            operation="flash",
            bytes_written=1024,
            duration_seconds=5.5,
        )

        assert result.success is True
        assert result.bytes_written == 1024
        assert result.duration_seconds == 5.5

    def test_failed_result(self):
        """Test failed flash result."""
        result = FlashResult(
            success=False,
            operation="flash",
            error="Connection lost",
        )

        assert result.success is False
        assert result.error == "Connection lost"
