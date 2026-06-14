# PR-004 Implementation Plan

> **Date**: 2026-06-14
> **PR**: PR-004 — Delete Remaining Dead Code and Fix Broken Test Suite
> **Status**: AWAITING APPROVAL — no code has been modified

---

## Assumption Verification Results

All 8 design assumptions re-verified against current source code on commit `a2042cb`.

| # | Assumption | Verified | Method | Result |
|---|-----------|----------|--------|--------|
| A1 | All 10 redirect packages have zero production importers | **YES** | `rg "from src\.(runtime\|tools\|...)" src/ --type py` excluding self | Only self-imports within redirect packages |
| A2 | `core/events/` has zero external production importers | **YES** | `rg "from.*core\.events" src/ --type py` | Only self-imports within `core/events/` |
| A3 | `api_server.py` has zero external importers | **YES** | `rg "api_server" src/` | Only `chat_endpoints.py` → `api_server.py` (both orphan) |
| A4 | `chat_endpoints.py` only imported by `api_server.py` | **YES** | `rg "chat_endpoints" src/` | Confirmed |
| A5 | `dashboard_websocket.py` has zero importers | **YES** | `rg "dashboard_websocket"` | Zero matches in entire repo |
| A6 | Redirect packages are labeled "Legacy alias" | **YES** | `rg "Legacy alias" src/ --type py` | 36 hits, all in redirect packages (plus 2 unrelated in `ab_partition.py`) |
| A7 | Canonical modules exist for all redirect targets | **YES** | Glob + Read for each canonical path | All verified — see deviation D1 below |
| A8 | Stale `__pycache__` exists in deleted package dirs | **YES** | `find` for `.pyc` files | 12+ stale `.pyc` files in `core/multi_agent/`, `core/orchestration/`, `multi_agent/` |

### Deviations from Design Document

**D1: `src/config/ai_support_config.py` is original code, not a redirect.**

The design doc lists `src/config/` as a pure redirect package (4 files). Verification reveals:

- `src/config/__init__.py` — redirect (imports from `core.config.output_policy` + `config.ai_support_config`)
- `src/config/output_policy.py` — redirect to `core.config.output_policy`
- `src/config/agent_prompts.py` — **broken redirect** (imports from itself — circular)
- `src/config/ai_support_config.py` — **ORIGINAL CODE** (123 LOC, contains `AISupportConfig`, `RuleConfig`, `MLRuleConfig`, `IndexingConfig`, `OutputConfig`)

`AISupportConfig` has **zero production importers** outside the `src/config/` package itself. The only external consumer is `tests/unit/test_config.py`.

**Resolution**: `src/config/ai_support_config.py` must be **relocated** to `src/core/config/ai_support_config.py` before the `src/config/` redirect package can be deleted. This is a mechanical move + import update, consistent with PR-004's "redirect to canonical" pattern.

**D2: `src/security/tool_permissions.py` is a stub, not a redirect.**

The design doc lists `src/security/` as a redirect with 1 file. Verification reveals it's a Phase 2B stub (not labeled "Legacy alias") with zero importers. Safe to delete — same outcome, different reason.

**D3: `src/retrieval/` does NOT exist as a redirect package.**

Two test files (`test_retrieval_manifest.py`, `test_retrieval_search_cache.py`) import from `src.retrieval.*`, but there is no `src/retrieval/` package. These imports resolve because `src/infrastructure/retrieval/` exists and Python path manipulation in the tests adds `src/` to `sys.path`, making `from src.retrieval.manifest` ambiguous. These tests must be updated to use `from src.infrastructure.retrieval.manifest` or `from infrastructure.retrieval.manifest`.

---

## Implementation Sequence

### Pre-flight checks (before any code changes)

```bash
# From src/ directory:
python -c "from interfaces.server.main import app"          # Must succeed
python -m pytest tests/ -q --tb=no 2>&1 | tail -1           # Baseline: 16 errors
```

---

### Commit 1: Relocate `ai_support_config.py` and update passing test imports

**Goal**: Move the one original file out of redirect packages, then update all passing test imports from redirect paths to canonical paths.

**Step 1a**: Move `src/config/ai_support_config.py` to `src/core/config/ai_support_config.py`

**Step 1b**: Update `tests/unit/test_config.py`:
- `from src.config.ai_support_config import ...` → `from src.core.config.ai_support_config import ...`

**Step 1c**: Update 8 passing test files (redirect → canonical imports):

| Test File | Old Import | New Import |
|-----------|-----------|------------|
| `tests/test_output_policy.py` | `from src.config.output_policy import OutputPolicy` | `from src.core.config.output_policy import OutputPolicy` |
| `tests/test_p2_sandbox.py` | `from src.tools.sandbox import ...` | `from src.core.tools.sandbox import ...` |
| `tests/test_p3_observability.py` | `from src.runtime.journal import ...` / `from src.runtime.replayer import ...` | `from src.core.runtime.journal import ...` / `from src.core.runtime.replayer import ...` |
| `tests/test_features_2025.py` | `from src.models import User` | `from src.infrastructure.models import User` (if User exists) or remove import if unused |
| `tests/test_runtime.py` | `from src.runtime import ...` | `from src.core.runtime import ...` |
| `tests/test_sandbox.py` | `from src.tools.sandbox import ...` / `from src.tools.audit import ...` / etc. | `from src.core.tools.sandbox import ...` / `from src.core.tools.audit import ...` / etc. |
| `tests/test_tools.py` | `from src.tools.schema import ...` / `from src.tools.registry import ...` / etc. | `from src.core.tools.schema import ...` / `from src.core.tools.registry import ...` / etc. |
| `tests/unit/test_config.py` | `from src.config.ai_support_config import ...` | `from src.core.config.ai_support_config import ...` |

**Verification after Commit 1**:
```bash
python -m pytest tests/test_output_policy.py tests/test_p2_sandbox.py tests/test_p3_observability.py tests/test_features_2025.py tests/test_runtime.py tests/test_sandbox.py tests/test_tools.py tests/unit/test_config.py --tb=short
# Expected: >= 175 passed, 2 failed (pre-existing)
```

---

### Commit 2: Fix or delete broken test files

**Goal**: Resolve all 16 test collection errors.

#### Category 1 — DELETE (6 files):

| File | Reason |
|------|--------|
| `tests/test_events.py` | Imports from `src.events` (deleted redirect) testing dead `core/events/` |
| `tests/test_hardware.py` | Imports from `src.hardware` (never existed) |
| `tests/test_learning.py` | Imports from `src.learning` (never existed) |
| `tests/test_observability.py` | Imports from `src.observability` (never existed) |
| `tests/test_p5_memory.py` | Imports from `src.memory.advanced_memory` (never existed) |
| `tests/test_phase4.py` | Imports from `src.introspection`, `src.healing`, `src.metrics` (none exist) |

#### Category 3 — INVESTIGATE and resolve (10 files):

| File | Issue | Resolution |
|------|-------|------------|
| `tests/test_aikicad_agent.py` | `WriteBoundaryGuard` doesn't exist in `domains.safety` | Already has `pytest.skip()` at line 26. Collects but skips. **If it still causes collection error**: add `pytestmark = pytest.mark.skip` before imports. **If it collects fine**: leave as-is (out of scope). |
| `tests/test_embedded_agent_regression.py` | Transitive import from `component_factory.py` → `src.benchmarking` | Already has `pytestmark = pytest.mark.skip`. **If collection error persists**: the skip marker should prevent it. Verify. |
| `tests/test_flash_tools.py` | `from src.tools.flash_tools import ...` (redirect) | **UPDATE**: `from src.core.tools.flash_tools import FlashPermissionGuard, FlashConfig, ...` + `from src.core.tools.schema import ToolPermission, ToolCategory` |
| `tests/test_hardware_engine.py` | `from src.hardware_engine import ...` (redirect) + `from src.hardware_engine.core.models import ...` | **UPDATE**: All imports from `src.hardware_engine.*` → `src.domains.hardware_engine.*` |
| `tests/test_p4_retrieval.py` | `from src.models import ChunkRecord` | **UPDATE**: `from src.infrastructure.models import ChunkRecord` (verified: `ChunkRecord` exists in `infrastructure/models/retrieval.py`) |
| `tests/test_p7_hardware.py` | `from src.hardware_engine.core.models import ...` + `from src.tools.flash_tools import ...` | **UPDATE**: `src.hardware_engine.*` → `src.domains.hardware_engine.*`, `src.tools.*` → `src.core.tools.*` |
| `tests/test_p9_production_concepts.py` | `from src.health.health_check import HealthCheck, HealthStatus, HealthCheckResult, HealthChecks` | `HealthStatus`, `HealthCheckResult`, `HealthChecks` don't exist anywhere. Redirect target `infrastructure.health.health_check` doesn't exist. **DELETE** — tests dead symbols. |
| `tests/test_phase15.py` | `from src.runtime import ...` + `from src.scheduler import Priority` | **UPDATE**: `src.runtime` → `src.core.runtime`, `src.scheduler` → `src.core.scheduler` |
| `tests/test_retrieval_manifest.py` | `from src.retrieval.manifest import IndexManifest` + `from src.config.agent_prompts import RAG_SCHEMA_VERSION` | **UPDATE**: `src.retrieval.manifest` → `src.infrastructure.retrieval.manifest`, `src.config.agent_prompts` → `src.core.config.agent_prompts` |
| `tests/test_retrieval_search_cache.py` | `from src.retrieval.search_cache import SearchCache` | **UPDATE**: `src.retrieval.search_cache` → `src.infrastructure.retrieval.search_cache` |

**Verification after Commit 2**:
```bash
python -m pytest tests/ -q --tb=no 2>&1 | tail -1
# Expected: 0-4 collection errors (down from 16)
# Remaining errors would be from pre-existing symbol mismatches in production code (WriteBoundaryGuard, etc.)
```

---

### Commit 3: Delete redirect packages + `core/events/` + orphan files

**Goal**: Remove all dead source code.

#### Group A — Redirect packages (delete entire directories + top-level files):

| Path | Files |
|------|-------|
| `src/runtime/` (directory) | `__init__.py`, `journal.py`, `replayer.py` |
| `src/runtime.py` (file) | 1 |
| `src/tools/` (directory) | `__init__.py`, `audit.py`, `cache.py`, `context.py`, `executor.py`, `flash_tools.py`, `registry.py`, `sandbox.py`, `schema.py` |
| `src/hardware_engine/` (directory) | 17 files across `core/`, `engine/`, `validator/`, `codegen/`, `integration/` subdirs |
| `src/hardware_engine.py` (file) | 1 |
| `src/config/` (directory) | `__init__.py`, `output_policy.py`, `agent_prompts.py` (3 files — `ai_support_config.py` was relocated in Commit 1) |
| `src/health/` (directory) | `__init__.py`, `health_check.py` |
| `src/llm/` (directory) | `__init__.py`, `ollama.py` |
| `src/models/` (directory) | `__init__.py`, `build.py` |
| `src/models.py` (file) | 1 |
| `src/parsing/` (directory) | `__init__.py`, `response_parser.py` |
| `src/security/` (directory) | `tool_permissions.py` |
| `src/scheduler/` (directory) | `__init__.py` |
| `src/scheduler.py` (file) | 1 |

**Total Group A**: ~48 files

#### Group B — Dead subsystem:

| Path | Files |
|------|-------|
| `src/core/events/` (directory) | `__init__.py`, `emitter.py`, `event.py`, `handlers.py`, `middleware.py`, `types.py` |

**Total Group B**: 6 files

#### Group C — Orphan files:

| Path | Reason |
|------|--------|
| `src/application/api/app/chat_endpoints.py` | Imports deleted `core.multi_agent.agent` |
| `src/application/api/app/api_server.py` | Only importer of `chat_endpoints.py` |
| `src/application/api/app/dashboard_websocket.py` | Zero importers |

**Total Group C**: 3 files

**Verification after Commit 3**:
```bash
python -c "from interfaces.server.main import app"    # Must succeed
python -c "import src.runtime" 2>&1                     # Must fail: ModuleNotFoundError
rg "Legacy alias" src/ --type py                        # Must return 0 hits (excluding ab_partition.py)
python -m pytest tests/ -q --tb=no                      # Errors must not increase
```

---

### Commit 4: Clean stale artifacts

**Goal**: Remove leftover `__pycache__` directories from PR-003 deletions.

| Path | Contents |
|------|----------|
| `src/core/multi_agent/` | Empty dir + `coordination/__pycache__/` (26+ `.pyc` files) |
| `src/core/orchestration/` | Empty dir + `__pycache__/` (5 `.pyc` files) |
| `src/multi_agent/` | Empty dir + `__pycache__/` (2 `.pyc` files) |

**Action**: `rm -rf` each directory (they contain only stale `.pyc` and empty `__init__`-less dirs).

**Verification after Commit 4**:
```bash
find src/core/multi_agent src/core/orchestration src/multi_agent -name "*.pyc" 2>/dev/null
# Must return empty
```

---

## Commit Messages

```
Commit 1: fix(tests): relocate ai_support_config and redirect test imports to canonical paths
Commit 2: fix(tests): delete dead test files and fix broken test imports
Commit 3: fix(dead-code): delete redirect packages, core/events, and orphan files
Commit 4: chore(cleanup): remove stale __pycache__ from PR-003 deletions
```

---

## Do Not Modify

| File / Directory | Reason |
|-----------------|--------|
| `src/interfaces/server/main.py` | Production server |
| `src/core/agent/` | Production agent |
| `src/application/orchestration/tool_execution/` | Live tool execution |
| `src/application/api/app/embedded_agent.py` | Live — imported by `core/agent/autonomous_loop.py` |
| `src/application/api/app/component_factory.py` | Live (pre-existing `src.benchmarking` bug — out of scope) |
| `src/domains/` | Live production code |
| `src/domain/` | Live domain layer |
| `src/infrastructure/` (except orphan files listed in Group C) | Live infrastructure |
| `src/shared/` | Live shared utilities |
| `src/schemas/` | Live API schemas |
| `src/agentic_ai/` | Live CLI entry point |
| `pyproject.toml` | No dependency changes |

---

## Risk Mitigations

| Risk | Mitigation |
|------|-----------|
| R1: Redirect has production importer | Verified by grep — zero external hits for all 10 packages |
| R2: Test import points to wrong canonical | Follow each redirect's own `__init__.py` mapping; run test after update |
| R5: Commit ordering mistake | Strict sequence: Commit 1 (update imports) before Commit 3 (delete source) |
| D1: `ai_support_config.py` is not a redirect | Relocate to `core/config/` in Commit 1 before deleting `src/config/` |

---

## Estimated Effort

| Phase | Time |
|-------|------|
| Commit 1 (relocate + test imports) | 30-45 min |
| Commit 2 (broken test resolution) | 45-60 min |
| Commit 3 (delete source) | 15-20 min |
| Commit 4 (clean artifacts) | 5 min |
| Verification | 15-20 min |
| **Total** | **~2 hours** |
