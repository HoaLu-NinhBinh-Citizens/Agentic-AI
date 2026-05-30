"""Slash command parser and dispatcher — mimics Cursor's /command syntax.

Supports:
    /fix [@file[:line]] [--dry-run] [--apply] [--interactive]  — Show and apply fixes
    /fix @file:line:end_line [options]                       — Range-based fix
    /fix @file --rule=ML001                                  — Rule-specific fix
    /review [--files=FILES] [--focus=AREA]                    — Run code review
    /explain [@symbol]                                        — Explain a symbol, class, or function
    /stats                                                   — Show review statistics
    /rules [--enable=RULES] [--disable=RULES]                — Manage rule configuration
    /help                                                    — Show available commands

Syntax:
    /command arg1 arg2 --flag=value --flag2
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import re
import shlex
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from src.infrastructure.patching import (
    ASTPatchEngine,
    Patch as ASTPatch,
    PatchResult as ASTPatchResult,
    create_patch_engine,
)

# Import Color for formatter
from src.interfaces.conversation.formatters import Color


# ─── Command types ──────────────────────────────────────────────────────────

class CommandCategory(Enum):
    REVIEW = "review"
    FIX = "fix"
    NAVIGATE = "navigate"
    CONFIG = "config"
    UTILITY = "utility"


@dataclass
class CommandContext:
    """Context passed to every command handler."""
    workspace_root: str
    files: list[str] = field(default_factory=list)
    lines: list[int] = field(default_factory=list)
    raw_args: str = ""
    raw_flags: dict[str, str] = field(default_factory=dict)
    config_path: Optional[str] = None

    @property
    def primary_file(self) -> Optional[str]:
        return self.files[0] if self.files else None

    @property
    def primary_line(self) -> Optional[int]:
        return self.lines[0] if self.lines else None


@dataclass
class CommandResult:
    """Result returned by a command handler."""
    success: bool
    output: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "errors": self.errors,
            "warnings": self.warnings,
            **self.data,
        }


@dataclass
class Command:
    """A registered slash command."""
    name: str
    description: str
    category: CommandCategory
    aliases: list[str] = field(default_factory=list)
    handler: Callable[[CommandContext], Any] = field(default=None)
    examples: list[str] = field(default_factory=list)


# ─── Fix Applicator ─────────────────────────────────────────────────────────


class FixApplicator:
    """Applies code fixes to files with backup support.

    This class handles applying suggested fixes to source files:
    1. Creates a backup of the original file
    2. Uses AST-aware patching for safe replacement
    3. Validates syntax after patch application
    4. Returns success/failure status with diff preview
    """

    def __init__(self, backup_dir: str | None = None) -> None:
        """Initialize the fix applicator.

        Args:
            backup_dir: Directory for backups (default: .ai_support/backups)
        """
        self.backup_dir = Path(backup_dir) if backup_dir else Path(".ai_support/backups")
        self._applied_count = 0
        self._failed_count = 0
        self._patch_engine: ASTPatchEngine | None = None

    @property
    def applied_count(self) -> int:
        """Number of fixes successfully applied."""
        return self._applied_count

    @property
    def failed_count(self) -> int:
        """Number of fixes that failed to apply."""
        return self._failed_count

    def _get_patch_engine(self) -> ASTPatchEngine:
        """Get or create the AST patch engine instance."""
        if self._patch_engine is None:
            self._patch_engine = create_patch_engine()
        return self._patch_engine

    async def apply_fix_ast(
        self,
        file_path: Path | str,
        line: int,
        new_code: str,
        old_code: str | None = None,
        create_backup: bool = True,
        dry_run: bool = False,
        language: str = "python",
    ) -> dict:
        """Apply a fix using AST-aware patching with syntax validation.

        Args:
            file_path: Path to the file to fix
            line: Line number (1-based) of the fix
            new_code: The new code to insert
            old_code: Optional old code to replace (for exact matching)
            create_backup: Whether to create a backup first
            dry_run: If True, return diff without applying
            language: Programming language for AST parsing

        Returns:
            Dict with success status, diff, and optional error message
        """
        file_path = Path(file_path)

        try:
            if not file_path.exists():
                return {"success": False, "error": f"File not found: {file_path}"}

            content = file_path.read_text(encoding="utf-8", errors="replace")

            # Find AST node at target position
            engine = self._get_patch_engine()
            column = 0
            node_info = engine.find_node_at_position(content, line, column, language)

            if not node_info:
                return {"success": False, "error": f"Could not find AST node at {file_path}:{line}"}

            # Generate patch
            patch = engine.generate_patch(
                file_path=file_path,
                content=content,
                node_start=node_info.start_point,
                node_end=node_info.end_point,
                new_code=new_code,
            )

            # Generate diff for preview
            patched_content = engine.apply_patch(content, patch)
            diff = engine.generate_diff(content, patched_content)

            if dry_run:
                return {
                    "success": True,
                    "dry_run": True,
                    "diff": patch.to_diff(),
                    "patched_preview": patched_content,
                }

            # Create backup if requested
            if create_backup:
                await self._create_backup(file_path, content.split("\n"))

            # Apply and validate
            result = engine.apply_and_validate(content, patch, language)

            if result.validation_passed:
                file_path.write_text(result.patched_content, encoding="utf-8")
                self._applied_count += 1
                return {
                    "success": True,
                    "patched": result.patched_content,
                    "modified_lines": result.modified_lines,
                }
            else:
                self._failed_count += 1
                return {
                    "success": False,
                    "error": f"Syntax validation failed: {result.error}",
                }

        except PermissionError:
            self._failed_count += 1
            return {"success": False, "error": f"Permission denied: {file_path}"}
        except Exception as e:
            self._failed_count += 1
            return {"success": False, "error": f"Failed to apply fix: {e}"}

    async def apply_fix(
        self,
        file_path: Path | str,
        line: int,
        new_code: str,
        old_code: str | None = None,
        create_backup: bool = True,
    ) -> tuple[bool, str]:
        """Apply a fix to a specific line in a file.

        Args:
            file_path: Path to the file to fix
            line: Line number (1-based) of the fix
            new_code: The new code to insert
            old_code: Optional old code to replace (for exact matching)
            create_backup: Whether to create a backup first

        Returns:
            Tuple of (success: bool, message: str)
        """
        file_path = Path(file_path)

        try:
            # Read original content
            if not file_path.exists():
                return False, f"File not found: {file_path}"

            content = file_path.read_text(encoding="utf-8", errors="replace")
            lines = content.split("\n")

            if line < 1 or line > len(lines):
                return False, f"Line {line} out of range (file has {len(lines)} lines)"

            # Create backup if requested
            if create_backup:
                backup_path = await self._create_backup(file_path, lines)
                if backup_path:
                    await self._ensure_backup_dir()

            # Find and replace the target line
            target_idx = line - 1  # Convert to 0-based index
            if old_code:
                # Find the line containing old_code
                found = False
                for i in range(max(0, target_idx - 2), min(len(lines), target_idx + 3)):
                    if old_code.strip() in lines[i].strip():
                        target_idx = i
                        found = True
                        break
                if not found:
                    return False, f"Could not find old code to replace: {old_code[:50]}..."

            # Apply the fix
            original_line = lines[target_idx]
            lines[target_idx] = new_code

            # Write back
            new_content = "\n".join(lines)
            file_path.write_text(new_content, encoding="utf-8")

            self._applied_count += 1
            return True, f"Applied fix at {file_path}:{line}\n  Old: {original_line.strip()[:50]}...\n  New: {new_code.strip()[:50]}..."

        except PermissionError:
            self._failed_count += 1
            return False, f"Permission denied: {file_path}"
        except Exception as e:
            self._failed_count += 1
            return False, f"Failed to apply fix: {e}"

    async def apply_finding_fix(
        self,
        finding,
        create_backup: bool = True,
        use_ast: bool = True,
    ) -> tuple[bool, str]:
        """Apply a fix from a Finding object using AST-aware patching.

        Args:
            finding: Finding object with file, line, and metadata
            create_backup: Whether to create a backup first
            use_ast: If True, use AST-aware patching (default: True)

        Returns:
            Tuple of (success: bool, message: str)
        """
        file_path = Path(finding.file)
        line = finding.line
        new_code = finding.metadata.get("new_code", "") if finding.metadata else ""

        # If no new_code in metadata, try the fix field
        if not new_code and finding.fix:
            new_code = self._extract_code_from_fix(finding.fix)

        if not new_code:
            return False, "No fix code available in finding"

        old_code = finding.metadata.get("old_code", "") if finding.metadata else None

        # Detect language from file extension
        language = self._detect_language(file_path)

        if use_ast:
            result = await self.apply_fix_ast(
                file_path=file_path,
                line=line,
                new_code=new_code,
                old_code=old_code,
                create_backup=create_backup,
                language=language,
            )
            if result["success"]:
                if result.get("dry_run"):
                    return True, f"Would apply AST patch (dry run):\n{result.get('diff', '')}"
                return True, f"Applied AST fix at {file_path}:{line}"
            else:
                return False, result.get("error", "Unknown error")

        return await self.apply_fix(
            file_path, line, new_code, old_code, create_backup
        )

    def _detect_language(self, file_path: Path) -> str:
        """Detect programming language from file extension."""
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".c": "c",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
        }
        return ext_map.get(file_path.suffix.lower(), "python")

    def _extract_code_from_fix(self, fix_text: str) -> str:
        """Extract code from a fix suggestion string.

        Args:
            fix_text: The fix suggestion text

        Returns:
            Extracted code or empty string
        """
        # Try to find code in markdown code blocks
        code_blocks = re.findall(r"```(?:\w+)?\n(.*?)```", fix_text, re.DOTALL)
        if code_blocks:
            return code_blocks[0].strip()

        # Try to find inline code
        inline = re.findall(r"`([^`]+)`", fix_text)
        if inline:
            return inline[0].strip()

        return fix_text.strip()

    async def _create_backup(self, file_path: Path, lines: list[str]) -> Path | None:
        """Create a backup of the file.

        Args:
            file_path: Original file path
            lines: File content as lines

        Returns:
            Path to backup file, or None if backup failed
        """
        try:
            await self._ensure_backup_dir()
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
            backup_path = self.backup_dir / backup_name

            content = "\n".join(lines)
            backup_path.write_text(content, encoding="utf-8")
            return backup_path
        except Exception:
            return None

    async def _ensure_backup_dir(self) -> None:
        """Ensure backup directory exists."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def get_backup_count(self) -> int:
        """Get number of backup files."""
        if not self.backup_dir.exists():
            return 0
        return len(list(self.backup_dir.iterdir()))


# ─── Builtin commands ────────────────────────────────────────────────────────

async def cmd_review(ctx: CommandContext) -> CommandResult:
    """Run code review on specified files using UnifiedReviewEngine."""
    # Check if unified pipeline is available
    try:
        from src.application.workflows.unified.review_engine import (
            UnifiedReviewEngine,
            ReviewEngineConfig,
        )
    except ImportError as e:
        # Fallback to legacy workflow
        return await _fallback_to_legacy_review(ctx, error_msg=f"Unified pipeline unavailable: {e}")

    files = ctx.files if ctx.files else []
    
    # If no files provided, check workspace for source files
    # Limit to prevent scanning large directories
    if not files:
        from pathlib import Path
        workspace = Path(ctx.workspace_root)
        if workspace.exists() and workspace.is_dir():
            try:
                # Find source files with a limit
                for ext in [".py", ".js", ".ts", ".c", ".cpp"]:
                    source_files = list(workspace.rglob(f"*{ext}"))[:50]  # Limit to 50 files
                    if source_files:
                        files = [str(f) for f in source_files]
                        break
            except Exception:
                pass
        if not files:
            return CommandResult(
                success=True,
                output="No source files found to review. Use /review @file.py to specify files explicitly.",
            )

    focus = ctx.raw_flags.get("focus", "all").split(",")
    if "all" in focus:
        focus = ["security", "quality", "ml", "embedded"]
    auto_apply = "auto" in ctx.raw_flags or ctx.raw_flags.get("mode") == "auto"

    # Normalize focus areas for unified pipeline
    normalized_focus = []
    for f in focus:
        if f in ["security", "quality", "ml", "embedded"]:
            normalized_focus.append(f)
        elif f == "code_quality":
            normalized_focus.append("quality")
        elif f == "best_practices":
            normalized_focus.append("quality")

    config = ReviewEngineConfig(
        focus_areas=normalized_focus or ["security", "quality", "ml"],
        output_format="markdown",
        confidence_threshold=0.5,
    )

    try:
        engine = UnifiedReviewEngine(config)
        # Convert to Path objects
        from pathlib import Path
        file_paths = [Path(f) for f in files]

        result = await engine.review(file_paths, incremental=False)

        output = _format_unified_review_summary(result)
        return CommandResult(
            success=True,
            output=output,
            data={
                "files_reviewed": result.stats.files_scanned,
                "total_findings": len(result.findings),
                "errors": result.stats.errors_count,
                "warnings": result.stats.warnings_count,
                "info": result.stats.info_count,
            },
        )
    except Exception as e:
        import logging
        logging.warning("Unified review failed: %s", e)
        # Fallback to legacy workflow
        return await _fallback_to_legacy_review(ctx, error_msg=f"Unified review failed: {e}")


async def _fallback_to_legacy_review(
    ctx: CommandContext, error_msg: str | None = None
) -> CommandResult:
    """Fallback when unified pipeline is unavailable."""
    return CommandResult(
        success=False,
        output=f"Code review unavailable. Unified pipeline failed: {error_msg or 'Unknown error'}",
    )


async def cmd_fix(ctx: CommandContext) -> CommandResult:
    """Show and apply fixes for a specific file or line using UnifiedReviewEngine.

    Supports interactive mode with --interactive or -i flag for user confirmation
    before applying each fix.

    Enhanced with FixCommandParser for Cursor-style commands:
        /fix @file:line          - Fix at specific line
        /fix @file:line:end      - Fix a range
        /fix @file --rule=ML001  - Rule-specific fix
        /fix @file --dry-run     - Preview without applying
    """
    from pathlib import Path

    is_interactive = "--interactive" in ctx.raw_flags or "-i" in ctx.raw_flags

    if is_interactive:
        return await cmd_fix_interactive(ctx)

    # Use FixCommandParser for enhanced command parsing (late import to avoid circular)
    from src.interfaces.cli.commands.fix import FixCommandParser
    parser = FixCommandParser()

    # Reconstruct raw command for parser
    raw = "/fix"
    if ctx.primary_file:
        raw += f" @{ctx.primary_file}"
        if ctx.primary_line:
            raw += f":{ctx.primary_line}"

    # Add any rule filter
    if ctx.raw_flags.get("rule"):
        raw += f" --rule={ctx.raw_flags.get('rule')}"

    cmd = parser.parse(raw)

    if not cmd:
        return CommandResult(
            success=False,
            output="Usage: /fix @filename[:line[:end_line]] [options]\n"
                   "  /fix @src/main.py:42\n"
                   "  /fix @src/main.py:42:50\n"
                   "  /fix @src/main.py:42 --dry-run\n"
                   "  /fix @src/main.py:42 --rule=ML001\n"
                   "  /fix @src/main.py --apply",
        )

    if not ctx.primary_file:
        return CommandResult(
            success=False,
            output="Usage: /fix @filename[:line]\n"
                   "  /fix @src/main.py:42\n"
                   "  /fix @src/utils.py\n"
                   "Use --apply flag to automatically apply fixes.",
        )

    files = [ctx.primary_file]

    # Check if unified pipeline is available
    try:
        from src.application.workflows.unified.review_engine import (
            UnifiedReviewEngine,
            ReviewEngineConfig,
        )
    except ImportError as e:
        # Fallback to legacy workflow
        return await _fallback_to_legacy_fix(ctx, error_msg=f"Unified pipeline unavailable: {e}")

    config = ReviewEngineConfig(
        focus_areas=["security", "quality", "ml", "embedded"],
        output_format="markdown",
        confidence_threshold=0.5,
    )

    # Initialize fix applicator
    applicator = FixApplicator()
    auto_apply = "--apply" in ctx.raw_flags or ctx.raw_flags.get("apply") == "true"
    explicit_dry_run = "--dry-run" in ctx.raw_flags or ctx.raw_flags.get("dry_run") == "true"
    show_diff = explicit_dry_run or not auto_apply  # Show diffs unless --apply is specified

    try:
        engine = UnifiedReviewEngine(config)
        result = await engine.review([Path(f) for f in files], incremental=False)

        # Filter to specific line if given
        fixes = result.findings
        if ctx.primary_line:
            fixes = [f for f in fixes if f.line == ctx.primary_line]

        # Filter to fixable findings
        fixable = [f for f in fixes if f.fix or (f.metadata and f.metadata.get("new_code"))]

        if not fixable:
            output = "No fixes found for the specified file/line."
            return CommandResult(success=True, output=output)

        output_lines = [f"## Found {len(fixable)} Fixes\n"]

        applied_count = 0
        failed_count = 0

        for fix in fixable:
            sev_icon = {
                "error": "[X]",
                "warning": "[!]",
                "info": "[i]",
            }.get(fix.severity.value, "?")
            output_lines.append(f"{sev_icon} `{fix.file}:{fix.line}` ")
            output_lines.append(f"**[{fix.rule_id}]** {fix.message[:60]}")

            if fix.context:
                output_lines.append(f"```\n{fix.context[:100]}\n```")

            if fix.fix:
                output_lines.append(f"**Fix:** {fix.fix[:80]}")

            # Show diff preview for dry-run mode
            if show_diff:
                result = await applicator.apply_fix_ast(
                    file_path=Path(fix.file),
                    line=fix.line,
                    new_code=applicator._extract_code_from_fix(fix.fix) if fix.fix else "",
                    create_backup=False,
                    dry_run=True,
                )
                if result.get("diff"):
                    output_lines.append(f"\n```diff\n{result['diff']}\n```")
                elif result.get("error"):
                    output_lines.append(f"\nAST patch error: {result['error']}")

            # Apply fix if auto-apply is enabled
            if auto_apply:
                success, msg = await applicator.apply_finding_fix(fix, create_backup=True)
                if success:
                    applied_count += 1
                    output_lines.append(f"\n✓ Applied: {msg}")
                else:
                    failed_count += 1
                    output_lines.append(f"\n✗ Failed: {msg}")

            output_lines.append("")

        # Summary
        if auto_apply:
            output_lines.append(f"\n### Summary\n")
            output_lines.append(f"- Applied: {applied_count}")
            output_lines.append(f"- Failed: {failed_count}")
            output_lines.append(f"- Backups: {applicator.get_backup_count()}")

            if failed_count > 0:
                output_lines.append(f"\n**Warning:** {failed_count} fixes failed. Check backups in `.ai_support/backups/`.")

        return CommandResult(
            success=True,
            output="\n".join(output_lines),
            data={
                "fix_count": len(fixable),
                "applied_count": applied_count if auto_apply else 0,
                "failed_count": failed_count,
                "fixes": [
                    {
                        "id": f.rule_id,
                        "file": f.file,
                        "line": f.line,
                        "rule": f.rule_id,
                        "reason": f.message[:80],
                        "severity": f.severity.value,
                    }
                    for f in fixable
                ],
            },
        )

    except Exception as e:
        import logging
        logging.warning("Unified fix failed: %s", e)
        # Fallback to legacy workflow
        return await _fallback_to_legacy_fix(ctx, error_msg=f"Unified fix failed: {e}")


async def _fallback_to_legacy_fix(
    ctx: CommandContext, error_msg: str | None = None
) -> CommandResult:
    """Fallback when unified pipeline is unavailable."""
    return CommandResult(
        success=False,
        output=f"Fix command unavailable. Unified pipeline failed: {error_msg or 'Unknown error'}",
    )


async def cmd_fix_interactive(ctx: CommandContext) -> CommandResult:
    """Interactive fix mode with user confirmation before each fix.

    Args:
        ctx: Command context with files, lines, and flags

    Returns:
        CommandResult with fix application results
    """
    from pathlib import Path

    if not ctx.primary_file:
        return CommandResult(
            success=False,
            output="Usage: /fix @filename[:line] --interactive\n"
                   "  /fix @src/main.py:42 --interactive\n"
                   "  /fix @src/utils.py -i",
        )

    try:
        from src.application.workflows.unified.review_engine import (
            UnifiedReviewEngine,
            ReviewEngineConfig,
        )
        from src.interfaces.cli.commands.fix_interactive import (
            run_interactive_fix,
            ConsolePromptProvider,
        )
    except ImportError as e:
        return CommandResult(
            success=False,
            output=f"Interactive fix mode unavailable: {e}",
        )

    files = [ctx.primary_file]

    config = ReviewEngineConfig(
        focus_areas=["security", "quality", "ml", "embedded"],
        output_format="markdown",
        confidence_threshold=0.5,
    )

    try:
        engine = UnifiedReviewEngine(config)
        result = await engine.review([Path(f) for f in files], incremental=False)

        fixes = result.findings
        if ctx.primary_line:
            fixes = [f for f in fixes if f.line == ctx.primary_line]

        fixable = [f for f in fixes if f.fix or (f.metadata and f.metadata.get("new_code"))]

        if not fixable:
            return CommandResult(
                success=True,
                output="No fixable issues found for the specified file/line.",
            )

        output_lines = [
            f"## Interactive Fix Mode",
            f"",
            f"Found {len(fixable)} fixable issue(s).",
            f"",
            f"Options:",
            f"  [y] Yes - apply this fix",
            f"  [n] No - skip this fix",
            f"  [a] Yes to all - apply all remaining fixes",
            f"  [q] Quit - skip all remaining fixes",
            f"  [e] Edit - open in editor for manual fix",
            f"  [s] Skip - skip this fix only",
            f"  [h] Help - show more details",
            f"",
        ]

        session_result = await run_interactive_fix(
            fixes=fixable,
            workspace_root=ctx.workspace_root,
            prompt_provider=ConsolePromptProvider(),
        )

        output_lines.append("")
        output_lines.append(f"### Session Summary")
        output_lines.append(f"- Applied: {session_result.applied_count}")
        output_lines.append(f"- Skipped: {session_result.skipped_count}")
        output_lines.append(f"- Total processed: {session_result.total_processed}")

        if session_result.was_aborted:
            output_lines.append("")
            output_lines.append("**Note:** Session was aborted by user.")

        applied = session_result.session.applied_fixes
        if applied:
            output_lines.append("")
            output_lines.append("### Applied Fixes")
            for fix in applied:
                output_lines.append(f"- `{fix.file_path}:{fix.line_start}` [{fix.rule_id}]")

        return CommandResult(
            success=True,
            output="\n".join(output_lines),
            data={
                "fix_count": len(fixable),
                "applied_count": session_result.applied_count,
                "skipped_count": session_result.skipped_count,
                "was_aborted": session_result.was_aborted,
            },
        )

    except Exception as e:
        import logging
        logging.warning("Interactive fix failed: %s", e)
        return CommandResult(
            success=False,
            output=f"Interactive fix failed: {e}",
        )


async def cmd_fix_interactive_enhanced(ctx: CommandContext) -> CommandResult:
    """Enhanced interactive fix with conversation, tradeoff analysis, and risk explanations.

    Args:
        ctx: Command context with files, lines, and flags

    Returns:
        CommandResult with conversational fix results
    """
    from pathlib import Path

    # Parse conversational flags
    auto_critical = "--auto-critical" in ctx.raw_flags or "auto_critical" in ctx.raw_flags
    explain_all = "--explain" in ctx.raw_flags or "explain" in ctx.raw_flags
    tradeoff_analysis = (
        "--tradeoff" in ctx.raw_flags
        or "-t" in ctx.raw_flags
        or "tradeoff" in ctx.raw_flags
    )

    if not ctx.primary_file:
        return CommandResult(
            success=False,
            output="Usage: /fix-chat @filename[:line] [--auto-critical] [--tradeoff]\n"
                   "  /fix-chat @src/main.py:42 --auto-critical\n"
                   "  /fix-chat @src/utils.py -t\n"
                   "  /fix-chat @src/main.py --tradeoff",
        )

    try:
        from src.application.workflows.unified.review_engine import (
            UnifiedReviewEngine,
            ReviewEngineConfig,
        )
        from src.interfaces.conversation.conversational_fix_engine import (
            ConversationalFixEngine,
            ConsoleConversationFormatter,
        )
        from src.core.fix_engine.llm_suggester import LLMSuggester, create_llm_suggester
    except ImportError as e:
        return CommandResult(
            success=False,
            output=f"Conversational fix mode unavailable: {e}",
        )

    files = [ctx.primary_file]

    config = ReviewEngineConfig(
        focus_areas=["security", "quality", "ml", "embedded"],
        output_format="markdown",
        confidence_threshold=0.5,
    )

    # Initialize formatter
    formatter = ConsoleConversationFormatter(use_colors=True)

    try:
        engine = UnifiedReviewEngine(config)
        result = await engine.review([Path(f) for f in files], incremental=False)

        findings = result.findings
        if ctx.primary_line:
            findings = [f for f in findings if f.line == ctx.primary_line]

        if not findings:
            return CommandResult(
                success=True,
                output="No findings found for the specified file/line.",
            )

        # Build output header
        output_lines = [
            formatter._bold(f"{'=' * 60}"),
            formatter._bold("Conversational Fix Mode"),
            formatter._bold(f"{'=' * 60}"),
            "",
            f"Found {len(findings)} finding(s) to review.",
            "",
        ]

        if auto_critical:
            output_lines.append(formatter._color(
                "[Auto] Will apply critical/error fixes automatically", Color.GREEN
            ))
            output_lines.append("")

        if tradeoff_analysis:
            output_lines.append(formatter._color(
                "[Analysis] Will show tradeoff comparisons", Color.CYAN
            ))
            output_lines.append("")

        output_lines.extend([
            "Commands:",
            "  [a] Apply - Apply the suggested fix",
            "  [s] Skip - Skip this finding",
            "  [t] Tradeoff - Compare fix options",
            "  [r] Risk - Explain the risks",
            "  [p] Preview - Show the diff",
            "  [c] Critical - Apply all critical fixes",
            "  [q] Quit - Exit session",
            "  [h] Help - Show all commands",
            "",
            formatter._bold(f"{'=' * 60}"),
            "",
        ])

        # Create conversational engine
        llm_suggester = None
        try:
            llm_suggester = create_llm_suggester()
        except Exception:
            pass  # LLM not required, will use fallback

        fix_engine = ConversationalFixEngine(
            fixer=None,  # Will be set if actual application needed
            llm_suggester=llm_suggester,
            formatter=formatter,
        )

        # Run conversational session
        session_result = await fix_engine.run_session(
            findings=findings,
            workspace_root=ctx.workspace_root,
            auto_critical=auto_critical,
        )

        # Add session results
        output_lines.append("")
        output_lines.append(formatter.format_summary(session_result))

        return CommandResult(
            success=True,
            output="\n".join(output_lines),
            data={
                "total_findings": len(findings),
                "applied_count": session_result.applied_count,
                "skipped_count": session_result.skipped_count,
                "auto_critical": auto_critical,
                "tradeoff_analysis": tradeoff_analysis,
            },
        )

    except Exception as e:
        import logging
        logging.warning("Conversational fix failed: %s", e)
        return CommandResult(
            success=False,
            output=f"Conversational fix failed: {e}",
        )


def _format_unified_fixes_list(fixes: list) -> str:
    """Format unified findings as fixes."""
    if not fixes:
        return "No fixes found for the specified file/line."

    output = f"## Found {len(fixes)} Fixes\n\n"
    for fix in fixes:
        sev_icon = {
            "error": "[X]",
            "warning": "[!]",
            "info": "[i]",
        }.get(fix.severity.value, "?")
        output += f"{sev_icon} `{fix.file}:{fix.line}` "
        output += f"**[{fix.rule_id}]** {fix.message[:60]}\n"

        if fix.context:
            output += f"```\n{fix.context[:100]}\n```\n"

        if fix.fix:
            output += f"**Fix:** {fix.fix[:80]}\n"
        output += "\n"
    return output


async def cmd_explain(ctx: CommandContext) -> CommandResult:
    """Explain a symbol, function, or class."""
    symbol_name = ctx.raw_args.strip()
    if not symbol_name:
        return CommandResult(
            success=False,
            output="Usage: /explain MyClass\n  /explain my_function",
        )

    from src.infrastructure.indexing.symbol_graph import SymbolGraph
    from src.infrastructure.indexing.reference_graph import ReferenceGraph

    symbol_graph = SymbolGraph()
    ref_graph = ReferenceGraph()

    # Try to find in symbol graph
    callers = symbol_graph.get_callers(symbol_name)
    callees = symbol_graph.get_callees(symbol_name)

    # Try reference graph
    info = ref_graph.get_symbol_info(symbol_name)

    output = _format_symbol_explanation(symbol_name, callers, callees, info)
    return CommandResult(success=True, output=output, data={
        "symbol": symbol_name,
        "callers": len(callers),
        "callees": len(callees),
    })


async def cmd_stats(ctx: CommandContext) -> CommandResult:
    """Show review statistics for the workspace."""
    from src.infrastructure.indexing.symbol_graph import SymbolGraph
    from src.infrastructure.indexing.dependency_graph import DependencyGraph

    sym_graph = SymbolGraph()
    dep_graph = DependencyGraph()

    # Get stats (these would be populated from previous runs)
    output = f"""## Review Statistics

**Symbol Graph:**
- Files indexed: {sym_graph.stats.files_indexed}
- Total symbols: {len(sym_graph._nodes)}

**Dependency Graph:**
- Modules indexed: {dep_graph.stats.modules_indexed}
- Import edges: {dep_graph.stats.import_edges_added}

**Note:** Run `/review` first to populate statistics.
"""
    return CommandResult(success=True, output=output)


async def cmd_rules(ctx: CommandContext) -> CommandResult:
    """Manage rule configuration."""
    from src.infrastructure.analysis.rule_engine import RuleEngine

    engine = RuleEngine()
    enable_list = ctx.raw_flags.get("enable", "").split(",")
    disable_list = ctx.raw_flags.get("disable", "").split(",")

    if enable_list and enable_list[0]:
        enabled = []
        for rule_id in enable_list:
            rule_id = rule_id.strip()
            if rule_id and engine.get_rule(rule_id):
                enabled.append(rule_id)
        output = f"Enabled rules: {', '.join(enabled)}"

    elif disable_list and disable_list[0]:
        disabled = []
        for rule_id in disable_list:
            rule_id = rule_id.strip()
            if rule_id:
                if engine.unregister(rule_id):
                    disabled.append(rule_id)
        output = f"Disabled rules: {', '.join(disabled)}"

    else:
        # List all rules
        by_sev: dict[str, int] = {}
        for rule in engine._rules.values():
            sev = rule.severity.value
            by_sev[sev] = by_sev.get(sev, 0) + 1

        output = "## Available Rules\n\n"
        output += f"Total: {len(engine._rules)} rules\n\n"
        for sev, count in sorted(by_sev.items()):
            output += f"- {sev.upper()}: {count} rules\n"

    return CommandResult(success=True, output=output)


async def cmd_help(ctx: CommandContext) -> CommandResult:
    """Show available slash commands."""
    commands = _get_all_commands()
    output = "## Available Slash Commands\n\n"
    for name, cmd in sorted(commands.items()):
        aliases = f" (aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
        output += f"**/{name}{aliases}**\n  {cmd.description}\n\n"
        if cmd.examples:
            output += "  Examples:\n"
            for ex in cmd.examples:
                output += f"    {ex}\n"
            output += "\n"
    return CommandResult(success=True, output=output)


# ─── Command registry ────────────────────────────────────────────────────────

_BUILTIN_COMMANDS: dict[str, Command] = {
    "review": Command(
        name="review",
        description="Run code review on files",
        category=CommandCategory.REVIEW,
        aliases=["r"],
        handler=cmd_review,
        examples=[
            "/review",
            "/review @src/",
            "/review --focus=security",
            "/review --files=src/a.py --focus=ml --auto",
        ],
    ),
    "fix": Command(
        name="fix",
        description="Show and apply fixes for a file or line (use --interactive for confirmation)",
        category=CommandCategory.FIX,
        aliases=["f"],
        handler=cmd_fix,
        examples=[
            "/fix @src/main.py",
            "/fix @src/utils.py:42",
            "/fix @src/handlers/auth.py:100",
            "/fix @src/main.py --apply",
            "/fix @src/main.py --interactive",
            "/fix @src/main.py -i",
            "/fix @src/main.py --interactive --auto-critical",
            "/fix @src/main.py -i -t",
        ],
    ),
    "fix-chat": Command(
        name="fix-chat",
        description="Conversational fix with tradeoff analysis and risk explanations",
        category=CommandCategory.FIX,
        aliases=["fc", "fixc"],
        handler=cmd_fix_interactive_enhanced,
        examples=[
            "/fix-chat @src/main.py",
            "/fix-chat @src/utils.py:42 --auto-critical",
            "/fix-chat @src/main.py --tradeoff",
            "/fix-chat @src/main.py -t",
        ],
    ),
    "explain": Command(
        name="explain",
        description="Explain a symbol, function, or class",
        category=CommandCategory.NAVIGATE,
        aliases=["e", "x"],
        handler=cmd_explain,
        examples=[
            "/explain MyClass",
            "/explain process_data",
            "/explain HTTPClient",
        ],
    ),
    "stats": Command(
        name="stats",
        description="Show review statistics",
        category=CommandCategory.UTILITY,
        aliases=["s", "stat"],
        handler=cmd_stats,
        examples=["/stats"],
    ),
    "rules": Command(
        name="rules",
        description="Manage rule configuration",
        category=CommandCategory.CONFIG,
        aliases=["rule"],
        handler=cmd_rules,
        examples=[
            "/rules",
            "/rules --enable=SEC001,SEC002",
            "/rules --disable=QUAL005",
        ],
    ),
    "help": Command(
        name="help",
        description="Show this help message",
        category=CommandCategory.UTILITY,
        aliases=["h", "?"],
        handler=cmd_help,
        examples=["/help", "/help review"],
    ),
}


def _get_all_commands() -> dict[str, Command]:
    return _BUILTIN_COMMANDS.copy()


def _parse_ref(ref: str) -> tuple[str, Optional[int]]:
    """Parse @file:line or @file reference."""
    match = re.match(r"@(.+?)(?::(\d+))?$", ref.strip())
    if match:
        file_path = match.group(1)
        line = int(match.group(2)) if match.group(2) else None
        return file_path, line
    return ref, None


def _parse_flags(args_str: str) -> tuple[list[str], dict[str, str]]:
    """Parse positional args and --flag=value flags."""
    parts = shlex.split(args_str)
    positional: list[str] = []
    flags: dict[str, str] = {}

    for part in parts:
        if part.startswith("--"):
            if "=" in part:
                key, val = part[2:].split("=", 1)
                flags[key.replace("-", "_")] = val
            else:
                flags[part[2:].replace("-", "_")] = "true"
        elif part.startswith("-"):
            flags[part[1:].replace("-", "_")] = "true"
        else:
            positional.append(part)

    return positional, flags


async def parse_and_execute(
    raw_input: str,
    workspace_root: str,
) -> CommandResult:
    """Parse a slash command and execute it.

    Args:
        raw_input: Raw user input like "/fix @src/main.py:42 --auto"
        workspace_root: Root directory of the workspace

    Returns:
        CommandResult with output and metadata
    """
    raw_input = raw_input.strip()
    if not raw_input.startswith("/"):
        return CommandResult(
            success=False,
            output=f"Unknown command: {raw_input}. Use /help for available commands.",
        )

    # Split command name from args
    parts = raw_input[1:].split(maxsplit=1)
    cmd_name = parts[0].lower()
    args_str = parts[1] if len(parts) > 1 else ""

    # Find command
    command = _BUILTIN_COMMANDS.get(cmd_name)
    if not command:
        # Try aliases
        for cmd in _BUILTIN_COMMANDS.values():
            if cmd_name in cmd.aliases:
                command = cmd
                break

    if not command:
        suggestions = [
            name for name in _BUILTIN_COMMANDS
            if name.startswith(cmd_name[:2])
        ]
        msg = f"Unknown command: /{cmd_name}"
        if suggestions:
            msg += f". Did you mean: {', '.join('/' + s for s in suggestions)}?"
        return CommandResult(success=False, output=msg)

    # Parse arguments
    positional_args, flags = _parse_flags(args_str)

    # Extract file references
    files: list[str] = []
    lines: list[int] = []
    remaining_args: list[str] = []

    for arg in positional_args:
        if arg.startswith("@"):
            f, ln = _parse_ref(arg)
            files.append(f)
            if ln:
                lines.append(ln)
        else:
            remaining_args.append(arg)

    # Build context
    ctx = CommandContext(
        workspace_root=workspace_root,
        files=files,
        lines=lines,
        raw_args=" ".join(remaining_args),
        raw_flags=flags,
    )

    # Execute
    try:
        result = await command.handler(ctx)
        if asyncio.iscoroutine(result):
            result = await result
        return result
    except Exception as exc:
        import logging
        logging.exception("Command execution failed")
        return CommandResult(
            success=False,
            output=f"Command /{cmd_name} failed: {exc}",
            errors=[str(exc)],
        )


# ─── Output formatters ──────────────────────────────────────────────────────

def _format_unified_review_summary(result) -> str:
    """Format unified review result for slash command output."""
    errors = result.stats.errors_count
    warnings = result.stats.warnings_count
    info = result.stats.info_count
    total = len(result.findings)
    duration_ms = result.stats.execution_time_ms

    output = f"""## Unified Code Review Summary

| Metric | Value |
|--------|-------|
| Files reviewed | {result.stats.files_scanned} |
| Total findings | {total} |
| Duration | {duration_ms:.0f}ms |
| Detectors | {', '.join(result.stats.detectors_used)} |

### By Severity

- **[X] Errors:** {errors}
- **[!] Warnings:** {warnings}
- **[i] Info:** {info}

### Top Findings

"""

    # Show top 5 findings
    top_findings = sorted(
        result.findings,
        key=lambda f: (-f.severity.to_numeric(), -f.confidence)
    )[:5]

    for i, f in enumerate(top_findings, 1):
        output += f"{i}. `[{f.rule_id}]` {f.file}:{f.line} - {f.message[:60]}\n"

    if result.suggestions:
        output += f"\n### Fix Suggestions\n\n"
        for sug in result.suggestions[:3]:
            output += f"- {sug.get('title', 'Fix')}: {sug.get('description', '')[:50]}...\n"

    return output


def _format_symbol_explanation(name: str, callers: list, callees: list, info) -> str:
    output = f"## Symbol: `{name}`\n\n"
    if info and info.definition:
        defn = info.definition
        output += f"**Type:** {defn.symbol_type}\n"
        output += f"**File:** `{defn.file_path}:{defn.line}`\n"
        if defn.signature:
            output += f"**Signature:** `{defn.signature}`\n"
        output += "\n"

    output += f"**Called by ({len(callers)} callers):**\n"
    if callers:
        for caller in callers[:5]:
            output += f"  - `{caller.caller_file}:{caller.caller_line}` `{caller.caller}`\n"
        if len(callers) > 5:
            output += f"  - ... and {len(callers) - 5} more\n"
    else:
        output += "  - (no callers found)\n"

    output += f"\n**Calls ({len(callees)} callees):**\n"
    if callees:
        for callee in callees[:5]:
            output += f"  - `{callee.callee_file}:{callee.callee_line}` `{callee.callee}`\n"
        if len(callees) > 5:
            output += f"  - ... and {len(callees) - 5} more\n"
    else:
        output += "  - (no callees found)\n"

    return output


# ─── CLI registration ────────────────────────────────────────────────────────

def register_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register slash command parser as a CLI subcommand."""
    parser = subparsers.add_parser(
        "slash",
        help="Execute slash commands (/fix, /review, /explain...)",
        description="Parse and execute slash commands in Cursor style",
    )
    parser.add_argument("command", nargs="+", help="Command to execute (e.g. '/fix @file:42')")
    parser.add_argument(
        "--workspace", "-w", default=".",
        help="Workspace root directory",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    parser.set_defaults(handler=_run_slash_command)


async def _run_slash_command(args: argparse.Namespace) -> int:
    """Run a slash command from CLI."""
    import json, sys

    raw = " ".join(args.command)
    result = await parse_and_execute(raw, args.workspace)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(result.output)
        if result.errors:
            for err in result.errors:
                print(f"[ERROR] {err}", file=sys.stderr)

    return 0 if result.success else 1
