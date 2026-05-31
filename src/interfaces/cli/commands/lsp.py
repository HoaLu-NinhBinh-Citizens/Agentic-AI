"""LSP server CLI command for AI_SUPPORT.

Usage:
    python -m ai_support lsp                    # Start on TCP localhost:8765
    python -m ai_support lsp --stdio             # Start with stdio transport
    python -m ai_support lsp --port 9000         # Custom port
    python -m ai_support lsp --root /path/to/repo  # Set workspace root
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)


def register(subparsers: argparse._SubParsersAction[Any]) -> None:
    """Register LSP command parser."""
    p = subparsers.add_parser(
        "lsp",
        help="Start AI_SUPPORT LSP server for IDE integration",
        description=(
            "Starts a Language Server Protocol (LSP) server that provides:\n"
            "  - Go-to-definition (F12)\n"
            "  - Find all references\n"
            "  - Hover info (type signatures)\n"
            "  - Inline diagnostics/errors\n"
            "  - Auto-completion\n"
            "  - Code lens\n\n"
            "Compatible with VSCode, Neovim, Emacs, and other LSP clients."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    p.add_argument(
        "--port",
        type=int,
        default=8765,
        help="TCP port to listen on (default: 8765)",
    )
    p.add_argument(
        "--stdio",
        action="store_true",
        help="Use stdio transport instead of TCP",
    )
    p.add_argument(
        "--root",
        type=str,
        default=None,
        help="Workspace root directory (default: current directory)",
    )
    p.add_argument(
        "--debounce",
        type=int,
        default=300,
        help="Diagnostics debounce delay in ms (default: 300)",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    p.add_argument(
        "--version",
        action="version",
        version="AI_SUPPORT LSP 1.0.0",
    )

    p.set_defaults(handler=run_lsp)


async def run_lsp(args: argparse.Namespace) -> int:
    """Run the LSP server."""
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Check if pygls is available
    try:
        from src.infrastructure.lsp.server import create_lsp_server
    except ImportError as e:
        print(
            "ERROR: AI_SUPPORT LSP module failed to import.\n"
            "Make sure pygls is installed:\n"
            "  pip install pygls\n"
            f"\nOriginal error: {e}",
            file=sys.stderr,
        )
        return 1

    try:
        # Create server
        server = create_lsp_server(
            root_path=args.root,
            debounce_ms=args.debounce,
        )

        if args.root:
            server.set_root_path(args.root)

        print(
            f"AI_SUPPORT LSP Server\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Root: {args.root or '.'}\n"
            f"Debounce: {args.debounce}ms\n",
            file=sys.stderr,
        )

        if args.stdio:
            print("Transport: stdio", file=sys.stderr)
            server.start_io()
        else:
            print(f"Transport: TCP", file=sys.stderr)
            print(f"Port: {args.port}", file=sys.stderr)
            server.start_tcp(host="localhost", port=args.port)

        # Run until shutdown
        await server.wait_for_shutdown()

        return 0

    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nShutting down...", file=sys.stderr)
        return 0
    except Exception as e:
        logger.exception("LSP server error")
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
