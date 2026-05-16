"""
Runtime Introspector - Live debugging for runtime

Practical debugging capabilities for production issues.

What you need NOW:
1. Live task graph - what's running, what's waiting
2. Queue states - depth, oldest item
3. Orphan detection - tasks that should have completed
4. Cancellation tree - who cancelled what
5. Event timeline - causality chain

Usage:
    inspector = RuntimeIntrospector()

    # Get snapshot
    snapshot = inspector.get_snapshot()
    print(inspector.format_snapshot(snapshot))

    # Check for orphans
    orphans = inspector.find_orphans()
    if orphans:
        print(f"WARNING: {len(orphans)} orphan tasks")

    # CLI command
    python -m src.core.runtime.introspector snapshot
"""

import asyncio
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TaskSnapshot:
    """Snapshot of a single task."""

    task_id: str
    name: str
    state: str  # "pending", "running", "done", "failed", "cancelled"
    created_at: float  # Unix timestamp
    started_at: float | None
    trace_id: str | None
    parent_id: str | None
    waiting_on: list[str] | None
    error: str | None

    @property
    def age_seconds(self) -> float:
        """Get task age in seconds."""
        return time.time() - self.created_at

    @property
    def is_orphan(self) -> bool:
        """Check if task is stuck (too old without completing)."""
        return self.state in ("pending", "running") and self.age_seconds > 300


@dataclass
class QueueSnapshot:
    """Snapshot of a queue."""

    name: str
    depth: int
    max_depth: int
    oldest_task_age: float | None
    items: list[dict]  # Task summaries


@dataclass
class WorkflowSnapshot:
    """Snapshot of a workflow."""

    workflow_id: str
    name: str
    state: str  # "active", "completed", "failed", "cancelled"
    started_at: float
    tasks: list[str]  # Task IDs
    error: str | None


@dataclass
class EventSnapshot:
    """Snapshot of a recent event."""

    event_id: str
    event_type: str
    timestamp: float
    source: str
    data: dict


@dataclass
class RuntimeSnapshot:
    """Full runtime snapshot."""

    timestamp: datetime
    uptime_seconds: float
    tasks: list[TaskSnapshot]
    queues: list[QueueSnapshot]
    workflows: list[WorkflowSnapshot]
    recent_events: list[EventSnapshot]
    orphan_tasks: list[str]
    system_stats: dict


class RuntimeIntrospector:
    """
    Live debugging for runtime.

    Provides practical debugging capabilities without over-engineering.

    Usage:
        inspector = RuntimeIntrospector()
        snapshot = inspector.get_snapshot()
        print(inspector.format_snapshot(snapshot))
    """

    def __init__(
        self,
        orphan_threshold_seconds: float = 300,
        max_events: int = 100,
    ):
        """
        Initialize introspector.

        Args:
            orphan_threshold_seconds: Task age before considered orphan
            max_events: Max recent events to capture
        """
        self._orphan_threshold = orphan_threshold_seconds
        self._max_events = max_events

        # Event history (simple in-memory)
        self._events: list[EventSnapshot] = []

        # Task registry for tracking
        self._task_registry: dict[str, TaskSnapshot] = {}

        # Workflow registry
        self._workflow_registry: dict[str, WorkflowSnapshot] = {}

        # Queue registry
        self._queue_registry: dict[str, QueueSnapshot] = {}

    def register_task(
        self,
        task_id: str,
        name: str,
        parent_id: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        """Register a task for tracking."""
        self._task_registry[task_id] = TaskSnapshot(
            task_id=task_id,
            name=name,
            state="pending",
            created_at=time.time(),
            started_at=None,
            trace_id=trace_id,
            parent_id=parent_id,
            waiting_on=None,
            error=None,
        )
        self._emit_event("task_registered", {"task_id": task_id, "name": name})

    def start_task(self, task_id: str) -> None:
        """Mark task as started."""
        task = self._task_registry.get(task_id)
        if task:
            task.state = "running"
            task.started_at = time.time()
            self._emit_event("task_started", {"task_id": task_id})

    def complete_task(self, task_id: str, error: str | None = None) -> None:
        """Mark task as completed."""
        task = self._task_registry.get(task_id)
        if task:
            task.state = "failed" if error else "done"
            task.error = error
            self._emit_event(
                "task_completed",
                {"task_id": task_id, "error": error},
            )

    def wait_on_task(self, task_id: str, waiting_for: list[str]) -> None:
        """Record that task is waiting on other tasks."""
        task = self._task_registry.get(task_id)
        if task:
            task.waiting_on = waiting_for

    def register_queue(self, name: str, depth: int, max_depth: int = 1000) -> None:
        """Register a queue for tracking."""
        self._queue_registry[name] = QueueSnapshot(
            name=name,
            depth=depth,
            max_depth=max_depth,
            oldest_task_age=None,
            items=[],
        )

    def update_queue(self, name: str, depth: int, items: list[dict] | None = None) -> None:
        """Update queue state."""
        queue = self._queue_registry.get(name)
        if queue:
            queue.depth = depth
            if items:
                queue.items = items[:10]  # Limit items
            # Calculate oldest age
            if items and "created_at" in items[0]:
                ages = [time.time() - item["created_at"] for item in items]
                queue.oldest_task_age = max(ages) if ages else None

    def register_workflow(self, workflow_id: str, name: str) -> None:
        """Register a workflow."""
        self._workflow_registry[workflow_id] = WorkflowSnapshot(
            workflow_id=workflow_id,
            name=name,
            state="active",
            started_at=time.time(),
            tasks=[],
            error=None,
        )
        self._emit_event("workflow_started", {"workflow_id": workflow_id, "name": name})

    def complete_workflow(
        self,
        workflow_id: str,
        state: str = "completed",
        error: str | None = None,
    ) -> None:
        """Mark workflow as completed."""
        workflow = self._workflow_registry.get(workflow_id)
        if workflow:
            workflow.state = state
            workflow.error = error
            self._emit_event(
                "workflow_completed",
                {"workflow_id": workflow_id, "state": state, "error": error},
            )

    def add_workflow_task(self, workflow_id: str, task_id: str) -> None:
        """Add task to workflow."""
        workflow = self._workflow_registry.get(workflow_id)
        if workflow and task_id not in workflow.tasks:
            workflow.tasks.append(task_id)

    def _emit_event(self, event_type: str, data: dict) -> None:
        """Emit an event for history."""
        event = EventSnapshot(
            event_id=f"{event_type}-{len(self._events)}",
            event_type=event_type,
            timestamp=time.time(),
            source="introspector",
            data=data,
        )
        self._events.append(event)
        # Trim history
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events :]

    def get_snapshot(self, start_time: float = 0) -> RuntimeSnapshot:
        """
        Get current runtime snapshot.

        Args:
            start_time: Runtime start timestamp for uptime calculation

        Returns:
            RuntimeSnapshot
        """
        # Collect asyncio tasks
        async_tasks = []
        for task in asyncio.all_tasks():
            if not task.done():
                async_tasks.append(task)

        # Build task list
        tasks = []
        for task_id, task in self._task_registry.items():
            tasks.append(task)

        # Find orphans
        orphans = [t.task_id for t in tasks if t.is_orphan]

        # System stats
        system_stats = {
            "python_version": sys.version.split()[0],
            "async_tasks": len(async_tasks),
            "tracked_tasks": len(self._task_registry),
            "active_tasks": len([t for t in tasks if t.state in ("pending", "running")]),
            "orphan_tasks": len(orphans),
            "workflows": len(self._workflow_registry),
            "queues": len(self._queue_registry),
        }

        return RuntimeSnapshot(
            timestamp=datetime.now(),
            uptime_seconds=time.time() - start_time if start_time else 0,
            tasks=tasks,
            queues=list(self._queue_registry.values()),
            workflows=list(self._workflow_registry.values()),
            recent_events=self._events[-50:],  # Last 50 events
            orphan_tasks=orphans,
            system_stats=system_stats,
        )

    def find_orphans(self) -> list[TaskSnapshot]:
        """Find tasks that have been stuck too long."""
        return [t for t in self._task_registry.values() if t.is_orphan]

    def get_task_chain(self, task_id: str) -> list[TaskSnapshot]:
        """Get task and all tasks it depends on."""
        chain = []
        visited = set()

        def collect(tid: str):
            if tid in visited:
                return
            visited.add(tid)
            task = self._task_registry.get(tid)
            if task:
                chain.append(task)
                if task.waiting_on:
                    for dep_id in task.waiting_on:
                        collect(dep_id)

        collect(task_id)
        return chain

    def format_snapshot(self, snapshot: RuntimeSnapshot) -> str:
        """
        Format snapshot as human-readable string.

        Returns multi-line snapshot report.
        """
        lines = [
            "=" * 60,
            f"RUNTIME SNAPSHOT - {snapshot.timestamp.isoformat()}",
            "=" * 60,
            "",
            "SYSTEM:",
            f"  Async Tasks:     {snapshot.system_stats['async_tasks']}",
            f"  Tracked Tasks:   {snapshot.system_stats['tracked_tasks']}",
            f"  Active Tasks:    {snapshot.system_stats['active_tasks']}",
            f"  Orphan Tasks:    {snapshot.system_stats['orphan_tasks']}",
            f"  Workflows:      {snapshot.system_stats['workflows']}",
            f"  Queues:         {snapshot.system_stats['queues']}",
            "",
        ]

        # Orphan warnings
        if snapshot.orphan_tasks:
            lines.append("⚠️  ORPHAN TASKS:")
            for task_id in snapshot.orphan_tasks[:5]:
                task = self._task_registry.get(task_id)
                if task:
                    lines.append(
                        f"  • {task.name} ({task.task_id}) - "
                        f"age: {task.age_seconds:.0f}s"
                    )
            if len(snapshot.orphan_tasks) > 5:
                lines.append(f"  ... and {len(snapshot.orphan_tasks) - 5} more")
            lines.append("")

        # Active tasks
        active = [t for t in snapshot.tasks if t.state in ("pending", "running")]
        if active:
            lines.append("ACTIVE TASKS:")
            for task in sorted(active, key=lambda t: t.created_at)[:20]:
                age = task.age_seconds
                waiting = f" → waiting: {', '.join(task.waiting_on)}" if task.waiting_on else ""
                lines.append(
                    f"  [{task.state:8}] {task.name} ({task.task_id}) "
                    f"age={age:.0f}s{waiting}"
                )
            lines.append("")

        # Queues
        if snapshot.queues:
            lines.append("QUEUES:")
            for queue in snapshot.queues:
                util = queue.depth / queue.max_depth if queue.max_depth else 0
                bar = "█" * int(util * 20) + "░" * (20 - int(util * 20))
                lines.append(
                    f"  {queue.name:15} [{bar}] {queue.depth}/{queue.max_depth}"
                )
            lines.append("")

        # Recent events
        if snapshot.recent_events:
            lines.append("RECENT EVENTS:")
            for event in snapshot.recent_events[-10:]:
                ts = datetime.fromtimestamp(event.timestamp).strftime("%H:%M:%S")
                lines.append(f"  {ts} {event.event_type}")
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)

    def format_task_tree(self, workflow_id: str | None = None) -> str:
        """Format task tree as ASCII tree."""
        lines = ["TASK TREE", "=" * 40]

        workflows = (
            [self._workflow_registry[workflow_id]]
            if workflow_id
            else self._workflow_registry.values()
        )

        for workflow in workflows:
            lines.append(f"\nWorkflow: {workflow.name} ({workflow.workflow_id})")
            lines.append(f"State: {workflow.state}")

            for task_id in workflow.tasks:
                self._format_task_line(task_id, 1, lines)

        return "\n".join(lines)

    def _format_task_line(
        self, task_id: str, depth: int, lines: list[str], prefix: str = ""
    ) -> None:
        """Format a single task line in tree."""
        task = self._task_registry.get(task_id)
        if not task:
            return

        state_icon = {"pending": "⏳", "running": "🔄", "done": "✅", "failed": "❌", "cancelled": "🚫"}.get(
            task.state, "?"
        )

        connector = "└── " if depth == 1 else "    "
        lines.append(f"{prefix}{connector}{state_icon} {task.name} ({task.task_id})")

        if task.waiting_on:
            for dep_id in task.waiting_on:
                self._format_task_line(dep_id, depth + 1, lines, prefix + "    ")


# Global introspector
_introspector: RuntimeIntrospector | None = None


def get_introspector() -> RuntimeIntrospector:
    """Get or create global introspector."""
    global _introspector
    if _introspector is None:
        _introspector = RuntimeIntrospector()
    return _introspector


# CLI entry point
async def main():
    """CLI for runtime introspection."""
    import argparse

    parser = argparse.ArgumentParser(description="Runtime Introspector")
    parser.add_argument("command", choices=["snapshot", "orphans", "tree"])
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    inspector = get_introspector()
    snapshot = inspector.get_snapshot()

    if args.command == "snapshot":
        if args.format == "text":
            print(inspector.format_snapshot(snapshot))
        else:
            import json

            print(
                json.dumps(
                    {
                        "timestamp": snapshot.timestamp.isoformat(),
                        "system": snapshot.system_stats,
                        "orphans": snapshot.orphan_tasks,
                    },
                    indent=2,
                )
            )

    elif args.command == "orphans":
        orphans = inspector.find_orphans()
        print(f"Found {len(orphans)} orphan tasks:")
        for task in orphans:
            print(f"  - {task.name} ({task.task_id}) age={task.age_seconds:.0f}s")

    elif args.command == "tree":
        print(inspector.format_task_tree())


if __name__ == "__main__":
    asyncio.run(main())
