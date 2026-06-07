"""Unit tests for TscParser — TypeScript compiler output parser.

Tests parsing of standard tsc diagnostics, error/warning severities,
TS error code extraction, and the format() round-trip.

Requirements: 5.2
"""

from __future__ import annotations

import pytest

from infrastructure.analysis.universal_repo.parsers.tsc_parser import TscParser


@pytest.fixture
def parser() -> TscParser:
    return TscParser()


# ─── Basic Diagnostic Parsing ─────────────────────────────────────────────────


class TestBasicDiagnosticParsing:
    """Test parsing of standard tsc diagnostic lines."""

    def test_parses_simple_error(self, parser: TscParser):
        output = "src/app.ts(10,5): error TS2304: Cannot find name 'foo'."
        errors = parser.parse(output)

        assert len(errors) == 1
        err = errors[0]
        assert err.file_path == "src/app.ts"
        assert err.line == 10
        assert err.column == 5
        assert err.severity == "error"
        assert err.error_code == "TS2304"
        assert err.message == "Cannot find name 'foo'."
        assert err.compiler == "tsc"

    def test_parses_type_mismatch_error(self, parser: TscParser):
        output = (
            "index.ts(3,14): error TS2345: Argument of type 'string' "
            "is not assignable to parameter of type 'number'."
        )
        errors = parser.parse(output)

        assert len(errors) == 1
        err = errors[0]
        assert err.file_path == "index.ts"
        assert err.line == 3
        assert err.column == 14
        assert err.severity == "error"
        assert err.error_code == "TS2345"
        assert "Argument of type 'string'" in err.message

    def test_parses_warning(self, parser: TscParser):
        output = "src/utils.ts(15,3): warning TS6133: 'x' is declared but its value is never read."
        errors = parser.parse(output)

        assert len(errors) == 1
        err = errors[0]
        assert err.severity == "warning"
        assert err.error_code == "TS6133"
        assert "'x' is declared but its value is never read." == err.message

    def test_parses_path_with_directory(self, parser: TscParser):
        output = "src/components/Button.tsx(42,12): error TS2339: Property 'onClick' does not exist."
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].file_path == "src/components/Button.tsx"
        assert errors[0].line == 42
        assert errors[0].column == 12

    def test_parses_windows_path(self, parser: TscParser):
        output = "C:\\Users\\dev\\src\\app.ts(5,3): error TS2304: Cannot find name 'bar'."
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].file_path == "C:\\Users\\dev\\src\\app.ts"
        assert errors[0].line == 5
        assert errors[0].column == 3


# ─── Multiple Errors ──────────────────────────────────────────────────────────


class TestMultipleErrors:
    """Test parsing of multiple errors in one output."""

    def test_parses_multiple_errors(self, parser: TscParser):
        output = (
            "src/app.ts(10,5): error TS2304: Cannot find name 'foo'.\n"
            "src/app.ts(15,9): warning TS6133: 'unused' is declared but never read.\n"
            "src/util.ts(3,1): error TS2345: Type mismatch."
        )
        errors = parser.parse(output)

        assert len(errors) == 3
        assert errors[0].severity == "error"
        assert errors[0].error_code == "TS2304"
        assert errors[1].severity == "warning"
        assert errors[1].error_code == "TS6133"
        assert errors[2].file_path == "src/util.ts"
        assert errors[2].error_code == "TS2345"


# ─── Empty/Edge Cases ────────────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and empty inputs."""

    def test_empty_string_returns_empty_list(self, parser: TscParser):
        assert parser.parse("") == []

    def test_whitespace_only_returns_empty_list(self, parser: TscParser):
        assert parser.parse("   \n\n  ") == []

    def test_non_diagnostic_output_returns_empty(self, parser: TscParser):
        output = "Starting compilation...\nFound 0 errors."
        assert parser.parse(output) == []

    def test_mixed_diagnostic_and_non_diagnostic(self, parser: TscParser):
        output = (
            "Starting compilation in watch mode...\n"
            "src/app.ts(10,5): error TS2304: Cannot find name 'foo'.\n"
            "Found 1 error."
        )
        errors = parser.parse(output)
        assert len(errors) == 1
        assert errors[0].message == "Cannot find name 'foo'."

    def test_column_one_based(self, parser: TscParser):
        output = "file.ts(1,1): error TS1005: ';' expected."
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].line == 1
        assert errors[0].column == 1


# ─── Format Method ───────────────────────────────────────────────────────────


class TestFormatMethod:
    """Test formatting CompilerError back to tsc-style output."""

    def test_format_simple_error(self, parser: TscParser):
        from infrastructure.analysis.universal_repo.models import CompilerError

        err = CompilerError(
            file_path="src/app.ts",
            line=10,
            column=5,
            severity="error",
            error_code="TS2304",
            message="Cannot find name 'foo'.",
            compiler="tsc",
        )
        result = parser.format(err)
        assert result == "src/app.ts(10,5): error TS2304: Cannot find name 'foo'."

    def test_format_warning(self, parser: TscParser):
        from infrastructure.analysis.universal_repo.models import CompilerError

        err = CompilerError(
            file_path="src/utils.ts",
            line=15,
            column=3,
            severity="warning",
            error_code="TS6133",
            message="'x' is declared but its value is never read.",
            compiler="tsc",
        )
        result = parser.format(err)
        assert result == "src/utils.ts(15,3): warning TS6133: 'x' is declared but its value is never read."

    def test_format_with_empty_error_code_uses_default(self, parser: TscParser):
        from infrastructure.analysis.universal_repo.models import CompilerError

        err = CompilerError(
            file_path="file.ts",
            line=1,
            column=1,
            severity="error",
            error_code="",
            message="some message",
            compiler="tsc",
        )
        result = parser.format(err)
        assert result == "file.ts(1,1): error TS0000: some message"


# ─── Round-Trip (Parse → Format → Parse) ─────────────────────────────────────


class TestRoundTrip:
    """Test that parse → format → parse produces equivalent results."""

    def test_round_trip_simple_error(self, parser: TscParser):
        original = "src/app.ts(10,5): error TS2304: Cannot find name 'foo'."
        errors = parser.parse(original)
        formatted = parser.format(errors[0])
        reparsed = parser.parse(formatted)

        assert len(reparsed) == 1
        assert reparsed[0].file_path == errors[0].file_path
        assert reparsed[0].line == errors[0].line
        assert reparsed[0].column == errors[0].column
        assert reparsed[0].severity == errors[0].severity
        assert reparsed[0].message == errors[0].message
        assert reparsed[0].error_code == errors[0].error_code

    def test_round_trip_warning(self, parser: TscParser):
        original = "src/utils.ts(15,3): warning TS6133: 'x' is declared but never read."
        errors = parser.parse(original)
        formatted = parser.format(errors[0])
        reparsed = parser.parse(formatted)

        assert len(reparsed) == 1
        assert reparsed[0].file_path == errors[0].file_path
        assert reparsed[0].severity == errors[0].severity
        assert reparsed[0].message == errors[0].message
        assert reparsed[0].error_code == errors[0].error_code

    def test_round_trip_type_mismatch(self, parser: TscParser):
        original = (
            "index.ts(3,14): error TS2345: Argument of type 'string' "
            "is not assignable to parameter of type 'number'."
        )
        errors = parser.parse(original)
        formatted = parser.format(errors[0])
        reparsed = parser.parse(formatted)

        assert len(reparsed) == 1
        assert reparsed[0].file_path == errors[0].file_path
        assert reparsed[0].line == errors[0].line
        assert reparsed[0].column == errors[0].column
        assert reparsed[0].error_code == errors[0].error_code
        assert reparsed[0].message == errors[0].message
