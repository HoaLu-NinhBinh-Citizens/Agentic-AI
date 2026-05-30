"""Code review workflow — review, suggest fixes, apply interactively, report.

DEPRECATED: This module is being replaced by src.application.workflows.unified.
Use UnifiedReviewEngine for new code.

This module provides end-to-end code review with fix application.
It supports two modes:
1. Unified mode: Uses UnifiedReviewEngine for ML-powered analysis
2. Legacy mode: Uses local regex patterns (backward compatibility)

The unified mode is preferred but falls back to legacy mode if unavailable.
"""

from __future__ import annotations

import logging
import uuid
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Warn when imported directly
warnings.warn(
    "code_review.workflow is deprecated. Use unified.UnifiedReviewEngine instead.",
    DeprecationWarning,
    stacklevel=2
)

from src.core.fix_engine.models import (
    Fix,
    FixBatch,
    FixSeverity,
    FixStatus,
    ReviewFinding,
    build_old_text,
    build_new_text,
)
from src.core.fix_engine.apply_fix import ApplyFixTool
from src.interfaces.tui.fix_panel import FixPanel

logger = logging.getLogger(__name__)

# Try to import unified pipeline (graceful degradation)
try:
    from src.application.workflows.unified import (
        UnifiedReviewEngine,
        ReviewEngineConfig,
        Finding,
        FindingSeverity,
    )
    UNIFIED_AVAILABLE = True
except ImportError:
    UNIFIED_AVAILABLE = False
    logger.warning("UnifiedReviewEngine not available, using legacy mode")


@dataclass
class ReviewWorkflowResult:
    """Result of a complete review workflow."""
    files_reviewed: int
    total_findings: int
    errors: int
    warnings: int
    info: int
    fix_batch: FixBatch
    duration_seconds: float = 0.0


class CodeReviewWorkflow:
    """End-to-end code review with fix application.

    Supports two modes:
    - Unified mode: Uses UnifiedReviewEngine for comprehensive ML-powered analysis
    - Legacy mode: Uses local regex patterns for backward compatibility

    Args:
        workspace_root: Root directory for the workspace
        use_unified: Force use of unified engine (default: auto-detect)
    """

    def __init__(
        self,
        workspace_root: Optional[str] = None,
        use_unified: Optional[bool] = None,
    ):
        self._workspace_root = workspace_root
        self._fix_tool = ApplyFixTool(workspace_root)
        self._panel = FixPanel(workspace_root)

        # Determine mode: use_unified=None means auto-detect
        if use_unified is None:
            self._use_unified = UNIFIED_AVAILABLE
        else:
            self._use_unified = use_unified and UNIFIED_AVAILABLE

        if not self._use_unified and not UNIFIED_AVAILABLE:
            warnings.warn(
                "UnifiedReviewEngine not available. Using legacy regex-based analysis. "
                "Install required dependencies for ML-powered analysis.",
                UserWarning,
                stacklevel=2,
            )
        elif self._use_unified:
            logger.info("Using UnifiedReviewEngine for code review")
        else:
            logger.info("Using legacy regex-based analysis")

    async def review_and_fix(
        self,
        files: list[str],
        focus_areas: Optional[list[str]] = None,
        auto_apply: bool = False,
        dry_run: bool = True,
        interactive: bool = True,
    ) -> ReviewWorkflowResult:
        """Run review on files, collect findings, apply fixes.

        Args:
            files: List of file paths to review
            focus_areas: Areas to focus on (e.g. ["security", "code_quality"])
            auto_apply: Automatically apply safe fixes without prompting
            dry_run: Validate fixes without applying
            interactive: Show interactive TUI panel

        Returns:
            ReviewWorkflowResult with all findings and applied fixes
        """
        import time
        start_time = time.time()

        if focus_areas is None:
            focus_areas = ["code_quality", "security", "best_practices"]

        logger.info("Starting review of %d files", len(files))

        # Use unified engine if available
        if self._use_unified and UNIFIED_AVAILABLE:
            findings = await self._collect_findings_unified(files, focus_areas)
        else:
            findings = await self._collect_findings_legacy(files, focus_areas)

        fixes = self._convert_findings_to_fixes(findings)
        fixes = self._deduplicate_fixes(fixes)

        logger.info("Collected %d findings", len(fixes))

        errors = sum(1 for f in fixes if f.severity == FixSeverity.ERROR)
        warnings = sum(1 for f in fixes if f.severity == FixSeverity.WARNING)
        info_count = sum(1 for f in fixes if f.severity == FixSeverity.INFO)

        batch = FixBatch()
        for fix in fixes:
            batch.add(fix)
        batch.update_counters()

        if dry_run:
            logger.info("Dry run mode - validating fixes only")
            for fix in fixes:
                valid, msg = self._fix_tool.validate_fix(
                    fix.file_path, fix.old_text, fix.new_text
                )
                if not valid:
                    fix.status = FixStatus.SKIPPED

        elif interactive and fixes:
            self._panel.load_fixes(fixes)
            if auto_apply:
                self._panel._interactive = False
                batch = self._apply_auto_safe_fixes(fixes)
            else:
                batch = self._panel.interactive_loop()

        elif auto_apply and fixes:
            batch = self._apply_auto_safe_fixes(fixes)

        duration = time.time() - start_time

        return ReviewWorkflowResult(
            files_reviewed=len(files),
            total_findings=len(fixes),
            errors=errors,
            warnings=warnings,
            info=info_count,
            fix_batch=batch,
            duration_seconds=duration,
        )

    async def _collect_findings_unified(
        self,
        files: list[str],
        focus_areas: list[str],
    ) -> list[ReviewFinding]:
        """Collect findings using UnifiedReviewEngine.

        Args:
            files: File paths to analyze
            focus_areas: Focus areas for detection

        Returns:
            List of ReviewFinding objects
        """
        from src.core.fix_engine.models import FixSeverity

        # Map focus areas to unified format
        unified_areas = self._map_focus_areas(focus_areas)

        try:
            config = ReviewEngineConfig(
                focus_areas=unified_areas,
                output_format="json",
                confidence_threshold=0.5,
            )
            engine = UnifiedReviewEngine(config)
            result = await engine.review(files)

            # Convert Unified Finding to ReviewFinding
            findings: list[ReviewFinding] = []
            for finding in result.findings:
                severity = self._map_severity(finding.severity)
                findings.append(ReviewFinding(
                    file_path=finding.file,
                    line=finding.line,
                    rule_id=finding.rule_id,
                    message=finding.message,
                    severity=severity,
                    suggested_fix=finding.fix,
                    confidence=finding.confidence,
                ))

            logger.info(
                "UnifiedReviewEngine found %d findings",
                len(findings)
            )
            return findings

        except Exception as exc:
            logger.warning(
                "UnifiedReviewEngine failed: %s. Falling back to legacy mode.",
                exc
            )
            warnings.warn(
                f"UnifiedReviewEngine failed with: {exc}. "
                "Using legacy regex-based analysis.",
                UserWarning,
                stacklevel=2,
            )
            return await self._collect_findings_legacy(files, focus_areas)

    def _map_focus_areas(self, focus_areas: list[str]) -> list[str]:
        """Map legacy focus areas to unified focus areas.

        Args:
            focus_areas: Legacy focus areas

        Returns:
            Unified focus areas
        """
        mapping = {
            "code_quality": ["quality"],
            "security": ["security"],
            "best_practices": ["quality"],
            "performance": ["quality"],
        }
        unified: set[str] = set()
        for area in focus_areas:
            unified.update(mapping.get(area, [area]))
        return list(unified) if unified else ["security", "quality"]

    def _map_severity(self, severity: "FindingSeverity") -> FixSeverity:
        """Map unified severity to legacy severity.

        Args:
            severity: Unified FindingSeverity

        Returns:
            Legacy FixSeverity
        """
        mapping = {
            FindingSeverity.ERROR: FixSeverity.ERROR,
            FindingSeverity.WARNING: FixSeverity.WARNING,
            FindingSeverity.INFO: FixSeverity.INFO,
            FindingSeverity.HINT: FixSeverity.INFO,
        }
        return mapping.get(severity, FixSeverity.WARNING)

    # ─── Legacy Analysis (Backward Compatibility) ────────────────────────────────

    async def _collect_findings_legacy(
        self, files: list[str], focus_areas: list[str]
    ) -> list[ReviewFinding]:
        """Collect findings using legacy regex patterns (backward compatibility).

        DEPRECATED: This method is kept for backward compatibility.
        Use _collect_findings_unified for ML-powered analysis.

        Args:
            files: File paths to analyze
            focus_areas: Areas to focus on

        Returns:
            List of ReviewFinding objects
        """
        warnings.warn(
            "Using legacy regex-based analysis. "
            "Consider using UnifiedReviewEngine for better results.",
            DeprecationWarning,
            stacklevel=2,
        )

        findings: list[ReviewFinding] = []

        for file_path in files:
            file_findings = await self._analyze_file_legacy(file_path, focus_areas)
            findings.extend(file_findings)

        return findings

    async def _analyze_file_legacy(
        self, file_path: str, focus_areas: list[str]
    ) -> list[ReviewFinding]:
        """Analyze a single file for issues using legacy regex patterns.

        DEPRECATED: Internal legacy method. Use UnifiedReviewEngine instead.

        Args:
            file_path: Path to file to analyze
            focus_areas: Areas to focus on

        Returns:
            List of findings
        """
        findings: list[ReviewFinding] = []
        findings.extend(await self._static_analysis_legacy(file_path))

        if "security" in focus_areas:
            findings.extend(await self._security_scan_legacy(file_path))

        return findings

    async def _static_analysis_legacy(self, file_path: str) -> list[ReviewFinding]:
        """Perform static analysis on file."""
        findings: list[ReviewFinding] = []
        import re

        try:
            full_path = Path(file_path)
            if not full_path.exists():
                return findings

            content = full_path.read_text(encoding="utf-8")
            lines = content.split("\n")

            rules = [
                (r"(?<![a-zA-Z_])(0x[0-9A-Fa-f]+|[2-9]\d{1,})(?![xXa-zA-Z0-9])",
                 "possible_magic_number", FixSeverity.WARNING,
                 "Magic number detected - consider using a named constant"),
                (r"//.*(TODO|FIXME|XXX|HACK)", "unresolved_todo",
                 FixSeverity.INFO, "Unresolved TODO/FIXME comment"),
                (r"while\s*\(\s*(1|true)\s*\)", "infinite_loop",
                 FixSeverity.ERROR, "Potential infinite loop without timeout"),
            ]

            for i, line in enumerate(lines, 1):
                for pattern, rule_id, severity, message in rules:
                    if re.search(pattern, line, re.IGNORECASE):
                        findings.append(ReviewFinding(
                            file_path=file_path,
                            line=i,
                            rule_id=rule_id,
                            message=f"{message} (line {i})",
                            severity=severity,
                            confidence=0.8,
                        ))

        except Exception as exc:
            logger.warning("Static analysis failed for %s: %s", file_path, exc)

        return findings

    async def _security_scan_legacy(self, file_path: str) -> list[ReviewFinding]:
        """Perform basic security scan on file."""
        findings: list[ReviewFinding] = []
        import re

        try:
            full_path = Path(file_path)
            if not full_path.exists():
                return findings

            content = full_path.read_text(encoding="utf-8")
            lines = content.split("\n")

            security_rules = [
                (r"password\s*=\s*['\"][^'\"]+['\"]", "hardcoded_password",
                 FixSeverity.ERROR, "Hardcoded password detected"),
                (r"api[_-]?key\s*=\s*['\"][^'\"]+['\"]", "hardcoded_api_key",
                 FixSeverity.ERROR, "Hardcoded API key detected"),
                (r"secret\s*=\s*['\"][^'\"]+['\"]", "hardcoded_secret",
                 FixSeverity.WARNING, "Hardcoded secret detected"),
                (r"eval\s*\(", "dangerous_eval",
                 FixSeverity.ERROR, "Use of eval() is dangerous"),
                (r"exec\s*\(", "dangerous_exec",
                 FixSeverity.ERROR, "Use of exec() is dangerous"),
            ]

            for i, line in enumerate(lines, 1):
                for pattern, rule_id, severity, message in security_rules:
                    if re.search(pattern, line, re.IGNORECASE):
                        findings.append(ReviewFinding(
                            file_path=file_path,
                            line=i,
                            rule_id=rule_id,
                            message=message,
                            severity=severity,
                            confidence=0.9,
                        ))

        except Exception as exc:
            logger.warning("Security scan failed for %s: %s", file_path, exc)

        return findings

    def _convert_findings_to_fixes(self, findings: list[ReviewFinding]) -> list[Fix]:
        """Convert ReviewAgent findings to Fix objects with actual old_text/new_text."""
        fixes: list[Fix] = []

        for finding in findings:
            # Extract actual code from file
            old_text = build_old_text(finding.file_path, finding.line, finding.rule_id)
            new_text = (
                finding.suggested_fix
                if finding.suggested_fix
                else build_new_text(finding.rule_id, old_text)
            )

            fix = Fix(
                id=str(uuid.uuid4())[:8],
                file_path=finding.file_path,
                line_start=finding.line,
                line_end=finding.line,
                old_text=old_text,
                new_text=new_text,
                reason=finding.message,
                rule_id=finding.rule_id,
                severity=finding.severity,
                confidence=finding.confidence,
                created_by="static_analysis",
            )
            fixes.append(fix)

        return fixes

    def _deduplicate_fixes(self, fixes: list[Fix]) -> list[Fix]:
        """Remove duplicate/overlapping fixes."""
        seen: dict[tuple[str, int, str], Fix] = {}
        unique: list[Fix] = []

        for fix in fixes:
            key = (fix.file_path, fix.line_start, fix.rule_id)
            if key not in seen:
                seen[key] = fix
                unique.append(fix)
            elif fix.confidence > seen[key].confidence:
                seen[key] = fix
                unique[unique.index(seen[key])] = fix

        return unique

    def _apply_auto_safe_fixes(self, fixes: list[Fix]) -> FixBatch:
        """Apply fixes that are safe to auto-apply (INFO severity, high confidence)."""
        safe_fixes = [
            f for f in fixes
            if f.severity == FixSeverity.INFO and f.confidence >= 0.9
        ]

        batch = self._fix_tool.apply_batch(safe_fixes)
        for fix in fixes:
            batch.add(fix)

        batch.update_counters()
        return batch
