"""Review CLI command — code review with fix application.

This command uses the UnifiedReviewEngine for ML-powered analysis.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

# Try to import UnifiedReviewEngine
try:
    from src.application.workflows.unified.review_engine import (
        UnifiedReviewEngine,
        ReviewEngineConfig,
    )
    from src.application.workflows.unified.result_formatter import (
        MarkdownFormatter,
        JsonFormatter,
        ConsoleFormatter,
        PipelineStats,
    )
    UNIFIED_AVAILABLE = True
except ImportError:
    UNIFIED_AVAILABLE = False


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register review command with subparsers."""
    parser = subparsers.add_parser(
        "review",
        help="Review code files and apply fixes",
        description="Run code review on files using UnifiedReviewEngine.",
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="Files or directories to review",
    )
    parser.add_argument(
        "--area", "-a",
        choices=["security", "quality", "ml", "embedded", "all"],
        default="all",
        help="Review focus area (default: all)",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["markdown", "json", "console"],
        default="console",
        help="Output format (default: console)",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.5,
        help="Minimum confidence threshold (0.0-1.0, default: 0.5)",
    )
    parser.add_argument(
        "--workspace",
        "-w",
        default=None,
        help="Workspace root directory",
    )
    parser.add_argument(
        "--exclude",
        "-e",
        nargs="*",
        default=[],
        help="Patterns to exclude from review",
    )
    parser.set_defaults(handler=run_review)


async def run_review(args: argparse.Namespace) -> int:
    """Execute the review command using UnifiedReviewEngine."""
    if not UNIFIED_AVAILABLE:
        print("Error: UnifiedReviewEngine not available. Please ensure dependencies are installed.", file=sys.stderr)
        return 1

    workspace_root = args.workspace or str(Path.cwd())

    files = await _resolve_files(args.files, args.exclude)

    if not files:
        print("No files found to review", file=sys.stderr)
        return 1

    # Parse focus areas
    if args.area == "all":
        focus_areas = ["security", "quality", "ml", "embedded"]
    else:
        focus_areas = [args.area]

    # Create config and engine
    config = ReviewEngineConfig(
        focus_areas=focus_areas,
        output_format=args.format,
        confidence_threshold=args.confidence,
    )
    engine = UnifiedReviewEngine(config)

    # Run review
    try:
        file_paths = [Path(f) for f in files]
        result = await engine.review(file_paths, incremental=False)

        # Format output
        formatter = _get_formatter(args.format, result.stats)
        output = formatter.format(result.findings, result.stats, result.suggestions)
        print(output)

        # Return exit code based on findings
        return 0 if result.stats.errors_count == 0 else 1

    except Exception as e:
        print(f"Error during review: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def _get_formatter(format_type: str, stats) -> MarkdownFormatter | JsonFormatter | ConsoleFormatter:
    """Get formatter by type."""
    formatters = {
        "markdown": MarkdownFormatter,
        "json": JsonFormatter,
        "console": ConsoleFormatter,
    }
    formatter_class = formatters.get(format_type, ConsoleFormatter)
    return formatter_class()


async def _resolve_files(
    patterns: list[str],
    exclude: list[str],
) -> list[str]:
    """Resolve file patterns to actual file paths."""
    files: list[str] = []
    exclude_patterns = set(exclude)

    for pattern in patterns:
        path = Path(pattern)
        if path.is_file():
            if not _should_exclude(str(path), exclude_patterns):
                files.append(str(path))
        elif path.is_dir():
            for ext in ("*.py", "*.c", "*.h", "*.cpp", "*.js", "*.ts"):
                for f in path.rglob(ext):
                    if not _should_exclude(str(f), exclude_patterns):
                        files.append(str(f))

    return sorted(set(files))


def _should_exclude(file_path: str, patterns: set[str]) -> bool:
    """Check if file should be excluded."""
    for pattern in patterns:
        if pattern in file_path:
            return True
    return False
