# PR-004 Priority Analysis

> **Date**: 2026-06-14
> **As of commit**: `a2042cb` (post PR-003)
> **Author**: Principal Engineer

---

## 1. Problem Inventory

### P-01: 16 test collection errors block the entire test suite

**Severity**: Critical
**Root cause**: Test files import from modules that don't exist or from symbols that aren't exported. The test runner hits `ImportError` during collection and aborts — no tests run at all unless `testpaths` restricts collection (currently set to `tests/unit` and `tests/integration` in `pyproject.toml`, but `python -m pytest tests/` collects everything).
**Evidence**: `python -m pytest tests/ -q --tb=no` → `Interrupted: 16 errors during collection`
**Affected modules**: 16 test files in `tests/` root
**Why it exists**: During phased development, test files were written against top-level redirect packages (`src.events`, `src.hardware`, `src.learning`, etc.) that were deleted in PR-002 without updating or deleting their test consumers. Other tests reference symbols that were never exported from their canonical modules.
**Risk**: Any developer running `python -m pytest tests/` sees 16 errors and zero passing tests. The test suite appears completely broken. Actual passing tests are invisible behind the collection failure wall.
**Scale impact**: Blocks all CI/CD, blocks all developer confidence, blocks all regression detection.

### P-02: 10 legacy redirect packages with zero production importers

**Severity**: High
**Root cause**: Top-level packages (`src/runtime`, `src/tools`, `src/hardware_engine`, `src/config`, `src/health`, `src/llm`, `src/models`, `src/parsing`, `src/security`, `src/scheduler`) are "Legacy alias" stubs that re-export symbols from canonical locations (`core.*`, `infrastructure.*`, `domains.*`). Zero production code imports them — only test files.
**Evidence**: `rg "from src\.<package>" src/ --type py` returns zero external hits for 8/10 packages. The 2 with self-references (`config`, `models`) have no external production callers either.
**Affected modules**: 10 directories, ~43 files, ~1,948 lines
**Why it exists**: Created during a migration to provide backward compatibility. The migration completed (production code uses canonical paths) but the redirects were never cleaned up.
**Risk**: New developers discover two import paths for the same symbol. Tests written against redirect paths silently diverge from production paths. Symbol mismatches accumulate (redirect exports a symbol that was renamed/removed in canonical location → `ImportError` only visible in tests).
**Scale impact**: Every redirect is a maintenance surface that drifts from canonical code.

### P-03: Dead `core/events/` subsystem (6 files, 1,366 lines)

**Severity**: High
**Root cause**: EventEmitter was built as infrastructure for orchestration systems. All orchestration systems were deleted in PR-003. The EventEmitter has zero production importers.
**Evidence**: `rg "from.*core\.events|import.*core\.events" src/ --type py` → only self-imports within `core/events/` itself.
**Affected modules**: `src/core/events/` (6 files)
**Why it exists**: Speculative infrastructure from phased development, never wired into production.
**Risk**: Low runtime risk (dead code), but contributes to codebase confusion and inflated file count.
**Scale impact**: 1,366 lines of dead code.

### P-04: Orphan files in `application/api/app/`

**Severity**: Medium
**Root cause**: `chat_endpoints.py` imports from deleted `core.multi_agent.agent`. `api_server.py` is an alternative FastAPI app not wired to production `main.py`. `dashboard_websocket.py` has zero importers.
**Evidence**: `rg "api_server|chat_endpoints|dashboard_websocket" src/ tests/ --type py` → only self-references or within the orphan cluster.
**Affected modules**: 3 files in `application/api/app/`
**Why it exists**: `api_server.py` was an earlier iteration of the server; `chat_endpoints.py` was its route module. Neither was wired into the final `interfaces/server/main.py`.
**Risk**: `chat_endpoints.py` will throw `ImportError` if anything ever tries to import it (references deleted `core.multi_agent.agent`). Silent broken code.
**Scale impact**: Small (~3 files).

### P-05: Stale `__pycache__` and `egg-info` artifacts

**Severity**: Low
**Root cause**: PR-003 deleted `.py` files but git doesn't track `__pycache__/` directories.
**Evidence**: 33 stale `.pyc` files in `core/multi_agent/`, `core/orchestration/`, `multi_agent/`.
**Affected modules**: Build artifacts only.
**Why it exists**: Normal git behavior — `.pyc` files are in `.gitignore`.
**Risk**: Stale `.pyc` can shadow imports in edge cases (Python imports `.pyc` if `.py` is missing).
**Scale impact**: Minimal.

---

## 2. Task Clustering

### Task A: Fix broken test suite (P-01 + P-02 + P-03 + P-04 + P-05)

Delete all remaining dead code (redirect packages, `core/events/`, orphan `application/api/app/` files) and fix or delete the 16 broken test files. This is one coherent task because:
- 12 of the 16 broken tests fail because they import from redirect packages (P-02)
- Deleting redirect packages requires updating or deleting their test consumers
- The remaining 4 broken tests import from `src.events` (deleted redirect to `core/events/` which is itself dead) or non-existent modules
- Fixing the test suite and deleting dead code are the same work

**However**, this violates the "one architectural problem per task" rule. Split:

### Task A: Delete remaining dead code (P-02 + P-03 + P-04 + P-05)

Delete 10 redirect packages, `core/events/`, 3 orphan `application/api/app/` files, stale `__pycache__`. Pure deletion.

### Task B: Fix 16 broken test files (P-01)

For each broken test: either redirect its imports to canonical locations, or delete it if the test is itself dead (tests dead code that no longer exists).

**Problem**: Task A and Task B are coupled. Deleting redirect packages in Task A breaks more tests. Fixing tests in Task B requires knowing which packages will be deleted. They must be done together or in strict sequence (B before A, or A+B atomically).

### Decision: Combine into single PR-004

Task A + Task B form one atomic operation: "Delete all remaining dead code and fix every broken test." The coupling is too tight to separate safely.

---

## 3. Priority Ranking

| Rank | Task | Engineering Value | Risk Reduction | Complexity | ROI |
|------|------|------------------|----------------|------------|-----|
| **P0** | **A+B: Dead code + broken tests** | Critical — unblocks test suite | High — eliminates 16 collection errors | Medium — mechanical deletion + import redirect | **Highest** — every future PR benefits from a working test suite |
| P1 | Import convention unification (dual `src.` vs bare) | High | Medium | High — touches hundreds of files | Medium — large blast radius |
| P2 | Dependency audit (remove unused `asyncpg`, `langchain`) | Medium | Low | Low | Low — cosmetic |

---

## 4. Why P0 — Why Now

The test suite is the foundation of every future PR. With 16 collection errors, no developer can trust `python -m pytest tests/`. Every PR from this point forward ships without regression confidence.

PR-001 hardened security. PR-002 deleted Tier 1+2 dead code. PR-003 consolidated orchestration. The natural next step is to finish the dead code audit (Tier 3: redirect packages + remaining dead subsystems) and restore the test suite to a usable state.

This is the last PR in the "clean the house" sequence before moving to feature work or deeper refactoring.
