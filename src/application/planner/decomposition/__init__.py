"""Task decomposition application module."""

from typing import Any

# Relative priority of review focus areas. Higher = reviewed earlier and
# surfaced first. Security and ML correctness issues tend to be the most
# costly, so they outrank style/quality.
AREA_PRIORITY: dict[str, int] = {
    "security": 100,
    "ml": 90,
    "embedded": 70,
    "quality": 50,
}
_DEFAULT_AREA_PRIORITY = 60


class Decomposition:
    """Decomposes complex tasks into ordered, dependency-aware subtasks."""

    async def decompose(self, task: str) -> list[dict[str, Any]]:
        """Decompose a free-form task into subtasks.

        Splits on common conjunctions so a compound request becomes several
        subtasks; a simple request stays a single subtask.
        """
        separators = [" and then ", " then ", "; ", " and ", ", "]
        parts = [task]
        for sep in separators:
            expanded: list[str] = []
            for part in parts:
                expanded.extend(p for p in part.split(sep) if p.strip())
            parts = expanded
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) <= 1:
            return [{"description": task, "subtasks": []}]
        return [{"description": p, "subtasks": []} for p in parts]

    def decompose_review(
        self,
        files: list[str],
        focus_areas: list[str],
        dependency_map: dict[str, list[str]] | None = None,
    ) -> list[dict[str, Any]]:
        """Decompose a code-review request into one subtask per file.

        Each subtask reviews a single file for the requested focus areas.
        Subtasks depend on the files they import (from ``dependency_map``)
        that are also in scope, so dependencies are reviewed first and
        cross-file context is established before dependents.

        Args:
            files: Source files to review.
            focus_areas: Detector areas to apply (e.g. security, ml, quality).
            dependency_map: Optional {file: [imported_files]} map. Edges to
                files outside ``files`` are ignored.

        Returns:
            One subtask dict per file with id, description, file, areas,
            priority, and depends_on (file ids in scope).
        """
        in_scope = list(dict.fromkeys(files))  # de-dupe, preserve order
        scope_set = set(in_scope)
        dependency_map = dependency_map or {}

        # Priority of a file = max priority across its applicable areas.
        area_score = max(
            (AREA_PRIORITY.get(a, _DEFAULT_AREA_PRIORITY) for a in focus_areas),
            default=_DEFAULT_AREA_PRIORITY,
        )

        subtasks: list[dict[str, Any]] = []
        for path in in_scope:
            depends_on = [
                dep for dep in dependency_map.get(path, []) if dep in scope_set and dep != path
            ]
            subtasks.append(
                {
                    "id": path,
                    "description": f"Review {path} for: {', '.join(focus_areas)}",
                    "file": path,
                    "areas": list(focus_areas),
                    "priority": area_score,
                    "depends_on": depends_on,
                }
            )
        return subtasks
