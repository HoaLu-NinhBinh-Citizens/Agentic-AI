"""Cursor-style markdown report generator for AI_SUPPORT."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Severity(Enum):
    """Finding severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class Finding:
    """A code review finding."""

    rule_id: str
    title: str
    severity: Severity
    file_path: str
    line: int
    message: str
    description: str = ""
    old_code: str = ""
    new_code: str = ""
    confidence: float = 1.0
    fixable: bool = True
    auto_fixable: bool = False
    risk_level: str = "MEDIUM"


@dataclass
class PipelineStats:
    """Pipeline execution statistics."""

    files_analyzed: int = 0
    duration_seconds: float = 0.0
    total_findings: int = 0
    findings_by_severity: dict[Severity, int] = field(default_factory=dict)


class MarkdownReportGenerator:
    """Generate Cursor-style markdown reports for code review output."""

    _EMOJI_MAP = {
        Severity.CRITICAL: "🔴",
        Severity.HIGH: "🟠",
        Severity.MEDIUM: "🟡",
        Severity.LOW: "🔵",
        Severity.INFO: "⚪",
    }

    def __init__(self, project_name: str = "Project", version: str = "1.0.0"):
        self.project_name = project_name
        self.version = version

    def generate(
        self,
        findings: list[Finding],
        stats: PipelineStats,
        recommendations: Optional[list[str]] = None,
    ) -> str:
        """Generate complete markdown report."""
        by_severity = self._group_by_severity(findings)
        by_file = self._group_by_file(findings)
        top3 = self._get_top_3_actionable(findings)

        sections = [
            self._build_header(stats),
            self._build_summary(by_severity),
            self._build_top_3(top3),
            self._build_detailed_findings(by_file),
            self._build_statistics(stats, findings),
            self._build_recommendations(recommendations or []),
            self._build_footer(),
        ]
        return "\n".join(sections)

    def _group_by_severity(
        self, findings: list[Finding]
    ) -> dict[Severity, list[Finding]]:
        groups: dict[Severity, list[Finding]] = {s: [] for s in Severity}
        for f in findings:
            groups[f.severity].append(f)
        return groups

    def _group_by_file(self, findings: list[Finding]) -> dict[str, list[Finding]]:
        groups: dict[str, list[Finding]] = {}
        for f in findings:
            groups.setdefault(f.file_path, []).append(f)
        return groups

    def _get_top_3_actionable(self, findings: list[Finding]) -> list[Finding]:
        """Get top 3 most important fixable findings."""
        fixable = [f for f in findings if f.fixable]
        severity_order = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2}
        sorted_findings = sorted(
            fixable,
            key=lambda f: (severity_order.get(f.severity, 99), -f.confidence),
        )
        return sorted_findings[:3]

    def _severity_emoji(self, severity: Severity) -> str:
        return self._EMOJI_MAP.get(severity, "⚪")

    def _build_header(self, stats: PipelineStats) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"""# 🔍 AI_SUPPORT Code Review

**Project:** {self.project_name}  
**Files analyzed:** {stats.files_analyzed}  
**Duration:** {stats.duration_seconds:.2f}s  
**Timestamp:** {timestamp}
"""

    def _build_summary(self, by_severity: dict[Severity, list[Finding]]) -> str:
        lines = ["## Summary\n", "| Severity | Count | Issues |", "|----------|-------|--------|"]
        for severity in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]:
            findings = by_severity.get(severity, [])
            if findings:
                emoji = self._severity_emoji(severity)
                issue_list = ", ".join(sorted(set(f.rule_id for f in findings[:5])))
                if len(findings) > 5:
                    issue_list += f" (+{len(findings) - 5} more)"
                lines.append(f"| {emoji} {severity.value.upper()} | {len(findings)} | {issue_list} |")
        return "\n".join(lines) + "\n\n"

    def _build_top_3(self, top3: list[Finding]) -> str:
        if not top3:
            return ""

        lines = ["## Top 3 Actionable Fixes\n"]
        for i, finding in enumerate(top3, 1):
            lines.append(f"### {i}. {self._severity_emoji(finding.severity)} [{finding.rule_id}] {finding.title}")
            lines.append(f"**File:** `{finding.file_path}` (line {finding.line})")
            lines.append(f"**Confidence:** {int(finding.confidence * 100)}%")
            lines.append(f"\n{finding.description}\n")

            # Extract old_code/new_code from metadata first (unified Finding),
            # then fall back to direct attributes (legacy Finding)
            old_code = getattr(finding, 'metadata', {}).get('old_code') or getattr(finding, 'old_code', '')
            new_code = getattr(finding, 'metadata', {}).get('new_code') or getattr(finding, 'new_code', '')

            if old_code:
                lines.append("```python")
                lines.append("# ❌ BEFORE")
                lines.append(old_code)
                lines.append("```\n")

            if new_code:
                lines.append("```python")
                lines.append("# ✅ AFTER")
                lines.append(new_code)
                lines.append("```\n")

            lines.append(f"**Risk Level:** {finding.risk_level}")
            lines.append(f"**Command:** `/fix @{finding.file_path}:{finding.line}`")
            lines.append("\n---\n")

        return "\n".join(lines)

    def _build_detailed_findings(self, by_file: dict[str, list[Finding]]) -> str:
        if not by_file:
            return ""

        lines = ["## Detailed Findings by File\n"]
        for file_path, findings in sorted(by_file.items()):
            lines.append(f"### 📄 {file_path}")

            by_sev = self._group_by_severity(findings)
            summary = ", ".join(
                f"{self._severity_emoji(s)}{len(by_sev.get(s, []))}"
                for s in Severity if by_sev.get(s)
            )
            lines.append(f"**{summary}**\n")

            lines.append("| Line | Rule | Severity | Message |")
            lines.append("|------|------|----------|---------|")
            for f in findings:
                msg = f.message[:50] + "..." if len(f.message) > 50 else f.message
                lines.append(f"| {f.line} | {f.rule_id} | {self._severity_emoji(f.severity)} | {msg} |")
            lines.append("")

            for f in findings:
                lines.append(f"#### [{f.rule_id}] {f.title}")
                lines.append(f"{f.description}\n")
                # Extract old_code/new_code from metadata first
                old_code = getattr(f, 'metadata', {}).get('old_code') or getattr(f, 'old_code', '')
                new_code = getattr(f, 'metadata', {}).get('new_code') or getattr(f, 'new_code', '')
                if old_code:
                    lines.append("```python")
                    lines.append("# ❌ BEFORE")
                    lines.append(old_code)
                    lines.append("```")
                if new_code:
                    lines.append("```python")
                    lines.append("# ✅ AFTER")
                    lines.append(new_code)
                    lines.append("```")
                lines.append("")

        return "\n".join(lines)

    def _build_statistics(self, stats: PipelineStats, findings: list[Finding]) -> str:
        fixable = sum(1 for f in findings if f.fixable)
        auto_fixable = sum(1 for f in findings if f.auto_fixable)
        manual = fixable - auto_fixable

        return f"""## Statistics

- **Total findings:** {len(findings)}
- **Fixable:** {fixable}
- **Auto-fixable:** {auto_fixable}
- **Requires manual review:** {manual}

"""

    def _build_recommendations(self, recommendations: list[str]) -> str:
        if not recommendations:
            return ""
        lines = ["## Recommendations\n"]
        for i, rec in enumerate(recommendations, 1):
            lines.append(f"{i}. {rec}")
        return "\n".join(lines) + "\n\n"

    def _build_footer(self) -> str:
        return f"---\n*Generated by AI_SUPPORT v{self.version}*\n"
