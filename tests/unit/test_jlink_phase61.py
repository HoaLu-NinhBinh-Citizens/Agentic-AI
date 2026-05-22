"""Unit tests for Phase 6.1 J-Link / probe manager."""

import asyncio
import pytest
from pathlib import Path

from src.domain.hardware.probe import probe_supports_memory
from src.infrastructure.hardware.jlink.probe import JLinkProbeAdapter, MockJLinkBackend
from src.infrastructure.hardware.jlink.rtt import RTTReader, RTTControlBlock, RTTChannelConfig
from src.infrastructure.hardware.probe_manager import ProbeManager
from src.domain.hardware.embedded_target import DebugProbeType


@pytest.fixture
def targets_path(tmp_path: Path) -> Path:
    p = tmp_path / "targets.yaml"
    p.write_text(
        "targets:\n  TestTarget:\n    jlink_device: STM32F407VG\n    jlink_speed_khz: 4000\n",
        encoding="utf-8",
    )
    return p


class TestJLinkProbeAdapter:
    @pytest.mark.asyncio
    async def test_memory_read_write(self) -> None:
        probe = JLinkProbeAdapter(use_mock=True)
        await probe.connect()
        assert probe_supports_memory(probe)
        ok = await probe.write_memory(0x20000000, b"\x01\x02\x03\x04")
        assert ok
        result = await probe.read_memory(0x20000000, 4)
        assert result.success
        assert result.data == b"\x01\x02\x03\x04"
        await probe.disconnect()

    @pytest.mark.asyncio
    async def test_register_access(self) -> None:
        probe = JLinkProbeAdapter(use_mock=True)
        await probe.connect()
        await probe.write_register("pc", 0x08001234)
        reg = await probe.read_register("pc")
        assert reg.value == 0x08001234
        await probe.disconnect()


class TestRTTReader:
    def test_inject_and_read(self) -> None:
        cb = RTTControlBlock(base_address=0x20000000, channels=[RTTChannelConfig()])
        reader = RTTReader(cb)
        assert reader.inject(0, b"hello\n") == 6
        ch = reader.get_channel(0)
        assert ch is not None
        assert ch.read(64) == b"hello\n"


class TestProbeManager:
    @pytest.mark.asyncio
    async def test_load_and_connect(self, targets_path: Path) -> None:
        mgr = ProbeManager(targets_path=targets_path)
        names = mgr.list_targets()
        assert "TestTarget" in names
        probe = await mgr.connect("TestTarget", DebugProbeType.JLINK, "test-1")
        assert probe.is_connected
        mem = mgr.get_memory_probe("test-1")
        assert mem is not None
        await mgr.disconnect_all()
