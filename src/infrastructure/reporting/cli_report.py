"""CLI-friendly report generator for terminal output."""

from typing import Optional

from src.infrastructure.reporting.markdown_report import (
    Finding,
    PipelineStats,
    Severity,
)


class CLIReportGenerator:
    """Generate concise CLI output with box-style formatting."""

    _severity_icons = {
        Severity.CRITICAL: "[CRIT]",
        Severity.HIGH: "[HIGH]",
        Severity.MEDIUM: "[MED ]",
        Severity.LOW: "[LOW ]",
        Severity.INFO: "[INFO]",
    }

    _severity_colors = {
        Severity.CRITICAL: "\033[91m",
        Severity.HIGH: "\033[93m",
        Severity.MEDIUM: "\033[33m",
        Severity.LOW: "\033[94m",
        Severity.INFO: "\033[90m",
    }
    _reset = "\033[0m"

    def __init__(self, use_colors: bool = True):
        self.use_colors = use_colors

    def generate(
        self,
        findings: list[Finding],
        stats: PipelineStats,
        max_width: int = 80,
    ) -> str:
        """Generate CLI-friendly report."""
        lines = []

        lines.append(self._build_header(stats))
        lines.append(self._build_summary(findings))
        lines.append(self._build_top_3(findings))
        lines.append(self._build_findings(findings, max_width))
        lines.append(self._build_footer(stats))

        return "\n".join(lines)

    def _color(self, severity: Severity, text: str) -> str:
        if not self.use_colors:
            return text
        color = self._severity_colors.get(severity, "")
        return f"{color}{text}{self._reset}"

    def _build_header(self, stats: PipelineStats) -> str:
        width = 60
        border = "═" * width
        return f"""
╔{border}╗
║{" AI_SUPPORT Code Review".ljust(width)}║
╠{border}╣
║ Files: {str(stats.files_analyzed).ljust(12)} Duration: {f"{stats.duration_seconds:.2f}s".ljust(14)}║
╚{border}╝
"""

    def _build_summary(self, findings: list[Finding]) -> str:
        if not findings:
            return "\n✓ No issues found.\n"

        by_severity: dict[Severity, list[Finding]] = {s: [] for s in Severity}
        for f in findings:
            by_severity[f.severity].append(f)

        lines = ["\n─── Summary ───"]
        for severity in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]:
            count = len(by_severity[severity])
            if count > 0:
                icon = self._severity_icons[severity]
                lines.append(f"  {icon} {severity.value.upper():8} : {count}")
        return "\n".join(lines) + "\n"

    def _build_top_3(self, findings: list[Finding]) -> str:
        fixable = [f for f in findings if f.fixable]
        severity_order = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2}
        sorted_findings = sorted(
            fixable,
            key=lambda f: (severity_order.get(f.severity, 99), -f.confidence),
        )
        top3 = sorted_findings[:3]

        if not top3:
            return ""

        lines = ["\n─── Top 3 Fixes ───"]
        for i, f in enumerate(top3, 1):
            icon = self._severity_icons[f.severity]
            severity_label = self._color(f.severity, icon)
            lines.append(f"  {i}. {severity_label} {f.title}")
            lines.append(f"     → {f.file_path}:{f.line}")
            lines.append(f"     → /fix @{f.file_path}:{f.line}")
        return "\n".join(lines) + "\n"

    def _build_findings(self, findings: list[Finding], max_width: int) -> str:
        if not findings:
            return ""

        by_file: dict[str, list[Finding]] = {}
        for f in findings:
            by_file.setdefault(f.file_path, []).append(f)

        lines = ["\n─── Findings by File ───"]
        for file_path, file_findings in sorted(by_file.items()):
            lines.append(f"\n  📄 {file_path}")
            for f in file_findings:
                icon = self._severity_icons[f.severity]
                msg = f.message[:max_width - 30] + "..." if len(f.message) > max_width - 30 else f.message
                lines.append(f"    {icon} L{f.line:4} {msg}")
        return "\n".join(lines) + "\n"

    def _build_footer(self, stats: PipelineStats) -> str:
        total = len(stats.findings_by_severity)
        return f"""
─── Statistics ───
  Total findings: {total}
  Files analyzed: {stats.files_analyzed}
  Duration: {stats.duration_seconds:.2f}s
"""
