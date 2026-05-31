"""Metrics command for AI_SUPPORT CLI.

Provides visibility into:
- Parser coverage (tree-sitter vs regex fallback)
- AST analysis statistics
- Indexing performance metrics
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from src.infrastructure.indexing.tree_sitter import (
    SafeTreeSitterIndexer,
    ParseStats,
    _EXTENSION_LANGUAGE,
)


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the metrics command."""
    p = subparsers.add_parser(
        "metrics",
        help="Show AST parsing and indexing statistics",
        description="Displays parser coverage metrics showing tree-sitter vs regex fallback usage.",
    )
    p.add_argument(
        "paths",
        nargs="*",
        default=["src/"],
        help="Paths to analyze (default: src/)",
    )
    p.add_argument(
        "--format",
        choices=["table", "json", "summary"],
        default="table",
        help="Output format (default: table)",
    )
    p.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress output",
    )
    p.set_defaults(handler=_run_metrics)


async def _run_metrics(args: argparse.Namespace) -> int:
    """Run metrics collection."""
    from src.infrastructure.indexing.tree_sitter import _EXTENSION_LANGUAGE

    paths = [Path(p) for p in args.paths]
    indexer = SafeTreeSitterIndexer()

    # Collect files by language
    files_by_lang: dict[str, list[Path]] = {}
    total_files = 0

    for root in paths:
        if root.is_file():
            files = [root]
        else:
            files = list(root.rglob("*"))
            files = [f for f in files if f.is_file() and f.suffix.lower() in _EXTENSION_LANGUAGE]

        for f in files:
            lang = _EXTENSION_LANGUAGE.get(f.suffix.lower(), "text")
            if lang not in files_by_lang:
                files_by_lang[lang] = []
            files_by_lang[lang].append(f)
            total_files += 1

    if total_files == 0:
        print("No indexable files found.")
        return 0

    # Index files and collect stats
    ts_count = 0
    regex_count = 0
    failed_count = 0
    lang_stats: dict[str, dict[str, int]] = {}

    for lang, files in files_by_lang.items():
        lang_stats[lang] = {"tree_sitter": 0, "regex": 0, "failed": 0}
        for f in files:
            result = await indexer.index_file(str(f))
            if result["status"] == "success":
                parser = result.get("parser", "unknown")
                if parser == "tree-sitter":
                    ts_count += 1
                    lang_stats[lang]["tree_sitter"] += 1
                elif parser == "regex":
                    regex_count += 1
                    lang_stats[lang]["regex"] += 1
                else:
                    failed_count += 1
                    lang_stats[lang]["failed"] += 1
            else:
                failed_count += 1
                lang_stats[lang]["failed"] += 1

    # Calculate percentages
    success_count = ts_count + regex_count
    ts_percentage = (ts_count / success_count * 100) if success_count > 0 else 0
    regex_percentage = (regex_count / success_count * 100) if success_count > 0 else 0

    # Output based on format
    if args.format == "json":
        await _output_json(ts_count, regex_count, failed_count, lang_stats, total_files)
    elif args.format == "summary":
        _output_summary(ts_count, regex_count, failed_count, ts_percentage, total_files)
    else:
        _output_table(ts_count, regex_count, failed_count, lang_stats, total_files, ts_percentage)

    return 0


def _output_table(
    ts_count: int,
    regex_count: int,
    failed_count: int,
    lang_stats: dict[str, dict[str, int]],
    total_files: int,
    ts_percentage: float,
) -> None:
    """Output metrics as a table."""
    # Header
    print("\n" + "=" * 70)
    print("AST PARSING METRICS")
    print("=" * 70)

    # Summary section
    print(f"\n{'Summary':<20}")
    print("-" * 40)
    print(f"  {'Total files:':<30} {total_files}")
    print(f"  {'Tree-sitter:':<30} {ts_count} ({ts_percentage:.1f}%)")
    print(f"  {'Regex fallback:':<30} {regex_count} ({100-ts_percentage:.1f}%)")
    print(f"  {'Failed:':<30} {failed_count}")

    # Progress bar for tree-sitter coverage
    bar_width = 40
    filled = int(bar_width * ts_percentage / 100)
    bar = "#" * filled + "-" * (bar_width - filled)
    print(f"\n  Tree-sitter coverage: [{bar}] {ts_percentage:.1f}%")

    # Per-language breakdown
    print(f"\n{'Language':<15} {'Tree-sitter':<15} {'Regex':<15} {'Total':<10}")
    print("-" * 55)

    for lang in sorted(lang_stats.keys()):
        stats = lang_stats[lang]
        total = stats["tree_sitter"] + stats["regex"] + stats["failed"]
        ts = stats["tree_sitter"]
        regex = stats["regex"]
        lang_display = lang.upper() if len(lang) <= 8 else lang[:8] + "..."
        print(f"  {lang_display:<13} {ts:<15} {regex:<15} {total:<10}")

    # Recommendations
    print("\n" + "=" * 70)
    print("RECOMMENDATIONS")
    print("=" * 70)

    if ts_percentage >= 95:
        print("  [OK] Excellent tree-sitter coverage across all languages")
    elif ts_percentage >= 80:
        print("  [!!] Good coverage, consider adding parsers for low-coverage languages")
    else:
        print("  [X] Low coverage - some languages may need parser installation")

    # Check for languages with high regex usage
    for lang, stats in lang_stats.items():
        total = stats["tree_sitter"] + stats["regex"] + stats["failed"]
        if total > 0:
            regex_ratio = stats["regex"] / total
            if regex_ratio > 0.5 and stats["tree_sitter"] > 0:
                print(f"  [!!] {lang}: {regex_ratio*100:.0f}% using regex fallback")

    print()


def _output_summary(
    ts_count: int,
    regex_count: int,
    failed_count: int,
    ts_percentage: float,
    total_files: int,
) -> None:
    """Output a single-line summary."""
    success = ts_count + regex_count
    print(f"Parser coverage: {ts_percentage:.1f}% tree-sitter ({ts_count}/{success})")


async def _output_json(
    ts_count: int,
    regex_count: int,
    failed_count: int,
    lang_stats: dict[str, dict[str, int]],
    total_files: int,
) -> None:
    """Output metrics as JSON."""
    import json

    success = ts_count + regex_count
    ts_percentage = (ts_count / success * 100) if success > 0 else 0

    output = {
        "summary": {
            "total_files": total_files,
            "tree_sitter": ts_count,
            "regex_fallback": regex_count,
            "failed": failed_count,
            "tree_sitter_percentage": round(ts_percentage, 2),
        },
        "by_language": {
            lang: {
                "tree_sitter": stats["tree_sitter"],
                "regex": stats["regex"],
                "failed": stats["failed"],
                "total": stats["tree_sitter"] + stats["regex"] + stats["failed"],
            }
            for lang, stats in lang_stats.items()
        },
    }

    print(json.dumps(output, indent=2))


async def _run_index_stats(args: argparse.Namespace) -> int:
    """Run indexing statistics collection."""
    from src.infrastructure.indexing.tree_sitter import SafeTreeSitterIndexer, ParseStats

    paths = [Path(p) for p in args.paths]
    indexer = SafeTreeSitterIndexer()

    total_files = 0
    for root in paths:
        if root.is_dir():
            total_files += len(list(root.rglob("*.py")))

    print(f"Indexing {total_files} files...")
    for root in paths:
        if root.is_dir():
            await indexer.index_directory(str(root))

    stats = indexer.get_status()
    print(f"\nFiles parsed: {stats['stats']['files_parsed']}")
    print(f"Incremental: {stats['stats']['files_incremental']}")
    print(f"Partial: {stats['stats']['files_partial']}")
    print(f"Regex fallback: {stats['stats']['files_fallback_regex']}")
    print(f"Failed: {stats['stats']['files_failed']}")

    return 0
