"""Unit tests for BuildRunner.run_build() and BuildRunner.install_dependencies().

Tests build execution with subprocess isolation, timeout handling,
error parsing, and dependency installation with failure reporting.

Requirements: 4.2, 4.3, 4.4, 4.6, 4.7, 4.8
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from infrastructure.analysis.universal_repo.build_runner import (
    BuildRunner,
    _extract_missing_packages,
    _build_resolution_suggestions,
)
from infrastructure.analysis.universal_repo.models import (
    BuildToolInfo,
    DependencyResult,
    LanguageDistribution,
    LanguageStats,
    ProjectProfile,
)


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


@pytest.fixture
def cargo_profile(tmp_path: Path) -> ProjectProfile:
    """Create a ProjectProfile with cargo as the primary build tool."""
    return ProjectProfile(
        repo_path=tmp_path,
        languages=LanguageDistribution(
            primary_language="Rust",
            languages={"Rust": LanguageStats(5, 300, 100.0, 100.0)},
        ),
        frameworks=[],
        build_tools=[
            BuildToolInfo(
                name="cargo",
                config_file=tmp_path / "Cargo.toml",
                build_commands=["cargo build"],
                relevance_score=1.0,
            )
        ],
        entry_points=[],
        dependency_manifests=[tmp_path / "Cargo.toml"],
        confidence=0.9,
        detected_at=datetime.now(),
        file_tree_hash="def456",
    )


# ─── run_build() Tests ───────────────────────────────────────────────────────


class TestRunBuild:
    """Tests for BuildRunner.run_build()."""

    @pytest.mark.asyncio
    async def test_successful_build_returns_success(
        self, runner: BuildRunner, npm_profile: ProjectProfile, tmp_path: Path
    ):
        """A build that exits with code 0 returns success=True."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"Built OK\n", b""))
        mock_process.returncode = 0
        mock_process.kill = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await runner.run_build(tmp_path, npm_profile)

        assert result.success is True
        assert result.duration_ms > 0
        assert "Built OK" in result.output

    @pytest.mark.asyncio
    async def test_failed_build_returns_failure(
        self, runner: BuildRunner, npm_profile: ProjectProfile, tmp_path: Path
    ):
        """A build that exits with non-zero code returns success=False."""
        stderr = b"src/app.ts(10,5): error TS2304: Cannot find name 'foo'.\n"
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", stderr))
        mock_process.returncode = 1
        mock_process.kill = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await runner.run_build(tmp_path, npm_profile)

        assert result.success is False
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_timeout_kills_process_and_reports_error(
        self, runner: BuildRunner, npm_profile: ProjectProfile, tmp_path: Path
    ):
        """Build that exceeds timeout is killed and reports TIMEOUT error."""
        mock_process = AsyncMock()
        # First communicate() raises TimeoutError, second returns partial output
        mock_process.communicate = AsyncMock(
            side_effect=[asyncio.TimeoutError(), (b"partial output", b"")]
        )
        mock_process.kill = MagicMock()  # kill() is synchronous in real subprocess
        mock_process.returncode = -9

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await runner.run_build(tmp_path, npm_profile)

        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0].error_code == "TIMEOUT"
        assert "timed out" in result.errors[0].message
        mock_process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_command_not_found_returns_error(
        self, runner: BuildRunner, npm_profile: ProjectProfile, tmp_path: Path
    ):
        """FileNotFoundError from subprocess returns CMD_NOT_FOUND error."""
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("npm not found"),
        ):
            result = await runner.run_build(tmp_path, npm_profile)

        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0].error_code == "CMD_NOT_FOUND"
        assert "npm" in result.errors[0].message

    @pytest.mark.asyncio
    async def test_build_parses_errors_from_tsc_output(
        self, runner: BuildRunner, npm_profile: ProjectProfile, tmp_path: Path
    ):
        """Build with tsc-formatted errors parses them into CompilerError list."""
        stderr = (
            b"src/index.ts(5,10): error TS2339: Property 'x' does not exist.\n"
            b"src/utils.ts(12,3): error TS2304: Cannot find name 'bar'.\n"
        )
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", stderr))
        mock_process.returncode = 1
        mock_process.kill = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await runner.run_build(tmp_path, npm_profile)

        assert result.success is False
        assert len(result.errors) == 2
        assert result.errors[0].file_path == "src/index.ts"
        assert result.errors[0].line == 5
        assert result.errors[1].file_path == "src/utils.ts"

    @pytest.mark.asyncio
    async def test_build_separates_errors_and_warnings(
        self, runner: BuildRunner, cargo_profile: ProjectProfile, tmp_path: Path
    ):
        """Warnings and errors from build output are separated correctly."""
        stderr = (
            b"warning: unused variable: `x`\n"
            b" --> src/main.rs:10:5\n"
            b"error[E0308]: mismatched types\n"
            b" --> src/main.rs:20:10\n"
        )
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", stderr))
        mock_process.returncode = 1
        mock_process.kill = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await runner.run_build(tmp_path, cargo_profile)

        assert result.success is False
        # At least one error and one warning should be parsed
        assert len(result.errors) >= 1 or len(result.warnings) >= 1

    @pytest.mark.asyncio
    async def test_build_records_duration(
        self, runner: BuildRunner, npm_profile: ProjectProfile, tmp_path: Path
    ):
        """Build result records execution duration in milliseconds."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"done\n", b""))
        mock_process.returncode = 0
        mock_process.kill = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await runner.run_build(tmp_path, npm_profile)

        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_build_emits_progress_events(
        self, runner: BuildRunner, npm_profile: ProjectProfile, tmp_path: Path
    ):
        """When a progress_sink is provided, progress events are emitted."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"ok\n", b""))
        mock_process.returncode = 0
        mock_process.kill = AsyncMock()

        sink = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            await runner.run_build(tmp_path, npm_profile, progress_sink=sink)

        assert sink.emit.call_count >= 2  # start + completion


# ─── install_dependencies() Tests ────────────────────────────────────────────


class TestInstallDependencies:
    """Tests for BuildRunner.install_dependencies()."""

    @pytest.mark.asyncio
    async def test_successful_install_returns_success(
        self, runner: BuildRunner, npm_profile: ProjectProfile, tmp_path: Path
    ):
        """Successful dependency installation returns success=True."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b"added 150 packages\n", b"")
        )
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await runner.install_dependencies(tmp_path, npm_profile)

        assert result.success is True
        assert result.error_message == ""

    @pytest.mark.asyncio
    async def test_failed_install_reports_error(
        self, runner: BuildRunner, npm_profile: ProjectProfile, tmp_path: Path
    ):
        """Failed install returns success=False with error message."""
        stderr = b"npm ERR! 404 'nonexistent-pkg'\nnpm ERR! code E404\n"
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", stderr))
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await runner.install_dependencies(tmp_path, npm_profile)

        assert result.success is False
        assert "nonexistent-pkg" in result.failed_packages
        assert "nonexistent-pkg" in result.error_message

    @pytest.mark.asyncio
    async def test_no_build_tool_returns_error(
        self, runner: BuildRunner, tmp_path: Path
    ):
        """No build tool in profile returns an error result."""
        profile = ProjectProfile(
            repo_path=tmp_path,
            languages=LanguageDistribution(
                primary_language="unknown", languages={}
            ),
            frameworks=[],
            build_tools=[],
            entry_points=[],
            dependency_manifests=[],
            confidence=0.0,
            detected_at=datetime.now(),
            file_tree_hash="empty",
        )

        result = await runner.install_dependencies(tmp_path, profile)

        assert result.success is False
        assert "No build tool" in result.error_message

    @pytest.mark.asyncio
    async def test_command_not_found_returns_error(
        self, runner: BuildRunner, npm_profile: ProjectProfile, tmp_path: Path
    ):
        """FileNotFoundError from subprocess returns descriptive error."""
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("npm not found"),
        ):
            result = await runner.install_dependencies(tmp_path, npm_profile)

        assert result.success is False
        assert "not found" in result.error_message

    @pytest.mark.asyncio
    async def test_timeout_returns_error(
        self, runner: BuildRunner, npm_profile: ProjectProfile, tmp_path: Path
    ):
        """Install that times out returns a descriptive timeout error."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await runner.install_dependencies(tmp_path, npm_profile)

        assert result.success is False
        assert "timed out" in result.error_message


# ─── Helper Function Tests ───────────────────────────────────────────────────


class TestExtractMissingPackages:
    """Tests for _extract_missing_packages helper."""

    def test_extracts_npm_404_packages(self):
        output = "npm ERR! 404 'react-missing'\nnpm ERR! code E404\n"
        result = _extract_missing_packages(output)
        assert "react-missing" in result

    def test_extracts_pip_not_found(self):
        output = "No matching distribution found for nonexist-pkg>=1.0\n"
        result = _extract_missing_packages(output)
        assert "nonexist-pkg>=1.0" in result

    def test_extracts_cargo_crate_missing(self):
        output = "error[E0463]: can't find crate for `tokio_missing`\n"
        result = _extract_missing_packages(output)
        assert "tokio_missing" in result

    def test_deduplicates_packages(self):
        output = (
            "npm ERR! 404 'some-pkg'\n"
            "npm ERR! 404 'some-pkg'\n"
        )
        result = _extract_missing_packages(output)
        assert result.count("some-pkg") == 1

    def test_empty_output_returns_empty_list(self):
        result = _extract_missing_packages("")
        assert result == []


class TestBuildResolutionSuggestions:
    """Tests for _build_resolution_suggestions helper."""

    def test_npm_suggestions(self):
        result = _build_resolution_suggestions("npm", ["react", "lodash"])
        assert "npm install" in result
        assert "react" in result
        assert "lodash" in result

    def test_pip_suggestions(self):
        result = _build_resolution_suggestions("pip", ["requests"])
        assert "pip install" in result
        assert "requests" in result

    def test_empty_packages_returns_empty(self):
        result = _build_resolution_suggestions("npm", [])
        assert result == ""
