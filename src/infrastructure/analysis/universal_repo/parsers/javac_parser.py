"""Java compiler (javac) output parser.

Parses the javac error format:
    file.java:line: error: message
    file.java:line: warning: message

Javac also emits a source line and a caret (^) pointing to the error
location, which are captured as raw_output context.

Requirements: 5.5
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..models import CompilerError

if TYPE_CHECKING:
    pass

# ─── Constants ────────────────────────────────────────────────────────────────

# Javac diagnostic line: file:line: severity: message
# Examples:
#   Main.java:10: error: cannot find symbol
#   src/Util.java:25: warning: [unchecked] unchecked conversion
#   C:\Users\dev\Main.java:5: error: ';' expected
# The file portion allows an optional drive letter (e.g., C:) at the start.
_DIAG_PATTERN = re.compile(
    r"^(?P<file>(?:[A-Za-z]:\\)?[^\s:][^:]*\.java)"
    r":(?P<line>\d+):\s*"
    r"(?P<severity>error|warning):\s*"
    r"(?P<message>.+)$"
)

# Context line containing source code (no leading colon-separated fields)
_CONTEXT_LINE_PATTERN = re.compile(r"^(\s+.*|.*\^.*)$")

# Caret indicator line
_CARET_LINE_PATTERN = re.compile(r"^\s*\^+\s*$")

COMPILER_NAME = "javac"
DEFAULT_COLUMN = 0  # javac doesn't always provide column info


class JavacParser:
    """Parser for Java compiler (javac) output.

    Implements the CompilerOutputParser protocol:
      - parse(output: str) -> list[CompilerError]
      - format(error: CompilerError) -> str

    The javac compiler emits diagnostics in the format:
        file.java:line: error: message
        file.java:line: warning: message

    Followed by an optional source line and caret (^) indicator.

    Requirement: 5.5 — Parse Java compiler (javac) error format:
                        file:line: error: message
    """

    def parse(self, output: str) -> list[CompilerError]:
        """Parse raw javac compiler output into structured errors.

        Handles:
        - Standard diagnostics: file.java:line: error: message
        - Warning diagnostics: file.java:line: warning: message
        - Source context lines with caret indicator

        Args:
            output: Raw text output from javac invocation.

        Returns:
            List of CompilerError objects extracted from the output.
        """
        if not output or not output.strip():
            return []

        lines = output.splitlines()
        errors: list[CompilerError] = []
        idx = 0

        while idx < len(lines):
            line = lines[idx]

            match = _DIAG_PATTERN.match(line)
            if match:
                error, idx = self._parse_diagnostic(match, lines, idx)
                errors.append(error)
                continue

            idx += 1

        return errors

    def format(self, error: CompilerError) -> str:
        """Format a CompilerError back into javac-style output.

        Reconstructs the standard javac diagnostic format from structured data.

        Args:
            error: A structured CompilerError object.

        Returns:
            Human-readable string in javac output format.
        """
        parts: list[str] = []

        formatted = f"{error.file_path}:{error.line}: {error.severity}: {error.message}"
        parts.append(formatted)

        # Append raw context if present (source line + caret)
        if error.raw_output:
            parts.append(error.raw_output)

        return "\n".join(parts)

    # ─── Private Helpers ──────────────────────────────────────────────────

    def _parse_diagnostic(
        self, match: re.Match[str], lines: list[str], idx: int
    ) -> tuple[CompilerError, int]:
        """Parse a javac diagnostic line and collect trailing context.

        Returns:
            Tuple of (CompilerError, next_line_index).
        """
        file_path = match.group("file")
        line_num = int(match.group("line"))
        severity = match.group("severity")
        message = match.group("message").strip()

        # Collect multi-line context (source line + caret)
        context_lines: list[str] = []
        idx += 1
        idx = self._collect_context(lines, idx, context_lines)

        # Derive column from caret position if available
        column = self._extract_column_from_caret(context_lines)

        raw_output = "\n".join(context_lines) if context_lines else ""

        error = CompilerError(
            file_path=file_path,
            line=line_num,
            column=column,
            severity=severity,
            error_code="",
            message=message,
            compiler=COMPILER_NAME,
            raw_output=raw_output,
        )
        return error, idx

    def _collect_context(
        self, lines: list[str], idx: int, context_lines: list[str]
    ) -> int:
        """Collect context lines following a diagnostic (source + caret).

        Context lines are those starting with whitespace or containing
        a caret (^) indicator. Stops at next diagnostic or empty line.

        Returns:
            The index of the next non-context line.
        """
        while idx < len(lines):
            line = lines[idx]
            # Empty lines end context collection
            if not line.strip():
                idx += 1
                break
            # If the line matches a new diagnostic, stop
            if _DIAG_PATTERN.match(line):
                break
            # Context lines: match pattern or contain caret
            if _CONTEXT_LINE_PATTERN.match(line) or _CARET_LINE_PATTERN.match(line):
                context_lines.append(line)
                idx += 1
            else:
                # Non-context, non-diagnostic line — stop
                break

        return idx

    @staticmethod
    def _extract_column_from_caret(context_lines: list[str]) -> int:
        """Extract column number from caret position in context.

        Scans context lines for a caret (^) indicator and returns
        its 1-indexed position. Returns DEFAULT_COLUMN if no caret found.

        Returns:
            1-indexed column position, or DEFAULT_COLUMN (0) if not found.
        """
        for line in context_lines:
            caret_pos = line.find("^")
            if caret_pos >= 0:
                # Return 1-indexed column position
                return caret_pos + 1
        return DEFAULT_COLUMN
