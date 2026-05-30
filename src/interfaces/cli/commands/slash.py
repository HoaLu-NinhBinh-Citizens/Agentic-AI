"""Slash command parser and dispatcher — mimics Cursor's /command syntax.

Supports:
    /fix [@file[:line]]           — Show fix suggestions for a file/line
    /review [--files=FILES] [--focus=AREA]  — Run code review
    /explain [@symbol]             — Explain a symbol, class, or function
    /stats                        — Show review statistics
    /rules [--enable=RULES] [--disable=RULES]  — Manage rule configuration
    /help                         — Show available commands

Syntax:
    /command arg1 arg2 --flag=value --flag2
"""

from __future__ import annotations

import argparse
import asyncio
import re
import shlex
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional


# ─── Command types ──────────────────────────────────────────────────────────

class CommandCategory(Enum):
    REVIEW = "review"
    FIX = "fix"
    NAVIGATE = "navigate"
    CONFIG = "config"
    UTILITY = "utility"


@dataclass
class CommandContext:
    """Context passed to every command handler."""
    workspace_root: str
    files: list[str] = field(default_factory=list)
    lines: list[int] = field(default_factory=list)
    raw_args: str = ""
    raw_flags: dict[str, str] = field(default_factory=dict)
    config_path: Optional[str] = None

    @property
    def primary_file(self) -> Optional[str]:
        return self.files[0] if self.files else None

    @property
    def primary_line(self) -> Optional[int]:
        return self.lines[0] if self.lines else None


@dataclass
class CommandResult:
    """Result returned by a command handler."""
    success: bool
    output: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "errors": self.errors,
            "warnings": self.warnings,
            **self.data,
        }


@dataclass
class Command:
    """A registered slash command."""
    name: str
    description: str
    category: CommandCategory
    aliases: list[str] = field(default_factory=list)
    handler: Callable[[CommandContext], Any] = field(default=None)
    examples: list[str] = field(default_factory=list)


# ─── Builtin commands ────────────────────────────────────────────────────────

async def cmd_review(ctx: CommandContext) -> CommandResult:
    """Run code review on specified files using UnifiedReviewEngine."""
    # Check if unified pipeline is available
    try:
        from src.application.workflows.unified.review_engine import (
            UnifiedReviewEngine,
            ReviewEngineConfig,
        )
    except ImportError as e:
        # Fallback to legacy workflow
        return await _fallback_to_legacy_review(ctx, error_msg=f"Unified pipeline unavailable: {e}")

    files = ctx.files if ctx.files else []
    
    # If no files provided, check workspace for source files
    # Limit to prevent scanning large directories
    if not files:
        from pathlib import Path
        workspace = Path(ctx.workspace_root)
        if workspace.exists() and workspace.is_dir():
            try:
                # Find source files with a limit
                for ext in [".py", ".js", ".ts", ".c", ".cpp"]:
                    source_files = list(workspace.rglob(f"*{ext}"))[:50]  # Limit to 50 files
                    if source_files:
                        files = [str(f) for f in source_files]
                        break
            except Exception:
                pass
        if not files:
            return CommandResult(
                success=True,
                output="No source files found to review. Use /review @file.py to specify files explicitly.",
            )

    focus = ctx.raw_flags.get("focus", "all").split(",")
    if "all" in focus:
        focus = ["security", "quality", "ml", "embedded"]
    auto_apply = "auto" in ctx.raw_flags or ctx.raw_flags.get("mode") == "auto"

    # Normalize focus areas for unified pipeline
    normalized_focus = []
    for f in focus:
        if f in ["security", "quality", "ml", "embedded"]:
            normalized_focus.append(f)
        elif f == "code_quality":
            normalized_focus.append("quality")
        elif f == "best_practices":
            normalized_focus.append("quality")

    config = ReviewEngineConfig(
        focus_areas=normalized_focus or ["security", "quality", "ml"],
        output_format="markdown",
        confidence_threshold=0.5,
    )

    try:
        engine = UnifiedReviewEngine(config)
        # Convert to Path objects
        from pathlib import Path
        file_paths = [Path(f) for f in files]

        result = await engine.review(file_paths, incremental=False)

        output = _format_unified_review_summary(result)
        return CommandResult(
            success=True,
            output=output,
            data={
                "files_reviewed": result.stats.files_scanned,
                "total_findings": len(result.findings),
                "errors": result.stats.errors_count,
                "warnings": result.stats.warnings_count,
                "info": result.stats.info_count,
            },
        )
    except Exception as e:
        import logging
        logging.warning("Unified review failed: %s", e)
        # Fallback to legacy workflow
        return await _fallback_to_legacy_review(ctx, error_msg=f"Unified review failed: {e}")


async def _fallback_to_legacy_review(
    ctx: CommandContext, error_msg: str | None = None
) -> CommandResult:
    """Fallback to legacy CodeReviewWorkflow if unified pipeline fails."""
    try:
        from src.application.workflows.code_review.workflow import CodeReviewWorkflow
    except ImportError:
        return CommandResult(
            success=False,
            output=f"Code review unavailable. {error_msg or 'Both unified and legacy pipelines failed.'}",
        )

    files = ctx.files if ctx.files else ["."]
    focus = ctx.raw_flags.get("focus", "all").split(",")

    try:
        workflow = CodeReviewWorkflow(ctx.workspace_root)
        result = await workflow.review_and_fix(
            files=files,
            focus_areas=focus,
            auto_apply=False,
            dry_run=True,
            interactive=False,
        )

        output = _format_review_summary(result)
        return CommandResult(success=True, output=output, data={
            "files_reviewed": result.files_reviewed,
            "total_findings": result.total_findings,
            "errors": result.errors,
            "warnings": result.warnings,
        })
    except Exception as e:
        return CommandResult(
            success=False,
            output=f"Code review failed. {error_msg or str(e)}",
            errors=[str(e)],
        )


async def cmd_fix(ctx: CommandContext) -> CommandResult:
    """Show and apply fixes for a specific file or line using UnifiedReviewEngine."""
    from pathlib import Path

    if not ctx.primary_file:
        return CommandResult(
            success=False,
            output="Usage: /fix @filename[:line]\n"
                   "  /fix @src/main.py:42\n"
                   "  /fix @src/utils.py",
        )

    files = [ctx.primary_file]

    # Check if unified pipeline is available
    try:
        from src.application.workflows.unified.review_engine import (
            UnifiedReviewEngine,
            ReviewEngineConfig,
        )
    except ImportError as e:
        # Fallback to legacy workflow
        return await _fallback_to_legacy_fix(ctx, error_msg=f"Unified pipeline unavailable: {e}")

    config = ReviewEngineConfig(
        focus_areas=["security", "quality", "ml", "embedded"],
        output_format="markdown",
        confidence_threshold=0.5,
    )

    try:
        engine = UnifiedReviewEngine(config)
        result = await engine.review([Path(f) for f in files], incremental=False)

        # Filter to specific line if given
        fixes = result.findings
        if ctx.primary_line:
            fixes = [f for f in fixes if f.line == ctx.primary_line]

        # Filter to fixable findings
        fixable = [f for f in fixes if f.fix]

        output = _format_unified_fixes_list(fixable)
        return CommandResult(success=True, output=output, data={
            "fix_count": len(fixable),
            "fixes": [
                {
                    "id": f.rule_id,
                    "file": f.file,
                    "line": f.line,
                    "rule": f.rule_id,
                    "reason": f.message[:80],
                    "severity": f.severity.value,
                }
                for f in fixable
            ],
        })

    except Exception as e:
        import logging
        logging.warning("Unified fix failed: %s", e)
        # Fallback to legacy workflow
        return await _fallback_to_legacy_fix(ctx, error_msg=f"Unified fix failed: {e}")


async def _fallback_to_legacy_fix(
    ctx: CommandContext, error_msg: str | None = None
) -> CommandResult:
    """Fallback to legacy CodeReviewWorkflow if unified pipeline fails."""
    try:
        from src.application.workflows.code_review.workflow import CodeReviewWorkflow
    except ImportError:
        return CommandResult(
            success=False,
            output=f"Fix command unavailable. {error_msg or 'Both unified and legacy pipelines failed.'}",
        )

    files = [ctx.primary_file]

    try:
        workflow = CodeReviewWorkflow(ctx.workspace_root)
        result = await workflow.review_and_fix(
            files=files,
            focus_areas=["code_quality", "security"],
            auto_apply=False,
            dry_run=True,
            interactive=False,
        )

        # Filter to specific line if given
        fixes = result.fix_batch.fixes
        if ctx.primary_line:
            fixes = [f for f in fixes if f.line_start == ctx.primary_line]

        output = _format_fixes_list(fixes)
        return CommandResult(success=True, output=output, data={
            "fix_count": len(fixes),
            "fixes": [
                {
                    "id": f.id,
                    "file": f.file_path,
                    "line": f.line_start,
                    "rule": f.rule_id,
                    "reason": f.reason[:80],
                    "severity": f.severity.value,
                }
                for f in fixes
            ],
        })
    except Exception as e:
        return CommandResult(
            success=False,
            output=f"Fix command failed. {error_msg or str(e)}",
            errors=[str(e)],
        )


def _format_unified_fixes_list(fixes: list) -> str:
    """Format unified findings as fixes."""
    if not fixes:
        return "No fixes found for the specified file/line."

    output = f"## Found {len(fixes)} Fixes\n\n"
    for fix in fixes:
        sev_icon = {
            "error": "[X]",
            "warning": "[!]",
            "info": "[i]",
        }.get(fix.severity.value, "?")
        output += f"{sev_icon} `{fix.file}:{fix.line}` "
        output += f"**[{fix.rule_id}]** {fix.message[:60]}\n"

        if fix.context:
            output += f"```\n{fix.context[:100]}\n```\n"

        if fix.fix:
            output += f"**Fix:** {fix.fix[:80]}\n"
        output += "\n"
    return output


async def cmd_explain(ctx: CommandContext) -> CommandResult:
    """Explain a symbol, function, or class."""
    symbol_name = ctx.raw_args.strip()
    if not symbol_name:
        return CommandResult(
            success=False,
            output="Usage: /explain MyClass\n  /explain my_function",
        )

    from src.infrastructure.indexing.symbol_graph import SymbolGraph
    from src.infrastructure.indexing.reference_graph import ReferenceGraph

    symbol_graph = SymbolGraph()
    ref_graph = ReferenceGraph()

    # Try to find in symbol graph
    callers = symbol_graph.get_callers(symbol_name)
    callees = symbol_graph.get_callees(symbol_name)

    # Try reference graph
    info = ref_graph.get_symbol_info(symbol_name)

    output = _format_symbol_explanation(symbol_name, callers, callees, info)
    return CommandResult(success=True, output=output, data={
        "symbol": symbol_name,
        "callers": len(callers),
        "callees": len(callees),
    })


async def cmd_stats(ctx: CommandContext) -> CommandResult:
    """Show review statistics for the workspace."""
    from src.infrastructure.indexing.symbol_graph import SymbolGraph
    from src.infrastructure.indexing.dependency_graph import DependencyGraph

    sym_graph = SymbolGraph()
    dep_graph = DependencyGraph()

    # Get stats (these would be populated from previous runs)
    output = f"""## Review Statistics

**Symbol Graph:**
- Files indexed: {sym_graph.stats.files_indexed}
- Total symbols: {len(sym_graph._nodes)}

**Dependency Graph:**
- Modules indexed: {dep_graph.stats.modules_indexed}
- Import edges: {dep_graph.stats.import_edges_added}

**Note:** Run `/review` first to populate statistics.
"""
    return CommandResult(success=True, output=output)


async def cmd_rules(ctx: CommandContext) -> CommandResult:
    """Manage rule configuration."""
    from src.infrastructure.analysis.rule_engine import RuleEngine

    engine = RuleEngine()
    enable_list = ctx.raw_flags.get("enable", "").split(",")
    disable_list = ctx.raw_flags.get("disable", "").split(",")

    if enable_list and enable_list[0]:
        enabled = []
        for rule_id in enable_list:
            rule_id = rule_id.strip()
            if rule_id and engine.get_rule(rule_id):
                enabled.append(rule_id)
        output = f"Enabled rules: {', '.join(enabled)}"

    elif disable_list and disable_list[0]:
        disabled = []
        for rule_id in disable_list:
            rule_id = rule_id.strip()
            if rule_id:
                if engine.unregister(rule_id):
                    disabled.append(rule_id)
        output = f"Disabled rules: {', '.join(disabled)}"

    else:
        # List all rules
        by_sev: dict[str, int] = {}
        for rule in engine._rules.values():
            sev = rule.severity.value
            by_sev[sev] = by_sev.get(sev, 0) + 1

        output = "## Available Rules\n\n"
        output += f"Total: {len(engine._rules)} rules\n\n"
        for sev, count in sorted(by_sev.items()):
            output += f"- {sev.upper()}: {count} rules\n"

    return CommandResult(success=True, output=output)


async def cmd_help(ctx: CommandContext) -> CommandResult:
    """Show available slash commands."""
    commands = _get_all_commands()
    output = "## Available Slash Commands\n\n"
    for name, cmd in sorted(commands.items()):
        aliases = f" (aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
        output += f"**/{name}{aliases}**\n  {cmd.description}\n\n"
        if cmd.examples:
            output += "  Examples:\n"
            for ex in cmd.examples:
                output += f"    {ex}\n"
            output += "\n"
    return CommandResult(success=True, output=output)


# ─── Command registry ────────────────────────────────────────────────────────

_BUILTIN_COMMANDS: dict[str, Command] = {
    "review": Command(
        name="review",
        description="Run code review on files",
        category=CommandCategory.REVIEW,
        aliases=["r"],
        handler=cmd_review,
        examples=[
            "/review",
            "/review @src/",
            "/review --focus=security",
            "/review --files=src/a.py --focus=ml --auto",
        ],
    ),
    "fix": Command(
        name="fix",
        description="Show and apply fixes for a file or line",
        category=CommandCategory.FIX,
        aliases=["f"],
        handler=cmd_fix,
        examples=[
            "/fix @src/main.py",
            "/fix @src/utils.py:42",
            "/fix @src/handlers/auth.py:100",
        ],
    ),
    "explain": Command(
        name="explain",
        description="Explain a symbol, function, or class",
        category=CommandCategory.NAVIGATE,
        aliases=["e", "x"],
        handler=cmd_explain,
        examples=[
            "/explain MyClass",
            "/explain process_data",
            "/explain HTTPClient",
        ],
    ),
    "stats": Command(
        name="stats",
        description="Show review statistics",
        category=CommandCategory.UTILITY,
        aliases=["s", "stat"],
        handler=cmd_stats,
        examples=["/stats"],
    ),
    "rules": Command(
        name="rules",
        description="Manage rule configuration",
        category=CommandCategory.CONFIG,
        aliases=["rule"],
        handler=cmd_rules,
        examples=[
            "/rules",
            "/rules --enable=SEC001,SEC002",
            "/rules --disable=QUAL005",
        ],
    ),
    "help": Command(
        name="help",
        description="Show this help message",
        category=CommandCategory.UTILITY,
        aliases=["h", "?"],
        handler=cmd_help,
        examples=["/help", "/help review"],
    ),
}


def _get_all_commands() -> dict[str, Command]:
    return _BUILTIN_COMMANDS.copy()


def _parse_ref(ref: str) -> tuple[str, Optional[int]]:
    """Parse @file:line or @file reference."""
    match = re.match(r"@(.+?)(?::(\d+))?$", ref.strip())
    if match:
        file_path = match.group(1)
        line = int(match.group(2)) if match.group(2) else None
        return file_path, line
    return ref, None


def _parse_flags(args_str: str) -> tuple[list[str], dict[str, str]]:
    """Parse positional args and --flag=value flags."""
    parts = shlex.split(args_str)
    positional: list[str] = []
    flags: dict[str, str] = {}

    for part in parts:
        if part.startswith("--"):
            if "=" in part:
                key, val = part[2:].split("=", 1)
                flags[key.replace("-", "_")] = val
            else:
                flags[part[2:].replace("-", "_")] = "true"
        elif part.startswith("-"):
            flags[part[1:].replace("-", "_")] = "true"
        else:
            positional.append(part)

    return positional, flags


async def parse_and_execute(
    raw_input: str,
    workspace_root: str,
) -> CommandResult:
    """Parse a slash command and execute it.

    Args:
        raw_input: Raw user input like "/fix @src/main.py:42 --auto"
        workspace_root: Root directory of the workspace

    Returns:
        CommandResult with output and metadata
    """
    raw_input = raw_input.strip()
    if not raw_input.startswith("/"):
        return CommandResult(
            success=False,
            output=f"Unknown command: {raw_input}. Use /help for available commands.",
        )

    # Split command name from args
    parts = raw_input[1:].split(maxsplit=1)
    cmd_name = parts[0].lower()
    args_str = parts[1] if len(parts) > 1 else ""

    # Find command
    command = _BUILTIN_COMMANDS.get(cmd_name)
    if not command:
        # Try aliases
        for cmd in _BUILTIN_COMMANDS.values():
            if cmd_name in cmd.aliases:
                command = cmd
                break

    if not command:
        suggestions = [
            name for name in _BUILTIN_COMMANDS
            if name.startswith(cmd_name[:2])
        ]
        msg = f"Unknown command: /{cmd_name}"
        if suggestions:
            msg += f". Did you mean: {', '.join('/' + s for s in suggestions)}?"
        return CommandResult(success=False, output=msg)

    # Parse arguments
    positional_args, flags = _parse_flags(args_str)

    # Extract file references
    files: list[str] = []
    lines: list[int] = []
    remaining_args: list[str] = []

    for arg in positional_args:
        if arg.startswith("@"):
            f, ln = _parse_ref(arg)
            files.append(f)
            if ln:
                lines.append(ln)
        else:
            remaining_args.append(arg)

    # Build context
    ctx = CommandContext(
        workspace_root=workspace_root,
        files=files,
        lines=lines,
        raw_args=" ".join(remaining_args),
        raw_flags=flags,
    )

    # Execute
    try:
        result = await command.handler(ctx)
        if asyncio.iscoroutine(result):
            result = await result
        return result
    except Exception as exc:
        import logging
        logging.exception("Command execution failed")
        return CommandResult(
            success=False,
            output=f"Command /{cmd_name} failed: {exc}",
            errors=[str(exc)],
        )


# ─── Output formatters ──────────────────────────────────────────────────────

def _format_review_summary(result) -> str:
    errors = result.errors
    warnings = result.warnings
    info = result.info
    total = result.total_findings

    emoji = {"error": "[X]", "warning": "[!]", "info": "[i]"}
    color = {"error": "red", "warning": "yellow", "info": "blue"}

    output = f"""## Code Review Summary

| Metric | Value |
|--------|-------|
| Files reviewed | {result.files_reviewed} |
| Total findings | {total} |
| Duration | {result.duration_seconds:.2f}s |

### By Severity

- **[X] Errors:** {errors}
- **[!] Warnings:** {warnings}
- **[i] Info:** {info}

### Fixes Applied

- Applied: {result.fix_batch.applied}
- Rejected: {result.fix_batch.rejected}
- Failed: {result.fix_batch.failed}
- Pending: {result.fix_batch.pending}
- Success rate: {result.fix_batch.success_rate:.0%}
"""
    return output


def _format_unified_review_summary(result) -> str:
    """Format unified review result for slash command output."""
    errors = result.stats.errors_count
    warnings = result.stats.warnings_count
    info = result.stats.info_count
    total = len(result.findings)
    duration_ms = result.stats.execution_time_ms

    output = f"""## Unified Code Review Summary

| Metric | Value |
|--------|-------|
| Files reviewed | {result.stats.files_scanned} |
| Total findings | {total} |
| Duration | {duration_ms:.0f}ms |
| Detectors | {', '.join(result.stats.detectors_used)} |

### By Severity

- **[X] Errors:** {errors}
- **[!] Warnings:** {warnings}
- **[i] Info:** {info}

### Top Findings

"""

    # Show top 5 findings
    top_findings = sorted(
        result.findings,
        key=lambda f: (-f.severity.to_numeric(), -f.confidence)
    )[:5]

    for i, f in enumerate(top_findings, 1):
        output += f"{i}. `[{f.rule_id}]` {f.file}:{f.line} - {f.message[:60]}\n"

    if result.suggestions:
        output += f"\n### Fix Suggestions\n\n"
        for sug in result.suggestions[:3]:
            output += f"- {sug.get('title', 'Fix')}: {sug.get('description', '')[:50]}...\n"

    return output


def _format_fixes_list(fixes: list) -> str:
    if not fixes:
        return "No fixes found for the specified file/line."

    output = f"## Found {len(fixes)} Fixes\n\n"
    for fix in fixes:
        sev_icon = {
            "error": "[X]",
            "warning": "[!]",
            "info": "[i]",
        }.get(fix.severity.value, "?")
        output += f"{sev_icon} `{fix.file_path}:{fix.line_start}` "
        output += f"**[{fix.rule_id}]** {fix.reason[:60]}\n"
        if fix.new_text:
            output += f"```\n{fix.new_text[:100]}\n```\n"
        output += "\n"
    return output


def _format_symbol_explanation(name: str, callers: list, callees: list, info) -> str:
    output = f"## Symbol: `{name}`\n\n"
    if info and info.definition:
        defn = info.definition
        output += f"**Type:** {defn.symbol_type}\n"
        output += f"**File:** `{defn.file_path}:{defn.line}`\n"
        if defn.signature:
            output += f"**Signature:** `{defn.signature}`\n"
        output += "\n"

    output += f"**Called by ({len(callers)} callers):**\n"
    if callers:
        for caller in callers[:5]:
            output += f"  - `{caller.caller_file}:{caller.caller_line}` `{caller.caller}`\n"
        if len(callers) > 5:
            output += f"  - ... and {len(callers) - 5} more\n"
    else:
        output += "  - (no callers found)\n"

    output += f"\n**Calls ({len(callees)} callees):**\n"
    if callees:
        for callee in callees[:5]:
            output += f"  - `{callee.callee_file}:{callee.callee_line}` `{callee.callee}`\n"
        if len(callees) > 5:
            output += f"  - ... and {len(callees) - 5} more\n"
    else:
        output += "  - (no callees found)\n"

    return output


# ─── CLI registration ────────────────────────────────────────────────────────

def register_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register slash command parser as a CLI subcommand."""
    parser = subparsers.add_parser(
        "slash",
        help="Execute slash commands (/fix, /review, /explain...)",
        description="Parse and execute slash commands in Cursor style",
    )
    parser.add_argument("command", nargs="+", help="Command to execute (e.g. '/fix @file:42')")
    parser.add_argument(
        "--workspace", "-w", default=".",
        help="Workspace root directory",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    parser.set_defaults(handler=_run_slash_command)


async def _run_slash_command(args: argparse.Namespace) -> int:
    """Run a slash command from CLI."""
    import json, sys

    raw = " ".join(args.command)
    result = await parse_and_execute(raw, args.workspace)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(result.output)
        if result.errors:
            for err in result.errors:
                print(f"[ERROR] {err}", file=sys.stderr)

    return 0 if result.success else 1
