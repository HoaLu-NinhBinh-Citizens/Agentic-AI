"""Tests for LSP Diagnostics Integration."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.interfaces.tui.lsp_diagnostics import (
    LSPClient,
    LSPDiagnosticsRenderer,
    Diagnostic,
    DiagnosticSeverity,
    FileDiagnostics,
    DiagnosticAnnotation,
)


class TestLSPClient:
    """Test suite for LSPClient."""

    @pytest.fixture
    def lsp_client(self):
        """Create an LSP client for testing."""
        return LSPClient(workspace_root=Path("/test/workspace"))

    def test_is_supported_language(self, lsp_client):
        """Test language support detection."""
        assert lsp_client.is_supported(Path("script.py")) is True
        assert lsp_client.is_supported(Path("app.js")) is True
        assert lsp_client.is_supported(Path("main.ts")) is True
        assert lsp_client.is_supported(Path("file.rs")) is True

    def test_unsupported_language(self, lsp_client):
        """Test unsupported language detection."""
        assert lsp_client.is_supported(Path("file.xyz")) is False
        assert lsp_client.is_supported(Path("file")) is False

    def test_get_language_id(self, lsp_client):
        """Test language ID retrieval."""
        assert lsp_client.get_language_id(Path("script.py")) == "python"
        assert lsp_client.get_language_id(Path("app.js")) == "javascript"
        assert lsp_client.get_language_id(Path("app.tsx")) == "typescriptreact"
        assert lsp_client.get_language_id(Path("main.rs")) == "rust"

    @pytest.mark.asyncio
    async def test_get_diagnostics_unsupported_file(self, lsp_client):
        """Test diagnostics for unsupported file type."""
        diagnostics = await lsp_client.get_diagnostics(Path("file.xyz"))
        assert diagnostics is None

    @pytest.mark.asyncio
    async def test_get_diagnostics_python_file(self, lsp_client):
        """Test diagnostics for Python file."""
        with patch.object(lsp_client, '_run_pylint', return_value=[]):
            diagnostics = await lsp_client.get_diagnostics(Path("script.py"))

            assert diagnostics is not None
            assert diagnostics.language_id == "python"
            assert isinstance(diagnostics.diagnostics, list)

    def test_parse_pylint_line_valid(self, lsp_client):
        """Test parsing valid pylint output."""
        line = "/path/to/file.py:42:10: E0001: Syntax error"
        result = lsp_client._parse_pylint_line(line, "/path/to/file.py")

        assert result is not None
        assert result.range_start == 42
        assert result.severity == DiagnosticSeverity.ERROR

    def test_parse_pylint_line_invalid(self, lsp_client):
        """Test parsing invalid pylint output."""
        line = "This is not pylint output"
        result = lsp_client._parse_pylint_line(line, "/path/to/file.py")

        assert result is None


class TestDiagnosticSeverity:
    """Test DiagnosticSeverity enum."""

    def test_severity_values(self):
        """Test severity enum values."""
        assert DiagnosticSeverity.ERROR.value == 1
        assert DiagnosticSeverity.WARNING.value == 2
        assert DiagnosticSeverity.INFORMATION.value == 3
        assert DiagnosticSeverity.HINT.value == 4


class TestDiagnostic:
    """Test Diagnostic dataclass."""

    def test_diagnostic_creation(self):
        """Test Diagnostic instantiation."""
        diag = Diagnostic(
            range_start=10,
            range_end=10,
            severity=DiagnosticSeverity.ERROR,
            code="E001",
            message="Test error",
            source="test_linter",
        )

        assert diag.range_start == 10
        assert diag.severity == DiagnosticSeverity.ERROR
        assert diag.code == "E001"


class TestFileDiagnostics:
    """Test FileDiagnostics dataclass."""

    def test_file_diagnostics_creation(self):
        """Test FileDiagnostics instantiation."""
        diag = Diagnostic(
            range_start=1, range_end=1,
            severity=DiagnosticSeverity.WARNING,
            code="W001", message="Warning"
        )

        file_diag = FileDiagnostics(
            file_path="/test/script.py",
            diagnostics=[diag],
            language_id="python",
        )

        assert file_diag.file_path == "/test/script.py"
        assert len(file_diag.diagnostics) == 1
        assert file_diag.language_id == "python"


class TestLSPDiagnosticsRenderer:
    """Test suite for LSPDiagnosticsRenderer."""

    def test_render_annotations(self):
        """Test annotation rendering."""
        diagnostics = [
            Diagnostic(
                range_start=10,
                range_end=10,
                severity=DiagnosticSeverity.ERROR,
                code="E001",
                message="Missing import",
            ),
            Diagnostic(
                range_start=25,
                range_end=25,
                severity=DiagnosticSeverity.WARNING,
                code="W001",
                message="Unused variable",
            ),
        ]

        annotations = LSPDiagnosticsRenderer.render_annotations(diagnostics)

        assert len(annotations) == 2
        assert annotations[0].line == 10
        assert annotations[0].severity == DiagnosticSeverity.ERROR
        assert annotations[1].severity == DiagnosticSeverity.WARNING

    def test_format_annotation_error(self):
        """Test formatting error annotation."""
        annotation = DiagnosticAnnotation(
            line=10,
            column=0,
            end_column=50,
            severity=DiagnosticSeverity.ERROR,
            message="Test error message",
            code="E001",
        )

        formatted = LSPDiagnosticsRenderer.format_annotation(annotation)

        assert "ERROR" in formatted
        assert "Test error message" in formatted

    def test_format_annotation_warning(self):
        """Test formatting warning annotation."""
        annotation = DiagnosticAnnotation(
            line=20,
            column=5,
            end_column=30,
            severity=DiagnosticSeverity.WARNING,
            message="Test warning",
            code="W001",
        )

        formatted = LSPDiagnosticsRenderer.format_annotation(annotation)

        assert "WARN" in formatted

    def test_get_gutter_indicator_error(self):
        """Test gutter indicator for errors."""
        indicator = LSPDiagnosticsRenderer.get_gutter_indicator(DiagnosticSeverity.ERROR)
        assert "red" in indicator.lower()

    def test_get_gutter_indicator_warning(self):
        """Test gutter indicator for warnings."""
        indicator = LSPDiagnosticsRenderer.get_gutter_indicator(DiagnosticSeverity.WARNING)
        assert "yellow" in indicator.lower()

    def test_get_gutter_indicator_info(self):
        """Test gutter indicator for info."""
        indicator = LSPDiagnosticsRenderer.get_gutter_indicator(DiagnosticSeverity.INFORMATION)
        assert "blue" in indicator.lower()

    def test_get_gutter_indicator_hint(self):
        """Test gutter indicator for hints."""
        indicator = LSPDiagnosticsRenderer.get_gutter_indicator(DiagnosticSeverity.HINT)
        assert "dim" in indicator.lower()

    def test_severity_styles_mapping(self):
        """Test severity styles are properly mapped."""
        styles = LSPDiagnosticsRenderer.SEVERITY_STYLES

        assert DiagnosticSeverity.ERROR in styles
        assert DiagnosticSeverity.WARNING in styles
        assert DiagnosticSeverity.INFORMATION in styles
        assert DiagnosticSeverity.HINT in styles

        error_style = styles[DiagnosticSeverity.ERROR]
        assert "f38ba8" in error_style[0]  # Red color


class TestDiagnosticAnnotation:
    """Test DiagnosticAnnotation dataclass."""

    def test_annotation_creation(self):
        """Test DiagnosticAnnotation instantiation."""
        annotation = DiagnosticAnnotation(
            line=42,
            column=10,
            end_column=50,
            severity=DiagnosticSeverity.ERROR,
            message="Test annotation",
            code="TEST001",
        )

        assert annotation.line == 42
        assert annotation.column == 10
        assert annotation.end_column == 50
        assert annotation.severity == DiagnosticSeverity.ERROR
        assert annotation.message == "Test annotation"
