# PR-001 Scope Definition

> **Document type**: Read-only planning — no code was modified.
> **Date**: 2026-06-13

---

## Affected Components

### Likely Modified Files

| File | Change | Lines Affected |
|------|--------|---------------|
| `src/core/runtime/runtime_manager.py` | C1: Change `STREAM_TIMEOUT_SEC` from 30.0 to env-var-configurable 300. Add `import os`. | Line 22 (constant), line 1-8 (imports) |
| `src/interfaces/server/main.py` | C2: CORS allowlist. C3: Path validation for `/api/fs/read` and `/api/fs/dir`. C4: Workspace root extraction to `app.state`. | Lines 214-220 (CORS), 284-305 (read_file), 308-339 (read_directory), 163-176 (lifespan workspace) |

### Likely Created Files

| File | Purpose |
|------|---------|
| `tests/test_path_validation.py` | Unit tests for path traversal, symlink escape, edge cases (T-02-U01, T-02-U02) |
| `tests/test_server_hardening.py` | Integration tests for CORS enforcement, timeout config, session TTL (T-02-U03, T-02-U04, T-02-U05, T-02-I01 through I04) |

### Possibly Modified Files

| File | Condition |
|------|-----------|
| `src/core/session/persistent_manager.py` | Only if the non-cachetools fallback path lacks TTL refresh-on-access |

### Files That MUST NOT Be Touched

- **All files outside the 2 target files** (except test files)
- `src/interfaces/server/websocket/` — WebSocket handler logic (protocol frozen)
- `src/core/agent/real_agent.py` — agent logic
- `src/infrastructure/` — all infrastructure modules
- `src/domain/` — all domain modules
- `src/application/` — all application modules
- `pyproject.toml` — no dependency changes
- `configs/` — no config file changes
- Frontend/Electron files (`src/AgenticAI/`)
- Any `__init__.py` files

---

## Change Boundary

### Allowed

| Category | Scope |
|----------|-------|
| CORS configuration | Change `allow_origins` from `["*"]` to explicit list with env var override |
| Stream timeout | Change `STREAM_TIMEOUT_SEC` constant to env-var-configurable value >= 120 |
| File API validation | Add `Path.resolve()` + `is_relative_to()` check in `read_file()` and `read_directory()` |
| Workspace root | Extract workspace root resolution from indexing block to `app.state` in `lifespan()` |
| Session TTL | Verify and document refresh-on-access behavior; fix fallback path if needed |
| Error responses | Add 403 response for invalid paths (additive error code per architecture freeze) |
| Environment variables | Add `STREAM_TIMEOUT_SEC`, `AI_SUPPORT_CORS_ORIGINS` env vars (additive, with sensible defaults) |
| Tests | Add unit tests for path validation, integration tests for CORS/timeout/session |

### Forbidden

| Category | Reason |
|----------|--------|
| REST endpoint rename/removal | Architecture freeze §1.1 |
| WebSocket protocol change | Architecture freeze §1.2 |
| New REST endpoints | Out of PR-001 scope |
| Rate limiting changes | Not part of T-02 |
| Authentication/authorization | Not part of T-02 |
| Health probe implementation | Part of T-01 (dead code — stubs will be deleted) |
| Session management redesign | Scope creep |
| File API response format change | Architecture freeze — valid paths must return same format |
| Dependency additions | Not needed for config changes |
| Frontend/Electron changes | Server-only PR |
| Formatting-only changes | No opportunistic cleanup |
| Import convention changes | Part of T-04 / PR-009 |

### Out of Scope (Must Wait for Another PR)

| Item | Target PR |
|------|-----------|
| Dead code deletion | PR-002 |
| Orchestration consolidation | PR-003 |
| FTS5 indexing | PR-005 |
| HTTP client consolidation | PR-010 |
| Dynamic per-provider timeout | Future enhancement (not in any planned PR) |
| `/api/fs/dir` path validation | **In scope** — same security vulnerability as `/api/fs/read` |

**Note**: `/api/fs/dir` (lines 308-339) has the same unrestricted path access as `/api/fs/read`. Both must be hardened in this PR. This was not explicitly called out in some planning documents but is clearly within the T-02/T-06 security scope.

---

## Modules / Packages / Services Classification

| Component | Classification | Justification |
|-----------|---------------|---------------|
| `interfaces.server` | **Likely affected** | CORS config + file API handler |
| `core.runtime` | **Likely affected** | Stream timeout constant |
| `core.session` | **Possibly affected** | TTL verification only |
| `core.agent` | Must NOT touch | Agent logic unchanged |
| `core.orchestration` | Must NOT touch | Orchestration unchanged |
| `application.*` | Must NOT touch | Application layer unchanged |
| `infrastructure.*` | Must NOT touch | Infrastructure unchanged |
| `domain.*` | Must NOT touch | Domain unchanged |
| `interfaces.tui` | Must NOT touch | TUI unchanged |

---

## API Impact

| API | Impact | Detail |
|-----|--------|--------|
| `GET /api/fs/read` | Additive 403 | Out-of-workspace paths now return 403. Valid workspace paths unchanged. |
| `GET /api/fs/dir` | Additive 403 | Same as above. |
| `GET /health` | None | Unchanged. |
| `GET /sessions` | None | Unchanged. |
| `POST /sessions` | None | Unchanged. |
| `DELETE /sessions/{id}` | None | Unchanged. |
| `GET /api/ai/config/status` | None | Unchanged. |
| `GET /api/score` | None | Unchanged. |
| `WS /ws/{session_id}` | Behavior change | Streams run longer before server-side kill (300s vs 30s). Protocol unchanged. |
| CORS headers | Restrictive change | `Access-Control-Allow-Origin` no longer `*`. |

---

## Storage Impact

None. No schema changes. No data migration. No new tables.

---

## Cache Impact

- Session cache TTL: behavior verified, not changed (already correct with `TTLCache`)
- No other cache affected
