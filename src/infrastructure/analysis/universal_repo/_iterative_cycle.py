"""Iterative build-fix cycle implementation.

Runs the build → parse errors → generate fixes → apply patches → rebuild
loop with a configurable maximum iteration count to prevent infinite loops.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .fix_generator import FileContext, FixGenerator
from .models import (
    AUTO_APPLY_FIX_THRESHOLD,
    CompilerError,
    FixPatch,
    IterativeBuildResult,
    MAX_FIX_ITERATIONS,
    ProjectProfile,
)

if TYPE_CHECKING:
    from .build_runner import BuildRunner
    from . import StreamSink

logger = logging.getLogger(__name__)

# Number of surrounding lines to include in file context for fix generation
_CONTEXT_LINES_RADIUS = 5


async def run_iterative_fix_cycle(
    runner: BuildRunner,
    repo_path: Path,
    profile: ProjectProfile,
    max_iterations: int = MAX_FIX_ITERATIONS,
    progress_sink: StreamSink | None = None,
) -> IterativeBuildResult:
    """Run build → fix → rebuild cycle up to max_iterations.

    Strategy:
    1. Run initial build via runner.run_build()
    2. If build succeeds → return success immediately (iterations_run=0)
    3. For each iteration (up to max_iterations):
       a. Collect errors from build result
       b. For each error, generate fixes via FixGenerator
       c. Filter patches: apply only if confidence > AUTO_APPLY_FIX_THRESHOLD (0.7)
       d. Apply high-confidence patches to files
       e. Re-run build
       f. If build succeeds → return success result
       g. Track resolved errors and remaining errors
    4. After max iterations: return failure with remaining errors and all patches

    Args:
        runner: BuildRunner instance for executing builds.
        repo_path: Root path of the repository.
        profile: Detected project profile with build tool information.
        max_iterations: Maximum fix-rebuild cycles (default 3).
        progress_sink: Optional sink for streaming progress events.

    Returns:
        An IterativeBuildResult with cycle outcomes.

    Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
    """
    from .models import BuildResult
    from .progress_emitter import PipelineProgressEmitter

    emitter = PipelineProgressEmitter(sink=progress_sink)
    emitter.start_phase("fix")
    fix_generator = FixGenerator(llm_provider=None)

    all_patches_applied: list[FixPatch] = []
    all_patches_failed: list[FixPatch] = []
    all_build_results: list[BuildResult] = []
    all_errors_resolved: list[CompilerError] = []

    # Step 1: Run initial build
    initial_result = await runner.run_build(repo_path, profile, progress_sink)
    all_build_results.append(initial_result)

    # Step 2: If build succeeds, return immediately
    if initial_result.success:
        return IterativeBuildResult(
            final_success=True,
            iterations_run=0,
            errors_resolved=[],
            errors_remaining=[],
            patches_applied=[],
            patches_failed=[],
            build_results=all_build_results,
        )

    previous_errors = initial_result.errors

    # Step 3: Iterative fix cycle
    for iteration in range(1, max_iterations + 1):
        await emitter.emit_fix_cycle_status(
            iteration=iteration,
            max_iterations=max_iterations,
            errors_fixed=len(all_errors_resolved),
            errors_remaining=len(previous_errors),
        )

        # 3a-b: For each error, generate fix suggestions
        iteration_patches: list[FixPatch] = []
        for error in previous_errors:
            context = _build_file_context(repo_path, error)
            fixes = await fix_generator.generate_fix(error, context)
            iteration_patches.extend(fixes)

        # 3c: Filter to high-confidence patches only
        high_confidence = [
            p for p in iteration_patches
            if p.confidence > AUTO_APPLY_FIX_THRESHOLD
        ]
        low_confidence = [
            p for p in iteration_patches
            if p.confidence <= AUTO_APPLY_FIX_THRESHOLD
        ]
        all_patches_failed.extend(low_confidence)

        if not high_confidence:
            # No patches to apply — cannot make progress
            logger.debug(
                "Iteration %d: no high-confidence patches available, stopping",
                iteration,
            )
            return IterativeBuildResult(
                final_success=False,
                iterations_run=iteration,
                errors_resolved=all_errors_resolved,
                errors_remaining=previous_errors,
                patches_applied=all_patches_applied,
                patches_failed=all_patches_failed,
                build_results=all_build_results,
            )

        # 3d: Apply high-confidence patches
        # Snapshot touched files first so a regressive iteration (rebuild
        # produces MORE errors than before) can be rolled back instead of
        # leaving the workspace in a worse state than we found it.
        iteration_snapshot = _snapshot_files(repo_path, high_confidence)
        applied, failed = _apply_patches(repo_path, high_confidence)
        all_patches_applied.extend(applied)
        all_patches_failed.extend(failed)

        if not applied:
            # All patches failed to apply — cannot make progress
            logger.debug(
                "Iteration %d: all patches failed to apply, stopping",
                iteration,
            )
            return IterativeBuildResult(
                final_success=False,
                iterations_run=iteration,
                errors_resolved=all_errors_resolved,
                errors_remaining=previous_errors,
                patches_applied=all_patches_applied,
                patches_failed=all_patches_failed,
                build_results=all_build_results,
            )

        # 3e: Re-run build
        rebuild_result = await runner.run_build(repo_path, profile, progress_sink)
        all_build_results.append(rebuild_result)

        # 3f: Check if build now succeeds
        if rebuild_result.success:
            all_errors_resolved.extend(previous_errors)

            await emitter.emit_fix_cycle_status(
                iteration=iteration,
                max_iterations=max_iterations,
                errors_fixed=len(all_errors_resolved),
                errors_remaining=0,
            )

            # Emit phase completion
            duration_ms = emitter.get_phase_duration_ms("fix")
            await emitter.emit_phase_complete(
                phase="fix",
                summary={
                    "iterations_run": iteration,
                    "patches_applied": len(all_patches_applied),
                    "errors_resolved": len(all_errors_resolved),
                    "final_success": True,
                },
                duration_ms=duration_ms,
            )

            return IterativeBuildResult(
                final_success=True,
                iterations_run=iteration,
                errors_resolved=all_errors_resolved,
                errors_remaining=[],
                patches_applied=all_patches_applied,
                patches_failed=all_patches_failed,
                build_results=all_build_results,
            )

        # 3g: Detect regression — patches that increase the error count made
        # the build worse, so restore the pre-iteration file state and stop.
        current_errors = rebuild_result.errors
        if len(current_errors) > len(previous_errors):
            logger.warning(
                "Iteration %d: error count regressed (%d -> %d), rolling back patches",
                iteration,
                len(previous_errors),
                len(current_errors),
            )
            _restore_files(iteration_snapshot)
            for patch in applied:
                if patch in all_patches_applied:
                    all_patches_applied.remove(patch)
            all_patches_failed.extend(applied)
            return IterativeBuildResult(
                final_success=False,
                iterations_run=iteration,
                errors_resolved=all_errors_resolved,
                errors_remaining=previous_errors,
                patches_applied=all_patches_applied,
                patches_failed=all_patches_failed,
                build_results=all_build_results,
            )

        # Track resolved vs remaining errors
        resolved = _find_resolved_errors(previous_errors, current_errors)
        all_errors_resolved.extend(resolved)
        previous_errors = current_errors

        await emitter.emit_fix_cycle_status(
            iteration=iteration,
            max_iterations=max_iterations,
            errors_fixed=len(all_errors_resolved),
            errors_remaining=len(current_errors),
        )

    # Step 4: Max iterations reached — report remaining errors
    await emitter.emit_fix_cycle_status(
        iteration=max_iterations,
        max_iterations=max_iterations,
        errors_fixed=len(all_errors_resolved),
        errors_remaining=len(previous_errors),
    )

    # Emit phase completion
    duration_ms = emitter.get_phase_duration_ms("fix")
    await emitter.emit_phase_complete(
        phase="fix",
        summary={
            "iterations_run": max_iterations,
            "max_iterations_reached": True,
            "errors_remaining": len(previous_errors),
            "patches_applied": len(all_patches_applied),
            "final_success": False,
        },
        duration_ms=duration_ms,
    )

    return IterativeBuildResult(
        final_success=False,
        iterations_run=max_iterations,
        errors_resolved=all_errors_resolved,
        errors_remaining=previous_errors,
        patches_applied=all_patches_applied,
        patches_failed=all_patches_failed,
        build_results=all_build_results,
    )


# ─── Private Helpers ─────────────────────────────────────────────────────────


def _snapshot_files(
    repo_path: Path, patches: list[FixPatch]
) -> dict[Path, str | None]:
    """Capture original content of every file a patch batch will touch.

    None marks a file that did not exist at snapshot time.
    """
    snapshot: dict[Path, str | None] = {}
    for patch in patches:
        if not patch.file_path:
            continue
        file_path = Path(patch.file_path)
        if not file_path.is_absolute():
            file_path = repo_path / file_path
        if file_path in snapshot:
            continue
        try:
            snapshot[file_path] = (
                file_path.read_text(encoding="utf-8", errors="replace")
                if file_path.exists()
                else None
            )
        except OSError:
            snapshot[file_path] = None
    return snapshot


def _restore_files(snapshot: dict[Path, str | None]) -> None:
    """Restore files to their snapshotted content (rollback)."""
    for file_path, content in snapshot.items():
        try:
            if content is None:
                file_path.unlink(missing_ok=True)
            else:
                file_path.write_text(content, encoding="utf-8")
        except OSError:
            logger.warning("Rollback failed to restore %s", file_path)


def _build_file_context(repo_path: Path, error: CompilerError) -> FileContext:
    """Build FileContext by reading the file around the error line.

    Args:
        repo_path: Root path of the repository.
        error: Compiler error with file_path and line info.

    Returns:
        FileContext with file content and surrounding lines.
    """
    if not error.file_path:
        return FileContext(file_path="", content="", surrounding_lines=[])

    file_path = Path(error.file_path)
    if not file_path.is_absolute():
        file_path = repo_path / file_path

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, IOError):
        return FileContext(
            file_path=error.file_path, content="", surrounding_lines=[]
        )

    lines = content.splitlines()
    error_line_idx = max(0, error.line - 1)  # Convert 1-based to 0-based
    start = max(0, error_line_idx - _CONTEXT_LINES_RADIUS)
    end = min(len(lines), error_line_idx + _CONTEXT_LINES_RADIUS + 1)
    surrounding = lines[start:end]

    return FileContext(
        file_path=error.file_path,
        content=content,
        surrounding_lines=surrounding,
    )


def _apply_patches(
    repo_path: Path, patches: list[FixPatch]
) -> tuple[list[FixPatch], list[FixPatch]]:
    """Apply patches to files by replacing old_code with new_code.

    Reads each file, performs the text replacement, and writes back.
    Patches that fail to apply (old_code not found in file) are tracked
    separately.

    Args:
        repo_path: Root path of the repository.
        patches: List of high-confidence FixPatch objects to apply.

    Returns:
        Tuple of (applied_patches, failed_patches).
    """
    applied: list[FixPatch] = []
    failed: list[FixPatch] = []

    for patch in patches:
        if not patch.file_path or not patch.old_code:
            # Patches without old_code (e.g., pure insertions) need special handling
            if patch.new_code and patch.file_path:
                success = _apply_insertion_patch(repo_path, patch)
                if success:
                    applied.append(patch)
                else:
                    failed.append(patch)
            else:
                failed.append(patch)
            continue

        file_path = Path(patch.file_path)
        if not file_path.is_absolute():
            file_path = repo_path / file_path

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except (OSError, IOError):
            logger.debug("Cannot read file for patch: %s", patch.file_path)
            failed.append(patch)
            continue

        if patch.old_code not in content:
            logger.debug(
                "Old code not found in %s for patch at line %d",
                patch.file_path,
                patch.line_start,
            )
            failed.append(patch)
            continue

        # Apply replacement (first occurrence only)
        new_content = content.replace(patch.old_code, patch.new_code, 1)

        try:
            file_path.write_text(new_content, encoding="utf-8")
            applied.append(patch)
            logger.debug(
                "Applied patch to %s (line %d): %s",
                patch.file_path,
                patch.line_start,
                patch.explanation,
            )
        except (OSError, IOError):
            logger.debug("Cannot write patched file: %s", patch.file_path)
            # A failed write may have truncated the file — restore original
            try:
                file_path.write_text(content, encoding="utf-8")
            except OSError:
                logger.warning(
                    "Could not restore %s after failed patch write", patch.file_path
                )
            failed.append(patch)

    return applied, failed


def _apply_insertion_patch(repo_path: Path, patch: FixPatch) -> bool:
    """Apply an insertion-only patch (empty old_code, non-empty new_code).

    Inserts new_code at the specified line_start position.

    Args:
        repo_path: Root path of the repository.
        patch: FixPatch with empty old_code and non-empty new_code.

    Returns:
        True if insertion succeeded, False otherwise.
    """
    file_path = Path(patch.file_path)
    if not file_path.is_absolute():
        file_path = repo_path / file_path

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, IOError):
        return False

    lines = content.splitlines(keepends=True)
    insert_idx = max(0, min(patch.line_start - 1, len(lines)))

    # Insert the new code with a newline
    new_line = patch.new_code if patch.new_code.endswith("\n") else patch.new_code + "\n"
    lines.insert(insert_idx, new_line)

    try:
        file_path.write_text("".join(lines), encoding="utf-8")
        return True
    except (OSError, IOError):
        return False


def _find_resolved_errors(
    previous_errors: list[CompilerError],
    current_errors: list[CompilerError],
) -> list[CompilerError]:
    """Identify errors that were resolved between iterations.

    An error is considered resolved if it was in previous_errors but
    no longer appears in current_errors (matched by file_path, line,
    and error_code).

    Args:
        previous_errors: Errors from the previous build iteration.
        current_errors: Errors from the current build iteration.

    Returns:
        List of CompilerError objects that were resolved.
    """
    current_keys = {
        (e.file_path, e.line, e.error_code) for e in current_errors
    }
    resolved = [
        e for e in previous_errors
        if (e.file_path, e.line, e.error_code) not in current_keys
    ]
    return resolved
