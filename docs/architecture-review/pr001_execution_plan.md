# PR-001 Execution Plan — Harden Server Defaults

> **Document type**: Read-only planning — no code was modified.
> **Date**: 2026-06-13

---

## 1. Cross-Document Consistency Check

All source documents reviewed. **No new contradictions found** beyond previously documented CD-1/CD-2/CD-3 (none affect PR-001).

Consistency confirmed across:
- `implementation_contract.md` PR-001 section
- `pr_breakdown.md` PR-001 entry
- `architecture_freeze.md` T-02 freeze exceptions
- `migration_strategy.md` T-02/T-06 section
- `rollback_strategy.md` T-02/T-06 section
- `test_strategy.md` T-02/T-06 section
- `validation_checklist.md` Phase A checklist

**One observation**: `implementation_contract.md` states "Changes confined to `main.py` and `runtime_manager.py`" — this is accurate based on source code inspection. No additional files require modification for the 4 changes.

---

## 2. Engineering Scope

### Exact Engineering Objective

Modify 4 configuration-level behaviors in 2 files:

| Change | File | Current Value | Target Value |
|--------|------|---------------|-------------|
| **C1**: Increase stream timeout | `src/core/runtime/runtime_manager.py:22` | `STREAM_TIMEOUT_SEC = 30.0` | `>= 120`, configurable via `STREAM_TIMEOUT_SEC` env var |
| **C2**: Restrict CORS origins | `src/interfaces/server/main.py:214-220` | `allow_origins=["*"]` | Explicit allowlist: `["http://localhost:5173", "http://localhost:8000"]` + env var override |
| **C3**: Add path validation to `/api/fs/read` | `src/interfaces/server/main.py:284-305` | No validation — accepts any path | Resolve path, validate against workspace root, reject symlink escapes |
| **C4**: Verify session TTL refresh-on-activity | `src/core/session/persistent_manager.py` | TTL=3600s via `cachetools.TTLCache` | Verify `TTLCache` auto-refreshes on access (it does — `TTLCache.__getitem__` resets timer). Document. |

### Root Cause Addressed
RC-2: Phase 1B defaults never updated for production.

### Expected Outcome
- P-02 (timeout mismatch): Resolved — stream timeout >= 120s with env var override
- P-11 (session TTL): Resolved — `TTLCache` already refreshes on access (document this)
- P-15 (CORS *): Resolved — explicit origin allowlist
- P-16 (unrestricted file read): Resolved — workspace-scoped path validation

### Success Metrics
- Zero CORS bypass from unauthorized origins
- Zero path traversal via file API
- Zero spurious TIMEOUT errors during normal chat
- Electron IDE (if it connects to backend) still works

---

## 3. Implementation Sequence

### Step 1: Gather evidence (preconditions)

Before writing any code:

1. **Determine workspace root at runtime**: The server already resolves workspace from `AI_SUPPORT_WORKSPACE` env var (line 170: `workspace = Path(os.getenv("AI_SUPPORT_WORKSPACE", ".")).resolve()`). However, this only runs when indexing is enabled. The path validation needs a workspace root available unconditionally.

   **Action**: Move workspace resolution to `ServerState` or `lifespan()` so it's always available, even without indexing. Default: `Path(".").resolve()`.

2. **Determine Electron origin**: Grep of `src/AgenticAI/src/` found no `ws://` or `http://localhost:8000` references. The Electron app appears to use `ollamaClient.ts` (direct Ollama at `http://localhost:11434`) and `aiService.ts` (direct LLM calls), not the Python backend server.

   **Finding**: **NEED MORE EVIDENCE** — The Electron IDE may not connect to the Python backend at all for chat. The `playwright.config.ts` uses `http://localhost:5173` (Vite dev server). If the Electron app does connect to the backend, it would be from `http://localhost:5173` (renderer) or the Electron main process (origin varies by platform — could be `file://`, `app://`, or `http://localhost`).

   **Conservative approach**: Allow `http://localhost:*` (any localhost port) plus env var `AI_SUPPORT_CORS_ORIGINS` for custom overrides.

3. **Measure max LLM generation time**: Anthropic adapter computes `120 + prompt_chars/50`, max 300s. Setting `STREAM_TIMEOUT_SEC = 300` matches the maximum provider timeout. Setting it to 120 with env var override is the minimum safe value.

4. **Record baseline test suite pass count**: Run `python -m pytest tests/` and record pass/fail/skip counts.

### Step 2: Implement C1 — Stream timeout (runtime_manager.py)

**File**: `src/core/runtime/runtime_manager.py`
**Line 22**: `STREAM_TIMEOUT_SEC = 30.0`

**Change**:
- Read from env var with fallback: `STREAM_TIMEOUT_SEC = float(os.getenv("STREAM_TIMEOUT_SEC", "300"))`
- Add `import os` at top of file
- Value 300 matches the maximum Anthropic timeout (120 + max prompt / 50, capped at 300)
- Env var allows per-deployment override without code change

**Affected behavior**:
- `RuntimeManager.execute()` at line 86: `timeout=STREAM_TIMEOUT_SEC` — now uses 300s instead of 30s
- Timeout error event (`"code": "TIMEOUT"`) still fires, just later
- No protocol change — same error type and format

**Risks**: None. Increasing timeout is strictly more permissive. A truly hung stream now takes longer to kill (300s vs 30s), but the cancellation button (`{type: "cancel"}`) still works instantly.

### Step 3: Implement C2 — CORS restriction (main.py)

**File**: `src/interfaces/server/main.py`
**Lines 214-220**: CORS middleware config

**Change**:
```
# Current:
allow_origins=["*"]

# Target:
_DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",   # Vite dev server / Electron renderer
    "http://localhost:8000",   # Self-origin
]
CORS_ORIGINS = os.getenv("AI_SUPPORT_CORS_ORIGINS", "").split(",") if os.getenv("AI_SUPPORT_CORS_ORIGINS") else _DEFAULT_CORS_ORIGINS
```

- Keep `allow_credentials=True` (needed for WebSocket)
- Keep `allow_methods=["*"]` and `allow_headers=["*"]` (standard for API servers)
- Env var `AI_SUPPORT_CORS_ORIGINS` allows comma-separated custom origins
- Empty env var falls back to defaults

**Risks**:
- If Electron uses an origin not in the list, it cannot connect. Mitigated by env var override and conservative `localhost` defaults.
- WebSocket connections may not send `Origin` headers in all cases. FastAPI's `CORSMiddleware` only checks CORS on HTTP requests with `Origin` header present. WebSocket upgrade requests are not blocked by CORS middleware in FastAPI/Starlette — they bypass it. **This means the CORS change does NOT block WebSocket connections.** CORS only affects HTTP REST calls (`/api/fs/read`, `/sessions`, etc.).

### Step 4: Implement C3 — Path validation for `/api/fs/read` (main.py)

**File**: `src/interfaces/server/main.py`
**Lines 284-305**: `read_file()` handler

**Change**: Add workspace root validation before reading:

```python
# Pseudocode (not actual implementation — planning only):
1. Resolve workspace root: workspace_root = app.state.workspace_root  # set in lifespan()
2. Resolve requested path: resolved = Path(path).resolve()
3. Check containment: if not resolved.is_relative_to(workspace_root): raise HTTPException(403)
4. Check is_file: if not resolved.is_file(): raise HTTPException(404)
5. Read and return
```

**Edge cases to handle**:
- **Symlink escape**: `resolved = Path(path).resolve()` follows symlinks, then `is_relative_to(workspace_root)` catches escapes. ✓
- **Path traversal**: `../../etc/passwd` → `resolve()` normalizes → `is_relative_to()` rejects. ✓
- **`..` that resolves inside workspace**: `src/../src/main.py` → resolves to `{workspace}/src/main.py` → passes. ✓
- **Absolute paths outside workspace**: `/etc/passwd` → `is_relative_to()` rejects. ✓
- **Windows UNC paths**: `\\server\share\file` → `resolve()` handles, `is_relative_to()` rejects. ✓
- **Null bytes**: Python's `Path()` raises `ValueError` on embedded null bytes. Catch and return 400. ✓

**Also apply to `/api/fs/dir`** (lines 308-339): Same validation pattern. Both endpoints accept arbitrary paths today.

**Workspace root source**: Add to `lifespan()`:
```python
workspace_root = Path(os.getenv("AI_SUPPORT_WORKSPACE", ".")).resolve()
app.state.workspace_root = workspace_root
```
This is already computed at line 170 but only inside the indexing `if` block. Move it to always execute.

### Step 5: Verify C4 — Session TTL

**File**: `src/core/session/persistent_manager.py`
**Lines 84-92**: `TTLCache` setup

**Finding from code review**: When `cachetools` is available, sessions use `TTLCache(maxsize=max_sess, ttl=ttl)`. `cachetools.TTLCache` automatically refreshes the TTL on every `__getitem__` call (i.e., every `get_session()` call). This means active sessions do NOT expire during use.

When `cachetools` is NOT available, the fallback is a plain `dict` with manual `_session_ttl` tracking. **NEED MORE EVIDENCE**: verify the fallback path also refreshes TTL on access. If it doesn't, that's a bug to fix.

**Action**: Verify the non-cachetools path. If it lacks refresh-on-access, add it. If it does, document it. This is a minor addendum, not a scope expansion.

### Step 6: Run tests and validate

1. Run full test suite — compare to baseline
2. Run PR-001 specific tests (see `pr001_validation.md`)
3. Manual validation (see validation checklist)

---

## 4. Commit Strategy

Structure as 4 separate commits within one PR for granular rollback (per `rollback_strategy.md` recommendation):

| Commit | Change | Independently Revertable |
|--------|--------|--------------------------|
| 1 | C1: Stream timeout increase + env var | Yes |
| 2 | C2: CORS origin restriction + env var | Yes |
| 3 | C3: Path validation for `/api/fs/read` and `/api/fs/dir` | Yes |
| 4 | C4: Session TTL verification + workspace root extraction | Yes |

Each commit should pass the full test suite independently.

---

## 5. Dependency Analysis

```
PR-001: Harden Server Defaults
  │
  Depends on: Nothing
  │
  Blocked by: Nothing
  │
  Enables: All subsequent PRs (security baseline established)
  │
  Soft dependency from: PR-002 through PR-012
  (they prefer working on a hardened server, but don't technically require it)
```

**Why PR-001 has no dependencies**: All 4 changes are configuration-level. They don't depend on any architectural decision (orchestration path, import convention, HTTP client) or any other PR's output.

**Why PR-001 enables everything**: After PR-001, the testing baseline runs on a secure server. This prevents security-related noise in subsequent PR testing.
