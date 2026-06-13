# PR-001 Risk Assessment

> **Document type**: Read-only planning — no code was modified.
> **Date**: 2026-06-13

---

## Risk Matrix

| Risk Dimension | Level | Justification | Mitigation |
|---------------|-------|---------------|------------|
| **Compile risk** | **Low** | Adding `import os` to `runtime_manager.py`. No other import changes. | Verified: `os` is stdlib, always available |
| **Runtime risk** | **Low** | Increasing timeout is strictly more permissive. Path validation adds a check before existing logic. CORS restriction reduces access. | Conservative defaults. Env var overrides for all 3 changes. |
| **Regression risk** | **Low** | Existing valid file reads still work (path validation only rejects out-of-workspace). Existing chat still works (timeout increased, not decreased). | Full test suite run after each commit. |
| **Security risk** | **Low (improves security)** | PR-001's purpose is closing security vulnerabilities. Risk is in the path validation logic itself (bypass). | Comprehensive edge case testing. Security review required. |
| **Migration risk** | **None** | No schema changes, no data migration, no new tables. | N/A |

---

## Specific Risks

### Risk 1: Path validation false positive

**Scenario**: A valid workspace file is rejected by path validation because:
- Windows case-insensitive paths don't match
- UNC paths don't resolve as expected
- Junction points (Windows) behave differently from symlinks

**Likelihood**: Low — `Path.resolve()` handles platform differences. `is_relative_to()` (Python 3.9+) is platform-aware.

**Impact**: High — users cannot read workspace files.

**Detection**: T-02-U01d (valid path test), T-02-I01b (integration test), manual QA.

**Mitigation**:
1. Test on both Windows and Linux
2. Env var `AI_SUPPORT_WORKSPACE` allows explicit workspace root override
3. Rollback: revert commit 3 only (path validation), other changes stay

**Python version check**: `is_relative_to()` requires Python 3.9+. Verify project's minimum Python version. If < 3.9, use `try: path.relative_to(root)` pattern instead.

### Risk 2: CORS blocks legitimate client

**Scenario**: A client other than the Electron IDE (e.g., a custom script, Jupyter notebook, browser extension) sends requests to the server and gets blocked by CORS.

**Likelihood**: Medium — unknown what clients exist.

**Impact**: Medium — client stops working until CORS list updated.

**Detection**: Client reports connection error. Server logs show no `Access-Control-Allow-Origin` header.

**Mitigation**:
1. `AI_SUPPORT_CORS_ORIGINS` env var for custom origins
2. Document the change in PR description
3. Rollback: revert commit 2 only

**Important note**: FastAPI/Starlette `CORSMiddleware` does NOT block WebSocket upgrade requests. It only applies to HTTP requests with an `Origin` header. WebSocket connections bypass CORS entirely. This means:
- WebSocket chat is NOT affected by CORS changes
- Only REST endpoints (`/api/fs/read`, `/sessions`, etc.) are affected
- This significantly reduces the risk of this change

### Risk 3: Timeout too long for hung streams

**Scenario**: An LLM provider hangs (network issue, server-side hang). With 30s timeout, users waited 30s. With 300s, they wait 300s before seeing the error.

**Likelihood**: Low — hung streams are rare. Users can cancel via `{type: "cancel"}` at any time.

**Impact**: Low — user experience during rare failure case is worse, but cancel button still works.

**Detection**: User reports long wait during LLM failure.

**Mitigation**:
1. `STREAM_TIMEOUT_SEC` env var allows lowering if needed
2. Cancel button (`{type: "cancel"}`) provides instant user-initiated abort
3. Future enhancement (out of scope): dynamic per-provider timeout

### Risk 4: Workspace root not set correctly

**Scenario**: `AI_SUPPORT_WORKSPACE` env var not set, server started from a directory that is NOT the project root. `Path(".").resolve()` points to wrong directory. All file reads rejected as out-of-workspace.

**Likelihood**: Medium — depends on deployment method.

**Impact**: High — all file reads fail.

**Detection**: T-02-I01b (valid file read test). Manual QA.

**Mitigation**:
1. Default `Path(".").resolve()` is correct when server is started from project root (typical usage)
2. `AI_SUPPORT_WORKSPACE` env var provides explicit override
3. Log the workspace root at startup for debugging
4. Rollback: revert commit 3

### Risk 5: Python version incompatibility

**Scenario**: `Path.is_relative_to()` was added in Python 3.9. If the project runs on 3.8, this will raise `AttributeError`.

**Likelihood**: Low — most modern projects use 3.9+.

**Detection**: Check `pyproject.toml` for `python_requires`. Or `python --version` in CI.

**Mitigation**: If < 3.9, use:
```python
try:
    resolved.relative_to(workspace_root)
except ValueError:
    raise HTTPException(status_code=403, detail="Access denied")
```

---

## NEED MORE EVIDENCE Items

| Item | Risk | Resolution Before Implementation |
|------|------|----------------------------------|
| Electron app origin header | Risk 2 (CORS blocks IDE) | Inspect Electron main process or capture `Origin` in browser DevTools. **Finding from code review**: Electron app may not connect to Python backend at all — uses `ollamaClient.ts` directly. If so, CORS change is zero-risk for IDE. |
| Python minimum version | Risk 5 (is_relative_to) | Check `pyproject.toml` `python_requires` field |
| Non-cachetools TTL fallback | C4 correctness | Read the non-cachetools code path in `persistent_manager.py` to verify refresh-on-access |
| Other clients of the REST API | Risk 2 (CORS) | Grep for `localhost:8000` or server URL references outside `src/interfaces/server/` |

---

## Exit Criteria

Implementation may proceed ONLY IF:

- [x] Architecture preserved — REST endpoints, WebSocket protocol, storage schemas unchanged
- [x] Contracts preserved — `architecture_freeze.md` freeze exceptions permit all 4 changes
- [x] Validation defined — `pr001_validation.md` covers unit, integration, regression, security, benchmark, manual
- [x] Rollback defined — 4 independent commits, each revertable
- [x] Tests defined — comprehensive edge case coverage for path validation
- [ ] **BEFORE IMPLEMENTATION**: Python minimum version verified (Risk 5)
- [ ] **BEFORE IMPLEMENTATION**: Baseline test suite pass count recorded
- [ ] **BEFORE IMPLEMENTATION**: Electron origin determined or confirmed irrelevant

If any exit criterion cannot be met: **DO NOT IMPLEMENT**. Resolve the blocker first.
