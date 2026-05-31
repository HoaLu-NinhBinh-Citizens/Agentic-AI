"""CLI entry point for AI_SUPPORT (Phase 7)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any, Callable, Coroutine

from src.interfaces.cli.commands import debug, flash, health, lsp, local_llm, metrics, review, slash, trace, unified_review, watch
from src.interfaces.cli.commands import test_gen

Handler = Callable[[argparse.Namespace], Coroutine[Any, Any, int]]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-support",
        description="AI_SUPPORT embedded intelligence CLI",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    health.register(sub)
    debug.register(sub)
    flash.register(sub)
    trace.register(sub)
    review.register(sub)
    unified_review.register(sub)
    metrics.register(sub)
    lsp.register(sub)
    watch.register(sub)
    test_gen.register(sub)
    slash.register_commands(sub)
    local_llm.register(sub)
    return parser


async def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler: Handler | None = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 1
    return await handler(args)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
