"""RTT trace CLI command (Phase 6.3)."""

from __future__ import annotations

import argparse
import asyncio
import sys

from src.domain.hardware.embedded_target import DebugProbeType
from src.infrastructure.hardware.jlink.rtt_tracer import RealTimeTracer, TraceBufferConfig
from src.infrastructure.hardware.probe_manager import ProbeManager, DEFAULT_TARGETS_PATH
from pathlib import Path


async def run_trace(args: argparse.Namespace) -> int:
    mgr = ProbeManager(
        targets_path=Path(args.targets) if args.targets else DEFAULT_TARGETS_PATH,
    )
    probe_id = args.probe_id or f"{args.target}:JLINK"
    probe = await mgr.connect(args.target, DebugProbeType.JLINK, probe_id)
    mem = mgr.get_memory_probe(probe_id)
    if mem is None:
        print("Memory probe required", file=sys.stderr)
        return 1

    tracer = RealTimeTracer.create_with_rtt(
        mem,
        rtt_base=args.rtt_base,
        buffer_config=TraceBufferConfig(poll_interval_s=args.interval),
    )
    tracer.track_registers(args.registers.split(",") if args.registers else ["pc"])
    if args.rtt_channel is not None and tracer._rtt:
        tracer._rtt.inject(args.rtt_channel, b"trace start\n")

    await tracer.start()
    try:
        await asyncio.sleep(args.duration)
    finally:
        await tracer.stop()
        await mgr.disconnect(probe_id)

    for entry in tracer.entries[-args.tail :]:
        print(f"[{entry.source}] {entry.message}")
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = subparsers.add_parser("trace", help="Real-time RTT/register trace")
    p.add_argument("target")
    p.add_argument("--duration", type=float, default=2.0)
    p.add_argument("--interval", type=float, default=0.1)
    p.add_argument("--registers", default="pc,sp")
    p.add_argument("--rtt-base", type=lambda x: int(x, 0), default=0x20000000)
    p.add_argument("--rtt-channel", type=int, default=0)
    p.add_argument("--targets", default=None)
    p.add_argument("--probe-id", default=None)
    p.add_argument("--tail", type=int, default=20)
    p.set_defaults(handler=run_trace)
