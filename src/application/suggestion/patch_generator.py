"""Patch Generator - Generate unified diffs and code patches.

This module provides comprehensive patch generation capabilities:
- Unified diff generation
- Side-by-side diff visualization
- Line-level change tracking
- Multiple output formats
- Batch patch generation

Usage:
    generator = PatchGenerator()
    patch = generator.generate(old_code, new_code, file_path)
    print(patch)
"""

from __future__ import annotations

import difflib
import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ─── Enums ───────────────────────────────────────────────────────────────────────


class DiffFormat(Enum):
    """Output format for diffs."""
    UNIFIED = "unified"
    SIDE_BY_SIDE = "side_by_side"
    CONTEXT = "context"
    HTML = "html"
    JSON = "json"


class ChangeType(Enum):
    """Type of change in a patch."""
    ADDED = "added"
    DELETED = "deleted"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


# ─── Data Classes ───────────────────────────────────────────────────────────────


@dataclass
class LineChange:
    """Represents a single line change.

    Attributes:
        line_number: Line number in the output (-1 for deleted, 0 for added)
        change_type: Type of change
        content: Line content
        old_line: Original line number (for modified lines)
        new_line: New line number (for modified lines)
    """
    line_number: int
    change_type: ChangeType
    content: str
    old_line: Optional[int] = None
    new_line: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "line_number": self.line_number,
            "change_type": self.change_type.value,
            "content": self.content,
            "old_line": self.old_line,
            "new_line": self.new_line,
        }


@dataclass
class Hunk:
    """A contiguous block of changes.

    Attributes:
        old_start: Starting line in original file
        old_count: Number of lines in original
        new_start: Starting line in new file
        new_count: Number of lines in new
        changes: List of changes in this hunk
        header: Optional hunk header
    """
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    changes: list[LineChange] = field(default_factory=list)
    header: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "old_start": self.old_start,
            "old_count": self.old_count,
            "new_start": self.new_start,
            "new_count": self.new_count,
            "changes": [c.to_dict() for c in self.changes],
            "header": self.header,
        }


@dataclass
class Patch:
    """Complete patch for a file.

    Attributes:
        file_path: Path to the file
        hunks: List of change hunks
        old_hash: MD5 hash of original content
        new_hash: MD5 hash of new content
        stats: Patch statistics
        format: Output format used
    """
    file_path: str
    hunks: list[Hunk] = field(default_factory=list)
    old_hash: str = ""
    new_hash: str = ""
    stats: dict[str, int] = field(default_factory=dict)
    format: DiffFormat = DiffFormat.UNIFIED

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "file_path": self.file_path,
            "hunks": [h.to_dict() for h in self.hunks],
            "old_hash": self.old_hash,
            "new_hash": self.new_hash,
            "stats": self.stats,
            "format": self.format.value,
        }

    @property
    def has_changes(self) -> bool:
        """Check if patch contains any changes."""
        return len(self.hunks) > 0


@dataclass
class PatchOptions:
    """Options for patch generation.

    Attributes:
        format: Output format
        context_lines: Lines of context before/after changes
        ignore_whitespace: Ignore whitespace changes
        ignore_case: Ignore case changes
        show_line_numbers: Show line numbers
        show_stats: Include statistics
        colorize: Use ANSI colors
        language_hint: Programming language for syntax highlighting
    """
    format: DiffFormat = DiffFormat.UNIFIED
    context_lines: int = 3
    ignore_whitespace: bool = False
    ignore_case: bool = False
    show_line_numbers: bool = True
    show_stats: bool = True
    colorize: bool = False
    language_hint: str = "python"


# ─── Patch Generator ───────────────────────────────────────────────────────────


class PatchGenerator:
    """Generate unified diffs and code patches.

    Provides multiple output formats and customizable options
    for visualizing and applying code changes.

    Usage:
        generator = PatchGenerator()
        patch = generator.generate(old_code, new_code, "file.py")
        print(patch.to_unified())
    """

    # ANSI color codes for terminal output
    COLORS = {
        "reset": "\033[0m",
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "bold": "\033[1m",
    }

    def __init__(self, options: Optional[PatchOptions] = None) -> None:
        """Initialize patch generator.

        Args:
            options: Generation options
        """
        self.options = options or PatchOptions()

    def generate(
        self,
        old_code: str,
        new_code: str,
        file_path: str = "file.py",
        options: Optional[PatchOptions] = None,
    ) -> Patch:
        """Generate a patch from old to new code.

        Args:
            old_code: Original code
            new_code: New code
            file_path: File path for the patch
            options: Optional override for generation options

        Returns:
            Patch object with hunks and metadata
        """
        opts = options or self.options

        # Preprocess if needed
        if opts.ignore_whitespace:
            old_code = self._remove_whitespace(old_code)
            new_code = self._remove_whitespace(new_code)
        if opts.ignore_case:
            old_code = old_code.lower()
            new_code = new_code.lower()

        # Generate unified diff
        diff_lines = self._generate_diff_lines(old_code, new_code, file_path, opts)

        # Parse into hunks
        hunks = self._parse_hunks(diff_lines, old_code, new_code)

        # Calculate stats
        stats = self._calculate_stats(hunks, old_code, new_code)

        patch = Patch(
            file_path=file_path,
            hunks=hunks,
            old_hash=self._compute_hash(old_code),
            new_hash=self._compute_hash(new_code),
            stats=stats,
            format=opts.format,
        )

        return patch

    def generate_from_strings(
        self,
        old_str: str,
        new_str: str,
        file_path: str = "file.py",
    ) -> str:
        """Generate a unified diff string directly.

        Args:
            old_str: Original string
            new_str: New string
            file_path: File path for header

        Returns:
            Unified diff string
        """
        diff = difflib.unified_diff(
            old_str.splitlines(keepends=True),
            new_str.splitlines(keepends=True),
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm="\n",
            n=self.options.context_lines,
        )
        return "".join(diff)

    def generate_side_by_side(
        self,
        old_code: str,
        new_code: str,
        width: int = 80,
    ) -> str:
        """Generate side-by-side diff view.

        Args:
            old_code: Original code
            new_code: New code
            width: Terminal width for display

        Returns:
            Side-by-side formatted string
        """
        old_lines = old_code.splitlines()
        new_lines = new_code.splitlines()

        # Use difflib's SideBySide formatter
        diff = difflib.diff_bytes(
            difflib.IS_LINE_JUNK,
            old_code.encode().splitlines(keepends=True),
            new_code.encode().splitlines(keepends=True),
        )

        half_width = (width - 3) // 2
        lines = []
        separator = "=" * width

        for group in difflib.SequenceMatcher(None, old_lines, new_lines).get_grouped_opcodes(
            self.options.context_lines
        ):
            lines.append(separator)

            for tag, i1, i2, j1, j2 in group:
                if tag == "equal":
                    for line in old_lines[i1:i2]:
                        lines.append(self._format_side_by_side_line(line, line, half_width))
                elif tag == "delete":
                    for line in old_lines[i1:i2]:
                        lines.append(
                            self._format_side_by_side_line(
                                line, "", half_width, is_old=True
                            )
                        )
                elif tag == "insert":
                    for line in new_lines[j1:j2]:
                        lines.append(
                            self._format_side_by_side_line(
                                "", line, half_width, is_new=True
                            )
                        )
                elif tag == "replace":
                    for old_line, new_line in zip(old_lines[i1:i2], new_lines[j1:j2]):
                        lines.append(
                            self._format_side_by_side_line(
                                old_line, new_line, half_width, is_modified=True
                            )
                        )

        return "\n".join(lines)

    def generate_json(
        self,
        old_code: str,
        new_code: str,
        file_path: str = "file.py",
    ) -> str:
        """Generate JSON-formatted diff.

        Args:
            old_code: Original code
            new_code: New code
            file_path: File path

        Returns:
            JSON string
        """
        import json

        patch = self.generate(old_code, new_code, file_path)
        return json.dumps(patch.to_dict(), indent=2)

    def generate_html(
        self,
        old_code: str,
        new_code: str,
        file_path: str = "file.py",
    ) -> str:
        """Generate HTML-formatted diff.

        Args:
            old_code: Original code
            new_code: New code
            file_path: File path

        Returns:
            HTML string
        """
        old_lines = old_code.splitlines()
        new_lines = new_code.splitlines()

        matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
        opcodes = matcher.get_opcodes()

        html_parts = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            '<style>',
            ".added { background-color: #d4edda; }",
            ".deleted { background-color: #f8d7da; }",
            ".modified { background-color: #fff3cd; }",
            "pre { font-family: monospace; }",
            ".line { white-space: pre; }",
            ".line-num { color: #666; width: 40px; display: inline-block; }",
            ".line-content { flex: 1; }",
            ".line-row { display: flex; }",
            "</style>",
            "</head>",
            "<body>",
            f"<h3>{file_path}</h3>",
            "<pre>",
        ]

        for tag, i1, i2, j1, j2 in opcodes:
            if tag == "equal":
                for i, line in enumerate(old_lines[i1:i2], i1 + 1):
                    html_parts.append(
                        f'<div class="line-row"><span class="line-num">{i}</span>'
                        f'<span class="line-content">{self._escape_html(line)}</span></div>'
                    )
            elif tag == "delete":
                for i, line in enumerate(old_lines[i1:i2], i1 + 1):
                    html_parts.append(
                        f'<div class="line-row deleted"><span class="line-num">-{i}</span>'
                        f'<span class="line-content">- {self._escape_html(line)}</span></div>'
                    )
            elif tag == "insert":
                for j, line in enumerate(new_lines[j1:j2], j1 + 1):
                    html_parts.append(
                        f'<div class="line-row added"><span class="line-num">+{j}</span>'
                        f'<span class="line-content">+ {self._escape_html(line)}</span></div>'
                    )
            elif tag == "replace":
                for i, line in enumerate(old_lines[i1:i2], i1 + 1):
                    html_parts.append(
                        f'<div class="line-row deleted"><span class="line-num">-{i}</span>'
                        f'<span class="line-content">- {self._escape_html(line)}</span></div>'
                    )
                for j, line in enumerate(new_lines[j1:j2], j1 + 1):
                    html_parts.append(
                        f'<div class="line-row added"><span class="line-num">+{j}</span>'
                        f'<span class="line-content">+ {self._escape_html(line)}</span></div>'
                    )

        html_parts.extend(["</pre>", "</body>", "</html>"])
        return "\n".join(html_parts)

    def generate_patch_summary(self, patch: Patch) -> str:
        """Generate a human-readable summary of a patch.

        Args:
            patch: The patch to summarize

        Returns:
            Summary string
        """
        lines = []
        lines.append(f"File: {patch.file_path}")
        lines.append(f"Hunks: {len(patch.hunks)}")
        lines.append(f"Lines added: {patch.stats.get('added', 0)}")
        lines.append(f"Lines deleted: {patch.stats.get('deleted', 0)}")
        lines.append(f"Lines modified: {patch.stats.get('modified', 0)}")
        return "\n".join(lines)

    # ─── Internal methods ────────────────────────────────────────────────────

    def _generate_diff_lines(
        self,
        old_code: str,
        new_code: str,
        file_path: str,
        options: PatchOptions,
    ) -> list[str]:
        """Generate diff lines using difflib.

        Args:
            old_code: Original code
            new_code: New code
            file_path: File path
            options: Generation options

        Returns:
            List of diff lines
        """
        diff = difflib.unified_diff(
            old_code.splitlines(keepends=True),
            new_code.splitlines(keepends=True),
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            n=options.context_lines,
        )
        return list(diff)

    def _parse_hunks(
        self,
        diff_lines: list[str],
        old_code: str,
        new_code: str,
    ) -> list[Hunk]:
        """Parse diff lines into hunks.

        Args:
            diff_lines: Raw diff output
            old_code: Original code
            new_code: New code

        Returns:
            List of parsed hunks
        """
        hunks: list[Hunk] = []
        current_hunk: Optional[Hunk] = None
        changes: list[LineChange] = []

        old_lines = old_code.splitlines()
        new_lines = new_code.splitlines()

        old_idx = 0
        new_idx = 0

        for line in diff_lines:
            if line.startswith("@@"):
                # Save previous hunk
                if current_hunk:
                    current_hunk.changes = changes
                    current_hunk.new_count = len(changes)
                    hunks.append(current_hunk)
                    changes = []

                # Parse hunk header: @@ -start,count +start,count @@
                match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
                if match:
                    old_start = int(match.group(1))
                    old_count = int(match.group(2) or 1)
                    new_start = int(match.group(3))
                    new_count = int(match.group(4) or 1)

                    current_hunk = Hunk(
                        old_start=old_start,
                        old_count=old_count,
                        new_start=new_start,
                        new_count=new_count,
                        header=line.strip(),
                    )
                    old_idx = old_start - 1
                    new_idx = new_start - 1

            elif line.startswith("-"):
                # Deletion
                changes.append(LineChange(
                    line_number=old_idx + 1,
                    change_type=ChangeType.DELETED,
                    content=line[1:].rstrip("\n"),
                    old_line=old_idx + 1,
                ))
                old_idx += 1

            elif line.startswith("+"):
                # Addition
                changes.append(LineChange(
                    line_number=new_idx + 1,
                    change_type=ChangeType.ADDED,
                    content=line[1:].rstrip("\n"),
                    new_line=new_idx + 1,
                ))
                new_idx += 1

            elif line.startswith(" "):
                # Context
                changes.append(LineChange(
                    line_number=old_idx + 1,
                    change_type=ChangeType.UNCHANGED,
                    content=line[1:].rstrip("\n"),
                    old_line=old_idx + 1,
                    new_line=new_idx + 1,
                ))
                old_idx += 1
                new_idx += 1

        # Save last hunk
        if current_hunk:
            current_hunk.changes = changes
            hunks.append(current_hunk)

        return hunks

    def _calculate_stats(
        self,
        hunks: list[Hunk],
        old_code: str,
        new_code: str,
    ) -> dict[str, int]:
        """Calculate patch statistics.

        Args:
            hunks: List of hunks
            old_code: Original code
            new_code: New code

        Returns:
            Statistics dictionary
        """
        added = 0
        deleted = 0
        modified = 0

        for hunk in hunks:
            for change in hunk.changes:
                if change.change_type == ChangeType.ADDED:
                    added += 1
                elif change.change_type == ChangeType.DELETED:
                    deleted += 1

        return {
            "added": added,
            "deleted": deleted,
            "modified": modified,
            "hunks": len(hunks),
            "old_lines": len(old_code.splitlines()),
            "new_lines": len(new_code.splitlines()),
        }

    def _compute_hash(self, content: str) -> str:
        """Compute MD5 hash of content.

        Args:
            content: Content to hash

        Returns:
            MD5 hex digest
        """
        return hashlib.md5(content.encode()).hexdigest()

    def _remove_whitespace(self, text: str) -> str:
        """Remove whitespace from text for comparison.

        Args:
            text: Input text

        Returns:
            Text with whitespace normalized
        """
        return re.sub(r"\s+", " ", text)

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters.

        Args:
            text: Input text

        Returns:
            HTML-escaped text
        """
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def _format_side_by_side_line(
        self,
        old: str,
        new: str,
        width: int,
        is_old: bool = False,
        is_new: bool = False,
        is_modified: bool = False,
    ) -> str:
        """Format a line for side-by-side display.

        Args:
            old: Old line content
            new: New line content
            width: Column width
            is_old: Line was deleted
            is_new: Line was inserted
            is_modified: Line was modified

        Returns:
            Formatted line
        """
        old_trunc = old[: width - 2] + ".." if len(old) > width else old
        new_trunc = new[: width - 2] + ".." if len(new) > width else new

        prefix = "  "
        if self.options.colorize:
            if is_old or is_modified:
                prefix = f"{self.COLORS['red']}-{self.COLORS['reset']} "
            elif is_new:
                prefix = f"{self.COLORS['green']}+{self.COLORS['reset']} "
            else:
                prefix = "  "

        return f"{prefix}{old_trunc:<{width}}| {new_trunc}"


# ─── Factory Function ───────────────────────────────────────────────────────────


def create_patch_generator(
    format: DiffFormat = DiffFormat.UNIFIED,
    **kwargs: Any,
) -> PatchGenerator:
    """Create a configured patch generator.

    Args:
        format: Output format
        **kwargs: Additional PatchOptions

    Returns:
        Configured PatchGenerator
    """
    options = PatchOptions(format=format, **kwargs)
    return PatchGenerator(options)


def generate_quick_diff(
    old_code: str,
    new_code: str,
    file_path: str = "file.py",
) -> str:
    """Quick function to generate a unified diff.

    Args:
        old_code: Original code
        new_code: New code
        file_path: File path

    Returns:
        Unified diff string
    """
    generator = PatchGenerator()
    return generator.generate_from_strings(old_code, new_code, file_path)
