-- Session persistence schema for Phase 1B
-- Only session metadata is persisted; streaming state is never persisted.

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    workspace TEXT,
    state TEXT NOT NULL CHECK (state IN ('active', 'ended'))
);

-- Index for listing active sessions quickly
CREATE INDEX IF NOT EXISTS idx_sessions_state ON sessions(state);
