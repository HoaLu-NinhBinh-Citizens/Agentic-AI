"""Durable workflow event store interface and adapters.

This module defines the runtime-facing protocol expected by workflow components
(e.g. `EventOrdering`, `WorkflowContext`, `StrongQueryExecutor`).

The SQLite implementation is the single-node durable backend for lab-stable mode.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from .event_ordering import WorkflowEvent


class EventStore(Protocol):
    async def get_last_sequence(self, workflow_id: str) -> int: ...

    async def append_batch(self, events: list[WorkflowEvent]) -> None: ...

    async def get_event(self, workflow_id: str, sequence: int) -> WorkflowEvent | None: ...

    async def get_events_from(
        self, workflow_id: str, from_sequence: int, limit: int = 100
    ) -> list[WorkflowEvent]: ...

    async def get_committed_events(self, workflow_id: str) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class StoredWorkflowEvent:
    workflow_id: str
    sequence: int
    event_type: str
    event_data: dict[str, Any]
    created_at_ms: int


def _parse_workflow_event_payload(payload_json: str) -> tuple[str, dict[str, Any]]:
    payload = json.loads(payload_json)
    event_type = payload.get("event_type") or payload.get("type") or ""
    event_data = payload.get("event_data") or payload.get("data") or payload
    return str(event_type), dict(event_data)
