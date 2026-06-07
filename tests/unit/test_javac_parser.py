"""Unit tests for JavacParser — Java compiler (javac) output parser.

Tests parsing of standard error/warning diagnostics, caret context,
column extraction from caret position, and the format() round-trip.

Requirements: 5.5
"""

from __future__ import annotations

import pytest

from infrastructure.analysis.universal_repo.parsers.javac_parser import JavacParser


@pytest.fixture
def parser() -> JavacParser:
    return JavacParser()


# ─── Basic Diagnostic Parsing ─────────────────────────────────────────────────


class TestBasicDiagnosticParsing:
    """Test parsing of standard javac diagnostic lines."""

    def test_parses_simple_error(self, parser: JavacParser):
        output = "Main.java:10: error: cannot find symbol"
        errors = parser.parse(output)

        assert len(errors) == 1
        err = errors[0]
        assert err.file_path == "Main.java"
        assert err.line == 10
        assert err.severity == "error"
        assert err.message == "cannot find symbol"
        assert err.compiler == "javac"
        assert err.error_code == ""

    def test_parses_warning(self, parser: JavacParser):
        output = "Util.java:25: warning: [unchecked] unchecked conversion"
        errors = parser.parse(output)

        assert len(errors) == 1
        err = errors[0]
        assert err.file_path == "Util.java"
        assert err.line == 25
        assert err.severity == "warning"
        assert err.message == "[unchecked] unchecked conversion"

    def test_parses_path_with_directory(self, parser: JavacParser):
        output = "src/com/example/App.java:42: error: method does not override"
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].file_path == "src/com/example/App.java"
        assert errors[0].line == 42

    def test_parses_windows_path(self, parser: JavacParser):
        output = "C:\\Users\\dev\\Main.java:5: error: ';' expected"
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].file_path == "C:\\Users\\dev\\Main.java"
        assert errors[0].line == 5
        assert errors[0].message == "';' expected"


# ─── Caret Context ────────────────────────────────────────────────────────────


class TestCaretContext:
    """Test handling of source line and caret (^) context."""

    def test_captures_caret_context(self, parser: JavacParser):
        output = (
            "Main.java:10: error: cannot find symbol\n"
            "        System.out.println(foo);\n"
            "                          ^"
        )
        errors = parser.parse(output)

        assert len(errors) == 1
        assert "System.out.println(foo);" in errors[0].raw_output
        assert "^" in errors[0].raw_output

    def test_extracts_column_from_caret(self, parser: JavacParser):
        output = (
            "Main.java:10: error: cannot find symbol\n"
            "        int x = foo;\n"
            "                ^"
        )
        errors = parser.parse(output)

        assert len(errors) == 1
        # Caret is at position 16 (0-indexed), so column is 17 (1-indexed)
        assert errors[0].column == 17

    def test_no_caret_gives_default_column(self, parser: JavacParser):
        output = "Main.java:10: error: cannot find symbol"
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].column == 0

    def test_context_stops_at_next_diagnostic(self, parser: JavacParser):
        output = (
            "Main.java:10: error: first error\n"
            "    code line\n"
            "    ^\n"
            "Main.java:15: error: second error"
        )
        errors = parser.parse(output)

        assert len(errors) == 2
        assert "code line" in errors[0].raw_output
        assert errors[1].file_path == "Main.java"
        assert errors[1].line == 15
        assert errors[1].raw_output == ""


# ─── Multiple Errors ──────────────────────────────────────────────────────────


class TestMultipleErrors:
    """Test parsing of multiple errors in one output."""

    def test_parses_multiple_errors(self, parser: JavacParser):
        output = (
            "Main.java:10: error: cannot find symbol\n"
            "Main.java:15: warning: [deprecation] method is deprecated\n"
            "Util.java:3: error: incompatible types"
        )
        errors = parser.parse(output)

        assert len(errors) == 3
        assert errors[0].severity == "error"
        assert errors[1].severity == "warning"
        assert errors[2].file_path == "Util.java"

    def test_parses_errors_with_interleaved_context(self, parser: JavacParser):
        output = (
            "Main.java:10: error: cannot find symbol\n"
            "        System.out.println(foo);\n"
            "                          ^\n"
            "Main.java:20: error: incompatible types\n"
            "        int x = \"hello\";\n"
            "                ^"
        )
        errors = parser.parse(output)

        assert len(errors) == 2
        assert errors[0].line == 10
        assert "foo" in errors[0].raw_output
        assert errors[1].line == 20
        assert '"hello"' in errors[1].raw_output


# ─── Empty/Edge Cases ────────────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and empty inputs."""

    def test_empty_string_returns_empty_list(self, parser: JavacParser):
        assert parser.parse("") == []

    def test_whitespace_only_returns_empty_list(self, parser: JavacParser):
        assert parser.parse("   \n\n  ") == []

    def test_non_diagnostic_output_returns_empty(self, parser: JavacParser):
        output = "Note: Some input files use unchecked operations.\n1 error"
        assert parser.parse(output) == []

    def test_mixed_diagnostic_and_non_diagnostic(self, parser: JavacParser):
        output = (
            "Note: Recompile with -Xlint:unchecked\n"
            "Main.java:5: error: unreported exception\n"
            "1 error\n"
        )
        errors = parser.parse(output)
        assert len(errors) == 1
        assert errors[0].message == "unreported exception"


# ─── Format Method ───────────────────────────────────────────────────────────


class TestFormatMethod:
    """Test formatting CompilerError back to javac-style output."""

    def test_format_simple_error(self, parser: JavacParser):
        from infrastructure.analysis.universal_repo.models import CompilerError

        err = CompilerError(
            file_path="Main.java",
            line=10,
            column=0,
            severity="error",
            error_code="",
            message="cannot find symbol",
            compiler="javac",
        )
        result = parser.format(err)
        assert result == "Main.java:10: error: cannot find symbol"

    def test_format_warning(self, parser: JavacParser):
        from infrastructure.analysis.universal_repo.models import CompilerError

        err = CompilerError(
            file_path="Util.java",
            line=25,
            column=0,
            severity="warning",
            error_code="",
            message="[unchecked] unchecked conversion",
            compiler="javac",
        )
        result = parser.format(err)
        assert result == "Util.java:25: warning: [unchecked] unchecked conversion"

    def test_format_includes_raw_output(self, parser: JavacParser):
        from infrastructure.analysis.universal_repo.models import CompilerError

        err = CompilerError(
            file_path="Main.java",
            line=10,
            column=17,
            severity="error",
            error_code="",
            message="cannot find symbol",
            compiler="javac",
            raw_output="        int x = foo;\n                ^",
        )
        result = parser.format(err)
        assert "Main.java:10: error: cannot find symbol" in result
        assert "        int x = foo;" in result
        assert "                ^" in result


# ─── Round-Trip (Parse → Format → Parse) ─────────────────────────────────────


class TestRoundTrip:
    """Test that parse → format → parse produces equivalent results."""

    def test_round_trip_simple_error(self, parser: JavacParser):
        original = "Main.java:10: error: cannot find symbol"
        errors = parser.parse(original)
        formatted = parser.format(errors[0])
        reparsed = parser.parse(formatted)

        assert len(reparsed) == 1
        assert reparsed[0].file_path == errors[0].file_path
        assert reparsed[0].line == errors[0].line
        assert reparsed[0].severity == errors[0].severity
        assert reparsed[0].message == errors[0].message

    def test_round_trip_warning(self, parser: JavacParser):
        original = "Util.java:25: warning: deprecated method"
        errors = parser.parse(original)
        formatted = parser.format(errors[0])
        reparsed = parser.parse(formatted)

        assert len(reparsed) == 1
        assert reparsed[0].file_path == errors[0].file_path
        assert reparsed[0].severity == errors[0].severity
        assert reparsed[0].message == errors[0].message

    def test_round_trip_with_context(self, parser: JavacParser):
        original = (
            "Main.java:10: error: cannot find symbol\n"
            "        int x = foo;\n"
            "                ^"
        )
        errors = parser.parse(original)
        formatted = parser.format(errors[0])
        reparsed = parser.parse(formatted)

        assert len(reparsed) == 1
        assert reparsed[0].file_path == errors[0].file_path
        assert reparsed[0].line == errors[0].line
        assert reparsed[0].severity == errors[0].severity
        assert reparsed[0].message == errors[0].message
        assert reparsed[0].column == errors[0].column
