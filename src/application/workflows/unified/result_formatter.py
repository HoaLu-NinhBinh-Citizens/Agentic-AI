"""Result Formatter — output formatting for code review results.

Provides multiple output formats:
- MarkdownFormatter: Cursor-style markdown output
- JsonFormatter: Structured JSON output

Each formatter implements ResultFormatter interface.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.application.workflows.unified.detector_base import Finding, FindingSeverity

# ─── Pipeline Stats ─────────────────────────────────────────────────────────────


@dataclass
class PipelineStats:
    """Statistics for a pipeline run."""
    files_scanned: int = 0
    findings_count: int = 0
    errors_count: int = 0
    warnings_count: int = 0
    info_count: int = 0
    hints_count: int = 0
    execution_time_ms: float = 0.0
    detectors_used: list[str] = field(default_factory=list)
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "files_scanned": self.files_scanned,
            "findings_count": self.findings_count,
            "errors_count": self.errors_count,
            "warnings_count": self.warnings_count,
            "info_count": self.info_count,
            "hints_count": self.hints_count,
            "execution_time_ms": self.execution_time_ms,
            "detectors_used": self.detectors_used,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_findings(
        cls,
        findings: list[Finding],
        execution_time_ms: float = 0.0,
        detectors_used: list[str] | None = None,
        files_scanned: int | None = None,
    ) -> PipelineStats:
        """Create stats from findings list.

        Args:
            findings: List of findings
            execution_time_ms: Execution time in milliseconds
            detectors_used: List of detector names used
            files_scanned: Number of files actually scanned.
                          If provided, this takes precedence (recommended).
                          A clean file (no findings) still counts as scanned.
        """
        stats = cls(execution_time_ms=execution_time_ms)
        # FIX: Use passed files_scanned value if available
        # This ensures clean files are counted (not just files with findings)
        if files_scanned is not None:
            stats.files_scanned = files_scanned
        else:
            # Fallback: count unique files with findings (misses clean files!)
            # Prefer passing files_scanned explicitly from the engine
            stats.files_scanned = len(set(f.file for f in findings)) if findings else 0
        stats.findings_count = len(findings)
        stats.errors_count = sum(1 for f in findings if f.severity == FindingSeverity.ERROR)
        stats.warnings_count = sum(1 for f in findings if f.severity == FindingSeverity.WARNING)
        stats.info_count = sum(1 for f in findings if f.severity == FindingSeverity.INFO)
        stats.hints_count = sum(1 for f in findings if f.severity == FindingSeverity.HINT)
        stats.detectors_used = detectors_used or []
        return stats


# ─── Result Formatter Interface ─────────────────────────────────────────────────


class ResultFormatter(ABC):
    """Abstract base class for result formatters.

    Implement this interface to add new output formats.
    """

    @abstractmethod
    def format(
        self,
        findings: list[Finding],
        stats: PipelineStats,
        suggestions: list[dict[str, Any]] | None = None,
    ) -> str:
        """Format findings into output string.

        Args:
            findings: List of findings to format
            stats: Pipeline statistics
            suggestions: Optional fix suggestions

        Returns:
            Formatted output string
        """
        pass

    def _group_by_severity(
        self,
        findings: list[Finding],
    ) -> dict[FindingSeverity, list[Finding]]:
        """Group findings by severity."""
        groups: dict[FindingSeverity, list[Finding]] = {
            FindingSeverity.ERROR: [],
            FindingSeverity.WARNING: [],
            FindingSeverity.INFO: [],
            FindingSeverity.HINT: [],
        }
        for finding in findings:
            groups[finding.severity].append(finding)
        return groups

    def _group_by_file(
        self,
        findings: list[Finding],
    ) -> dict[str, list[Finding]]:
        """Group findings by file."""
        groups: dict[str, list[Finding]] = {}
        for finding in findings:
            if finding.file not in groups:
                groups[finding.file] = []
            groups[finding.file].append(finding)
        return groups

    def _format_severity_badge(self, severity: FindingSeverity) -> str:
        """Format severity as markdown badge."""
        badges = {
            FindingSeverity.ERROR: "🔴 ERROR",
            FindingSeverity.WARNING: "🟡 WARNING",
            FindingSeverity.INFO: "🔵 INFO",
            FindingSeverity.HINT: "⚪ HINT",
        }
        return badges.get(severity, str(severity.value))


# ─── Markdown Formatter ─────────────────────────────────────────────────────────


class MarkdownFormatter(ResultFormatter):
    """Cursor-style markdown output formatter.

    Produces a well-structured markdown report with:
    - Summary section
    - Top actionable fixes (sorted by severity)
    - Before/after code blocks where applicable
    - File-by-file breakdown
    """

    def __init__(self, include_stats: bool = True, max_findings_per_file: int = 20) -> None:
        """Initialize formatter.

        Args:
            include_stats: Include statistics section
            max_findings_per_file: Limit findings per file
        """
        self.include_stats = include_stats
        self.max_findings_per_file = max_findings_per_file

    def format(
        self,
        findings: list[Finding],
        stats: PipelineStats,
        suggestions: list[dict[str, Any]] | None = None,
    ) -> str:
        """Format findings as markdown.

        Args:
            findings: Findings to format
            stats: Pipeline statistics
            suggestions: Optional fix suggestions

        Returns:
            Markdown formatted string
        """
        lines: list[str] = []

        # Header
        lines.append("# Code Review Report")
        lines.append("")
        lines.append(f"Generated: {stats.timestamp}")
        lines.append("")

        # Summary
        if self.include_stats:
            lines.extend(self._format_summary(stats))
            lines.append("")

        # Top actionable fixes (errors and warnings, sorted by confidence)
        top_findings = self._get_top_findings(findings)
        if top_findings:
            lines.extend(self._format_top_fixes(top_findings))
            lines.append("")

        # Group by file for detailed breakdown
        by_file = self._group_by_file(findings)
        if by_file:
            lines.extend(self._format_file_breakdown(by_file))
            lines.append("")

        # Fix suggestions if available
        if suggestions:
            lines.extend(self._format_suggestions(suggestions))

        return "\n".join(lines)

    def _format_summary(self, stats: PipelineStats) -> list[str]:
        """Format summary statistics."""
        lines: list[str] = []

        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Files Scanned | {stats.files_scanned} |")
        lines.append(f"| Total Findings | {stats.findings_count} |")
        lines.append(f"| 🔴 Errors | {stats.errors_count} |")
        lines.append(f"| 🟡 Warnings | {stats.warnings_count} |")
        lines.append(f"| 🔵 Info | {stats.info_count} |")
        lines.append(f"| ⚪ Hints | {stats.hints_count} |")
        lines.append(f"| Execution Time | {stats.execution_time_ms:.0f}ms |")

        if stats.detectors_used:
            lines.append(f"| Detectors | {', '.join(stats.detectors_used)} |")

        return lines

    def _get_top_findings(self, findings: list[Finding]) -> list[Finding]:
        """Get top actionable findings (errors and warnings, high confidence)."""
        actionable = [
            f for f in findings
            if f.severity in (FindingSeverity.ERROR, FindingSeverity.WARNING)
            and f.confidence >= 0.7
        ]
        # Sort by severity, then confidence, then line number
        actionable.sort(
            key=lambda f: (
                -f.severity.to_numeric(),
                -f.confidence,
                f.line,
            )
        )
        return actionable[:10]  # Top 10

    def _format_top_fixes(self, findings: list[Finding]) -> list[str]:
        """Format top actionable fixes section."""
        lines: list[str] = []

        lines.append("## Top Actionable Fixes")
        lines.append("")
        lines.append("These issues should be addressed first:")
        lines.append("")

        for i, finding in enumerate(findings, 1):
            lines.append(f"### {i}. {self._format_severity_badge(finding.severity)} {finding.rule_name}")
            lines.append("")
            lines.append(f"**File:** `{finding.file}:{finding.line}`")
            lines.append("")

            # Get old_code and new_code from metadata (for ML detector)
            old_code = finding.metadata.get("old_code", "")
            new_code = finding.metadata.get("new_code", "")

            # Show code with before/after if available
            if old_code or new_code:
                if old_code:
                    lines.append("**Before (problematic code):**")
                    lines.append("```python")
                    lines.append(f"")
                    lines.append(old_code)
                    lines.append("```")
                    lines.append("")
                if new_code:
                    lines.append("**After (suggested fix):**")
                    lines.append("```python")
                    lines.append("")
                    lines.append(new_code)
                    lines.append("```")
                    lines.append("")
            elif finding.context:
                # Fallback to context
                lines.append("**Code:**")
                lines.append("```")
                lines.append(finding.context)
                lines.append("```")
                lines.append("")

            lines.append(f"**Message:** {finding.message}")
            lines.append("")

            if finding.fix:
                lines.append(f"**Suggested Fix:** {finding.fix}")
                lines.append("")

            # Show explanation if available (for ML detector)
            if finding.metadata.get("explanation"):
                lines.append(f"**Explanation:** {finding.metadata['explanation']}")
                lines.append("")

            if finding.metadata.get("cwe"):
                lines.append(f"**CWE:** [{finding.metadata['cwe']}](https://cwe.mitre.org/data/definitions/{finding.metadata['cwe'].replace('CWE-', '')}.html)")
                lines.append("")

            lines.append("---")
            lines.append("")

        return lines

    def _format_file_breakdown(
        self,
        by_file: dict[str, list[Finding]],
    ) -> list[str]:
        """Format file-by-file breakdown."""
        lines: list[str] = []

        lines.append("## Detailed Findings by File")
        lines.append("")

        for file_path, file_findings in sorted(by_file.items()):
            # Format file header
            rel_path = self._get_relative_path(file_path)
            lines.append(f"### 📄 `{rel_path}`")
            lines.append("")

            # Group by severity
            by_severity = self._group_by_severity(file_findings)

            # Show errors first, then warnings, etc.
            severity_order = [
                FindingSeverity.ERROR,
                FindingSeverity.WARNING,
                FindingSeverity.INFO,
                FindingSeverity.HINT,
            ]

            shown = 0
            for severity in severity_order:
                severity_findings = by_severity.get(severity, [])
                for finding in severity_findings:
                    if shown >= self.max_findings_per_file:
                        remaining = len(file_findings) - shown
                        if remaining > 0:
                            lines.append(f"_... and {remaining} more findings_")
                        break

                    lines.append(f"- {self._format_severity_badge(finding.severity)} ")
                    lines.append(f"  Line {finding.line}: [{finding.rule_name}] {finding.message[:80]}")

                    if finding.fix:
                        lines.append(f"  - Fix: {finding.fix[:60]}")

                    shown += 1

            lines.append("")

        return lines

    def _format_suggestions(self, suggestions: list[dict[str, Any]]) -> list[str]:
        """Format fix suggestions."""
        lines: list[str] = []

        lines.append("## Fix Suggestions")
        lines.append("")

        for i, suggestion in enumerate(suggestions[:10], 1):
            lines.append(f"### {i}. {suggestion.get('title', 'Suggestion')}")
            lines.append("")
            lines.append(f"{suggestion.get('description', '')}")
            lines.append("")

            if suggestion.get("code_before") or suggestion.get("code_after"):
                lines.append("**Before:**")
                lines.append("```")
                lines.append(suggestion.get("code_before", ""))
                lines.append("```")
                lines.append("")
                lines.append("**After:**")
                lines.append("```")
                lines.append(suggestion.get("code_after", ""))
                lines.append("```")
                lines.append("")

            if suggestion.get("risk"):
                lines.append(f"**Risk Level:** {suggestion['risk']}")
                lines.append("")

            lines.append("---")
            lines.append("")

        return lines

    def _get_relative_path(self, file_path: str) -> str:
        """Convert absolute path to relative for display."""
        try:
            return str(Path(file_path).relative_to(Path.cwd()))
        except ValueError:
            return file_path


# ─── JSON Formatter ─────────────────────────────────────────────────────────────


class JsonFormatter(ResultFormatter):
    """Structured JSON output formatter.

    Produces machine-readable JSON output for integration with other tools.
    """

    def __init__(self, pretty: bool = True) -> None:
        """Initialize formatter.

        Args:
            pretty: Use pretty printing (indent=2)
        """
        self.pretty = pretty

    def format(
        self,
        findings: list[Finding],
        stats: PipelineStats,
        suggestions: list[dict[str, Any]] | None = None,
    ) -> str:
        """Format findings as JSON.

        Args:
            findings: Findings to format
            stats: Pipeline statistics
            suggestions: Optional fix suggestions

        Returns:
            JSON formatted string
        """
        output = {
            "report": {
                "generated_at": stats.timestamp,
                "stats": stats.to_dict(),
            },
            "findings": [
                {
                    "rule_id": f.rule_id,
                    "rule_name": f.rule_name,
                    "severity": f.severity.value,
                    "file": f.file,
                    "line": f.line,
                    "end_line": f.end_line,
                    "column": f.column,
                    "message": f.message,
                    "fix": f.fix,
                    "confidence": f.confidence,
                    "detector": f.detector,
                    "metadata": f.metadata,
                }
                for f in findings
            ],
        }

        if suggestions:
            output["suggestions"] = suggestions

        if self.pretty:
            return json.dumps(output, indent=2)
        return json.dumps(output)


# ─── Console Formatter ─────────────────────────────────────────────────────────


class ConsoleFormatter(ResultFormatter):
    """Simple console output formatter.

    Produces colored, compact console output.
    """

    SEVERITY_COLORS = {
        FindingSeverity.ERROR: "\033[91m",    # Red
        FindingSeverity.WARNING: "\033[93m",  # Yellow
        FindingSeverity.INFO: "\033[94m",     # Blue
        FindingSeverity.HINT: "\033[90m",    # Gray
    }
    RESET = "\033[0m"

    def __init__(self, use_colors: bool = True) -> None:
        """Initialize formatter.

        Args:
            use_colors: Use ANSI color codes
        """
        self.use_colors = use_colors

    def format(
        self,
        findings: list[Finding],
        stats: PipelineStats,
        suggestions: list[dict[str, Any]] | None = None,
    ) -> str:
        """Format findings for console.

        Args:
            findings: Findings to format
            stats: Pipeline statistics
            suggestions: Optional fix suggestions

        Returns:
            Console formatted string
        """
        lines: list[str] = []

        # Summary
        lines.append(self._color("=== Code Review Summary ===", FindingSeverity.INFO))
        lines.append(f"Files: {stats.files_scanned}, ")
        lines.append(f"Findings: {stats.findings_count} ")
        lines.append(f"(🔴 {stats.errors_count} errors, ")
        lines.append(f"🟡 {stats.warnings_count} warnings)")
        lines.append("")

        # Group by severity
        by_severity = self._group_by_severity(findings)

        # Show errors first
        for severity in [FindingSeverity.ERROR, FindingSeverity.WARNING]:
            findings_list = by_severity.get(severity, [])
            if not findings_list:
                continue

            lines.append(self._color(f"--- {severity.value.upper()}S ---", severity))
            for f in findings_list[:15]:
                lines.append(f"  {self._color('●', severity)} {f.file}:{f.line} [{f.rule_name}]")
            if len(findings_list) > 15:
                lines.append(f"  ... and {len(findings_list) - 15} more")
            lines.append("")

        return "\n".join(lines)

    def _color(self, text: str, severity: FindingSeverity) -> str:
        """Apply color to text if colors enabled."""
        if not self.use_colors:
            return text
        color = self.SEVERITY_COLORS.get(severity, "")
        return f"{color}{text}{self.RESET}"


# ─── Factory ────────────────────────────────────────────────────────────────────


def get_formatter(format_type: str) -> ResultFormatter:
    """Get formatter by name.

    Args:
        format_type: Formatter type ("markdown", "json", "console")

    Returns:
        Formatter instance
    """
    formatters = {
        "markdown": MarkdownFormatter,
        "json": JsonFormatter,
        "console": ConsoleFormatter,
    }

    formatter_class = formatters.get(format_type.lower(), MarkdownFormatter)
    return formatter_class()
