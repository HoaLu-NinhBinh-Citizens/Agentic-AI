"""SQLite-backed event store adapter for workflow runtime.

Bridges the generic SQLite append-only store to the workflow runtime's
`EventStore` protocol (sequence-based events).
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from .event_ordering import WorkflowEvent
from .sqlite_event_store import SQLiteEventStore


class SQLiteWorkflowEventStore:
    def __init__(self, *, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._schema_path = Path(__file__).with_name("sqlite_schema.sql")
        self._store = SQLiteEventStore(self._db_path, self._schema_path)
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        await self._store.initialize()

    async def close(self) -> None:
        await self._store.close()

    async def get_last_sequence(self, workflow_id: str) -> int:
        return await self._store.get_last_version(workflow_id)

    async def append_event(
        self,
        *,
        workflow_id: str,
        event_type: str,
        event_data: dict[str, Any],
        sequence: int,
    ) -> None:
        # sequence is treated as expected_version for strict ordering.
        expected = sequence - 1
        await self._store.append(
            workflow_id,
            [(event_type, {"event_type": event_type, "event_data": event_data})],
            expected_version=expected,
            schema_version=1,
        )

    async def append_batch(self, events: list[WorkflowEvent]) -> None:
        if not events:
            return

        # Group by workflow_id; append each stream with expected_version.
        by_workflow: dict[str, list[WorkflowEvent]] = {}
        for e in events:
            by_workflow.setdefault(e.workflow_id, []).append(e)

        for workflow_id, batch in by_workflow.items():
            batch_sorted = sorted(batch, key=lambda x: x.sequence)
            expected_version = batch_sorted[0].sequence - 1
            items: list[tuple[str, dict[str, Any]]] = []
            for e in batch_sorted:
                items.append(
                    (
                        e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
                        {
                            "event_type": e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
                            "event_data": e.event_data,
                            "created_at": e.created_at,
                            "sequence": e.sequence,
                        },
                    )
                )
            await self._store.append(
                workflow_id,
                items,
                expected_version=expected_version,
                schema_version=1,
            )

    async def get_event(self, workflow_id: str, sequence: int) -> Optional[WorkflowEvent]:
        events = await self.get_events_from(workflow_id, from_sequence=sequence, limit=1)
        return events[0] if events else None

    async def get_events_from(
        self,
        workflow_id: str,
        from_sequence: int,
        limit: int = 100,
    ) -> list[WorkflowEvent]:
        stored = await self._store.read(workflow_id, from_version=from_sequence, limit=limit)
        out: list[WorkflowEvent] = []
        for e in stored:
            payload = e.payload
            event_type = payload.get("event_type", e.event_type)
            event_data = payload.get("event_data", payload)
            out.append(
                WorkflowEvent(
                    event_id=f"{workflow_id}:{e.version}",
                    workflow_id=workflow_id,
                    event_type=event_type,
                    sequence=e.version,
                    event_data=event_data,
                    created_at=(e.created_at_ms / 1000.0),
                    is_committed=True,
                )
            )
        return out

    async def get_committed_events(self, workflow_id: str) -> list[dict[str, Any]]:
        events = await self._store.read(workflow_id, from_version=1, limit=100000)
        out: list[dict[str, Any]] = []
        for e in events:
            payload = e.payload
            event_type = payload.get("event_type", e.event_type)
            event_data = payload.get("event_data", payload)
            out.append({"event_type": event_type, "data": event_data, "sequence": e.version})
        return out
