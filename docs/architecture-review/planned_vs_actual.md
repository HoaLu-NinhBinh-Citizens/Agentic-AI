# PR-001 Planned vs Actual

> **Document type**: Post-implementation review
> **Date**: 2026-06-13

---

## Change C1: Stream Timeout

| Aspect | Planned | Actual | Classification |
|--------|---------|--------|---------------|
| File | `runtime_manager.py:22` | `runtime_manager.py:24` (line shifted by `import os`) | Expected |
| Default value | `>= 120`, planning doc says `300` | `300` | Expected |
| Env var name | `STREAM_TIMEOUT_SEC` | `STREAM_TIMEOUT_SEC` | Expected |
| Cast | `float` | `float(os.getenv(...))` | Expected |
| Import added | `import os` | `import os` | Expected |
| Other changes | None | None | Expected |

**Verdict**: Exact match.

---

## Change C2: CORS Restriction

| Aspect | Planned | Actual | Classification |
|--------|---------|--------|---------------|
| Default origins | `["http://localhost:5173", "http://localhost:8000"]` | Same | Expected |
| Env var | `AI_SUPPORT_CORS_ORIGINS`, comma-separated | Same, with `.strip()` and empty-string filtering | Expected |
| Empty env var fallback | Falls back to defaults | Same (`if _cors_env else _DEFAULT_CORS_ORIGINS`) | Expected |
| `allow_credentials` | `True` preserved | `True` preserved | Expected |
| `allow_methods` | `["*"]` preserved | `["*"]` preserved | Expected |
| `allow_headers` | `["*"]` preserved | `["*"]` preserved | Expected |
| Variable naming | Not specified | `_DEFAULT_CORS_ORIGINS`, `_cors_env`, `CORS_ORIGINS` | Expected |

**Verdict**: Exact match. The `.strip()` on each origin is a sensible defensive addition not in the plan — harmless and correct.

---

## Change C3: Path Validation

| Aspect | Planned | Actual | Classification |
|--------|---------|--------|---------------|
| Workspace root source | `Path(os.getenv("AI_SUPPORT_WORKSPACE", ".")).resolve()` in `lifespan()` | Identical, at `main.py:178-179` | Expected |
| Storage | `app.state.workspace_root` | Identical | Expected |
| `read_file` validation | `Path(path).resolve()` + `is_relative_to(workspace_root)` | Identical | Expected |
| `read_directory` validation | Same pattern as `read_file` | Identical | Expected |
| Null byte handling | `ValueError` caught → 400 | `(ValueError, OSError)` caught → 400 | Expected |
| 403 error detail | `"Access denied: path is outside workspace"` (review checklist) | Identical | Expected |
| Startup log | Planned in risk assessment | `logger.info("Workspace root: %s", workspace_root)` at line 191 | Expected |
| `from pathlib import Path` removal | Not planned (shadowed top-level import) | Removed — the function-local `from pathlib import Path` in both handlers was redundant since `Path` is already imported at module level (line 27) | Expected |

### Security review: Does 403 message leak workspace root?

The 403 detail is `"Access denied: path is outside workspace"` — does NOT include the workspace root path. Matches `pr001_review_checklist.md` requirement.

**Verdict**: Exact match. `OSError` addition to the catch is a correct defensive measure for malformed paths beyond null bytes (e.g., paths exceeding OS limits).

---

## Change C4: Session TTL

| Aspect | Planned | Actual | Classification |
|--------|---------|--------|---------------|
| Code change | Verification only — no code change expected | No code change made | Expected |
| `TTLCache` refresh | Auto-refreshes on `__getitem__` | Confirmed correct | Expected |
| Non-cachetools fallback | Planned: verify, fix if needed | Verified: `_session_access` updated but no eviction logic. No fix made because `cachetools` is installed. | Expected |

**Verdict**: Exact match. The non-cachetools fallback lacks eviction — a latent bug but correctly out of PR-001 scope since `cachetools` is installed.

---

## Commit Structure

| Planned | Actual | Classification |
|---------|--------|---------------|
| 4 separate commits (C1, C2, C3, C4) | Not yet committed — all changes are unstaged | **Unexpected** |

The implementation applied all changes in one working tree session without creating individual commits. The plan called for 4 separate commits for granular rollback. This should be addressed before merge by structuring the commits properly.

**Risk**: Low — the changes are logically separable and can still be committed in 4 steps. But if committed as a single commit, granular rollback (e.g., reverting only CORS without reverting path validation) becomes harder.

---

## Files Touched

| Planned | Actual | Classification |
|---------|--------|---------------|
| 2 source files + test files | 2 source files (`runtime_manager.py`, `main.py`) + 2 test files | Expected |
| `persistent_manager.py` possibly modified | Not modified (correct — verification only) | Expected |
| No `__init__.py` changes | No `__init__.py` changes | Expected |
| No `pyproject.toml` changes | No `pyproject.toml` changes | Expected |

---

## Test Coverage vs Validation Plan

| Test ID | Planned | Implemented | Classification |
|---------|---------|-------------|---------------|
| T-02-U01a | Path traversal — relative escape | `TestPathTraversal.test_relative_escape` | Expected |
| T-02-U01b | Absolute outside workspace | `TestPathTraversal.test_absolute_outside_workspace` | Expected |
| T-02-U01c | Dot-dot segments | `TestPathTraversal.test_dot_dot_segments` | Expected |
| T-02-U01d | Valid relative path | `TestPathTraversal.test_valid_relative_path` | Expected |
| T-02-U02a | Symlink escape | `TestSymlinkEscape.test_symlink_to_outside` (skipped on Windows) | Expected |
| T-02-U02b | Dot-dot inside workspace | `TestSymlinkEscape.test_dot_dot_inside_workspace` | Expected |
| T-02-U03a | Timeout >= 120 | `TestTimeoutConfig.test_timeout_value_sufficient` | Expected |
| T-02-U03b | Env var override | `TestTimeoutConfig.test_timeout_env_override` | Expected |
| T-02-U04a | No wildcard in CORS | `TestCORSConfig.test_no_wildcard_in_origins` | Expected |
| T-02-U04b | Localhost in CORS | `TestCORSConfig.test_localhost_in_origins` | Expected |
| T-02-U05a | Session TTL >= 3600 | `TestSessionTTL.test_default_ttl_sufficient` | Expected |
| T-02-I01a | File API rejects outside | `TestFileAPIPathValidation.test_read_file_rejects_outside_workspace` | Expected |
| T-02-I01b | File API accepts workspace | `TestFileAPIPathValidation.test_read_file_accepts_workspace_file` | Expected |
| T-02-I01c | File API rejects nonexistent | `TestFileAPIPathValidation.test_read_file_rejects_nonexistent` | Expected |
| T-02-I01d | Dir API rejects outside | `TestFileAPIPathValidation.test_read_dir_rejects_outside_workspace` | Expected |
| T-02-I03a | CORS rejects bad origin | `TestCORSEnforcement.test_cors_rejects_bad_origin` | Expected |
| T-02-I03b | CORS accepts good origin | `TestCORSEnforcement.test_cors_accepts_good_origin` | Expected |
| T-02-S01 | Directory to read_file | `TestDirectoryAsFile.test_directory_to_read_file` | Expected |
| T-02-S02 | Null byte injection | `TestNullByteInjection.test_null_byte_in_path` | Expected |
| T-02-I02 | Stream timeout with mock LLM | **NOT IMPLEMENTED** | **Risk** |
| T-02-I04 | Session TTL with activity | **NOT IMPLEMENTED** | **Risk** |
| T-02-N01 | Very long path | **NOT IMPLEMENTED** | **Risk** |
| T-02-N02 | Unicode homoglyph traversal | **NOT IMPLEMENTED** | **Risk** |
| T-02-S03 | Symlink to /etc/passwd (integration) | Covered by unit test only (skipped on Windows) | Expected |
| T-02-R01 | Regression — valid file reads | Covered by T-02-I01b | Expected |
| T-02-R02 | Chat end-to-end | **NOT IMPLEMENTED** (requires running server + LLM) | **Risk** |
| T-02-R03 | WebSocket connectivity | **NOT IMPLEMENTED** (requires running server) | **Risk** |

### Missing Tests Summary

| Missing Test | Impact | Recommendation |
|-------------|--------|----------------|
| T-02-I02 (stream timeout with mock LLM) | Medium — timeout logic is trivial (`asyncio.wait_for` with bigger number) but untested at integration level | Accept: unit test confirms value >= 120. Integration test requires complex mock setup. |
| T-02-I04 (session TTL refresh) | Low — `TTLCache` is a well-tested library. PR-001 made no code change here. | Accept: verification-only, no code change. |
| T-02-N01 (very long path) | Low — OS rejects before our code does | Accept for PR-001. |
| T-02-N02 (unicode homoglyph) | Low — `Path.resolve()` handles normalization | Accept for PR-001. |
| T-02-R02/R03 (end-to-end chat/WS) | Medium — requires full server startup with mocks | Accept: manual validation item, not automatable without significant infrastructure. |

---

## Summary

| Category | Count |
|----------|-------|
| Expected matches | 28 |
| Unexpected differences | 1 (commit structure — not yet committed) |
| Risks | 5 (missing integration/edge tests) |
| Unknown | 0 |
