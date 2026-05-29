"""SQLite-backed event store and idempotency store for workflow runtime.

Implements append-only per-workflow streams with optimistic concurrency.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import aiosqlite


@dataclass(frozen=True)
class StoredEvent:
    workflow_id: str
    version: int
    schema_version: int
    event_type: str
    payload: dict[str, Any]
    payload_hash: str
    created_at_ms: int


class ConcurrencyError(RuntimeError):
    pass


class SQLiteEventStore:
    def __init__(self, db_path: str | Path, schema_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._schema_path = Path(schema_path)
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        schema = self._schema_path.read_text(encoding="utf-8")
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(schema)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    def _hash_payload(self, payload: dict[str, Any]) -> str:
        content = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(content.encode()).hexdigest()

    async def get_last_version(self, workflow_id: str) -> int:
        async with self._lock:
            if not self._conn:
                raise RuntimeError("Event store not initialized")

            cur = await self._conn.execute(
                "SELECT MAX(version) AS v FROM workflow_events WHERE workflow_id = ?",
                (workflow_id,),
            )
            row = await cur.fetchone()
            return int(row["v"] or 0)

    async def append(
        self,
        workflow_id: str,
        events: list[tuple[str, dict[str, Any]]],
        expected_version: int,
        schema_version: int = 1,
    ) -> int:
        """Append events atomically.

        Returns last committed version.
        """
        if not events:
            return expected_version

        now_ms = int(time.time() * 1000)

        async with self._lock:
            if not self._conn:
                raise RuntimeError("Event store not initialized")

            await self._conn.execute("BEGIN IMMEDIATE")
            try:
                cur = await self._conn.execute(
                    "SELECT MAX(version) AS v FROM workflow_events WHERE workflow_id = ?",
                    (workflow_id,),
                )
                row = await cur.fetchone()
                actual_version = int(row["v"] or 0)

                if actual_version != expected_version:
                    raise ConcurrencyError(
                        f"Version mismatch for {workflow_id}: expected {expected_version}, got {actual_version}"
                    )

                next_version = expected_version
                for event_type, payload in events:
                    next_version += 1
                    payload_hash = self._hash_payload(payload)
                    await self._conn.execute(
                        """
                        INSERT INTO workflow_events (
                          workflow_id, version, schema_version, event_type, payload_json, payload_hash, created_at_ms
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            workflow_id,
                            next_version,
                            schema_version,
                            event_type,
                            json.dumps(payload, separators=(",", ":"), sort_keys=True),
                            payload_hash,
                            now_ms,
                        ),
                    )

                await self._conn.execute(
                    "INSERT OR REPLACE INTO workflow_streams (workflow_id, status, updated_at_ms) VALUES (?, ?, ?)",
                    (workflow_id, "running", now_ms),
                )

                await self._conn.commit()
                return next_version
            except Exception:
                await self._conn.rollback()
                raise

    async def read(self, workflow_id: str, from_version: int = 1, limit: int = 10000) -> list[StoredEvent]:
        async with self._lock:
            if not self._conn:
                raise RuntimeError("Event store not initialized")

            cur = await self._conn.execute(
                """
                SELECT workflow_id, version, schema_version, event_type, payload_json, payload_hash, created_at_ms
                FROM workflow_events
                WHERE workflow_id = ? AND version >= ?
                ORDER BY version ASC
                LIMIT ?
                """,
                (workflow_id, from_version, limit),
            )
            rows = await cur.fetchall()

        events: list[StoredEvent] = []
        for r in rows:
            events.append(
                StoredEvent(
                    workflow_id=r["workflow_id"],
                    version=int(r["version"]),
                    schema_version=int(r["schema_version"]),
                    event_type=r["event_type"],
                    payload=json.loads(r["payload_json"]),
                    payload_hash=r["payload_hash"],
                    created_at_ms=int(r["created_at_ms"]),
                )
            )
        return events


class SQLiteIdempotencyStore:
    def __init__(self, conn_provider: SQLiteEventStore) -> None:
        self._provider = conn_provider

    def _hash_request(self, request: dict[str, Any]) -> str:
        content = json.dumps(request, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(content.encode()).hexdigest()

    async def get_or_reserve(
        self,
        *,
        key: str,
        workflow_id: str,
        activity_name: str,
        request: dict[str, Any],
    ) -> tuple[str, Optional[dict[str, Any]]]:
        """Reserve key for execution.

        Returns (status, response_json_or_none).
        """
        store = self._provider
        async with store._lock:
            if not store._conn:
                raise RuntimeError("Event store not initialized")

            now_ms = int(time.time() * 1000)
            req_hash = self._hash_request(request)

            cur = await store._conn.execute(
                "SELECT key, request_hash, status, response_json FROM idempotency_keys WHERE key = ?",
                (key,),
            )
            row = await cur.fetchone()

            if row is None:
                await store._conn.execute(
                    """
                    INSERT INTO idempotency_keys (key, workflow_id, activity_name, request_hash, status, response_json, created_at_ms, updated_at_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (key, workflow_id, activity_name, req_hash, "reserved", None, now_ms, now_ms),
                )
                await store._conn.commit()
                return "reserved", None

            if row["request_hash"] != req_hash:
                raise RuntimeError("Idempotency key reused with different request")

            status = row["status"]
            if status == "completed" and row["response_json"]:
                return "completed", json.loads(row["response_json"])

            return status, None

    async def complete(self, *, key: str, response: dict[str, Any]) -> None:
        store = self._provider
        async with store._lock:
            if not store._conn:
                raise RuntimeError("Event store not initialized")

            now_ms = int(time.time() * 1000)
            await store._conn.execute(
                "UPDATE idempotency_keys SET status = ?, response_json = ?, updated_at_ms = ? WHERE key = ?",
                ("completed", json.dumps(response, separators=(",", ":"), sort_keys=True), now_ms, key),
            )
            await store._conn.commit()

    async def fail(self, *, key: str) -> None:
        store = self._provider
        async with store._lock:
            if not store._conn:
                raise RuntimeError("Event store not initialized")

            now_ms = int(time.time() * 1000)
            await store._conn.execute(
                "UPDATE idempotency_keys SET status = ?, updated_at_ms = ? WHERE key = ?",
                ("failed", now_ms, key),
            )
            await store._conn.commit()
