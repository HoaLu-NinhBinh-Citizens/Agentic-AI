"""Unit tests for the planner wiring and the review agent loop."""

import asyncio
from dataclasses import dataclass

from src.application.planner.decomposition import Decomposition
from src.application.planner.dependency_graph import DependencyGraph
from src.application.planner.task_planner import TaskPlanner
from src.application.workflows.review_agent_loop import ReviewAgentLoop


# ─── Fakes ────────────────────────────────────────────────────────────────


@dataclass
class FakeFinding:
    rule_id: str
    file: str
    line: int = 1


class FakeReview:
    def __init__(self, findings):
        self.findings = findings


class FakeEngine:
    """Duck-typed UnifiedReviewEngine: returns canned findings per file."""

    def __init__(self, mapping):
        self._mapping = mapping
        self.calls = []

    async def review(self, paths, incremental=False):
        file = str(paths[0])
        self.calls.append(file)
        return FakeReview(list(self._mapping.get(file, [])))


class RaisingEngine:
    def __init__(self, bad_file):
        self._bad = bad_file
        self.calls = []

    async def review(self, paths, incremental=False):
        file = str(paths[0])
        self.calls.append(file)
        if file == self._bad:
            raise RuntimeError("boom")
        return FakeReview([FakeFinding("ML001", file)])


# ─── DependencyGraph topological order ──────────────────────────────────────


class TestDependencyGraphOrder:
    def test_dependencies_come_first(self):
        g = DependencyGraph()
        g.add_task("a", ["b"])
        g.add_task("b", ["c"])
        g.add_task("c", [])
        order = g.get_order()
        assert order.index("c") < order.index("b") < order.index("a")

    def test_no_dependencies_preserves_insertion_order(self):
        g = DependencyGraph()
        g.add_task("x", [])
        g.add_task("y", [])
        assert g.get_order() == ["x", "y"]

    def test_cycle_does_not_deadlock(self):
        g = DependencyGraph()
        g.add_task("a", ["b"])
        g.add_task("b", ["a"])
        order = g.get_order()
        assert set(order) == {"a", "b"}

    def test_referenced_but_unadded_dep_included_first(self):
        g = DependencyGraph()
        g.add_task("a", ["lib"])  # lib never added explicitly
        order = g.get_order()
        assert order.index("lib") < order.index("a")


# ─── Decomposition ──────────────────────────────────────────────────────────


class TestDecomposition:
    def test_decompose_review_one_subtask_per_file(self):
        d = Decomposition()
        subs = d.decompose_review(["a.py", "b.py"], ["ml"])
        assert [s["file"] for s in subs] == ["a.py", "b.py"]
        assert all(s["areas"] == ["ml"] for s in subs)

    def test_decompose_review_filters_out_of_scope_deps(self):
        d = Decomposition()
        subs = d.decompose_review(
            ["a.py", "b.py"],
            ["security"],
            dependency_map={"a.py": ["b.py", "external.py"]},
        )
        a = next(s for s in subs if s["file"] == "a.py")
        assert a["depends_on"] == ["b.py"]  # external.py dropped

    def test_priority_reflects_highest_area(self):
        d = Decomposition()
        subs = d.decompose_review(["a.py"], ["quality", "security"])
        assert subs[0]["priority"] == 100  # security outranks quality

    def test_decompose_splits_compound_task(self):
        d = Decomposition()
        subs = asyncio.run(d.decompose("review auth and fix the logger"))
        assert len(subs) == 2

    def test_decompose_simple_task_stays_single(self):
        d = Decomposition()
        subs = asyncio.run(d.decompose("review the auth module"))
        assert len(subs) == 1


# ─── TaskPlanner ────────────────────────────────────────────────────────────


class TestTaskPlanner:
    def test_plan_review_orders_dependencies_first(self):
        planner = TaskPlanner()
        plan = planner.plan_review(
            ["a.py", "b.py"],
            ["ml"],
            dependency_map={"a.py": ["b.py"]},
        )
        files = [s["file"] for s in plan]
        assert files.index("b.py") < files.index("a.py")

    def test_plan_review_includes_all_files(self):
        planner = TaskPlanner()
        plan = planner.plan_review(["a.py", "b.py", "c.py"], ["quality"])
        assert {s["file"] for s in plan} == {"a.py", "b.py", "c.py"}


# ─── ReviewAgentLoop ────────────────────────────────────────────────────────


class TestReviewAgentLoop:
    def test_aggregates_findings_in_dependency_order(self):
        engine = FakeEngine(
            {
                "a.py": [FakeFinding("ML001", "a.py")],
                "b.py": [FakeFinding("SEC001", "b.py")],
            }
        )
        loop = ReviewAgentLoop(engine)
        result = asyncio.run(
            loop.run(["a.py", "b.py"], ["ml", "security"], {"a.py": ["b.py"]})
        )
        assert engine.calls == ["b.py", "a.py"]  # dependency reviewed first
        assert result.total_findings == 2
        assert result.failed_subtasks == 0

    def test_deduplicates_findings_across_subtasks(self):
        dup = FakeFinding("ML001", "a.py", 5)
        engine = FakeEngine({"a.py": [dup, dup]})
        loop = ReviewAgentLoop(engine)
        result = asyncio.run(loop.run(["a.py"], ["ml"]))
        assert result.total_findings == 1

    def test_one_failed_subtask_does_not_abort_loop(self):
        engine = RaisingEngine(bad_file="a.py")
        loop = ReviewAgentLoop(engine)
        result = asyncio.run(loop.run(["a.py", "b.py"], ["ml"]))
        assert result.failed_subtasks == 1
        # b.py still reviewed and produced a finding
        assert result.total_findings == 1
        assert any(r.status == "error" and r.file == "a.py" for r in result.subtask_results)

    def test_clarifier_asked_when_no_focus_areas(self):
        engine = FakeEngine({"a.py": []})
        asked = []

        async def clarifier(question):
            asked.append(question)
            return "security"

        loop = ReviewAgentLoop(engine, clarifier=clarifier)
        result = asyncio.run(loop.run(["a.py"], focus_areas=None))
        assert asked  # the loop asked something
        assert result.plan[0]["areas"] == ["security"]

    def test_defaults_used_when_no_clarifier(self):
        engine = FakeEngine({"a.py": []})
        loop = ReviewAgentLoop(engine)  # no clarifier
        result = asyncio.run(loop.run(["a.py"], focus_areas=None))
        assert result.plan[0]["areas"] == ["security", "quality", "ml"]
