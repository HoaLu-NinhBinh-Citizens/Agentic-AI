"""Flash CLI command (dry-run by default)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


async def run_flash(args: argparse.Namespace) -> int:
    """Validate firmware path and print flash plan (dry-run unless --execute)."""
    fw = Path(args.firmware)
    if not fw.is_file():
        print(f"Firmware not found: {fw}", file=sys.stderr)
        return 1

    plan = {
        "target": args.target,
        "firmware": str(fw.resolve()),
        "dry_run": not args.execute,
        "slot": args.slot,
        "size_bytes": fw.stat().st_size,
    }
    if args.execute:
        plan["status"] = "execute_not_wired"
        plan["message"] = "Use hardware pipeline or enable flash manager integration"
        print("Execute requested but CLI uses dry-run safety. Use server flash API.", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(plan, indent=2))
    else:
        print(f"[dry-run] Would flash {fw.name} to {args.target} slot {args.slot}")
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = subparsers.add_parser("flash", help="Flash firmware (dry-run default)")
    p.add_argument("target", help="Target name (EngineCar, RemoteControl, …)")
    p.add_argument("firmware", help="Path to .bin/.elf")
    p.add_argument("--slot", choices=["A", "B", "auto"], default="auto")
    p.add_argument("--execute", action="store_true", help="Attempt real flash (requires integration)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(handler=run_flash)
