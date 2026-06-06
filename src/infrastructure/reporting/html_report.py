"""Self-contained HTML report generator for AI_SUPPORT code review.

Produces a single HTML file with all CSS/JS embedded inline.
Features:
- Syntax-highlighted code snippets
- Severity badges with color coding
- Side-by-side diff for before/after code
- Navigation links and table of contents
- Summary table with severity counts
- Responsive layout
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Optional

from src.infrastructure.reporting.markdown_report import (
    Finding,
    PipelineStats,
    Severity,
)


_SEVERITY_COLORS = {
    Severity.CRITICAL: "#dc3545",
    Severity.HIGH: "#fd7e14",
    Severity.MEDIUM: "#ffc107",
    Severity.LOW: "#0d6efd",
    Severity.INFO: "#6c757d",
}

_SEVERITY_LABELS = {
    Severity.CRITICAL: "CRITICAL",
    Severity.HIGH: "HIGH",
    Severity.MEDIUM: "MEDIUM",
    Severity.LOW: "LOW",
    Severity.INFO: "INFO",
}


_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       margin: 0; padding: 20px; background: #1e1e2e; color: #cdd6f4; }
.container { max-width: 1200px; margin: 0 auto; }
h1, h2, h3 { color: #89b4fa; }
.header { border-bottom: 2px solid #45475a; padding-bottom: 16px; margin-bottom: 24px; }
.stats { display: flex; gap: 24px; flex-wrap: wrap; margin: 16px 0; }
.stat-box { background: #313244; padding: 12px 20px; border-radius: 8px; }
.stat-box .value { font-size: 24px; font-weight: bold; color: #89dceb; }
.stat-box .label { font-size: 12px; color: #a6adc8; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px;
         font-size: 11px; font-weight: 600; color: #fff; }
.summary-table { width: 100%; border-collapse: collapse; margin: 16px 0; }
.summary-table th, .summary-table td { padding: 8px 12px; text-align: left;
                                         border-bottom: 1px solid #45475a; }
.summary-table th { background: #313244; }
.finding-card { background: #313244; border-radius: 8px; padding: 16px;
                margin: 12px 0; border-left: 4px solid; }
.finding-card h4 { margin: 0 0 8px 0; }
.code-block { background: #11111b; border-radius: 6px; padding: 12px;
              overflow-x: auto; font-family: 'JetBrains Mono', monospace; font-size: 13px; }
.diff-container { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.diff-remove { background: rgba(220, 53, 69, 0.15); border-left: 3px solid #dc3545; }
.diff-add { background: rgba(25, 135, 84, 0.15); border-left: 3px solid #198754; }
.toc { background: #313244; padding: 16px; border-radius: 8px; margin: 16px 0; }
.toc a { color: #89b4fa; text-decoration: none; }
.toc a:hover { text-decoration: underline; }
.file-section { margin: 24px 0; }
.nav-link { color: #89b4fa; text-decoration: none; font-size: 13px; }
@media (max-width: 768px) { .diff-container { grid-template-columns: 1fr; } }
"""


class HTMLReportGenerator:
    """Generate self-contained HTML report with embedded CSS."""

    def __init__(self, project_name: str = "Project", version: str = "1.0.0"):
        self.project_name = project_name
        self.version = version

    def generate(
        self,
        findings: list[Finding],
        stats: PipelineStats,
        recommendations: Optional[list[str]] = None,
    ) -> str:
        """Generate complete HTML report as a single string."""
        by_severity = self._group_by_severity(findings)
        by_file = self._group_by_file(findings)
        top3 = self._get_top_3(findings)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        parts = [
            "<!DOCTYPE html>",
            "<html lang='en'>",
            "<head>",
            "<meta charset='UTF-8'>",
            "<meta name='viewport' content='width=device-width, initial-scale=1.0'>",
            f"<title>AI_SUPPORT Review - {html.escape(self.project_name)}</title>",
            f"<style>{_CSS}</style>",
            "</head>",
            "<body>",
            "<div class='container'>",
            self._build_header(stats, timestamp),
            self._build_toc(by_file),
            self._build_summary_table(by_severity),
            self._build_top_fixes(top3),
            self._build_file_sections(by_file),
            self._build_recommendations(recommendations or []),
            self._build_footer(),
            "</div>",
            "</body>",
            "</html>",
        ]
        return "\n".join(parts)

    def _build_header(self, stats: PipelineStats, timestamp: str) -> str:
        return f"""
<div class='header'>
  <h1>🔍 AI_SUPPORT Code Review</h1>
  <div class='stats'>
    <div class='stat-box'><div class='value'>{stats.files_analyzed}</div><div class='label'>Files Analyzed</div></div>
    <div class='stat-box'><div class='value'>{stats.total_findings}</div><div class='label'>Total Findings</div></div>
    <div class='stat-box'><div class='value'>{stats.duration_seconds:.2f}s</div><div class='label'>Duration</div></div>
    <div class='stat-box'><div class='value'>{timestamp}</div><div class='label'>Timestamp</div></div>
  </div>
</div>"""

    def _build_toc(self, by_file: dict[str, list[Finding]]) -> str:
        links = []
        for file_path in sorted(by_file.keys()):
            count = len(by_file[file_path])
            anchor = html.escape(file_path.replace("/", "_").replace("\\", "_"))
            links.append(f"  <li><a href='#{anchor}'>{html.escape(file_path)} ({count})</a></li>")
        return f"""
<div class='toc'>
  <h3>📑 Table of Contents</h3>
  <ul>
    <li><a href='#summary'>Summary</a></li>
    <li><a href='#top-fixes'>Top Fixes</a></li>
{''.join(links)}
  </ul>
</div>"""

    def _build_summary_table(self, by_severity: dict[Severity, list[Finding]]) -> str:
        rows = []
        for sev in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]:
            count = len(by_severity.get(sev, []))
            if count > 0:
                color = _SEVERITY_COLORS[sev]
                label = _SEVERITY_LABELS[sev]
                rows.append(f"    <tr><td><span class='badge' style='background:{color}'>{label}</span></td><td>{count}</td></tr>")
        return f"""
<div id='summary'>
  <h2>Summary</h2>
  <table class='summary-table'>
    <thead><tr><th>Severity</th><th>Count</th></tr></thead>
    <tbody>
{''.join(rows)}
    </tbody>
  </table>
</div>"""

    def _build_top_fixes(self, top3: list[Finding]) -> str:
        if not top3:
            return ""
        cards = []
        for i, f in enumerate(top3, 1):
            color = _SEVERITY_COLORS.get(f.severity, "#6c757d")
            diff_html = self._render_diff(f) if f.old_code and f.new_code else ""
            cards.append(f"""
  <div class='finding-card' style='border-left-color:{color}'>
    <h4>{i}. [{f.rule_id}] {html.escape(f.title)}</h4>
    <p>{html.escape(f.message)}</p>
    <p><code>{html.escape(f.file_path)}:{f.line}</code> | Confidence: {int(f.confidence * 100)}%</p>
    {diff_html}
    <p class='nav-link'><code>/fix @{html.escape(f.file_path)}:{f.line}</code></p>
  </div>""")
        return f"""
<div id='top-fixes'>
  <h2>🔧 Top Fixes</h2>
{''.join(cards)}
</div>"""

    def _build_file_sections(self, by_file: dict[str, list[Finding]]) -> str:
        sections = []
        for file_path, findings in sorted(by_file.items()):
            anchor = html.escape(file_path.replace("/", "_").replace("\\", "_"))
            finding_rows = []
            for f in findings:
                color = _SEVERITY_COLORS.get(f.severity, "#6c757d")
                label = _SEVERITY_LABELS.get(f.severity, "INFO")
                diff_html = self._render_diff(f) if (f.old_code or f.new_code) else ""
                finding_rows.append(f"""
      <div class='finding-card' style='border-left-color:{color}'>
        <span class='badge' style='background:{color}'>{label}</span>
        <strong>[{html.escape(f.rule_id)}]</strong> L{f.line}: {html.escape(f.message[:120])}
        {diff_html}
      </div>""")
            sections.append(f"""
<div class='file-section' id='{anchor}'>
  <h3>📄 {html.escape(file_path)}</h3>
{''.join(finding_rows)}
</div>""")
        return "\n".join(sections)

    def _render_diff(self, finding: Finding) -> str:
        """Render side-by-side diff in HTML."""
        parts = []
        if finding.old_code:
            escaped = html.escape(finding.old_code)
            parts.append(f"<div class='code-block diff-remove'><pre>{escaped}</pre></div>")
        if finding.new_code:
            escaped = html.escape(finding.new_code)
            parts.append(f"<div class='code-block diff-add'><pre>{escaped}</pre></div>")
        if len(parts) == 2:
            return f"<div class='diff-container'>{''.join(parts)}</div>"
        return "".join(parts)

    def _build_recommendations(self, recs: list[str]) -> str:
        if not recs:
            return ""
        items = "\n".join(f"  <li>{html.escape(r)}</li>" for r in recs)
        return f"""
<div>
  <h2>💡 Recommendations</h2>
  <ol>{items}</ol>
</div>"""

    def _build_footer(self) -> str:
        return f"""
<div style='margin-top:40px;padding-top:16px;border-top:1px solid #45475a;color:#6c757d;font-size:12px'>
  Generated by AI_SUPPORT v{self.version}
</div>"""

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _group_by_severity(self, findings: list[Finding]) -> dict[Severity, list[Finding]]:
        groups: dict[Severity, list[Finding]] = {s: [] for s in Severity}
        for f in findings:
            groups[f.severity].append(f)
        return groups

    def _group_by_file(self, findings: list[Finding]) -> dict[str, list[Finding]]:
        groups: dict[str, list[Finding]] = {}
        for f in findings:
            groups.setdefault(f.file_path, []).append(f)
        return groups

    def _get_top_3(self, findings: list[Finding]) -> list[Finding]:
        fixable = [f for f in findings if f.fixable]
        severity_order = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2}
        sorted_findings = sorted(
            fixable,
            key=lambda f: (severity_order.get(f.severity, 99), -f.confidence),
        )
        return sorted_findings[:3]
