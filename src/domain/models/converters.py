"""Converters for transforming various finding types to unified ReviewIssue.

This module provides converters that transform:
- MLFinding (from infrastructure ML detector) -> ReviewIssue
- Finding (from detector_base) -> ReviewIssue
- Fix (from fix_engine models) -> ReviewIssue
- Any legacy finding format -> ReviewIssue

Usage:
    from src.domain.models.converters import MLFindingConverter, FindingConverter
    
    # Convert MLFinding to ReviewIssue
    issue = MLFindingConverter.convert(ml_finding)
    
    # Convert Finding to ReviewIssue
    issue = FindingConverter.convert(finding)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Union

from src.domain.models.review_issue import (
    CodeEvidence,
    FixOption,
    ReviewIssue,
    Severity,
    generate_issue_id,
)

if TYPE_CHECKING:
    from src.application.workflows.unified.detector_base import Finding as UnifiedFinding
    from src.infrastructure.analysis.ml_detectors.detector import MLFinding
    from src.core.fix_engine.models import Fix


class MLFindingConverter:
    """Converter for MLFinding to ReviewIssue.
    
    Transforms infrastructure ML findings to unified schema.
    
    Example:
        from src.infrastructure.analysis.ml_detectors import MLDetector, MLFinding
        
        detector = MLDetector()
        findings = detector.detect_file(path, content)
        
        for f in findings:
            issue = MLFindingConverter.convert(f)
    """
    
    # Map MLSeverity to unified Severity
    _SEVERITY_MAP = {
        "CRITICAL": Severity.CRITICAL,
        "HIGH": Severity.HIGH,
        "MEDIUM": Severity.MEDIUM,
    }
    
    @classmethod
    def convert(cls, finding: "MLFinding") -> ReviewIssue:
        """Convert MLFinding to ReviewIssue.
        
        Args:
            finding: MLFinding from infrastructure detector
            
        Returns:
            Unified ReviewIssue
        """
        # Create code evidence
        evidence = CodeEvidence(
            file=finding.file_path or "",
            line_start=finding.line,
            line_end=finding.end_line or finding.line,
            old_code=finding.old_code,
            new_code=finding.new_code,
        )
        
        # Create fix option from old/new code
        fix_id = generate_issue_id(finding.rule_id, finding.file_path or "", finding.line)

        # Fix risk is usually lower than issue severity
        # ML issues are critical but fixes are often straightforward
        issue_severity = cls._map_severity(finding.severity.value)
        fix_risk = Severity.LOW if issue_severity == Severity.CRITICAL else issue_severity

        fix = FixOption(
            id=f"fix-{fix_id}",
            title=f"Fix {finding.rule_id}",
            description=finding.explanation,
            old_code=finding.old_code,
            new_code=finding.new_code,
            risk=fix_risk,
            confidence=finding.confidence,
            effort="medium",
        )
        
        return ReviewIssue(
            id=fix_id,
            rule_id=finding.rule_id,
            severity=cls._map_severity(finding.severity.value),
            file=finding.file_path or "",
            line=finding.line,
            end_line=finding.end_line or finding.line,
            title=finding.message[:80] if finding.message else f"{finding.rule_id} issue",
            message=finding.message,
            explanation=finding.explanation,
            evidence=evidence,
            fixes=[fix],
            confidence=finding.confidence,
            tags=["ml", "machine-learning"],
            detector="ml",
            detection_method=finding.detection_method,
        )
    
    @classmethod
    def _map_severity(cls, ml_severity: str) -> Severity:
        """Map MLSeverity to unified Severity."""
        return cls._SEVERITY_MAP.get(ml_severity, Severity.MEDIUM)


class FindingConverter:
    """Converter for unified Finding to ReviewIssue.
    
    Transforms findings from the unified pipeline's detector_base.
    
    Example:
        from src.application.workflows.unified.detector_base import Finding
        from src.domain.models.converters import FindingConverter
        
        finding = Finding(rule_id="SEC001", ...)
        issue = FindingConverter.convert(finding)
    """
    
    # Map FindingSeverity to unified Severity
    _SEVERITY_MAP = {
        "error": Severity.CRITICAL,
        "warning": Severity.HIGH,
        "info": Severity.INFO,
        "hint": Severity.LOW,
    }
    
    @classmethod
    def convert(cls, finding: "UnifiedFinding") -> ReviewIssue:
        """Convert Finding to ReviewIssue.
        
        Args:
            finding: Finding from detector_base
            
        Returns:
            Unified ReviewIssue
        """
        # Create code evidence from metadata or context
        evidence = None
        if finding.metadata.get("old_code") or finding.context:
            evidence = CodeEvidence(
                file=finding.file,
                line_start=finding.line,
                line_end=finding.end_line or finding.line,
                old_code=finding.metadata.get("old_code", finding.context or ""),
                new_code=finding.metadata.get("new_code", ""),
            )
        
        # Create fix options from metadata
        fixes = []
        if finding.fix:
            fix = FixOption(
                id=f"fix-{finding.rule_id}-{finding.line}",
                title=finding.rule_name or f"Fix {finding.rule_id}",
                description=finding.fix,
                new_code=finding.metadata.get("new_code", ""),
                old_code=finding.metadata.get("old_code", ""),
                risk=cls._map_severity(finding.severity.value),
                confidence=finding.confidence,
            )
            fixes.append(fix)
        
        return ReviewIssue(
            id=generate_issue_id(finding.rule_id, finding.file, finding.line),
            rule_id=finding.rule_id,
            severity=cls._map_severity(finding.severity.value),
            file=finding.file,
            line=finding.line,
            end_line=finding.end_line or finding.line,
            title=finding.rule_name or finding.rule_id,
            message=finding.message,
            explanation=finding.metadata.get("explanation", ""),
            evidence=evidence,
            fixes=fixes,
            confidence=finding.confidence,
            tags=finding.metadata.get("tags", []),
            cwe_id=finding.metadata.get("cwe", ""),
            detector=finding.detector,
            detection_method=finding.metadata.get("detection_method", ""),
        )
    
    @classmethod
    def _map_severity(cls, severity_value: str) -> Severity:
        """Map FindingSeverity string to unified Severity."""
        return cls._SEVERITY_MAP.get(severity_value.lower(), Severity.MEDIUM)


class FixConverter:
    """Converter for Fix to ReviewIssue.
    
    Transforms fixes from fix_engine.models.
    
    Example:
        from src.core.fix_engine.models import Fix
        from src.domain.models.converters import FixConverter
        
        fix = Fix(id="fix-1", ...)
        issue = FixConverter.to_review_issue(fix)
    """
    
    # Map FixSeverity to unified Severity
    _SEVERITY_MAP = {
        "error": Severity.CRITICAL,
        "warning": Severity.HIGH,
        "info": Severity.MEDIUM,
    }
    
    @classmethod
    def to_review_issue(cls, fix: "Fix", rule_id: str = "", message: str = "") -> ReviewIssue:
        """Convert Fix to ReviewIssue.
        
        Args:
            fix: Fix from fix_engine
            rule_id: Optional rule ID override
            message: Optional message override
            
        Returns:
            Unified ReviewIssue
        """
        issue_id = generate_issue_id(
            rule_id or fix.rule_id or "unknown",
            fix.file_path,
            fix.line_start,
        )
        
        # Create code evidence
        evidence = CodeEvidence(
            file=fix.file_path,
            line_start=fix.line_start,
            line_end=fix.line_end,
            old_code=fix.old_text,
            new_code=fix.new_text,
        )
        
        # Create fix option
        fix_option = FixOption(
            id=fix.id,
            title=f"Fix {fix.rule_id}" if fix.rule_id else "Suggested fix",
            description=fix.reason,
            old_code=fix.old_text,
            new_code=fix.new_text,
            risk=cls._map_severity(fix.severity.value),
            confidence=fix.confidence,
        )
        
        return ReviewIssue(
            id=issue_id,
            rule_id=fix.rule_id or rule_id or "unknown",
            severity=cls._map_severity(fix.severity.value),
            file=fix.file_path,
            line=fix.line_start,
            end_line=fix.line_end,
            title=f"Fix {fix.rule_id}" if fix.rule_id else "Code fix suggestion",
            message=message or fix.reason,
            explanation=fix.llm_explanation,
            evidence=evidence,
            fixes=[fix_option],
            confidence=fix.confidence,
            tags=["fix", "suggestion"],
            detector="fix_engine",
        )
    
    @classmethod
    def _map_severity(cls, fix_severity: str) -> Severity:
        """Map FixSeverity string to unified Severity."""
        return cls._SEVERITY_MAP.get(fix_severity.lower(), Severity.MEDIUM)


def convert_to_review_issue(
    finding: Union["MLFinding", "UnifiedFinding", "Fix"],
    **kwargs: Any,
) -> ReviewIssue:
    """Generic converter that auto-detects the finding type.
    
    Args:
        finding: Any supported finding type
        **kwargs: Additional arguments passed to converter
        
    Returns:
        Unified ReviewIssue
        
    Raises:
        ValueError: If finding type is not supported
    """
    # Check for MLFinding
    if hasattr(finding, "severity") and hasattr(finding, "old_code") and hasattr(finding, "new_code"):
        if hasattr(finding, "detection_method"):
            return MLFindingConverter.convert(finding)
    
    # Check for unified Finding
    if hasattr(finding, "metadata") and hasattr(finding, "rule_name"):
        return FindingConverter.convert(finding)
    
    # Check for Fix
    if hasattr(finding, "old_text") and hasattr(finding, "new_text"):
        return FixConverter.to_review_issue(finding, **kwargs)
    
    raise ValueError(f"Unsupported finding type: {type(finding)}")


def convert_batch(
    findings: list[Union["MLFinding", "UnifiedFinding", "Fix"]],
) -> list[ReviewIssue]:
    """Convert a batch of findings to ReviewIssues.
    
    Args:
        findings: List of findings to convert
        
    Returns:
        List of unified ReviewIssues
    """
    return [convert_to_review_issue(f) for f in findings]


def deduplicate_issues(issues: list[ReviewIssue]) -> list[ReviewIssue]:
    """Deduplicate issues by rule_id, file, and line.
    
    Args:
        issues: List of issues to deduplicate
        
    Returns:
        Deduplicated list of issues
    """
    seen: set[tuple[str, str, int]] = set()
    result: list[ReviewIssue] = []
    
    for issue in issues:
        key = (issue.rule_id, issue.file, issue.line)
        if key not in seen:
            seen.add(key)
            result.append(issue)
    
    return result
