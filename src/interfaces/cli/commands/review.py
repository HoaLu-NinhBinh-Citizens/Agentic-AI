"""Review CLI command — code review with fix application."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

from src.application.workflows.code_review.workflow import CodeReviewWorkflow


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register review command with subparsers."""
    parser = subparsers.add_parser(
        "review",
        help="Review code files and apply fixes",
        description="Run code review on files, collect findings, and apply fixes",
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="Files or directories to review",
    )
    parser.add_argument(
        "--area", "-a",
        choices=["security", "quality", "all"],
        default="all",
        help="Review focus area (default: all)",
    )
    parser.add_argument(
        "--fix", "-f",
        action="store_true",
        help="Suggest fixes for issues found",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply fixes interactively after review",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Automatically apply safe fixes (INFO level, high confidence)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Validate fixes without applying (default: True)",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Actually apply fixes (overrides --dry-run)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
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
    """Execute the review command."""
    workspace_root = args.workspace or str(Path.cwd())

    files = await _resolve_files(args.files, args.exclude)

    if not files:
        print("No files found to review", file=sys.stderr)
        return 1

    focus_areas = _parse_focus_areas(args.area)

    dry_run = not args.no_dry_run
    if args.apply:
        dry_run = False

    workflow = CodeReviewWorkflow(workspace_root)

    result = await workflow.review_and_fix(
        files=files,
        focus_areas=focus_areas,
        auto_apply=args.auto,
        dry_run=dry_run,
        interactive=args.apply,
    )

    if args.json:
        _print_json_result(result)
    else:
        _print_human_result(result, args)

    return 0 if result.errors == 0 else 1


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


def _parse_focus_areas(area: str) -> list[str]:
    """Parse focus area string to list."""
    mapping = {
        "security": ["security"],
        "quality": ["code_quality", "best_practices"],
        "all": ["code_quality", "security", "best_practices", "performance"],
    }
    return mapping.get(area, mapping["all"])


def _print_human_result(result, args) -> None:
    """Print human-readable result."""
    print("\n" + "=" * 60)
    print("CODE REVIEW RESULTS")
    print("=" * 60)
    print(f"Files reviewed:    {result.files_reviewed}")
    print(f"Total findings:    {result.total_findings}")
    print(f"  Errors:          {result.errors}")
    print(f"  Warnings:        {result.warnings}")
    print(f"  Info:            {result.info}")
    print("-" * 60)
    print(f"Duration:          {result.duration_seconds:.2f}s")
    print("-" * 60)

    batch = result.fix_batch
    print(f"Fixes:")
    print(f"  Applied:         {batch.applied}")
    print(f"  Rejected:        {batch.rejected}")
    print(f"  Failed:          {batch.failed}")
    print(f"  Pending:         {batch.pending}")
    print(f"  Success rate:    {batch.success_rate:.0%}")

    if args.apply or args.fix:
        if batch.fixes:
            print("\n" + "-" * 60)
            print("FIX DETAILS:")
            for fix in batch.fixes[:10]:
                status_icon = {
                    "applied": "✓",
                    "rejected": "✗",
                    "failed": "✗",
                    "skipped": "−",
                    "pending": "○",
                }.get(fix.status.value, "?")
                print(f"  [{status_icon}] {fix.file_path}:{fix.line_start}")
                print(f"       {fix.reason[:60]}")
            if len(batch.fixes) > 10:
                print(f"  ... and {len(batch.fixes) - 10} more")


def _print_json_result(result) -> None:
    """Print JSON result."""
    output = {
        "files_reviewed": result.files_reviewed,
        "total_findings": result.total_findings,
        "errors": result.errors,
        "warnings": result.warnings,
        "info": result.info,
        "duration_seconds": round(result.duration_seconds, 2),
        "fixes": {
            "applied": result.fix_batch.applied,
            "rejected": result.fix_batch.rejected,
            "failed": result.fix_batch.failed,
            "pending": result.fix_batch.pending,
            "success_rate": round(result.fix_batch.success_rate, 2),
        },
        "details": [
            {
                "id": fix.id,
                "file": fix.file_path,
                "line": fix.line_start,
                "severity": fix.severity.value,
                "status": fix.status.value,
                "rule": fix.rule_id,
                "reason": fix.reason,
            }
            for fix in result.fix_batch.fixes
        ],
    }
    print(json.dumps(output, indent=2))
