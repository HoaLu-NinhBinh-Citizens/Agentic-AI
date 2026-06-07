"""Go compiler output parser.

Parses the Go compiler error format:
    file:line:column: message

All Go compiler errors are severity="error" — the Go toolchain does not
emit warnings as compiler errors. The `go vet` tool emits diagnostics
separately, but this parser targets `go build` output.

Requirements: 5.4
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..models import CompilerError

if TYPE_CHECKING:
    pass

# ─── Constants ────────────────────────────────────────────────────────────────

# Go compiler diagnostic line: file:line:col: message
# Examples:
#   ./main.go:10:5: undefined: foo
#   main.go:15:2: syntax error: unexpected newline
#   pkg/util/helper.go:3:1: imported and not used: "fmt"
#   C:\Users\dev\main.go:5:3: undefined: bar
# The file portion allows an optional drive letter (e.g., C:) or ./ prefix.
_DIAG_PATTERN = re.compile(
    r"^(?P<file>(?:\./)?(?:[A-Za-z]:\\)?[^\s:][^:]*)"
    r":(?P<line>\d+):(?P<col>\d+):\s*"
    r"(?P<message>.+)$"
)

# Go linker errors without column info: file:line: message
# Examples:
#   ./main.go:10: undefined reference to 'foo'
_DIAG_NO_COL_PATTERN = re.compile(
    r"^(?P<file>(?:\./)?(?:[A-Za-z]:\\)?[^\s:][^:]*)"
    r":(?P<line>\d+):\s*"
    r"(?P<message>.+)$"
)

COMPILER_NAME = "go"
DEFAULT_SEVERITY = "error"


class GoParser:
    """Parser for Go compiler (go build) output.

    Implements the CompilerOutputParser protocol:
      - parse(output: str) -> list[CompilerError]
      - format(error: CompilerError) -> str

    The Go compiler emits diagnostics in the format:
        file.go:line:col: message

    All diagnostics are treated as errors since the Go compiler
    does not produce warnings during compilation.

    Requirement: 5.4 — Parse Go compiler error format: file:line:column: message
    """

    def parse(self, output: str) -> list[CompilerError]:
        """Parse raw Go compiler output into structured errors.

        Handles:
        - Standard diagnostics: file:line:col: message
        - Diagnostics without column: file:line: message
        - Relative paths with ./ prefix

        Args:
            output: Raw text output from `go build` invocation.

        Returns:
            List of CompilerError objects extracted from the output.
        """
        if not output or not output.strip():
            return []

        lines = output.splitlines()
        errors: list[CompilerError] = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Try standard format with column
            match = _DIAG_PATTERN.match(line)
            if match:
                error = self._build_error(
                    file_path=match.group("file"),
                    line_num=int(match.group("line")),
                    col_num=int(match.group("col")),
                    message=match.group("message").strip(),
                )
                errors.append(error)
                continue

            # Try format without column (linker-style)
            match_no_col = _DIAG_NO_COL_PATTERN.match(line)
            if match_no_col:
                error = self._build_error(
                    file_path=match_no_col.group("file"),
                    line_num=int(match_no_col.group("line")),
                    col_num=0,
                    message=match_no_col.group("message").strip(),
                )
                errors.append(error)

        return errors

    def format(self, error: CompilerError) -> str:
        """Format a CompilerError back into Go compiler-style output.

        Reconstructs the standard Go diagnostic format from structured data.

        Args:
            error: A structured CompilerError object.

        Returns:
            Human-readable string in Go compiler output format.
        """
        if error.column > 0:
            return f"{error.file_path}:{error.line}:{error.column}: {error.message}"
        return f"{error.file_path}:{error.line}: {error.message}"

    # ─── Private Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _build_error(
        file_path: str,
        line_num: int,
        col_num: int,
        message: str,
    ) -> CompilerError:
        """Create a CompilerError with Go-specific defaults.

        All Go compiler errors have severity="error" and no error_code.
        """
        return CompilerError(
            file_path=file_path,
            line=line_num,
            column=col_num,
            severity=DEFAULT_SEVERITY,
            error_code="",
            message=message,
            compiler=COMPILER_NAME,
        )
