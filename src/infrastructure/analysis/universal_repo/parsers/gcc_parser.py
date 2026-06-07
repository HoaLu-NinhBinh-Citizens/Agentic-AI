"""GCC/G++/Clang compiler output parser.

Parses the standard GCC/Clang error format:
    file:line:column: severity: message [-Wflag]

Handles errors, warnings, and notes. Multi-line context (caret lines,
source snippets) is captured in raw_output.

Requirements: 5.1
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..models import CompilerError

if TYPE_CHECKING:
    pass

# ─── Constants ────────────────────────────────────────────────────────────────

# Main diagnostic line: file:line:col: severity: message
# Examples:
#   main.c:10:5: error: use of undeclared identifier 'foo'
#   src/util.c:25:1: warning: unused variable 'x' [-Wunused-variable]
#   C:\Users\dev\src\main.c:5:3: error: expected ';'
# The file portion allows an optional drive letter (e.g., C:) at the start.
_DIAG_PATTERN = re.compile(
    r"^(?P<file>(?:[A-Za-z]:\\)?[^\s:][^:]*):(?P<line>\d+):(?P<col>\d+):\s*"
    r"(?P<severity>error|warning|note):\s*"
    r"(?P<message>.+)$"
)

# Linker-style error without file location:
#   error: linker command failed with exit code 1
_LINKER_PATTERN = re.compile(
    r"^(?P<severity>error|warning|note):\s*(?P<message>.+)$"
)

# Error code in brackets at end of message: [-Wunused-variable]
_ERROR_CODE_PATTERN = re.compile(r"\[(-W[\w-]+)\]\s*$")

# Context lines: start with spaces, or contain caret indicator ^
_CONTEXT_LINE_PATTERN = re.compile(r"^(\s+.*|.*\^.*)$")

COMPILER_NAME = "gcc"


class GccParser:
    """Parser for GCC/G++ and Clang compiler output.

    Implements the CompilerOutputParser protocol:
      - parse(output: str) -> list[CompilerError]
      - format(error: CompilerError) -> str

    The parser handles the standard diagnostic format emitted by gcc, g++,
    and clang compilers, including multi-line context and error codes in
    bracket notation.

    Requirement: 5.1 — Parse gcc/g++ error format: file:line:column: severity: message
    """

    def parse(self, output: str) -> list[CompilerError]:
        """Parse raw GCC/Clang compiler output into structured errors.

        Handles:
        - Standard diagnostics: file:line:col: severity: message
        - Linker errors: error: message (no file location)
        - Error codes in brackets: [-Wflag]
        - Multi-line context (source snippets, caret indicators)

        Args:
            output: Raw text output from gcc/g++/clang invocation.

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

            # Try standard diagnostic format first
            match = _DIAG_PATTERN.match(line)
            if match:
                error, idx = self._parse_diagnostic(match, lines, idx)
                errors.append(error)
                continue

            # Try linker-style error (no file location)
            linker_match = _LINKER_PATTERN.match(line)
            if linker_match:
                error, idx = self._parse_linker_error(linker_match, lines, idx)
                errors.append(error)
                continue

            idx += 1

        return errors

    def format(self, error: CompilerError) -> str:
        """Format a CompilerError back into GCC-style output.

        Reconstructs the standard gcc diagnostic format from structured data.

        Args:
            error: A structured CompilerError object.

        Returns:
            Human-readable string in gcc/clang output format.
        """
        parts: list[str] = []

        if error.file_path:
            # Standard format: file:line:col: severity: message
            location = f"{error.file_path}:{error.line}:{error.column}"
            message = error.message
            if error.error_code:
                message = f"{message} [{error.error_code}]"
            parts.append(f"{location}: {error.severity}: {message}")
        else:
            # Linker-style: severity: message
            message = error.message
            if error.error_code:
                message = f"{message} [{error.error_code}]"
            parts.append(f"{error.severity}: {message}")

        # Append raw context if present
        if error.raw_output:
            parts.append(error.raw_output)

        return "\n".join(parts)

    # ─── Private Helpers ──────────────────────────────────────────────────

    def _parse_diagnostic(
        self, match: re.Match[str], lines: list[str], idx: int
    ) -> tuple[CompilerError, int]:
        """Parse a standard diagnostic line and collect trailing context.

        Returns:
            Tuple of (CompilerError, next_line_index).
        """
        file_path = match.group("file")
        line_num = int(match.group("line"))
        col_num = int(match.group("col"))
        severity = match.group("severity")
        message = match.group("message").strip()

        # Extract error code from brackets at end of message
        error_code = self._extract_error_code(message)
        if error_code:
            # Remove the bracket portion from message
            message = _ERROR_CODE_PATTERN.sub("", message).strip()

        # Collect multi-line context
        context_lines: list[str] = []
        idx += 1
        idx = self._collect_context(lines, idx, context_lines)

        raw_output = "\n".join(context_lines) if context_lines else ""

        error = CompilerError(
            file_path=file_path,
            line=line_num,
            column=col_num,
            severity=severity,
            error_code=error_code,
            message=message,
            compiler=COMPILER_NAME,
            raw_output=raw_output,
        )
        return error, idx

    def _parse_linker_error(
        self, match: re.Match[str], lines: list[str], idx: int
    ) -> tuple[CompilerError, int]:
        """Parse a linker-style error (no file location).

        Returns:
            Tuple of (CompilerError, next_line_index).
        """
        severity = match.group("severity")
        message = match.group("message").strip()

        error_code = self._extract_error_code(message)
        if error_code:
            message = _ERROR_CODE_PATTERN.sub("", message).strip()

        # Collect any following context lines
        context_lines: list[str] = []
        idx += 1
        idx = self._collect_context(lines, idx, context_lines)

        raw_output = "\n".join(context_lines) if context_lines else ""

        error = CompilerError(
            file_path="",
            line=0,
            column=0,
            severity=severity,
            error_code=error_code,
            message=message,
            compiler=COMPILER_NAME,
            raw_output=raw_output,
        )
        return error, idx

    def _collect_context(
        self, lines: list[str], idx: int, context_lines: list[str]
    ) -> int:
        """Collect multi-line context following a diagnostic.

        Context lines are those that start with whitespace or contain
        a caret (^) indicator pointing to the error location.

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
            if _DIAG_PATTERN.match(line) or _LINKER_PATTERN.match(line):
                break
            # Context lines: start with space or contain caret
            if _CONTEXT_LINE_PATTERN.match(line):
                context_lines.append(line)
                idx += 1
            else:
                # Non-context, non-diagnostic line — stop
                break

        return idx

    @staticmethod
    def _extract_error_code(message: str) -> str:
        """Extract error code from bracket notation at end of message.

        Example: "unused variable 'x' [-Wunused-variable]"
                 → returns "-Wunused-variable"

        Returns:
            The error code string, or empty string if not found.
        """
        match = _ERROR_CODE_PATTERN.search(message)
        if match:
            return match.group(1)
        return ""
