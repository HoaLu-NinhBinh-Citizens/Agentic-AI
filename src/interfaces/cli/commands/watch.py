"""Watch command - auto-review on file changes with IDE bridge.

Usage:
    ai-support watch src/
    ai-support watch --patterns "*.py" "*.c" src/
    ai-support watch --rules security quality --debounce 1000
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path
from typing import Any, Optional

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
    parser.add_argument(
        "--output", "-o",
        choices=["console", "json", "vim"],
        default="console",
        help="Output format (default: console)",
    )
    parser.add_argument(
        "--ide-bridge",
        action="store_true",
        help="Enable IDE bridge for real-time diagnostics",
    )
    parser.add_argument(
        "--lsp-port",
        type=int,
        default=8765,
        help="LSP bridge port (default: 8765)",
    )
    parser.set_defaults(handler=run_watch)


async def run_watch(args: argparse.Namespace) -> int:
    """Execute the watch command with optional IDE bridge."""
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
            output_format=getattr(args, "output", "console"),
            enable_caching=False,
        )
    except ImportError:
        config = None
        print("Warning: ReviewEngineConfig not available, using defaults", file=sys.stderr)

    # Create service
    service = AutoReviewService(path, config)

    # Handle shutdown
    shutdown_event = asyncio.Event()
    lsp_server = None

    def handle_shutdown(sig):
        async def _shutdown():
            print("\nReceived shutdown signal, stopping watcher...")
            if lsp_server:
                lsp_server.close()
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

    # Start IDE bridge if requested
    if getattr(args, "ide_bridge", False):
        lsp_port = getattr(args, "lsp_port", 8765)
        lsp_server = await _start_lsp_bridge(service, lsp_port)
        if lsp_server:
            print(f"  LSP Bridge: tcp://localhost:{lsp_port}")

    # Start watching
    try:
        await service.start_watching()
        print(f"Watching {path} for changes...")
        print("Press Ctrl+C to stop")
        print("-" * 50)

        # Start async monitoring task
        monitor_task = asyncio.create_task(_monitor_changes(service, args))

        # Wait for shutdown
        await shutdown_event.wait()

        # Cancel monitor
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

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


async def _start_lsp_bridge(service: AutoReviewService, port: int):
    """Start LSP bridge server for IDE integration."""
    try:
        import json

        async def handle_client(reader, writer):
            addr = writer.get_extra_info("peername")
            print(f"[LSP] Client connected: {addr}")

            try:
                while True:
                    line = await reader.readline()
                    if not line:
                        break

                    try:
                        request = json.loads(line.decode())
                        response = await _handle_lsp_request(service, request)
                        if response:
                            writer.write((json.dumps(response) + "\n").encode())
                            await writer.drain()
                    except json.JSONDecodeError:
                        pass

            except (ConnectionResetError, BrokenPipeError):
                pass
            finally:
                writer.close()
                await writer.wait_closed()
                print(f"[LSP] Client disconnected: {addr}")

        server = await asyncio.start_server(handle_client, "localhost", port)
        print(f"[LSP] Bridge started on tcp://localhost:{port}")
        return server

    except Exception as e:
        print(f"Warning: Could not start LSP bridge: {e}", file=sys.stderr)
        return None


async def _handle_lsp_request(service: AutoReviewService, request: dict) -> Optional[dict]:
    """Handle LSP request from IDE."""
    import json

    method = request.get("method", "")
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "capabilities": {
                    "textDocumentSync": 1,
                    "hoverProvider": True,
                    "completionProvider": {"resolveProvider": False},
                    "publishDiagnosticsProvider": True,
                },
            },
        }

    if method == "shutdown":
        return {"jsonrpc": "2.0", "id": req_id, "result": None}

    if method == "exit":
        return None

    # Return diagnostics for current state
    if method in ("textDocument/didOpen", "textDocument/didChange"):
        params = request.get("params", {})
        uri = params.get("textDocument", {}).get("uri", "")
        path = uri.replace("file://", "") if uri.startswith("file://") else uri
        diagnostics = service.get_diagnostics(Path(path))

        return {
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {
                "uri": uri,
                "diagnostics": [
                    {
                        "range": {
                            "start": {"line": d.line - 1, "character": 0},
                            "end": {"line": d.line - 1, "character": 100},
                        },
                        "severity": _lsp_severity(d.severity),
                        "message": d.message,
                        "source": "AI_SUPPORT",
                        "code": d.rule_id,
                    }
                    for d in diagnostics
                ],
            },
        }

    return None


def _lsp_severity(severity: str) -> int:
    """Map severity to LSP integer."""
    mapping = {"error": 1, "warning": 2, "info": 3}
    return mapping.get(severity.lower(), 3)


async def _monitor_changes(service: AutoReviewService, args: argparse.Namespace) -> None:
    """Monitor for changes and display diagnostics."""
    import time

    last_stats = {"diagnostics_count": 0}

    while True:
        try:
            await asyncio.sleep(2)

            stats = service.get_stats()
            current_count = stats.get("diagnostics_count", 0)

            if current_count != last_stats["diagnostics_count"]:
                if not getattr(args, "no_progress", False):
                    print(f"[Review] {current_count} diagnostics active")
                last_stats["diagnostics_count"] = current_count

        except asyncio.CancelledError:
            break
        except Exception:
            pass


def print_banner(path: Path) -> None:
    """Print startup banner."""
    print("=" * 50)
    print("  AI_SUPPORT Auto-Review Watcher")
    print("=" * 50)
    print(f"  Project: {path}")
    print(f"  Mode: Real-time file monitoring + auto-review")
    print("=" * 50)
