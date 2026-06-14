# PR-004 Success Criteria

> **Date**: 2026-06-14
> **PR**: PR-004 — Delete Remaining Dead Code and Fix Broken Test Suite

---

## Success Criteria

| # | Criterion | Metric | Verification |
|---|-----------|--------|-------------|
| S1 | All legacy redirect packages deleted | 10 directories removed (`runtime`, `tools`, `hardware_engine`, `config`, `health`, `llm`, `models`, `parsing`, `security`, `scheduler`) | `python -c "import src.runtime"` → `ModuleNotFoundError` (repeat for all 10) |
| S2 | `core/events/` deleted | 6 files removed | `python -c "import src.core.events"` → `ModuleNotFoundError` |
| S3 | Orphan `application/api/app/` files deleted | 3 files removed (`chat_endpoints.py`, `api_server.py`, `dashboard_websocket.py`) | Files do not exist on disk |
| S4 | Zero "Legacy alias" stubs remain | `rg "Legacy alias" src/ --type py` returns zero hits | Zero output |
| S5 | Zero test collection errors from deleted modules | `python -m pytest tests/ -q --tb=no` has fewer collection errors than baseline (16) | Error count reduced; ideally 0, acceptable <=4 (for pre-existing symbol mismatches in production code like `WriteBoundaryGuard`) |
| S6 | Previously passing tests still pass | Tests in updated files pass | `python -m pytest tests/test_tools.py tests/test_sandbox.py tests/test_runtime.py tests/test_output_policy.py tests/test_p2_sandbox.py tests/test_p3_observability.py tests/test_features_2025.py tests/unit/test_config.py --tb=no` → >= 175 passed |
| S7 | Server starts without import errors | Production path intact | `python -c "from interfaces.server.main import app"` → no error |
| S8 | No live code deleted | All files in do-not-modify list exist and unchanged | `git diff HEAD -- src/interfaces/server/main.py src/core/agent/ src/application/orchestration/tool_execution/` → empty |
| S9 | Stale `__pycache__` cleaned | No `.pyc` files in deleted package directories | `find src/core/multi_agent src/core/orchestration src/multi_agent -name "*.pyc" 2>/dev/null` → empty |
| S10 | No new files created | Deletion and import update only | `git diff --name-status` shows only D (deleted) and M (modified), no A (added) |

---

## Failure Criteria

| # | Criterion | Action |
|---|-----------|--------|
| F1 | Server fails to start after any commit | Revert immediately |
| F2 | Any previously passing test fails after import redirect | Fix the import; if unfixable, revert the specific test change |
| F3 | Test collection errors increase above 16 | Revert; something was deleted that shouldn't have been |
| F4 | Any file in the do-not-modify list was modified | Revert the modification |
| F5 | A redirect package turns out to have a production importer | Do not delete that package; remove it from scope |

---

## Implementation Estimates

| Dimension | Estimate |
|-----------|---------|
| **Complexity** | Medium-Low — mostly mechanical deletion + grep-guided import redirect |
| **Risk** | Low — all deletions verified by grep, server import tested |
| **Expected commits** | 4 (test import update → test fix/delete → source deletion → artifact cleanup) |
| **Expected files modified** | ~8 test files updated, ~6 test files deleted, ~52 source files deleted, ~4 `__pycache__` dirs cleaned = ~70 files total |
| **Expected lines deleted** | ~3,576 source + ~2,000 dead tests = ~5,500 lines |
| **Migration cost** | Zero — no data migration, no schema changes |
| **Rollback cost** | Low — `git revert` per commit. Each commit is independently revertable. |
| **Testing cost** | Low — run existing test suite. No new tests to write. |
| **Deployment impact** | None — deleted code has zero production callers |
| **Estimated time** | 2-3 hours including verification |

---

## Post-PR-004 State

| Metric | Before PR-004 | After PR-004 |
|--------|-------------|-------------|
| Python source files (excl. Electron) | ~1,296 | ~1,244 (-52) |
| Test files | ~351 | ~345 (-6) |
| Test collection errors | 16 | 0-4 |
| Legacy redirect packages | 10 | 0 |
| Dead subsystems | 1 (`core/events/`) | 0 |
| "Legacy alias" stubs | 10 | 0 |
| Orphan `application/api/app/` files | 3 | 0 |
| Stale `__pycache__` from PR-003 | 33 .pyc files | 0 |
