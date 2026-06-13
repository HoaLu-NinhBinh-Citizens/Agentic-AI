# PR-001 Review Checklist

> **Document type**: Read-only planning — no code was modified.
> **Date**: 2026-06-13

---

## Pre-Review Verification

Before requesting review, the implementing engineer must confirm:

- [ ] Baseline test pass count recorded before changes
- [ ] Python minimum version verified (>= 3.9 for `is_relative_to`, or fallback used)
- [ ] Electron origin determined or confirmed irrelevant to CORS change

---

## Reviewer Checklist

### Architecture Preservation (Mandatory)

- [ ] No REST endpoint removed or renamed
- [ ] No REST endpoint response schema changed (valid paths return same format)
- [ ] No WebSocket message type removed or renamed
- [ ] No WebSocket message field removed
- [ ] No SQLite column removed or renamed
- [ ] No environment variable removed or renamed
- [ ] No `pyproject.toml` entry point changed
- [ ] No new dependencies added
- [ ] `/api/fs/read` returns same `{"content": ..., "path": ...}` for valid workspace paths

### Change C1: Stream Timeout

- [ ] `STREAM_TIMEOUT_SEC` reads from `os.getenv("STREAM_TIMEOUT_SEC", "300")`
- [ ] Default value >= 120 (per implementation contract)
- [ ] Value is cast to `float`
- [ ] `import os` added
- [ ] No other changes to `runtime_manager.py`
- [ ] Timeout error event format unchanged: `{"type": "error", "data": {"code": "TIMEOUT", "message": "Stream timeout"}}`

### Change C2: CORS Restriction

- [ ] `allow_origins` does NOT contain `"*"`
- [ ] Default origins include `http://localhost:5173` and `http://localhost:8000`
- [ ] `AI_SUPPORT_CORS_ORIGINS` env var overrides defaults when set
- [ ] Empty env var falls back to defaults (not empty list)
- [ ] `allow_credentials=True` preserved
- [ ] `allow_methods=["*"]` preserved
- [ ] `allow_headers=["*"]` preserved

### Change C3: Path Validation

- [ ] `app.state.workspace_root` set in `lifespan()` as `Path(os.getenv("AI_SUPPORT_WORKSPACE", ".")).resolve()`
- [ ] `read_file()` resolves path with `Path(path).resolve()`
- [ ] `read_file()` checks `resolved.is_relative_to(workspace_root)` (or `.relative_to()` with try/except for Python < 3.9)
- [ ] `read_file()` returns 403 for out-of-workspace paths
- [ ] `read_file()` returns 404 for nonexistent files (unchanged behavior)
- [ ] `read_file()` handles `ValueError` from null bytes in path → 400
- [ ] `read_directory()` has identical path validation as `read_file()`
- [ ] Symlinks resolved before containment check (via `resolve()`)
- [ ] No path validation bypass found (security review)
- [ ] Error response for 403: `{"detail": "Access denied: path is outside workspace"}` or similar
- [ ] Workspace root logged at startup for debugging

### Change C4: Session TTL

- [ ] `TTLCache` refresh-on-access behavior documented (or code comment added)
- [ ] Non-cachetools fallback path verified for refresh-on-access
- [ ] No functional change to session TTL behavior (verification only)

### Code Quality

- [ ] No unrelated refactoring
- [ ] No opportunistic cleanup
- [ ] No formatting-only changes
- [ ] No comments referencing ticket numbers or task IDs
- [ ] Error messages are descriptive but don't leak internal paths
- [ ] Workspace root path not included in 403 error messages (information disclosure)

### Tests

- [ ] Unit tests cover all path traversal edge cases (T-02-U01a through U01d)
- [ ] Unit tests cover symlink escape (T-02-U02a, U02b)
- [ ] Unit tests cover timeout config (T-02-U03a, U03b)
- [ ] Unit tests cover CORS config (T-02-U04a, U04b)
- [ ] Integration tests cover file API security (T-02-I01a through I01d)
- [ ] Security tests cover null byte, directory-as-file, symlink (T-02-S01 through S03)
- [ ] All existing tests pass (same count as baseline)
- [ ] Tests run on the target OS (Windows if that's the deployment target)

### Commit Structure

- [ ] 4 separate commits (C1, C2, C3, C4)
- [ ] Each commit passes full test suite independently
- [ ] Commits follow Conventional Commits: `fix(server): ...`
- [ ] Each commit is independently revertable

---

## Security Review (Required)

The security reviewer must verify:

- [ ] Path validation cannot be bypassed with:
  - Double encoding (`%2e%2e%2f`)
  - Unicode normalization
  - OS-specific path separators (`\` on Windows)
  - Null bytes
  - Very long paths
  - Symlink chains
  - Junction points (Windows)
  - Case sensitivity edge cases (Windows)
- [ ] 403 error does not leak the workspace root path
- [ ] CORS restriction is effective for HTTP REST requests
- [ ] CORS does not break WebSocket connections (Starlette CORS middleware does not apply to WebSocket upgrades — verify)

---

## Approval Criteria

| Reviewer | Required | Focus |
|----------|----------|-------|
| Code reviewer | Yes | Code quality, test coverage, commit structure |
| Security reviewer | Yes | Path validation bypass, CORS effectiveness |
| Architecture reviewer | No | Config-only changes within freeze exceptions |
| Performance reviewer | No | No performance-sensitive changes |

**Merge requires**: Both code review and security review approval.

---

## Post-Merge Monitoring

After merge, monitor for 24 hours:

- [ ] Zero false-positive 403s on valid file reads (check server logs for 403 status codes)
- [ ] Zero TIMEOUT errors during normal chat (check server logs for TIMEOUT events)
- [ ] Zero CORS-related connection failures (check server logs for missing Origin headers)
- [ ] Server starts cleanly in CI/CD pipeline

If any monitoring item fails: evaluate rollback of the specific commit (C1, C2, C3, or C4).
