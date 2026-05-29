-- SQLite schema for workflow event store + idempotency

PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS workflow_events (
  workflow_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  schema_version INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL,
  PRIMARY KEY (workflow_id, version)
);

CREATE INDEX IF NOT EXISTS idx_workflow_events_workflow
  ON workflow_events(workflow_id, version);

CREATE TABLE IF NOT EXISTS workflow_streams (
  workflow_id TEXT PRIMARY KEY,
  status TEXT,
  updated_at_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
  key TEXT PRIMARY KEY,
  workflow_id TEXT NOT NULL,
  activity_name TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  status TEXT NOT NULL,
  response_json TEXT,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_idempotency_workflow
  ON idempotency_keys(workflow_id, activity_name);
