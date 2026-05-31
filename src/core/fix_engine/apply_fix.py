"""Apply fix tool — applies or rejects code fixes with rollback support.

This tool supports both:
- Legacy Fix objects (from src.core.fix_engine.models)
- Unified FixOption objects (from src.domain.models.review_issue)

Features:
- Automatic backup before applying fixes
- Multi-file batch operations
- Conflict detection and resolution
- Interactive apply with preview
"""

import hashlib
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from src.core.fix_engine.models import Fix, FixBatch, FixResult, FixStatus
from src.core.fix_engine.conflict_resolver import ConflictResolver
from src.infrastructure.patching.diff_parser import ApplyResult

logger = logging.getLogger(__name__)

BACKUP_DIR = Path(".cursor/ai_support/backups")
AUTO_BACKUP_DIR = Path(".cursor/ai_support/auto_backups")

# Type alias for supported fix types
FixInput = Union[Fix, "FixOption", "ReviewIssue"]


class ApplyFixTool:
    """Tool for applying code fixes with rollback capability and conflict resolution."""

    def __init__(self, workspace_root: Optional[str] = None):
        self._workspace_root = Path(workspace_root) if workspace_root else Path.cwd()
        self._backup_dir = self._workspace_root / BACKUP_DIR
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        self.conflict_resolver = ConflictResolver()
        # In-memory rollback store: fix_id -> original content
        self._rollback_store: dict[str, str] = {}

    def _compute_hash(self, content: str) -> str:
        """Compute SHA256 hash prefix of content for backup naming."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _create_backup(self, file_path: str, content: str) -> str:
        """Create a backup of file content."""
        backup_name = f"{self._compute_hash(content)}_{Path(file_path).name}"
        backup_path = self._backup_dir / backup_name
        backup_path.write_text(content, encoding="utf-8")
        logger.debug("Backup created: %s", backup_path)
        return str(backup_path)

    def _restore_backup(self, backup_path: str, file_path: str) -> bool:
        """Restore file from backup."""
        try:
            content = Path(backup_path).read_text(encoding="utf-8")
            Path(file_path).write_text(content, encoding="utf-8")
            logger.info("Restored from backup: %s", file_path)
            return True
        except Exception as exc:
            logger.error("Restore failed: %s", exc)
            return False

    def _auto_backup(self, file_path: Path) -> Path:
        """Create automatic backup before applying fix.
        
        Creates a timestamped backup in the auto_backups directory.
        Keeps only the last 100 backups per file.
        
        Args:
            file_path: Path to the file to backup
            
        Returns:
            Path to the backup file
        """
        backup_dir = self._workspace_root / AUTO_BACKUP_DIR
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_path = backup_dir / f"{file_path.name}.{timestamp}.bak"
        
        try:
            if file_path.exists():
                shutil.copy2(file_path, backup_path)
                logger.debug("Auto-backup created: %s", backup_path)
            else:
                # Create empty marker for new files
                backup_path.write_text("", encoding='utf-8')
                logger.debug("Auto-backup created (new file): %s", backup_path)
            
            # Cleanup old backups (keep last 100)
            self._cleanup_old_backups(file_path.name, backup_dir)
            
        except Exception as e:
            logger.warning("Auto-backup failed for %s: %s", file_path, e)
        
        return backup_path

    def _cleanup_old_backups(self, file_name: str, backup_dir: Path) -> None:
        """Remove old automatic backups, keeping only the most recent 100.
        
        Args:
            file_name: Base file name to match
            backup_dir: Directory containing backups
        """
        try:
            pattern = f"{file_name}.*.bak"
            backups = sorted(backup_dir.glob(pattern), key=lambda p: p.stat().st_mtime)
            
            # Remove oldest backups beyond the limit
            for old_backup in backups[:-100]:
                try:
                    old_backup.unlink()
                except OSError:
                    pass
        except Exception as e:
            logger.debug("Backup cleanup failed: %s", e)

    def validate_fix(
        self, file_path: str, old_text: str, new_text: str
    ) -> tuple[bool, str]:
        """Validate fix before applying: check old_text exists."""
        try:
            full_path = self._workspace_root / file_path
            if not full_path.exists():
                return False, f"File not found: {file_path}"
            current = full_path.read_text(encoding="utf-8")
            if old_text not in current:
                return False, f"old_text not found in {file_path}"
            return True, "valid"
        except Exception as exc:
            return False, str(exc)

    def apply_fix(self, fix: Fix) -> FixResult:
        """Apply a single fix with backup and validation.

        Stores original content in _rollback_store for in-memory rollback.
        Creates automatic backup before applying.
        """
        result = FixResult(fix_id=fix.id, success=False)

        try:
            full_path = self._workspace_root / fix.file_path
            if not full_path.exists():
                result.error = f"File not found: {fix.file_path}"
                return result

            current = full_path.read_text(encoding="utf-8")

            if fix.old_text and fix.old_text not in current:
                result.error = f"old_text not found in {fix.file_path}"
                fix.mark_failed()
                return result

            # Store original for in-memory rollback
            self._rollback_store[fix.id] = current

            # Create automatic backup before applying
            auto_backup_path = self._auto_backup(full_path)
            result.backup_path = str(auto_backup_path)

            backup_path = self._create_backup(fix.file_path, current)
            result.backup_path = backup_path

            if fix.old_text:
                new_content = current.replace(fix.old_text, fix.new_text, 1)
            else:
                new_content = fix.new_text

            full_path.write_text(new_content, encoding="utf-8")
            result.new_content = new_content
            result.success = True
            fix.mark_applied()

            logger.info("Applied fix %s to %s", fix.id, fix.file_path)

        except Exception as exc:
            result.error = str(exc)
            fix.mark_failed()
            logger.error("Failed to apply fix %s: %s", fix.id, exc)

        return result

    def apply_batch(
        self,
        fixes: list[Fix],
        dry_run: bool = False,
        resolve_conflicts: bool = True,
    ) -> FixBatch:
        """Apply multiple fixes. If dry_run=True, validate all without applying.

        Args:
            fixes: List of fixes to apply
            dry_run: If True, validate without applying
            resolve_conflicts: If True, detect and resolve conflicts

        Returns:
            FixBatch with results
        """
        batch = FixBatch()
        applied_results: list[tuple[Fix, FixResult]] = []

        if resolve_conflicts:
            conflicts = self.conflict_resolver.detect_conflicts(fixes)
            if conflicts:
                logger.info("Detected %d conflicts, resolving...", len(conflicts))
                fixes = self.conflict_resolver.get_safe_order(fixes)

        sorted_fixes = sorted(
            fixes,
            key=lambda f: (f.file_path, -f.line_start)
        )

        for fix in sorted_fixes:
            batch.add(fix)

            valid, msg = self.validate_fix(
                fix.file_path, fix.old_text, fix.new_text
            )
            if not valid:
                fix.mark_failed()
                fix.status = FixStatus.SKIPPED
                logger.warning("Skipping fix %s: %s", fix.id, msg)
                continue

            if dry_run:
                fix.status = FixStatus.PENDING
                continue

            result = self.apply_fix(fix)
            applied_results.append((fix, result))

            if not result.success:
                logger.warning("Fix %s failed: %s", fix.id, result.error)
                self._rollback_fixes(applied_results[:-1])
                break

        batch.update_counters()
        return batch

    def _rollback_fixes(
        self, applied: list[tuple[Fix, FixResult]]
    ) -> int:
        """Rollback applied fixes in reverse order."""
        restored = 0
        for fix, result in reversed(applied):
            if result.has_backup:
                if self._restore_backup(result.backup_path, fix.file_path):
                    restored += 1
                    fix.status = FixStatus.PENDING
        logger.info("Rolled back %d fixes", restored)
        return restored

    def rollback(self, results: list[FixResult]) -> int:
        """Rollback fixes from a batch of results.

        Uses in-memory rollback store first, then falls back to backup files.
        """
        restored = 0
        for result in reversed(results):
            # Try in-memory rollback first
            if result.fix_id in self._rollback_store:
                try:
                    for fix in self._find_fixes_by_backup(result.fix_id):
                        full_path = self._workspace_root / fix.file_path
                        full_path.write_text(self._rollback_store[result.fix_id], encoding="utf-8")
                        fix.status = FixStatus.PENDING
                        restored += 1
                        logger.info("Rolled back fix %s (in-memory)", result.fix_id)
                    del self._rollback_store[result.fix_id]
                    continue
                except Exception as e:
                    logger.warning("In-memory rollback failed for %s: %s", result.fix_id, e)

            # Fall back to backup file
            if result.has_backup:
                parts = Path(result.backup_path).name.split("_", 1)
                if len(parts) > 1:
                    original_name = parts[1]
                    for fix in self._find_fixes_by_backup(result.fix_id):
                        if self._restore_backup(result.backup_path, fix.file_path):
                            restored += 1
                            fix.status = FixStatus.PENDING
        return restored

    def rollback_fix(self, fix_id: str) -> bool:
        """Rollback a single fix by ID using in-memory store.

        Args:
            fix_id: The ID of the fix to rollback.

        Returns:
            True if rollback succeeded, False otherwise.
        """
        if fix_id not in self._rollback_store:
            logger.warning("No rollback data found for fix_id: %s", fix_id)
            return False

        try:
            # Find the fix in our known fixes (we'd need to track applied fixes)
            # For now, use the backup path approach
            fixes = self._find_fixes_by_backup(fix_id)
            if fixes:
                full_path = self._workspace_root / fixes[0].file_path
                full_path.write_text(self._rollback_store[fix_id], encoding="utf-8")
                del self._rollback_store[fix_id]
                logger.info("Rolled back fix %s", fix_id)
                return True
        except Exception as e:
            logger.error("Rollback failed for %s: %s", fix_id, e)

        return False

    def _find_fixes_by_backup(self, fix_id: str) -> list[Fix]:
        """Find fixes by ID from backup directory (used for rollback).
        
        Searches the backup directory for fix records matching the given fix_id.
        Returns empty list if backup dir doesn't exist or no matching fixes found.
        """
        fixes: list[Fix] = []
        backup_dir = self._workspace_root / ".aisupport" / "backups"
        if not backup_dir.exists():
            return fixes
        
        # Look for fix records matching the fix_id
        for backup_file in backup_dir.glob(f"*.json"):
            try:
                import json
                data = json.loads(backup_file.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("fix_id") == fix_id:
                    fixes.append(Fix(
                        fix_id=data["fix_id"],
                        file_path=data["file_path"],
                        old_text=data.get("old_text", ""),
                        new_text=data.get("new_text", ""),
                        line_start=data.get("line_start", 0),
                        line_end=data.get("line_end", 0),
                    ))
            except (json.JSONDecodeError, KeyError, OSError):
                continue
        
        return fixes

    def interactive_apply(self, fix: Fix) -> FixResult:
        """Interactive apply: returns result, caller handles prompts."""
        return self.apply_fix(fix)

    def preview_fix(self, fix: Fix) -> tuple[str, str]:
        """Generate preview of old and new content for display."""
        try:
            full_path = self._workspace_root / fix.file_path
            current = full_path.read_text(encoding="utf-8")

            if fix.old_text in current:
                old_display = fix.old_text
                new_display = fix.new_text
            else:
                lines = current.split("\n")
                line_start = fix.line_start - 1
                line_end = fix.line_end
                if 0 <= line_start < len(lines):
                    old_display = "\n".join(lines[line_start:line_end])
                    new_display = fix.new_text
                else:
                    old_display = "(content not found)"
                    new_display = fix.new_text

            return old_display, new_display
        except Exception as exc:
            return f"(error reading file: {exc})", fix.new_text

    # ─── FixOption Support (Unified Schema) ─────────────────────────────────────

    def apply_fix_option(
        self,
        fix_option: "FixOption",
        file_path: Optional[str] = None,
    ) -> FixResult:
        """Apply a FixOption from the unified schema.

        Args:
            fix_option: FixOption to apply
            file_path: Optional file path override

        Returns:
            FixResult with success status
        """
        result = FixResult(fix_id=fix_option.id, success=False)

        try:
            target_file = file_path or fix_option.apply_command.split()[0] if fix_option.apply_command else ""
            if not target_file and hasattr(fix_option, 'id'):
                result.error = "No file path provided for FixOption"
                return result

            # Handle file path from apply_command
            if not target_file and fix_option.apply_command:
                parts = fix_option.apply_command.split()
                if parts:
                    target_file = parts[0]

            if not target_file:
                result.error = "No file path specified"
                return result

            full_path = self._workspace_root / target_file
            if not full_path.exists():
                result.error = f"File not found: {target_file}"
                return result

            current = full_path.read_text(encoding="utf-8")

            # Apply the fix
            if fix_option.old_code and fix_option.old_code in current:
                new_content = current.replace(fix_option.old_code, fix_option.new_code, 1)
            elif fix_option.diff:
                # Apply from diff using the unified diff parser
                from src.infrastructure.patching.diff_parser import UnifiedDiffParser
                parser = UnifiedDiffParser()
                try:
                    new_content = parser.apply_diff(current, fix_option.diff, target_file)
                except ValueError as e:
                    result.error = str(e)
                    return result
            else:
                # No old_code, just use new_code directly
                new_content = fix_option.new_code

            # Create automatic backup before applying
            auto_backup_path = self._auto_backup(full_path)
            result.backup_path = str(auto_backup_path)

            # Create named backup
            backup_path = self._create_backup(target_file, current)
            result.backup_path = backup_path

            full_path.write_text(new_content, encoding="utf-8")
            result.new_content = new_content
            result.success = True

            logger.info("Applied FixOption %s to %s", fix_option.id, target_file)

        except Exception as exc:
            result.error = str(exc)
            logger.error("Failed to apply FixOption %s: %s", fix_option.id, exc)

        return result

    def _apply_diff(
        self,
        file_path: str,
        diff: str,
    ) -> ApplyResult:
        """Apply a unified diff to a file.

        Args:
            file_path: Path to the file to modify.
            diff: Unified diff string.

        Returns:
            ApplyResult with success status and details.
        """
        try:
            full_path = self._workspace_root / file_path
            if not full_path.exists():
                return ApplyResult(
                    success=False,
                    file_path=file_path,
                    error=f"File not found: {file_path}",
                )

            # Read current content
            current = full_path.read_text(encoding="utf-8")

            # Parse and apply diff
            from src.infrastructure.patching.diff_parser import UnifiedDiffParser

            parser = UnifiedDiffParser()
            result = parser.parse(diff)

            if not result.success:
                return ApplyResult(
                    success=False,
                    file_path=file_path,
                    error=f"Invalid diff: {result.error}",
                )

            # Apply hunks to content
            content_lines = current.splitlines(keepends=False)
            total_modified = 0

            for file_diff in result.files:
                # Skip if paths don't match (when diff contains different file)
                if file_diff.new_path and file_diff.new_path != file_path:
                    # Try with old_path too
                    if file_diff.old_path != file_path:
                        continue

                for hunk in file_diff.hunks:
                    content_lines = parser.apply_hunk(content_lines, hunk)
                    total_modified += hunk.new_count

            # Write back modified content
            full_path.write_text("\n".join(content_lines), encoding="utf-8")

            logger.info("Applied diff to %s (%d lines modified)", file_path, total_modified)

            return ApplyResult(
                success=True,
                file_path=file_path,
                lines_modified=total_modified,
            )

        except Exception as exc:
            logger.error("Failed to apply diff to %s: %s", file_path, exc)
            return ApplyResult(
                success=False,
                file_path=file_path,
                error=str(exc),
            )

    def apply_review_issue(
        self,
        issue: "ReviewIssue",
        fix_index: int = 0,
    ) -> FixResult:
        """Apply a fix from a ReviewIssue.

        Args:
            issue: ReviewIssue containing the fix
            fix_index: Index of the fix option to apply (default: 0 = primary)

        Returns:
            FixResult with success status
        """
        if not issue.is_fixable:
            return FixResult(
                fix_id=issue.id,
                success=False,
                error="Issue has no fix options",
            )

        if fix_index >= len(issue.fixes):
            return FixResult(
                fix_id=issue.id,
                success=False,
                error=f"Fix index {fix_index} out of range",
            )

        fix_option = issue.fixes[fix_index]
        return self.apply_fix_option(fix_option, file_path=issue.file)

    def preview_fix_option(self, fix_option: "FixOption", file_path: str) -> tuple[str, str]:
        """Preview a FixOption before applying.

        Args:
            fix_option: FixOption to preview
            file_path: Path to the file

        Returns:
            Tuple of (old_code, new_code) for display
        """
        try:
            full_path = self._workspace_root / file_path
            current = full_path.read_text(encoding="utf-8")

            if fix_option.old_code in current:
                return fix_option.old_code, fix_option.new_code

            return "(content not found)", fix_option.new_code
        except Exception as exc:
            return f"(error reading file: {exc})", fix_option.new_code

    # ─── Unified Interface ───────────────────────────────────────────────────────

    def apply(
        self,
        fix_input: FixInput,
        **kwargs,
    ) -> FixResult:
        """Apply any supported fix type.

        Args:
            fix_input: Fix, FixOption, or ReviewIssue
            **kwargs: Additional arguments (file_path for FixOption)

        Returns:
            FixResult with success status
        """
        # Import here to avoid circular imports
        from src.domain.models.review_issue import FixOption as UnifiedFixOption, ReviewIssue as UnifiedReviewIssue

        if isinstance(fix_input, UnifiedReviewIssue):
            return self.apply_review_issue(fix_input, kwargs.get("fix_index", 0))
        elif isinstance(fix_input, UnifiedFixOption):
            return self.apply_fix_option(fix_input, kwargs.get("file_path"))
        elif isinstance(fix_input, Fix):
            return self.apply_fix(fix_input)
        else:
            return FixResult(
                fix_id="unknown",
                success=False,
                error=f"Unsupported fix type: {type(fix_input)}",
            )
