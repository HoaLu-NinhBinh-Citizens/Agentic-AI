# PR-001 Validation Plan

> **Document type**: Read-only planning — no code was modified.
> **Date**: 2026-06-13

---

## Before Implementation

| Check | Method | Pass Criteria |
|-------|--------|--------------|
| Baseline test suite | `python -m pytest tests/` | Record exact pass/fail/skip counts |
| Current `STREAM_TIMEOUT_SEC` value | Read `runtime_manager.py:22` | Confirm 30.0 |
| Current CORS config | Read `main.py:214-220` | Confirm `allow_origins=["*"]` |
| Current file API validation | Read `main.py:284-305` | Confirm no path validation beyond `is_file()` |
| Workspace env var | Check `AI_SUPPORT_WORKSPACE` usage | Confirm only used in indexing block (line 170) |
| Session TTL behavior | Read `persistent_manager.py:84-92` | Confirm `TTLCache` usage with 3600s TTL |
| `cachetools` availability | `python -c "import cachetools"` | Confirm installed (determines TTL refresh path) |

---

## During Implementation

### After Commit 1 (Stream Timeout)

| Check | Method | Pass Criteria |
|-------|--------|--------------|
| Constant changed | Read `runtime_manager.py` | `STREAM_TIMEOUT_SEC` reads from env var, defaults to 300 |
| Env var override works | `STREAM_TIMEOUT_SEC=60 python -c "from core.runtime.runtime_manager import STREAM_TIMEOUT_SEC; print(STREAM_TIMEOUT_SEC)"` | Prints 60.0 |
| Test suite | `python -m pytest tests/` | Same pass count as baseline |

### After Commit 2 (CORS)

| Check | Method | Pass Criteria |
|-------|--------|--------------|
| CORS config | Read `main.py` CORS section | `allow_origins` does not contain `"*"` |
| Default origins | Verify localhost origins in list | `http://localhost:5173` and `http://localhost:8000` present |
| Env var override | Verify `AI_SUPPORT_CORS_ORIGINS` parsing | Comma-separated origins override defaults |
| Test suite | `python -m pytest tests/` | Same pass count as baseline |

### After Commit 3 (Path Validation)

| Check | Method | Pass Criteria |
|-------|--------|--------------|
| Workspace root | Verify `app.state.workspace_root` set in `lifespan()` | Defaults to `Path(".").resolve()` |
| Path validation in `read_file` | Code review | `Path(path).resolve().is_relative_to(workspace_root)` |
| Path validation in `read_directory` | Code review | Same pattern as `read_file` |
| Symlink handling | Code review | `resolve()` follows symlinks before `is_relative_to()` |
| Null byte handling | Code review | `ValueError` from `Path()` caught, returns 400 |
| Test suite | `python -m pytest tests/` | Same pass count as baseline |

### After Commit 4 (Session TTL)

| Check | Method | Pass Criteria |
|-------|--------|--------------|
| TTL refresh verified | Code review of `TTLCache` usage | `__getitem__` resets timer (built-in `cachetools` behavior) |
| Fallback path | Code review of non-cachetools path | Refresh-on-access implemented or already present |
| Test suite | `python -m pytest tests/` | Same pass count as baseline |

---

## After Implementation (Full Validation)

### Unit Tests Required

| Test ID | Description | Input | Expected |
|---------|-------------|-------|----------|
| T-02-U01a | Path traversal — relative escape | `../../etc/passwd` | 403 |
| T-02-U01b | Path traversal — absolute outside workspace | `/etc/passwd` or `C:\Windows\System32\config\SAM` | 403 |
| T-02-U01c | Path traversal — dot-dot segments | `src/../../../etc/passwd` | 403 |
| T-02-U01d | Valid relative path | `src/interfaces/server/main.py` | 200 with content |
| T-02-U02a | Symlink escape | Symlink inside workspace → outside file | 403 |
| T-02-U02b | Dot-dot resolving inside workspace | `src/../src/main.py` | 200 |
| T-02-U03a | Timeout constant value | N/A | `STREAM_TIMEOUT_SEC >= 120` |
| T-02-U03b | Timeout env var override | Set env var | Value matches env var |
| T-02-U04a | CORS no wildcard | N/A | `"*"` not in `allow_origins` |
| T-02-U04b | CORS includes localhost | N/A | `http://localhost:5173` in origins |
| T-02-U05a | Session TTL >= 3600s | N/A | Default TTL >= 3600 |

### Integration Tests Required

| Test ID | Description | Method | Expected |
|---------|-------------|--------|----------|
| T-02-I01a | File API rejects out-of-workspace | HTTP GET `/api/fs/read?path=/etc/passwd` | 403 |
| T-02-I01b | File API accepts workspace file | HTTP GET `/api/fs/read?path=src/main.py` (relative) | 200 + content |
| T-02-I01c | File API rejects nonexistent | HTTP GET `/api/fs/read?path=nonexistent.txt` | 404 |
| T-02-I01d | Dir API rejects out-of-workspace | HTTP GET `/api/fs/dir?path=/etc` | 403 |
| T-02-I02 | Stream timeout with long mock | Start server, mock 60s LLM stream, send chat | Stream NOT killed at 30s, completes or hits 300s |
| T-02-I03a | CORS rejects bad origin | HTTP with `Origin: http://evil.example.com` | No `Access-Control-Allow-Origin` header |
| T-02-I03b | CORS accepts good origin | HTTP with `Origin: http://localhost:5173` | Correct CORS headers |
| T-02-I04 | Session TTL refresh | Create session → wait 50% TTL → access → wait 50% → access | Session alive |

### Regression Tests Required

| Test ID | Description | Expected |
|---------|-------------|----------|
| T-02-R01 | All previously valid file reads | Identical content returned |
| T-02-R02 | Chat end-to-end | Token stream → done event, no timeout for normal responses |
| T-02-R03 | WebSocket connectivity | WebSocket connection succeeds (CORS does not affect WebSocket in FastAPI) |

### Security Tests Required

| Test ID | Description | Expected |
|---------|-------------|----------|
| T-02-S01 | Directory path to read_file | 400 or 404 (not a file listing) |
| T-02-S02 | Null byte injection | `path=src/main.py%00.txt` → 400 |
| T-02-S03 | Symlink to /etc/passwd | 403 |
| T-02-N01 | Very long path | Path > OS max → 400 |
| T-02-N02 | Unicode homoglyph traversal | 403 for traversal attempts |

### Benchmark Tests Required

| Metric | Method | Threshold |
|--------|--------|-----------|
| `stream_timeout_headroom_s` | `STREAM_TIMEOUT_SEC` minus max observed `llm_total_generation_time_s` | > 0 (timeout exceeds max generation) |

### Manual Validation Required

- [ ] Server starts: `uvicorn interfaces.server.main:app`
- [ ] Chat works: send message via WebSocket, receive streamed response
- [ ] Long prompt completes: > 30s generation does NOT timeout
- [ ] File read works: workspace file returns content
- [ ] File read blocked: out-of-workspace path returns 403
- [ ] Dir listing works: workspace directory returns listing
- [ ] Dir listing blocked: out-of-workspace directory returns 403

---

## Merge Checks

| Check | Method | Pass Criteria |
|-------|--------|--------------|
| Build succeeds | `pip install -e .` | Exit 0 |
| All existing tests pass | `python -m pytest tests/` | Pass count >= baseline |
| New tests pass | `python -m pytest tests/test_path_validation.py tests/test_server_hardening.py` | All pass |
| No unrelated changes | `git diff --stat` | Only 2 source files + test files |
| Architecture preserved | Review against `architecture_freeze.md` checklist | All items pass |
| Rollback verified | `git stash && python -m pytest tests/ && git stash pop` | Tests pass without changes |
| Security review | Manual code review of path validation logic | No bypass found |
