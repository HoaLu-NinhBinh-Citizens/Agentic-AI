# PR-004 Final Scope (Post-Review)

> **Date**: 2026-06-14
> **Status**: APPROVED — no blockers
> **Based on**: Independent design review against source code at commit `a2042cb`

---

## IN SCOPE (verified)

### Deletions

| Item | Files | Verified |
|------|-------|----------|
| `src/runtime/` + `src/runtime.py` | 4 | Zero production importers confirmed |
| `src/tools/` | 9 | Zero production importers confirmed |
| `src/hardware_engine/` + `src/hardware_engine.py` | 18 | Zero production importers confirmed |
| `src/config/` (3 files after relocating `ai_support_config.py`) | 3 | Zero production importers confirmed |
| `src/health/` | 2 | Zero production importers confirmed |
| `src/llm/` | 2 | Zero production importers confirmed |
| `src/models/` + `src/models.py` | 3 | Zero production importers confirmed |
| `src/parsing/` | 2 | Zero production importers confirmed |
| `src/security/` | 1 | Zero importers confirmed (stub, not a redirect — no `__init__.py`) |
| `src/scheduler/` + `src/scheduler.py` | 2 | Zero production importers confirmed |
| `src/core/events/` | 6 | Zero external importers confirmed |
| `src/application/api/app/chat_endpoints.py` | 1 | Only imported by `api_server.py` (also deleted) |
| `src/application/api/app/api_server.py` | 1 | Zero external importers confirmed |
| `src/application/api/app/dashboard_websocket.py` | 1 | Zero importers confirmed |
| Stale `__pycache__` dirs (3 trees) | ~33 `.pyc` | Confirmed present |

### Move

| From | To | Reason |
|------|----|--------|
| `src/config/ai_support_config.py` | `src/core/config/ai_support_config.py` | Original code inside redirect package |

### Test File Deletions (verified dead)

| File | Reason |
|------|--------|
| `tests/test_events.py` | Imports from `src.events.*` (deleted redirect); `core/events/` also being deleted |
| `tests/test_hardware.py` | Imports from `src.hardware` (never existed) |
| `tests/test_learning.py` | Imports from `src.learning` (never existed) |
| `tests/test_observability.py` | Imports from `src.observability` (never existed) |
| `tests/test_phase4.py` | Imports from `src.introspection`, `src.healing`, `src.metrics` (none exist) |
| `tests/test_p9_production_concepts.py` | Imports `HealthStatus`, `HealthCheckResult`, `HealthChecks` — none exist at redirect target |

### Test File Updates (verified redirect → canonical)

| File | Redirect | Canonical |
|------|----------|-----------|
| `tests/test_output_policy.py` | `src.config.output_policy` | `src.core.config.output_policy` |
| `tests/test_p2_sandbox.py` | `src.tools.sandbox` | `src.core.tools.sandbox` |
| `tests/test_p3_observability.py` | `src.runtime.*` | `src.core.runtime.*` |
| `tests/test_runtime.py` | `src.runtime.*` | `src.core.runtime.*` |
| `tests/test_sandbox.py` | `src.tools.*` | `src.core.tools.*` |
| `tests/test_tools.py` | `src.tools.*` | `src.core.tools.*` |
| `tests/unit/test_config.py` | `src.config.ai_support_config` | `src.core.config.ai_support_config` |
| `tests/test_flash_tools.py` | `src.tools.*` | `src.core.tools.*` |
| `tests/test_hardware_engine.py` | `src.hardware_engine.*` | `src.domains.hardware_engine.*` |
| `tests/test_p4_retrieval.py` | `src.models` | `src.infrastructure.models` |
| `tests/test_p7_hardware.py` | `src.hardware_engine.*` + `src.tools.*` | `src.domains.hardware_engine.*` + `src.core.tools.*` |
| `tests/test_retrieval_manifest.py` | `src.retrieval.*` + `src.config.*` | `src.infrastructure.retrieval.*` + `src.core.config.*` |
| `tests/test_retrieval_search_cache.py` | `src.retrieval.*` | `src.infrastructure.retrieval.*` |

### Test Files Requiring Investigation During Implementation

| File | Issue | Fallback |
|------|-------|----------|
| `tests/test_features_2025.py` | Line 114 imports `User` from `src.models` — verify `User` exists in `infrastructure.models` | If missing, delete that test class |
| `tests/test_p5_memory.py` | Imports `src.memory.advanced_memory` — canonical `src/core/memory/advanced_memory.py` exists | Try UPDATE to `src.core.memory.advanced_memory`; if fails, DELETE |
| `tests/test_phase15.py` | Imports ~20 symbols from `src.runtime` + `src.scheduler` — not all may be exported | Try UPDATE; DELETE if too many missing symbols |
| `tests/test_aikicad_agent.py` | Has `pytest.skip()` at module level; `WriteBoundaryGuard` missing from `domains.safety` | Verify it doesn't cause collection error; if it does, add `pytestmark` |
| `tests/test_embedded_agent_regression.py` | Has `pytestmark = pytest.mark.skip`; transitive `src.benchmarking` import | Verify collection succeeds with skip marker |

---

## OUT OF SCOPE (unchanged)

| Item | Reason |
|------|--------|
| Import convention unification (`src.` vs bare) | PR-009 — different blast radius |
| Fixing `component_factory.py` → `src.benchmarking` | Pre-existing bug in live code |
| Fixing `WriteBoundaryGuard` export in `domains.safety` | Production code symbol fix |
| Fixing `HardwareModels` export | Production code symbol fix |
| Fixing 2 pre-existing test failures | Logic bugs, not import errors |
| `pyproject.toml` dependency changes | Separate audit |
| Any new files or abstractions | Deletion + redirect only |

## MUST NOT TOUCH (unchanged, verified)

| File / Directory | Verified No Deleted-Package Imports |
|-----------------|--------------------------------------|
| `src/interfaces/server/main.py` | Yes |
| `src/core/agent/` | Yes |
| `src/application/orchestration/tool_execution/` | Yes |
| `src/application/api/app/embedded_agent.py` | Yes |
| `src/application/api/app/component_factory.py` | Yes |
| `src/domains/` (source) | Yes |
| `src/domain/` | Yes |
| `src/infrastructure/` (except orphan files) | Yes |
| `src/shared/` | Yes |
| `src/schemas/` | Yes |
| `src/agentic_ai/` | Yes |
| `pyproject.toml` | N/A |

---

## Commit Sequence (unchanged, verified safe)

| # | Commit | Content |
|---|--------|---------|
| 1 | `fix(tests): relocate ai_support_config and redirect test imports to canonical paths` | Move `ai_support_config.py` + update ~8 passing test imports |
| 2 | `fix(tests): delete dead test files and fix broken test imports` | Delete 6 dead tests + investigate/fix 10 case-by-case tests |
| 3 | `fix(dead-code): delete redirect packages, core/events, and orphan files` | Delete ~57 source files |
| 4 | `chore(cleanup): remove stale __pycache__ from PR-003 deletions` | Clean 3 directory trees |

**Critical ordering verified**: Commit 1 before Commit 3. Rollback is commit-by-commit safe.
