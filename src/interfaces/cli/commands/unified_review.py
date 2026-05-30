"""Unified Review CLI command — ML-powered code review using UnifiedReviewEngine.

This command provides full access to the unified pipeline with:
- ML-based detection (AST analysis, data flow)
- Security, quality, and embedded-specific detectors
- Configurable focus areas
- Multiple output formats (markdown, json, cli)

Usage:
    python -m src.interfaces.cli.main unified-review src/file.py --focus security
    python -m src.interfaces.cli.main unified-review src/ --format markdown --output report.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

# Import unified pipeline components
try:
    from src.application.workflows.unified import (
        UnifiedReviewEngine,
        ReviewEngineConfig,
        ReviewResult,
        Finding,
    )
    from src.infrastructure.reporting import (
        MarkdownReportGenerator,
        JSONReportGenerator,
        CLIReportGenerator,
    )
    UNIFIED_AVAILABLE = True
except ImportError as exc:
    UNIFIED_AVAILABLE = False
    print(f"Error: Unified pipeline not available: {exc}", file=sys.stderr)
    print("Install required dependencies or use the legacy 'review' command.", file=sys.stderr)
    sys.exit(1)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register unified-review command with subparsers."""
    parser = subparsers.add_parser(
        "unified-review",
        help="Run unified ML-powered code review",
        description="Run comprehensive code review using the unified ML-powered pipeline. "
                    "Supports security, quality, ML, and embedded-specific analysis.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="Files or directories to review",
    )
    parser.add_argument(
        "--focus", "-f",
        choices=["security", "quality", "ml", "embedded", "all"],
        default="all",
        help="Focus areas for review (default: all)",
    )
    parser.add_argument(
        "--format", "-o",
        choices=["markdown", "json", "cli"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--output", "-w",
        type=Path,
        help="Output file (default: stdout)",
    )
    parser.add_argument(
        "--threshold", "-t",
        type=float,
        default=0.5,
        help="Minimum confidence threshold (0.0-1.0, default: 0.5)",
    )
    parser.add_argument(
        "--max-findings",
        type=int,
        default=50,
        help="Maximum findings per file (default: 50)",
    )
    parser.add_argument(
        "--auto-fix",
        action="store_true",
        help="Automatically apply safe fixes",
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        default=True,
        help="Enable parallel processing (default: True)",
    )
    parser.add_argument(
        "--no-parallel",
        action="store_true",
        help="Disable parallel processing",
    )
    parser.add_argument(
        "--languages",
        nargs="*",
        default=[],
        help="Restrict to specific languages (e.g., python js)",
    )
    parser.set_defaults(handler=run_unified_review)


async def run_unified_review(args: argparse.Namespace) -> int:
    """Execute the unified review command.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, 1 for issues found)
    """
    if not UNIFIED_AVAILABLE:
        print("Error: Unified pipeline not available", file=sys.stderr)
        return 1

    # Expand paths to files
    files = _expand_paths(args.paths)
    if not files:
        print("No files found to review", file=sys.stderr)
        return 1

    print(f"Analyzing {len(files)} file(s)...")

    # Configure engine
    focus_areas = _parse_focus_areas(args.focus)
    config = ReviewEngineConfig(
        focus_areas=focus_areas,
        output_format=args.format,
        confidence_threshold=args.threshold,
        max_findings_per_file=args.max_findings,
        languages=args.languages if args.languages else [],
        enable_parallel=not args.no_parallel,
    )

    # Run review
    engine = UnifiedReviewEngine(config)
    result = await engine.review(files)

    # Generate output
    output = _format_output(result, args.format, files)

    # Write output
    if args.output:
        args.output.write_text(output, encoding="utf-8")
        print(f"Report written to: {args.output}")
    else:
        print(output)

    # Print summary
    _print_summary(result)

    # Auto-fix if requested
    if args.auto_fix and result.suggestions:
        print(f"\n{len(result.suggestions)} fixes available. "
              "Use the 'review --apply' command for interactive fix application.")

    # Exit code based on findings
    return 0 if result.stats.errors_count == 0 else 1


def _expand_paths(paths: list[Path]) -> list[str]:
    """Expand paths to file list.

    Args:
        paths: Input paths (files or directories)

    Returns:
        List of file path strings
    """
    extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".c", ".cpp", ".h", ".rs", ".go", ".java"}
    files: list[str] = []
    seen: set[str] = set()

    for path in paths:
        if path.is_file():
            if str(path) not in seen:
                seen.add(str(path))
                files.append(str(path))
        elif path.is_dir():
            for ext in extensions:
                for f in path.rglob(f"*{ext}"):
                    if str(f) not in seen:
                        seen.add(str(f))
                        files.append(str(f))

    return files


def _parse_focus_areas(focus: str) -> list[str]:
    """Parse focus argument to focus areas list.

    Args:
        focus: Focus area string

    Returns:
        List of focus areas
    """
    if focus == "all":
        return ["security", "quality", "ml", "embedded"]
    return [focus]


def _format_output(result: ReviewResult, format_type: str, files: list[str]) -> str:
    """Format review result for output.

    Args:
        result: Review result from engine
        format_type: Output format type
        files: List of files analyzed

    Returns:
        Formatted output string
    """
    if format_type == "json":
        return json.dumps(result.to_dict(), indent=2)

    if format_type == "cli":
        reporter = CLIReportGenerator()
        findings = [_to_reporter_finding(f) for f in result.findings]
        stats = _to_reporter_stats(result, len(files))
        return reporter.generate(findings, stats)

    # Markdown (default)
    reporter = MarkdownReportGenerator("Unified Review")
    findings = [_to_reporter_finding(f) for f in result.findings]
    stats = _to_reporter_stats(result, len(files))
    return reporter.generate(findings, stats)


def _to_reporter_finding(finding: Finding):
    """Convert unified Finding to reporter Finding format.

    Args:
        finding: Unified Finding

    Returns:
        Reporter Finding object
    """
    from src.infrastructure.reporting.markdown_report import Severity

    # Map severity
    sev_map = {
        "error": Severity.CRITICAL,
        "warning": Severity.MEDIUM,
        "info": Severity.INFO,
    }

    return ReporterFinding(
        rule_id=finding.rule_id,
        title=finding.rule_name or finding.rule_id,
        severity=sev_map.get(finding.severity.value, Severity.MEDIUM),
        file_path=finding.file,
        line=finding.line,
        message=finding.message,
        description=finding.context,
        old_code=finding.fix if finding.fix else "",
        confidence=finding.confidence,
        fixable=bool(finding.fix),
        auto_fixable=False,
        risk_level="MEDIUM",
    )


def _to_reporter_stats(result: ReviewResult, file_count: int):
    """Convert result stats to reporter stats format.

    Args:
        result: Review result
        file_count: Number of files

    Returns:
        Reporter PipelineStats
    """
    from src.infrastructure.reporting.markdown_report import Severity, PipelineStats

    by_severity = {s: 0 for s in Severity}
    for f in result.findings:
        sev_map = {
            "error": Severity.CRITICAL,
            "warning": Severity.MEDIUM,
            "info": Severity.INFO,
        }
        sev = sev_map.get(f.severity.value, Severity.MEDIUM)
        by_severity[sev] = by_severity.get(sev, 0) + 1

    return PipelineStats(
        files_analyzed=file_count,
        duration_seconds=result.stats.execution_time_ms / 1000,
        total_findings=len(result.findings),
        findings_by_severity=by_severity,
    )


def _print_summary(result: ReviewResult) -> None:
    """Print review summary to console.

    Args:
        result: Review result
    """
    print("\n" + "=" * 50)
    print("UNIFIED REVIEW SUMMARY")
    print("=" * 50)
    print(f"Total findings:     {len(result.findings)}")
    print(f"  Errors:           {result.stats.errors_count}")
    print(f"  Warnings:         {result.stats.warnings_count}")
    print(f"  Info:             {result.stats.info_count}")
    print(f"Duration:           {result.stats.execution_time_ms:.0f}ms")
    print(f"Detectors used:     {', '.join(result.stats.detectors_used)}")
    print("=" * 50)


# Import reporter Finding for type hints
from src.infrastructure.reporting.markdown_report import Finding as ReporterFinding


async def main() -> int:
    """CLI entry point for standalone execution."""
    parser = argparse.ArgumentParser(description="Unified ML-powered Code Review")
    parser.add_argument("paths", nargs="+", type=Path, help="Files or directories")
    parser.add_argument("--focus", "-f", default="all",
                        choices=["security", "quality", "ml", "embedded", "all"])
    parser.add_argument("--format", "-o", default="markdown",
                        choices=["markdown", "json", "cli"])
    parser.add_argument("--output", "-w", type=Path, help="Output file")
    parser.add_argument("--threshold", "-t", type=float, default=0.5)
    parser.add_argument("--auto-fix", action="store_true")

    args = parser.parse_args()
    return await run_unified_review(args)


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
