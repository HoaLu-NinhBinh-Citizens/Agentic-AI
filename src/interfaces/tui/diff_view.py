"""Diff View Component — displays file changes with syntax highlighting.

This module provides:
- Unified diff parser
- Side-by-side diff view
- Inline diff annotations
- Fix application preview

Usage:
    diff_view = DiffViewRenderer()
    diff_panel = diff_view.render_diff(old_content, new_content, file_path)
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class DiffType(Enum):
    """Type of diff line."""
    CONTEXT = "context"
    ADDED = "added"
    REMOVED = "removed"
    HEADER = "header"


@dataclass
class DiffLine:
    """A single line in a diff."""
    line_type: DiffType
    content: str
    old_line_num: Optional[int] = None
    new_line_num: Optional[int] = None


@dataclass
class DiffHunk:
    """A hunk (section) of changes in a diff."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[DiffLine]


@dataclass
class FileDiff:
    """Complete diff for a file."""
    old_path: str
    new_path: str
    hunks: list[DiffHunk]
    stats: dict[str, int]


class DiffViewRenderer:
    """Renders diff views for the TUI."""

    ADDED_COLOR = "#a6e3a1"      # Green
    REMOVED_COLOR = "#f38ba8"   # Red
    CONTEXT_COLOR = "#6c7086"   # Gray
    HEADER_COLOR = "#89b4fa"    # Blue

    def __init__(self, context_lines: int = 3):
        """Initialize diff renderer.

        Args:
            context_lines: Number of context lines around changes
        """
        self.context_lines = context_lines

    def compute_diff(
        self,
        old_content: str,
        new_content: str,
        old_path: str = "old",
        new_path: str = "new",
    ) -> FileDiff:
        """Compute unified diff between two contents.

        Args:
            old_content: Original content
            new_content: New content
            old_path: Path for old file
            new_path: Path for new file

        Returns:
            FileDiff with hunks and statistics
        """
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        differ = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=old_path,
            tofile=new_path,
            n=self.context_lines,
        )

        hunks = self._parse_unified_diff(list(differ))

        added = sum(1 for h in hunks for l in h.lines if l.line_type == DiffType.ADDED)
        removed = sum(1 for h in hunks for l in h.lines if l.line_type == DiffType.REMOVED)

        return FileDiff(
            old_path=old_path,
            new_path=new_path,
            hunks=hunks,
            stats={"added": added, "removed": removed, "hunks": len(hunks)},
        )

    def _parse_unified_diff(self, lines: list[str]) -> list[DiffHunk]:
        """Parse unified diff output into hunks."""
        hunks = []
        current_hunk = None
        current_lines = []

        old_line = 0
        new_line = 0
        old_start = 0
        old_count = 0
        new_start = 0
        new_count = 0

        for raw_line in lines:
            line = raw_line.rstrip("\n\r")

            if line.startswith("@@"):
                if current_hunk:
                    current_hunk.lines = current_lines
                    hunks.append(current_hunk)
                    current_lines = []

                match = self._parse_hunk_header(line)
                if match:
                    old_start, old_count, new_start, new_count = match
                    old_line = old_start
                    new_line = new_start

                current_hunk = DiffHunk(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    lines=[],
                )

            elif current_hunk:
                if line.startswith("+") and not line.startswith("+++"):
                    current_lines.append(DiffLine(
                        DiffType.ADDED,
                        line[1:],
                        old_line_num=None,
                        new_line_num=new_line,
                    ))
                    new_line += 1

                elif line.startswith("-") and not line.startswith("---"):
                    current_lines.append(DiffLine(
                        DiffType.REMOVED,
                        line[1:],
                        old_line_num=old_line,
                        new_line_num=None,
                    ))
                    old_line += 1

                elif line.startswith(" ") or line == "":
                    current_lines.append(DiffLine(
                        DiffType.CONTEXT,
                        line[1:] if line.startswith(" ") else line,
                        old_line_num=old_line,
                        new_line_num=new_line,
                    ))
                    old_line += 1
                    new_line += 1

        if current_hunk:
            current_hunk.lines = current_lines
            hunks.append(current_hunk)

        return hunks

    def _parse_hunk_header(self, line: str) -> Optional[tuple[int, int, int, int]]:
        """Parse @@ header into (old_start, old_count, new_start, new_count)."""
        import re
        match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if match:
            old_start = int(match.group(1))
            old_count = int(match.group(2)) if match.group(2) else 1
            new_start = int(match.group(3))
            new_count = int(match.group(4)) if match.group(4) else 1
            return (old_start, old_count, new_start, new_count)
        return None

    def render_unified(
        self,
        diff: FileDiff,
        max_lines: int = 100,
    ) -> list[str]:
        """Render diff in unified format for display.

        Args:
            diff: The file diff
            max_lines: Maximum lines to display

        Returns:
            List of formatted lines
        """
        lines = []

        for hunk in diff.hunks:
            lines.append(f"{self.HEADER_COLOR}@@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@{self.CONTEXT_COLOR}")

            for diff_line in hunk.lines[:max_lines]:
                if diff_line.line_type == DiffType.ADDED:
                    prefix = f"{self.ADDED_COLOR}+{self.ADDED_COLOR}"
                    lines.append(f"{prefix} {diff_line.content}")

                elif diff_line.line_type == DiffType.REMOVED:
                    prefix = f"{self.REMOVED_COLOR}-{self.REMOVED_COLOR}"
                    lines.append(f"{prefix} {diff_line.content}")

                else:
                    prefix = f"{self.CONTEXT_COLOR} {self.CONTEXT_COLOR}"
                    lines.append(f"{prefix} {diff_line.content}")

        return lines

    def render_stats(self, diff: FileDiff) -> str:
        """Render diff statistics.

        Args:
            diff: The file diff

        Returns:
            Formatted statistics string
        """
        added = diff.stats.get("added", 0)
        removed = diff.stats.get("removed", 0)

        parts = []
        if added > 0:
            parts.append(f"{self.ADDED_COLOR}+{added}{self.CONTEXT_COLOR}")
        if removed > 0:
            parts.append(f"{self.REMOVED_COLOR}-{removed}{self.CONTEXT_COLOR}")

        if not parts:
            return "No changes"

        return f"Changes: {' '.join(parts)}"


class FixPreviewRenderer:
    """Renders fix application previews."""

    def __init__(self):
        self.diff_renderer = DiffViewRenderer()

    def create_preview(
        self,
        original_content: str,
        fixed_content: str,
        file_path: Path,
    ) -> dict:
        """Create a fix preview.

        Args:
            original_content: Original file content
            fixed_content: Fixed file content
            file_path: Path to the file

        Returns:
            Dict with preview data
        """
        diff = self.diff_renderer.compute_diff(
            original_content,
            fixed_content,
            old_path=str(file_path),
            new_path=f"{file_path} (fixed)",
        )

        return {
            "diff": diff,
            "stats": diff.stats,
            "preview_lines": self.diff_renderer.render_unified(diff),
            "can_apply": diff.stats.get("added", 0) > 0 or diff.stats.get("removed", 0) > 0,
        }

    def format_fix_summary(self, preview: dict) -> str:
        """Format a human-readable fix summary.

        Args:
            preview: Preview dict from create_preview

        Returns:
            Formatted summary string
        """
        stats = preview.get("stats", {})
        added = stats.get("added", 0)
        removed = stats.get("removed", 0)
        hunks = stats.get("hunks", 0)

        summary = f"Fix summary: {hunks} hunk(s), "
        summary += f"{added} line(s) added, {removed} line(s) removed"

        return summary
