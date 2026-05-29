"""Postgres-backed workflow event store + idempotency store.

This is the multi-instance substrate replacement for `sqlite_event_store.py`.

Design goals:
- Durable append-only workflow streams (per-workflow total ordering)
- Optimistic concurrency via (workflow_id, version) uniqueness
- Idempotency key registry with request hash binding
- Async interface compatible with existing runtime adapters

NOTE: This module intentionally does *not* depend on wall clock for correctness.
Timestamps are stored as `created_at_ms` for observability only.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

import asyncpg


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


class PostgresEventStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def initialize(self) -> None:
        self._pool = await asyncpg.create_pool(dsn=self._dsn, min_size=1, max_size=10)
        async with self._pool.acquire() as conn:
            await conn.execute(_POSTGRES_SCHEMA_SQL)

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    def _hash_payload(self, payload: dict[str, Any]) -> str:
        content = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(content.encode()).hexdigest()

    async def get_last_version(self, workflow_id: str) -> int:
        if not self._pool:
            raise RuntimeError("Event store not initialized")

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COALESCE(MAX(version), 0) AS v FROM workflow_events WHERE workflow_id=$1",
                workflow_id,
            )
            return int(row["v"])

    async def append(
        self,
        workflow_id: str,
        events: list[tuple[str, dict[str, Any]]],
        expected_version: int,
        schema_version: int = 1,
    ) -> int:
        if not events:
            return expected_version

        if not self._pool:
            raise RuntimeError("Event store not initialized")

        now_ms = int(time.time() * 1000)

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT COALESCE(MAX(version), 0) AS v FROM workflow_events WHERE workflow_id=$1 FOR UPDATE",
                    workflow_id,
                )
                actual_version = int(row["v"])
                if actual_version != expected_version:
                    raise ConcurrencyError(
                        f"Version mismatch for {workflow_id}: expected {expected_version}, got {actual_version}"
                    )

                next_version = expected_version
                for event_type, payload in events:
                    next_version += 1
                    payload_hash = self._hash_payload(payload)
                    try:
                        await conn.execute(
                            """
                            INSERT INTO workflow_events
                              (workflow_id, version, schema_version, event_type, payload_json, payload_hash, created_at_ms)
                            VALUES ($1, $2, $3, $4, $5, $6, $7)
                            """,
                            workflow_id,
                            next_version,
                            schema_version,
                            event_type,
                            json.dumps(payload, separators=(",", ":"), sort_keys=True),
                            payload_hash,
                            now_ms,
                        )
                    except asyncpg.UniqueViolationError as e:
                        raise ConcurrencyError("Concurrent append detected") from e

                await conn.execute(
                    """
                    INSERT INTO workflow_streams (workflow_id, status, updated_at_ms)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (workflow_id) DO UPDATE SET status=EXCLUDED.status, updated_at_ms=EXCLUDED.updated_at_ms
                    """,
                    workflow_id,
                    "running",
                    now_ms,
                )

                return next_version

    async def read(self, workflow_id: str, from_version: int = 1, limit: int = 10000) -> list[StoredEvent]:
        if not self._pool:
            raise RuntimeError("Event store not initialized")

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT workflow_id, version, schema_version, event_type, payload_json, payload_hash, created_at_ms
                FROM workflow_events
                WHERE workflow_id=$1 AND version >= $2
                ORDER BY version ASC
                LIMIT $3
                """,
                workflow_id,
                from_version,
                limit,
            )

        out: list[StoredEvent] = []
        for r in rows:
            out.append(
                StoredEvent(
                    workflow_id=str(r["workflow_id"]),
                    version=int(r["version"]),
                    schema_version=int(r["schema_version"]),
                    event_type=str(r["event_type"]),
                    payload=json.loads(r["payload_json"]),
                    payload_hash=str(r["payload_hash"]),
                    created_at_ms=int(r["created_at_ms"]),
                )
            )
        return out


class PostgresIdempotencyStore:
    def __init__(self, conn_provider: PostgresEventStore) -> None:
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
    ) -> tuple[str, dict[str, Any] | None]:
        store = self._provider
        if not store._pool:
            raise RuntimeError("Event store not initialized")

        now_ms = int(time.time() * 1000)
        req_hash = self._hash_request(request)

        async with store._pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT key, request_hash, status, response_json FROM idempotency_keys WHERE key=$1 FOR UPDATE",
                    key,
                )

                if row is None:
                    await conn.execute(
                        """
                        INSERT INTO idempotency_keys
                          (key, workflow_id, activity_name, request_hash, status, response_json, created_at_ms, updated_at_ms)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                        """,
                        key,
                        workflow_id,
                        activity_name,
                        req_hash,
                        "reserved",
                        None,
                        now_ms,
                        now_ms,
                    )
                    return "reserved", None

                if str(row["request_hash"]) != req_hash:
                    raise RuntimeError("Idempotency key reused with different request")

                status = str(row["status"])
                if status == "completed" and row["response_json"]:
                    return "completed", json.loads(row["response_json"])

                return status, None

    async def complete(self, *, key: str, response: dict[str, Any]) -> None:
        store = self._provider
        if not store._pool:
            raise RuntimeError("Event store not initialized")

        now_ms = int(time.time() * 1000)

        async with store._pool.acquire() as conn:
            await conn.execute(
                "UPDATE idempotency_keys SET status=$1, response_json=$2, updated_at_ms=$3 WHERE key=$4",
                "completed",
                json.dumps(response, separators=(",", ":"), sort_keys=True),
                now_ms,
                key,
            )

    async def fail(self, *, key: str) -> None:
        store = self._provider
        if not store._pool:
            raise RuntimeError("Event store not initialized")

        now_ms = int(time.time() * 1000)

        async with store._pool.acquire() as conn:
            await conn.execute(
                "UPDATE idempotency_keys SET status=$1, updated_at_ms=$2 WHERE key=$3",
                "failed",
                now_ms,
                key,
            )


_POSTGRES_SCHEMA_SQL = r"""
CREATE TABLE IF NOT EXISTS workflow_events (
  workflow_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  schema_version INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  created_at_ms BIGINT NOT NULL,
  PRIMARY KEY (workflow_id, version)
);

CREATE INDEX IF NOT EXISTS idx_workflow_events_workflow
  ON workflow_events(workflow_id, version);

CREATE TABLE IF NOT EXISTS workflow_streams (
  workflow_id TEXT PRIMARY KEY,
  status TEXT,
  updated_at_ms BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
  key TEXT PRIMARY KEY,
  workflow_id TEXT NOT NULL,
  activity_name TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  status TEXT NOT NULL,
  response_json TEXT,
  created_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_idempotency_workflow
  ON idempotency_keys(workflow_id, activity_name);
"""
