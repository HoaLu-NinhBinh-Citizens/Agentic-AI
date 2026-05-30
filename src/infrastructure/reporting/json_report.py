"""JSON report generator for CI/CD integration."""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Optional

from src.infrastructure.reporting.markdown_report import (
    Finding,
    PipelineStats,
    Severity,
)


@dataclass
class JSONFinding:
    """Serializable finding for JSON output."""

    rule_id: str
    title: str
    severity: str
    file_path: str
    line: int
    message: str
    description: str
    old_code: Optional[str]
    new_code: Optional[str]
    confidence: float
    fixable: bool
    auto_fixable: bool
    risk_level: str

    @classmethod
    def from_finding(cls, finding: Finding) -> "JSONFinding":
        return cls(
            rule_id=finding.rule_id,
            title=finding.title,
            severity=finding.severity.value,
            file_path=finding.file_path,
            line=finding.line,
            message=finding.message,
            description=finding.description,
            old_code=finding.old_code or None,
            new_code=finding.new_code or None,
            confidence=finding.confidence,
            fixable=finding.fixable,
            auto_fixable=finding.auto_fixable,
            risk_level=finding.risk_level,
        )


class JSONReportGenerator:
    """Generate JSON output for CI/CD pipelines and tooling integration."""

    def __init__(self, project_name: str = "Project", version: str = "1.0.0"):
        self.project_name = project_name
        self.version = version

    def generate(
        self,
        findings: list[Finding],
        stats: PipelineStats,
        recommendations: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Generate JSON report."""
        json_findings = [JSONFinding.from_finding(f) for f in findings]
        by_file = self._group_by_file(findings)
        by_severity = self._group_by_severity(findings)
        top3 = self._get_top_3_actionable(findings)

        return {
            "version": self.version,
            "timestamp": datetime.now().isoformat(),
            "project": self.project_name,
            "summary": self._build_summary(by_severity),
            "top_fixes": self._build_top_fixes(top3),
            "findings": [asdict(f) for f in json_findings],
            "by_file": self._build_by_file(by_file),
            "statistics": self._build_statistics(findings),
            "recommendations": recommendations or [],
        }

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

    def _get_top_3_actionable(self, findings: list[Finding]) -> list[Finding]:
        fixable = [f for f in findings if f.fixable]
        severity_order = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2}
        sorted_findings = sorted(
            fixable,
            key=lambda f: (severity_order.get(f.severity, 99), -f.confidence),
        )
        return sorted_findings[:3]

    def _build_summary(self, by_severity: dict[Severity, list[Finding]]) -> dict[str, Any]:
        return {
            "critical": len(by_severity.get(Severity.CRITICAL, [])),
            "high": len(by_severity.get(Severity.HIGH, [])),
            "medium": len(by_severity.get(Severity.MEDIUM, [])),
            "low": len(by_severity.get(Severity.LOW, [])),
            "info": len(by_severity.get(Severity.INFO, [])),
            "total": sum(len(v) for v in by_severity.values()),
        }

    def _build_top_fixes(self, top3: list[Finding]) -> list[dict[str, Any]]:
        return [
            {
                "rank": i + 1,
                "rule_id": f.rule_id,
                "title": f.title,
                "severity": f.severity.value,
                "file_path": f.file_path,
                "line": f.line,
                "confidence": f.confidence,
                "risk_level": f.risk_level,
                "fix_command": f"/fix @{f.file_path}:{f.line}",
            }
            for i, f in enumerate(top3)
        ]

    def _build_by_file(self, by_file: dict[str, list[Finding]]) -> dict[str, Any]:
        result = {}
        for file_path, findings in sorted(by_file.items()):
            by_sev = self._group_by_severity(findings)
            result[file_path] = {
                "count": len(findings),
                "by_severity": {s.value: len(by_sev.get(s, [])) for s in Severity},
                "findings": [
                    {
                        "line": f.line,
                        "rule_id": f.rule_id,
                        "severity": f.severity.value,
                        "message": f.message,
                    }
                    for f in findings
                ],
            }
        return result

    def _build_statistics(self, findings: list[Finding]) -> dict[str, Any]:
        fixable = sum(1 for f in findings if f.fixable)
        auto_fixable = sum(1 for f in findings if f.auto_fixable)
        return {
            "total": len(findings),
            "fixable": fixable,
            "auto_fixable": auto_fixable,
            "manual_review_required": fixable - auto_fixable,
        }
