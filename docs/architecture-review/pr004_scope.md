# PR-004 Scope Definition

> **Date**: 2026-06-14
> **PR**: PR-004 — Delete Remaining Dead Code and Fix Broken Test Suite

---

## IN SCOPE

| Item | Type | Reason |
|------|------|--------|
| Delete `src/runtime/` (3 files) | Deletion | Legacy redirect, zero production importers |
| Delete `src/tools/` (9 files) | Deletion | Legacy redirect, zero production importers |
| Delete `src/hardware_engine/` (17 files) | Deletion | Legacy redirect, zero production importers |
| Delete `src/config/` (4 files) | Deletion | Legacy redirect, zero production importers |
| Delete `src/health/` (2 files) | Deletion | Legacy redirect, zero production importers |
| Delete `src/llm/` (2 files) | Deletion | Legacy redirect, zero production importers |
| Delete `src/models/` (2 files) | Deletion | Legacy redirect, zero production importers |
| Delete `src/parsing/` (2 files) | Deletion | Legacy redirect, zero production importers |
| Delete `src/security/` (1 file) | Deletion | Legacy redirect, zero production importers |
| Delete `src/scheduler/` (1 file) | Deletion | Legacy redirect, zero production importers |
| Delete `src/core/events/` (6 files) | Deletion | Dead subsystem, zero production importers |
| Delete `src/application/api/app/chat_endpoints.py` | Deletion | Orphan, imports from deleted module |
| Delete `src/application/api/app/api_server.py` | Deletion | Orphan FastAPI app, not production server |
| Delete `src/application/api/app/dashboard_websocket.py` | Deletion | Zero importers |
| Delete stale `__pycache__/` in `core/multi_agent/`, `core/orchestration/`, `multi_agent/` | Cleanup | Leftover from PR-003 |
| Update 8 passing test files: redirect → canonical imports | Import fix | Required before redirect deletion |
| Delete 6 dead test files (`test_events`, `test_hardware`, `test_learning`, `test_observability`, `test_p5_memory`, `test_phase4`) | Deletion | Import from non-existent modules |
| Investigate and fix/delete 10 case-by-case test files | Fix or delete | Must resolve collection errors |

---

## OUT OF SCOPE

| Item | Reason | When |
|------|--------|------|
| Import convention unification (`src.` prefix vs bare imports) | Much larger blast radius (~749 import lines). Different risk profile. | PR-009 |
| Fixing `component_factory.py` → `src.benchmarking` broken import | Live production file. Requires investigation of what `benchmarking` should resolve to. | Separate PR |
| Fixing `WriteBoundaryGuard` export in `domains/safety/__init__.py` | Production code symbol fix. Requires understanding whether symbol was renamed or never implemented. | Separate PR |
| Fixing `HardwareModels` export in `domains/hardware_engine/core/models.py` | Production code symbol fix. | Separate PR |
| Fixing 2 pre-existing test failures (`test_p3_observability::test_session_and_request_id`, `test_tools::test_registry_unregister`) | Logic bugs in tests, not import errors. | Separate PR |
| Removing `asyncpg` from `pyproject.toml` | Dependency audit. `asyncpg` is declared but likely unused in production path. Needs verification. | Separate PR |
| Removing `langchain` from `pyproject.toml` | May still be used by infrastructure code. Needs grep + verification. | Separate PR |
| Any new abstractions or wrappers | This PR is deletion-only + mechanical import redirect. | Never in this PR |
| Any changes to `pyproject.toml` dependencies | No packages are being removed. | N/A |
| Regenerating `egg-info` | Happens automatically on next `pip install -e .` | Automatic |

---

## EXPLICITLY FORBIDDEN

| Item | Reason |
|------|--------|
| Modifying `src/interfaces/server/main.py` | Production server. No dead imports from target packages. |
| Modifying `src/core/agent/` | Production agent code. |
| Modifying `src/application/orchestration/tool_execution/` | Live tool execution service. |
| Modifying `src/application/api/app/embedded_agent.py` | Live — imported by autonomous loop. |
| Modifying `src/domains/` source code | Live production code. Tests may be deleted/updated, but source must not change. |
| Modifying `src/domain/` source code | Live domain layer. |
| Modifying `src/infrastructure/` source code | Live infrastructure. Only allowed: delete explicitly orphan files listed above. |
| Modifying `src/shared/` | Live shared utilities. |
| Modifying `pyproject.toml` | No dependency changes in this PR. |
| Adding any new Python files | Deletion and import redirect only. |
| Adding skip markers as a fix for broken tests | If a test can't be fixed by import redirect, it must be deleted, not skipped. Exception: tests that already have skip markers (e.g., `test_embedded_agent_regression.py`). |
| Creating any new redirect or compatibility layer | The goal is to eliminate redirects, not create new ones. |

---

## Scope Creep Risks

| Risk | Trigger | Mitigation |
|------|---------|------------|
| "While I'm here, let me also fix `component_factory.py`" | Touching `application/api/app/` | `component_factory.py` is LIVE code with a pre-existing bug. Do not touch. |
| "Let me also update the import convention to bare imports" | Updating test imports from `src.tools` → `src.core.tools` | Only change the package path. Do not change the prefix convention (`src.` vs bare). |
| "Let me clean up the `domains/safety/__init__.py` exports" | Investigating `test_aikicad_agent.py` failure | If the symbol doesn't exist, delete the test. Do not modify production code to add exports. |
| "Let me also remove unused dependencies" | Seeing `langchain` in `pyproject.toml` | Dependency audit is a separate PR. Do not touch `pyproject.toml`. |
| "Let me fix the 2 failing tests too" | Seeing `test_p3_observability` and `test_tools` failures | Pre-existing logic bugs. Out of scope. |
| "Let me delete more orphan files in `application/api/app/`" | Looking at `dashboard_api.py`, `migrator.py`, etc. | Only delete files explicitly listed in scope (3 files). Others need investigation first. |
