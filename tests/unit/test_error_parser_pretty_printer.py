"""Unit tests for ErrorParser pretty-printer formatting through the facade.

Verifies that ErrorParser.format() correctly delegates to each registered
parser and that the round-trip property (parse → format → parse) holds
across all 5 supported compiler styles via the factory function.

Requirements: 8.1, 8.2, 8.3
"""

from __future__ import annotations

import pytest

from infrastructure.analysis.universal_repo.error_parser import (
    ErrorParser,
    create_error_parser,
)
from infrastructure.analysis.universal_repo.models import CompilerError


# ─── Factory / Default Registration ──────────────────────────────────────────


class TestCreateErrorParser:
    """Test the factory function and create_default classmethod."""

    def test_create_error_parser_returns_instance(self):
        ep = create_error_parser()
        assert isinstance(ep, ErrorParser)

    def test_create_default_registers_all_compilers(self):
        ep = ErrorParser.create_default()
        supported = ep.get_supported_compilers()
        assert "gcc" in supported
        assert "tsc" in supported
        assert "rustc" in supported
        assert "go" in supported
        assert "javac" in supported

    def test_create_error_parser_equivalent_to_create_default(self):
        ep1 = create_error_parser()
        ep2 = ErrorParser.create_default()
        assert ep1.get_supported_compilers() == ep2.get_supported_compilers()


# ─── Format Delegation ────────────────────────────────────────────────────────


class TestFormatDelegation:
    """Test that ErrorParser.format() delegates correctly to each parser."""

    @pytest.fixture
    def ep(self) -> ErrorParser:
        return create_error_parser()

    def test_format_gcc_style(self, ep: ErrorParser):
        err = CompilerError(
            file_path="main.c",
            line=10,
            column=5,
            severity="error",
            error_code="",
            message="undeclared identifier 'foo'",
            compiler="gcc",
        )
        result = ep.format(err, "gcc")
        assert "main.c:10:5: error: undeclared identifier 'foo'" in result

    def test_format_tsc_style(self, ep: ErrorParser):
        err = CompilerError(
            file_path="app.ts",
            line=3,
            column=14,
            severity="error",
            error_code="TS2345",
            message="Argument of type 'string' is not assignable.",
            compiler="tsc",
        )
        result = ep.format(err, "tsc")
        assert result == "app.ts(3,14): error TS2345: Argument of type 'string' is not assignable."

    def test_format_rustc_style(self, ep: ErrorParser):
        err = CompilerError(
            file_path="src/main.rs",
            line=10,
            column=5,
            severity="error",
            error_code="E0308",
            message="mismatched types",
            compiler="rustc",
        )
        result = ep.format(err, "rustc")
        assert "error[E0308]: mismatched types" in result
        assert "--> src/main.rs:10:5" in result

    def test_format_go_style(self, ep: ErrorParser):
        err = CompilerError(
            file_path="./main.go",
            line=10,
            column=5,
            severity="error",
            error_code="",
            message="undefined: foo",
            compiler="go",
        )
        result = ep.format(err, "go")
        assert result == "./main.go:10:5: undefined: foo"

    def test_format_javac_style(self, ep: ErrorParser):
        err = CompilerError(
            file_path="Main.java",
            line=10,
            column=0,
            severity="error",
            error_code="",
            message="cannot find symbol",
            compiler="javac",
        )
        result = ep.format(err, "javac")
        assert "Main.java:10: error: cannot find symbol" in result

    def test_format_unregistered_style_raises(self, ep: ErrorParser):
        err = CompilerError(
            file_path="test.c",
            line=1,
            column=1,
            severity="error",
            error_code="",
            message="test",
            compiler="gcc",
        )
        with pytest.raises(ValueError, match="No parser registered for style 'unknown'"):
            ep.format(err, "unknown")


# ─── Round-Trip Through Facade ────────────────────────────────────────────────


class TestRoundTripFacade:
    """Test parse → format → parse equivalence through ErrorParser facade."""

    @pytest.fixture
    def ep(self) -> ErrorParser:
        return create_error_parser()

    def test_round_trip_gcc(self, ep: ErrorParser):
        original = "main.c:10:5: error: use of undeclared identifier 'foo'"
        errors = ep.parse(original, "gcc")
        formatted = ep.format(errors[0], "gcc")
        reparsed = ep.parse(formatted, "gcc")

        assert len(reparsed) == 1
        assert reparsed[0].file_path == errors[0].file_path
        assert reparsed[0].line == errors[0].line
        assert reparsed[0].column == errors[0].column
        assert reparsed[0].severity == errors[0].severity
        assert reparsed[0].message == errors[0].message
        assert reparsed[0].error_code == errors[0].error_code

    def test_round_trip_gcc_with_error_code(self, ep: ErrorParser):
        original = "src/util.c:25:1: warning: unused variable 'x' [-Wunused-variable]"
        errors = ep.parse(original, "gcc")
        formatted = ep.format(errors[0], "gcc")
        reparsed = ep.parse(formatted, "gcc")

        assert len(reparsed) == 1
        assert reparsed[0].file_path == errors[0].file_path
        assert reparsed[0].severity == errors[0].severity
        assert reparsed[0].message == errors[0].message
        assert reparsed[0].error_code == errors[0].error_code

    def test_round_trip_tsc(self, ep: ErrorParser):
        original = "src/app.ts(10,5): error TS2304: Cannot find name 'foo'."
        errors = ep.parse(original, "tsc")
        formatted = ep.format(errors[0], "tsc")
        reparsed = ep.parse(formatted, "tsc")

        assert len(reparsed) == 1
        assert reparsed[0].file_path == errors[0].file_path
        assert reparsed[0].line == errors[0].line
        assert reparsed[0].column == errors[0].column
        assert reparsed[0].severity == errors[0].severity
        assert reparsed[0].message == errors[0].message
        assert reparsed[0].error_code == errors[0].error_code

    def test_round_trip_rustc(self, ep: ErrorParser):
        original = (
            "error[E0308]: mismatched types\n"
            " --> src/main.rs:10:5"
        )
        errors = ep.parse(original, "rustc")
        formatted = ep.format(errors[0], "rustc")
        reparsed = ep.parse(formatted, "rustc")

        assert len(reparsed) == 1
        assert reparsed[0].file_path == errors[0].file_path
        assert reparsed[0].line == errors[0].line
        assert reparsed[0].column == errors[0].column
        assert reparsed[0].severity == errors[0].severity
        assert reparsed[0].message == errors[0].message
        assert reparsed[0].error_code == errors[0].error_code

    def test_round_trip_go(self, ep: ErrorParser):
        original = "./main.go:10:5: undefined: foo"
        errors = ep.parse(original, "go")
        formatted = ep.format(errors[0], "go")
        reparsed = ep.parse(formatted, "go")

        assert len(reparsed) == 1
        assert reparsed[0].file_path == errors[0].file_path
        assert reparsed[0].line == errors[0].line
        assert reparsed[0].column == errors[0].column
        assert reparsed[0].message == errors[0].message

    def test_round_trip_javac(self, ep: ErrorParser):
        original = "Main.java:10: error: cannot find symbol"
        errors = ep.parse(original, "javac")
        formatted = ep.format(errors[0], "javac")
        reparsed = ep.parse(formatted, "javac")

        assert len(reparsed) == 1
        assert reparsed[0].file_path == errors[0].file_path
        assert reparsed[0].line == errors[0].line
        assert reparsed[0].severity == errors[0].severity
        assert reparsed[0].message == errors[0].message

    def test_round_trip_rustc_without_code(self, ep: ErrorParser):
        original = "error: could not compile `myproject`"
        errors = ep.parse(original, "rustc")
        formatted = ep.format(errors[0], "rustc")
        reparsed = ep.parse(formatted, "rustc")

        assert len(reparsed) == 1
        assert reparsed[0].severity == errors[0].severity
        assert reparsed[0].message == errors[0].message
        assert reparsed[0].error_code == errors[0].error_code

    def test_round_trip_go_no_column(self, ep: ErrorParser):
        original = "./main.go:15: syntax error"
        errors = ep.parse(original, "go")
        formatted = ep.format(errors[0], "go")
        reparsed = ep.parse(formatted, "go")

        assert len(reparsed) == 1
        assert reparsed[0].file_path == errors[0].file_path
        assert reparsed[0].line == errors[0].line
        assert reparsed[0].message == errors[0].message
