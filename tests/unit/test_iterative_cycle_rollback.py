"""Tests for regression rollback in the iterative build-fix cycle.

When an iteration's patches cause the rebuild to report MORE errors than
before, the cycle must restore the pre-iteration file state and stop,
instead of leaving the workspace worse than it found it.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from infrastructure.analysis.universal_repo._iterative_cycle import (
    _restore_files,
    _snapshot_files,
    run_iterative_fix_cycle,
)
from infrastructure.analysis.universal_repo.models import (
    BuildCommand,
    BuildResult,
    BuildToolInfo,
    CompilerError,
    FixPatch,
    LanguageDistribution,
    LanguageStats,
    ProjectProfile,
)


def _make_error(file_path: str = "main.c", line: int = 1, code: str = "E1") -> CompilerError:
    return CompilerError(
        file_path=file_path,
        line=line,
        column=0,
        severity="error",
        error_code=code,
        message="boom",
        compiler="gcc",
    )


def _make_patch(confidence: float = 0.9, file_path: str = "main.c") -> FixPatch:
    return FixPatch(
        file_path=file_path,
        line_start=1,
        line_end=1,
        old_code="old",
        new_code="new",
        explanation="test patch",
        confidence=confidence,
        source="template",
    )


def _make_build_result(success: bool, errors: list[CompilerError]) -> BuildResult:
    return BuildResult(
        success=success,
        errors=errors,
        warnings=[],
        output="build output",
        duration_ms=100.0,
        command=BuildCommand(
            command=["make"],
            working_directory=Path("/tmp"),
            environment={},
            timeout_seconds=180,
        ),
    )


@pytest.fixture
def profile(tmp_path: Path) -> ProjectProfile:
    return ProjectProfile(
        repo_path=tmp_path,
        languages=LanguageDistribution(
            primary_language="C",
            languages={"C": LanguageStats(1, 10, 100.0, 100.0)},
        ),
        frameworks=[],
        build_tools=[
            BuildToolInfo(
                name="make",
                config_file=tmp_path / "Makefile",
                build_commands=["make"],
                relevance_score=1.0,
            )
        ],
        entry_points=[],
        dependency_manifests=[],
        confidence=0.9,
        detected_at=datetime.now(),
        file_tree_hash="abc123",
    )


class TestSnapshotRestore:
    def test_snapshot_and_restore_roundtrip(self, tmp_path: Path):
        target = tmp_path / "main.c"
        target.write_text("original", encoding="utf-8")
        patches = [_make_patch(file_path="main.c")]

        snapshot = _snapshot_files(tmp_path, patches)
        target.write_text("mutated", encoding="utf-8")
        _restore_files(snapshot)

        assert target.read_text(encoding="utf-8") == "original"

    def test_snapshot_of_missing_file_restores_to_absent(self, tmp_path: Path):
        patches = [_make_patch(file_path="created_later.c")]
        snapshot = _snapshot_files(tmp_path, patches)

        created = tmp_path / "created_later.c"
        created.write_text("should vanish on rollback", encoding="utf-8")
        _restore_files(snapshot)

        assert not created.exists()


class TestRegressionRollback:
    @pytest.mark.asyncio
    async def test_regressing_iteration_rolls_back_and_stops(
        self, tmp_path: Path, profile: ProjectProfile, monkeypatch
    ):
        target = tmp_path / "main.c"
        target.write_text("int main() { old }", encoding="utf-8")

        one_error = [_make_error(code="E1")]
        worse_errors = [_make_error(code="E1"), _make_error(line=2, code="E2")]

        runner = AsyncMock()
        runner.run_build = AsyncMock(
            side_effect=[
                _make_build_result(False, one_error),     # initial build
                _make_build_result(False, worse_errors),  # rebuild regressed
            ]
        )

        async def fake_generate_fix(self, error, context):
            return [_make_patch(confidence=0.9)]

        monkeypatch.setattr(
            "infrastructure.analysis.universal_repo.fix_generator."
            "FixGenerator.generate_fix",
            fake_generate_fix,
        )

        result = await run_iterative_fix_cycle(
            runner, tmp_path, profile, max_iterations=3
        )

        assert result.final_success is False
        assert result.iterations_run == 1
        # Errors reported are the PRE-regression set (state was restored)
        assert [e.error_code for e in result.errors_remaining] == ["E1"]
        # The regressive patch is reported as failed, not applied
        assert result.patches_applied == []
        assert any(p.explanation == "test patch" for p in result.patches_failed)
        # Workspace content was rolled back
        assert target.read_text(encoding="utf-8") == "int main() { old }"

    @pytest.mark.asyncio
    async def test_non_regressing_iteration_keeps_patches(
        self, tmp_path: Path, profile: ProjectProfile, monkeypatch
    ):
        target = tmp_path / "main.c"
        target.write_text("int main() { old }", encoding="utf-8")

        runner = AsyncMock()
        runner.run_build = AsyncMock(
            side_effect=[
                _make_build_result(False, [_make_error(code="E1")]),
                _make_build_result(True, []),  # rebuild succeeds
            ]
        )

        async def fake_generate_fix(self, error, context):
            return [_make_patch(confidence=0.9)]

        monkeypatch.setattr(
            "infrastructure.analysis.universal_repo.fix_generator."
            "FixGenerator.generate_fix",
            fake_generate_fix,
        )

        result = await run_iterative_fix_cycle(
            runner, tmp_path, profile, max_iterations=3
        )

        assert result.final_success is True
        assert len(result.patches_applied) == 1
        # The fix stayed applied (no rollback)
        assert target.read_text(encoding="utf-8") == "int main() { new }"
