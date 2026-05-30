"""Code review workflow — review, suggest fixes, apply interactively, report."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.core.fix_engine.models import (
    Fix,
    FixBatch,
    FixSeverity,
    FixStatus,
    ReviewFinding,
)
from src.core.fix_engine.apply_fix import ApplyFixTool
from src.interfaces.tui.fix_panel import FixPanel

logger = logging.getLogger(__name__)


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
    """End-to-end code review with fix application."""

    def __init__(self, workspace_root: Optional[str] = None):
        self._workspace_root = workspace_root
        self._fix_tool = ApplyFixTool(workspace_root)
        self._panel = FixPanel(workspace_root)

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

        findings = await self._collect_findings(files, focus_areas)
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

    async def _collect_findings(
        self, files: list[str], focus_areas: list[str]
    ) -> list[ReviewFinding]:
        """Collect findings from static analysis of files."""
        findings: list[ReviewFinding] = []

        for file_path in files:
            file_findings = await self._analyze_file(file_path, focus_areas)
            findings.extend(file_findings)

        return findings

    async def _analyze_file(
        self, file_path: str, focus_areas: list[str]
    ) -> list[ReviewFinding]:
        """Analyze a single file for issues."""
        findings: list[ReviewFinding] = []
        findings.extend(await self._static_analysis(file_path))

        if "security" in focus_areas:
            findings.extend(await self._security_scan(file_path))

        return findings

    async def _static_analysis(self, file_path: str) -> list[ReviewFinding]:
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

    async def _security_scan(self, file_path: str) -> list[ReviewFinding]:
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
        """Convert ReviewAgent findings to Fix objects."""
        fixes: list[Fix] = []

        for finding in findings:
            fix = Fix(
                id=str(uuid.uuid4())[:8],
                file_path=finding.file_path,
                line_start=finding.line,
                line_end=finding.line,
                old_text="",  # Static analysis doesn't provide exact fix
                new_text=finding.suggested_fix or "",
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
