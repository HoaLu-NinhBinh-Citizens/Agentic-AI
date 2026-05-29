"""Event store backend factory.

Provides a single place to choose the durable event store implementation
based on configuration.

Backends:
- sqlite (default): local single-node durable mode
- postgres: multi-instance substrate
"""

from __future__ import annotations

from src.core.config.config_loader import Config

from .sqlite_workflow_event_store import SQLiteWorkflowEventStore
from .postgres_workflow_event_store import PostgresWorkflowEventStore


def create_workflow_event_store(cfg: Config, *, sqlite_db_path: str) -> object:
    backend = str(cfg.get("workflow.store.backend") or "sqlite").strip().lower()
    if backend == "postgres":
        dsn = str(cfg.get("workflow.store.postgres.dsn") or "").strip()
        if not dsn:
            raise RuntimeError("workflow.store.postgres.dsn must be set when backend=postgres")
        return PostgresWorkflowEventStore(dsn=dsn)

    if backend != "sqlite":
        raise RuntimeError(f"Unsupported workflow.store.backend: {backend}")

    return SQLiteWorkflowEventStore(db_path=sqlite_db_path)
