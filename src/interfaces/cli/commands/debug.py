"""Debug probe CLI commands (Phase 6.1 / 7)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from src.domain.hardware.embedded_target import DebugProbeType
from src.infrastructure.hardware.probe_manager import ProbeManager, DEFAULT_TARGETS_PATH


async def run_debug_connect(args: argparse.Namespace) -> int:
    mgr = ProbeManager(targets_path=Path(args.targets) if args.targets else DEFAULT_TARGETS_PATH)
    targets = mgr.list_targets()
    if args.target not in targets:
        print(f"Unknown target: {args.target}. Available: {', '.join(targets)}", file=sys.stderr)
        return 1
    probe = await mgr.connect(args.target, DebugProbeType.JLINK, args.probe_id)
    info = await probe.get_probe_info()
    out = {"target": args.target, "serial": info.serial, "type": info.probe_type.value, "connected": True}
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"Connected {args.target} via {info.probe_type.value} ({info.serial})")
    if not args.keep:
        await mgr.disconnect(args.probe_id or f"{args.target}:JLINK")
    return 0


async def run_debug_memory(args: argparse.Namespace) -> int:
    mgr = ProbeManager(targets_path=Path(args.targets) if args.targets else DEFAULT_TARGETS_PATH)
    probe_id = args.probe_id or f"{args.target}:JLINK"
    mem = mgr.get_memory_probe(probe_id)
    if mem is None:
        probe = await mgr.connect(args.target, DebugProbeType.JLINK, probe_id)
        mem = mgr.get_memory_probe(probe_id)
        if mem is None:
            print("Probe does not support memory access", file=sys.stderr)
            return 1
    else:
        probe = mgr.get_probe(probe_id)
    if probe is None or not probe.is_connected:
        await mgr.connect(args.target, DebugProbeType.JLINK, probe_id)
        mem = mgr.get_memory_probe(probe_id)
    result = await mem.read_memory(args.address, args.size)  # type: ignore[union-attr]
    if not result.success:
        print(result.error or "read failed", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"address": hex(result.address), "hex": result.data.hex()}, indent=2))
    else:
        print(result.data.hex())
    await mgr.disconnect(probe_id)
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = subparsers.add_parser("debug", help="Target debug via J-Link")
    sub = p.add_subparsers(dest="debug_cmd", required=True)

    c = sub.add_parser("connect", help="Connect to target")
    c.add_argument("target", help="Target name from targets.yaml")
    c.add_argument("--targets", help="Path to targets.yaml")
    c.add_argument("--probe-id", default=None)
    c.add_argument("--keep", action="store_true", help="Keep connection open")
    c.add_argument("--json", action="store_true")
    c.set_defaults(handler=run_debug_connect)

    m = sub.add_parser("mem", help="Read target memory")
    m.add_argument("target")
    m.add_argument("address", type=lambda x: int(x, 0))
    m.add_argument("size", type=int, default=16)
    m.add_argument("--targets", default=None)
    m.add_argument("--probe-id", default=None)
    m.add_argument("--json", action="store_true")
    m.set_defaults(handler=run_debug_memory)
