"""Unit tests for the iterative build-fix cycle.

Tests the run_iterative_fix_cycle() function which wires
BuildRunner → ErrorParser → FixGenerator → apply patches → rebuild loop.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from infrastructure.analysis.universal_repo.build_runner import BuildRunner
from infrastructure.analysis.universal_repo.models import (
    AUTO_APPLY_FIX_THRESHOLD,
    BuildCommand,
    BuildResult,
    BuildToolInfo,
    CompilerError,
    FixPatch,
    IterativeBuildResult,
    LanguageDistribution,
    LanguageStats,
    MAX_FIX_ITERATIONS,
    ProjectProfile,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def runner() -> BuildRunner:
    return BuildRunner()


@pytest.fixture
def npm_profile(tmp_path: Path) -> ProjectProfile:
    """Create a ProjectProfile with npm as the primary build tool."""
    return ProjectProfile(
        repo_path=tmp_path,
        languages=LanguageDistribution(
            primary_language="TypeScript",
            languages={"TypeScript": LanguageStats(10, 500, 100.0, 100.0)},
        ),
        frameworks=[],
        build_tools=[
            BuildToolInfo(
                name="npm",
                config_file=tmp_path / "package.json",
                build_commands=["npm run build"],
                relevance_score=1.0,
            )
        ],
        entry_points=[],
        dependency_manifests=[tmp_path / "package.json"],
        confidence=0.9,
        detected_at=datetime.now(),
        file_tree_hash="abc123",
    )


def _make_error(file_path: str = "src/app.ts", line: int = 10, code: str = "TS2304") -> CompilerError:
    """Helper to create a CompilerError for testing."""
    return CompilerError(
        file_path=file_path,
        line=line,
        column=5,
        severity="error",
        error_code=code,
        message=f"Cannot find name 'foo' [{code}]",
        compiler="tsc",
    )


def _make_patch(
    file_path: str = "src/app.ts",
    confidence: float = 0.85,
    old_code: str = "foo",
    new_code: str = "bar",
) -> FixPatch:
    """Helper to create a FixPatch for testing."""
    return FixPatch(
        file_path=file_path,
        line_start=10,
        line_end=10,
        old_code=old_code,
        new_code=new_code,
        explanation="Replace foo with bar",
        confidence=confidence,
        source="template",
    )


def _make_build_result(
    success: bool, errors: list[CompilerError] | None = None
) -> BuildResult:
    """Helper to create a BuildResult for testing."""
    return BuildResult(
        success=success,
        errors=errors or [],
        warnings=[],
        output="build output",
        duration_ms=100.0,
        command=BuildCommand(
            command=["npm", "run", "build"],
            working_directory=Path("/tmp"),
            environment={},
            timeout_seconds=180,
        ),
    )


# ─── Tests: Cycle Termination (Requirement 7.3) ─────────────────────────────


class TestCycleTermination:
    """Test that the cycle terminates after max_iterations."""

    @pytest.mark.asyncio
    async def test_terminates_after_3_iterations_max(
        self, runner: BuildRunner, npm_profile: ProjectProfile, tmp_path: Path
    ):
        """Cycle stops after MAX_FIX_ITERATIONS even if errors remain.

        Requirement 7.3: limit automatic fix-rebuild iterations to max 3.
        """
        errors = [_make_error()]
        high_conf_patch = _make_patch(confidence=0.85)

        # Build always fails with the same error
        failing_result = _make_build_result(success=False, errors=errors)

        with (
            patch.object(
                runner, "run_build", new_callable=AsyncMock, return_value=failing_result
            ),
            patch(
                "infrastructure.analysis.universal_repo._iterative_cycle.FixGenerator"
            ) as MockFG,
            patch(
                "infrastructure.analysis.universal_repo._iterative_cycle._apply_patches",
                return_value=([high_conf_patch], []),
            ),
        ):
            mock_fg_instance = MockFG.return_value
            mock_fg_instance.generate_fix = AsyncMock(return_value=[high_conf_patch])

            result = await runner.run_iterative_fix_cycle(
                tmp_path, npm_profile, max_iterations=3
            )

        assert result.iterations_run <= MAX_FIX_ITERATIONS
        assert result.iterations_run == 3
        assert result.final_success is False

    @pytest.mark.asyncio
    async def test_terminates_early_when_no_high_confidence_patches(
        self, runner: BuildRunner, npm_profile: ProjectProfile, tmp_path: Path
    ):
        """Cycle terminates early if no patches exceed confidence threshold.

        Requirements 7.2, 7.3: Only high-confidence patches are applied;
        if none available, cannot make progress and should stop.
        """
        errors = [_make_error()]
        low_conf_patch = _make_patch(confidence=0.5)  # Below threshold

        failing_result = _make_build_result(success=False, errors=errors)

        with (
            patch.object(
                runner, "run_build", new_callable=AsyncMock, return_value=failing_result
            ),
            patch(
                "infrastructure.analysis.universal_repo._iterative_cycle.FixGenerator"
            ) as MockFG,
        ):
            mock_fg_instance = MockFG.return_value
            mock_fg_instance.generate_fix = AsyncMock(return_value=[low_conf_patch])

            result = await runner.run_iterative_fix_cycle(
                tmp_path, npm_profile, max_iterations=3
            )

        # Should stop after first iteration since no high-confidence patches
        assert result.iterations_run == 1
        assert result.final_success is False
        assert len(result.errors_remaining) > 0

    @pytest.mark.asyncio
    async def test_stops_early_on_success(
        self, runner: BuildRunner, npm_profile: ProjectProfile, tmp_path: Path
    ):
        """Cycle stops before max iterations when build succeeds.

        Requirement 7.4: Report success when all errors resolved.
        """
        errors = [_make_error()]
        high_conf_patch = _make_patch(confidence=0.85)

        failing_result = _make_build_result(success=False, errors=errors)
        success_result = _make_build_result(success=True, errors=[])

        src_file = tmp_path / "src" / "app.ts"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text("const x = foo;\n")

        # First call fails, second (after fix) succeeds
        build_results = [failing_result, success_result]

        with (
            patch.object(
                runner,
                "run_build",
                new_callable=AsyncMock,
                side_effect=build_results,
            ),
            patch(
                "infrastructure.analysis.universal_repo._iterative_cycle.FixGenerator"
            ) as MockFG,
        ):
            mock_fg_instance = MockFG.return_value
            mock_fg_instance.generate_fix = AsyncMock(return_value=[high_conf_patch])

            result = await runner.run_iterative_fix_cycle(
                tmp_path, npm_profile, max_iterations=3
            )

        assert result.iterations_run == 1
        assert result.final_success is True


# ─── Tests: High-Confidence Filter (Requirement 7.2) ─────────────────────────


class TestHighConfidenceFilter:
    """Test that only patches with confidence > 0.7 are applied."""

    @pytest.mark.asyncio
    async def test_only_high_confidence_patches_applied(
        self, runner: BuildRunner, npm_profile: ProjectProfile, tmp_path: Path
    ):
        """Only patches with confidence > AUTO_APPLY_FIX_THRESHOLD are applied.

        Requirement 7.2: Apply patches with Confidence_Score above 0.7.
        """
        errors = [_make_error(file_path="src/a.ts"), _make_error(file_path="src/b.ts")]
        high_patch = _make_patch(file_path="src/a.ts", confidence=0.85, old_code="badA", new_code="goodA")
        low_patch = _make_patch(file_path="src/b.ts", confidence=0.5, old_code="badB", new_code="goodB")

        failing_result = _make_build_result(success=False, errors=errors)
        success_result = _make_build_result(success=True, errors=[])

        # Create source files
        (tmp_path / "src").mkdir(parents=True, exist_ok=True)
        (tmp_path / "src" / "a.ts").write_text("const x = badA;\n")
        (tmp_path / "src" / "b.ts").write_text("const y = badB;\n")

        build_calls = [failing_result, success_result]

        with (
            patch.object(
                runner,
                "run_build",
                new_callable=AsyncMock,
                side_effect=build_calls,
            ),
            patch(
                "infrastructure.analysis.universal_repo._iterative_cycle.FixGenerator"
            ) as MockFG,
        ):
            mock_fg_instance = MockFG.return_value
            # Return both high and low confidence patches
            mock_fg_instance.generate_fix = AsyncMock(
                side_effect=[[high_patch], [low_patch]]
            )

            result = await runner.run_iterative_fix_cycle(
                tmp_path, npm_profile, max_iterations=3
            )

        # High-confidence patch is applied, low-confidence is in failed list
        assert high_patch in result.patches_applied
        assert low_patch in result.patches_failed

    @pytest.mark.asyncio
    async def test_patches_at_exactly_threshold_are_not_applied(
        self, runner: BuildRunner, npm_profile: ProjectProfile, tmp_path: Path
    ):
        """Patches at exactly the threshold (0.7) are NOT applied.

        The filter uses > 0.7, not >= 0.7, so exactly 0.7 is excluded.
        """
        errors = [_make_error()]
        boundary_patch = _make_patch(confidence=AUTO_APPLY_FIX_THRESHOLD)  # 0.7 exactly

        failing_result = _make_build_result(success=False, errors=errors)

        with (
            patch.object(
                runner, "run_build", new_callable=AsyncMock, return_value=failing_result
            ),
            patch(
                "infrastructure.analysis.universal_repo._iterative_cycle.FixGenerator"
            ) as MockFG,
        ):
            mock_fg_instance = MockFG.return_value
            mock_fg_instance.generate_fix = AsyncMock(return_value=[boundary_patch])

            result = await runner.run_iterative_fix_cycle(
                tmp_path, npm_profile, max_iterations=3
            )

        # Patch at exactly threshold should NOT be applied
        assert boundary_patch not in result.patches_applied
        assert boundary_patch in result.patches_failed
        assert result.final_success is False


# ─── Tests: Success Reporting (Requirement 7.4) ──────────────────────────────


class TestSuccessReporting:
    """Test success reporting when all errors resolved."""

    @pytest.mark.asyncio
    async def test_success_when_initial_build_succeeds(
        self, runner: BuildRunner, npm_profile: ProjectProfile, tmp_path: Path
    ):
        """If initial build succeeds, returns success with 0 iterations.

        Requirement 7.4: Report success with summary of applied patches.
        """
        success_result = _make_build_result(success=True, errors=[])

        with patch.object(
            runner, "run_build", new_callable=AsyncMock, return_value=success_result
        ):
            result = await runner.run_iterative_fix_cycle(
                tmp_path, npm_profile, max_iterations=3
            )

        assert result.final_success is True
        assert result.iterations_run == 0
        assert result.errors_resolved == []
        assert result.errors_remaining == []
        assert result.patches_applied == []

    @pytest.mark.asyncio
    async def test_success_reports_applied_patches(
        self, runner: BuildRunner, npm_profile: ProjectProfile, tmp_path: Path
    ):
        """Success result includes summary of all applied patches.

        Requirement 7.4: Report success with a summary of applied patches.
        """
        errors = [_make_error()]
        high_patch = _make_patch(confidence=0.9, old_code="broken", new_code="fixed")

        failing_result = _make_build_result(success=False, errors=errors)
        success_result = _make_build_result(success=True, errors=[])

        src_file = tmp_path / "src" / "app.ts"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text("const x = broken;\n")

        with (
            patch.object(
                runner,
                "run_build",
                new_callable=AsyncMock,
                side_effect=[failing_result, success_result],
            ),
            patch(
                "infrastructure.analysis.universal_repo._iterative_cycle.FixGenerator"
            ) as MockFG,
        ):
            mock_fg_instance = MockFG.return_value
            mock_fg_instance.generate_fix = AsyncMock(return_value=[high_patch])

            result = await runner.run_iterative_fix_cycle(
                tmp_path, npm_profile, max_iterations=3
            )

        assert result.final_success is True
        assert len(result.patches_applied) > 0
        assert result.errors_resolved == errors

    @pytest.mark.asyncio
    async def test_success_includes_all_build_results(
        self, runner: BuildRunner, npm_profile: ProjectProfile, tmp_path: Path
    ):
        """Success result includes the history of all build results.

        Requirement 7.4: Report success after fix-rebuild cycle.
        """
        errors = [_make_error()]
        high_patch = _make_patch(confidence=0.9, old_code="bad", new_code="good")

        failing_result = _make_build_result(success=False, errors=errors)
        success_result = _make_build_result(success=True, errors=[])

        src_file = tmp_path / "src" / "app.ts"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text("const x = bad;\n")

        with (
            patch.object(
                runner,
                "run_build",
                new_callable=AsyncMock,
                side_effect=[failing_result, success_result],
            ),
            patch(
                "infrastructure.analysis.universal_repo._iterative_cycle.FixGenerator"
            ) as MockFG,
        ):
            mock_fg_instance = MockFG.return_value
            mock_fg_instance.generate_fix = AsyncMock(return_value=[high_patch])

            result = await runner.run_iterative_fix_cycle(
                tmp_path, npm_profile, max_iterations=3
            )

        # Should have initial build + 1 rebuild
        assert len(result.build_results) == 2
        assert result.build_results[0].success is False
        assert result.build_results[1].success is True


# ─── Tests: Remaining Errors Reporting (Requirement 7.5) ──────────────────────


class TestRemainingErrorsReporting:
    """Test remaining errors reporting after max iterations."""

    @pytest.mark.asyncio
    async def test_reports_remaining_errors_after_max_iterations(
        self, runner: BuildRunner, npm_profile: ProjectProfile, tmp_path: Path
    ):
        """After max iterations, remaining errors are reported.

        Requirement 7.5: Report remaining errors with all attempted fixes.
        """
        errors = [_make_error(file_path="src/a.ts"), _make_error(file_path="src/b.ts")]
        high_patch = _make_patch(confidence=0.85, old_code="broken", new_code="fixed")

        failing_result = _make_build_result(success=False, errors=errors)

        with (
            patch.object(
                runner, "run_build", new_callable=AsyncMock, return_value=failing_result
            ),
            patch(
                "infrastructure.analysis.universal_repo._iterative_cycle.FixGenerator"
            ) as MockFG,
            patch(
                "infrastructure.analysis.universal_repo._iterative_cycle._apply_patches",
                return_value=([high_patch], []),
            ),
        ):
            mock_fg_instance = MockFG.return_value
            mock_fg_instance.generate_fix = AsyncMock(return_value=[high_patch])

            result = await runner.run_iterative_fix_cycle(
                tmp_path, npm_profile, max_iterations=3
            )

        assert result.final_success is False
        assert result.iterations_run == MAX_FIX_ITERATIONS
        assert len(result.errors_remaining) > 0
        assert len(result.patches_applied) > 0

    @pytest.mark.asyncio
    async def test_reports_all_attempted_fixes(
        self, runner: BuildRunner, npm_profile: ProjectProfile, tmp_path: Path
    ):
        """After failure, result includes both applied and failed patches.

        Requirement 7.5: Report all attempted fixes and their outcomes.
        """
        errors = [_make_error(file_path="src/a.ts"), _make_error(file_path="src/b.ts")]
        high_patch = _make_patch(file_path="src/a.ts", confidence=0.85, old_code="err1", new_code="fix1")
        low_patch = _make_patch(file_path="src/b.ts", confidence=0.4, old_code="err2", new_code="fix2")

        failing_result = _make_build_result(success=False, errors=errors)

        (tmp_path / "src").mkdir(parents=True, exist_ok=True)
        (tmp_path / "src" / "a.ts").write_text("const x = err1;\n")
        (tmp_path / "src" / "b.ts").write_text("const y = err2;\n")

        with (
            patch.object(
                runner, "run_build", new_callable=AsyncMock, return_value=failing_result
            ),
            patch(
                "infrastructure.analysis.universal_repo._iterative_cycle.FixGenerator"
            ) as MockFG,
        ):
            mock_fg_instance = MockFG.return_value
            # First error gets high confidence, second gets low confidence
            mock_fg_instance.generate_fix = AsyncMock(
                side_effect=[[high_patch], [low_patch]]
            )

            result = await runner.run_iterative_fix_cycle(
                tmp_path, npm_profile, max_iterations=1
            )

        # Low-confidence patches are tracked in patches_failed
        assert low_patch in result.patches_failed

    @pytest.mark.asyncio
    async def test_tracks_resolved_errors_between_iterations(
        self, runner: BuildRunner, npm_profile: ProjectProfile, tmp_path: Path
    ):
        """Errors that disappear between builds are tracked as resolved.

        Requirements 7.4, 7.5: Track which errors get resolved vs remain.
        """
        error_a = _make_error(file_path="src/a.ts", line=10, code="TS2304")
        error_b = _make_error(file_path="src/b.ts", line=20, code="TS2339")
        high_patch = _make_patch(confidence=0.85, old_code="bad", new_code="good")

        # First build: both errors. Second build: only error_b remains. Third: still error_b.
        result_both = _make_build_result(success=False, errors=[error_a, error_b])
        result_one = _make_build_result(success=False, errors=[error_b])

        # Initial build + up to 3 rebuilds = 4 total calls
        build_calls = [result_both, result_one, result_one, result_one]

        with (
            patch.object(
                runner,
                "run_build",
                new_callable=AsyncMock,
                side_effect=build_calls,
            ),
            patch(
                "infrastructure.analysis.universal_repo._iterative_cycle.FixGenerator"
            ) as MockFG,
            patch(
                "infrastructure.analysis.universal_repo._iterative_cycle._apply_patches",
                return_value=([high_patch], []),
            ),
        ):
            mock_fg_instance = MockFG.return_value
            mock_fg_instance.generate_fix = AsyncMock(return_value=[high_patch])

            result = await runner.run_iterative_fix_cycle(
                tmp_path, npm_profile, max_iterations=3
            )

        # error_a should be resolved (disappeared after iteration 1)
        assert error_a in result.errors_resolved
        # error_b should remain
        assert error_b in result.errors_remaining
