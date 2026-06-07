"""Unit tests for GccParser — GCC/G++/Clang output parser.

Tests parsing of standard diagnostics, linker errors, error codes,
multi-line context, and the format() round-trip.

Requirements: 5.1
"""

from __future__ import annotations

import pytest

from infrastructure.analysis.universal_repo.parsers.gcc_parser import GccParser


@pytest.fixture
def parser() -> GccParser:
    return GccParser()


# ─── Basic Diagnostic Parsing ─────────────────────────────────────────────────


class TestBasicDiagnosticParsing:
    """Test parsing of standard gcc/clang diagnostic lines."""

    def test_parses_simple_error(self, parser: GccParser):
        output = "main.c:10:5: error: use of undeclared identifier 'foo'"
        errors = parser.parse(output)

        assert len(errors) == 1
        err = errors[0]
        assert err.file_path == "main.c"
        assert err.line == 10
        assert err.column == 5
        assert err.severity == "error"
        assert err.message == "use of undeclared identifier 'foo'"
        assert err.compiler == "gcc"
        assert err.error_code == ""

    def test_parses_warning_with_error_code(self, parser: GccParser):
        output = "src/util.c:25:1: warning: unused variable 'x' [-Wunused-variable]"
        errors = parser.parse(output)

        assert len(errors) == 1
        err = errors[0]
        assert err.file_path == "src/util.c"
        assert err.line == 25
        assert err.column == 1
        assert err.severity == "warning"
        assert err.message == "unused variable 'x'"
        assert err.error_code == "-Wunused-variable"
        assert err.compiler == "gcc"

    def test_parses_note_severity(self, parser: GccParser):
        output = "header.h:3:10: note: 'foo' declared here"
        errors = parser.parse(output)

        assert len(errors) == 1
        err = errors[0]
        assert err.severity == "note"
        assert err.message == "'foo' declared here"

    def test_parses_path_with_directory(self, parser: GccParser):
        output = "/home/user/project/src/lib/math.cpp:42:12: error: no matching function"
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].file_path == "/home/user/project/src/lib/math.cpp"
        assert errors[0].line == 42
        assert errors[0].column == 12

    def test_parses_windows_path(self, parser: GccParser):
        output = "C:\\Users\\dev\\src\\main.c:5:3: error: expected ';'"
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].file_path == "C:\\Users\\dev\\src\\main.c"
        assert errors[0].line == 5
        assert errors[0].column == 3


# ─── Multiple Errors ──────────────────────────────────────────────────────────


class TestMultipleErrors:
    """Test parsing of multiple errors in one output."""

    def test_parses_multiple_errors(self, parser: GccParser):
        output = (
            "main.c:10:5: error: use of undeclared identifier 'foo'\n"
            "main.c:15:9: warning: comparison of integers [-Wsign-compare]\n"
            "util.c:3:1: error: expected ';' after expression"
        )
        errors = parser.parse(output)

        assert len(errors) == 3
        assert errors[0].severity == "error"
        assert errors[1].severity == "warning"
        assert errors[1].error_code == "-Wsign-compare"
        assert errors[2].file_path == "util.c"


# ─── Linker Errors ───────────────────────────────────────────────────────────


class TestLinkerErrors:
    """Test parsing of linker-style errors without file location."""

    def test_parses_linker_error(self, parser: GccParser):
        output = "error: linker command failed with exit code 1"
        errors = parser.parse(output)

        assert len(errors) == 1
        err = errors[0]
        assert err.file_path == ""
        assert err.line == 0
        assert err.column == 0
        assert err.severity == "error"
        assert err.message == "linker command failed with exit code 1"
        assert err.compiler == "gcc"

    def test_parses_linker_warning(self, parser: GccParser):
        output = "warning: duplicate symbol '_main'"
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].severity == "warning"
        assert errors[0].message == "duplicate symbol '_main'"


# ─── Multi-line Context ───────────────────────────────────────────────────────


class TestMultilineContext:
    """Test handling of multi-line error context (source snippets, carets)."""

    def test_captures_caret_context(self, parser: GccParser):
        output = (
            "main.c:10:5: error: use of undeclared identifier 'foo'\n"
            "    int x = foo;\n"
            "            ^~~"
        )
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].raw_output == "    int x = foo;\n            ^~~"

    def test_captures_multi_line_context(self, parser: GccParser):
        output = (
            "test.c:20:3: error: expected expression\n"
            "    if (x ==) {\n"
            "           ^"
        )
        errors = parser.parse(output)

        assert len(errors) == 1
        assert "if (x ==)" in errors[0].raw_output
        assert "^" in errors[0].raw_output

    def test_context_stops_at_next_diagnostic(self, parser: GccParser):
        output = (
            "a.c:1:1: error: first error\n"
            "    code line\n"
            "    ^\n"
            "b.c:2:2: error: second error"
        )
        errors = parser.parse(output)

        assert len(errors) == 2
        assert "code line" in errors[0].raw_output
        assert errors[1].file_path == "b.c"
        assert errors[1].raw_output == ""


# ─── Empty/Edge Cases ────────────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and empty inputs."""

    def test_empty_string_returns_empty_list(self, parser: GccParser):
        assert parser.parse("") == []

    def test_whitespace_only_returns_empty_list(self, parser: GccParser):
        assert parser.parse("   \n\n  ") == []

    def test_non_diagnostic_output_returns_empty(self, parser: GccParser):
        output = "Building target main.o...\nCompilation complete."
        assert parser.parse(output) == []

    def test_mixed_diagnostic_and_non_diagnostic(self, parser: GccParser):
        output = (
            "Building project...\n"
            "main.c:5:1: error: unknown type name 'foo'\n"
            "Build failed."
        )
        errors = parser.parse(output)
        assert len(errors) == 1
        assert errors[0].message == "unknown type name 'foo'"


# ─── Format Method ───────────────────────────────────────────────────────────


class TestFormatMethod:
    """Test formatting CompilerError back to gcc-style output."""

    def test_format_simple_error(self, parser: GccParser):
        from infrastructure.analysis.universal_repo.models import CompilerError

        err = CompilerError(
            file_path="main.c",
            line=10,
            column=5,
            severity="error",
            error_code="",
            message="use of undeclared identifier 'foo'",
            compiler="gcc",
        )
        result = parser.format(err)
        assert result == "main.c:10:5: error: use of undeclared identifier 'foo'"

    def test_format_warning_with_error_code(self, parser: GccParser):
        from infrastructure.analysis.universal_repo.models import CompilerError

        err = CompilerError(
            file_path="src/util.c",
            line=25,
            column=1,
            severity="warning",
            error_code="-Wunused-variable",
            message="unused variable 'x'",
            compiler="gcc",
        )
        result = parser.format(err)
        assert result == "src/util.c:25:1: warning: unused variable 'x' [-Wunused-variable]"

    def test_format_linker_error(self, parser: GccParser):
        from infrastructure.analysis.universal_repo.models import CompilerError

        err = CompilerError(
            file_path="",
            line=0,
            column=0,
            severity="error",
            error_code="",
            message="linker command failed",
            compiler="gcc",
        )
        result = parser.format(err)
        assert result == "error: linker command failed"

    def test_format_includes_raw_output(self, parser: GccParser):
        from infrastructure.analysis.universal_repo.models import CompilerError

        err = CompilerError(
            file_path="test.c",
            line=5,
            column=3,
            severity="error",
            error_code="",
            message="expected expression",
            compiler="gcc",
            raw_output="    if (x ==) {\n           ^",
        )
        result = parser.format(err)
        assert "test.c:5:3: error: expected expression" in result
        assert "    if (x ==) {" in result
        assert "           ^" in result


# ─── Round-Trip (Parse → Format → Parse) ─────────────────────────────────────


class TestRoundTrip:
    """Test that parse → format → parse produces equivalent results."""

    def test_round_trip_simple_error(self, parser: GccParser):
        original = "main.c:10:5: error: use of undeclared identifier 'foo'"
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

    def test_round_trip_warning_with_code(self, parser: GccParser):
        original = "src/util.c:25:1: warning: unused variable 'x' [-Wunused-variable]"
        errors = parser.parse(original)
        formatted = parser.format(errors[0])
        reparsed = parser.parse(formatted)

        assert len(reparsed) == 1
        assert reparsed[0].file_path == errors[0].file_path
        assert reparsed[0].severity == errors[0].severity
        assert reparsed[0].message == errors[0].message
        assert reparsed[0].error_code == errors[0].error_code

    def test_round_trip_linker_error(self, parser: GccParser):
        original = "error: linker command failed with exit code 1"
        errors = parser.parse(original)
        formatted = parser.format(errors[0])
        reparsed = parser.parse(formatted)

        assert len(reparsed) == 1
        assert reparsed[0].message == errors[0].message
        assert reparsed[0].severity == errors[0].severity
