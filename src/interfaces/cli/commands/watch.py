"""Watch command — auto-review on file changes.

Usage:
    python -m agentic_ai.cli watch src/
    python -m agentic_ai.cli watch --patterns "*.py" src/
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path

from src.infrastructure.watchdog import AutoReviewService


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register watch command with subparsers."""
    parser = subparsers.add_parser(
        "watch",
        help="Watch files and auto-review on changes",
        description="Monitor code files and automatically run review when changes are detected.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="src/",
        help="Path to watch (default: src/)",
    )
    parser.add_argument(
        "--patterns", "-p",
        nargs="*",
        default=None,
        help="File patterns to watch (e.g., *.py *.c)",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress output",
    )
    parser.add_argument(
        "--rules",
        nargs="*",
        help="Specific rules to check (security, quality, ml, embedded)",
    )
    parser.add_argument(
        "--debounce",
        type=int,
        default=2000,
        help="Debounce delay in ms (default: 2000)",
    )
    parser.set_defaults(handler=run_watch)


async def run_watch(args: argparse.Namespace) -> int:
    """Execute the watch command."""
    path = Path(args.path)

    if not path.exists():
        print(f"Error: Path does not exist: {path}", file=sys.stderr)
        return 1

    # Determine focus areas
    focus_areas = None
    if args.rules:
        focus_areas = args.rules

    # Import config
    try:
        from src.application.workflows.unified.review_engine import (
            ReviewEngineConfig,
        )
        config = ReviewEngineConfig(
            focus_areas=focus_areas,
            output_format="console",
            enable_caching=False,
        )
    except ImportError:
        config = None
        print("Warning: ReviewEngineConfig not available, using defaults", file=sys.stderr)

    # Create service
    service = AutoReviewService(path, config)

    # Handle shutdown
    shutdown_event = asyncio.Event()

    def handle_shutdown(sig):
        async def _shutdown():
            print("\nReceived shutdown signal, stopping watcher...")
            await service.stop()
            shutdown_event.set()
        asyncio.create_task(_shutdown())

    # Set up signal handlers
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: handle_shutdown(s))
    except (NotImplementedError, AttributeError):
        # Windows doesn't support add_signal_handler
        pass

    # Print banner
    print_banner(path)

    # Start watching
    try:
        await service.start_watching()
        print(f"Watching {path} for changes...")
        print("Press Ctrl+C to stop")
        print("-" * 50)

        # Wait for shutdown
        await shutdown_event.wait()

        # Print stats
        stats = service.get_stats()
        print("\n" + "-" * 50)
        print("Auto-review stats:")
        print(f"  Files reviewed: {stats['files_reviewed']}")
        print(f"  Reviews triggered: {stats['reviews_triggered']}")
        print(f"  Diagnostics found: {stats['diagnostics_count']}")
        print(f"  Errors: {stats['errors_count']}")

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def print_banner(path: Path) -> None:
    """Print startup banner."""
    print("=" * 50)
    print("  AI_SUPPORT Auto-Review Watcher")
    print("=" * 50)
    print(f"  Project: {path}")
    print(f"  Mode: Real-time file monitoring + auto-review")
    print("=" * 50)
