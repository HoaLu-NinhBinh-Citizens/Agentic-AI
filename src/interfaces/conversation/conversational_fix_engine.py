"""Conversational fix engine for interactive code fix workflow.

This module provides conversational UX for applying fixes with:
- Multi-option tradeoffs
- Risk explanations
- User preference learning
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from src.core.fix_engine.llm_suggester import LLMSuggester


class UXAction(Enum):
    APPLY = "apply"
    SKIP = "skip"
    EXPLAIN_RISK = "explain_risk"
    EXPLAIN_TRADEOFF = "explain_tradeoff"
    PREVIEW = "preview"
    CHOOSE_OPTION = "choose_option"
    APPLY_ALL_CRITICAL = "apply_all_critical"
    UNDO_LAST = "undo_last"
    QUIT = "quit"
    HELP = "help"


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class FixOption:
    """A single fix option with metadata."""
    index: int
    label: str
    new_code: str
    old_code: str = ""
    confidence: float = 0.8
    risk: RiskLevel = RiskLevel.MEDIUM
    explanation: str = ""
    tradeoffs: list[str] = field(default_factory=list)

    def risk_color(self) -> str:
        """Return ANSI color code for risk level."""
        colors = {
            RiskLevel.LOW: "\033[92m",      # Green
            RiskLevel.MEDIUM: "\033[93m",   # Yellow
            RiskLevel.HIGH: "\033[91m",     # Red
            RiskLevel.CRITICAL: "\033[95m", # Magenta
        }
        return colors.get(self.risk, "\033[0m")


@dataclass
class FixContext:
    """Context for a single fix."""
    file_path: str
    line: int
    rule_id: str
    message: str
    explanation: str
    root_cause: str
    old_code: str = ""
    options: list[FixOption] = field(default_factory=list)
    severity: str = "warning"

    def is_critical(self) -> bool:
        """Check if this is a critical severity."""
        return self.severity.upper() in ("CRITICAL", "ERROR")


@dataclass
class FixDecision:
    """User's decision for a fix."""
    action: UXAction
    chosen_option_index: Optional[int] = None
    reason: Optional[str] = None


@dataclass
class ConversationState:
    """State of conversational fix session."""
    fixes: list[FixContext]
    current_index: int = 0
    decisions: dict[int, FixDecision] = field(default_factory=dict)
    applied: list[int] = field(default_factory=list)
    skipped: list[int] = field(default_factory=list)
    undo_stack: list[int] = field(default_factory=list)

    @property
    def remaining(self) -> int:
        """Number of remaining fixes."""
        return len(self.fixes) - self.current_index

    @property
    def current(self) -> Optional[FixContext]:
        """Get current fix context."""
        if 0 <= self.current_index < len(self.fixes):
            return self.fixes[self.current_index]
        return None

    def advance(self) -> bool:
        """Move to next fix. Returns False if no more fixes."""
        self.current_index += 1
        return self.current is not None

    def record_applied(self, index: int) -> None:
        """Record an applied fix."""
        if index not in self.applied:
            self.applied.append(index)
            self.undo_stack.append(index)

    def record_skipped(self, index: int) -> None:
        """Record a skipped fix."""
        if index not in self.skipped:
            self.skipped.append(index)

    def undo_last(self) -> Optional[int]:
        """Undo the last applied fix. Returns the index."""
        if self.undo_stack:
            index = self.undo_stack.pop()
            if index in self.applied:
                self.applied.remove(index)
            return index
        return None


@dataclass
class ConversationResult:
    """Result of conversational session."""
    applied: list[FixContext]
    skipped: list[FixContext]
    summary: str

    @property
    def applied_count(self) -> int:
        return len(self.applied)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)


class ConversationalFixEngine:
    """Engine for conversational fix workflow.

    Provides interactive UX for applying code fixes with:
    - Multiple fix options with tradeoffs
    - Risk explanations
    - Auto-critic mode for critical fixes
    - Undo support
    """

    def __init__(
        self,
        fixer: Any = None,
        llm_suggester: Optional[LLMSuggester] = None,
        formatter: Any = None,
    ) -> None:
        """Initialize the conversational fix engine.

        Args:
            fixer: Fix applicator tool
            llm_suggester: Optional LLM for tradeoff analysis
            formatter: Output formatter (uses default if None)
        """
        self.fixer = fixer
        self.llm_suggester = llm_suggester
        self._formatter = formatter

        # Import default formatter if needed
        if self._formatter is None:
            try:
                from src.interfaces.conversation.formatters import (
                    ConsoleConversationFormatter,
                )
                self._formatter = ConsoleConversationFormatter()
            except ImportError:
                self._formatter = None

    async def run_session(
        self,
        findings: list[Any],
        workspace_root: str,
        auto_critical: bool = False,
    ) -> ConversationResult:
        """Run interactive session for all findings.

        Args:
            findings: List of findings from review
            workspace_root: Root directory of workspace
            auto_critical: If True, auto-apply critical fixes

        Returns:
            ConversationResult with session outcomes
        """
        # Convert findings to FixContext
        contexts = await self._build_fix_contexts(findings)

        if not contexts:
            return ConversationResult(
                applied=[],
                skipped=[],
                summary="No fixable issues found.",
            )

        state = ConversationState(fixes=contexts)
        applied_contexts: list[FixContext] = []
        skipped_contexts: list[FixContext] = []

        # Process each fix
        while state.current is not None:
            context = state.current

            # Auto-apply critical if enabled
            if auto_critical and context.is_critical():
                await self._apply_fix(context, state)
                applied_contexts.append(context)
                state.advance()
                continue

            # Show intro and get decision
            intro = await self._show_fix_intro(context)
            print(intro)

            decision = await self._prompt_user(context)

            # Process decision
            if decision.action == UXAction.APPLY:
                await self._apply_fix(context, state, decision.chosen_option_index)
                applied_contexts.append(context)
                state.advance()

            elif decision.action == UXAction.SKIP:
                state.record_skipped(state.current_index)
                skipped_contexts.append(context)
                state.advance()

            elif decision.action == UXAction.EXPLAIN_RISK:
                explanation = await self._show_risk_explanation(
                    context, decision.chosen_option_index or 0
                )
                print(explanation)

            elif decision.action == UXAction.EXPLAIN_TRADEOFF:
                explanation = await self._show_tradeoff(context)
                print(explanation)

            elif decision.action == UXAction.PREVIEW:
                preview = await self._show_preview(context, decision.chosen_option_index or 0)
                print(preview)

            elif decision.action == UXAction.APPLY_ALL_CRITICAL:
                # Apply current and all remaining critical
                while state.current is not None:
                    if state.current.is_critical():
                        await self._apply_fix(state.current, state)
                        applied_contexts.append(state.current)
                    else:
                        state.record_skipped(state.current_index)
                        skipped_contexts.append(state.current)
                    state.advance()

            elif decision.action == UXAction.UNDO_LAST:
                undone_index = state.undo_last()
                if undone_index is not None and undone_index < len(applied_contexts):
                    applied_contexts.pop()
                print("Undid last applied fix.")

            elif decision.action == UXAction.QUIT:
                # Mark remaining as skipped
                while state.current is not None:
                    state.record_skipped(state.current_index)
                    skipped_contexts.append(state.current)
                    state.advance()
                break

            elif decision.action == UXAction.HELP:
                help_text = self._show_help()
                print(help_text)

            else:
                state.advance()

        summary = self._build_summary(state)
        return ConversationResult(
            applied=applied_contexts,
            skipped=skipped_contexts,
            summary=summary,
        )

    async def _build_fix_contexts(
        self, findings: list[Any]
    ) -> list[FixContext]:
        """Build FixContext from findings.

        Args:
            findings: List of Finding objects

        Returns:
            List of FixContext
        """
        contexts: list[FixContext] = []

        for finding in findings:
            # Extract metadata
            file_path = getattr(finding, "file", "unknown")
            line = getattr(finding, "line", 1)
            rule_id = getattr(finding, "rule_id", "UNKNOWN")
            message = getattr(finding, "message", "")
            explanation = getattr(finding, "explanation", "")
            root_cause = getattr(finding, "root_cause", "")
            severity = getattr(finding, "severity", "warning")

            if isinstance(severity, Enum):
                severity = severity.value

            # Get old code
            metadata = getattr(finding, "metadata", {}) or {}
            old_code = metadata.get("old_code", "")

            # Get fix options
            options: list[FixOption] = []

            # From metadata
            new_code = metadata.get("new_code", "")
            if new_code:
                options.append(FixOption(
                    index=0,
                    label="Recommended Fix",
                    new_code=new_code,
                    old_code=old_code,
                    confidence=0.9,
                    risk=RiskLevel.MEDIUM,
                    explanation="Standard recommended fix",
                ))

            # From fix field
            fix = getattr(finding, "fix", "")
            if fix and not options:
                options.append(FixOption(
                    index=0,
                    label="Suggested Fix",
                    new_code=fix,
                    old_code=old_code,
                    confidence=0.8,
                    risk=RiskLevel.MEDIUM,
                ))

            # Generate options with LLM if available
            if not options and self.llm_suggester:
                llm_options = await self._generate_llm_options(finding)
                options.extend(llm_options)

            # Add safe/alternative options
            if options:
                options.append(FixOption(
                    index=len(options),
                    label="Skip for Now",
                    new_code="",
                    old_code=old_code,
                    confidence=0.0,
                    risk=RiskLevel.LOW,
                    explanation="Skip this fix temporarily",
                ))

            context = FixContext(
                file_path=str(file_path),
                line=int(line),
                rule_id=str(rule_id),
                message=str(message),
                explanation=str(explanation),
                root_cause=str(root_cause),
                old_code=str(old_code),
                options=options,
                severity=str(severity),
            )
            contexts.append(context)

        return contexts

    async def _generate_llm_options(
        self, finding: Any
    ) -> list[FixOption]:
        """Generate fix options using LLM.

        Args:
            finding: Finding object

        Returns:
            List of FixOption
        """
        if not self.llm_suggester:
            return []

        try:
            from src.core.fix_engine.llm_suggester import CodeContext
            context = CodeContext.from_file(finding.file, finding.line)
            suggestion = await self.llm_suggester.suggest_fix(finding, context)

            if suggestion:
                return [
                    FixOption(
                        index=0,
                        label="LLM-Generated Fix",
                        new_code=suggestion.suggested_code,
                        old_code=context.get_relevant_code(finding.line),
                        confidence=suggestion.confidence,
                        risk=RiskLevel.MEDIUM,
                        explanation=suggestion.explanation,
                        tradeoffs=suggestion.alternative_suggestions,
                    )
                ]
        except Exception:
            pass

        return []

    async def _show_fix_intro(self, context: FixContext) -> str:
        """Generate introduction for a fix.

        Args:
            context: Fix context

        Returns:
            Formatted intro text
        """
        severity_icons = {
            "CRITICAL": "[X]",
            "ERROR": "[X]",
            "WARNING": "[!]",
            "INFO": "[i]",
        }
        icon = severity_icons.get(context.severity.upper(), "?")

        lines = [
            "",
            f"{'=' * 60}",
            f"{icon} Fix: [{context.rule_id}] - {context.severity.upper()} severity",
            f"{'=' * 60}",
            f"File: {context.file_path}:{context.line}",
            f"",
            f"Issue: {context.message}",
            f"",
        ]

        if context.explanation:
            lines.append(f"Why: {context.explanation}")
            lines.append("")

        if context.options:
            lines.append("Options:")
            for opt in context.options:
                risk_indicator = self._risk_indicator(opt.risk)
                lines.append(
                    f"  [{opt.index}] {opt.label} {risk_indicator}"
                )
            lines.append("")

        lines.append("Actions: [a]pply [s]kip [t]radeoff [r]isk [h]elp [q]uit")
        lines.append("")

        return "\n".join(lines)

    def _risk_indicator(self, risk: RiskLevel) -> str:
        """Generate risk indicator string."""
        indicators = {
            RiskLevel.LOW: "(LOW risk)",
            RiskLevel.MEDIUM: "(MEDIUM risk)",
            RiskLevel.HIGH: "(HIGH risk)",
            RiskLevel.CRITICAL: "(CRITICAL risk)",
        }
        return indicators.get(risk, "")

    async def _show_options(
        self, context: FixContext
    ) -> str:
        """Show fix options with tradeoffs.

        Args:
            context: Fix context

        Returns:
            Formatted options text
        """
        if not context.options:
            return "No options available for this fix."

        lines = ["", "Fix Options:", ""]

        for opt in context.options:
            risk = opt.risk.value.upper()
            lines.append(f"[{opt.index}] {opt.label} - {risk} risk")
            lines.append(f"    Confidence: {opt.confidence * 100:.0f}%")
            if opt.explanation:
                lines.append(f"    {opt.explanation}")
            if opt.tradeoffs:
                lines.append("    Tradeoffs:")
                for tradeoff in opt.tradeoffs:
                    lines.append(f"      - {tradeoff}")
            lines.append("")

        return "\n".join(lines)

    async def _show_risk_explanation(
        self,
        context: FixContext,
        option_index: int,
    ) -> str:
        """Explain risk of a specific option.

        Args:
            context: Fix context
            option_index: Index of the option

        Returns:
            Risk explanation text
        """
        if option_index >= len(context.options):
            return "Invalid option index."

        option = context.options[option_index]

        lines = [
            "",
            f"Risk Analysis for [{option.label}]:",
            f"",
            f"Risk Level: {option.risk.value.upper()}",
            f"Confidence: {option.confidence * 100:.0f}%",
            f"",
        ]

        if option.explanation:
            lines.append(f"Explanation:\n{option.explanation}")
            lines.append("")

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

        lines.append("Considerations:")
        if option.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            lines.append("- This fix modifies critical code paths")
            lines.append("- Test thoroughly after applying")
            lines.append("- Consider creating a backup first")
        else:
            lines.append("- This is a low-risk change")
            lines.append("- Standard testing should suffice")

        return "\n".join(lines)

    async def _show_tradeoff(
        self, context: FixContext
    ) -> str:
        """Compare tradeoffs between options.

        Args:
            context: Fix context

        Returns:
            Tradeoff comparison text
        """
        if not context.options or len(context.options) < 2:
            return "Not enough options to compare."

        lines = [
            "",
            "Tradeoff Analysis:",
            "",
        ]

        for i, opt in enumerate(context.options):
            risk = opt.risk.value.upper()
            lines.append(f"Option [{i}] {opt.label}:")
            lines.append(f"  Risk: {risk}")
            lines.append(f"  Confidence: {opt.confidence * 100:.0f}%")

            if opt.tradeoffs:
                lines.append("  Tradeoffs:")
                for tradeoff in opt.tradeoffs:
                    lines.append(f"    - {tradeoff}")
            lines.append("")

        # Use LLM for deeper analysis if available
        if self.llm_suggester and len(context.options) > 1:
            analysis = await self._generate_tradeoff_analysis(context)
            if analysis:
                lines.append("LLM Analysis:")
                lines.append(analysis)

        return "\n".join(lines)

    async def _generate_tradeoff_analysis(
        self,
        context: FixContext,
    ) -> str:
        """Use LLM to analyze tradeoffs if available.

        Args:
            context: Fix context

        Returns:
            LLM-generated analysis or empty string
        """
        if not self.llm_suggester:
            return ""

        try:
            prompt = self._build_tradeoff_prompt(context)
            response = await self.llm_suggester.llm_provider.complete(
                prompt=prompt,
                max_tokens=500,
                temperature=0.3,
            )
            return response
        except Exception:
            return ""

    def _build_tradeoff_prompt(self, context: FixContext) -> str:
        """Build tradeoff analysis prompt.

        Args:
            context: Fix context

        Returns:
            Formatted prompt
        """
        from src.interfaces.conversation.prompts import TRADEOFF_PROMPT

        options_text = ""
        for i, opt in enumerate(context.options):
            options_text += f"[{i}] {opt.label}: {opt.explanation}\n"
            if opt.tradeoffs:
                options_text += f"    Tradeoffs: {', '.join(opt.tradeoffs)}\n"

        return TRADEOFF_PROMPT.format(
            message=context.message,
            file_path=context.file_path,
            line=context.line,
            explanation=context.explanation,
            options=options_text,
        )

    async def _show_preview(
        self,
        context: FixContext,
        option_index: int,
    ) -> str:
        """Show diff preview for an option.

        Args:
            context: Fix context
            option_index: Option to preview

        Returns:
            Diff preview text
        """
        if option_index >= len(context.options):
            return "Invalid option index."

        option = context.options[option_index]

        lines = [
            "",
            f"Preview for [{option.label}]:",
            "",
            "```diff",
        ]

        if context.old_code:
            lines.append(f"- {context.old_code}")
        if option.new_code:
            lines.append(f"+ {option.new_code}")

        lines.extend(["```", ""])

        return "\n".join(lines)

    async def _prompt_user(self, context: FixContext) -> FixDecision:
        """Prompt user for decision.

        Args:
            context: Current fix context

        Returns:
            User's decision
        """
        # For now, return a default decision
        # In real CLI, this would read from stdin
        return FixDecision(action=UXAction.SKIP)

    def _parse_response(self, response: str) -> FixDecision:
        """Parse user response into FixDecision.

        Args:
            response: User input string

        Returns:
            Parsed decision
        """
        response = response.strip().lower()

        # Check for numbered option
        number_match = re.match(r"^(\d+)$", response)
        if number_match:
            option_index = int(number_match.group(1))
            return FixDecision(
                action=UXAction.CHOOSE_OPTION,
                chosen_option_index=option_index,
            )

        # Keyword shortcuts
        shortcuts = {
            "a": UXAction.APPLY,
            "apply": UXAction.APPLY,
            "y": UXAction.APPLY,
            "yes": UXAction.APPLY,
            "s": UXAction.SKIP,
            "skip": UXAction.SKIP,
            "n": UXAction.SKIP,
            "no": UXAction.SKIP,
            "t": UXAction.EXPLAIN_TRADEOFF,
            "tradeoff": UXAction.EXPLAIN_TRADEOFF,
            "r": UXAction.EXPLAIN_RISK,
            "risk": UXAction.EXPLAIN_RISK,
            "p": UXAction.PREVIEW,
            "preview": UXAction.PREVIEW,
            "c": UXAction.APPLY_ALL_CRITICAL,
            "critical": UXAction.APPLY_ALL_CRITICAL,
            "u": UXAction.UNDO_LAST,
            "undo": UXAction.UNDO_LAST,
            "q": UXAction.QUIT,
            "quit": UXAction.QUIT,
            "h": UXAction.HELP,
            "help": UXAction.HELP,
        }

        action = shortcuts.get(response)
        if action:
            return FixDecision(action=action)

        return FixDecision(action=UXAction.SKIP)

    async def _apply_fix(
        self,
        context: FixContext,
        state: ConversationState,
        option_index: int = 0,
    ) -> bool:
        """Apply a fix.

        Args:
            context: Fix context
            state: Conversation state
            option_index: Option to apply

        Returns:
            True if successful
        """
        if not self.fixer or option_index >= len(context.options):
            state.record_applied(state.current_index)
            return False

        option = context.options[option_index]

        try:
            if hasattr(self.fixer, "apply_fix"):
                success, _ = await self.fixer.apply_fix(
                    file_path=context.file_path,
                    line=context.line,
                    new_code=option.new_code,
                    old_code=context.old_code,
                )
            else:
                success = False

            state.record_applied(state.current_index)
            return success
        except Exception:
            state.record_applied(state.current_index)
            return False

    def _build_summary(self, state: ConversationState) -> str:
        """Build session summary.

        Args:
            state: Final conversation state

        Returns:
            Summary text
        """
        total = len(state.fixes)
        applied = len(state.applied)
        skipped = len(state.skipped)

        lines = [
            "",
            f"{'=' * 60}",
            "Session Summary",
            f"{'=' * 60}",
            f"Total fixes: {total}",
            f"Applied: {applied}",
            f"Skipped: {skipped}",
        ]

        if state.undo_stack:
            lines.append(f"Undo operations: {len(state.undo_stack)}")

        lines.append("")

        if state.applied:
            lines.append("Applied fixes:")
            for idx in state.applied:
                if idx < len(state.fixes):
                    ctx = state.fixes[idx]
                    lines.append(f"  - {ctx.file_path}:{ctx.line} [{ctx.rule_id}]")

        return "\n".join(lines)

    def _show_help(self) -> str:
        """Show help text.

        Returns:
            Help text
        """
        return """
Conversational Fix Help
=======================

Actions:
  a, apply, y, yes  - Apply the current fix
  s, skip, n, no     - Skip this fix
  t, tradeoff        - Show tradeoff comparison
  r, risk            - Explain risks
  p, preview         - Preview the change
  c, critical        - Apply all critical fixes
  u, undo             - Undo last applied fix
  q, quit             - Quit session
  h, help             - Show this help

Shortcuts:
  0, 1, 2, ...       - Select option by number
  --auto-critical     - Auto-apply critical fixes
  --explain           - Explain all findings
  --tradeoff, -t      - Show tradeoff analysis

Examples:
  /fix @file.py:42 --interactive --auto-critical
  /fix @file.py:42 -i -t
"""
