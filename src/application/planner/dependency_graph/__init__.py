"""Dependency graph application module."""

from typing import Any


class DependencyGraph:
    """Manages task dependencies and produces a valid execution order."""

    def __init__(self):
        self._graph: dict[str, list[str]] = {}

    def add_task(self, task_id: str, depends_on: list[str]) -> None:
        """Add task with dependencies."""
        self._graph[task_id] = list(depends_on)

    def get_order(self) -> list[str]:
        """Return tasks in dependency-respecting (topological) order.

        A task's dependencies are emitted before the task itself (Kahn's
        algorithm). Insertion order is preserved as a stable tie-break.
        Dependencies referenced but never added explicitly are treated as
        zero-dependency nodes. Cycles do not deadlock: once no further
        progress is possible, the remaining nodes are appended in insertion
        order so the caller still gets a complete, usable list.
        """
        deps: dict[str, list[str]] = {}
        for node, node_deps in self._graph.items():
            deps.setdefault(node, [])
            for dep in node_deps:
                deps[node].append(dep)
                deps.setdefault(dep, [])

        order_hint = list(deps.keys())
        resolved: list[str] = []
        resolved_set: set[str] = set()
        remaining = dict(deps)

        while remaining:
            progressed = False
            for node in order_hint:
                if node not in remaining:
                    continue
                if all(dep in resolved_set for dep in remaining[node]):
                    resolved.append(node)
                    resolved_set.add(node)
                    del remaining[node]
                    progressed = True
            if not progressed:
                # Cycle (or unsatisfiable dep): emit the rest in stable order
                # rather than spinning forever.
                for node in order_hint:
                    if node in remaining:
                        resolved.append(node)
                        del remaining[node]
                break

        return resolved
