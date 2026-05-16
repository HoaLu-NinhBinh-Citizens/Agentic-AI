"""
Execution Tracker - DAG-based task dependency tracking

Provides visibility into workflow execution flow with:
1. Task dependency graph (DAG)
2. Execution ordering (topological sort)
3. Root cause analysis (backtrace from failures)
4. ASCII visualization

Usage:
    tracker = ExecutionTracker()

    # Create tasks with dependencies
    tracker.create_task("task1", "Build firmware")
    tracker.create_task("task2", "Run tests", depends_on=["task1"])
    tracker.create_task("task3", "Deploy", depends_on=["task2"])

    # Get execution order
    order = tracker.get_execution_order()
    print(f"Execute: {' -> '.join(order)}")

    # Root cause analysis
    if failed:
        cause = tracker.find_root_cause("task3")
        print(f"Failed because: {cause}")
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from collections import deque


class TaskState(Enum):
    """Task execution state."""
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


@dataclass
class TaskNode:
    """
    Node in the execution DAG.

    Represents a single task with its dependencies and state.
    """

    task_id: str
    name: str
    state: TaskState = TaskState.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    error: str | None = None

    # DAG edges
    depends_on: list[str] = field(default_factory=list)  # Parents (must complete first)
    dependents: list[str] = field(default_factory=list)  # Children (wait for this)

    # Metadata
    workflow_id: str | None = None
    priority: int = 0  # Higher = more important
    metadata: dict = field(default_factory=dict)

    @property
    def age_seconds(self) -> float:
        """Get task age in seconds."""
        return time.time() - self.created_at

    @property
    def duration_seconds(self) -> float | None:
        """Get task duration if completed."""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None

    @property
    def is_terminal(self) -> bool:
        """Check if task has no dependents."""
        return len(self.dependents) == 0

    @property
    def is_source(self) -> bool:
        """Check if task has no dependencies."""
        return len(self.depends_on) == 0

    def get_ready_dependents(self, completed: set[str]) -> list[str]:
        """Get dependents whose all dependencies are met."""
        ready = []
        for dep_id in self.dependents:
            if all(p in completed for p in self._get_all_dependencies(dep_id)):
                ready.append(dep_id)
        return ready

    def _get_all_dependencies(self, task_id: str) -> list[str]:
        """Recursively get all dependencies for a task."""
        node = self if task_id == self.task_id else None
        if not node:
            return []
        deps = list(node.depends_on)
        return deps


class ExecutionGraph:
    """
    Directed Acyclic Graph (DAG) for task execution tracking.

    Manages task dependencies and provides execution ordering.
    """

    def __init__(self, max_nodes: int = 10000):
        """
        Initialize execution graph.

        Args:
            max_nodes: Maximum number of nodes before cleanup
        """
        self._nodes: dict[str, TaskNode] = {}
        self._max_nodes = max_nodes
        self._workflows: dict[str, set[str]] = {}  # workflow_id -> set of task_ids

    def create_task(
        self,
        task_id: str,
        name: str,
        depends_on: list[str] | None = None,
        workflow_id: str | None = None,
        priority: int = 0,
        metadata: dict | None = None,
    ) -> TaskNode:
        """
        Create a new task node.

        Args:
            task_id: Unique task identifier
            name: Human-readable task name
            depends_on: List of task_ids this task depends on
            workflow_id: Optional workflow grouping
            priority: Task priority (higher = more important)
            metadata: Optional metadata dict

        Returns:
            Created TaskNode

        Raises:
            ValueError: If depends_on contains non-existent tasks
            ValueError: If would create a cycle
        """
        # Check for existing task
        if task_id in self._nodes:
            raise ValueError(f"Task already exists: {task_id}")

        # Validate dependencies
        depends_on = depends_on or []
        for dep_id in depends_on:
            if dep_id not in self._nodes:
                raise ValueError(f"Dependency not found: {dep_id}")

        # Check for cycles (would create circular dependency)
        if self._would_create_cycle(task_id, depends_on):
            raise ValueError(f"Would create cycle: {task_id} depends on {depends_on}")

        # Create node
        node = TaskNode(
            task_id=task_id,
            name=name,
            depends_on=depends_on,
            workflow_id=workflow_id,
            priority=priority,
            metadata=metadata or {},
        )
        self._nodes[task_id] = node

        # Update parent nodes' dependents
        for dep_id in depends_on:
            self._nodes[dep_id].dependents.append(task_id)

        # Track workflow
        if workflow_id:
            if workflow_id not in self._workflows:
                self._workflows[workflow_id] = set()
            self._workflows[workflow_id].add(task_id)

        # Cleanup if too many nodes
        self._maybe_cleanup()

        return node

    def get_task(self, task_id: str) -> TaskNode | None:
        """Get task node by ID."""
        return self._nodes.get(task_id)

    def get_workflow_tasks(self, workflow_id: str) -> list[TaskNode]:
        """Get all tasks for a workflow."""
        task_ids = self._workflows.get(workflow_id, set())
        return [self._nodes[tid] for tid in task_ids if tid in self._nodes]

    def update_state(
        self,
        task_id: str,
        state: TaskState,
        error: str | None = None,
    ) -> None:
        """Update task state."""
        node = self._nodes.get(task_id)
        if not node:
            return

        node.state = state
        node.error = error

        if state == TaskState.RUNNING and node.started_at is None:
            node.started_at = time.time()
        elif state in (TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED, TaskState.SKIPPED):
            node.completed_at = time.time()

    def get_execution_order(self, workflow_id: str | None = None) -> list[str]:
        """
        Get topological sort of tasks (execution order).

        Returns list of task_ids in order they should be executed.
        Handles parallel execution groups.
        """
        if workflow_id:
            task_ids = self._workflows.get(workflow_id, set())
            nodes = {tid: self._nodes[tid] for tid in task_ids if tid in self._nodes}
        else:
            nodes = dict(self._nodes)

        # Kahn's algorithm for topological sort
        in_degree = {tid: len(n.depends_on) for tid, n in nodes.items()}
        queue = deque([tid for tid, deg in in_degree.items() if deg == 0])
        result = []

        while queue:
            # Sort by priority for same-level tasks
            queue = deque(sorted(queue, key=lambda t: -nodes[t].priority))
            task_id = queue.popleft()
            result.append(task_id)

            # Reduce in-degree for dependents
            for dep_id in nodes[task_id].dependents:
                if dep_id in in_degree:
                    in_degree[dep_id] -= 1
                    if in_degree[dep_id] == 0:
                        queue.append(dep_id)

        return result

    def get_parallel_groups(self, workflow_id: str | None = None) -> list[list[str]]:
        """
        Get tasks grouped by execution level (parallel at same level).

        Returns list of groups, each group can run in parallel.
        """
        if workflow_id:
            task_ids = self._workflows.get(workflow_id, set())
            nodes = {tid: self._nodes[tid] for tid in task_ids if tid in self._nodes}
        else:
            nodes = dict(self._nodes)

        # Calculate levels using BFS from sources
        levels: dict[str, int] = {}
        queue = deque()

        # Initialize sources (no dependencies)
        for tid, node in nodes.items():
            if len(node.depends_on) == 0:
                levels[tid] = 0
                queue.append(tid)

        # BFS to calculate level of each node
        while queue:
            task_id = queue.popleft()
            for dep_id in nodes[task_id].dependents:
                if dep_id in nodes:
                    new_level = levels[task_id] + 1
                    if dep_id not in levels or levels[dep_id] < new_level:
                        levels[dep_id] = new_level
                        queue.append(dep_id)

        # Group by level
        groups: dict[int, list[str]] = {}
        for tid, level in levels.items():
            if level not in groups:
                groups[level] = []
            groups[level].append(tid)

        # Sort tasks within each group by priority
        result = []
        for level in sorted(groups.keys()):
            group = sorted(groups[level], key=lambda t: -nodes[t].priority)
            result.append(group)

        return result

    def find_root_cause(self, task_id: str) -> list[str]:
        """
        Trace back to find root cause of task failure.

        Returns list of task_ids from root to the failed task.
        """
        if task_id not in self._nodes:
            return []

        path = []
        current = task_id
        visited = set()

        while current:
            if current in visited:
                break
            visited.add(current)
            path.append(current)

            node = self._nodes.get(current)
            if not node:
                break

            # If this task failed, find which dependency caused it
            if node.state == TaskState.FAILED and node.error:
                # Find first failed dependency
                for dep_id in node.depends_on:
                    dep = self._nodes.get(dep_id)
                    if dep and dep.state == TaskState.FAILED:
                        current = dep_id
                        break
                else:
                    # No failed dependency found, this is the root cause
                    break
            elif node.depends_on:
                # Walk back to first dependency
                current = node.depends_on[0]
            else:
                break

        return list(reversed(path))

    def get_execution_frontier(self, completed: set[str]) -> list[str]:
        """
        Get tasks that are ready to execute.

        Args:
            completed: Set of completed task_ids

        Returns:
            List of task_ids ready to run (all dependencies met)
        """
        ready = []
        for task_id, node in self._nodes.items():
            if task_id in completed:
                continue
            if node.state != TaskState.PENDING:
                continue
            # Check all dependencies are completed
            if all(dep in completed for dep in node.depends_on):
                ready.append(task_id)

        # Sort by priority
        return sorted(ready, key=lambda t: -self._nodes[t].priority)

    def detect_cycles(self) -> list[list[str]]:
        """
        Detect cycles in the graph.

        Returns:
            List of cycles (each cycle is a list of task_ids)
        """
        cycles = []
        visited = set()
        rec_stack = set()

        def dfs(task_id: str, path: list[str]) -> None:
            visited.add(task_id)
            rec_stack.add(task_id)
            path.append(task_id)

            node = self._nodes.get(task_id)
            if node:
                for dep_id in node.dependents:
                    if dep_id not in visited:
                        dfs(dep_id, path.copy())
                    elif dep_id in rec_stack:
                        # Found cycle
                        cycle_start = path.index(dep_id)
                        cycle = path[cycle_start:] + [dep_id]
                        cycles.append(cycle)

            rec_stack.remove(task_id)

        for task_id in self._nodes:
            if task_id not in visited:
                dfs(task_id, [])

        return cycles

    def _would_create_cycle(self, task_id: str, depends_on: list[str]) -> bool:
        """Check if adding dependencies would create a cycle."""
        # Simple check: if task_id is in depends_on chain
        checked = set()
        for dep_id in depends_on:
            to_check = [dep_id]
            while to_check:
                current = to_check.pop()
                if current == task_id:
                    return True
                if current in checked:
                    continue
                checked.add(current)
                node = self._nodes.get(current)
                if node:
                    to_check.extend(node.depends_on)
        return False

    def _maybe_cleanup(self) -> None:
        """Remove old completed tasks if too many."""
        if len(self._nodes) <= self._max_nodes:
            return

        # Remove completed tasks older than 1 hour
        cutoff = time.time() - 3600
        to_remove = [
            tid for tid, node in self._nodes.items()
            if node.state in (TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED, TaskState.SKIPPED)
            and node.completed_at and node.completed_at < cutoff
        ]

        for tid in to_remove[:100]:  # Remove 100 at a time
            self._remove_task(tid)

    def _remove_task(self, task_id: str) -> None:
        """Remove a task and clean up references."""
        node = self._nodes.pop(task_id, None)
        if not node:
            return

        # Remove from parent's dependents
        for dep_id in node.depends_on:
            parent = self._nodes.get(dep_id)
            if parent and task_id in parent.dependents:
                parent.dependents.remove(task_id)

        # Remove from workflow
        if node.workflow_id and node.workflow_id in self._workflows:
            self._workflows[node.workflow_id].discard(task_id)

    def get_stats(self) -> dict[str, Any]:
        """Get graph statistics."""
        state_counts = {}
        for node in self._nodes.values():
            state_counts[node.state.value] = state_counts.get(node.state.value, 0) + 1

        return {
            "total_tasks": len(self._nodes),
            "state_counts": state_counts,
            "workflows": len(self._workflows),
            "pending": state_counts.get("pending", 0),
            "running": state_counts.get("running", 0),
            "completed": state_counts.get("done", 0),
            "failed": state_counts.get("failed", 0),
        }


class ExecutionTracker:
    """
    High-level execution tracking with DAG visualization.

    Combines ExecutionGraph with practical debugging features.
    """

    def __init__(self, max_nodes: int = 10000):
        """
        Initialize execution tracker.

        Args:
            max_nodes: Maximum tracked tasks before cleanup
        """
        self._graph = ExecutionGraph(max_nodes=max_nodes)
        self._start_time = time.time()

    def create_task(
        self,
        task_id: str,
        name: str,
        depends_on: list[str] | None = None,
        workflow_id: str | None = None,
        priority: int = 0,
        metadata: dict | None = None,
    ) -> TaskNode:
        """Create and register a task."""
        return self._graph.create_task(
            task_id=task_id,
            name=name,
            depends_on=depends_on,
            workflow_id=workflow_id,
            priority=priority,
            metadata=metadata,
        )

    def start(self, task_id: str) -> None:
        """Mark task as started."""
        self._graph.update_state(task_id, TaskState.RUNNING)

    def complete(self, task_id: str, success: bool = True, error: str | None = None) -> None:
        """Mark task as completed."""
        state = TaskState.DONE if success else TaskState.FAILED
        self._graph.update_state(task_id, state, error)

    def skip(self, task_id: str) -> None:
        """Mark task as skipped."""
        self._graph.update_state(task_id, TaskState.SKIPPED)

    def cancel(self, task_id: str) -> None:
        """Mark task as cancelled."""
        self._graph.update_state(task_id, TaskState.CANCELLED)

    def get_execution_order(self, workflow_id: str | None = None) -> list[str]:
        """Get tasks in execution order."""
        return self._graph.get_execution_order(workflow_id)

    def get_parallel_groups(self, workflow_id: str | None = None) -> list[list[str]]:
        """Get tasks grouped by parallel execution level."""
        return self._graph.get_parallel_groups(workflow_id)

    def find_root_cause(self, task_id: str) -> list[str]:
        """Find root cause of task failure."""
        return self._graph.find_root_cause(task_id)

    def get_ready_tasks(self, completed: set[str]) -> list[str]:
        """Get tasks ready to execute."""
        return self._graph.get_execution_frontier(completed)

    def format_dag(self, workflow_id: str | None = None) -> str:
        """
        Format DAG as ASCII visualization.

        Shows task dependencies in a tree-like format.
        """
        if workflow_id:
            tasks = self._graph.get_workflow_tasks(workflow_id)
        else:
            tasks = list(self._graph._nodes.values())

        if not tasks:
            return "No tasks in graph"

        lines = ["EXECUTION DAG", "=" * 50]

        # Group by state
        by_state: dict[TaskState, list[TaskNode]] = {}
        for task in tasks:
            by_state.setdefault(task.state, []).append(task)

        # Show by state
        for state in [TaskState.RUNNING, TaskState.PENDING, TaskState.FAILED, TaskState.DONE]:
            if state in by_state:
                lines.append(f"\n{state.value.upper()}:")
                for task in by_state[state]:
                    deps = f" <- [{', '.join(task.depends_on)}]" if task.depends_on else ""
                    err = f" [{task.error}]" if task.error else ""
                    lines.append(f"  * {task.name} ({task.task_id}){deps}{err}")

        return "\n".join(lines)

    def format_execution_plan(self, workflow_id: str | None = None) -> str:
        """
        Format execution plan with parallel groups.

        Shows recommended execution order with parallel grouping.
        """
        groups = self.get_parallel_groups(workflow_id)

        if not groups:
            return "No tasks to execute"

        lines = ["EXECUTION PLAN", "=" * 50]

        for i, group in enumerate(groups):
            if len(group) == 1:
                lines.append(f"\nStep {i + 1}: {self._graph.get_task(group[0]).name}")
            else:
                lines.append(f"\nStep {i + 1} (parallel):")
                for task_id in group:
                    task = self._graph.get_task(task_id)
                    lines.append(f"  ├─ {task.name}")

        return "\n".join(lines)

    def format_root_cause(self, task_id: str) -> str:
        """Format root cause analysis for a failed task."""
        path = self.find_root_cause(task_id)

        if not path:
            return f"Task not found: {task_id}"

        lines = ["ROOT CAUSE ANALYSIS", "=" * 50]
        lines.append(f"Tracing: {task_id}")

        for i, tid in enumerate(path):
            node = self._graph.get_task(tid)
            if not node:
                continue

            arrow = "    " if i == len(path) - 1 else "|-- "
            state_icon = {
                TaskState.FAILED: "[X]",
                TaskState.DONE: "[OK]",
                TaskState.PENDING: "[..]",
                TaskState.RUNNING: "[>>",
            }.get(node.state, "[?]")

            error_info = f" - {node.error}" if node.error else ""
            lines.append(f"  {arrow}{state_icon} {node.name} ({tid}){error_info}")

        return "\n".join(lines)

    def get_stats(self) -> dict[str, Any]:
        """Get execution statistics."""
        return self._graph.get_stats()

    def detect_cycles(self) -> list[list[str]]:
        """Detect cycles in the graph."""
        return self._graph.detect_cycles()


# Global tracker
_tracker: ExecutionTracker | None = None


def get_tracker() -> ExecutionTracker:
    """Get or create global tracker."""
    global _tracker
    if _tracker is None:
        _tracker = ExecutionTracker()
    return _tracker
