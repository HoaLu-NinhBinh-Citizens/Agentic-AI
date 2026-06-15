"""Task planner application module."""

from typing import Any

from src.application.planner.decomposition import Decomposition
from src.application.planner.dependency_graph import DependencyGraph


class TaskPlanner:
    """Plans task decomposition and ordering."""

    def __init__(self) -> None:
        self._decomposition = Decomposition()

    async def plan(self, task: str) -> list[dict[str, Any]]:
        """Plan a free-form task into prioritized subtasks."""
        subtasks = await self._decomposition.decompose(task)
        return [
            {"description": st["description"], "priority": 5}
            for st in subtasks
        ]

    def plan_review(
        self,
        files: list[str],
        focus_areas: list[str],
        dependency_map: dict[str, list[str]] | None = None,
    ) -> list[dict[str, Any]]:
        """Produce review subtasks in dependency-respecting execution order.

        Decomposes the review into per-file subtasks, then orders them so a
        file's in-scope dependencies are reviewed before the file itself.
        Files with equal dependency standing keep their input order.

        Returns:
            The subtask dicts from :meth:`Decomposition.decompose_review`,
            reordered for execution.
        """
        subtasks = self._decomposition.decompose_review(
            files, focus_areas, dependency_map
        )
        by_id = {st["id"]: st for st in subtasks}

        graph = DependencyGraph()
        for st in subtasks:
            graph.add_task(st["id"], st["depends_on"])

        ordered_ids = graph.get_order()
        # get_order may surface referenced-but-out-of-scope deps; keep only
        # real subtasks, and append any subtask the ordering missed.
        ordered = [by_id[i] for i in ordered_ids if i in by_id]
        seen = {st["id"] for st in ordered}
        ordered.extend(st for st in subtasks if st["id"] not in seen)
        return ordered
