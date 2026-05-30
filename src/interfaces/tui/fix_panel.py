"""Interactive fix panel — TUI for reviewing and applying fixes."""

from __future__ import annotations

import sys
from typing import Optional

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.prompt import Confirm, Prompt
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from src.core.fix_engine.models import (
    Fix,
    FixBatch,
    FixResult,
    FixStatus,
    FixSeverity,
)
from src.core.fix_engine.apply_fix import ApplyFixTool


class FixPanel:
    """Interactive TUI panel for fix management with rich display."""

    def __init__(self, workspace_root: Optional[str] = None):
        self._console = Console() if RICH_AVAILABLE else None
        self._apply_tool = ApplyFixTool(workspace_root)
        self._current_idx = 0
        self._fixes: list[Fix] = []
        self._interactive = True

    def load_fixes(self, fixes: list[Fix]) -> None:
        """Load fixes into the panel."""
        self._fixes = list(fixes)
        self._current_idx = 0

    def _print(self, *args, **kwargs) -> None:
        """Print with rich or fallback to print."""
        if self._console:
            self._console.print(*args, **kwargs)
        else:
            print(*args, **kwargs)

    def _clear(self) -> None:
        """Clear screen."""
        if self._console:
            self._console.clear()
        else:
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()

    def show_summary(self) -> None:
        """Show summary table of all fixes."""
        self._clear()

        if not self._fixes:
            self._print("[bold]No fixes loaded.[/bold]")
            return

        errors = sum(1 for f in self._fixes if f.severity == FixSeverity.ERROR)
        warnings = sum(1 for f in self._fixes if f.severity == FixSeverity.WARNING)
        infos = sum(1 for f in self._fixes if f.severity == FixSeverity.INFO)

        self._print(f"\n[bold]Fix Summary[/bold] — {len(self._fixes)} fixes")
        self._print(f"  Errors: [red]{errors}[/red]  ")
        self._print(f"Warnings: [yellow]{warnings}[/yellow]  ")
        self._print(f"Info: [blue]{infos}[/blue]\n")

        if RICH_AVAILABLE:
            table = Table(show_header=True, header_style="bold")
            table.add_column("#", style="dim", width=3)
            table.add_column("File")
            table.add_column("Line", justify="right")
            table.add_column("Sev", width=7)
            table.add_column("Rule", width=15)
            table.add_column("Reason")

            for i, fix in enumerate(self._fixes, 1):
                sev_color = {
                    FixSeverity.ERROR: "red",
                    FixSeverity.WARNING: "yellow",
                    FixSeverity.INFO: "blue",
                }.get(fix.severity, "white")

                status_color = {
                    FixStatus.APPLIED: "green",
                    FixStatus.REJECTED: "red",
                    FixStatus.FAILED: "red",
                    FixStatus.SKIPPED: "dim",
                    FixStatus.PENDING: "white",
                }.get(fix.status, "white")

                table.add_row(
                    str(i),
                    fix.file_path[:40],
                    str(fix.line_start),
                    f"[{sev_color}]{fix.severity.value}[/{sev_color}]",
                    fix.rule_id[:15] if fix.rule_id else "-",
                    fix.reason[:50] if fix.reason else "-",
                )
            self._console.print(table)
        else:
            self._print(f"{'#':<3} {'File':<40} {'Line':<6} {'Sev':<8} {'Reason'}")
            self._print("-" * 80)
            for i, fix in enumerate(self._fixes, 1):
                self._print(
                    f"{i:<3} {fix.file_path[:38]:<40} "
                    f"{fix.line_start:<6} {fix.severity.value:<8} "
                    f"{fix.reason[:40] if fix.reason else '-'}"
                )

    def show_fix_detail(self, fix: Fix) -> None:
        """Show detailed view of a single fix."""
        self._clear()

        sev_color = {
            FixSeverity.ERROR: "red",
            FixSeverity.WARNING: "yellow",
            FixSeverity.INFO: "blue",
        }.get(fix.severity, "white")

        status_icon = {
            FixStatus.APPLIED: "[green]✓ APPLIED[/green]",
            FixStatus.REJECTED: "[red]✗ REJECTED[/red]",
            FixStatus.FAILED: "[red]✗ FAILED[/red]",
            FixStatus.SKIPPED: "[dim]— SKIPPED[/dim]",
            FixStatus.PENDING: "[white]○ PENDING[/white]",
        }.get(fix.status, "")

        header = f"Fix #{fix.id} {status_icon}"
        self._print(f"\n[bold]{header}[/bold]")
        self._print(f"File: [cyan]{fix.file_path}[/cyan]:{fix.line_start}")
        self._print(f"Severity: [{sev_color}]{fix.severity.value.upper()}[/{sev_color}]")
        self._print(f"Rule: {fix.rule_id if fix.rule_id else '-'}")
        self._print(f"Confidence: {fix.confidence:.0%}")
        self._print(f"Created by: {fix.created_by}")
        self._print(f"\n[bold]Reason:[/bold] {fix.reason}")

        if fix.llm_explanation:
            self._print(f"\n[bold]LLM Explanation:[/bold]")
            self._print(fix.llm_explanation)

        self._print("\n[bold]Current code:[/bold]")
        self._print(self._format_old_text(fix.old_text))

        self._print("\n[bold]Suggested fix:[/bold]")
        self._print(self._format_new_text(fix.new_text))

    def _format_old_text(self, text: str) -> str:
        """Format old text for display."""
        if not text:
            return "(no old text specified)"
        if RICH_AVAILABLE:
            syntax = Syntax(text, "python", theme="monokai", line_numbers=True)
            return syntax
        return text

    def _format_new_text(self, text: str) -> str:
        """Format new text for display."""
        if not text:
            return "(no new text specified)"
        if RICH_AVAILABLE:
            syntax = Syntax(text, "python", theme="monokai", line_numbers=True)
            return syntax
        return text

    def show_diff_preview(self, fix: Fix) -> None:
        """Show colored diff for a fix."""
        self._clear()
        self._print(f"\n[bold]Diff Preview:[/bold] {fix.file_path}:{fix.line_start}\n")

        self._print("[red]- OLD TEXT (to be removed)[/red]")
        old_lines = fix.old_text.split("\n") if fix.old_text else []
        for i, line in enumerate(old_lines, fix.line_start):
            self._print(f"  {i:4d} | {line}")

        self._print()
        self._print("[green]+ NEW TEXT (to be added)[/green]")
        new_lines = fix.new_text.split("\n") if fix.new_text else []
        for i, line in enumerate(new_lines, fix.line_start):
            self._print(f"  {i:4d} | {line}")

    def interactive_loop(self) -> FixBatch:
        """Main interactive loop for fix management."""
        if not self._fixes:
            return FixBatch()

        batch = FixBatch()
        for fix in self._fixes:
            batch.add(fix)

        commands = {
            "n": self._next_fix,
            "p": self._prev_fix,
            "a": self._apply_current,
            "r": self._reject_current,
            "s": self._skip_current,
            "v": self._view_detail,
            "d": self._view_diff,
            "q": self._quit,
            "A": lambda: self._apply_all(batch),
            "R": lambda: self._reject_all(batch),
        }

        self._show_prompt()

        while self._interactive and self._current_idx < len(self._fixes):
            fix = self._fixes[self._current_idx]
            self._print_status(fix, batch)

            try:
                cmd = input("\n> ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                cmd = "q"

            if cmd == "q":
                break
            elif cmd in commands:
                action = commands[cmd]
                if callable(action):
                    action()
            else:
                self._print("Unknown command. Valid: n, p, a, r, s, v, d, A, R, q")

        batch.update_counters()
        return batch

    def _show_prompt(self) -> None:
        """Show navigation commands."""
        self._print("\n[bold]Commands:[/bold]")
        self._print("  [cyan]n[/cyan]/[cyan]p[/cyan] - Next/Previous fix")
        self._print("  [cyan]a/r/s[/cyan] - Apply/Reject/Skip current fix")
        self._print("  [cyan]A/R[/cyan] - Apply/Reject all remaining")
        self._print("  [cyan]v/d[/cyan] - View detail/diff")
        self._print("  [cyan]q[/cyan] - Quit and return batch")

    def _print_status(self, fix: Fix, batch: FixBatch) -> None:
        """Print current status line."""
        progress = f"Fix {self._current_idx + 1}/{len(self._fixes)}"
        applied = batch.applied
        rejected = batch.rejected
        skipped = sum(1 for f in self._fixes if f.status == FixStatus.SKIPPED)

        status_line = (
            f"{progress} | "
            f"[green]✓{applied}[/green] "
            f"[red]✗{rejected}[/red] "
            f"[dim]−{skipped}[/dim]"
        )
        self._print(f"\n{status_line}")
        self._print(f"Current: {fix.file_path}:{fix.line_start} — {fix.reason[:60]}")

    def _next_fix(self) -> None:
        """Move to next fix."""
        if self._current_idx < len(self._fixes) - 1:
            self._current_idx += 1

    def _prev_fix(self) -> None:
        """Move to previous fix."""
        if self._current_idx > 0:
            self._current_idx -= 1

    def _apply_current(self) -> None:
        """Apply the current fix."""
        if self._current_idx < len(self._fixes):
            fix = self._fixes[self._current_idx]
            result = self._apply_tool.apply_fix(fix)
            if result.success:
                self._print(f"[green]Applied fix {fix.id}[/green]")
            else:
                self._print(f"[red]Failed: {result.error}[/red]")

    def _reject_current(self) -> None:
        """Reject the current fix."""
        if self._current_idx < len(self._fixes):
            fix = self._fixes[self._current_idx]
            fix.mark_rejected()
            self._print(f"[yellow]Rejected fix {fix.id}[/yellow]")

    def _skip_current(self) -> None:
        """Skip the current fix."""
        if self._current_idx < len(self._fixes):
            fix = self._fixes[self._current_idx]
            fix.status = FixStatus.SKIPPED
            self._print(f"[dim]Skipped fix {fix.id}[/dim]")

    def _view_detail(self) -> None:
        """View current fix in detail."""
        if self._current_idx < len(self._fixes):
            self.show_fix_detail(self._fixes[self._current_idx])
            input("\nPress Enter to continue...")

    def _view_diff(self) -> None:
        """View current fix diff."""
        if self._current_idx < len(self._fixes):
            self.show_diff_preview(self._fixes[self._current_idx])
            input("\nPress Enter to continue...")

    def _apply_all(self, batch: FixBatch) -> None:
        """Apply all remaining fixes."""
        remaining = [
            f for f in self._fixes[self._current_idx:]
            if f.status == FixStatus.PENDING
        ]
        if remaining:
            self._print(f"Applying {len(remaining)} fixes...")
            result_batch = self._apply_tool.apply_batch(remaining)
            for fix in remaining:
                batch.add(fix)
            batch.update_counters()
            self._print(f"[green]Applied {result_batch.applied} fixes[/green]")
        self._current_idx = len(self._fixes)

    def _reject_all(self, batch: FixBatch) -> None:
        """Reject all remaining fixes."""
        remaining = [
            f for f in self._fixes[self._current_idx:]
            if f.status == FixStatus.PENDING
        ]
        for fix in remaining:
            fix.mark_rejected()
            batch.add(fix)
        batch.update_counters()
        self._print(f"[yellow]Rejected {len(remaining)} fixes[/yellow]")
        self._current_idx = len(self._fixes)

    def _quit(self) -> None:
        """Quit the interactive loop."""
        self._interactive = False
