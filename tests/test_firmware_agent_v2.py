"""
Tests for Firmware Agent
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.multi_agent.agent import FirmwareAgent, Task, AgentType, AgentStatus


@pytest.fixture
def agent():
    return FirmwareAgent()


class TestFirmwareAgent:
    """Tests for FirmwareAgent"""

    @pytest.mark.asyncio
    async def test_initialization(self, agent):
        assert agent.agent_type == AgentType.FIRMWARE
        assert agent.status == AgentStatus.IDLE

    @pytest.mark.asyncio
    async def test_can_handle_firmware_task(self, agent):
        task = Task(type="firmware", description="Generate HAL driver for UART")
        assert await agent.can_handle(task) is True

    @pytest.mark.asyncio
    async def test_can_handle_embedded_task(self, agent):
        task = Task(type="embedded", description="Implement STM32 driver")
        assert await agent.can_handle(task) is True

    @pytest.mark.asyncio
    async def test_cannot_handle_other_task(self, agent):
        task = Task(type="review", description="Review code")
        assert await agent.can_handle(task) is False


class TestFirmwareAgentBasic:
    """Basic tests for FirmwareAgent"""

    def test_agent_creation(self):
        agent = FirmwareAgent()
        assert agent._running is False
        assert agent.embedded_agent is None
        assert agent.build_agent is not None
        assert agent.flash_agent is not None

    def test_get_capabilities(self):
        agent = FirmwareAgent()
        caps = agent.get_capabilities()
        assert "firmware_generation" in caps
        assert "firmware_build" in caps
        assert "firmware_flash" in caps

    @pytest.mark.asyncio
    async def test_build(self, agent):
        result = await agent.build("EngineCar", clean=False)
        assert "success" in result
        assert "project" in result or "error" in result

    @pytest.mark.asyncio
    async def test_flash_dry_run(self, agent):
        result = await agent.flash("EngineCar", dry_run=True)
        assert result["success"] is True
        assert result["mode"] == "dry_run"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
