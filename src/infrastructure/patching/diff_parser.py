"""Unified diff parser for parsing and applying patches.

Provides:
- Parsing unified diff format into structured objects
- Applying hunks to content with line-level precision
- Support for multiple files in a single diff

Architecture:
    UnifiedDiffParser.parse() → list[ParsedFileDiff]
    UnifiedDiffParser.apply_hunk() → modified content lines
    UnifiedDiffParser.apply_diff() → complete modified content
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DiffHunk:
    """A single hunk of a unified diff."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str]

    @property
    def removed_lines(self) -> list[str]:
        """Get lines being removed (starting with '-')."""
        return [l[1:] for l in self.lines if l.startswith("-")]

    @property
    def added_lines(self) -> list[str]:
        """Get lines being added (starting with '+')."""
        return [l[1:] for l in self.lines if l.startswith("+")]

    @property
    def context_lines(self) -> list[str]:
        """Get context lines (starting with ' ')."""
        return [l[1:] for l in self.lines if l.startswith(" ")]


@dataclass
class ParsedFileDiff:
    """Parsed unified diff for a single file."""
    old_path: str
    new_path: str
    hunks: list[DiffHunk] = field(default_factory=list)

    def apply_to(self, content_lines: list[str]) -> list[str]:
        """Apply all hunks to content lines, returning modified lines."""
        result = content_lines.copy()
        for hunk in reversed(self.hunks):
            result = _apply_single_hunk(result, hunk)
        return result


@dataclass
class ParseResult:
    """Result of parsing a diff."""
    success: bool
    files: list[ParsedFileDiff] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def hunks(self) -> list[DiffHunk]:
        """Get all hunks from all files."""
        return [h for f in self.files for h in f.hunks]


class UnifiedDiffParser:
    """Parse unified diff format with support for multi-file diffs.

    Supports standard unified diff format:
        --- a/file.py
        +++ b/file.py
        @@ -start,count +start,count @@
        - removed line
        + added line
         context line

    Usage:
        parser = UnifiedDiffParser()
        result = parser.parse(diff_text)

        if result.success:
            for file_diff in result.files:
                modified_lines = file_diff.apply_to(original_lines)
    """

    # Pattern for diff header: --- a/path and +++ b/path
    # Matches: --- a/test.py or --- test.py (with optional timestamp)
    # Uses greedy + to match full path (non-greedy +? caused issues)
    HEADER_PATTERN = re.compile(
        r"^---\s+(?:a/)?([^\t\n]+)\n"
        r"^\+\+\+\s+(?:b/)?([^\t\n]+)",
        re.MULTILINE,
    )

    # Pattern for hunk header: @@ -old,count +new,count @@
    HUNK_PATTERN = re.compile(
        r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*?)(?=\n@@|\n---|\n\+\+\+|$)",
        re.MULTILINE | re.DOTALL,
    )

    def __init__(self, strict: bool = False) -> None:
        """
        Args:
            strict: If True, validate that hunks match content exactly.
        """
        self._strict = strict

    def parse(self, diff_text: str) -> ParseResult:
        """Parse unified diff text into structured format.

        Args:
            diff_text: Unified diff string to parse.

        Returns:
            ParseResult with parsed files and hunks.
        """
        if not diff_text or not diff_text.strip():
            return ParseResult(success=False, error="Empty diff")

        try:
            files = self._parse_files(diff_text)
            if not files:
                return ParseResult(success=False, error="No valid diff hunks found")
            return ParseResult(success=True, files=files)
        except Exception as e:
            logger.error("Failed to parse diff: %s", e)
            return ParseResult(success=False, error=str(e))

    def _parse_files(self, diff_text: str) -> list[ParsedFileDiff]:
        """Parse multiple file diffs from a single diff string."""
        files: list[ParsedFileDiff] = []

        # Split by file headers
        parts = re.split(r"(?=^--- )", diff_text, flags=re.MULTILINE)

        for part in parts:
            if not part.strip():
                continue

            # Check if this is a file header section
            header_match = self.HEADER_PATTERN.match(part)
            if header_match:
                # Strip a/ and b/ prefixes if present
                old_path = header_match.group(1)
                new_path = header_match.group(2)
                if old_path.startswith("a/"):
                    old_path = old_path[2:]
                if new_path.startswith("b/"):
                    new_path = new_path[2:]

                file_diff = ParsedFileDiff(old_path=old_path, new_path=new_path)

                # Parse hunks in this file section
                hunks = self._parse_hunks_in_section(part)
                file_diff.hunks.extend(hunks)
                files.append(file_diff)

        return files

    def _parse_hunks_in_section(self, section: str) -> list[DiffHunk]:
        """Parse all hunks within a file section.
        
        Uses a line-by-line approach since the regex can't easily capture
        the variable-length content between hunks.
        """
        hunks: list[DiffHunk] = []
        lines = section.split("\n")
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Look for hunk header
            hunk_match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)", line)
            if hunk_match:
                old_start = int(hunk_match.group(1))
                old_count = int(hunk_match.group(2)) if hunk_match.group(2) else 1
                new_start = int(hunk_match.group(3))
                new_count = int(hunk_match.group(4)) if hunk_match.group(4) else 1
                
                # Collect hunk lines until next hunk or end
                hunk_lines: list[str] = []
                i += 1
                
                while i < len(lines):
                    next_line = lines[i]
                    # Stop at next hunk header or file header
                    if next_line.startswith("@@ ") or next_line.startswith("--- "):
                        break
                    # Skip empty lines that might be at the end
                    if not next_line and i == len(lines) - 1:
                        break
                    hunk_lines.append(next_line)
                    i += 1
                
                hunks.append(DiffHunk(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    lines=hunk_lines,
                ))
                continue
            
            i += 1
        
        return hunks

    def parse_hunk_header(self, header: str) -> tuple[int, int, int, int]:
        """Parse @@ header into line counts.

        Args:
            header: Hunk header string like "@@ -1,3 +1,4 @@"

        Returns:
            Tuple of (old_start, old_count, new_start, new_count)
        """
        match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", header)
        if not match:
            raise ValueError(f"Invalid hunk header: {header}")

        old_start = int(match.group(1))
        old_count = int(match.group(2)) if match.group(2) else 1
        new_start = int(match.group(3))
        new_count = int(match.group(4)) if match.group(4) else 1

        return old_start, old_count, new_start, new_count

    def apply_hunk(
        self,
        content: list[str],
        hunk: DiffHunk,
    ) -> list[str]:
        """Apply a single hunk to content lines.

        Args:
            content: Original content as list of lines (without trailing \\n).
            hunk: Hunk to apply.

        Returns:
            Modified content lines.
        """
        return _apply_single_hunk(content, hunk)

    def apply_diff(
        self,
        original: str,
        diff: str,
        file_path: Optional[str] = None,
    ) -> str:
        """Apply a unified diff to original content.

        Args:
            original: Original file content.
            diff: Unified diff string.
            file_path: Optional file path to select specific file from multi-file diff.

        Returns:
            Modified content string.
        """
        result = self.parse(diff)
        if not result.success:
            raise ValueError(f"Invalid diff: {result.error}")

        content_lines = original.splitlines(keepends=False)

        for file_diff in result.files:
            # If file_path specified, skip non-matching files
            if file_path and file_path not in (file_diff.old_path, file_diff.new_path):
                continue

            content_lines = file_diff.apply_to(content_lines)

        return "\n".join(content_lines)


def _hunk_old_lines(hunk: DiffHunk) -> list[tuple[bool, str]]:
    """(is_context, text) for lines the hunk expects in the original.

    A bare empty string is treated as a blank context line: LLM- and
    editor-generated diffs frequently emit blank context lines without the
    leading space.
    """
    old_lines: list[tuple[bool, str]] = []
    for line in hunk.lines:
        if line == "":
            old_lines.append((True, ""))
        elif line.startswith(" "):
            old_lines.append((True, line[1:]))
        elif line.startswith("-"):
            old_lines.append((False, line[1:]))
    return old_lines


def _matches_at(
    content: list[str],
    expected: list[tuple[bool, str]],
    pos: int,
    strict_removed: bool,
) -> bool:
    """Check whether the hunk's expected lines fit content at `pos`.

    Context lines must match exactly. Removed lines may differ (LLM diffs
    often paraphrase the line being deleted) — unless the hunk has no
    context at all, in which case removed lines anchor the position and
    must match exactly to avoid deleting arbitrary content.
    """
    if pos < 0 or pos + len(expected) > len(content):
        return False
    for offset, (is_context, text) in enumerate(expected):
        if (is_context or strict_removed) and content[pos + offset] != text:
            return False
    return True


def _find_hunk_anchor(
    content: list[str], old_lines: list[tuple[bool, str]], declared: int
) -> Optional[int]:
    """Locate where the hunk's old lines actually appear in content.

    Prefers the declared position; otherwise relocates to the nearest match
    (handles off-by-N hunk headers without risking corruption).
    Returns None when no position matches.
    """
    # Without any context line, removed lines are the only anchor and must
    # match exactly; with context, the context anchors the position.
    strict_removed = not any(is_context for is_context, _ in old_lines)

    if _matches_at(content, old_lines, declared, strict_removed):
        return declared

    n = len(old_lines)
    candidates = [
        i
        for i in range(0, len(content) - n + 1)
        if _matches_at(content, old_lines, i, strict_removed)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda i: abs(i - declared))


def _apply_single_hunk(content: list[str], hunk: DiffHunk) -> list[str]:
    """Apply a single hunk to content lines.

    The hunk's expected original lines (context + removals) must match the
    file content — at the declared position or, failing that, at the nearest
    exact match elsewhere in the file. A hunk whose original lines cannot be
    found raises ValueError instead of being force-applied, because silently
    clamping bounds corrupts files when LLM-generated hunk headers are off.
    """
    if not hunk.lines:
        return content

    old_lines = _hunk_old_lines(hunk)
    declared = max(hunk.old_start - 1, 0)

    if not old_lines:
        # Pure-insertion hunk: nothing to validate against, keep declared position
        anchor = min(declared, len(content))
    else:
        anchor = _find_hunk_anchor(content, old_lines, declared)
        if anchor is None:
            raise ValueError(
                f"Hunk @@ -{hunk.old_start},{hunk.old_count} @@ does not match "
                f"file content: expected lines not found "
                f"(first expected line: {old_lines[0][1]!r})"
            )

    result = content[:anchor]
    orig_idx = anchor

    for line in hunk.lines:
        if line.startswith("-"):
            # Removed line - skip from original
            orig_idx += 1
        elif line.startswith("+"):
            # Added line - include in result
            result.append(line[1:])
        elif line.startswith(" ") or line == "":
            # Context line (blank context may lack the leading space)
            result.append(content[orig_idx])
            orig_idx += 1
        # Other markers ("\\ No newline at end of file", etc.) are ignored

    result.extend(content[orig_idx:])
    return result


class ApplyResult:
    """Result of applying a diff."""

    def __init__(
        self,
        success: bool,
        file_path: Optional[str] = None,
        lines_modified: int = 0,
        error: Optional[str] = None,
    ) -> None:
        self.success = success
        self.file_path = file_path
        self.lines_modified = lines_modified
        self.error = error

    def __repr__(self) -> str:
        if self.success:
            return f"ApplyResult(success=True, file={self.file_path}, modified={self.lines_modified})"
        return f"ApplyResult(success=False, error={self.error})"


def create_parser(strict: bool = False) -> UnifiedDiffParser:
    """Factory function to create a UnifiedDiffParser."""
    return UnifiedDiffParser(strict=strict)
