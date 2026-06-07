"""TypeScript compiler (tsc) output parser.

Parses the standard tsc error format:
    file(line,column): error TSnnnn: message

Handles errors and warnings. Extracts TS error codes (e.g., TS2304, TS2345).

Requirements: 5.2
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..models import CompilerError

if TYPE_CHECKING:
    pass

# ─── Constants ────────────────────────────────────────────────────────────────

# Main diagnostic line: file(line,column): severity TScode: message
# Examples:
#   src/app.ts(10,5): error TS2304: Cannot find name 'foo'.
#   index.ts(3,14): error TS2345: Argument of type 'string' is not assignable...
#   C:\Users\dev\src\app.ts(10,5): warning TS6133: 'x' is declared but...
# The file portion allows an optional drive letter (e.g., C:) at the start.
_DIAG_PATTERN = re.compile(
    r"^(?P<file>(?:[A-Za-z]:\\)?[^\s(][^(]*)\((?P<line>\d+),(?P<col>\d+)\):\s*"
    r"(?P<severity>error|warning)\s+"
    r"(?P<code>TS\d+):\s*"
    r"(?P<message>.+)$"
)

COMPILER_NAME = "tsc"


class TscParser:
    """Parser for TypeScript compiler (tsc) output.

    Implements the CompilerOutputParser protocol:
      - parse(output: str) -> list[CompilerError]
      - format(error: CompilerError) -> str

    The parser handles the standard diagnostic format emitted by the
    TypeScript compiler, including error codes and both error/warning
    severities.

    Requirement: 5.2 — Parse tsc error format: file(line,column): error TSnnnn: message
    """

    def parse(self, output: str) -> list[CompilerError]:
        """Parse raw tsc compiler output into structured errors.

        Handles:
        - Standard diagnostics: file(line,col): severity TScode: message
        - Both error and warning severities
        - TS error code extraction

        Args:
            output: Raw text output from tsc invocation.

        Returns:
            List of CompilerError objects extracted from the output.
        """
        if not output or not output.strip():
            return []

        lines = output.splitlines()
        errors: list[CompilerError] = []

        for line in lines:
            match = _DIAG_PATTERN.match(line)
            if match:
                error = self._parse_diagnostic(match)
                errors.append(error)

        return errors

    def format(self, error: CompilerError) -> str:
        """Format a CompilerError back into tsc-style output.

        Reconstructs the standard tsc diagnostic format from structured data.
        Format: file_path(line,column): severity TScode: message

        Args:
            error: A structured CompilerError object.

        Returns:
            Human-readable string in tsc output format.
        """
        location = f"{error.file_path}({error.line},{error.column})"
        code = error.error_code if error.error_code else "TS0000"
        return f"{location}: {error.severity} {code}: {error.message}"

    # ─── Private Helpers ──────────────────────────────────────────────────

    def _parse_diagnostic(self, match: re.Match[str]) -> CompilerError:
        """Parse a single tsc diagnostic line into a CompilerError.

        Args:
            match: Regex match object from _DIAG_PATTERN.

        Returns:
            A structured CompilerError object.
        """
        file_path = match.group("file")
        line_num = int(match.group("line"))
        col_num = int(match.group("col"))
        severity = match.group("severity")
        error_code = match.group("code")
        message = match.group("message").strip()

        return CompilerError(
            file_path=file_path,
            line=line_num,
            column=col_num,
            severity=severity,
            error_code=error_code,
            message=message,
            compiler=COMPILER_NAME,
            raw_output="",
        )
