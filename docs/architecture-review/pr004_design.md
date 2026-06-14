# PR-004 Design — Delete Remaining Dead Code and Fix Broken Test Suite

> **Document type**: Design — no code modified.
> **Date**: 2026-06-14
> **Author**: Principal Engineer
> **Status**: READY FOR IMPLEMENTATION
> **Depends on**: PR-001 (merged), PR-002 (implemented), PR-003 (implemented)

---

## 1. Goal

Delete all remaining dead code (legacy redirect packages, dead `core/events/` subsystem, orphan application files) and fix every broken test file so the test suite collects and runs without errors.

### Root Causes Addressed

**RC-1: Legacy redirect packages never cleaned up.** Ten top-level packages (`src/runtime`, `src/tools`, `src/hardware_engine`, `src/config`, `src/health`, `src/llm`, `src/models`, `src/parsing`, `src/security`, `src/scheduler`) exist solely to re-export symbols from canonical locations. Zero production code imports them. ~16 test files import through them, of which 12 are broken by symbol mismatch or missing sub-modules.

**RC-2: Dead `core/events/` subsystem.** EventEmitter (6 files, 1,366 lines) was infrastructure for deleted orchestration systems. Zero production importers. One test file (`test_events.py`) tested it via the now-deleted `src.events` redirect.

**RC-3: Orphan `application/api/app/` files.** `chat_endpoints.py` imports from deleted `core.multi_agent.agent`. `api_server.py` imports `chat_endpoints.py`. `dashboard_websocket.py` has zero importers. All three are unreachable from the production server.

**RC-4: Test files import from non-existent modules.** Six test files import from modules that never existed in the canonical tree (`src.events`, `src.hardware`, `src.learning`, `src.observability`, `src.memory`, `src.introspection`, `src.retrieval`, `src.healing`, `src.metrics`). These were either deleted redirects or modules that were planned but never implemented.

---

## 2. Why PR-004 Is Next

1. **PR-001** (security hardening) — merged.
2. **PR-002** (Tier 1+2 dead code) — implemented.
3. **PR-003** (orchestration consolidation) — implemented.
4. **PR-004** (Tier 3 dead code + test suite fix) — completes the dead code audit and restores test suite usability. Every future PR depends on a working test suite.

PR-004 is the last "cleanup" PR before feature work or deeper refactoring (import convention unification, dependency audit) can proceed with confidence.

---

## 3. Scope

### 3.1 Dead Code to Delete

#### Group A: Legacy redirect packages (10 packages, ~43 files)

| Package | Files | Lines | Production Importers | Test Importers | Action |
|---------|-------|-------|---------------------|----------------|--------|
| `src/runtime/` | 3 | ~180 | 0 | 3 (`test_p3_observability`, `test_phase15`, `test_runtime`) | **DELETE** |
| `src/tools/` | 9 | ~450 | 0 | 5 (`test_flash_tools`, `test_p2_sandbox`, `test_p7_hardware`, `test_sandbox`, `test_tools`) | **DELETE** |
| `src/hardware_engine/` | 17 | ~800 | 0 | 2 (`test_hardware_engine`, `test_p7_hardware`) | **DELETE** |
| `src/config/` | 4 | ~200 | 0 (self-imports only) | 3 (`test_output_policy`, `test_retrieval_manifest`, `unit/test_config`) | **DELETE** |
| `src/health/` | 2 | ~40 | 0 | 2 (`test_p9_production_concepts`, `test_phase4`) | **DELETE** |
| `src/llm/` | 2 | ~20 | 0 | 0 | **DELETE** |
| `src/models/` | 2 | ~80 | 0 (self-imports only) | 2 (`test_features_2025`, `test_p4_retrieval`) | **DELETE** |
| `src/parsing/` | 2 | ~20 | 0 | 0 | **DELETE** |
| `src/security/` | 1 | ~10 | 0 | 0 | **DELETE** |
| `src/scheduler/` | 1 | ~10 | 0 | 1 (`test_phase15`) | **DELETE** |

**Confidence**: High — all are explicitly labeled "Legacy alias" in their docstrings. Zero production callers verified by grep.

#### Group B: `src/core/events/` (6 files, 1,366 lines)

| File | External Importers |
|------|-------------------|
| `__init__.py` | None (self-imports only) |
| `emitter.py` | None |
| `event.py` | None |
| `handlers.py` | None (self-reference in docstring) |
| `middleware.py` | None |
| `types.py` | None |

**Confidence**: High — zero production callers. The `watchdog.events` imports in `infrastructure/` are from the third-party `watchdog` library, not from `core.events`.

#### Group C: Orphan `application/api/app/` files (3 files)

| File | Broken Import | External Importers | Action |
|------|--------------|-------------------|--------|
| `chat_endpoints.py` | `core.multi_agent.agent` (deleted in PR-003) | `api_server.py` only | **DELETE** |
| `api_server.py` | `chat_endpoints` (being deleted) | None | **DELETE** |
| `dashboard_websocket.py` | None | None | **DELETE** |

**Confidence**: High — `api_server.py` is not wired to production `main.py`. Verified by grepping `src/interfaces/` for `api_server`.

#### Group D: Stale `__pycache__` directories (33 files)

| Directory | Stale `.pyc` files |
|-----------|-------------------|
| `src/core/multi_agent/__pycache__/` | 3 |
| `src/core/multi_agent/coordination/__pycache__/` | 26 |
| `src/core/orchestration/__pycache__/` | 5 |
| `src/multi_agent/__pycache__/` | 2 |

**Action**: Delete all four `__pycache__` directories and their parent empty directories.

#### Summary

| Group | Items | Files | Lines |
|-------|-------|-------|-------|
| A | 10 redirect packages | ~43 | ~1,810 |
| B | `core/events/` | 6 | 1,366 |
| C | Orphan app files | 3 | ~400 |
| D | Stale `__pycache__` | 33 .pyc | — |
| **Total** | | **~85** | **~3,576** |

### 3.2 Broken Test Files — Classification and Action

Each of the 16 broken test files falls into one of three categories:

#### Category 1: Tests that import ONLY from deleted/non-existent modules → DELETE

These test files import from modules that don't exist and never will. The tests test dead code.

| Test File | Broken Imports | Canonical Equivalent Exists? | Action |
|-----------|---------------|------------------------------|--------|
| `test_events.py` | `src.events.*` | `core.events.*` exists but is also being deleted (Group B) | **DELETE** |
| `test_hardware.py` | `src.hardware` | Module never existed | **DELETE** |
| `test_learning.py` | `src.learning` | Module never existed | **DELETE** |
| `test_observability.py` | `src.observability` | Module never existed | **DELETE** |
| `test_p5_memory.py` | `src.memory.advanced_memory` | Module never existed | **DELETE** |
| `test_phase4.py` | `src.introspection`, `src.health`, `src.healing`, `src.metrics` | 3 of 4 never existed; `src.health` is a redirect being deleted | **DELETE** |

**Tests to delete: 6**

#### Category 2: Tests that import from redirect packages where canonical equivalent works → UPDATE imports

These tests currently pass through redirect packages. They test real code. Their imports must be updated to canonical paths before the redirect packages are deleted.

| Test File | Redirect Imports | Canonical Path | Currently Passing? | Action |
|-----------|-----------------|----------------|-------------------|--------|
| `test_output_policy.py` | `src.config.*` | `src.core.config.*` | Yes | **UPDATE** |
| `test_p2_sandbox.py` | `src.tools.*` | `src.core.tools.*` | Yes | **UPDATE** |
| `test_p3_observability.py` | `src.runtime.*` | `src.core.runtime.*` | Yes (1 fail) | **UPDATE** |
| `test_features_2025.py` | `src.models.*` | `src.infrastructure.models.*` | Yes | **UPDATE** |
| `test_runtime.py` | `src.runtime.*` | `src.core.runtime.*` | Yes | **UPDATE** |
| `test_sandbox.py` | `src.tools.*` | `src.core.tools.*` | Yes | **UPDATE** |
| `test_tools.py` | `src.tools.*` | `src.core.tools.*` | Yes (1 fail) | **UPDATE** |
| `unit/test_config.py` | `src.config.*` | `src.core.config.*` | Yes | **UPDATE** |

**Tests to update (import redirect): 8**

#### Category 3: Tests that fail for mixed reasons → CASE-BY-CASE

| Test File | Broken Imports | Has Skip Marker? | Action |
|-----------|---------------|-----------------|--------|
| `test_aikicad_agent.py` | `WriteBoundaryGuard` from `domains.safety` (symbol missing) | No, but has `# Skip this module` comment | **Investigate**: if symbol doesn't exist, test is dead → DELETE or add `pytestmark = skip` |
| `test_embedded_agent_regression.py` | Transitive: `component_factory.py` → `src.benchmarking` | Yes (`pytestmark = skip`) | **UPDATE**: fix the import chain so collection succeeds (skip marker will prevent execution) |
| `test_flash_tools.py` | `src.tools.flash_tools.FlashTool` (symbol not exported) + uses redirect | No | **Investigate**: if `FlashTool` doesn't exist in canonical `core.tools.flash_tools`, test is dead → DELETE |
| `test_hardware_engine.py` | `src.hardware_engine.*` (redirect) + `HardwareModels` symbol missing | No | **Investigate**: update redirect imports; if `HardwareModels` doesn't exist in canonical location, test is dead → DELETE or skip |
| `test_p4_retrieval.py` | `ChunkRecord` from `src.models` (symbol missing) | No | **Investigate**: if `ChunkRecord` exists in canonical location, update import; if not, test is dead → DELETE |
| `test_p7_hardware.py` | `src.hardware_engine.*` + `src.tools.*` (redirects) + `HardwareModels` missing | No | **UPDATE** redirect imports; if `HardwareModels` doesn't exist, DELETE |
| `test_p9_production_concepts.py` | `src.health.health_check` (redirect) + `src.infrastructure.health.health_check` | No, but has 23 skip markers on individual tests | **Investigate**: if `infrastructure.health.health_check` module exists, update import; if not, DELETE |
| `test_phase15.py` | `src.runtime.*` + `src.scheduler` (redirects) + `TaskScheduler` symbol missing | No | **UPDATE** redirect imports; if `TaskScheduler` doesn't exist in canonical `core.runtime`, DELETE or skip |
| `test_retrieval_manifest.py` | `src.retrieval.manifest` + `src.config.*` (redirect) | No | **Investigate**: if `infrastructure.retrieval.manifest` exists, update; if not, DELETE |
| `test_retrieval_search_cache.py` | `src.retrieval.search_cache` | No | **Investigate**: if `infrastructure.retrieval.search_cache` exists, update; if not, DELETE |

**Tests requiring investigation: 10** (some will be deleted, some updated)

### 3.3 Non-Broken Test Files That Use Redirects → UPDATE

8 currently-passing test files use redirect imports and will break when redirect packages are deleted. They must be updated to canonical imports BEFORE the redirects are deleted.

**Currently passing tests to update: 8** (175 individual tests across these files)

---

## 4. Implementation Strategy

### Commit Sequence (4 commits)

| # | Commit | Content | Risk | Independently Revertable |
|---|--------|---------|------|--------------------------|
| 1 | Update passing test imports | Redirect 8 currently-passing test files from `src.runtime`, `src.tools`, `src.config`, `src.models`, `src.scheduler` to canonical paths | Zero — tests keep passing | Yes |
| 2 | Fix or delete broken test files | Delete 6 dead test files. Investigate and fix or delete 10 case-by-case test files. | Low — these tests already don't run | Yes |
| 3 | Delete redirect packages + `core/events/` + orphan files | Remove Groups A, B, C source files | Medium — tests from commit 1+2 must be correct | Yes (reverts cleanly) |
| 4 | Clean stale artifacts | Delete `__pycache__` directories from PR-003 deletions | Zero | Yes |

**Critical ordering**: Commit 1 MUST land before Commit 3. If redirect packages are deleted before test imports are updated, 175 currently-passing tests will break.

---

## 5. Files That MUST NOT Be Modified

| File / Directory | Reason |
|-----------------|--------|
| `src/interfaces/server/main.py` | Production server |
| `src/core/agent/` | Production agent |
| `src/application/orchestration/tool_execution/` | Live tool execution |
| `src/application/api/app/embedded_agent.py` | Live — imported by `core/agent/autonomous_loop.py` |
| `src/application/api/app/component_factory.py` | Live — imported by `embedded_agent.py` (has pre-existing broken import of `src.benchmarking`, but fixing that is out of scope) |
| `src/domains/` | Live production code |
| `src/domain/` | Live domain layer |
| `src/infrastructure/` (except noted orphan files) | Live infrastructure |
| `src/shared/` | Live shared utilities |
| `src/schemas/` | Live API schemas |
| `src/agentic_ai/` | Live CLI entry point |
| `pyproject.toml` | No dependency changes needed |

---

## 6. Out of Scope

| Item | Reason |
|------|--------|
| Import convention unification (`src.` vs bare) | PR-009 scope. Much larger blast radius. |
| Fixing `component_factory.py` → `src.benchmarking` | Pre-existing broken import in live code. Separate investigation needed. |
| Fixing `WriteBoundaryGuard` export in `domains.safety` | Symbol-level fix in production code. Separate PR. |
| Fixing `HardwareModels` export in `domains.hardware_engine.core.models` | Symbol-level fix in production code. Separate PR. |
| Fixing 2 currently-failing tests (`test_p3_observability::test_session_and_request_id`, `test_tools::test_registry_unregister`) | Pre-existing test failures, not import errors. Separate fix. |
| Removing `asyncpg` or `langchain` from `pyproject.toml` | Dependency audit is a separate task. |
| Any new code, abstractions, or features | Deletion and import redirect only. |

---

## 7. Runtime Impact

**None.** All deleted code has zero callers from the production server. The production chat path (`main.py` → `RealAgent` → `ToolExecutionService`) is untouched.

---

## 8. API Impact

**None.** No REST endpoints, WebSocket messages, or MCP protocol changes.

---

## 9. Test Strategy

### Pre-Implementation Baseline

| Check | Method | Expected |
|-------|--------|----------|
| Collection errors | `python -m pytest tests/ -q --tb=no` | 16 errors |
| Passing tests in redirect-using files | `python -m pytest tests/test_output_policy.py tests/test_p2_sandbox.py tests/test_p3_observability.py tests/test_features_2025.py tests/test_runtime.py tests/test_sandbox.py tests/test_tools.py tests/unit/test_config.py --tb=no` | 175 passed, 2 failed |

### Post-Implementation Verification

| Check | Method | Pass Criteria |
|-------|--------|---------------|
| Server starts | `python -c "from interfaces.server.main import app"` (from `src/`) | No ImportError |
| Zero collection errors from deleted imports | `python -m pytest tests/ -q --tb=no` | 0 errors from deleted modules |
| Previously passing tests still pass | `python -m pytest tests/test_output_policy.py tests/test_p2_sandbox.py tests/test_p3_observability.py tests/test_features_2025.py tests/test_runtime.py tests/test_sandbox.py tests/test_tools.py tests/unit/test_config.py --tb=no` | >= 175 passed |
| Redirect packages gone | `python -c "import src.runtime"` | `ModuleNotFoundError` |
| `core/events/` gone | `python -c "import src.core.events"` | `ModuleNotFoundError` |
| No redirect references | `rg "Legacy alias" src/ --type py` | Zero hits |

---

## 10. Rollback Strategy

### Trigger

- Any previously passing test fails unexpectedly after import redirect
- Server fails to start
- `ToolExecutionService` import breaks
- Any file in the do-not-modify list is missing

### Procedure

1. `git revert <latest-commit>` — start with most recent
2. Verify: `python -m pytest tests/test_tools.py tests/test_sandbox.py tests/test_runtime.py --tb=no` — 175 pass
3. Verify: server starts without import errors

---

## 11. Assumption Verification

| Assumption | Verified | Method | Result |
|------------|---------|--------|--------|
| A1: All 10 redirect packages have zero production importers | **YES** | `rg "from src\.<pkg>" src/ --type py` excluding self-imports | Zero hits for all 10 |
| A2: `core/events/` has zero external production importers | **YES** | `rg "from.*core\.events" src/ --type py` | Only self-imports |
| A3: `watchdog.events` imports are 3rd-party, not `core.events` | **YES** | Read the import lines — `from watchdog.events import` | Confirmed |
| A4: `api_server.py` has zero external importers | **YES** | `rg "api_server" src/ tests/` excluding self | Zero hits |
| A5: `chat_endpoints.py` only imported by `api_server.py` | **YES** | `rg "chat_endpoints" src/` | Only `api_server.py` |
| A6: `dashboard_websocket.py` has zero importers | **YES** | `rg "dashboard_websocket" src/ tests/` | Zero hits |
| A7: 175 tests pass through redirect packages | **YES** | Ran pytest on 8 test files | 175 passed, 2 failed (pre-existing) |
| A8: Redirect packages are explicitly labeled "Legacy alias" | **YES** | Read `__init__.py` docstrings | All say "Legacy alias" |

---

## STOP

**READY TO PREPARE PR-004 IMPLEMENTATION**
