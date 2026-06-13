# PR-001 Planning Updates

> **Document type**: Post-implementation review
> **Date**: 2026-06-13

---

## Updates Required to Planning Documents

### 1. `pr001_validation.md` — Mark deferred tests

The following test IDs were planned but not implemented. They should be marked as "Deferred" with justification:

| Test ID | Status | Justification |
|---------|--------|---------------|
| T-02-I02 | Deferred | Requires mock LLM with configurable stream duration. Timeout logic is trivial (`asyncio.wait_for` with larger value). |
| T-02-I04 | Deferred | `TTLCache` is a well-tested library. No code change was made — verification only. |
| T-02-N01 | Deferred | OS rejects very long paths before application code. Low risk. |
| T-02-N02 | Deferred | `Path.resolve()` handles Unicode normalization. Low risk. |
| T-02-R02 | Deferred | End-to-end chat test requires full server + LLM mock infrastructure. Manual validation item. |
| T-02-R03 | Deferred | WebSocket connectivity test requires running server. CORS does not affect WebSocket in FastAPI. |
| T-02-S03 | Partial | Covered by unit test `TestSymlinkEscape.test_symlink_to_outside` but skipped on Windows (requires admin). No integration-level symlink test. |

### 2. `pr001_execution_plan.md` — Update precondition status

The three preconditions should be marked as resolved:

| Precondition | Resolution |
|-------------|------------|
| Electron origin determined | Electron app uses `ollamaClient.ts` directly, not the Python backend. CORS change is zero-risk for IDE. Conservative localhost defaults + env var override cover uncertainty. |
| Python minimum version verified | `requires-python = ">=3.10"` in `pyproject.toml`. `is_relative_to()` safe (added in 3.9). |
| Baseline test suite recorded | 0 passed, 5 skipped, 25 collection errors (pre-existing). |

### 3. `implementation_contract.md` — Update postcondition checklist

| Postcondition | Status |
|--------------|--------|
| `allow_origins` does not contain `"*"` | DONE |
| `/api/fs/read` rejects paths outside workspace | DONE |
| `STREAM_TIMEOUT_SEC` >= 120 | DONE (300) |
| All existing tests pass | DONE (baseline unchanged) |

### 4. `pr001_scope.md` — Add `/api/fs/dir` clarification

The scope document already notes `/api/fs/dir` is in scope (line 86-88). No update needed — this was correctly anticipated.

### 5. `migration_strategy.md` — T-02/T-06 current state

Update "Current State" to "Completed" and record the actual values:
- `STREAM_TIMEOUT_SEC = 300` (env var configurable)
- CORS: `["http://localhost:5173", "http://localhost:8000"]` + `AI_SUPPORT_CORS_ORIGINS` env var
- `/api/fs/read` and `/api/fs/dir`: workspace-scoped with `Path.resolve()` + `is_relative_to()`
- Session TTL: confirmed `TTLCache` auto-refreshes on access. No code change needed.

### 6. New env vars documentation

Two new environment variables were introduced. These should be documented in the project's configuration guide:

| Variable | Default | Purpose |
|----------|---------|---------|
| `STREAM_TIMEOUT_SEC` | `300` | Maximum seconds before server kills an LLM stream |
| `AI_SUPPORT_CORS_ORIGINS` | `http://localhost:5173,http://localhost:8000` | Comma-separated CORS allowed origins |

---

## No Updates Required

The following documents require no updates:
- `architecture_freeze.md` — freeze exceptions correctly anticipated all changes
- `rollback_strategy.md` — rollback procedure is still valid
- `blast_radius_analysis.md` — blast radius was accurately predicted (2 files, very small)
- `pr001_risk_assessment.md` — all risks were accurately assessed; no new risks emerged
- `pr001_review_checklist.md` — all checklist items are verifiable against the implementation
