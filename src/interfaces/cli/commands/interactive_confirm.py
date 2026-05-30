"""Interactive confirmation workflow for fix application.

This module provides an interactive confirmation flow that asks users before
applying fixes, with support for batch operations and auto-approval rules.

Supports:
- Single fix confirmation with code diff preview
- Batch fix processing with progress tracking
- Auto-approval for critical fixes
- Yes-to-all / No-to-all modes
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Protocol

from src.domain.models.review_issue import ReviewIssue
from src.shared.enums.severity import Severity as UnifiedSeverity


class ConfirmAction(Enum):
    """User action for fix confirmation."""
    YES = "y"
    NO = "n"
    YES_TO_ALL = "a"
    NO_TO_ALL = "q"
    EDIT = "e"
    HELP = "h"
    SKIP = "s"


# Alias for Severity from shared.enums (used throughout codebase)
Severity = UnifiedSeverity


class ConfirmAction(Enum):
    """User action for fix confirmation."""
    YES = "y"
    NO = "n"
    YES_TO_ALL = "a"
    NO_TO_ALL = "q"
    EDIT = "e"
    HELP = "h"
    SKIP = "s"


@dataclass
class ConfirmationPrompt:
    """Prompt displayed to user for fix confirmation."""
    index: int
    total: int
    severity_icon: str
    rule_id: str
    file_path: str
    line: int
    message: str
    old_code_preview: str
    new_code_preview: str
    risk_level: str

    def to_display_string(self) -> str:
        """Convert prompt to displayable string."""
        lines = [
            "",
            f"[{self.index}/{self.total}] {self.severity_icon} {self.rule_id}",
            f"  File: {self.file_path}:{self.line}",
            f"  Message: {self.message}",
            "",
            "  Current Code:",
            f"  {self.old_code_preview}",
            "",
            "  Proposed Fix:",
            f"  {self.new_code_preview}",
            "",
            f"  Risk: {self.risk_level}",
            "",
        ]
        return "\n".join(lines)


@dataclass
class BatchResult:
    """Result of batch fix operation."""
    applied_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    total_processed: int = 0
    was_aborted: bool = False
    applied_fix_ids: list[str] = field(default_factory=list)
    skipped_fix_ids: list[str] = field(default_factory=list)


class PromptProvider(Protocol):
    """Protocol for user prompt providers."""

    async def get_confirmation(
        self,
        prompt: ConfirmationPrompt,
        choices: list[str],
    ) -> str:
        """Get user confirmation for a fix."""
        ...


class ConsolePromptProvider:
    """Console-based prompt provider."""

    def __init__(
        self,
        output_writer: Callable[[str], None] = print,
        input_reader: Callable[[str], str] = input,
    ) -> None:
        self._write = output_writer
        self._read = input_reader

    async def get_confirmation(
        self,
        prompt: ConfirmationPrompt,
        choices: list[str],
    ) -> str:
        """Display prompt to console and get user response."""
        self._write(prompt.to_display_string())

        choices_display = "/".join(c.upper() for c in choices)
        self._write(f"  Apply this fix? [{choices_display}]: ")

        response = self._read("").strip().lower()
        return response if response in choices else "n"


class InteractiveConfirmationFlow:
    """Interactive confirmation flow for applying fixes.

    This class manages the interactive confirmation process for applying
    fixes, supporting batch operations and auto-approval rules.

    Usage:
        flow = InteractiveConfirmationFlow()
        result = await flow.run_batch(findings, apply_func)
        print(f"Applied {result.applied_count} fixes")
    """

    def __init__(
        self,
        prompt_provider: Optional[PromptProvider] = None,
        output_writer: Callable[[str], None] = print,
        input_reader: Callable[[str], str] = input,
    ) -> None:
        self._provider = prompt_provider or ConsolePromptProvider(
            output_writer=output_writer,
            input_reader=input_reader,
        )
        self._write = output_writer
        self._yes_to_all = False
        self._no_to_all = False
        self._applied_count = 0
        self._skipped_count = 0
        self._failed_count = 0
        self._applied_ids: list[str] = []
        self._skipped_ids: list[str] = []

    @property
    def applied_count(self) -> int:
        """Number of fixes applied in this session."""
        return self._applied_count

    @property
    def skipped_count(self) -> int:
        """Number of fixes skipped in this session."""
        return self._skipped_count

    async def confirm_and_apply(
        self,
        finding: ReviewIssue,
        index: int,
        total: int,
        apply_func: Callable[[ReviewIssue], asyncio.Future],
    ) -> bool:
        """Show confirmation prompt and apply if user agrees.

        Args:
            finding: The finding to confirm and potentially apply
            index: Current index in batch (1-based)
            total: Total number of findings
            apply_func: Async function to apply the fix

        Returns:
            True if fix was applied, False if skipped or failed
        """
        # Check auto-approval rules
        auto_decision = self._should_apply(finding)
        if auto_decision is True:
            result = await apply_func(finding)
            if result:
                self._applied_count += 1
                self._applied_ids.append(finding.id)
            else:
                self._failed_count += 1
            return result

        if auto_decision is False:
            self._skipped_count += 1
            self._skipped_ids.append(finding.id)
            return False

        # Build and display prompt
        prompt = self._build_prompt(finding, index, total)
        choices = ["y", "n", "a", "q", "e", "h", "s"]

        response = await self._provider.get_confirmation(prompt, choices)

        action = self._parse_response(response)

        if action == ConfirmAction.YES:
            result = await apply_func(finding)
            if result:
                self._applied_count += 1
                self._applied_ids.append(finding.id)
            else:
                self._failed_count += 1
            return result

        elif action == ConfirmAction.YES_TO_ALL:
            self._yes_to_all = True
            result = await apply_func(finding)
            if result:
                self._applied_count += 1
                self._applied_ids.append(finding.id)
            else:
                self._failed_count += 1
            return result

        elif action == ConfirmAction.NO_TO_ALL:
            self._no_to_all = True
            self._skipped_count += 1
            self._skipped_ids.append(finding.id)
            return False

        elif action == ConfirmAction.NO:
            self._skipped_count += 1
            self._skipped_ids.append(finding.id)
            return False

        elif action == ConfirmAction.SKIP:
            self._skipped_count += 1
            self._skipped_ids.append(finding.id)
            return False

        elif action == ConfirmAction.HELP:
            self._show_help()
            return await self.confirm_and_apply(finding, index, total, apply_func)

        elif action == ConfirmAction.EDIT:
            self._skipped_count += 1
            self._skipped_ids.append(finding.id)
            self._write(f"  Skipped for manual edit: {finding.id}")
            return False

        return False

    def _build_prompt(
        self,
        finding: ReviewIssue,
        index: int,
        total: int,
    ) -> ConfirmationPrompt:
        """Build confirmation prompt for a finding."""
        severity = finding.severity
        severity_icon = severity.emoji if hasattr(severity, 'emoji') else self._get_severity_icon(severity)

        old_code = ""
        new_code = ""

        if hasattr(finding, 'evidence') and finding.evidence:
            if hasattr(finding.evidence, 'old_code') and finding.evidence.old_code:
                old_code = self._truncate_code(finding.evidence.old_code)
            if hasattr(finding.evidence, 'new_code') and finding.evidence.new_code:
                new_code = self._truncate_code(finding.evidence.new_code)
        elif hasattr(finding, 'fixes') and finding.fixes:
            for fix in finding.fixes:
                if hasattr(fix, 'old_code') and fix.old_code and not old_code:
                    old_code = self._truncate_code(fix.old_code)
                if hasattr(fix, 'new_code') and fix.new_code and not new_code:
                    new_code = self._truncate_code(fix.new_code)

        risk = "Low"
        if hasattr(finding, 'fixes') and finding.fixes:
            for fix in finding.fixes:
                if hasattr(fix, 'risk'):
                    risk = fix.risk.value if hasattr(fix.risk, 'value') else str(fix.risk)
                    break

        return ConfirmationPrompt(
            index=index,
            total=total,
            severity_icon=severity_icon,
            rule_id=finding.rule_id,
            file_path=finding.file,
            line=finding.line,
            message=finding.message[:80] if finding.message else "",
            old_code_preview=old_code,
            new_code_preview=new_code,
            risk_level=risk,
        )

    def _show_code_diff(
        self,
        old_code: str,
        new_code: str,
        max_lines: int = 5,
    ) -> str:
        """Show code diff with highlighting."""
        old_lines = old_code.split("\n")[:max_lines]
        new_lines = new_code.split("\n")[:max_lines]

        if len(old_code.split("\n")) > max_lines:
            old_lines.append("  ...")
        if len(new_code.split("\n")) > max_lines:
            new_lines.append("  ...")

        lines = ["  --- Current ---"]
        for line in old_lines:
            lines.append(f"  {line}")

        lines.append("")
        lines.append("  +++ Proposed +++")
        for line in new_lines:
            lines.append(f"  +{line}")

        return "\n".join(lines)

    def _show_help(self) -> None:
        """Display help information."""
        help_text = """
  Available commands:
    [y] Yes    - Apply this fix
    [n] No     - Skip this fix
    [a] All    - Yes to all remaining fixes
    [q] Quit   - No to all remaining fixes (quit)
    [e] Edit   - Skip and open for manual edit
    [s] Skip   - Skip this fix only
    [h] Help   - Show this help message
"""
        self._write(help_text)

    async def run_batch(
        self,
        findings: list[ReviewIssue],
        apply_func: Callable[[ReviewIssue], asyncio.Future],
    ) -> BatchResult:
        """Run interactive confirmation for batch of findings.

        Args:
            findings: List of findings to process
            apply_func: Async function to apply each fix

        Returns:
            BatchResult with counts and details
        """
        if not findings:
            return BatchResult()

        self._write(f"\nFound {len(findings)} fix(es). Reviewing...\n")

        for i, finding in enumerate(findings, 1):
            if self._no_to_all:
                self._skipped_count += 1
                self._skipped_ids.append(finding.id)
                continue

            await self.confirm_and_apply(finding, i, len(findings), apply_func)

        return BatchResult(
            applied_count=self._applied_count,
            skipped_count=self._skipped_count,
            failed_count=self._failed_count,
            total_processed=len(findings),
            was_aborted=self._no_to_all,
            applied_fix_ids=self._applied_ids,
            skipped_fix_ids=self._skipped_ids,
        )

    def print_summary(self) -> str:
        """Print final summary of actions.

        Returns:
            Summary string
        """
        lines = [
            "",
            "=" * 60,
            "Summary",
            "=" * 60,
            f"  Applied:  {self._applied_count}",
            f"  Skipped:  {self._skipped_count}",
            f"  Failed:   {self._failed_count}",
            "",
        ]

        if self._applied_ids:
            lines.append("  Applied fixes:")
            for fix_id in self._applied_ids:
                lines.append(f"    - {fix_id}")
            lines.append("")

        if self._skipped_ids:
            lines.append("  Skipped fixes:")
            for fix_id in self._skipped_ids:
                lines.append(f"    - {fix_id}")
            lines.append("")

        lines.append("=" * 60)

        summary = "\n".join(lines)
        self._write(summary)
        return summary

    def _should_apply(self, finding: ReviewIssue) -> Optional[bool]:
        """Check if this finding should be auto-approved.

        Args:
            finding: The finding to check

        Returns:
            True to auto-apply, False to auto-skip, None for user prompt
        """
        if self._yes_to_all:
            return True

        if self._no_to_all:
            return False

        severity = finding.severity
        severity_value = severity.value if hasattr(severity, 'value') else str(severity)
        
        # Critical severity auto-applies
        if severity_value == "critical" or severity == Severity.CRITICAL:
            return True

        return None

    def _parse_response(self, response: str) -> ConfirmAction:
        """Parse user response to ConfirmAction.

        Args:
            response: User input string

        Returns:
            Corresponding ConfirmAction
        """
        response_map = {
            "y": ConfirmAction.YES,
            "n": ConfirmAction.NO,
            "a": ConfirmAction.YES_TO_ALL,
            "q": ConfirmAction.NO_TO_ALL,
            "e": ConfirmAction.EDIT,
            "h": ConfirmAction.HELP,
            "s": ConfirmAction.SKIP,
        }
        return response_map.get(response, ConfirmAction.NO)

    def _get_severity_icon(self, severity) -> str:
        """Get icon for severity level."""
        icons = {
            Severity.CRITICAL: "[X]",
            Severity.HIGH: "[!]",
            Severity.MEDIUM: "[@]",
            Severity.LOW: "[i]",
            Severity.INFO: "[i]",
        }
        return icons.get(severity, "?")

    def _truncate_code(self, code: str, max_length: int = 100) -> str:
        """Truncate code for display.

        Args:
            code: Code string to truncate
            max_length: Maximum length

        Returns:
            Truncated code string
        """
        if not code:
            return "(none)"

        lines = code.split("\n")
        truncated_lines = []
        current_length = 0

        for line in lines:
            if current_length + len(line) > max_length:
                truncated_lines.append(line[:max_length - current_length] + "...")
                break
            truncated_lines.append(line)
            current_length += len(line)

        result = "\n".join(truncated_lines)
        if len(code) > max_length and not result.endswith("..."):
            result = result[:max_length] + "..."
        return result


# ─── Template strings for CLI output ──────────────────────────────────────────

CONFIRM_BATCH_TEMPLATE = """
Found {{total}} fix(es). Apply?

{{fixes_list}}

[A]pply all, [N]o to all, or choose individually: """

FIX_PROMPT_TEMPLATE = """
[{{index}}/{{total}}] {{severity}} {{rule_id}}
  File: {{file_path}}:{{line}}
  Message: {{message}}

  Code:
  ```
  {{old_code}}
  ```

  Fix:
  ```
  {{new_code}}
  ```

  Apply this fix? [y/N/e(dit)/q(uit)]
"""

HELP_TEXT = """
Interactive Fix Confirmation
============================

Options:
  [y] Yes    - Apply this fix
  [n] No     - Skip this fix
  [a] Yes to all - Apply all remaining fixes
  [q] Quit   - Skip all remaining fixes
  [e] Edit   - Skip and note for manual edit
  [s] Skip   - Skip this fix only
  [h] Help   - Show this help

Severity Levels:
  [X] Critical - Auto-applied (security/data loss risk)
  [!] High     - Recommended to fix
  [@] Medium   - Optional improvement
  [i] Low/Info - Suggestion only
"""
