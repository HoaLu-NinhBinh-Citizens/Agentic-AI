"""Unified Result Formatter — output formatting for code review results using ReviewIssue.

Provides multiple output formats:
- UnifiedMarkdownFormatter: Cursor-style markdown output using ReviewIssue
- UnifiedJsonFormatter: Structured JSON output using ReviewIssue

Each formatter implements UnifiedFormatter interface and consumes ReviewIssue objects.

Usage:
    from src.application.workflows.unified.result_formatter import UnifiedMarkdownFormatter
    
    formatter = UnifiedMarkdownFormatter()
    report = formatter.format(issues, stats)
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.domain.models.review_issue import ReviewIssue, Severity, FixOption


@dataclass
class UnifiedPipelineStats:
    """Statistics for a pipeline run using unified ReviewIssue."""
    
    files_scanned: int = 0
    total_issues: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    info_count: int = 0
    
    execution_time_ms: float = 0.0
    detectors_used: list[str] = field(default_factory=list)
    issues_by_file: dict[str, int] = field(default_factory=dict)
    
    timestamp: str = ""
    
    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "files_scanned": self.files_scanned,
            "total_issues": self.total_issues,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "info_count": self.info_count,
            "execution_time_ms": self.execution_time_ms,
            "detectors_used": self.detectors_used,
            "issues_by_file": self.issues_by_file,
            "timestamp": self.timestamp,
        }
    
    @classmethod
    def from_issues(
        cls,
        issues: list[ReviewIssue],
        execution_time_ms: float = 0.0,
        detectors_used: Optional[list[str]] = None,
        files_scanned: int = 0,
    ) -> UnifiedPipelineStats:
        """Create stats from ReviewIssue list.
        
        Args:
            issues: List of ReviewIssue objects
            execution_time_ms: Execution time in milliseconds
            detectors_used: List of detector names used
            files_scanned: Number of files scanned
        """
        stats = cls(
            execution_time_ms=execution_time_ms,
            detectors_used=detectors_used or [],
            files_scanned=files_scanned,
        )
        
        stats.total_issues = len(issues)
        
        # Count by severity
        severity_counts = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 0,
            Severity.MEDIUM: 0,
            Severity.LOW: 0,
            Severity.INFO: 0,
        }
        
        for issue in issues:
            severity_counts[issue.severity] = severity_counts.get(issue.severity, 0) + 1
            
            # Count by file
            stats.issues_by_file[issue.file] = stats.issues_by_file.get(issue.file, 0) + 1
        
        stats.critical_count = severity_counts[Severity.CRITICAL]
        stats.high_count = severity_counts[Severity.HIGH]
        stats.medium_count = severity_counts[Severity.MEDIUM]
        stats.low_count = severity_counts[Severity.LOW]
        stats.info_count = severity_counts[Severity.INFO]
        
        return stats

    @classmethod
    def from_findings(
        cls,
        findings: list,
        execution_time_ms: float = 0.0,
        detectors_used: Optional[list[str]] = None,
        files_scanned: int = 0,
    ) -> UnifiedPipelineStats:
        """Create stats from legacy Finding list (backward compatibility).

        Args:
            findings: List of legacy Finding objects (detector_base Finding)
            execution_time_ms: Execution time in milliseconds
            detectors_used: List of detector names used
            files_scanned: Number of files scanned
        """
        from src.application.workflows.unified.detector_base import FindingSeverity

        stats = cls(
            execution_time_ms=execution_time_ms,
            detectors_used=detectors_used or [],
            files_scanned=files_scanned,
        )

        stats.total_issues = len(findings)

        severity_counts = {
            FindingSeverity.ERROR: 0,
            FindingSeverity.WARNING: 0,
            FindingSeverity.INFO: 0,
            FindingSeverity.HINT: 0,
        }

        for finding in findings:
            sev = finding.severity
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            stats.issues_by_file[finding.file] = stats.issues_by_file.get(finding.file, 0) + 1

        stats.critical_count = severity_counts[FindingSeverity.ERROR]
        stats.high_count = severity_counts[FindingSeverity.WARNING]
        stats.info_count = severity_counts[FindingSeverity.INFO]

        return stats

    @property
    def findings_count(self) -> int:
        """Alias for total_issues (backward compatibility)."""
        return self.total_issues

    @property
    def errors_count(self) -> int:
        """Alias for critical_count (backward compatibility)."""
        return self.critical_count


class UnifiedFormatter(ABC):
    """Abstract base class for unified result formatters.
    
    Implement this interface to add new output formats.
    """
    
    @abstractmethod
    def format(
        self,
        issues: list[ReviewIssue],
        stats: Optional[UnifiedPipelineStats] = None,
    ) -> str:
        """Format issues into output string.
        
        Args:
            issues: List of ReviewIssue to format
            stats: Optional pipeline statistics
            
        Returns:
            Formatted output string
        """
        pass
    
    def _group_by_severity(
        self,
        issues: list[ReviewIssue],
    ) -> dict[str, list[ReviewIssue]]:
        """Group issues by severity."""
        groups: dict[str, list[ReviewIssue]] = {
            "CRITICAL": [],
            "HIGH": [],
            "MEDIUM": [],
            "LOW": [],
            "INFO": [],
        }
        for issue in issues:
            sev_key = str(issue.severity).upper()
            if sev_key not in groups:
                sev_key = issue.severity.value if hasattr(issue.severity, 'value') else str(issue.severity)
            groups.setdefault(sev_key, []).append(issue)
        return groups
    
    def _group_by_file(
        self,
        issues: list[ReviewIssue],
    ) -> dict[str, list[ReviewIssue]]:
        """Group issues by file."""
        groups: dict[str, list[ReviewIssue]] = {}
        for issue in issues:
            if issue.file not in groups:
                groups[issue.file] = []
            groups[issue.file].append(issue)
        return groups
    
    def _format_severity_badge(self, severity: Severity) -> str:
        """Format severity as markdown badge."""
        badges = {
            Severity.CRITICAL: "🔴 CRITICAL",
            Severity.HIGH: "🟠 HIGH",
            Severity.MEDIUM: "🟡 MEDIUM",
            Severity.LOW: "🔵 LOW",
            Severity.INFO: "⚪ INFO",
        }
        return badges.get(severity, str(severity.value))


class UnifiedMarkdownFormatter(UnifiedFormatter):
    """Cursor-style markdown output formatter using ReviewIssue.
    
    Produces a well-structured markdown report with:
    - Summary section
    - Top actionable fixes (sorted by severity)
    - Before/after code blocks with diffs
    - File-by-file breakdown
    
    Usage:
        formatter = UnifiedMarkdownFormatter()
        report = formatter.format(issues, stats)
    """
    
    def __init__(
        self,
        include_stats: bool = True,
        max_issues_per_file: int = 20,
        max_top_issues: int = 10,
    ) -> None:
        """Initialize formatter.
        
        Args:
            include_stats: Include statistics section
            max_issues_per_file: Limit issues per file in breakdown
            max_top_issues: Maximum number of top issues to show
        """
        self.include_stats = include_stats
        self.max_issues_per_file = max_issues_per_file
        self.max_top_issues = max_top_issues
    
    def format(
        self,
        issues: list[ReviewIssue],
        stats: Optional[UnifiedPipelineStats] = None,
    ) -> str:
        """Format issues as markdown.
        
        Args:
            issues: Issues to format
            stats: Optional pipeline statistics
            
        Returns:
            Markdown formatted string
        """
        lines: list[str] = []
        
        # Generate stats if not provided
        if stats is None:
            stats = UnifiedPipelineStats.from_issues(issues)
        
        # Header
        lines.append("# Code Review Report")
        lines.append("")
        lines.append(f"Generated: {stats.timestamp}")
        lines.append("")
        
        # Summary
        if self.include_stats:
            lines.extend(self._format_summary(stats))
            lines.append("")
        
        # Top actionable issues
        top_issues = self._get_top_issues(issues)
        if top_issues:
            lines.extend(self._format_top_issues(top_issues))
            lines.append("")
        
        # Group by file for detailed breakdown
        by_file = self._group_by_file(issues)
        if by_file:
            lines.extend(self._format_file_breakdown(by_file))
            lines.append("")
        
        # Top 3 Recommended Actions
        rec_lines = self.format_recommended_actions(issues, max_actions=3)
        if rec_lines:
            lines.append(rec_lines)
            lines.append("")

        return "\n".join(lines)

    def _format_summary(self, stats: UnifiedPipelineStats) -> list[str]:
        """Format summary statistics."""
        lines: list[str] = []
        
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Files Scanned | {stats.files_scanned} |")
        lines.append(f"| Total Issues | {stats.total_issues} |")
        lines.append(f"| 🔴 Critical | {stats.critical_count} |")
        lines.append(f"| 🟠 High | {stats.high_count} |")
        lines.append(f"| 🟡 Medium | {stats.medium_count} |")
        lines.append(f"| 🔵 Low | {stats.low_count} |")
        lines.append(f"| ⚪ Info | {stats.info_count} |")
        lines.append(f"| Execution Time | {stats.execution_time_ms:.0f}ms |")
        
        if stats.detectors_used:
            lines.append(f"| Detectors | {', '.join(stats.detectors_used)} |")
        
        return lines
    
    def _get_top_issues(self, issues: list[ReviewIssue]) -> list[ReviewIssue]:
        """Get top actionable issues (critical and high severity, high confidence)."""
        actionable = []
        for i in issues:
            sev_str = str(i.severity).upper()
            if sev_str in ("CRITICAL", "HIGH") and i.confidence >= 0.7:
                actionable.append(i)
        # Sort by severity weight, then confidence, then line number
        actionable.sort(
            key=lambda i: (
                -getattr(i.severity, 'weight', 50),
                -i.confidence,
                i.line,
            )
        )
        return actionable[:self.max_top_issues]
    
    def _format_top_issues(self, issues: list[ReviewIssue]) -> list[str]:
        """Format top actionable issues section."""
        lines: list[str] = []
        
        lines.append("## Top Actionable Issues")
        lines.append("")
        lines.append("These issues should be addressed first:")
        lines.append("")
        
        for i, issue in enumerate(issues, 1):
            lines.append(f"### {i}. {self._format_severity_badge(issue.severity)} {issue.title or issue.rule_id}")
            lines.append("")
            lines.append(f"**File:** `{issue.location}`")
            lines.append(f"**Rule:** `{issue.rule_id}`")
            lines.append(f"**Confidence:** {issue.confidence:.0%}")
            lines.append("")
            
            # Show message
            if issue.message:
                lines.append(f"**Message:** {issue.message}")
                lines.append("")
            
            # Show code evidence with before/after
            if issue.evidence:
                if issue.evidence.old_code:
                    lines.append("**Before (problematic code):**")
                    lines.append("```python")
                    lines.append(issue.evidence.old_code)
                    lines.append("```")
                    lines.append("")
                
                if issue.evidence.new_code:
                    lines.append("**After (suggested fix):**")
                    lines.append("```python")
                    lines.append(issue.evidence.new_code)
                    lines.append("```")
                    lines.append("")
            
            # Show explanation
            if issue.explanation:
                lines.append(f"**Explanation:** {issue.explanation}")
                lines.append("")
            
            # Show fix options
            if issue.fixes:
                if len(issue.fixes) == 1:
                    # Single fix option
                    fix = issue.fixes[0]
                    lines.append("**Fix:**")
                    lines.append(f"```python\n{fix.new_code}\n```")
                    if fix.tradeoff:
                        lines.append(f"*Tradeoff:* {fix.tradeoff}")
                else:
                    # Multiple fix options
                    lines.append("**Fix Options:**")
                    for j, fix in enumerate(issue.fixes, 1):
                        risk_icon = "✅" if fix.is_safe else "⚠️"
                        lines.append(f"\n##### Option {j}: {risk_icon} {fix.title}")
                        if fix.tradeoff:
                            lines.append(f"*Tradeoff:* {fix.tradeoff}")
                        lines.append(f"\n```python\n{fix.new_code}\n```")
                        if fix.test_recommendation:
                            lines.append(f"\n*Test:* {fix.test_recommendation}")
                    lines.append("")
            
            # Show CWE reference
            if issue.cwe_id:
                cwe_num = issue.cwe_id.replace("CWE-", "")
                lines.append(f"**CWE:** [{issue.cwe_id}](https://cwe.mitre.org/data/definitions/{cwe_num}.html)")
                lines.append("")
            
            lines.append("---")
            lines.append("")
        
        return lines
    
    def _format_file_breakdown(
        self,
        by_file: dict[str, list[ReviewIssue]],
    ) -> list[str]:
        """Format file-by-file breakdown."""
        lines: list[str] = []
        
        lines.append("## Detailed Issues by File")
        lines.append("")
        
        for file_path, file_issues in sorted(by_file.items()):
            # Format file header
            rel_path = self._get_relative_path(file_path)
            lines.append(f"### 📄 `{rel_path}`")
            lines.append("")
            
            # Group by severity
            by_severity = self._group_by_severity(file_issues)
            
            # Show critical first, then high, etc.
            severity_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]

            shown = 0
            for sev_key in severity_order:
                severity_issues = by_severity.get(sev_key, [])
                for issue in severity_issues:
                    if shown >= self.max_issues_per_file:
                        remaining = len(file_issues) - shown
                        if remaining > 0:
                            lines.append(f"_... and {remaining} more issues_")
                        break
                    
                    # Get primary fix if available
                    fix_hint = ""
                    if issue.is_auto_fixable:
                        fix_hint = " [auto-fixable]"
                    elif issue.is_fixable:
                        fix_hint = " [has fix]"
                    
                    lines.append(f"- {self._format_severity_badge(issue.severity)} ")
                    lines.append(f"  Line {issue.line}: [{issue.rule_id}] {issue.message[:80]}{fix_hint}")
                    
                    shown += 1
            
            lines.append("")
        
        return lines
    
    def _get_relative_path(self, file_path: str) -> str:
        """Convert absolute path to relative for display."""
        try:
            return str(Path(file_path).relative_to(Path.cwd()))
        except ValueError:
            return file_path
    
    def format_recommended_actions(
        self,
        issues: list[ReviewIssue],
        max_actions: int = 3,
    ) -> str:
        """Format Top N Recommended Actions summary.

        This provides actionable, prioritized recommendations based on
        severity + fixability + confidence scoring.

        Args:
            issues: List of issues to prioritize
            max_actions: Maximum number of actions to show (default: 3)

        Returns:
            Markdown formatted recommended actions section
        """
        if not issues:
            return ""

        # Score each issue: severity_weight * confidence * fixability
        scored_issues = []
        for issue in issues:
            # Severity weight (0-1)
            severity_score = getattr(issue.severity, 'weight', 50)

            # Confidence score (0-1)
            confidence_score = issue.confidence

            # Fixability bonus
            fixability_score = 1.0
            if issue.is_auto_fixable:
                fixability_score = 1.5  # 50% bonus for auto-fixable
            elif issue.is_fixable:
                fixability_score = 1.2  # 20% bonus for fixable

            # Calculate final score
            total_score = severity_score * confidence_score * fixability_score

            scored_issues.append((total_score, issue))

        # Sort by score (descending) and take top N
        scored_issues.sort(key=lambda x: -x[0])
        top_issues = [issue for _, issue in scored_issues[:max_actions]]

        if not top_issues:
            return ""

        lines: list[str] = []
        lines.append("## Top 3 Recommended Actions")
        lines.append("")
        lines.append("| Priority | Action | File | Line |")
        lines.append("|----------|--------|------|------|")

        priority_labels = ["1st", "2nd", "3rd", "4th", "5th"]

        for i, issue in enumerate(top_issues):
            # Format action description
            if issue.is_auto_fixable:
                action = f"Auto-fix: {issue.rule_id}"
            elif issue.is_fixable:
                action = f"Review & fix: {issue.rule_id}"
            else:
                action = f"Review: {issue.rule_id}"

            # Truncate long messages
            message = issue.message[:40] + "..." if len(issue.message) > 40 else issue.message

            priority = priority_labels[i] if i < len(priority_labels) else f"#{i+1}"
            sev_str = str(issue.severity).upper()
            severity_emoji = {
                "CRITICAL": "🔴",
                "HIGH": "🟠",
                "MEDIUM": "🟡",
                "LOW": "🔵",
                "INFO": "⚪",
            }.get(sev_str, "")

            lines.append(
                f"| {priority} {severity_emoji} | "
                f"{action} - {message} | "
                f"`{Path(issue.file).name}` | "
                f"`{issue.line}` |"
            )

        lines.append("")
        lines.append("> **Tip:** Run `/fix @<filename>` to auto-fix auto-fixable issues")
        lines.append("")

        return "\n".join(lines)


class UnifiedJsonFormatter(UnifiedFormatter):
    """Structured JSON output formatter using ReviewIssue.
    
    Produces machine-readable JSON output for integration with other tools.
    
    Usage:
        formatter = UnifiedJsonFormatter()
        json_output = formatter.format(issues, stats)
    """
    
    def __init__(self, pretty: bool = True) -> None:
        """Initialize formatter.
        
        Args:
            pretty: Use pretty printing (indent=2)
        """
        self.pretty = pretty
    
    def format(
        self,
        issues: list[ReviewIssue],
        stats: Optional[UnifiedPipelineStats] = None,
    ) -> str:
        """Format issues as JSON.
        
        Args:
            issues: Issues to format
            stats: Optional pipeline statistics
            
        Returns:
            JSON formatted string
        """
        output: dict[str, Any] = {
            "report": {
                "generated_at": datetime.now().isoformat(),
                "stats": stats.to_dict() if stats else {},
            },
            "issues": [issue.to_dict() for issue in issues],
        }
        
        if self.pretty:
            return json.dumps(output, indent=2, ensure_ascii=False)
        return json.dumps(output, ensure_ascii=False)


class UnifiedConsoleFormatter(UnifiedFormatter):
    """Simple console output formatter using ReviewIssue.
    
    Produces colored, compact console output.
    
    Usage:
        formatter = UnifiedConsoleFormatter()
        console_output = formatter.format(issues, stats)
    """
    
    SEVERITY_COLORS = {
        Severity.CRITICAL: "\033[91m",    # Red
        Severity.HIGH: "\033[93m",         # Orange/Yellow
        Severity.MEDIUM: "\033[93m",       # Yellow
        Severity.LOW: "\033[94m",          # Blue
        Severity.INFO: "\033[90m",         # Gray
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
        issues: list[ReviewIssue],
        stats: Optional[UnifiedPipelineStats] = None,
    ) -> str:
        """Format issues for console.
        
        Args:
            issues: Issues to format
            stats: Optional pipeline statistics
            
        Returns:
            Console formatted string
        """
        lines: list[str] = []
        
        # Summary
        if stats is None:
            stats = UnifiedPipelineStats.from_issues(issues)
        
        lines.append(self._color("=== Code Review Summary ===", Severity.INFO))
        lines.append(f"Files: {stats.files_scanned}, Issues: {stats.total_issues}")
        lines.append(f"🔴 {stats.critical_count} critical, 🟠 {stats.high_count} high, 🟡 {stats.medium_count} medium")
        lines.append("")
        
        # Group by severity
        by_severity = self._group_by_severity(issues)
        
        # Show critical first, then high
        for severity in [Severity.CRITICAL, Severity.HIGH]:
            severity_issues = by_severity.get(severity, [])
            if not severity_issues:
                continue
            
            lines.append(self._color(f"--- {severity.label}S ---", severity))
            for issue in severity_issues[:15]:
                fix_indicator = " [FIX]" if issue.is_fixable else ""
                lines.append(f"  {self._color('●', severity)} {issue.file}:{issue.line} [{issue.rule_id}]{fix_indicator}")
            if len(severity_issues) > 15:
                lines.append(f"  ... and {len(severity_issues) - 15} more")
            lines.append("")
        
        return "\n".join(lines)
    
    def _color(self, text: str, severity: Severity) -> str:
        """Apply color to text if colors enabled."""
        if not self.use_colors:
            return text
        color = self.SEVERITY_COLORS.get(severity, "")
        return f"{color}{text}{self.RESET}"


# ─── Factory ────────────────────────────────────────────────────────────────────


def get_formatter(format_type: str) -> UnifiedFormatter:
    """Get formatter by name.
    
    Args:
        format_type: Formatter type ("markdown", "json", "console")
    
    Returns:
        Formatter instance
    """
    formatters: dict[str, type[UnifiedFormatter]] = {
        "markdown": UnifiedMarkdownFormatter,
        "json": UnifiedJsonFormatter,
        "console": UnifiedConsoleFormatter,
    }
    
    formatter_class = formatters.get(format_type.lower(), UnifiedMarkdownFormatter)
    return formatter_class()


# =============================================================================
# Backward Compatibility Aliases
# =============================================================================

# Alias old name to new unified class
PipelineStats = UnifiedPipelineStats
MarkdownFormatter = UnifiedMarkdownFormatter  # Old name
JsonFormatter = UnifiedJsonFormatter
ConsoleFormatter = UnifiedConsoleFormatter
ResultFormatter = UnifiedFormatter  # Old base class name
