"""Interactive fix command with user confirmation.

This module provides an interactive session for applying code fixes
with user confirmation before each fix is applied.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Protocol

from src.core.fix_engine.models import Fix, FixBatch, FixResult, FixStatus

logger = logging.getLogger(__name__)


class FixResponse(Enum):
    """User response to a fix confirmation prompt."""
    YES = "y"
    NO = "n"
    YES_TO_ALL = "a"
    NO_TO_ALL = "q"
    EDIT = "e"
    SKIP = "s"
    HELP = "h"


class FixDecision(Enum):
    """Internal decision for fix handling."""
    APPLY = "apply"
    SKIP = "skip"
    ABORT = "abort"
    EDIT = "edit"


@dataclass
class InteractiveFixSession:
    """Session for interactive fix application.

    Attributes:
        workspace_root: Root directory of the workspace
        fixes: List of fixes to potentially apply
        current_index: Current position in the fixes list
        auto_approved: Set of rule IDs to auto-approve
        skip_remaining: If True, skip all remaining fixes
        yes_to_all: If True, auto-approve all remaining fixes
        applied_fixes: List of fixes that were applied
        skipped_fixes: List of fixes that were skipped
    """
    workspace_root: str
    fixes: list[Fix]
    current_index: int = 0
    auto_approved: set[str] = field(default_factory=set)
    skip_remaining: bool = False
    yes_to_all: bool = False
    applied_fixes: list[Fix] = field(default_factory=list)
    skipped_fixes: list[Fix] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.auto_approved is None:
            self.auto_approved = set()

    @property
    def total_fixes(self) -> int:
        """Total number of fixes in session."""
        return len(self.fixes)

    @property
    def remaining_fixes(self) -> int:
        """Number of fixes remaining."""
        return self.total_fixes - self.current_index

    @property
    def current_fix(self) -> Optional[Fix]:
        """Get the current fix to process."""
        if 0 <= self.current_index < len(self.fixes):
            return self.fixes[self.current_index]
        return None

    def mark_applied(self, fix: Fix) -> None:
        """Mark a fix as applied."""
        fix.mark_applied()
        self.applied_fixes.append(fix)

    def mark_skipped(self, fix: Fix) -> None:
        """Mark a fix as skipped."""
        fix.status = FixStatus.SKIPPED
        self.skipped_fixes.append(fix)

    def advance(self) -> None:
        """Move to the next fix."""
        self.current_index += 1


@dataclass
class InteractiveFixResult:
    """Result of an interactive fix session.

    Attributes:
        session: The session that was run
        applied_count: Number of fixes applied
        skipped_count: Number of fixes skipped
        total_processed: Total fixes processed
    """
    session: InteractiveFixSession
    applied_count: int = 0
    skipped_count: int = 0
    total_processed: int = 0

    @property
    def was_aborted(self) -> bool:
        """Check if session was aborted by user."""
        return self.session.skip_remaining

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "applied_count": self.applied_count,
            "skipped_count": self.skipped_count,
            "total_processed": self.total_processed,
            "was_aborted": self.was_aborted,
            "applied_fixes": [
                {
                    "id": f.id,
                    "file": f.file_path,
                    "line": f.line_start,
                    "rule_id": f.rule_id,
                }
                for f in self.session.applied_fixes
            ],
            "skipped_fixes": [
                {
                    "id": f.id,
                    "file": f.file_path,
                    "line": f.line_start,
                    "rule_id": f.rule_id,
                }
                for f in self.session.skipped_fixes
            ],
        }


class UserPromptProvider(Protocol):
    """Protocol for user prompt providers."""

    async def prompt(
        self,
        message: str,
        choices: list[str],
        default: str,
    ) -> str:
        """Prompt user with a message and return choice."""
        ...


class ConsolePromptProvider:
    """Console-based prompt provider using asyncio."""

    async def prompt(
        self,
        message: str,
        choices: list[str],
        default: str,
    ) -> str:
        """Prompt user with a message and return choice."""
        print(f"\n{message}")
        print(f"Choices: {', '.join(choices)}")
        print(f"Default: {default}")

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, input, f"Enter choice [{default}]: ")

        response = response.strip().lower()
        if not response:
            return default

        for choice in choices:
            if response == choice.lower() or response == choice:
                return choice

        return default


async def run_interactive_fix(
    fixes: list[Fix],
    workspace_root: str,
    prompt_provider: Optional[UserPromptProvider] = None,
    auto_approved_rules: Optional[set[str]] = None,
) -> InteractiveFixResult:
    """Run interactive fix session.

    Args:
        fixes: List of fixes to potentially apply
        workspace_root: Root directory of the workspace
        prompt_provider: Provider for user prompts (uses console if None)
        auto_approved_rules: Set of rule IDs to auto-approve without prompting

    Returns:
        InteractiveFixResult with session results
    """
    provider = prompt_provider or ConsolePromptProvider()

    session = InteractiveFixSession(
        workspace_root=workspace_root,
        fixes=fixes,
    )

    if auto_approved_rules:
        session.auto_approved = auto_approved_rules

    applied_count = 0
    skipped_count = 0

    while session.current_fix is not None:
        fix = session.current_fix

        if session.skip_remaining:
            session.mark_skipped(fix)
            skipped_count += 1
            session.advance()
            continue

        if should_auto_apply(fix.rule_id, session):
            session.mark_applied(fix)
            applied_count += 1
            session.advance()
            continue

        decision = await prompt_user(fix, provider)

        if decision == FixDecision.APPLY:
            session.mark_applied(fix)
            applied_count += 1
            if session.yes_to_all:
                session.auto_approved.add(fix.rule_id)

        elif decision == FixDecision.SKIP:
            session.mark_skipped(fix)
            skipped_count += 1

        elif decision == FixDecision.ABORT:
            session.skip_remaining = True
            while session.current_fix is not None:
                session.mark_skipped(session.current_fix)
                skipped_count += 1
                session.advance()
            break

        elif decision == FixDecision.EDIT:
            session.mark_skipped(fix)
            skipped_count += 1

        session.advance()

    return InteractiveFixResult(
        session=session,
        applied_count=applied_count,
        skipped_count=skipped_count,
        total_processed=applied_count + skipped_count,
    )


async def prompt_user(fix: Fix, provider: UserPromptProvider) -> FixDecision:
    """Prompt user for fix decision.

    Args:
        fix: The fix to prompt about
        provider: Prompt provider

    Returns:
        FixDecision based on user response
    """
    severity_icons = {
        "error": "[X]",
        "warning": "[!]",
        "info": "[i]",
    }
    icon = severity_icons.get(fix.severity.value, "?")

    message = f"""
{icon} Fix: {fix.rule_id}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
File: {fix.file_path}:{fix.line_start}
Reason: {fix.reason}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""".strip()

    choices = ["y", "n", "a", "q", "e", "s", "h"]

    response = await provider.prompt(
        message=message,
        choices=choices,
        default="n",
    )

    if response.lower() == "y":
        return FixDecision.APPLY
    elif response.lower() == "a":
        return FixDecision.APPLY
    elif response.lower() == "q":
        return FixDecision.ABORT
    elif response.lower() == "e":
        return FixDecision.EDIT
    elif response.lower() == "s":
        return FixDecision.SKIP
    elif response.lower() == "h":
        return FixDecision.SKIP
    else:
        return FixDecision.SKIP


def should_auto_apply(rule_id: str, session: InteractiveFixSession) -> bool:
    """Check if rule should be auto-applied based on session state.

    Args:
        rule_id: The rule ID to check
        session: The interactive session

    Returns:
        True if the fix should be auto-applied
    """
    if session.yes_to_all:
        return True

    if rule_id in session.auto_approved:
        return True

    return False


def format_fix_preview(fix: Fix, max_context_lines: int = 5) -> str:
    """Format a fix for preview display.

    Args:
        fix: The fix to format
        max_context_lines: Maximum lines of context to show

    Returns:
        Formatted string for preview
    """
    lines = [
        f"## Fix: {fix.rule_id}",
        f"",
        f"**File:** `{fix.file_path}:{fix.line_start}`",
        f"**Severity:** {fix.severity.value}",
        f"**Reason:** {fix.reason}",
        f"",
        f"**Current Code:**",
        f"```",
        fix.old_text[:200] if fix.old_text else "(auto-generated)",
        f"```",
        f"",
        f"**Proposed Fix:**",
        f"```",
        fix.new_text[:200] if fix.new_text else "(no change)",
        f"```",
    ]

    return "\n".join(lines)


async def apply_interactive_fixes(
    fixes: list[Fix],
    workspace_root: str,
    apply_tool,
    prompt_provider: Optional[UserPromptProvider] = None,
) -> tuple[list[FixResult], InteractiveFixResult]:
    """Apply fixes interactively with user confirmation.

    This combines the interactive session with actual fix application.

    Args:
        fixes: List of fixes to potentially apply
        workspace_root: Root directory of the workspace
        apply_tool: ApplyFixTool instance to apply actual fixes
        prompt_provider: Provider for user prompts

    Returns:
        Tuple of (list of FixResults, InteractiveFixResult)
    """
    result = await run_interactive_fix(
        fixes=fixes,
        workspace_root=workspace_root,
        prompt_provider=prompt_provider,
    )

    results: list[FixResult] = []

    for fix in result.session.applied_fixes:
        fix_result = apply_tool.apply_fix(fix)
        results.append(fix_result)

        if not fix_result.success:
            logger.warning(
                "Failed to apply fix %s: %s",
                fix.id,
                fix_result.error,
            )

    return results, result
