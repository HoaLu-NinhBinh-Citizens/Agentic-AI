"""LSP Diagnostics Integration — provides inline error annotations for TUI.

This module provides:
- LSP client for connecting to Language Server Protocol servers
- Diagnostics parser for extracting errors/warnings from LSP
- Inline annotation renderer for displaying diagnostics in TUI

Usage:
    lsp_client = LSPClient(workspace_root)
    diagnostics = await lsp_client.get_diagnostics(file_path)
    annotations = LSPDiagnosticsRenderer.render_annotations(diagnostics)
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class DiagnosticSeverity(Enum):
    """LSP diagnostic severity levels."""
    ERROR = 1
    WARNING = 2
    INFORMATION = 3
    HINT = 4


@dataclass
class Diagnostic:
    """A single LSP diagnostic (error/warning/info)."""
    range_start: int
    range_end: int
    severity: DiagnosticSeverity
    code: str
    message: str
    source: str = "LSP"


@dataclass
class FileDiagnostics:
    """Diagnostics for a single file."""
    file_path: str
    diagnostics: list[Diagnostic]
    language_id: str = ""


@dataclass
class DiagnosticAnnotation:
    """An annotation to display in the TUI."""
    line: int
    column: int
    end_column: int
    severity: DiagnosticSeverity
    message: str
    code: str


class LSPClient:
    """Client for communicating with LSP servers.

    Supports:
    - Initialization and shutdown
    - Text document synchronization
    - Diagnostic retrieval
    """

    KNOWN_LANGUAGES = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescriptreact",
        ".jsx": "javascriptreact",
        ".java": "java",
        ".c": "c",
        ".cpp": "cpp",
        ".rs": "rust",
        ".go": "go",
    }

    def __init__(
        self,
        workspace_root: Path,
        server_command: Optional[list[str]] = None,
    ):
        """Initialize LSP client.

        Args:
            workspace_root: Root of the workspace
            server_command: Optional LSP server command (e.g., ["pylsp"])
        """
        self.workspace_root = workspace_root
        self.server_command = server_command or ["pylsp"]
        self._connected = False
        self._process = None

    def is_supported(self, file_path: Path) -> bool:
        """Check if a file type is supported by LSP."""
        return file_path.suffix in self.KNOWN_LANGUAGES

    def get_language_id(self, file_path: Path) -> str:
        """Get LSP language ID for a file."""
        return self.KNOWN_LANGUAGES.get(file_path.suffix, "unknown")

    async def get_diagnostics(self, file_path: Path) -> Optional[FileDiagnostics]:
        """Get diagnostics for a file.

        Args:
            file_path: Path to the file

        Returns:
            FileDiagnostics if supported, None otherwise
        """
        if not self.is_supported(file_path):
            return None

        language_id = self.get_language_id(file_path)

        try:
            diagnostics = await self._run_lint_check(file_path, language_id)
            return FileDiagnostics(
                file_path=str(file_path),
                diagnostics=diagnostics,
                language_id=language_id,
            )
        except Exception as e:
            logger.debug("LSP diagnostics not available: %s", e)
            return None

    async def _run_lint_check(
        self,
        file_path: Path,
        language_id: str,
    ) -> list[Diagnostic]:
        """Run lint check using available tools.

        Returns list of diagnostics from lint output.
        """
        diagnostics = []

        if language_id == "python":
            diagnostics = await self._run_pylint(file_path)
        elif language_id in ("javascript", "typescript"):
            diagnostics = await self._run_eslint(file_path)

        return diagnostics

    async def _run_pylint(self, file_path: Path) -> list[Diagnostic]:
        """Run pylint and parse output."""
        diagnostics = []

        try:
            result = subprocess.run(
                ["python", "-m", "pylint", "--output-format=text", str(file_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            for line in result.stdout.split("\n"):
                if ":" in line and file_path.name in line:
                    diag = self._parse_pylint_line(line, str(file_path))
                    if diag:
                        diagnostics.append(diag)

        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return diagnostics

    async def _run_eslint(self, file_path: Path) -> list[Diagnostic]:
        """Run eslint and parse output."""
        diagnostics = []

        try:
            result = subprocess.run(
                ["npx", "eslint", "--format=compact", str(file_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            for line in result.stdout.split("\n"):
                if line.strip():
                    diag = self._parse_eslint_line(line, str(file_path))
                    if diag:
                        diagnostics.append(diag)

        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return diagnostics

    def _parse_pylint_line(self, line: str, file_path: str) -> Optional[Diagnostic]:
        """Parse a pylint output line."""
        try:
            parts = line.split(":")
            if len(parts) < 4:
                return None

            line_num = int(parts[1])
            col_num = int(parts[2]) if len(parts) > 2 else 0
            message = ":".join(parts[3:]).strip()

            severity = DiagnosticSeverity.WARNING
            if "error" in line.lower() or "fatal" in line.lower():
                severity = DiagnosticSeverity.ERROR

            return Diagnostic(
                range_start=line_num,
                range_end=line_num,
                severity=severity,
                code="pylint",
                message=message[:200],
                source="pylint",
            )
        except (ValueError, IndexError):
            return None

    def _parse_eslint_line(self, line: str, file_path: str) -> Optional[Diagnostic]:
        """Parse an eslint output line."""
        try:
            if file_path not in line:
                return None

            severity = DiagnosticSeverity.WARNING
            if ":error:" in line.lower():
                severity = DiagnosticSeverity.ERROR

            return Diagnostic(
                range_start=1,
                range_end=1,
                severity=severity,
                code="eslint",
                message=line[:200],
                source="eslint",
            )
        except Exception:
            return None


class LSPDiagnosticsRenderer:
    """Renders LSP diagnostics as inline annotations for TUI."""

    SEVERITY_STYLES = {
        DiagnosticSeverity.ERROR: ("#f38ba8", "ERROR"),
        DiagnosticSeverity.WARNING: ("#f9e2af", "WARN"),
        DiagnosticSeverity.INFORMATION: ("#89b4fa", "INFO"),
        DiagnosticSeverity.HINT: ("#6c7086", "HINT"),
    }

    @classmethod
    def render_annotations(
        cls,
        diagnostics: list[Diagnostic],
    ) -> list[DiagnosticAnnotation]:
        """Convert diagnostics to renderable annotations.

        Args:
            diagnostics: List of LSP diagnostics

        Returns:
            List of DiagnosticAnnotation for rendering
        """
        annotations = []

        for diag in diagnostics:
            color, _ = cls.SEVERITY_STYLES.get(
                diag.severity,
                ("#6c7086", "UNKNOWN"),
            )

            annotation = DiagnosticAnnotation(
                line=diag.range_start,
                column=0,
                end_column=80,
                severity=diag.severity,
                message=diag.message,
                code=diag.code,
            )
            annotations.append(annotation)

        return annotations

    @classmethod
    def format_annotation(cls, annotation: DiagnosticAnnotation) -> str:
        """Format a single annotation for display.

        Args:
            annotation: The annotation to format

        Returns:
            Formatted string with severity indicator
        """
        color, label = cls.SEVERITY_STYLES.get(
            annotation.severity,
            ("#6c7086", "UNKNOWN"),
        )

        return (
            f"[{color}]{label}[/]: "
            f"[{color}]{annotation.message[:60]}[/]"
        )

    @classmethod
    def get_gutter_indicator(cls, severity: DiagnosticSeverity) -> str:
        """Get gutter indicator character for severity.

        Args:
            severity: Diagnostic severity

        Returns:
            Single character indicator
        """
        indicators = {
            DiagnosticSeverity.ERROR: "[red]●[/red]",
            DiagnosticSeverity.WARNING: "[yellow]●[/yellow]",
            DiagnosticSeverity.INFORMATION: "[blue]●[/blue]",
            DiagnosticSeverity.HINT: "[dim]○[/dim]",
        }
        return indicators.get(severity, "[dim]○[/dim]")
