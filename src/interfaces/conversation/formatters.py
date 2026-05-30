"""Rich CLI formatters for conversational UX.

This module provides terminal-friendly formatters for displaying:
- Fix introductions
- Options with risk indicators
- Progress bars
- Diff previews
- Session summaries
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.interfaces.conversation.conversational_fix_engine import (
    ConversationResult,
    FixContext,
    FixOption,
    RiskLevel,
)


class Color:
    """ANSI color codes for terminal output."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Foreground colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright colors
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"


class ConsoleConversationFormatter:
    """Format conversational UX for terminal with colors and rich output."""

    def __init__(self, use_colors: bool = True) -> None:
        """Initialize formatter.

        Args:
            use_colors: Whether to use ANSI colors (default: True)
        """
        self.use_colors = use_colors

    def _color(self, text: str, color: str) -> str:
        """Apply color to text."""
        if not self.use_colors:
            return text
        return f"{color}{text}{Color.RESET}"

    def _bold(self, text: str) -> str:
        """Make text bold."""
        if not self.use_colors:
            return text
        return f"{Color.BOLD}{text}{Color.RESET}"

    def _dim(self, text: str) -> str:
        """Make text dim."""
        if not self.use_colors:
            return text
        return f"{Color.DIM}{text}{Color.RESET}"

    def format_intro(self, context: FixContext) -> str:
        """Format fix introduction.

        Args:
            context: Fix context to format

        Returns:
            Formatted intro text
        """
        severity_colors = {
            "CRITICAL": Color.BRIGHT_MAGENTA,
            "ERROR": Color.BRIGHT_RED,
            "WARNING": Color.BRIGHT_YELLOW,
            "INFO": Color.BRIGHT_CYAN,
        }
        sev_color = severity_colors.get(context.severity.upper(), Color.WHITE)

        severity_icon = {
            "CRITICAL": "[X]",
            "ERROR": "[X]",
            "WARNING": "[!]",
            "INFO": "[i]",
        }.get(context.severity.upper(), "?")

        lines = [
            "",
            self._bold(f"{'=' * 60}"),
            f"{self._color(severity_icon, sev_color)} "
            f"{self._bold(f'[{context.rule_id}]')} - "
            f"{self._color(context.severity.upper(), sev_color)} severity",
            self._bold(f"{'=' * 60}"),
            f"File: {self._color(context.file_path, Color.CYAN)}:{self._color(str(context.line), Color.CYAN)}",
            "",
            f"Issue: {context.message}",
            "",
        ]

        if context.explanation:
            lines.append(self._dim(f"Why: {context.explanation}"))
            lines.append("")

        return "\n".join(lines)

    def format_options(self, options: list[FixOption]) -> str:
        """Format options with risk indicators.

        Args:
            options: List of fix options

        Returns:
            Formatted options text
        """
        if not options:
            return "No options available."

        lines = [self._bold("Options:"), ""]

        for opt in options:
            risk_color = self._get_risk_color(opt.risk)
            risk_text = self._risk_text(opt.risk)

            # Option label with index
            option_line = f"  [{self._color(str(opt.index), Color.CYAN)}] "
            option_line += self._bold(opt.label)
            option_line += f" {self._color(risk_text, risk_color)}"
            lines.append(option_line)

            # Confidence
            confidence_bar = self._make_progress_bar(opt.confidence, 10)
            lines.append(f"      Confidence: {confidence_bar} {opt.confidence * 100:.0f}%")

            # Explanation
            if opt.explanation:
                lines.append(f"      {self._dim(opt.explanation)}")

            # Tradeoffs
            if opt.tradeoffs:
                lines.append("      Tradeoffs:")
                for tradeoff in opt.tradeoffs[:3]:
                    lines.append(f"        - {self._dim(tradeoff)}")

            lines.append("")

        return "\n".join(lines)

    def format_risk_indicator(self, risk: RiskLevel) -> str:
        """Format risk as colored indicator.

        Args:
            risk: Risk level

        Returns:
            Formatted risk indicator
        """
        color = self._get_risk_color(risk)
        text = self._risk_text(risk)
        return self._color(f"[{text}]", color)

    def _get_risk_color(self, risk: RiskLevel) -> str:
        """Get color for risk level."""
        colors = {
            RiskLevel.LOW: Color.GREEN,
            RiskLevel.MEDIUM: Color.YELLOW,
            RiskLevel.HIGH: Color.RED,
            RiskLevel.CRITICAL: Color.MAGENTA,
        }
        return colors.get(risk, Color.WHITE)

    def _risk_text(self, risk: RiskLevel) -> str:
        """Get text representation of risk."""
        texts = {
            RiskLevel.LOW: "LOW risk",
            RiskLevel.MEDIUM: "MEDIUM risk",
            RiskLevel.HIGH: "HIGH risk",
            RiskLevel.CRITICAL: "CRITICAL risk",
        }
        return texts.get(risk, "UNKNOWN risk")

    def _make_progress_bar(self, value: float, width: int) -> str:
        """Create a text progress bar.

        Args:
            value: Value between 0.0 and 1.0
            width: Bar width in characters

        Returns:
            Progress bar string
        """
        filled = int(value * width)
        empty = width - filled

        filled_color = self._color("█" * filled, Color.GREEN)
        empty_color = self._color("░" * empty, Color.DIM)
        return f"[{filled_color}{empty_color}]"

    def format_progress(self, current: int, total: int) -> str:
        """Format progress bar.

        Args:
            current: Current item number (1-based)
            total: Total items

        Returns:
            Formatted progress bar
        """
        if total == 0:
            percentage = 100
        else:
            percentage = int((current / total) * 100)

        bar_width = 30
        filled = int((current / max(total, 1)) * bar_width)
        bar = self._color("█" * filled, Color.CYAN) + self._color("░" * (bar_width - filled), Color.DIM)

        return f"[{bar}] {percentage}% ({current}/{total})"

    def format_diff_preview(
        self,
        old_code: str,
        new_code: str,
        file_path: str = "",
        line: int = 0,
    ) -> str:
        """Format diff preview.

        Args:
            old_code: Original code
            new_code: New code
            file_path: File path for header
            line: Line number for header

        Returns:
            Formatted diff preview
        """
        lines = [self._bold("Diff Preview:")]

        if file_path:
            lines.append(f"{self._dim(file_path)}:{line}")
            lines.append("")

        lines.append("```diff")
        lines.append(self._color("- " + old_code, Color.RED))
        lines.append(self._color("+ " + new_code, Color.GREEN))
        lines.append("```")

        return "\n".join(lines)

    def format_summary(self, result: ConversationResult) -> str:
        """Format final summary.

        Args:
            result: Session result

        Returns:
            Formatted summary
        """
        total = result.applied_count + result.skipped_count

        # Stats box
        lines = [
            "",
            self._bold(f"{'=' * 60}"),
            self._bold("Session Summary"),
            self._bold(f"{'=' * 60}"),
            "",
        ]

        # Stats with colors
        applied_color = Color.GREEN if result.applied_count > 0 else Color.DIM
        skipped_color = Color.YELLOW if result.skipped_count > 0 else Color.DIM

        lines.append(f"  Total fixes: {self._bold(str(total))}")
        lines.append(f"  Applied: {self._color(str(result.applied_count), applied_color)}")
        lines.append(f"  Skipped: {self._color(str(result.skipped_count), skipped_color)}")
        lines.append("")

        # Applied fixes
        if result.applied:
            lines.append(self._bold("Applied Fixes:"))
            for ctx in result.applied:
                lines.append(
                    f"  {self._color('✓', Color.GREEN)} "
                    f"{self._color(ctx.file_path, Color.CYAN)}:{ctx.line} "
                    f"[{ctx.rule_id}]"
                )
            lines.append("")

        # Skipped fixes
        if result.skipped:
            lines.append(self._bold("Skipped Fixes:"))
            for ctx in result.skipped:
                lines.append(
                    f"  {self._color('○', Color.YELLOW)} "
                    f"{self._color(ctx.file_path, Color.CYAN)}:{ctx.line} "
                    f"[{ctx.rule_id}]"
                )
            lines.append("")

        lines.append(self._bold(f"{'=' * 60}"))

        return "\n".join(lines)

    def format_help(self) -> str:
        """Format help text.

        Returns:
            Formatted help
        """
        return self._bold("""
Conversational Fix Commands
==========================

Actions:
  """ + self._color("a, apply", Color.GREEN) + """, y, yes   Apply the current fix
  """ + self._color("s, skip", Color.YELLOW) + """, n, no    Skip this fix
  """ + self._color("t, tradeoff", Color.CYAN) + """        Show tradeoff comparison
  """ + self._color("r, risk", Color.CYAN) + """             Explain risks
  """ + self._color("p, preview", Color.CYAN) + """           Preview the change
  """ + self._color("c, critical", Color.MAGENTA) + """       Apply all critical fixes
  """ + self._color("u, undo", Color.YELLOW) + """             Undo last applied fix
  """ + self._color("q, quit", Color.RED) + """               Quit session
  """ + self._color("h, help", Color.BLUE) + """              Show this help

Shortcuts:
  0, 1, 2, ...              Select option by number
  --auto-critical             Auto-apply critical fixes
  --explain, -e              Explain all findings
  --tradeoff, -t             Show tradeoff analysis
  --interactive, -i          Interactive mode
""")

    def format_risk_explanation(
        self,
        context: FixContext,
        option_index: int,
    ) -> str:
        """Format detailed risk explanation.

        Args:
            context: Fix context
            option_index: Selected option index

        Returns:
            Formatted risk explanation
        """
        if option_index >= len(context.options):
            return self._color("Invalid option index.", Color.RED)

        option = context.options[option_index]
        risk_color = self._get_risk_color(option.risk)

        lines = [
            "",
            self._bold(f"Risk Analysis: [{option.label}]"),
            self._bold(f"{'=' * 40}"),
            "",
            f"Risk Level: {self._color(option.risk.value.upper(), risk_color)}",
            f"Confidence: {option.confidence * 100:.0f}%",
            "",
        ]

        if option.explanation:
            lines.append("Explanation:")
            lines.append(self._dim(option.explanation))
            lines.append("")

        # Code changes
        if option.old_code:
            lines.append("Before:")
            lines.append("```")
            lines.append(option.old_code)
            lines.append("```")
            lines.append("")

        if option.new_code:
            lines.append("After:")
            lines.append("```")
            lines.append(option.new_code)
            lines.append("```")
            lines.append("")

        # Risk considerations
        lines.append(self._bold("Considerations:"))

        if option.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            lines.append(f"  {self._color('⚠', Color.YELLOW)} This fix modifies critical code paths")
            lines.append(f"  {self._color('⚠', Color.YELLOW)} Test thoroughly after applying")
            lines.append(f"  {self._color('⚠', Color.YELLOW)} Consider creating a backup first")
        else:
            lines.append(f"  {self._color('✓', Color.GREEN)} This is a low-risk change")
            lines.append(f"  {self._color('✓', Color.GREEN)} Standard testing should suffice")

        if option.tradeoffs:
            lines.append("")
            lines.append(self._bold("Tradeoffs:"))
            for tradeoff in option.tradeoffs:
                lines.append(f"  - {self._dim(tradeoff)}")

        return "\n".join(lines)

    def format_tradeoff_comparison(
        self,
        contexts: list[FixContext],
    ) -> str:
        """Format tradeoff comparison between multiple options.

        Args:
            contexts: List of fix contexts to compare

        Returns:
            Formatted comparison
        """
        if not contexts:
            return "No options to compare."

        lines = [
            "",
            self._bold("Tradeoff Comparison"),
            self._bold(f"{'=' * 50}"),
            "",
        ]

        for i, ctx in enumerate(contexts):
            risk_color = Color.GREEN
            if ctx.options:
                option = ctx.options[0]
                risk_color = self._get_risk_color(option.risk)

            lines.append(f"[{i}] {self._bold(ctx.rule_id)}")
            lines.append(f"    File: {ctx.file_path}:{ctx.line}")
            lines.append(f"    Severity: {ctx.severity}")

            if ctx.options:
                opt = ctx.options[0]
                lines.append(
                    f"    Risk: {self._color(opt.risk.value.upper(), risk_color)}"
                )
                lines.append(f"    Confidence: {opt.confidence * 100:.0f}%")

            if ctx.options and ctx.options[0].explanation:
                lines.append(f"    {self._dim(ctx.options[0].explanation[:80])}")

            lines.append("")

        return "\n".join(lines)


def create_formatter(use_colors: bool = True) -> ConsoleConversationFormatter:
    """Create a formatter instance.

    Args:
        use_colors: Whether to use colors

    Returns:
        ConsoleConversationFormatter instance
    """
    return ConsoleConversationFormatter(use_colors=use_colors)
