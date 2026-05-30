"""Unified ReviewIssue schema for AI_SUPPORT code review system.

This module provides the unified ReviewIssue, CodeEvidence, and FixOption classes
that all components (ML detector, rule engine, formatters, fix applicators) use.

Architecture:
- CodeEvidence: Code context with diff generation
- FixOption: A single fix option for an issue
- ReviewIssue: Unified representation of a review finding/issue
"""

from __future__ import annotations

import difflib
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Severity(Enum):
    """Finding severity level with weight for sorting."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"

    @property
    def weight(self) -> float:
        """Get weight for sorting."""
        weights = {
            "CRITICAL": 1.0,
            "HIGH": 0.8,
            "MEDIUM": 0.5,
            "LOW": 0.3,
            "INFO": 0.1,
        }
        return weights.get(self.value, 0.5)

    @classmethod
    def from_old_format(cls, value: str) -> Severity:
        """Convert from legacy format strings."""
        mapping = {
            "error": cls.CRITICAL,
            "warning": cls.HIGH,
            "info": cls.INFO,
            "hint": cls.LOW,
        }
        return mapping.get(value.lower(), cls.MEDIUM)

    def to_old_format(self) -> str:
        """Convert to legacy format strings."""
        mapping = {
            "CRITICAL": "error",
            "HIGH": "error",
            "MEDIUM": "warning",
            "LOW": "info",
            "INFO": "info",
        }
        return mapping.get(self.value, "warning")


@dataclass
class CodeEvidence:
    """Evidence for a finding - code context with diff support."""
    
    file: str
    line_start: int
    line_end: int
    old_code: str = ""
    new_code: str = ""
    context_before: list[str] = field(default_factory=list)
    context_after: list[str] = field(default_factory=list)
    
    @property
    def diff(self) -> str:
        """Generate unified diff from old_code to new_code."""
        if not self.old_code:
            return ""
        old_lines = self.old_code.splitlines(keepends=True)
        new_lines = self.new_code.splitlines(keepends=True) if self.new_code else []
        
        if not new_lines:
            new_lines = [""] * len(old_lines)
        
        diff_lines = list(difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{self.file}",
            tofile=f"b/{self.file}",
            lineterm="",
        ))
        return "".join(diff_lines)
    
    @property
    def location(self) -> str:
        """Human-readable location string."""
        if self.line_start == self.line_end:
            return f"{self.file}:{self.line_start}"
        return f"{self.file}:{self.line_start}-{self.line_end}"
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "file": self.file,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "old_code": self.old_code,
            "new_code": self.new_code,
            "context_before": self.context_before,
            "context_after": self.context_after,
            "diff": self.diff,
        }


@dataclass
class FixOption:
    """A single fix option for an issue."""
    
    id: str
    title: str
    description: str = ""
    old_code: str = ""
    new_code: str = ""
    diff: str = ""
    risk: Severity = Severity.MEDIUM
    confidence: float = 1.0
    effort: str = "low"  # low, medium, high
    apply_command: str = ""
    rollback_command: str = ""
    tests_to_run: list[str] = field(default_factory=list)
    
    def __post_init__(self) -> None:
        if not self.diff and self.old_code and self.new_code:
            self.diff = self._generate_diff()
    
    def _generate_diff(self) -> str:
        """Generate unified diff from old_code to new_code."""
        old_lines = self.old_code.splitlines(keepends=True)
        new_lines = self.new_code.splitlines(keepends=True)
        
        diff_lines = list(difflib.unified_diff(
            old_lines,
            new_lines,
            lineterm="",
        ))
        return "".join(diff_lines)
    
    @property
    def is_safe(self) -> bool:
        """Check if fix is considered safe (low risk)."""
        return self.risk in (Severity.LOW, Severity.INFO)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "old_code": self.old_code,
            "new_code": self.new_code,
            "diff": self.diff,
            "risk": self.risk.value,
            "confidence": self.confidence,
            "effort": self.effort,
            "apply_command": self.apply_command,
            "rollback_command": self.rollback_command,
            "tests_to_run": self.tests_to_run,
        }


@dataclass
class ReviewIssue:
    """Unified representation of a review finding/issue.
    
    This is the central schema that all components use:
    - ML detector produces ReviewIssue objects
    - Rule engine produces ReviewIssue objects
    - Formatters consume ReviewIssue objects
    - FixApplicator consumes ReviewIssue objects
    
    Attributes:
        id: Unique identifier for this issue
        rule_id: Rule identifier (e.g., "ML001", "SEC001")
        severity: Severity level
        file: File path
        line: Line number
        end_line: End line number (for multi-line issues)
        title: Short title/summary
        message: Detailed message
        explanation: Root cause explanation
        root_cause: Root cause analysis
        evidence: Code evidence with context
        fixes: List of fix options
        confidence: Detection confidence (0.0-1.0)
        tags: Categorization tags
        cwe_id: CWE vulnerability ID
        detector: Source detector ("ml", "security", "quality", "embedded")
        detection_method: How it was detected ("ast", "regex", "data_flow", "llm")
    """
    
    id: str
    rule_id: str
    severity: Severity
    file: str
    line: int
    end_line: Optional[int] = None
    
    title: str = ""
    message: str = ""
    explanation: str = ""
    root_cause: str = ""
    
    evidence: Optional[CodeEvidence] = None
    fixes: list[FixOption] = field(default_factory=list)
    
    confidence: float = 1.0
    tags: list[str] = field(default_factory=list)
    cwe_id: str = ""
    
    # Metadata
    detector: str = ""  # "ml", "security", "quality", "embedded"
    detection_method: str = ""  # "ast", "regex", "data_flow", "llm"
    
    def __post_init__(self) -> None:
        if self.end_line is None:
            self.end_line = self.line
    
    @property
    def is_fixable(self) -> bool:
        """Check if this issue has any fix options."""
        return len(self.fixes) > 0
    
    @property
    def is_auto_fixable(self) -> bool:
        """Check if this issue can be auto-fixed (has low-risk fix)."""
        return any(f.risk == Severity.LOW for f in self.fixes)
    
    @property
    def primary_fix(self) -> Optional[FixOption]:
        """Get the recommended fix (lowest risk, highest confidence)."""
        if not self.fixes:
            return None
        return min(
            self.fixes,
            key=lambda f: (f.risk.weight, -f.confidence)
        )
    
    @property
    def location(self) -> str:
        """Human-readable location string."""
        if self.line == self.end_line:
            return f"{self.file}:{self.line}"
        return f"{self.file}:{self.line}-{self.end_line}"
    
    def to_markdown(self) -> str:
        """Convert to markdown format for reporting."""
        lines: list[str] = []
        
        # Header with severity badge
        severity_badge = {
            Severity.CRITICAL: "🔴 CRITICAL",
            Severity.HIGH: "🟠 HIGH",
            Severity.MEDIUM: "🟡 MEDIUM",
            Severity.LOW: "🔵 LOW",
            Severity.INFO: "⚪ INFO",
        }
        badge = severity_badge.get(self.severity, str(self.severity.value))
        
        lines.append(f"### {badge} {self.title or self.rule_id}")
        lines.append("")
        lines.append(f"**File:** `{self.location}`")
        lines.append(f"**Rule:** `{self.rule_id}`")
        lines.append(f"**Confidence:** {self.confidence:.0%}")
        lines.append("")
        
        # Message
        if self.message:
            lines.append(f"**Message:** {self.message}")
            lines.append("")
        
        # Code evidence with diff
        if self.evidence:
            if self.evidence.old_code:
                lines.append("**Before (problematic code):**")
                lines.append("```python")
                lines.append(self.evidence.old_code)
                lines.append("```")
                lines.append("")
            
            if self.evidence.new_code:
                lines.append("**After (suggested fix):**")
                lines.append("```python")
                lines.append(self.evidence.new_code)
                lines.append("```")
                lines.append("")
        
        # Explanation
        if self.explanation:
            lines.append(f"**Explanation:** {self.explanation}")
            lines.append("")
        
        # Root cause
        if self.root_cause:
            lines.append(f"**Root Cause:** {self.root_cause}")
            lines.append("")
        
        # Fix options
        if self.fixes:
            lines.append("**Fix Options:**")
            for i, fix in enumerate(self.fixes, 1):
                risk_icon = "✅" if fix.is_safe else "⚠️"
                lines.append(f"{i}. {risk_icon} **{fix.title}**")
                if fix.description:
                    lines.append(f"   - {fix.description}")
            lines.append("")
        
        # CWE reference
        if self.cwe_id:
            cwe_num = self.cwe_id.replace("CWE-", "")
            lines.append(f"**CWE:** [{self.cwe_id}](https://cwe.mitre.org/data/definitions/{cwe_num}.html)")
            lines.append("")
        
        return "\n".join(lines)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "severity_weight": self.severity.weight,
            "file": self.file,
            "line": self.line,
            "end_line": self.end_line,
            "title": self.title,
            "message": self.message,
            "explanation": self.explanation,
            "root_cause": self.root_cause,
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "fixes": [f.to_dict() for f in self.fixes],
            "confidence": self.confidence,
            "tags": self.tags,
            "cwe_id": self.cwe_id,
            "detector": self.detector,
            "detection_method": self.detection_method,
            "is_fixable": self.is_fixable,
            "is_auto_fixable": self.is_auto_fixable,
            "location": self.location,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReviewIssue:
        """Create ReviewIssue from dictionary."""
        # Parse severity
        sev = data.get("severity", "MEDIUM")
        if isinstance(sev, str):
            severity = Severity(sev)
        else:
            severity = sev
        
        # Parse evidence
        evidence = None
        if data.get("evidence"):
            ev_data = data["evidence"]
            evidence = CodeEvidence(
                file=ev_data.get("file", ""),
                line_start=ev_data.get("line_start", 0),
                line_end=ev_data.get("line_end", 0),
                old_code=ev_data.get("old_code", ""),
                new_code=ev_data.get("new_code", ""),
                context_before=ev_data.get("context_before", []),
                context_after=ev_data.get("context_after", []),
            )
        
        # Parse fixes
        fixes = []
        for fix_data in data.get("fixes", []):
            risk = fix_data.get("risk", "MEDIUM")
            if isinstance(risk, str):
                risk = Severity(risk)
            fixes.append(FixOption(
                id=fix_data.get("id", ""),
                title=fix_data.get("title", ""),
                description=fix_data.get("description", ""),
                old_code=fix_data.get("old_code", ""),
                new_code=fix_data.get("new_code", ""),
                diff=fix_data.get("diff", ""),
                risk=risk,
                confidence=fix_data.get("confidence", 1.0),
                effort=fix_data.get("effort", "low"),
                apply_command=fix_data.get("apply_command", ""),
                rollback_command=fix_data.get("rollback_command", ""),
                tests_to_run=fix_data.get("tests_to_run", []),
            ))
        
        return cls(
            id=data.get("id", ""),
            rule_id=data.get("rule_id", ""),
            severity=severity,
            file=data.get("file", ""),
            line=data.get("line", 0),
            end_line=data.get("end_line"),
            title=data.get("title", ""),
            message=data.get("message", ""),
            explanation=data.get("explanation", ""),
            root_cause=data.get("root_cause", ""),
            evidence=evidence,
            fixes=fixes,
            confidence=data.get("confidence", 1.0),
            tags=data.get("tags", []),
            cwe_id=data.get("cwe_id", ""),
            detector=data.get("detector", ""),
            detection_method=data.get("detection_method", ""),
        )


def generate_issue_id(rule_id: str, file: str, line: int) -> str:
    """Generate a unique issue ID.
    
    Args:
        rule_id: Rule identifier
        file: File path
        line: Line number
    
    Returns:
        Unique issue ID string
    """
    raw = f"{rule_id}:{file}:{line}"
    hash_suffix = hashlib.md5(raw.encode()).hexdigest()[:8]
    return f"{rule_id.lower()}-{hash_suffix}"
