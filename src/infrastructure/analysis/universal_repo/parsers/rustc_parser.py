"""Rust compiler (rustc) output parser.

Parses the structured diagnostic output format emitted by rustc:
    error[E0308]: mismatched types
     --> src/main.rs:10:5

Handles errors, warnings, multi-line error spans, suggestion blocks,
and error codes (E0308, E0425, etc.). Context between error headers
is captured in raw_output; help/suggestion lines are stored separately.

Requirements: 5.3
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..models import CompilerError

if TYPE_CHECKING:
    pass

# ─── Constants ────────────────────────────────────────────────────────────────

# Error/warning header with optional error code in brackets:
#   error[E0308]: mismatched types
#   warning[unused_variables]: unused variable `x`
#   error: could not compile `myproject`
_HEADER_PATTERN = re.compile(
    r"^(error|warning)(\[(?P<code>E\d+)\])?:\s*(?P<message>.+)$"
)

# Location line:
#   --> src/main.rs:10:5
_LOCATION_PATTERN = re.compile(
    r"^\s*-->\s*(?P<file>.+):(?P<line>\d+):(?P<col>\d+)\s*$"
)

# Suggestion lines (help annotations):
#   = help: consider borrowing here
#   help: try using a conversion method
_SUGGESTION_PATTERN = re.compile(
    r"^\s*=\s*help:\s*(?P<suggestion>.+)$"
)

_SUGGESTION_ALT_PATTERN = re.compile(
    r"^\s*help:\s*(?P<suggestion>.+)$"
)

COMPILER_NAME = "rustc"


class RustcParser:
    """Parser for Rust compiler (rustc) output.

    Implements the CompilerOutputParser protocol:
      - parse(output: str) -> list[CompilerError]
      - format(error: CompilerError) -> str

    The parser handles rustc's structured diagnostic format including
    multi-line error spans, error codes (E0308, etc.), and suggestion
    blocks (help: lines).

    Requirement: 5.3 — Parse rustc error format including multi-line
    error spans and suggestion blocks.
    """

    def parse(self, output: str) -> list[CompilerError]:
        """Parse raw rustc compiler output into structured errors.

        Handles:
        - Error headers with codes: error[E0308]: message
        - Error headers without codes: error: message
        - Warning headers: warning[code]: message / warning: message
        - Location lines: --> file:line:col
        - Suggestion lines: = help: ... or help: ...
        - Multi-line context (source snippets, span indicators)

        Args:
            output: Raw text output from a rustc invocation.

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

            match = _HEADER_PATTERN.match(line)
            if match:
                error, idx = self._parse_diagnostic(match, lines, idx)
                errors.append(error)
                continue

            idx += 1

        return errors

    def format(self, error: CompilerError) -> str:
        """Format a CompilerError back into rustc-style output.

        Reconstructs the standard rustc diagnostic format from structured data.

        Args:
            error: A structured CompilerError object.

        Returns:
            Human-readable string in rustc output format.
        """
        parts: list[str] = []

        # Header line: error[E0308]: message or error: message
        if error.error_code:
            parts.append(f"{error.severity}[{error.error_code}]: {error.message}")
        else:
            parts.append(f"{error.severity}: {error.message}")

        # Location line: --> file:line:col
        if error.file_path:
            parts.append(f" --> {error.file_path}:{error.line}:{error.column}")

        # Append raw context if present
        if error.raw_output:
            parts.append(error.raw_output)

        return "\n".join(parts)

    # ─── Private Helpers ──────────────────────────────────────────────────

    def _parse_diagnostic(
        self, match: re.Match[str], lines: list[str], idx: int
    ) -> tuple[CompilerError, int]:
        """Parse a rustc diagnostic header and collect body content.

        Collects the location line, context lines (source snippets, span
        indicators), and suggestion/help lines that follow the header.

        Returns:
            Tuple of (CompilerError, next_line_index).
        """
        severity = match.group(1)
        error_code = match.group("code") or ""
        message = match.group("message").strip()

        file_path = ""
        line_num = 0
        col_num = 0
        suggestions: list[str] = []
        context_lines: list[str] = []

        idx += 1

        # Collect all lines until the next error/warning header
        while idx < len(lines):
            current = lines[idx]

            # Stop at the next diagnostic header
            if _HEADER_PATTERN.match(current):
                break

            # Try to match a location line
            loc_match = _LOCATION_PATTERN.match(current)
            if loc_match and not file_path:
                file_path = loc_match.group("file")
                line_num = int(loc_match.group("line"))
                col_num = int(loc_match.group("col"))
                context_lines.append(current)
                idx += 1
                continue

            # Try to match suggestion lines
            sug_match = _SUGGESTION_PATTERN.match(current)
            if sug_match:
                suggestions.append(sug_match.group("suggestion").strip())
                context_lines.append(current)
                idx += 1
                continue

            sug_alt_match = _SUGGESTION_ALT_PATTERN.match(current)
            if sug_alt_match:
                suggestions.append(sug_alt_match.group("suggestion").strip())
                context_lines.append(current)
                idx += 1
                continue

            # Any other line is context (source snippets, pipe chars, etc.)
            context_lines.append(current)
            idx += 1

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
            suggestions=suggestions,
        )
        return error, idx
