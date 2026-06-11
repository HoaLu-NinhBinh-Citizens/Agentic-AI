"""Pipeline Orchestrator — wires all Universal Repo Handler phases together.

Implements the full pipeline: detect → analyze → build → parse → fix → iterate → report.
Provides a single entry point for processing repositories.

Requirements: 1.1, 2.1, 3.1, 4.1, 5.6, 6.1, 7.1, 9.1, 10.1
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from .build_runner import BuildRunner
from .models import (
    IterativeBuildResult,
    LanguageDistribution,
    ProjectProfile,
    MAX_FIX_ITERATIONS,
)
from .project_detector import ProjectDetector
from .progress_emitter import PipelineProgressEmitter
from .rule_engine import UniversalRuleEngine

if TYPE_CHECKING:
    from . import StreamSink

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Complete result from running the full analysis pipeline.

    Contains the project profile, analysis findings, build results,
    and any fix patches generated.
    """

    profile: ProjectProfile
    findings: list
    build_result: IterativeBuildResult
    success: bool
    errors: list[str]


async def run_pipeline(
    repo_path: Path,
    progress_sink: StreamSink | None = None,
    install_deps: bool = True,
    max_iterations: int = MAX_FIX_ITERATIONS,
) -> PipelineResult:
    """Run the complete Universal Repo Handler pipeline.

    Pipeline phases:
    1. detect — Scan repository for languages, frameworks, build tools
    2. analyze — Run static analysis via UniversalRuleEngine
    3. build — Execute build and parse errors
    4. fix — If build fails, run iterative fix cycle
    5. report — Return complete result with all outcomes

    Args:
        repo_path: Root path of the repository to process.
        progress_sink: Optional sink for streaming progress events.
        install_deps: Whether to run dependency installation before building.
        max_iterations: Maximum fix-rebuild cycles (default 3).

    Returns:
        A PipelineResult with profile, findings, build results, and status.

    Requirements: 1.1, 2.1, 3.1, 4.1, 5.6, 6.1, 7.1, 9.1, 10.1
    """
    emitter = PipelineProgressEmitter(sink=progress_sink)
    all_errors: list[str] = []

    # Phase 1: Detection
    detector = ProjectDetector()
    try:
        profile = await detector.detect(repo_path, progress_sink)
    except Exception as exc:
        logger.error("Detection failed: %s", exc)
        all_errors.append(f"Detection error: {exc}")
        return PipelineResult(
            profile=ProjectProfile(
                repo_path=repo_path,
                languages=LanguageDistribution(primary_language="unknown", languages={}),
                frameworks=[],
                build_tools=[],
                entry_points=[],
                dependency_manifests=[],
                confidence=0.0,
                detected_at=datetime.now(timezone.utc),
                file_tree_hash="",
            ),
            findings=[],
            build_result=IterativeBuildResult(
                final_success=False,
                iterations_run=0,
                errors_resolved=[],
                errors_remaining=[],
                patches_applied=[],
                patches_failed=[],
                build_results=[],
            ),
            success=False,
            errors=all_errors,
        )

    # Phase 2: Analysis (optional - skip if no build tools)
    findings = []
    if profile.languages.languages:
        rule_engine = UniversalRuleEngine()
        try:
            findings = await rule_engine.analyze_project(
                repo_path, profile, progress_sink
            )
        except Exception as exc:
            logger.warning("Analysis failed: %s", exc)
            all_errors.append(f"Analysis error: {exc}")

    # Phase 3: Build
    runner = BuildRunner()

    # Install dependencies if requested and profile has build tools
    if install_deps and profile.build_tools:
        try:
            dep_result = await runner.install_dependencies(repo_path, profile)
            if not dep_result.success:
                logger.warning("Dependency install failed: %s", dep_result.error_message)
        except Exception as exc:
            logger.warning("Dependency installation error: %s", exc)

    # Run iterative build-fix cycle
    try:
        build_result = await runner.run_iterative_fix_cycle(
            repo_path=repo_path,
            profile=profile,
            max_iterations=max_iterations,
            progress_sink=progress_sink,
        )
    except ValueError as exc:
        if "no_build_tool_detected" in str(exc):
            logger.info("No build tool detected, skipping build phase")
            build_result = IterativeBuildResult(
                final_success=True,
                iterations_run=0,
                errors_resolved=[],
                errors_remaining=[],
                patches_applied=[],
                patches_failed=[],
                build_results=[],
            )
        else:
            logger.error("Build failed: %s", exc)
            all_errors.append(f"Build error: {exc}")
            build_result = IterativeBuildResult(
                final_success=False,
                iterations_run=0,
                errors_resolved=[],
                errors_remaining=[],
                patches_applied=[],
                patches_failed=[],
                build_results=[],
            )
    except Exception as exc:
        logger.error("Build failed unexpectedly: %s", exc)
        all_errors.append(f"Build error: {exc}")
        build_result = IterativeBuildResult(
            final_success=False,
            iterations_run=0,
            errors_resolved=[],
            errors_remaining=[],
            patches_applied=[],
            patches_failed=[],
            build_results=[],
        )

    # Phase 5: Report completion
    await emitter.emit_phase_complete(
        phase="complete",
        summary={
            "pipeline_success": build_result.final_success and not all_errors,
            "primary_language": profile.languages.primary_language,
            "findings_count": len(findings),
            "build_success": build_result.final_success,
            "patches_applied": len(build_result.patches_applied),
        },
        duration_ms=0,
    )

    return PipelineResult(
        profile=profile,
        findings=findings,
        build_result=build_result,
        success=build_result.final_success and not all_errors,
        errors=all_errors,
    )


__all__ = [
    "PipelineResult",
    "run_pipeline",
]