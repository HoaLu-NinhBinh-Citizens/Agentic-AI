"""Cursor-style /fix command handler.

This module provides the FixCommandParser and FixCommandExecutor for handling
Cursor-style /fix commands like `/fix @src/app.py:42`.

Example commands:
    /fix @src/main.py:42
    /fix @src/main.py:42:50
    /fix @src/main.py:42 --dry-run
    /fix @src/main.py:42 --rule=ML001
    /fix @src/main.py --apply
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.interfaces.cli.commands.slash import CommandResult
from src.core.fix_engine.apply_fix import ApplyFixTool


# ─── Data Classes ────────────────────────────────────────────────────────────


@dataclass
class FixCommand:
    """Parsed /fix command."""
    file_path: str
    line_start: int | None = None
    line_end: int | None = None
    rule_id: str | None = None
    dry_run: bool = False
    preview: bool = True
    interactive: bool = False
    apply: bool = False
    focus_areas: list[str] = field(default_factory=list)


@dataclass
class FixCommandResult:
    """Result of a /fix command execution."""
    success: bool
    output: str
    findings_count: int = 0
    applied_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    errors: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def to_command_result(self) -> CommandResult:
        """Convert to CommandResult for CLI compatibility."""
        return CommandResult(
            success=self.success,
            output=self.output,
            errors=self.errors,
            data={
                "findings_count": self.findings_count,
                "applied_count": self.applied_count,
                "failed_count": self.failed_count,
                "skipped_count": self.skipped_count,
                **self.data,
            },
        )


# ─── Parser ──────────────────────────────────────────────────────────────────


class FixCommandParser:
    """Parse /fix commands like `/fix @src/app.py:42`."""

    # Pattern: /fix @filename[:line[:end_line]] [options]
    PATTERN = re.compile(
        r"^/fix\s+@(?P<file>[^\s:]+)"
        r"(?::(?P<line>\d+))?"
        r"(?::(?P<end_line>\d+))?"
        r"(?:\s+(?P<options>.*))?$"
    )

    # Pattern for rule ID extraction
    RULE_PATTERN = re.compile(r"--rule=(ML\d+|SEC\d+|QUAL\d+|EMB\d+|CRASH\d+|ASSERT\d+)")

    def parse(self, raw: str) -> FixCommand | None:
        """Parse /fix command string.

        Args:
            raw: Raw command string like "/fix @src/main.py:42 --dry-run"

        Returns:
            FixCommand if parsing succeeds, None otherwise
        """
        match = self.PATTERN.match(raw.strip())
        if not match:
            return None

        groups = match.groupdict()
        options_str = groups.get("options") or ""

        return FixCommand(
            file_path=groups["file"],
            line_start=int(groups["line"]) if groups["line"] else None,
            line_end=int(groups["end_line"]) if groups["end_line"] else None,
            rule_id=self._extract_rule(options_str),
            dry_run=self._has_flag(options_str, "--dry-run"),
            preview=not self._has_flag(options_str, "--no-preview"),
            interactive=self._has_flag(options_str, "--interactive") or self._has_flag(options_str, "-i"),
            apply=self._has_flag(options_str, "--apply"),
            focus_areas=self._extract_focus(options_str),
        )

    def _has_flag(self, options: str, flag: str) -> bool:
        """Check if a flag is present in options."""
        return flag in options

    def _extract_rule(self, options: str) -> str | None:
        """Extract rule ID from options like --rule=ML001."""
        match = self.RULE_PATTERN.search(options)
        return match.group(1) if match else None

    def _extract_focus(self, options: str) -> list[str]:
        """Extract focus areas from --focus=area1,area2."""
        match = re.search(r"--focus=([\w,]+)", options)
        if match:
            return [f.strip() for f in match.group(1).split(",")]
        return []


# ─── Executor ─────────────────────────────────────────────────────────────────


class FixCommandExecutor:
    """Execute /fix command using the unified review pipeline."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.fixer = ApplyFixTool(str(workspace_root))
        self._parser = FixCommandParser()

    async def execute(self, cmd: FixCommand) -> FixCommandResult:
        """Execute parsed fix command.

        Args:
            cmd: Parsed FixCommand

        Returns:
            FixCommandResult with execution details
        """
        try:
            # Validate file path
            file_path = self.workspace_root / cmd.file_path
            if not file_path.exists():
                return FixCommandResult(
                    success=False,
                    output=f"File not found: {cmd.file_path}",
                    errors=[f"File does not exist: {cmd.file_path}"],
                )

            # Run review to find findings
            findings = await self._find_finding_at_line(
                file_path=str(file_path),
                line=cmd.line_start,
                rule_id=cmd.rule_id,
            )

            if not findings:
                return FixCommandResult(
                    success=True,
                    output=f"No findings found at {cmd.file_path}"
                           + (f":{cmd.line_start}" if cmd.line_start else ""),
                    findings_count=0,
                )

            # Build output
            output_lines = []
            output_lines.append(f"## Found {len(findings)} Finding(s)\n")
            output_lines.append(f"**File:** `{cmd.file_path}`")
            if cmd.line_start:
                output_lines.append(f"**Line:** {cmd.line_start}")
            if cmd.rule_id:
                output_lines.append(f"**Rule:** {cmd.rule_id}")
            output_lines.append("")

            # Use interactive confirmation flow if interactive mode enabled
            if cmd.interactive and len(findings) > 1:
                return await self._execute_interactive(cmd, findings, output_lines)

            applied_count = 0
            failed_count = 0

            for i, finding in enumerate(findings, 1):
                output_lines.append(f"### {i}. {finding.rule_id}")
                output_lines.append(f"**Severity:** {finding.severity.value}")
                output_lines.append(f"**Message:** {finding.message}")
                output_lines.append(f"**Confidence:** {finding.confidence:.0%}")

                if finding.context:
                    output_lines.append(f"\n```\n{finding.context[:200]}\n```")

                if finding.fix:
                    output_lines.append(f"\n**Suggested Fix:**\n```\n{finding.fix[:300]}\n```")

                # Generate preview
                if cmd.preview and finding.fix:
                    preview = await self._preview_fix(finding)
                    if preview:
                        output_lines.append(f"\n**Preview:**\n```diff\n{preview}\n```")

                # Apply fix if requested
                if cmd.apply and not cmd.dry_run:
                    result = await self._apply_fix(finding)
                    if result["success"]:
                        applied_count += 1
                        output_lines.append(f"\n✓ Applied fix successfully")
                    else:
                        failed_count += 1
                        output_lines.append(f"\n✗ Failed: {result.get('error', 'Unknown error')}")

                output_lines.append("\n---")

            # Summary
            output_lines.append("\n### Summary")
            output_lines.append(f"- **Findings:** {len(findings)}")
            output_lines.append(f"- **Applied:** {applied_count}")
            output_lines.append(f"- **Failed:** {failed_count}")

            if cmd.dry_run:
                output_lines.append("\n*Dry run mode - no changes made*")

            return FixCommandResult(
                success=True,
                output="\n".join(output_lines),
                findings_count=len(findings),
                applied_count=applied_count,
                failed_count=failed_count,
                data={
                    "file": cmd.file_path,
                    "line": cmd.line_start,
                    "rule_id": cmd.rule_id,
                    "dry_run": cmd.dry_run,
                },
            )

        except Exception as e:
            return FixCommandResult(
                success=False,
                output=f"Error executing /fix command: {e}",
                errors=[str(e)],
            )

    async def _execute_interactive(
        self,
        cmd: FixCommand,
        findings: list,
        output_lines: list[str],
    ) -> FixCommandResult:
        """Execute fix command with interactive confirmation flow.

        Args:
            cmd: Parsed FixCommand
            findings: List of findings to process
            output_lines: Output lines to append to

        Returns:
            FixCommandResult with execution details
        """
        from src.interfaces.cli.commands.interactive_confirm import (
            InteractiveConfirmationFlow,
            ConsolePromptProvider,
        )

        output_lines.append("\n### Interactive Confirmation Mode\n")

        # Convert findings to ReviewIssue-like objects for confirmation flow
        issues = [self._finding_to_issue(f) for f in findings]

        # Create confirmation flow
        flow = InteractiveConfirmationFlow(
            prompt_provider=ConsolePromptProvider(),
        )

        async def apply_func(issue):
            """Apply fix for an issue."""
            result = await self._apply_finding_fix(issue)
            return result.get("success", False)

        # Run batch confirmation
        result = await flow.run_batch(issues, apply_func)

        # Add results to output
        output_lines.append(f"- **Found:** {len(findings)}")
        output_lines.append(f"- **Applied:** {result.applied_count}")
        output_lines.append(f"- **Skipped:** {result.skipped_count}")
        output_lines.append(f"- **Failed:** {result.failed_count}")

        if result.was_aborted:
            output_lines.append("\n*Session aborted by user*")

        return FixCommandResult(
            success=True,
            output="\n".join(output_lines),
            findings_count=len(findings),
            applied_count=result.applied_count,
            failed_count=result.failed_count,
            skipped_count=result.skipped_count,
            data={
                "file": cmd.file_path,
                "line": cmd.line_start,
                "interactive": True,
            },
        )

    def _finding_to_issue(self, finding) -> "ReviewIssue":
        """Convert a Finding to ReviewIssue for confirmation flow."""
        from src.domain.models.review_issue import ReviewIssue, CodeEvidence, FixOption, Severity

        # Extract old/new code from finding
        evidence = CodeEvidence(
            file=finding.file,
            line_start=finding.line,
            line_end=finding.end_line,
            old_code=finding.context or "",
            new_code=finding.fix or "",
        )

        fix_option = FixOption(
            id=f"fix-{finding.rule_id}-{finding.line}",
            title=f"Fix {finding.rule_id}",
            description=finding.message,
            old_code=finding.context or "",
            new_code=finding.fix or "",
            risk=Severity.MEDIUM,
            confidence=finding.confidence,
        )

        return ReviewIssue(
            id=finding.rule_id,
            rule_id=finding.rule_id,
            severity=finding.severity,
            file=finding.file,
            line=finding.line,
            end_line=finding.end_line,
            title=finding.message[:80] if finding.message else f"{finding.rule_id} issue",
            message=finding.message,
            explanation=finding.context or "",
            evidence=evidence,
            fixes=[fix_option],
            confidence=finding.confidence,
            tags=[],
            detector=finding.detector,
        )

    async def _apply_finding_fix(self, issue) -> dict[str, Any]:
        """Apply a fix from a ReviewIssue-like object.

        Args:
            issue: ReviewIssue or similar object

        Returns:
            Dict with success status and optional error
        """
        try:
            from src.core.fix_engine.models import Fix, FixSeverity

            # Map severity (normalize to lowercase for matching)
            severity_value = issue.severity.value.lower() if hasattr(issue.severity, 'value') else str(issue.severity).lower()
            severity_map = {
                "critical": FixSeverity.ERROR,
                "error": FixSeverity.ERROR,
                "high": FixSeverity.ERROR,
                "warning": FixSeverity.WARNING,
                "medium": FixSeverity.WARNING,
                "low": FixSeverity.INFO,
                "info": FixSeverity.INFO,
            }
            fix_severity = severity_map.get(severity_value, FixSeverity.WARNING)

            # Extract old/new code from issue
            old_code = ""
            new_code = ""

            if hasattr(issue, 'evidence') and issue.evidence:
                old_code = issue.evidence.old_code or ""
                new_code = issue.evidence.new_code or ""

            if not new_code and hasattr(issue, 'fixes') and issue.fixes:
                for fix in issue.fixes:
                    if hasattr(fix, 'new_code') and fix.new_code:
                        new_code = fix.new_code
                        old_code = getattr(fix, 'old_code', "") or old_code
                        break

            fix = Fix(
                id=issue.id if hasattr(issue, 'id') else f"fix-{issue.rule_id}-{issue.line}",
                file_path=issue.file,
                line_start=issue.line,
                line_end=issue.end_line,
                old_text=old_code,
                new_text=new_code,
                reason=issue.message if hasattr(issue, 'message') else "",
                rule_id=issue.rule_id,
                severity=fix_severity,
            )

            result = self.fixer.apply_fix(fix)

            return {
                "success": result.success,
                "error": result.error if not result.success else None,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    async def _find_finding_at_line(
        self,
        file_path: str,
        line: int | None,
        rule_id: str | None = None,
    ) -> list:
        """Find findings at specific line from unified pipeline.

        Args:
            file_path: Path to file to analyze
            line: Specific line number, or None for entire file
            rule_id: Optional rule ID to filter by

        Returns:
            List of Finding objects
        """
        from src.application.workflows.unified.pipeline import UnifiedReviewPipeline, PipelineConfig
        from src.application.workflows.unified.detector_base import Finding

        config = PipelineConfig(
            enable_ml=True,
            enable_security=True,
            enable_quality=True,
            enable_embedded=True,
            min_confidence=0.5,
        )

        pipeline = UnifiedReviewPipeline(config)

        try:
            issues = await pipeline.analyze([Path(file_path)])

            findings: list[Finding] = []
            for issue in issues:
                # Filter by line if specified
                if line is not None:
                    if issue.line != line:
                        continue

                # Filter by rule if specified
                if rule_id is not None:
                    if issue.rule_id != rule_id:
                        continue

                # Convert ReviewIssue to Finding for compatibility
                finding = self._issue_to_finding(issue)
                findings.append(finding)

            return findings

        except Exception as e:
            # Fallback: return empty list on error
            return []

    def _issue_to_finding(self, issue) -> "Finding":
        """Convert a ReviewIssue to a Finding for compatibility."""
        from src.application.workflows.unified.detector_base import Finding

        return Finding(
            rule_id=issue.rule_id,
            rule_name=issue.rule_id,
            severity=issue.severity,
            file=issue.file,
            line=issue.line,
            end_line=issue.line + 1,
            message=issue.message,
            fix=issue.fixes[0].new_code if issue.fixes else "",
            confidence=issue.confidence,
            context=issue.code_snippet if hasattr(issue, 'code_snippet') else "",
            detector=issue.detector,
        )

    async def _preview_fix(self, finding) -> str | None:
        """Generate preview diff for a fix.

        Args:
            finding: Finding with fix suggestion

        Returns:
            Diff string or None
        """
        try:
            file_path = self.workspace_root / finding.file
            if not file_path.exists():
                return None

            content = file_path.read_text(encoding="utf-8")
            lines = content.split("\n")

            line_idx = finding.line - 1
            if 0 <= line_idx < len(lines):
                old_line = lines[line_idx]
                new_line = finding.fix if finding.fix else old_line

                import difflib
                diff = difflib.unified_diff(
                    [old_line + "\n"],
                    [new_line + "\n"],
                    fromfile=f"{finding.file}:{finding.line}",
                    tofile=f"{finding.file}:{finding.line} (fixed)",
                    lineterm="",
                )
                return "".join(diff)

            return None

        except Exception:
            return None

    async def _apply_fix(self, finding) -> dict[str, Any]:
        """Apply a fix for a finding.

        Args:
            finding: Finding to fix

        Returns:
            Dict with success status and optional error
        """
        try:
            from src.core.fix_engine.models import Fix, FixSeverity

            # Convert Finding to Fix
            severity_map = {
                "critical": FixSeverity.ERROR,
                "high": FixSeverity.ERROR,
                "medium": FixSeverity.WARNING,
                "low": FixSeverity.INFO,
            }
            fix_severity = severity_map.get(finding.severity.value, FixSeverity.WARNING)

            fix = Fix(
                id=f"fix-{finding.rule_id}-{finding.line}",
                file_path=finding.file,
                line_start=finding.line,
                line_end=finding.end_line,
                old_text=finding.context if finding.context else "",
                new_text=finding.fix if finding.fix else "",
                reason=finding.message,
                rule_id=finding.rule_id,
                severity=fix_severity,
            )

            result = self.fixer.apply_fix(fix)

            return {
                "success": result.success,
                "error": result.error if not result.success else None,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }


# ─── CLI Integration ──────────────────────────────────────────────────────────


async def handle_fix_command(ctx, /):
    """CLI handler for /fix command.

    Integrates with the existing slash command system.

    Args:
        ctx: CommandContext with workspace_root and raw command info

    Returns:
        CommandResult for CLI output
    """
    # Late import to avoid circular dependency
    from src.interfaces.cli.commands.slash import CommandContext as CC

    if not isinstance(ctx, CC):
        # If passed as dict, convert
        ctx = CC(
            workspace_root=ctx.get("workspace_root", "."),
            files=ctx.get("files", []),
            lines=ctx.get("lines", []),
        )

    parser = FixCommandParser()
    executor = FixCommandExecutor(Path(ctx.workspace_root))

    # Reconstruct raw command from context
    raw = f"/fix @{ctx.primary_file or ''}"
    if ctx.primary_line:
        raw += f":{ctx.primary_line}"

    # Add flags from context
    if ctx.raw_flags.get("dry_run") or ctx.raw_flags.get("dry-run"):
        raw += " --dry-run"
    if ctx.raw_flags.get("apply"):
        raw += " --apply"
    if ctx.raw_flags.get("interactive") or ctx.raw_flags.get("i"):
        raw += " --interactive"
    if ctx.raw_flags.get("rule"):
        raw += f" --rule={ctx.raw_flags.get('rule')}"

    cmd = parser.parse(raw)

    if not cmd:
        return CommandResult(
            success=False,
            output="Invalid /fix command. Usage:\n"
                   "  /fix @filename[:line] [--dry-run] [--apply] [--rule=RULE]\n\n"
                   "Examples:\n"
                   "  /fix @src/main.py:42\n"
                   "  /fix @src/main.py:42 --dry-run\n"
                   "  /fix @src/main.py --rule=ML001",
        )

    result = await executor.execute(cmd)
    return result.to_command_result()
