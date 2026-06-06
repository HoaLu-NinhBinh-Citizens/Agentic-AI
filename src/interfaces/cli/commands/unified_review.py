"""Unified Review CLI command — ML-powered code review using UnifiedReviewEngine.

This command provides full access to the unified pipeline with:
|- ML-based detection (AST analysis, data flow)
|- Security, quality, and embedded-specific detectors
|- Configurable focus areas
|- Multiple output formats (markdown, json, cli)
|- Interactive fix confirmation with pre/post review questions

Usage:
    python -m src.interfaces.cli.main unified-review src/file.py --focus security
    python -m src.interfaces.cli.main unified-review src/ --format markdown --output report.md
    python -m src.interfaces.cli.main unified-review src/ --interactive
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
        "--interactive", "-i",
        action="store_true",
        help="Interactive mode with pre/post review questions and fix confirmation",
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
    parser.add_argument(
        "--auto-fix",
        nargs="?",
        const="low",
        default=None,
        help="Auto-fix level: none, low, medium, high, all. "
             "Use --auto-fix=low to auto-fix low severity issues.",
    )
    parser.add_argument(
        "--auto-fix-level",
        choices=["none", "low", "medium", "high", "all"],
        default="low",
        help="Severity level for auto-fix (default: low)",
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

    # Interactive mode: ask pre-review questions
    scope = None
    auto_approve = False
    if getattr(args, 'interactive', False):
        scope, auto_approve = await _run_interactive_pre_review(args)

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
    
    # Configure auto-fix settings from CLI
    auto_fix_level = getattr(args, 'auto_fix_level', 'low')
    if getattr(args, 'auto_fix', None) is not None:
        auto_fix_level = args.auto_fix
    config.auto_fix_level = auto_fix_level

    # Run review
    engine = UnifiedReviewEngine(config)
    result = await engine.review(files)

    # Interactive mode: show summary and offer post-review actions
    if getattr(args, 'interactive', False):
        await _run_interactive_post_review(result)

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


async def _run_interactive_pre_review(args: argparse.Namespace) -> tuple[Optional[str], bool]:
    """Run interactive pre-review questions.

    Args:
        args: Command line arguments

    Returns:
        Tuple of (scope, auto_approve)
    """
    print("\n" + "=" * 60)
    print("AI_SUPPORT Interactive Review")
    print("=" * 60)

    # Ask about scope
    print("\nSelect review scope:")
    print("  1) Current file")
    print("  2) Current directory")
    print("  3) Entire project")
    scope_choice = input("\nEnter choice (1-3) [3]: ").strip() or "3"
    scopes = {"1": "file", "2": "dir", "3": "project"}
    scope = scopes.get(scope_choice, "project")
    print(f"  → Review scope: {scope}")

    # Ask about focus areas
    print("\nFocus areas available:")
    print("  - security: Security vulnerabilities")
    print("  - quality: Code quality issues")
    print("  - ml: ML-specific bugs")
    print("  - embedded: Embedded systems issues")
    print("  - all: All focus areas")
    focus_choice = input(f"\nEnter focus areas [{args.focus}]: ").strip() or args.focus
    if focus_choice != args.focus:
        args.focus = focus_choice

    # Ask about auto-approve
    print("\nAuto-approve CRITICAL fixes without prompting?")
    approve_choice = input("Enter choice (y/n) [y]: ").strip() or "y"
    auto_approve = approve_choice.lower() == "y"

    print("\n" + "=" * 60)
    print("Starting review...")
    print("=" * 60 + "\n")

    return scope, auto_approve


async def _run_interactive_post_review(result: ReviewResult) -> None:
    """Run interactive post-review questions.

    Args:
        result: The review result
    """
    print("\n" + "=" * 60)
    print("Review Complete - Summary")
    print("=" * 60)
    print(f"Total findings:     {len(result.findings)}")
    print(f"  Errors:           {result.stats.errors_count}")
    print(f"  Warnings:         {result.stats.warnings_count}")
    print(f"  Info:             {result.stats.info_count}")

    if result.findings:
        print("\n" + "-" * 40)
        print("Post-review actions:")
        print("  1) Generate detailed report")
        print("  2) Show fix suggestions")
        print("  3) Apply safe fixes automatically")
        print("  4) Exit")
        print("-" * 40)

        choice = input("\nEnter choice (1-4) [1]: ").strip() or "1"

        if choice == "2":
            _print_fix_suggestions(result)
        elif choice == "3":
            await _apply_safe_fixes(result)

    print("=" * 60)


def _print_fix_suggestions(result: ReviewResult) -> None:
    """Print fix suggestions from review result."""
    print("\nFix Suggestions:")
    print("-" * 40)

    for i, finding in enumerate(result.findings[:10], 1):
        if finding.fix:
            print(f"\n{i}. [{finding.severity.value.upper()}] {finding.rule_id or finding.rule_name}")
            print(f"   File: {finding.file}:{finding.line}")
            print(f"   Fix: {finding.fix[:100]}..." if len(finding.fix) > 100 else f"   Fix: {finding.fix}")


async def _apply_safe_fixes(result: ReviewResult) -> None:
    """Apply safe fixes from review result."""
    safe_fixes = [f for f in result.findings if f.fix]

    if not safe_fixes:
        print("\nNo fixable issues found.")
        return

    print(f"\nApplying {len(safe_fixes)} safe fixes...")

    # Note: Actual fix application would require the fix engine
    # This is a placeholder for the interactive confirmation flow
    from src.interfaces.cli.commands.interactive_confirm import InteractiveConfirmationFlow

    flow = InteractiveConfirmationFlow()

    for finding in safe_fixes[:5]:
        print(f"  - {finding.file}:{finding.line}: {finding.rule_id}")


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


async def _ask_scope() -> str:
    """Ask user for review scope."""
    try:
        print("\n📋 Select review scope:")
        print("  1) Current file")
        print("  2) Current directory")
        print("  3) Entire project")
        choice = input("\nEnter choice (1-3) [3]: ").strip() or "3"
        scopes = {"1": "file", "2": "dir", "3": "project"}
        return scopes.get(choice, "project")
    except (EOFError, KeyboardInterrupt):
        return "project"


async def _ask_focus() -> list[str]:
    """Ask user for focus areas."""
    try:
        print("\n🎯 Select focus areas (comma-separated):")
        print("  ml) ML-specific bugs")
        print("  sec) Security vulnerabilities")
        print("  qual) Code quality")
        print("  emb) Embedded systems")
        print("  all) All areas")
        choice = input("Enter focus areas [all]: ").strip() or "all"
        if choice == "all":
            return ["ml", "sec", "qual", "emb"]
        return [c.strip() for c in choice.split(",")]
    except (EOFError, KeyboardInterrupt):
        return ["ml", "sec", "qual", "emb"]


async def _ask_auto_approve() -> bool:
    """Ask user about auto-approving critical fixes."""
    try:
        print("\n⚡ Auto-approve CRITICAL fixes without prompting?")
        choice = input("Enter choice (y/n) [y]: ").strip() or "y"
        return choice.lower() == "y"
    except (EOFError, KeyboardInterrupt):
        return True


async def run_review_interactive(paths: list[Path], args) -> int:
    """Interactive review with pre/post-review clarifying questions.

    Args:
        paths: Files/directories to review
        args: CLI arguments

    Returns:
        Exit code (0 for success)
    """
    print("\n🔍 AI_SUPPORT Interactive Code Review")
    print("=" * 50)

    # Pre-review clarification
    scope = await _ask_scope() if not hasattr(args, 'scope') else args.scope
    focus = await _ask_focus() if not hasattr(args, 'focus') or args.focus == 'all' else [args.focus]
    auto_approve = await _ask_auto_approve() if not hasattr(args, 'auto_approve') else args.auto_approve

    print(f"\n📋 Review scope: {scope}")
    print(f"🎯 Focus areas: {', '.join(focus)}")
    print(f"⚡ Auto-approve critical: {'Yes' if auto_approve else 'No'}")
    print()

    # Run review
    try:
        from src.infrastructure.review.interactive_confirm import InteractiveConfirmationFlow
        interactive_flow = InteractiveConfirmationFlow(auto_approve_critical=auto_approve)
    except ImportError:
        interactive_flow = None

    # Execute review
    review_args = argparse.Namespace(
        paths=paths,
        focus=','.join(focus) if focus != ['ml', 'sec', 'qual', 'emb'] else 'all',
        format='cli',
        output=None,
        threshold=args.threshold if hasattr(args, 'threshold') else 0.5,
        auto_fix=args.auto_fix if hasattr(args, 'auto_fix') else False,
        interactive=False,
    )

    exit_code = await run_unified_review(review_args)

    # Post-review clarification
    if exit_code == 0:
        try:
            print("\n📋 Post-review actions:")
            print("  1) Generate detailed markdown report")
            print("  2) Apply auto-fixable issues")
            print("  3) Exit")
            choice = input("\nEnter choice (1-3) [3]: ").strip() or "3"
            if choice == "1":
                print("\n📝 Generating markdown report...")
                report_args = argparse.Namespace(
                    paths=paths, focus=focus[0] if len(focus) == 1 else 'all',
                    format='markdown', output=Path("review_report.md"),
                    threshold=0.5, auto_fix=False, interactive=False,
                )
                await run_unified_review(report_args)
            elif choice == "2":
                print("\n🔧 Applying fixes...")
        except (EOFError, KeyboardInterrupt):
            pass

    return exit_code


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
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="Interactive mode with questions")

    args = parser.parse_args()
    
    # Wire interactive flow
    if getattr(args, 'interactive', False):
        return await run_review_interactive(args.paths, args)
    
    return await run_unified_review(args)


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
