"""Unit tests for Phase 6.3 real-time tracing."""

import asyncio
import pytest

from src.infrastructure.hardware.jlink.probe import JLinkProbeAdapter
from src.infrastructure.hardware.jlink.rtt_tracer import (
    MemoryWatchpoint,
    RealTimeTracer,
    TraceBufferConfig,
    WatchpointKind,
)


@pytest.mark.asyncio
async def test_tracer_registers_and_watchpoints() -> None:
    probe = JLinkProbeAdapter(use_mock=True)
    await probe.connect()
    await probe.write_register("pc", 0x08001000)
    await probe.write_memory(0x20000100, b"\x00")

    tracer = RealTimeTracer.create_with_rtt(probe, rtt_base=0x20000000)
    tracer.track_registers(["pc"])
    tracer.add_watchpoint(
        MemoryWatchpoint(0x20000100, 4, WatchpointKind.CHANGE, "test"),
    )

    await tracer.sample_registers()
    assert len(tracer.entries) >= 1

    await tracer.sample_watchpoints()
    await probe.write_memory(0x20000100, b"\xff")
    changes = await tracer.sample_watchpoints()
    assert changes == 1
    await probe.disconnect()


@pytest.mark.asyncio
async def test_tracer_background_loop() -> None:
    probe = JLinkProbeAdapter(use_mock=True)
    await probe.connect()
    tracer = RealTimeTracer(
        probe,
        config=TraceBufferConfig(max_entries=50, poll_interval_s=0.05),
    )
    tracer.track_registers(["r0"])
    await tracer.start()
    await asyncio.sleep(0.15)
    await tracer.stop()
    assert tracer.entries
    await probe.disconnect()
