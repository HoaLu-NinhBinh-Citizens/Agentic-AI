"""
Async build pipeline for parallel compilation.

Provides:
- Parallel CMake configure + build
- Async subprocess execution
- Build cache (Ninja) integration
- Build graph with dependency tracking
- Progress reporting
"""

import asyncio
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class AsyncBuildResult:
    """Result of an async build step."""

    def __init__(
        self,
        step: str,
        status: str,
        stdout: str = "",
        stderr: str = "",
        returncode: int = 0,
        elapsed_seconds: float = 0.0,
    ):
        self.step = step
        self.status = status  # "success", "failed", "timeout"
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.elapsed_seconds = elapsed_seconds

    @property
    def success(self) -> bool:
        return self.status == "success" and self.returncode == 0


class AsyncBuildStep:
    """A single step in the build pipeline."""

    def __init__(
        self,
        name: str,
        command: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout_seconds: int = 300,
        depends_on: Optional[List[str]] = None,
    ):
        self.name = name
        self.command = command
        self.cwd = cwd or os.getcwd()
        self.env = env
        self.timeout_seconds = timeout_seconds
        self.depends_on = depends_on or []
        self._result: Optional[AsyncBuildResult] = None

    @property
    def result(self) -> Optional[AsyncBuildResult]:
        return self._result

    def __repr__(self) -> str:
        return f"BuildStep({self.name})"


class AsyncBuildPipeline:
    """
    Async build pipeline that executes steps in dependency order.

    Supports:
    - Parallel execution of independent steps
    - Dependency graph resolution
    - Timeout handling
    - Environment variable injection
    - Ninja build cache support
    """

    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root)
        self.steps: List[AsyncBuildStep] = []
        self._step_by_name: Dict[str, AsyncBuildStep] = {}

    def add_step(self, step: AsyncBuildStep):
        """Add a build step to the pipeline."""
        self.steps.append(step)
        self._step_by_name[step.name] = step

    def add_cmake_configure(
        self,
        name: str,
        source_dir: str,
        build_dir: str,
        cmake_args: Optional[List[str]] = None,
        generator: str = "Ninja",
        depends_on: Optional[List[str]] = None,
    ) -> AsyncBuildStep:
        """Add a CMake configure step."""
        cmake_path = self._find_cmake()
        build_path = Path(build_dir)
        build_path.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(cmake_path),
            "-S", str(Path(source_dir)),
            "-B", str(build_path),
            f"-DCMAKE_BUILD_TYPE=Release",
        ]
        if generator:
            cmd.extend(["-G", generator])
        if cmake_args:
            cmd.extend(cmake_args)

        step = AsyncBuildStep(
            name=name,
            command=cmd,
            cwd=str(self.workspace_root),
            depends_on=depends_on,
        )
        self.add_step(step)
        return step

    def add_cmake_build(
        self,
        name: str,
        build_dir: str,
        targets: Optional[List[str]] = None,
        jobs: int = 4,
        depends_on: Optional[List[str]] = None,
        timeout_seconds: int = 300,
    ) -> AsyncBuildStep:
        """Add a CMake build step."""
        cmake_path = self._find_cmake()
        cmd = [str(cmake_path), "--build", str(build_dir)]
        if targets:
            for target in targets:
                cmd.extend(["--target", target])
        cmd.extend(["--", f"-j{jobs}"])

        step = AsyncBuildStep(
            name=name,
            command=cmd,
            cwd=str(self.workspace_root),
            timeout_seconds=timeout_seconds,
            depends_on=depends_on,
        )
        self.add_step(step)
        return step

    def add_make_build(
        self,
        name: str,
        directory: str,
        jobs: int = 4,
        target: str = "all",
        make_path: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
        timeout_seconds: int = 300,
    ) -> AsyncBuildStep:
        """Add a Make build step."""
        make_cmd = make_path or self._find_make()
        cmd = [str(make_cmd), f"-j{jobs}"]
        if target:
            cmd.append(target)

        step = AsyncBuildStep(
            name=name,
            command=cmd,
            cwd=str(Path(directory).resolve()),
            timeout_seconds=timeout_seconds,
            depends_on=depends_on,
        )
        self.add_step(step)
        return step

    def add_shell_command(
        self,
        name: str,
        command: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        depends_on: Optional[List[str]] = None,
        timeout_seconds: int = 120,
    ) -> AsyncBuildStep:
        """Add a generic shell command step."""
        step = AsyncBuildStep(
            name=name,
            command=command,
            cwd=cwd,
            env=env,
            timeout_seconds=timeout_seconds,
            depends_on=depends_on,
        )
        self.add_step(step)
        return step

    async def run(self, max_parallel: int = 4) -> Dict[str, AsyncBuildResult]:
        """
        Execute all steps in dependency order with parallel execution.

        Args:
            max_parallel: Maximum number of steps to run in parallel.

        Returns:
            Dict mapping step name -> AsyncBuildResult.
        """
        results: Dict[str, AsyncBuildResult] = {}
        completed: set = set()

        # Topological sort with parallelism awareness
        pending = list(self.steps)

        while pending:
            # Find steps that are ready to run (all dependencies met)
            ready = [
                step for step in pending
                if all(dep in completed for dep in step.depends_on)
            ]

            if not ready:
                if pending:
                    # Circular dependency or unreachable step
                    logger.error("Build pipeline stalled: remaining steps have unmet dependencies")
                    for step in pending:
                        results[step.name] = AsyncBuildResult(
                            step=step.name,
                            status="failed",
                            stderr="Unmet dependencies: " + ", ".join(step.depends_on),
                        )
                    break
                break

            # Run up to max_parallel steps concurrently
            batch = ready[:max_parallel]
            tasks = [self._run_step(step) for step in batch]

            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for step, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    results[step.name] = AsyncBuildResult(
                        step=step.name,
                        status="failed",
                        stderr=str(result),
                    )
                else:
                    results[step.name] = result
                completed.add(step.name)
                pending.remove(step)

        # Mark any remaining steps as failed
        for step in pending:
            if step.name not in results:
                results[step.name] = AsyncBuildResult(
                    step=step.name,
                    status="failed",
                    stderr="Step not executed",
                )

        return results

    async def _run_step(self, step: AsyncBuildStep) -> AsyncBuildResult:
        """Execute a single build step asynchronously."""
        logger.info("Build: Running step '%s' - %s", step.name, " ".join(step.command))
        started = time.perf_counter()

        # Build environment
        env = dict(os.environ)
        if step.env:
            env.update(step.env)

        try:
            process = await asyncio.create_subprocess_exec(
                *step.command,
                cwd=step.cwd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=step.timeout_seconds,
                )
                stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
                stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                elapsed = time.perf_counter() - started
                logger.error("Build step '%s' timed out after %.1fs", step.name, elapsed)
                return AsyncBuildResult(
                    step=step.name,
                    status="timeout",
                    stdout="",
                    stderr=f"Step timed out after {step.timeout_seconds}s",
                    returncode=-1,
                    elapsed_seconds=elapsed,
                )

            elapsed = time.perf_counter() - started
            status = "success" if process.returncode == 0 else "failed"

            if status == "failed":
                logger.warning(
                    "Build step '%s' failed (exit %d) in %.1fs",
                    step.name,
                    process.returncode,
                    elapsed,
                )
            else:
                logger.info(
                    "Build step '%s' completed in %.1fs",
                    step.name,
                    elapsed,
                )

            return AsyncBuildResult(
                step=step.name,
                status=status,
                stdout=stdout,
                stderr=stderr,
                returncode=process.returncode,
                elapsed_seconds=elapsed,
            )

        except Exception as exc:
            elapsed = time.perf_counter() - started
            logger.exception("Build step '%s' raised exception", step.name)
            return AsyncBuildResult(
                step=step.name,
                status="failed",
                stderr=str(exc),
                returncode=-1,
                elapsed_seconds=elapsed,
            )

    def _find_cmake(self) -> Path:
        """Find the cmake executable."""
        # Check common locations
        candidates = [
            Path("cmake/build/cmake/bin/cmake.exe"),
            Path("cmake"),
            Path("Tools/cmake/bin/cmake.exe"),
            Path("Tools/cmake"),
            Path("cmake"),
        ]
        for candidate in candidates:
            resolved = self.workspace_root / candidate
            if resolved.exists():
                return resolved.resolve()
        # Fall back to PATH
        return Path("cmake")

    def _find_make(self) -> Path:
        """Find the make executable."""
        return Path("make")

    def print_results(self, results: Dict[str, AsyncBuildResult]):
        """Print build results to stdout."""
        print("\n" + "=" * 60)
        print("Async Build Pipeline Results")
        print("=" * 60)
        total = len(results)
        succeeded = sum(1 for r in results.values() if r.success)
        failed = total - succeeded

        for name, result in results.items():
            icon = "[OK]" if result.success else "[FAIL]"
            print(f"{icon} {name} ({result.elapsed_seconds:.1f}s)")
            if not result.success:
                if result.stderr:
                    for line in result.stderr.splitlines()[:5]:
                        print(f"     {line.strip()}")
        print("=" * 60)
        print(f"Total: {total} | Success: {succeeded} | Failed: {failed}")
        print("=" * 60)
