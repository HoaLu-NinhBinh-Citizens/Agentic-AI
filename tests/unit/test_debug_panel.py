"""Unit tests for Debugger Panel and Test Runner."""
import pytest
import asyncio
from src.interfaces.tui.debug_panel import (
    Breakpoint, BreakpointType, DebugEvent, DebuggerPanel,
    DebugState, StackFrame, Variable, WatchExpression,
)
from src.interfaces.tui.test_runner import (
    TestCase, TestClass, TestRun, TestRunnerPanel, TestState,
)


# ─── Debugger Tests ───────────────────────────────────────────────────────────

class TestBreakpoint:
    def test_creation(self):
        bp = Breakpoint(id="bp-1", file_path="test.py", line=10)
        assert bp.enabled is True
        assert bp.hit_count == 0

    def test_matches_line(self):
        bp = Breakpoint(id="bp-1", file_path="test.py", line=10)
        assert bp.matches_line("test.py", 10)
        assert not bp.matches_line("test.py", 11)
        assert not bp.matches_line("other.py", 10)


class TestStackFrame:
    def test_creation(self):
        frame = StackFrame(id="frame-1", name="my_func", file_path="test.py", line=5)
        assert frame.name == "my_func"
        assert frame.locals == {}
        assert frame.args == {}


class TestVariable:
    def test_creation(self):
        v = Variable(name="x", value=42)
        assert v.name == "x"
        assert v.value == 42
        assert v.type == "int"

    def test_dict(self):
        v = Variable(name="s", value="hello")
        d = v.to_dict()
        assert d["name"] == "s"
        assert d["value"] == "'hello'"
        assert d["type"] == "str"


class TestWatchExpression:
    def test_creation(self):
        w = WatchExpression(id="w1", expression="x + y")
        assert w.expression == "x + y"
        assert w.enabled is True

    def test_error(self):
        w = WatchExpression(id="w1", expression="undefined", error="NameError")
        assert w.error == "NameError"


class TestDebuggerPanel:
    def setup_method(self):
        self.panel = DebuggerPanel()

    def test_initial_state(self):
        assert self.panel.state == DebugState.STOPPED
        assert not self.panel.is_running

    def test_add_breakpoint(self):
        bp = self.panel.add_breakpoint("test.py", 10)
        assert bp.file_path == "test.py"
        assert bp.line == 10
        assert len(self.panel._breakpoints) == 1

    def test_add_conditional_breakpoint(self):
        bp = self.panel.add_breakpoint("test.py", 10, condition="x > 5")
        assert bp.condition == "x > 5"

    def test_remove_breakpoint(self):
        bp = self.panel.add_breakpoint("test.py", 10)
        result = self.panel.remove_breakpoint(bp.id)
        assert result is True
        assert len(self.panel._breakpoints) == 0

    def test_remove_breakpoint_not_found(self):
        result = self.panel.remove_breakpoint("nonexistent")
        assert result is False

    def test_toggle_breakpoint(self):
        bp = self.panel.add_breakpoint("test.py", 10)
        assert bp.enabled is True
        self.panel.toggle_breakpoint(bp.id)
        assert bp.enabled is False
        self.panel.toggle_breakpoint(bp.id)
        assert bp.enabled is True

    def test_get_breakpoints(self):
        self.panel.add_breakpoint("test.py", 10)
        self.panel.add_breakpoint("test.py", 20)
        self.panel.add_breakpoint("other.py", 5)

        all_bp = self.panel.get_breakpoints()
        assert len(all_bp) == 3

        py_bp = self.panel.get_breakpoints("test.py")
        assert len(py_bp) == 2

    def test_add_watch(self):
        watch = self.panel.add_watch("len(items)")
        assert watch.expression == "len(items)"
        assert len(self.panel._watch) == 1

    def test_remove_watch(self):
        watch = self.panel.add_watch("x")
        self.panel.remove_watch(watch.id)
        assert len(self.panel._watch) == 0

    def test_evaluate_no_frames(self):
        result = self.panel.evaluate("1 + 1")
        assert result is None

    def test_evaluate_with_frame(self):
        frame = StackFrame(id="f1", name="test", file_path="test.py", line=1)
        frame.locals = {"x": 10, "y": 20}
        self.panel._frames = [frame]

        result = self.panel.evaluate("x + y")
        assert result == 30

    def test_evaluate_error(self):
        frame = StackFrame(id="f1", name="test", file_path="test.py", line=1)
        frame.locals = {}
        self.panel._frames = [frame]

        result = self.panel.evaluate("undefined_var")
        assert "Error" in str(result)

    def test_set_frame(self):
        f1 = StackFrame(id="f1", name="outer", file_path="a.py", line=1)
        f2 = StackFrame(id="f2", name="inner", file_path="b.py", line=5)
        self.panel._frames = [f1, f2]
        self.panel.set_frame("f2")
        assert self.panel._selected_frame == "f2"

    def test_stats(self):
        self.panel.add_breakpoint("test.py", 10)
        stats = self.panel.get_stats()
        assert stats["breakpoints_created"] == 1
        assert stats["breakpoints_total"] == 1


# ─── Test Runner Tests ───────────────────────────────────────────────────────

class TestTestCase:
    def test_creation(self):
        tc = TestCase(id="test-1", name="test_add")
        assert tc.state == TestState.QUEUED
        assert tc.display_name == "test_add"

    def test_class_name(self):
        tc = TestCase(id="test-1", name="test_add", class_name="TestMath")
        assert tc.display_name == "TestMath::test_add"

    def test_is_failure(self):
        tc = TestCase(id="t1", name="test", state=TestState.FAILED)
        assert tc.is_failure is True
        tc.state = TestState.PASSED
        assert tc.is_failure is False


class TestTestClass:
    def test_counts(self):
        tc = TestClass(name="TestMath")
        tc.tests = [
            TestCase(id="t1", name="a", state=TestState.PASSED),
            TestCase(id="t2", name="b", state=TestState.PASSED),
            TestCase(id="t3", name="c", state=TestState.FAILED),
            TestCase(id="t4", name="d", state=TestState.SKIPPED),
        ]
        assert tc.passed == 2
        assert tc.failed == 1
        assert tc.skipped == 1
        assert tc.total == 4


class TestTestRun:
    def test_creation(self):
        run = TestRun(id="run-1")
        assert run.total_tests == 0
        assert run.pass_rate == 0.0
        assert not run.is_complete

    def test_pass_rate(self):
        run = TestRun(id="run-1")
        run.total_tests = 10
        run.passed = 7
        run.failed = 3
        assert run.pass_rate == 0.7


class TestTestRunnerPanel:
    def setup_method(self):
        self.panel = TestRunnerPanel(pytest_path="pytest")

    def test_initial_state(self):
        assert self.panel._current_run is None
        assert self.panel._running_process is None

    def test_set_filter(self):
        self.panel.set_filter(TestState.FAILED)
        assert self.panel._filter == TestState.FAILED

    def test_clear_filter(self):
        self.panel.set_filter(TestState.FAILED)
        self.panel.set_filter(None)
        assert self.panel._filter is None

    def test_get_test_by_id_not_found(self):
        result = self.panel.get_test_by_id("nonexistent")
        assert result is None

    def test_stats(self):
        stats = self.panel.get_stats()
        assert "runs" in stats
        assert "total_tests_run" in stats

    def test_parse_discovered_tests_empty(self):
        result = self.panel._parse_discovered_tests("")
        assert result == []
