"""Build runner with command construction and iterative fix cycles.

Discovers and executes build commands based on a ProjectProfile's detected
build tools. Supports npm/yarn/pnpm, cargo, go, make, cmake, gradle, and
maven build systems.

Requirements: 4.1, 4.2, 4.3, 4.4, 4.6, 4.7, 4.8, 7.1
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .error_parser import ErrorParser
from .models import (
    BuildCommand,
    BuildResult,
    BuildToolInfo,
    CompilerError,
    DependencyResult,
    IterativeBuildResult,
    PipelineProgressEvent,
    ProjectProfile,
    DEFAULT_BUILD_TIMEOUT_SECONDS,
)

if TYPE_CHECKING:
    from . import StreamSink

logger = logging.getLogger(__name__)


# ─── Build Tool Command Mapping ──────────────────────────────────────────────

# Maps build tool name to the default command list for building.
_BUILD_TOOL_COMMANDS: dict[str, list[str]] = {
    "npm": ["npm", "run", "build"],
    "yarn": ["yarn", "build"],
    "pnpm": ["pnpm", "run", "build"],
    "cargo": ["cargo", "build"],
    "go": ["go", "build", "./..."],
    "make": ["make"],
    "cmake": ["cmake", "--build", "build"],
    "gradle": ["./gradlew", "build"],
    "maven": ["mvn", "compile"],
}

# Maps build tool name to the dependency installation command.
_INSTALL_COMMANDS: dict[str, list[str]] = {
    "npm": ["npm", "install"],
    "yarn": ["yarn", "install"],
    "pnpm": ["pnpm", "install"],
    "cargo": ["cargo", "fetch"],
    "go": ["go", "mod", "download"],
    "pip": ["pip", "install", "-e", "."],
    "poetry": ["poetry", "install"],
    "setuptools": ["pip", "install", "-e", "."],
    "gradle": ["./gradlew", "dependencies"],
    "maven": ["mvn", "dependency:resolve"],
}

# Maps build tool name to the compiler name used by ErrorParser.
_TOOL_TO_COMPILER: dict[str, str] = {
    "npm": "tsc",
    "yarn": "tsc",
    "pnpm": "tsc",
    "cargo": "rustc",
    "go": "go",
    "make": "gcc",
    "cmake": "gcc",
    "gradle": "javac",
    "maven": "javac",
}

# Regex for extracting missing package names from install failure output.
_MISSING_PACKAGE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"npm ERR! 404\s+'([^']+)'"),
    re.compile(r"npm ERR! notarget No matching version found for ([^\s]+)"),
    re.compile(r"error\[E0463\]: can't find crate for `([^`]+)`"),
    re.compile(r"No matching distribution found for ([^\s]+)"),
    re.compile(r"Could not find artifact ([^\s]+)"),
    re.compile(r"cannot find package \"([^\"]+)\""),
    re.compile(r"ERROR: Could not find a version that satisfies the requirement ([^\s]+)"),
]


class BuildRunner:
    """Discovers and executes build commands with iterative fix cycles.

    Given a ProjectProfile produced by ProjectDetector, constructs the
    appropriate build command for the highest-relevance build tool, executes
    builds with subprocess isolation and timeout, and supports iterative
    fix-rebuild cycles.

    Requirement: 4.1 — Construct appropriate Build_Command from Project_Profile.
    """

    def construct_build_command(self, profile: ProjectProfile) -> BuildCommand:
        """Construct the appropriate build command from the project profile.

        Selects the highest-relevance build tool from the profile and maps
        it to the corresponding shell command.

        Args:
            profile: A ProjectProfile containing detected build tools.

        Returns:
            A BuildCommand with the command list, working directory, empty
            environment overrides, and the default timeout.

        Raises:
            ValueError: If no build tools are detected in the profile.
        """
        if not profile.build_tools:
            raise ValueError("no_build_tool_detected")

        # Select the first (highest relevance) build tool
        primary_tool: BuildToolInfo = profile.build_tools[0]
        tool_name = primary_tool.name.lower()

        command = _BUILD_TOOL_COMMANDS.get(tool_name)
        if command is None:
            raise ValueError(
                f"Unsupported build tool: '{tool_name}'. "
                f"Supported tools: {sorted(_BUILD_TOOL_COMMANDS.keys())}"
            )

        return BuildCommand(
            command=list(command),  # Copy to prevent mutation
            working_directory=profile.repo_path,
            environment={},
            timeout_seconds=DEFAULT_BUILD_TIMEOUT_SECONDS,
        )

    async def run_build(
        self,
        repo_path: Path,
        profile: ProjectProfile,
        progress_sink: StreamSink | None = None,
    ) -> BuildResult:
        """Execute build and capture errors.

        Runs the build command as a subprocess with configurable timeout.
        Parses stdout/stderr for compiler errors via ErrorParser.

        Args:
            repo_path: Root path of the repository.
            profile: Detected project profile with build tool information.
            progress_sink: Optional sink for streaming progress events.

        Returns:
            A BuildResult indicating the outcome of the build.

        Requirements: 4.2, 4.3, 4.4, 4.6
        """
        build_command = self.construct_build_command(profile)
        tool_name = profile.build_tools[0].name.lower()
        compiler = _TOOL_TO_COMPILER.get(tool_name, "gcc")

        start_time = time.perf_counter()

        if progress_sink:
            await progress_sink.emit(PipelineProgressEvent(
                phase="build",
                progress_percent=0.0,
                message=f"Starting build: {' '.join(build_command.command)}",
            ))

        try:
            process = await asyncio.create_subprocess_exec(
                *build_command.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(build_command.working_directory),
                env=build_command.environment or None,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=build_command.timeout_seconds,
                )
            except asyncio.TimeoutError:
                # Kill the process on timeout
                process.kill()
                # Collect any partial output available
                partial_stdout = b""
                partial_stderr = b""
                try:
                    partial_stdout, partial_stderr = await asyncio.wait_for(
                        process.communicate(), timeout=5,
                    )
                except (asyncio.TimeoutError, ProcessLookupError):
                    pass

                duration_ms = (time.perf_counter() - start_time) * 1000
                partial_output = (
                    partial_stdout.decode(errors="replace")
                    + partial_stderr.decode(errors="replace")
                )
                timeout_error = CompilerError(
                    file_path="",
                    line=0,
                    column=0,
                    severity="error",
                    error_code="TIMEOUT",
                    message=(
                        f"Build timed out after {build_command.timeout_seconds}s. "
                        f"Partial output captured."
                    ),
                    compiler=compiler,
                    raw_output=partial_output,
                )

                if progress_sink:
                    await progress_sink.emit(PipelineProgressEvent(
                        phase="build",
                        progress_percent=100.0,
                        message="Build timed out",
                        data={"timeout_seconds": build_command.timeout_seconds},
                    ))

                return BuildResult(
                    success=False,
                    errors=[timeout_error],
                    warnings=[],
                    output=partial_output,
                    duration_ms=duration_ms,
                    command=build_command,
                )

        except FileNotFoundError:
            duration_ms = (time.perf_counter() - start_time) * 1000
            not_found_error = CompilerError(
                file_path="",
                line=0,
                column=0,
                severity="error",
                error_code="CMD_NOT_FOUND",
                message=f"Build command not found: {build_command.command[0]}",
                compiler=compiler,
            )
            return BuildResult(
                success=False,
                errors=[not_found_error],
                warnings=[],
                output="",
                duration_ms=duration_ms,
                command=build_command,
            )

        duration_ms = (time.perf_counter() - start_time) * 1000
        stdout_text = stdout_bytes.decode(errors="replace")
        stderr_text = stderr_bytes.decode(errors="replace")
        combined_output = stdout_text + stderr_text

        # Parse compiler errors from output
        errors: list[CompilerError] = []
        warnings: list[CompilerError] = []

        error_parser = ErrorParser.create_default()
        try:
            parsed = error_parser.parse(combined_output, compiler)
            for err in parsed:
                if err.severity == "warning":
                    warnings.append(err)
                else:
                    errors.append(err)
        except ValueError:
            # No parser registered for this compiler — skip structured parsing
            logger.debug("No parser for compiler '%s', skipping error parsing", compiler)

        success = process.returncode == 0

        if progress_sink:
            await progress_sink.emit(PipelineProgressEvent(
                phase="build",
                progress_percent=100.0,
                message="Build complete" if success else "Build failed",
                data={
                    "return_code": process.returncode,
                    "error_count": len(errors),
                    "warning_count": len(warnings),
                },
            ))

        return BuildResult(
            success=success,
            errors=errors,
            warnings=warnings,
            output=combined_output,
            duration_ms=duration_ms,
            command=build_command,
        )

    async def install_dependencies(
        self,
        repo_path: Path,
        profile: ProjectProfile,
    ) -> DependencyResult:
        """Run dependency installation as a pre-build step.

        Maps the detected build tool to the appropriate install command
        and executes it. Parses failure output for missing package names.

        Args:
            repo_path: Root path of the repository.
            profile: Detected project profile with build tool information.

        Returns:
            A DependencyResult indicating the outcome of installation.

        Requirements: 4.7, 4.8
        """
        if not profile.build_tools:
            return DependencyResult(
                success=False,
                installed_packages=[],
                failed_packages=[],
                error_message="No build tool detected; cannot determine install command.",
            )

        tool_name = profile.build_tools[0].name.lower()
        install_cmd = _INSTALL_COMMANDS.get(tool_name)

        if install_cmd is None:
            return DependencyResult(
                success=False,
                installed_packages=[],
                failed_packages=[],
                error_message=(
                    f"No install command configured for tool '{tool_name}'. "
                    f"Supported tools: {sorted(_INSTALL_COMMANDS.keys())}"
                ),
            )

        try:
            process = await asyncio.create_subprocess_exec(
                *install_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(repo_path),
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=DEFAULT_BUILD_TIMEOUT_SECONDS,
            )
        except FileNotFoundError:
            return DependencyResult(
                success=False,
                installed_packages=[],
                failed_packages=[],
                error_message=(
                    f"Install command not found: '{install_cmd[0]}'. "
                    f"Ensure the tool is installed and available on PATH."
                ),
            )
        except asyncio.TimeoutError:
            return DependencyResult(
                success=False,
                installed_packages=[],
                failed_packages=[],
                error_message=(
                    f"Dependency installation timed out after "
                    f"{DEFAULT_BUILD_TIMEOUT_SECONDS}s."
                ),
            )

        stdout_text = stdout_bytes.decode(errors="replace")
        stderr_text = stderr_bytes.decode(errors="replace")
        combined_output = stdout_text + stderr_text

        if process.returncode == 0:
            return DependencyResult(
                success=True,
                installed_packages=[],
                failed_packages=[],
                error_message="",
            )

        # Parse output for missing packages
        failed_packages = _extract_missing_packages(combined_output)
        suggestions = _build_resolution_suggestions(tool_name, failed_packages)

        return DependencyResult(
            success=False,
            installed_packages=[],
            failed_packages=failed_packages,
            error_message=(
                f"Dependency installation failed (exit code {process.returncode}). "
                + (suggestions if suggestions else combined_output[:500])
            ),
        )

    async def run_iterative_fix_cycle(
        self,
        repo_path: Path,
        profile: ProjectProfile,
        max_iterations: int = 3,
        progress_sink: "StreamSink | None" = None,
    ) -> IterativeBuildResult:
        """Run build → fix → rebuild cycle.

        Executes the iterative cycle: build → parse errors → generate fixes
        → apply high-confidence patches → rebuild, up to max_iterations.

        Args:
            repo_path: Root path of the repository.
            profile: Detected project profile with build tool information.
            max_iterations: Maximum number of fix-rebuild cycles (default 3).
            progress_sink: Optional sink for streaming progress events.

        Returns:
            An IterativeBuildResult with cycle outcomes.

        Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
        """
        from ._iterative_cycle import run_iterative_fix_cycle as _run_cycle

        return await _run_cycle(
            runner=self,
            repo_path=repo_path,
            profile=profile,
            max_iterations=max_iterations,
            progress_sink=progress_sink,
        )


# ─── Helper Functions ────────────────────────────────────────────────────────


def _extract_missing_packages(output: str) -> list[str]:
    """Extract missing package names from install failure output.

    Scans output against known regex patterns for common package managers.

    Args:
        output: Combined stdout+stderr from the install command.

    Returns:
        Deduplicated list of package names that appear to be missing.
    """
    packages: list[str] = []
    for pattern in _MISSING_PACKAGE_PATTERNS:
        matches = pattern.findall(output)
        packages.extend(matches)
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for pkg in packages:
        if pkg not in seen:
            seen.add(pkg)
            unique.append(pkg)
    return unique


def _build_resolution_suggestions(tool_name: str, failed_packages: list[str]) -> str:
    """Build human-readable resolution suggestions for failed packages.

    Args:
        tool_name: The build tool that triggered install (e.g., "npm", "pip").
        failed_packages: List of package names that failed to install.

    Returns:
        A suggestion string, or empty string if no packages were identified.
    """
    if not failed_packages:
        return ""

    pkg_list = ", ".join(failed_packages)
    suggestions_map: dict[str, str] = {
        "npm": f"Try: npm install {' '.join(failed_packages)} --save",
        "yarn": f"Try: yarn add {' '.join(failed_packages)}",
        "pnpm": f"Try: pnpm add {' '.join(failed_packages)}",
        "pip": f"Try: pip install {' '.join(failed_packages)}",
        "poetry": f"Try: poetry add {' '.join(failed_packages)}",
        "setuptools": f"Try: pip install {' '.join(failed_packages)}",
        "cargo": f"Check that crates exist: {pkg_list}",
        "go": f"Try: go get {' '.join(failed_packages)}",
        "gradle": f"Add missing dependencies to build.gradle: {pkg_list}",
        "maven": f"Add missing dependencies to pom.xml: {pkg_list}",
    }

    suggestion = suggestions_map.get(tool_name, f"Missing packages: {pkg_list}")
    return f"Missing packages: {pkg_list}. {suggestion}"
