"""Health check CLI command."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


async def run_health(args: argparse.Namespace) -> int:
    """Print server health or local OK."""
    if args.url:
        try:
            import httpx
        except ImportError:
            print("httpx required for remote health", file=sys.stderr)
            return 1
        async with httpx.AsyncClient(timeout=args.timeout) as client:
            resp = await client.get(f"{args.url.rstrip('/')}/health")
            data: dict[str, Any] = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"status": resp.text}
            data["http_status"] = resp.status_code
    else:
        data = {"status": "ok", "component": "ai-support-cli", "mode": "local"}

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(data.get("status", data))
    return 0 if data.get("status") in ("ok", "healthy") or data.get("http_status") == 200 else 1


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = subparsers.add_parser("health", help="Check AI_SUPPORT health")
    p.add_argument("--url", help="Server base URL (e.g. http://127.0.0.1:8000)")
    p.add_argument("--timeout", type=float, default=5.0)
    p.add_argument("--json", action="store_true")
    p.set_defaults(handler=run_health)
