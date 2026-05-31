"""Auto-review triggered by file changes.

Watches code files and automatically runs code review when changes are detected,
updating a diagnostics cache for LSP-like inline diagnostics.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from src.application.workflows.unified.review_engine import (
        UnifiedReviewEngine,
        ReviewEngineConfig,
    )
    from src.application.workflows.unified.detector_base import Finding

logger = logging.getLogger(__name__)


@dataclass
class Diagnostic:
    """Represents a diagnostic (issue/warning/error) for a file."""

    file: str
    line: int
    end_line: int | None
    severity: str  # "error", "warning", "info"
    rule_id: str
    message: str
    confidence: float


@dataclass
class AutoReviewStats:
    """Statistics for auto-review service."""

    files_reviewed: int = 0
    reviews_triggered: int = 0
    diagnostics_count: int = 0
    errors_count: int = 0


class AutoReviewService:
    """Watch files and run review automatically.

    This service monitors code files for changes and triggers
    code review when modifications are detected, caching
    diagnostics for real-time display.

    Usage:
        service = AutoReviewService(Path("src/"))
        await service.start_watching()
    """

    def __init__(
        self,
        project_root: Path,
        config: "ReviewEngineConfig | None" = None,
    ):
        self.project_root = project_root
        self._config = config
        self._review_engine: "UnifiedReviewEngine | None" = None
        self._watcher = None
        self._running = False
        self._review_lock = asyncio.Lock()
        self._review_debounce_task: asyncio.Task | None = None
        self._pending_paths: set[str] = set()

        # Diagnostics cache: path -> list of diagnostics
        self.diagnostics_cache: dict[str, list[Diagnostic]] = {}

        # Statistics
        self.stats = AutoReviewStats()

    async def _on_file_changed(self, events: list) -> None:
        """Handle file change events and trigger review."""
        changed_paths = [str(e.path) for e in events if hasattr(e, "path")]
        if not changed_paths:
            return

        logger.info(
            "file_changes_detected",
            count=len(changed_paths),
            files=changed_paths[:5],  # Log first 5 for clarity
        )

        # Add to pending paths
        async with self._review_lock:
            for path in changed_paths:
                self._pending_paths.add(path)

            # Cancel existing debounce task
            if self._review_debounce_task and not self._review_debounce_task.done():
                self._review_debounce_task.cancel()

            # Create new debounced review task
            self._review_debounce_task = asyncio.create_task(
                self._debounced_review()
            )

    async def _debounced_review(self) -> None:
        """Wait for debounce period then run review."""
        # Wait for debounce period (2 seconds)
        await asyncio.sleep(2)

        # Get pending paths
        async with self._review_lock:
            paths_to_review = self._pending_paths.copy()
            self._pending_paths.clear()

        if paths_to_review:
            await self._run_review(paths_to_review)

    async def _run_review(self, paths: list[str]) -> None:
        """Run review on the specified paths."""
        if self._review_engine is None:
            await self._init_engine()

        if self._review_engine is None:
            logger.error("review_engine_not_available")
            return

        try:
            self.stats.reviews_triggered += 1
            logger.info("starting_auto_review", paths_count=len(paths))

            # Run review
            file_paths = [Path(p) for p in paths]
            result = await self._review_engine.review(
                file_paths,
                incremental=False,  # Full review for changed files
            )

            # Update diagnostics cache
            await self._update_diagnostics_cache(result.findings)

            self.stats.files_reviewed += len(paths)
            self.stats.diagnostics_count = sum(
                len(d) for d in self.diagnostics_cache.values()
            )

            # Log summary
            if result.findings:
                logger.info(
                    "auto_review_complete",
                    files=len(paths),
                    findings=len(result.findings),
                    errors=result.stats.errors_count,
                    warnings=result.stats.warnings_count,
                )
            else:
                logger.info("auto_review_complete_no_findings", files=len(paths))

        except Exception as exc:
            self.stats.errors_count += 1
            logger.error("auto_review_error", exc=str(exc), paths=paths)

    async def _init_engine(self) -> None:
        """Initialize the review engine lazily."""
        try:
            from src.application.workflows.unified.review_engine import (
                UnifiedReviewEngine,
                ReviewEngineConfig,
            )

            config = self._config or ReviewEngineConfig(
                focus_areas=["security", "quality", "ml", "embedded"],
                output_format="json",
                enable_caching=False,  # Disable for auto-review to ensure fresh results
            )
            self._review_engine = UnifiedReviewEngine(config)
            logger.info("review_engine_initialized")

        except ImportError as exc:
            logger.error("failed_to_import_review_engine", exc=str(exc))
            self._review_engine = None

    async def _update_diagnostics_cache(
        self,
        findings: list,
    ) -> None:
        """Update diagnostics cache from findings."""
        # Group findings by file
        by_file: dict[str, list[Diagnostic]] = {}
        for finding in findings:
            file_path = getattr(finding, "file", None) or str(finding.path)
            if file_path not in by_file:
                by_file[file_path] = []

            # Determine severity
            severity = "info"
            if hasattr(finding, "severity"):
                severity_map = {
                    "CRITICAL": "error",
                    "HIGH": "error",
                    "MEDIUM": "warning",
                    "LOW": "info",
                }
                severity = severity_map.get(
                    getattr(finding.severity, "value", "MEDIUM"),
                    "info",
                )

            diagnostic = Diagnostic(
                file=file_path,
                line=getattr(finding, "line", 1),
                end_line=getattr(finding, "end_line", None),
                severity=severity,
                rule_id=getattr(finding, "rule_id", "UNKNOWN"),
                message=getattr(finding, "message", ""),
                confidence=getattr(finding, "confidence", 0.5),
            )
            by_file[file_path].append(diagnostic)

        # Update cache
        for file_path, diagnostics in by_file.items():
            self.diagnostics_cache[file_path] = diagnostics

        # Clear diagnostics for files that no longer have findings
        # (files that were modified and no longer have issues)
        files_with_findings = set(by_file.keys())
        paths_to_remove = [
            p for p in self.diagnostics_cache
            if p not in files_with_findings
        ]
        for path in paths_to_remove:
            del self.diagnostics_cache[path]

    async def start_watching(self) -> None:
        """Start auto-review mode."""
        from .file_watcher import FileWatcher, WatchConfig

        self._running = True

        # Initialize engine
        await self._init_engine()

        # Configure watcher
        config = WatchConfig(
            paths=[self.project_root],
            patterns=[
                "*.py", "*.c", "*.h", "*.cpp", "*.hpp",
                "*.rs", "*.go", "*.java", "*.ts", "*.tsx",
                "*.js", "*.jsx",
            ],
            debounce_ms=2000,
            exclude_dirs={
                ".git", "__pycache__", "node_modules", ".venv",
                "venv", "build", "dist", ".pytest_cache",
                ".mypy_cache", ".tox", ".eggs", "*.egg-info",
            },
        )

        self._watcher = FileWatcher(config, self._on_file_changed)
        await self._watcher.start()

        logger.info(
            "auto_review_service_started",
            root=str(self.project_root),
        )

    async def stop(self) -> None:
        """Stop auto-review service."""
        self._running = False
        if self._watcher:
            await self._watcher.stop()
        if self._review_debounce_task:
            self._review_debounce_task.cancel()
            try:
                await self._review_debounce_task
            except asyncio.CancelledError:
                pass

        logger.info("auto_review_service_stopped", stats=self.stats)

    def get_diagnostics(self, path: Path | str) -> list[Diagnostic]:
        """Get cached diagnostics for a file."""
        path_str = str(path)
        return self.diagnostics_cache.get(path_str, [])

    def get_all_diagnostics(self) -> dict[str, list[Diagnostic]]:
        """Get all cached diagnostics."""
        return self.diagnostics_cache.copy()

    def clear_diagnostics(self, path: Path | str | None = None) -> None:
        """Clear diagnostics cache.

        Args:
            path: Specific file to clear, or None to clear all.
        """
        if path is None:
            self.diagnostics_cache.clear()
        else:
            path_str = str(path)
            self.diagnostics_cache.pop(path_str, None)

    def get_stats(self) -> dict[str, Any]:
        """Get service statistics."""
        return {
            "running": self._running,
            "files_reviewed": self.stats.files_reviewed,
            "reviews_triggered": self.stats.reviews_triggered,
            "diagnostics_count": self.stats.diagnostics_count,
            "errors_count": self.stats.errors_count,
            "cached_files": len(self.diagnostics_cache),
        }
