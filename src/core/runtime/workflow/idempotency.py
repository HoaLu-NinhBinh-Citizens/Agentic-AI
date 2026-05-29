"""Idempotent activity execution helpers.

Provides a small abstraction layer so workflow runtime can enforce idempotency
without depending on the enterprise coordination modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol


class IdempotencyStore(Protocol):
    async def get_or_reserve(
        self,
        *,
        key: str,
        workflow_id: str,
        activity_name: str,
        request: dict[str, Any],
    ) -> tuple[str, Optional[dict[str, Any]]]: ...

    async def complete(self, *, key: str, response: dict[str, Any]) -> None: ...

    async def fail(self, *, key: str) -> None: ...


@dataclass(frozen=True)
class IdempotencyDecision:
    should_execute: bool
    cached_response: Optional[dict[str, Any]]


async def decide_idempotency(
    *,
    store: IdempotencyStore,
    key: str,
    workflow_id: str,
    activity_name: str,
    request: dict[str, Any],
) -> IdempotencyDecision:
    status, response = await store.get_or_reserve(
        key=key,
        workflow_id=workflow_id,
        activity_name=activity_name,
        request=request,
    )

    if status == "completed":
        return IdempotencyDecision(should_execute=False, cached_response=response)

    # If reserved/failed/pending, execute again (at-least-once), but key reuse is guarded.
    return IdempotencyDecision(should_execute=True, cached_response=None)
