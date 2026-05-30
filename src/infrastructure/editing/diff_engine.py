"""Automated diff engine — generates before/after diffs with line-level precision.

Provides:
- Unified diff generation using difflib
- Colored terminal output using rich (with graceful fallback)
- Multi-file coordinated edits
- EditPlan dataclass for structured fixes
- Context-preserving diffs with configurable context lines
- Diff application (parse + apply unified diffs)

Architecture:
    DiffEngine.generate_diff() → difflib.unified_diff → colored render
    DiffEngine.apply_diff() → parse unified diff → reconstruct content
    EditPlan → structured representation of a single-file change
    generate_multi_file_diff() → combine multiple EditPlans into one diff
"""

from __future__ import annotations

import difflib
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ─── Enums and constants ───────────────────────────────────────────────────────

class Severity(Enum):
    """Severity level for an edit plan item."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    MEDIUM = "medium"


class Confidence(Enum):
    """Confidence level for an edit suggestion."""
    HIGH = "high"      # Definite fix (syntax, type error, etc.)
    MEDIUM = "medium"  # Likely correct (semantic, style)
    LOW = "low"        # Suggestion (best practice, refactor)


# ─── Data structures ───────────────────────────────────────────────────────────

@dataclass
class LineRange:
    """Inclusive line range (1-based, matching editor conventions)."""
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 1:
            self.start = 1
        if self.end < self.start:
            self.end = self.start


@dataclass
class HunkInfo:
    """A single hunk in a diff."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines_removed: list[str] = field(default_factory=list)
    lines_added: list[str] = field(default_factory=list)
    lines_context: list[str] = field(default_factory=list)


@dataclass
class EditPlan:
    """Structured representation of a single file change.

    Attributes:
        file_path: Path to the file to edit (relative or absolute).
        old_lines: Lines being replaced (original state).
        new_lines: Replacement lines.
        line_range: Line range in original file being replaced.
        reason: Human-readable explanation of why this edit is needed.
        severity: How critical this edit is.
        confidence: How confident we are this edit is correct.
        hunks: Parsed diff hunks (populated after generate_diff is called).
        old_label: Label for the original version in diff output.
        new_label: Label for the modified version in diff output.
    """
    file_path: str
    old_lines: list[str]
    new_lines: list[str]
    line_range: LineRange | None = None
    reason: str = ""
    severity: Optional[Severity] = field(default=None)
    confidence: Optional[Confidence] = field(default=None)
    hunks: list[HunkInfo] = field(default_factory=list)
    old_label: str = "original"
    new_label: str = "modified"

    def __post_init__(self) -> None:
        if self.line_range is None:
            self.line_range = LineRange(
                start=1,
                end=len(self.old_lines) if self.old_lines else 1,
            )
        if self.severity is None:
            self.severity = Severity.MEDIUM
        if self.confidence is None:
            self.confidence = Confidence.MEDIUM

    @property
    def is_addition(self) -> bool:
        """True if this is a pure addition (no lines removed)."""
        return not self.old_lines or all(line.strip() == "" for line in self.old_lines)

    @property
    def is_deletion(self) -> bool:
        """True if this is a pure deletion (no lines added)."""
        return not self.new_lines or all(line.strip() == "" for line in self.new_lines)

    def diff_label(self) -> str:
        """Short label for this edit."""
        if self.is_addition:
            return f"+{len(self.new_lines)} lines added"
        if self.is_deletion:
            return f"-{len(self.old_lines)} lines removed"
        return f"~{len(self.old_lines)} → {len(self.new_lines)} lines"

    def with_options(self, options: list[str]) -> list[EditPlan]:
        """Generate multiple EditPlan alternatives from this fix.

        Creates one plan per option plus the default, each with a different new_text.
        """
        plans = []
        for i, opt in enumerate(options):
            plan = EditPlan(
                file_path=self.file_path,
                old_lines=self.old_lines,
                new_lines=opt.split("\n"),
                line_range=self.line_range,
                reason=self.reason,
                severity=self.severity,
                confidence=Confidence.MEDIUM,
                old_label=self.old_label,
                new_label=self.new_label,
            )
            plans.append(plan)
        return plans


# ─── Diff Engine ───────────────────────────────────────────────────────────────

class DiffEngine:
    """Generates line-level diffs with formatting and application support.

    Usage:
        engine = DiffEngine()

        # Generate a unified diff
        diff = engine.generate_diff(old, new, "a.py", "b.py")

        # Render with colors
        colored = engine.render_colored(diff)

        # Generate structured edit plan
        plan = engine.generate_edit_plan("src/foo.py", old, new)

        # Apply a diff
        result = engine.apply_diff(original, diff_str)
    """

    def __init__(
        self,
        context_lines: int = 3,
        tab_size: int = 4,
        show_stats: bool = True,
    ) -> None:
        """
        Args:
            context_lines: Number of context lines around each hunk.
            tab_size: Tab expansion size for alignment.
            show_stats: Include +/-/total stats in diff header.
        """
        self._context = context_lines
        self._tab_size = tab_size
        self._show_stats = show_stats

    # ─── Core diff generation ───────────────────────────────────────────────────

    def generate_diff(
        self,
        old_content: str,
        new_content: str,
        old_label: str = "original",
        new_label: str = "modified",
    ) -> str:
        """Generate a unified diff string from two contents.

        Args:
            old_content: Original file content.
            new_content: Modified file content.
            old_label: Label shown in the --- header line.
            new_label: Label shown in the +++ header line.

        Returns:
            Unified diff string with headers, hunks, and stats.
        """
        old_lines = self._split_lines(old_content)
        new_lines = self._split_lines(new_content)

        udiff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=old_label,
            tofile=new_label,
            n=self._context,
            lineterm="",
        )

        diff_str = "\n".join(udiff)

        if self._show_stats:
            added = sum(1 for l in new_lines if l not in old_lines)
            removed = sum(1 for l in old_lines if l not in new_lines)
            diff_str = self._add_stats_header(diff_str, added, removed, old_label)

        return diff_str

    def generate_diff_from_lines(
        self,
        old_lines: list[str],
        new_lines: list[str],
        old_label: str = "original",
        new_label: str = "modified",
    ) -> str:
        """Generate unified diff from two line lists.

        Args:
            old_lines: Original lines (no trailing newlines).
            new_lines: New lines (no trailing newlines).
            old_label: Label for old version.
            new_label: Label for new version.

        Returns:
            Unified diff string.
        """
        udiff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=old_label,
            tofile=new_label,
            n=self._context,
            lineterm="",
        )
        return "\n".join(udiff)

    def generate_edit_plan(
        self,
        file_path: str,
        old_text: str,
        new_text: str,
        reason: str = "",
        severity: Severity = Severity.MEDIUM,
        confidence: Confidence = Confidence.MEDIUM,
    ) -> EditPlan:
        """Generate a structured EditPlan for an edit.

        Analyzes the old/new content to determine the line range and
        parses the resulting diff into hunks.

        Args:
            file_path: Path to the file.
            old_text: Original text.
            new_text: Replacement text.
            reason: Why this edit should be applied.
            severity: How critical the change is.
            confidence: How confident we are in this edit.

        Returns:
            EditPlan with parsed hunks.
        """
        old_lines = self._split_lines(old_text)
        new_lines = self._split_lines(new_text)

        # Find the changed line range by comparing the texts
        # Look for the first and last difference
        line_range = self._find_changed_range(old_lines, new_lines)

        # Generate the diff and parse hunks
        diff = self.generate_diff(old_text, new_text, file_path, file_path)
        hunks = self._parse_hunks(diff)

        return EditPlan(
            file_path=file_path,
            old_lines=old_lines,
            new_lines=new_lines,
            line_range=line_range,
            reason=reason,
            severity=severity,
            confidence=confidence,
            hunks=hunks,
            old_label=file_path,
            new_label=file_path,
        )

    # ─── Color rendering ───────────────────────────────────────────────────────

    def render_colored(self, diff: str) -> str:
        """Render a diff string with ANSI colors.

        Uses rich for best results, falls back to basic ANSI codes.

        Args:
            diff: Unified diff string.

        Returns:
            Diff string with ANSI color codes embedded.
        """
        # Try rich first
        try:
            from rich.syntax import Syntax
            from rich.text import Text
            from io import StringIO
            from rich.console import Console

            lines = diff.split("\n")
            colored_lines: list[str] = []

            for line in lines:
                if line.startswith("---"):
                    colored_lines.append(self._colorize_line(line, "red"))
                elif line.startswith("+++"):
                    colored_lines.append(self._colorize_line(line, "green"))
                elif line.startswith("@@"):
                    colored_lines.append(self._colorize_line(line, "cyan"))
                elif line.startswith("-"):
                    colored_lines.append(self._colorize_line(line, "red"))
                elif line.startswith("+"):
                    colored_lines.append(self._colorize_line(line, "green"))
                elif line.startswith(" "):
                    colored_lines.append(line)
                else:
                    colored_lines.append(line)

            return "\n".join(colored_lines)
        except ImportError:
            return self._render_ansi_fallback(diff)

    def _colorize_line(self, line: str, color: str) -> str:
        """Colorize a single line with ANSI codes."""
        colors = {
            "red": "\033[91m",
            "green": "\033[92m",
            "yellow": "\033[93m",
            "blue": "\033[94m",
            "cyan": "\033[96m",
            "magenta": "\033[95m",
            "white": "\033[97m",
            "bold_red": "\033[1;31m",
            "bold_green": "\033[1;32m",
        }
        reset = "\033[0m"
        prefix = colors.get(color, "")
        return f"{prefix}{line}{reset}"

    def _render_ansi_fallback(self, diff: str) -> str:
        """Simple ANSI fallback without rich."""
        lines = diff.split("\n")
        result_lines: list[str] = []

        for line in lines:
            if line.startswith("---"):
                result_lines.append(self._colorize_line(line, "red"))
            elif line.startswith("+++"):
                result_lines.append(self._colorize_line(line, "green"))
            elif line.startswith("@@"):
                result_lines.append(self._colorize_line(line, "cyan"))
            elif line.startswith("-"):
                result_lines.append(self._colorize_line(line, "red"))
            elif line.startswith("+"):
                result_lines.append(self._colorize_line(line, "green"))
            else:
                result_lines.append(line)

        return "\n".join(result_lines)

    def render_colored_rich(self, diff: str) -> str:
        """Render diff using rich for fancy terminal output.

        Returns:
            String with rich markup (use with rich.print()).
        """
        try:
            from rich.console import Console
            from rich.syntax import Syntax
            from io import StringIO

            buf = StringIO()
            console = Console(file=buf, force_terminal=True, width=120)
            syntax = Syntax(diff, "diff", theme="monokai", line_numbers=False)
            console.print(syntax)
            return buf.getvalue()
        except ImportError:
            return diff

    # ─── Diff application ───────────────────────────────────────────────────────

    def apply_diff(self, original: str, diff: str) -> str:
        """Apply a unified diff string to original content.

        Parses the diff, validates it can be applied cleanly, and
        reconstructs the modified content.

        Args:
            original: Original content string.
            diff: Unified diff string.

        Returns:
            Modified content string.

        Raises:
            ValueError: If the diff cannot be applied cleanly.
        """
        lines = self._split_lines(original)
        hunks = self._parse_hunks(diff)

        if not hunks:
            # No changes — return original
            return original

        result_lines: list[str] = []
        src_idx = 0  # Current position in original lines (0-based)

        for hunk in hunks:
            # 1. Copy unchanged lines before this hunk
            hunk_start = hunk.old_start - 1  # Convert to 0-based
            if hunk_start > src_idx:
                result_lines.extend(lines[src_idx:hunk_start])
                src_idx = hunk_start

            # 2. Apply the hunk changes
            old_section = hunk.lines_removed
            new_section = hunk.lines_added

            # Verify the old section matches
            actual_old = lines[src_idx:src_idx + len(old_section)]
            if self._normalize_lines(actual_old) != self._normalize_lines(old_section):
                # Try to find a matching position nearby (fuzzy apply)
                offset = self._find_matching_offset(lines, old_section, src_idx, hunk)
                if offset is not None:
                    # Copy lines between old position and found position
                    if offset > src_idx:
                        result_lines.extend(lines[src_idx:offset])
                        src_idx = offset
                else:
                    raise ValueError(
                        f"Hunk does not match at line {hunk.old_start}: "
                        f"expected {old_section[:3]}..., got {actual_old[:3]}..."
                    )

            # 3. Add the new lines
            result_lines.extend(new_section)
            src_idx += len(old_section)

        # Copy any remaining lines after the last hunk
        if src_idx < len(lines):
            result_lines.extend(lines[src_idx:])

        return "\n".join(result_lines)

    def _find_matching_offset(
        self,
        lines: list[str],
        pattern: list[str],
        start: int,
        hunk: HunkInfo,
    ) -> int | None:
        """Find where a hunk's old_section appears in lines (fuzzy matching).

        Searches within a window around the expected position.
        """
        window = 20  # Search within 20 lines of expected position
        search_start = max(0, start - window)
        search_end = min(len(lines), start + window + hunk.old_count + window)

        for i in range(search_start, search_end):
            if self._normalize_lines(lines[i:i + len(pattern)]) == self._normalize_lines(pattern):
                return i

        return None

    # ─── Multi-file diff ───────────────────────────────────────────────────────

    def generate_multi_file_diff(self, plans: list[EditPlan]) -> str:
        """Generate a combined diff for multiple file changes.

        Args:
            plans: List of EditPlan objects, one per file.

        Returns:
            Combined unified diff string with all changes.
        """
        if not plans:
            return ""

        diff_parts: list[str] = []

        for plan in plans:
            diff = self.generate_diff_from_lines(
                plan.old_lines,
                plan.new_lines,
                old_label=plan.old_label,
                new_label=plan.new_label,
            )
            if diff:
                diff_parts.append(diff)

        return "\n".join(diff_parts)

    def generate_multi_file_diff_from_text(
        self,
        changes: dict[str, tuple[str, str]],
    ) -> str:
        """Generate diff for multiple file changes from text pairs.

        Args:
            changes: Dict mapping file_path → (old_text, new_text).

        Returns:
            Combined unified diff string.
        """
        plans = [
            self.generate_edit_plan(path, old, new)
            for path, (old, new) in changes.items()
        ]
        return self.generate_multi_file_diff(plans)

    # ─── Hunk parsing ──────────────────────────────────────────────────────────

    def _parse_hunks(self, diff: str) -> list[HunkInfo]:
        """Parse unified diff into structured HunkInfo objects.

        Extracts @@ -start,count +start,count @@ headers and
        the removed/added/context lines between them.
        """
        hunks: list[HunkInfo] = []
        lines = diff.split("\n")

        hunk_pattern = re.compile(
            r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)"
        )

        current_hunk: HunkInfo | None = None
        current_context_start = -1

        for raw_line in lines:
            hunk_match = hunk_pattern.match(raw_line)
            if hunk_match:
                # Save previous hunk
                if current_hunk is not None:
                    hunks.append(current_hunk)

                old_start = int(hunk_match.group(1))
                old_count = int(hunk_match.group(2) or 1)
                new_start = int(hunk_match.group(3))
                new_count = int(hunk_match.group(4) or 1)

                current_hunk = HunkInfo(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    lines_removed=[],
                    lines_added=[],
                    lines_context=[],
                )
                current_context_start = len(hunks)

                # Handle inline context after @@
                remainder = hunk_match.group(5)
                if remainder and remainder.strip():
                    line = remainder.strip()
                    current_hunk.lines_context.append(line)

                continue

            if current_hunk is None:
                continue

            if raw_line.startswith("-"):
                current_hunk.lines_removed.append(raw_line[1:])
            elif raw_line.startswith("+"):
                current_hunk.lines_added.append(raw_line[1:])
            elif raw_line.startswith(" ") or raw_line == "":
                stripped = raw_line[1:] if raw_line.startswith(" ") else raw_line
                current_hunk.lines_context.append(stripped)

        if current_hunk is not None:
            hunks.append(current_hunk)

        return hunks

    # ─── Line utilities ────────────────────────────────────────────────────────

    @staticmethod
    def _split_lines(content: str) -> list[str]:
        """Split content into lines, removing trailing newlines."""
        if not content:
            return []
        return content.splitlines(keepends=False)

    @staticmethod
    def _normalize_lines(lines: list[str]) -> list[str]:
        """Strip trailing whitespace for comparison purposes."""
        return [l.rstrip() for l in lines]

    @staticmethod
    def _find_changed_range(
        old_lines: list[str],
        new_lines: list[str],
    ) -> LineRange:
        """Find the range of changed lines between two line lists."""
        sm = difflib.SequenceMatcher(None, old_lines, new_lines)
        opcodes = list(sm.get_opcodes())

        min_line = len(old_lines)
        max_line = 0

        for tag, i1, i2, j1, j2 in opcodes:
            if tag in ("replace", "delete"):
                min_line = min(min_line, i1 + 1)  # 1-based
                max_line = max(max_line, i2)
            elif tag == "equal":
                # Extend range to include adjacent context
                if i2 > min_line and i1 <= max_line + 5:
                    pass  # Overlapping context

        if max_line == 0:
            max_line = min_line

        return LineRange(start=min_line, end=max_line)

    @staticmethod
    def _add_stats_header(
        diff: str,
        added: int,
        removed: int,
        file_label: str,
    ) -> str:
        """Add a statistics header to the diff output."""
        stats = f"# {file_label}: +{added} -{removed} lines\n"
        if diff:
            return stats + diff
        return ""

    # ─── Validation ────────────────────────────────────────────────────────────

    def validate_diff(self, original: str, diff: str) -> dict[str, Any]:
        """Validate that a diff can be cleanly applied.

        Args:
            original: Original content.
            diff: Unified diff string.

        Returns:
            Dict with 'valid', 'error' (if invalid), and 'stats'.
        """
        try:
            hunks = self._parse_hunks(diff)
            lines = self._split_lines(original)

            for hunk in hunks:
                start = hunk.old_start - 1
                end = start + hunk.old_count
                if start < 0 or end > len(lines):
                    return {
                        "valid": False,
                        "error": f"Hunk out of bounds: {hunk.old_start}-{end}",
                        "stats": {},
                    }

            # Try to apply to verify
            result = self.apply_diff(original, diff)
            return {
                "valid": True,
                "error": "",
                "stats": {
                    "hunks": len(hunks),
                    "lines_added": sum(len(h.lines_added) for h in hunks),
                    "lines_removed": sum(len(h.lines_removed) for h in hunks),
                    "result_length": len(result),
                },
            }
        except Exception as e:
            return {
                "valid": False,
                "error": str(e),
                "stats": {},
            }

    # ─── Convenience formatters ───────────────────────────────────────────────

    def format_summary(self, plan: EditPlan) -> str:
        """Format a human-readable summary of an edit plan."""
        parts = [
            f"File: {plan.file_path}",
            f"Change: {plan.diff_label()}",
            f"Severity: {plan.severity.value}",
            f"Confidence: {plan.confidence.value}",
        ]
        if plan.reason:
            parts.append(f"Reason: {plan.reason}")
        if plan.line_range:
            parts.append(f"Lines: {plan.line_range.start}-{plan.line_range.end}")
        return " | ".join(parts)

    def format_stats(self, diff: str) -> dict[str, int]:
        """Extract statistics from a diff string."""
        added = diff.count("\n+") - (1 if diff.startswith("+") else 0)
        removed = diff.count("\n-") - (1 if diff.startswith("-") else 0)
        hunks = diff.count("@@")
        return {
            "added": max(0, added),
            "removed": max(0, removed),
            "hunks": hunks,
        }
