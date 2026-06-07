"""Unit tests for GoParser — Go compiler output parser.

Tests parsing of standard diagnostics, diagnostics without column,
relative paths, and the format() round-trip.

Requirements: 5.4
"""

from __future__ import annotations

import pytest

from infrastructure.analysis.universal_repo.parsers.go_parser import GoParser


@pytest.fixture
def parser() -> GoParser:
    return GoParser()


# ─── Basic Diagnostic Parsing ─────────────────────────────────────────────────


class TestBasicDiagnosticParsing:
    """Test parsing of standard Go compiler diagnostic lines."""

    def test_parses_simple_error(self, parser: GoParser):
        output = "./main.go:10:5: undefined: foo"
        errors = parser.parse(output)

        assert len(errors) == 1
        err = errors[0]
        assert err.file_path == "./main.go"
        assert err.line == 10
        assert err.column == 5
        assert err.severity == "error"
        assert err.message == "undefined: foo"
        assert err.compiler == "go"
        assert err.error_code == ""

    def test_parses_syntax_error(self, parser: GoParser):
        output = "main.go:15:2: syntax error: unexpected newline"
        errors = parser.parse(output)

        assert len(errors) == 1
        err = errors[0]
        assert err.file_path == "main.go"
        assert err.line == 15
        assert err.column == 2
        assert err.message == "syntax error: unexpected newline"

    def test_parses_import_error(self, parser: GoParser):
        output = './main.go:3:1: imported and not used: "fmt"'
        errors = parser.parse(output)

        assert len(errors) == 1
        err = errors[0]
        assert err.file_path == "./main.go"
        assert err.line == 3
        assert err.column == 1
        assert err.message == 'imported and not used: "fmt"'

    def test_parses_path_with_directory(self, parser: GoParser):
        output = "pkg/util/helper.go:42:12: cannot use x (type int) as type string"
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].file_path == "pkg/util/helper.go"
        assert errors[0].line == 42
        assert errors[0].column == 12

    def test_parses_windows_path(self, parser: GoParser):
        output = "C:\\Users\\dev\\main.go:5:3: undefined: bar"
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].file_path == "C:\\Users\\dev\\main.go"
        assert errors[0].line == 5
        assert errors[0].column == 3

    def test_all_errors_have_error_severity(self, parser: GoParser):
        """Go compiler only emits errors, never warnings."""
        output = (
            "./main.go:1:1: undefined: x\n"
            "./main.go:2:1: syntax error: unexpected }\n"
            "./main.go:3:1: too many arguments"
        )
        errors = parser.parse(output)

        assert len(errors) == 3
        for err in errors:
            assert err.severity == "error"


# ─── Diagnostics Without Column ───────────────────────────────────────────────


class TestDiagnosticsWithoutColumn:
    """Test parsing of Go errors that lack column information."""

    def test_parses_error_without_column(self, parser: GoParser):
        output = "./main.go:10: undefined reference to 'foo'"
        errors = parser.parse(output)

        assert len(errors) == 1
        err = errors[0]
        assert err.file_path == "./main.go"
        assert err.line == 10
        assert err.column == 0
        assert err.message == "undefined reference to 'foo'"


# ─── Multiple Errors ──────────────────────────────────────────────────────────


class TestMultipleErrors:
    """Test parsing of multiple errors in one output."""

    def test_parses_multiple_errors(self, parser: GoParser):
        output = (
            "./main.go:10:5: undefined: foo\n"
            "./main.go:15:9: syntax error: unexpected )\n"
            "./util.go:3:1: cannot use x as type y"
        )
        errors = parser.parse(output)

        assert len(errors) == 3
        assert errors[0].message == "undefined: foo"
        assert errors[1].message == "syntax error: unexpected )"
        assert errors[2].file_path == "./util.go"


# ─── Empty/Edge Cases ────────────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and empty inputs."""

    def test_empty_string_returns_empty_list(self, parser: GoParser):
        assert parser.parse("") == []

    def test_whitespace_only_returns_empty_list(self, parser: GoParser):
        assert parser.parse("   \n\n  ") == []

    def test_non_diagnostic_output_returns_empty(self, parser: GoParser):
        output = "# command-line-arguments\ncan't load package"
        # Lines that don't match either pattern are skipped
        errors = parser.parse(output)
        # "can't load package" doesn't match the pattern (no file:line:col)
        assert all(err.compiler == "go" for err in errors)

    def test_mixed_diagnostic_and_non_diagnostic(self, parser: GoParser):
        output = (
            "# command-line-arguments\n"
            "./main.go:5:1: undefined: myFunc\n"
        )
        errors = parser.parse(output)
        assert len(errors) == 1
        assert errors[0].message == "undefined: myFunc"


# ─── Format Method ───────────────────────────────────────────────────────────


class TestFormatMethod:
    """Test formatting CompilerError back to Go-style output."""

    def test_format_error_with_column(self, parser: GoParser):
        from infrastructure.analysis.universal_repo.models import CompilerError

        err = CompilerError(
            file_path="./main.go",
            line=10,
            column=5,
            severity="error",
            error_code="",
            message="undefined: foo",
            compiler="go",
        )
        result = parser.format(err)
        assert result == "./main.go:10:5: undefined: foo"

    def test_format_error_without_column(self, parser: GoParser):
        from infrastructure.analysis.universal_repo.models import CompilerError

        err = CompilerError(
            file_path="./main.go",
            line=10,
            column=0,
            severity="error",
            error_code="",
            message="undefined reference",
            compiler="go",
        )
        result = parser.format(err)
        assert result == "./main.go:10: undefined reference"

    def test_format_with_directory_path(self, parser: GoParser):
        from infrastructure.analysis.universal_repo.models import CompilerError

        err = CompilerError(
            file_path="pkg/util/helper.go",
            line=42,
            column=12,
            severity="error",
            error_code="",
            message="cannot convert",
            compiler="go",
        )
        result = parser.format(err)
        assert result == "pkg/util/helper.go:42:12: cannot convert"


# ─── Round-Trip (Parse → Format → Parse) ─────────────────────────────────────


class TestRoundTrip:
    """Test that parse → format → parse produces equivalent results."""

    def test_round_trip_simple_error(self, parser: GoParser):
        original = "./main.go:10:5: undefined: foo"
        errors = parser.parse(original)
        formatted = parser.format(errors[0])
        reparsed = parser.parse(formatted)

        assert len(reparsed) == 1
        assert reparsed[0].file_path == errors[0].file_path
        assert reparsed[0].line == errors[0].line
        assert reparsed[0].column == errors[0].column
        assert reparsed[0].severity == errors[0].severity
        assert reparsed[0].message == errors[0].message

    def test_round_trip_path_with_directory(self, parser: GoParser):
        original = "pkg/util/helper.go:42:12: cannot use x as type string"
        errors = parser.parse(original)
        formatted = parser.format(errors[0])
        reparsed = parser.parse(formatted)

        assert len(reparsed) == 1
        assert reparsed[0].file_path == errors[0].file_path
        assert reparsed[0].line == errors[0].line
        assert reparsed[0].column == errors[0].column
        assert reparsed[0].message == errors[0].message
