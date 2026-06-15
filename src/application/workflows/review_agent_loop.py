"""Review agent loop — plan → (clarify) → execute → aggregate.

Wires the planner (task decomposition + dependency ordering) onto the
``UnifiedReviewEngine`` so a multi-file review runs as an ordered, resilient
agent loop instead of a single flat scan. This connects the previously
orphaned planner package into the review production path.

The engine is injected (duck-typed: ``async review(paths, incremental=False)``
returning an object with a ``.findings`` list) so the loop is testable without
running real detectors.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, Protocol

from src.application.planner.task_planner import TaskPlanner

logger = logging.getLogger(__name__)

_DEFAULT_FOCUS = ["security", "quality", "ml"]
_VALID_FOCUS = {"security", "quality", "ml", "embedded"}

# Async callable that asks the user a question and returns their answer (or
# None if they decline / there is no interactive frontend).
Clarifier = Callable[[str], Awaitable[Optional[str]]]


class _ReviewEngine(Protocol):
    async def review(self, paths: list[Path], incremental: bool = False) -> Any: ...


@dataclass
class SubtaskResult:
    """Outcome of reviewing a single file in the plan."""

    file: str
    status: str  # "ok" | "error"
    finding_count: int = 0
    error: Optional[str] = None


@dataclass
class AgentLoopResult:
    """Aggregate result of a planned review run."""

    plan: list[dict[str, Any]]
    subtask_results: list[SubtaskResult] = field(default_factory=list)
    findings: list[Any] = field(default_factory=list)
    clarifications: list[dict[str, str]] = field(default_factory=list)

    @property
    def total_findings(self) -> int:
        return len(self.findings)

    @property
    def failed_subtasks(self) -> int:
        return sum(1 for r in self.subtask_results if r.status == "error")


class ReviewAgentLoop:
    """Plans a review, optionally clarifies scope, then executes it in order."""

    def __init__(
        self,
        engine: _ReviewEngine,
        planner: TaskPlanner | None = None,
        clarifier: Clarifier | None = None,
    ) -> None:
        self._engine = engine
        self._planner = planner or TaskPlanner()
        self._clarifier = clarifier

    async def run(
        self,
        files: list[str],
        focus_areas: list[str] | None = None,
        dependency_map: dict[str, list[str]] | None = None,
    ) -> AgentLoopResult:
        """Execute the planned review loop.

        Args:
            files: Files to review.
            focus_areas: Detector areas; if empty/None and a clarifier is set,
                the user is asked which areas to use, else defaults apply.
            dependency_map: Optional {file: [imported_files]} for ordering.
        """
        clarifications: list[dict[str, str]] = []

        files, focus_areas = await self._clarify_scope(
            files, focus_areas, clarifications
        )

        plan = self._planner.plan_review(files, focus_areas, dependency_map)

        result = AgentLoopResult(plan=plan, clarifications=clarifications)
        if not plan:
            return result

        seen: set[tuple[str, str, int]] = set()
        for subtask in plan:
            file = subtask["file"]
            try:
                review = await self._engine.review([Path(file)], incremental=False)
                file_findings = list(getattr(review, "findings", []) or [])
                # Deduplicate across subtasks by (rule_id, file, line).
                new_findings = []
                for f in file_findings:
                    key = (
                        str(getattr(f, "rule_id", "")),
                        str(getattr(f, "file", file)),
                        int(getattr(f, "line", 0) or 0),
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    new_findings.append(f)
                result.findings.extend(new_findings)
                result.subtask_results.append(
                    SubtaskResult(
                        file=file, status="ok", finding_count=len(new_findings)
                    )
                )
            except Exception as exc:  # one bad file must not abort the loop
                logger.warning("Review subtask failed for %s: %s", file, exc)
                result.subtask_results.append(
                    SubtaskResult(file=file, status="error", error=str(exc))
                )

        return result

    async def _clarify_scope(
        self,
        files: list[str],
        focus_areas: list[str] | None,
        clarifications: list[dict[str, str]],
    ) -> tuple[list[str], list[str]]:
        """Resolve ambiguous scope, asking the user only when a clarifier exists."""
        focus_areas = [a for a in (focus_areas or []) if a in _VALID_FOCUS]

        if not files and self._clarifier is not None:
            question = "Which files should I review? (space- or comma-separated paths)"
            answer = await self._clarifier(question)
            clarifications.append({"question": question, "answer": answer or ""})
            if answer:
                files = [p for p in answer.replace(",", " ").split() if p]

        if not focus_areas and self._clarifier is not None:
            question = (
                "Which focus areas? Options: security, quality, ml, embedded "
                "(blank = all)."
            )
            answer = await self._clarifier(question)
            clarifications.append({"question": question, "answer": answer or ""})
            if answer:
                focus_areas = [
                    a.strip()
                    for a in answer.replace(",", " ").split()
                    if a.strip() in _VALID_FOCUS
                ]

        if not focus_areas:
            focus_areas = list(_DEFAULT_FOCUS)
        return files, focus_areas
