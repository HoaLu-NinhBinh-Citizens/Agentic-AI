"""Test Runner Panel — Cursor-like test panel.

Provides a visual test runner with:
- Test discovery (pytest, unittest)
- Run all / run selected
- Filter by status (passed, failed, skipped)
- Test output view
- Coverage display
- Re-run failed tests
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional


# ─── Test state ───────────────────────────────────────────────────────────────

class TestState(Enum):
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    QUEUED = "queued"


class TestOutcome(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"
    SKIP = "skip"


# ─── Data models ──────────────────────────────────────────────────────────────

@dataclass
class TestCase:
    """A single test case."""
    id: str
    name: str
    class_name: str = ""
    file_path: str = ""
    line: int = 0
    state: TestState = TestState.QUEUED
    duration_ms: int = 0
    message: str = ""
    traceback: str = ""
    output: str = ""
    stdout: str = ""
    stderr: str = ""

    @property
    def display_name(self) -> str:
        if self.class_name:
            return f"{self.class_name}::{self.name}"
        return self.name

    @property
    def is_failure(self) -> bool:
        return self.state in (TestState.FAILED, TestState.ERROR)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.display_name,
            "file": self.file_path,
            "line": self.line,
            "state": self.state.value,
            "duration": self.duration_ms,
            "message": self.message,
            "traceback": self.traceback,
        }


@dataclass
class TestClass:
    """A test class (or module for non-class tests)."""
    name: str
    file_path: str = ""
    tests: list[TestCase] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for t in self.tests if t.state == TestState.PASSED)

    @property
    def failed(self) -> int:
        return sum(1 for t in self.tests if t.state in (TestState.FAILED, TestState.ERROR))

    @property
    def skipped(self) -> int:
        return sum(1 for t in self.tests if t.state == TestState.SKIPPED)

    @property
    def total(self) -> int:
        return len(self.tests)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "file": self.file_path,
            "tests": [t.to_dict() for t in self.tests],
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "total": self.total,
        }


@dataclass
class TestRun:
    """A test run session."""
    id: str
    started_at: float = field(default_factory=time.time)
    completed_at: float = 0
    test_classes: list[TestClass] = field(default_factory=list)
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration_ms: int = 0

    @property
    def is_complete(self) -> bool:
        return self.completed_at > 0

    @property
    def pass_rate(self) -> float:
        if self.total_tests == 0:
            return 0.0
        return self.passed / self.total_tests

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "classes": [c.to_dict() for c in self.test_classes],
            "totalTests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "errors": self.errors,
            "durationMs": self.duration_ms,
            "passRate": self.pass_rate,
        }


# ─── Test Runner Panel ────────────────────────────────────────────────────────

class TestRunnerPanel:
    """Cursor-like test runner panel.

    Integrates with pytest for test execution.
    """

    def __init__(
        self,
        pytest_path: str = "pytest",
        root_dir: str = ".",
    ):
        self._pytest_path = pytest_path
        self._root_dir = Path(root_dir)
        self._current_run: Optional[TestRun] = None
        self._previous_runs: list[TestRun] = []
        self._callbacks: list[Callable[[dict], None]] = []
        self._running_process: Optional[asyncio.subprocess.Process] = None
        self._running_tests: dict[str, TestCase] = {}
        self._filter: Optional[TestState] = None
        self._stats = {
            "runs": 0,
            "total_tests_run": 0,
            "total_passed": 0,
            "total_failed": 0,
        }

    # ─── Discovery ───────────────────────────────────────────────────────────

    async def discover_tests(
        self,
        paths: Optional[list[str]] = None,
    ) -> list[TestClass]:
        """Discover all tests in the given paths."""
        if paths is None:
            paths = ["tests/"]

        cmd = [
            self._pytest_path,
            "--collect-only",
            "-q",
            "--no-header",
            "--tb=no",
        ]
        cmd.extend(paths)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._root_dir),
            )
            stdout, stderr = await proc.communicate()
            output = stdout.decode("utf-8", errors="replace")

            return self._parse_discovered_tests(output)
        except Exception as exc:
            return []

    def _parse_discovered_tests(self, output: str) -> list[TestClass]:
        """Parse pytest --collect-only output."""
        test_classes: dict[str, TestClass] = {}
        current_class: Optional[str] = None
        current_file: str = ""

        for line in output.split("\n"):
            line = line.strip()
            if not line or line.startswith("="):
                continue

            # Parse test line: "test_file.py::ClassName::test_name"
            if "::" in line:
                parts = line.split("::")
                if len(parts) >= 3:
                    file_path = parts[0]
                    class_name = parts[1]
                    test_name = parts[2]
                elif len(parts) == 2:
                    file_path = parts[0]
                    class_name = ""
                    test_name = parts[1]
                else:
                    continue

                class_key = f"{file_path}::{class_name}"
                if class_key not in test_classes:
                    test_classes[class_key] = TestClass(
                        name=class_name or file_path,
                        file_path=file_path,
                    )
                    current_file = file_path

                test_id = f"{class_key}::{test_name}"
                test = TestCase(
                    id=test_id,
                    name=test_name,
                    class_name=class_name,
                    file_path=file_path,
                )
                test_classes[class_key].tests.append(test)

        return list(test_classes.values())

    # ─── Execution ───────────────────────────────────────────────────────────

    async def run_tests(
        self,
        paths: Optional[list[str]] = None,
        test_ids: Optional[list[str]] = None,
        rerun_failed: bool = False,
    ) -> TestRun:
        """Run tests and return results."""
        self._stats["runs"] += 1
        start_time = time.time()

        run = TestRun(id=f"run-{self._stats['runs']}")
        self._current_run = run

        self._send_to_ide({
            "type": "test/run_started",
            "runId": run.id,
        })

        # Build command
        cmd = [
            self._pytest_path,
            "-v",
            "--tb=short",
            "--no-header",
        ]

        if rerun_failed and self._previous_runs:
            # Re-run only failed tests from last run
            last_run = self._previous_runs[-1]
            failed_ids = []
            for cls in last_run.test_classes:
                for test in cls.tests:
                    if test.is_failure:
                        failed_ids.append(f'"{test.id}"')
            if failed_ids:
                cmd.extend(["-k", " or ".join(failed_ids)])

        elif test_ids:
            cmd.extend(test_ids)

        elif paths:
            cmd.extend(paths)

        else:
            cmd.extend(["tests/"])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._root_dir),
            )
            self._running_process = proc

            stdout, stderr = await proc.communicate()
            output = stdout.decode("utf-8", errors="replace")
            err_output = stderr.decode("utf-8", errors="replace")

            # Parse results
            self._parse_test_output(output, run)

        except Exception as exc:
            run.completed_at = time.time()
            run.errors = 1

        run.completed_at = time.time()
        run.duration_ms = int((run.completed_at - start_time) * 1000)

        self._stats["total_tests_run"] += run.total_tests
        self._stats["total_passed"] += run.passed
        self._stats["total_failed"] += run.failed

        self._previous_runs.append(run)
        if len(self._previous_runs) > 10:
            self._previous_runs.pop(0)

        self._send_to_ide({
            "type": "test/run_completed",
            "run": run.to_dict(),
        })

        return run

    def _parse_test_output(self, output: str, run: TestRun) -> None:
        """Parse pytest verbose output."""
        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Parse PASSED, FAILED, SKIPPED, ERROR lines
            # Format: "PASSED test_file.py::Class::test_name"
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue

            status_str = parts[0]
            test_path = parts[1]

            # Map status
            if status_str == "PASSED":
                state = TestState.PASSED
            elif status_str == "FAILED":
                state = TestState.FAILED
            elif status_str == "SKIPPED":
                state = TestState.SKIPPED
            elif status_str == "ERROR":
                state = TestState.ERROR
            else:
                continue

            # Parse file::class::name
            test_parts = test_path.split("::")
            file_path = test_parts[0]
            class_name = test_parts[1] if len(test_parts) > 1 else ""
            test_name = test_parts[-1]

            # Find or create class
            class_key = f"{file_path}::{class_name}"
            test_class = next((c for c in run.test_classes if f"{c.file_path}::{c.name}" == class_key), None)
            if not test_class:
                test_class = TestClass(name=class_name or file_path, file_path=file_path)
                run.test_classes.append(test_class)

            # Create test case
            test = TestCase(
                id=test_path,
                name=test_name,
                class_name=class_name,
                file_path=file_path,
                state=state,
            )
            test_class.tests.append(test)
            run.total_tests += 1

            if state == TestState.PASSED:
                run.passed += 1
            elif state in (TestState.FAILED, TestState.ERROR):
                run.failed += 1
            else:
                run.skipped += 1

    async def stop(self) -> None:
        """Stop the running test process."""
        if self._running_process:
            self._running_process.terminate()
            try:
                await asyncio.wait_for(self._running_process.wait(), timeout=5)
            except asyncio.TimeoutExpired:
                self._running_process.kill()
            self._running_process = None

    # ─── Filtering ────────────────────────────────────────────────────────────

    def set_filter(self, state: Optional[TestState]) -> None:
        """Set the test filter."""
        self._filter = state

    def get_filtered_tests(self, run: TestRun) -> list[TestCase]:
        """Get tests filtered by the current filter."""
        tests = []
        for cls in run.test_classes:
            tests.extend(cls.tests)

        if self._filter:
            tests = [t for t in tests if t.state == self._filter]

        return tests

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def get_test_by_id(self, test_id: str) -> Optional[TestCase]:
        """Find a test case by ID."""
        if not self._current_run:
            return None

        for cls in self._current_run.test_classes:
            for test in cls.tests:
                if test.id == test_id:
                    return test
        return None

    # ─── IDE communication ────────────────────────────────────────────────────

    def on_message(self, callback: Callable[[dict], None]) -> None:
        self._callbacks.append(callback)

    def _send_to_ide(self, message: dict) -> None:
        for cb in self._callbacks:
            try:
                cb(message)
            except Exception:
                pass

    # ─── Stats ───────────────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "current_run": self._current_run.to_dict() if self._current_run else None,
            "previous_runs": len(self._previous_runs),
        }

    # ─── Render ───────────────────────────────────────────────────────────────

    def render_panel(self) -> str:
        """Render the test panel as a string."""
        if not self._current_run:
            return "┌─ Tests ───────────────────────────────┐\n│ No test run. Press F5 or Ctrl+T to run.  │\n└────────────────────────────────────────────┘"

        run = self._current_run
        lines = [
            "┌─ Test Results ──────────────────────────┐",
            f"│ {run.id}                              │",
            f"│ Tests: {run.total_tests:<5} │",
            f"│ Passed: {run.passed:<5} │",
            f"│ Failed: {run.failed:<5} │",
            f"│ Skipped: {run.skipped:<5} │",
            f"│ Duration: {run.duration_ms}ms",
            "├────────────────────────────────────────────┤",
        ]

        for cls in run.test_classes[:5]:
            status_icon = "✓" if cls.failed == 0 else "✗"
            line = f"│ {status_icon} {cls.name[:36]:<36}│"
            lines.append(line[:50].ljust(50) + "│")
            for test in cls.tests[:3]:
                icon = {"passed": "✓", "failed": "✗", "skipped": "⊘", "error": "✗"}.get(test.state.value, "?")
                name = test.name[:30]
                line = f"│   {icon} {name:<30}│"
                lines.append(line[:50].ljust(50) + "│")

        lines.append("└────────────────────────────────────────────┘")
        return "\n".join(lines)
