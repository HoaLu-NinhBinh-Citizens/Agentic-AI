"""Architecture tests to prevent code structure decay.

These tests verify that the codebase maintains proper separation of concerns
and dependency boundaries.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

import pytest


ROOT_DIR = Path(__file__).parent.parent.parent.parent / "src"


class DependencyCollector(ast.NodeVisitor):
    """AST visitor to collect import statements."""

    def __init__(self) -> None:
        self.imports: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self.imports.append(node.module)
        self.generic_visit(node)


def get_imports(file_path: Path) -> set[str]:
    """Get all imports from a Python file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))
        collector = DependencyCollector()
        collector.visit(tree)
        return set(collector.imports)
    except SyntaxError:
        return set()


def get_file_module(path: Path) -> str:
    """Get the module path for a file relative to src/."""
    rel = path.relative_to(ROOT_DIR)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    elif parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


class TestLayerBoundaries:
    """Tests for layer separation."""

    def test_domain_has_no_infrastructure_imports(self):
        """Domain layer should not import from infrastructure layer.

        Domain should be pure business logic without external dependencies.
        """
        domain_dir = ROOT_DIR / "domain"

        violations: list[tuple[Path, str]] = []
        for py_file in domain_dir.rglob("*.py"):
            imports = get_imports(py_file)
            for imp in imports:
                if imp.startswith("infrastructure."):
                    violations.append((py_file, imp))

        assert not violations, (
            f"Domain files should not import infrastructure:\n" +
            "\n".join(f"  {f.relative_to(ROOT_DIR)}: {imp}" for f, imp in violations)
        )

    def test_domain_has_no_interfaces_imports(self):
        """Domain layer should not import from interfaces layer.

        Domain is the innermost layer and should be independent.
        """
        domain_dir = ROOT_DIR / "domain"

        violations: list[tuple[Path, str]] = []
        for py_file in domain_dir.rglob("*.py"):
            imports = get_imports(py_file)
            for imp in imports:
                if imp.startswith("interfaces."):
                    violations.append((py_file, imp))

        assert not violations, (
            f"Domain files should not import interfaces:\n" +
            "\n".join(f"  {f.relative_to(ROOT_DIR)}: {imp}" for f, imp in violations)
        )

    def test_core_execution_has_no_websocket_imports(self):
        """Core execution should not import from interfaces.server.websocket.

        This would create a circular dependency and tight coupling.
        """
        exec_dir = ROOT_DIR / "core" / "execution"

        violations: list[tuple[Path, str]] = []
        for py_file in exec_dir.rglob("*.py"):
            imports = get_imports(py_file)
            for imp in imports:
                if "websocket" in imp.lower():
                    violations.append((py_file, imp))

        assert not violations, (
            f"Core execution should not import websocket:\n" +
            "\n".join(f"  {f.relative_to(ROOT_DIR)}: {imp}" for f, imp in violations)
        )

    def test_core_agent_has_no_websocket_imports(self):
        """Core agent should not import from interfaces.server.websocket.

        WebSocket is a transport concern, not a core concern.
        """
        agent_dir = ROOT_DIR / "core" / "agent"

        violations: list[tuple[Path, str]] = []
        for py_file in agent_dir.rglob("*.py"):
            imports = get_imports(py_file)
            for imp in imports:
                if "websocket" in imp.lower():
                    violations.append((py_file, imp))

        assert not violations, (
            f"Core agent should not import websocket:\n" +
            "\n".join(f"  {f.relative_to(ROOT_DIR)}: {imp}" for f, imp in violations)
        )

    def test_application_has_no_direct_domain_imports(self):
        """Application layer should import domain models."""
        pass


class TestToolExecutionComponents:
    """Tests for tool execution component structure."""

    def test_tool_call_has_state_enum(self):
        """ToolCallState enum must define all expected states."""
        from domain.models.tool_call import ToolCallState

        expected_states = {
            "PENDING", "RUNNING", "COMPLETED",
            "FAILED", "TIMED_OUT", "CANCELLED", "ORPHANED"
        }
        actual_states = {s.name for s in ToolCallState}

        assert expected_states == actual_states, (
            f"Missing states: {expected_states - actual_states}"
        )

    def test_tool_call_has_allowed_transitions(self):
        """ALLOWED_TRANSITIONS must be defined."""
        from domain.models.tool_call import ALLOWED_TRANSITIONS, ToolCallState

        assert ALLOWED_TRANSITIONS is not None
        assert ToolCallState.PENDING in ALLOWED_TRANSITIONS
        assert ToolCallState.RUNNING in ALLOWED_TRANSITIONS

    def test_tool_call_has_transition_validation(self):
        """validate_transition function must exist and work."""
        from domain.models.tool_call import (
            ToolCallState,
            validate_transition,
            InvalidStateTransitionError,
        )

        validate_transition(ToolCallState.PENDING, ToolCallState.RUNNING)

        with pytest.raises(InvalidStateTransitionError):
            validate_transition(ToolCallState.COMPLETED, ToolCallState.RUNNING)

    def test_execution_result_exists(self):
        """ToolExecutionResult dataclass must exist."""
        from domain.models.execution import ToolExecutionResult

        result = ToolExecutionResult(success=True, content=[{"type": "text", "text": "hi"}])
        assert result.success is True
        assert len(result.content) == 1

    def test_execution_context_exists(self):
        """ExecutionContext dataclass must exist."""
        from domain.models.execution import ExecutionContext

        ctx = ExecutionContext(session_id="s1", trace_id="t1")
        assert ctx.session_id == "s1"
        assert ctx.trace_id == "t1"

    def test_execution_result_factory_methods(self):
        """ToolExecutionResult should have factory methods."""
        from domain.models.execution import ToolExecutionResult

        success = ToolExecutionResult.success_result(content=[{"type": "text"}])
        assert success.success is True
        assert len(success.content) == 1

        error = ToolExecutionResult.error_result(
            error="failed",
            error_code="ERROR",
        )
        assert error.success is False
        assert error.error == "failed"


class TestNoCircularDependencies:
    """Tests for circular dependency detection."""

    def test_no_circular_domain_to_application(self):
        """Application should not circularly depend on domain."""
        app_dir = ROOT_DIR / "application"
        domain_dir = ROOT_DIR / "domain"

        app_imports_domain = False
        domain_imports_app = False

        for py_file in app_dir.rglob("*.py"):
            imports = get_imports(py_file)
            if any(i.startswith("domain.") for i in imports):
                app_imports_domain = True
                break

        for py_file in domain_dir.rglob("*.py"):
            imports = get_imports(py_file)
            if any(i.startswith("application.") for i in imports):
                domain_imports_app = True
                break

        assert not (app_imports_domain and domain_imports_app), (
            "Circular dependency detected between domain and application"
        )


class TestToolExecutionRuntime:
    """Tests for tool execution runtime integrity."""

    def test_tool_tracker_enforces_max_pending(self):
        """ToolTracker should enforce max_pending limit."""
        import asyncio
        from core.execution.tool_tracker import ToolTracker
        from domain.models.tool_call import ToolCallRecord, ToolCallState
        from shared.exceptions.tool_errors import ToolBusyError

        async def test():
            tracker = ToolTracker("test", max_pending=2)

            record1 = ToolCallRecord(
                call_id="c1",
                session_id="test",
                tool_name="t1",
                arguments={},
                state=ToolCallState.PENDING,
            )
            await tracker.add_pending(record1)

            record2 = ToolCallRecord(
                call_id="c2",
                session_id="test",
                tool_name="t2",
                arguments={},
                state=ToolCallState.PENDING,
            )
            await tracker.add_pending(record2)

            record3 = ToolCallRecord(
                call_id="c3",
                session_id="test",
                tool_name="t3",
                arguments={},
                state=ToolCallState.PENDING,
            )

            with pytest.raises(ToolBusyError):
                await tracker.add_pending(record3)

        asyncio.run(test())

    def test_state_transitions_are_validated(self):
        """Invalid state transitions should raise errors."""
        import asyncio
        from core.execution.tool_tracker import ToolTracker
        from domain.models.tool_call import (
            ToolCallRecord,
            ToolCallState,
            InvalidStateTransitionError,
        )

        async def test():
            tracker = ToolTracker("test")

            record = ToolCallRecord(
                call_id="c1",
                session_id="test",
                tool_name="t1",
                arguments={},
                state=ToolCallState.PENDING,
            )
            await tracker.add_pending(record)

            await tracker.update_state("c1", ToolCallState.RUNNING)

            with pytest.raises(InvalidStateTransitionError):
                await tracker.update_state("c1", ToolCallState.PENDING)

        asyncio.run(test())
