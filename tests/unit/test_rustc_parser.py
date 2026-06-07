"""Unit tests for RustcParser.

Tests parsing of rustc compiler output including error codes,
multi-line spans, suggestion blocks, warnings, and formatting.

Requirements: 5.3
"""

from __future__ import annotations

from src.infrastructure.analysis.universal_repo.parsers import RustcParser


class TestRustcParserParse:
    """Tests for RustcParser.parse() method."""

    def setup_method(self) -> None:
        self.parser = RustcParser()

    def test_empty_output_returns_empty_list(self) -> None:
        assert self.parser.parse("") == []
        assert self.parser.parse("   ") == []

    def test_error_with_code_and_location(self) -> None:
        output = (
            "error[E0308]: mismatched types\n"
            " --> src/main.rs:10:5\n"
            "  |\n"
            '10 |     let x: u32 = "hello";\n'
            "  |                  ^^^^^^^ expected `u32`, found `&str`\n"
        )
        errors = self.parser.parse(output)
        assert len(errors) == 1
        e = errors[0]
        assert e.error_code == "E0308"
        assert e.severity == "error"
        assert e.message == "mismatched types"
        assert e.file_path == "src/main.rs"
        assert e.line == 10
        assert e.column == 5
        assert e.compiler == "rustc"

    def test_error_without_code(self) -> None:
        output = "error: could not compile `myproject`\n"
        errors = self.parser.parse(output)
        assert len(errors) == 1
        e = errors[0]
        assert e.error_code == ""
        assert e.severity == "error"
        assert e.message == "could not compile `myproject`"
        assert e.file_path == ""
        assert e.line == 0
        assert e.column == 0

    def test_warning_with_location(self) -> None:
        output = (
            "warning: unused variable `x`\n"
            " --> src/lib.rs:5:9\n"
            "  |\n"
            "5 |     let x = 42;\n"
            "  |         ^\n"
        )
        errors = self.parser.parse(output)
        assert len(errors) == 1
        e = errors[0]
        assert e.severity == "warning"
        assert e.file_path == "src/lib.rs"
        assert e.line == 5
        assert e.column == 9

    def test_suggestion_with_equals_help(self) -> None:
        output = (
            "error[E0308]: mismatched types\n"
            " --> src/main.rs:10:5\n"
            "  |\n"
            "  = help: try using a conversion method\n"
        )
        errors = self.parser.parse(output)
        assert len(errors) == 1
        assert len(errors[0].suggestions) == 1
        assert "conversion method" in errors[0].suggestions[0]

    def test_suggestion_with_help_prefix(self) -> None:
        output = (
            "error[E0425]: cannot find value `foo` in this scope\n"
            " --> src/main.rs:3:5\n"
            "  |\n"
            "3 |     foo;\n"
            "  |     ^^^\n"
            "  |\n"
            "  help: consider importing this function\n"
        )
        errors = self.parser.parse(output)
        assert len(errors) == 1
        assert len(errors[0].suggestions) == 1
        assert "consider importing" in errors[0].suggestions[0]

    def test_multiple_errors(self) -> None:
        output = (
            "error[E0425]: cannot find value `foo` in this scope\n"
            " --> src/main.rs:3:5\n"
            "  |\n"
            "3 |     foo;\n"
            "  |     ^^^ not found in this scope\n"
            "error[E0308]: mismatched types\n"
            " --> src/main.rs:7:14\n"
            "  |\n"
            "7 |     let x: i32 = true;\n"
            "  |                  ^^^^ expected `i32`, found `bool`\n"
        )
        errors = self.parser.parse(output)
        assert len(errors) == 2
        assert errors[0].error_code == "E0425"
        assert errors[0].file_path == "src/main.rs"
        assert errors[0].line == 3
        assert errors[1].error_code == "E0308"
        assert errors[1].file_path == "src/main.rs"
        assert errors[1].line == 7

    def test_multiple_suggestions(self) -> None:
        output = (
            "error[E0308]: mismatched types\n"
            " --> src/main.rs:10:5\n"
            "  |\n"
            "  = help: consider using `.into()`\n"
            "  = help: or try using `as` for primitive casting\n"
        )
        errors = self.parser.parse(output)
        assert len(errors) == 1
        assert len(errors[0].suggestions) == 2
        assert ".into()" in errors[0].suggestions[0]
        assert "`as`" in errors[0].suggestions[1]

    def test_raw_output_captures_context(self) -> None:
        output = (
            "error[E0308]: mismatched types\n"
            " --> src/main.rs:10:5\n"
            "  |\n"
            '10 |     let x: u32 = "hello";\n'
            "  |                  ^^^^^^^ expected `u32`, found `&str`\n"
        )
        errors = self.parser.parse(output)
        assert len(errors) == 1
        assert errors[0].raw_output != ""
        assert "src/main.rs:10:5" in errors[0].raw_output

    def test_windows_paths(self) -> None:
        output = (
            "error[E0308]: mismatched types\n"
            " --> C:\\Users\\dev\\project\\src\\main.rs:10:5\n"
        )
        errors = self.parser.parse(output)
        assert len(errors) == 1
        assert errors[0].file_path == "C:\\Users\\dev\\project\\src\\main.rs"


class TestRustcParserFormat:
    """Tests for RustcParser.format() method."""

    def setup_method(self) -> None:
        self.parser = RustcParser()

    def test_format_error_with_code(self) -> None:
        from src.infrastructure.analysis.universal_repo.models import CompilerError

        error = CompilerError(
            file_path="src/main.rs",
            line=10,
            column=5,
            severity="error",
            error_code="E0308",
            message="mismatched types",
            compiler="rustc",
        )
        formatted = self.parser.format(error)
        assert "error[E0308]: mismatched types" in formatted
        assert " --> src/main.rs:10:5" in formatted

    def test_format_error_without_code(self) -> None:
        from src.infrastructure.analysis.universal_repo.models import CompilerError

        error = CompilerError(
            file_path="",
            line=0,
            column=0,
            severity="error",
            error_code="",
            message="could not compile `myproject`",
            compiler="rustc",
        )
        formatted = self.parser.format(error)
        assert "error: could not compile `myproject`" in formatted
        assert "-->" not in formatted

    def test_format_warning_with_code(self) -> None:
        from src.infrastructure.analysis.universal_repo.models import CompilerError

        error = CompilerError(
            file_path="src/lib.rs",
            line=5,
            column=9,
            severity="warning",
            error_code="",
            message="unused variable `x`",
            compiler="rustc",
        )
        formatted = self.parser.format(error)
        assert "warning: unused variable `x`" in formatted
        assert " --> src/lib.rs:5:9" in formatted

    def test_format_includes_raw_output(self) -> None:
        from src.infrastructure.analysis.universal_repo.models import CompilerError

        error = CompilerError(
            file_path="src/main.rs",
            line=10,
            column=5,
            severity="error",
            error_code="E0308",
            message="mismatched types",
            compiler="rustc",
            raw_output="  |\n10 |     let x = foo;\n  |             ^^^",
        )
        formatted = self.parser.format(error)
        assert "let x = foo;" in formatted
        assert "^^^" in formatted
