# PR-002 Revision — Invalidated Assumptions & Corrected Scope

> **Document type**: Revision — no code modified.
> **Date**: 2026-06-13
> **Author**: Principal Engineer review
> **Status**: APPROVED FOR IMPLEMENTATION
> **Supersedes**: `pr002_design.md` sections 3, 5, 6, 7, 8, 9

---

## 1. Invalidated Assumptions

Every assumption below was stated in `pr002_design.md` and contradicted by source code audit.

### A1. File counts are wrong across all Tier 2 packages

| Package | PR002 Claimed | Actual | Delta |
|---------|--------------|--------|-------|
| `src/app/` | 8 files | 4 files | -4 |
| `src/agent/` | 10 files | 5 files | -5 |
| `src/infrastructure/distributed/` | 15 files | 8 files | -7 |
| `src/infrastructure/fleet/` | 3 files | 1 file | -2 |
| `src/infrastructure/chaos/` | 3 files | 1 file | -2 |
| `src/core/checkpoint/` | 9 files | 5 files | -4 |
| **Tier 2 total** | **48 files** | **24 files** | **-24** |

**Impact**: Total deletion count drops from 59 to 35. Percentage drops from ~3.9% to ~2.3%.

### A2. `tests/test_aikicad_agent.py` does NOT import exclusively from dead modules

PR002 lists this test for deletion because it imports from `src.app`. Reality: it imports from **14 modules in `src.domains/`** (live code) plus `src.multi_agent.pdf_knowledge_agent` (live code). Deleting it removes test coverage for live production code.

Imports from live packages:
- `src.domains.eda.kicad` (4 symbols)
- `src.domains.firmware` (4 symbols)
- `src.domains.knowledge` (2 symbols)
- `src.domains.runtime` (1 symbol)
- `src.domains.knowledge.ocr` (1 symbol)
- `src.domains.autonomy` (1 symbol) + 4 sub-modules
- `src.domains.safety` (1 symbol)
- `src.domains.schema_validator` (1 symbol)
- `src.domains.validation` (1 symbol)
- `src.multi_agent.pdf_knowledge_agent` (1 symbol)

### A3. `tests/test_embedded_agent_regression.py` imports from live modules beyond `src.app`

PR002 lists this for deletion. Reality: also imports from `src.config.agent_prompts`, `src.llm.ollama`, `src.models`, `src.parsing.response_parser` — all live.

### A4. `tests/test_agent_control_flow.py` imports from live modules beyond `src.agent`

Also imports from `src.models.build` and `src.models` — live code.

### A5. `tests/test_agent_executor.py` imports from live modules beyond `src.agent`

Also imports from `src.models` and `src.models.build` — live code.

### A6. `tests/test_p9_production_runtime.py` imports from non-existent modules

Imports `src.app.api_state` and `src.app.api_models` — these files do **not exist** in `src/app/`. Also imports `src.health.health_check`. This test is already broken; deletion is safe but the reason is different from what PR002 states.

### A7. `tests/test_chaos.py` imports from `src.chaos`, not `src.infrastructure.chaos`

PR002 claims it imports from `src.infrastructure.chaos`. Reality: it imports from `src.chaos` (which does not exist — `src/chaos/` not found). This test is already broken.

### A8. `tests/integration/production_test.py` imports from many live modules

PR002 flagged this for verification. Result: it imports from **9 distinct live packages** including `src.core.agent`, `src.core.multi_agent`, `src.core.session`, `src.infrastructure.hardware`, `src.domain.hardware`, `src.infrastructure.resilience`, `src.infrastructure.vector_db`, `src.core.runtime`. Only **one** import is from a dead module (`src.core.checkpoint.snapshot`). This test must NOT be deleted. The single dead import must be removed.

---

## 2. Revised Delete Candidates

### Tier 1: Zero Importers (unchanged, confirmed)

| Target | File Count | Confidence |
|--------|-----------|------------|
| `src/infrastructure/sharding/` | 1 | High — verified zero importers |
| `src/core/health/` | 4 (empty `__init__.py` stubs) | High — real health impl is in `src/infrastructure/observability/health` |
| `src/core/execution/worker_pool/` | 1 | High — verified zero importers |
| `src/core/execution/executor/` | 1 | High — verified zero importers |
| `src/core/execution/task_queue/` | 1 | High — verified zero importers |

**Tier 1 total: 8 files** (was 11 — health/ has 4 files not 7).

### Tier 2: Test-Only Importers (revised)

| Target | Actual File Count | External Test Importers | Production Importers | Confidence |
|--------|----------|------------------------|---------------------|------------|
| `src/app/` | 4 | 6 test files (but see A2, A3) | None (self-redirects only) | High |
| `src/agent/` | 5 | 2 test files (but see A4, A5) | None | High |
| `src/infrastructure/distributed/` | 8 | 3 test files | None (self-imports only) | High |
| `src/infrastructure/fleet/` | 1 | 1 test file | None | High |
| `src/infrastructure/chaos/` | 1 | 1 test file | None | High |
| `src/core/checkpoint/` | 5 | 1 test file (mixed — see A8) | None | High |

**Tier 2 total: 24 files** (was 48).

### Test Files: Revised Actions

| Test File | PR002 Action | Revised Action | Reason |
|-----------|-------------|----------------|--------|
| `tests/test_aikicad_agent.py` | Delete | **UPDATE** — remove `src.app` imports, keep file | Imports 14 live `src.domains` modules |
| `tests/test_api_server.py` | Delete | Delete | Only imports from `src.app` |
| `tests/test_dashboard_e2e.py` | Delete | Delete | Only imports from `src.app` |
| `tests/test_embedded_agent_bootstrap.py` | Delete | Delete | Only imports from `src.app` |
| `tests/test_embedded_agent_regression.py` | Delete | **UPDATE** — remove `src.app` import, keep file | Also imports `src.config`, `src.llm`, `src.models`, `src.parsing` |
| `tests/test_p9_production_runtime.py` | Delete | Delete | Already broken — imports non-existent `src.app.api_state`, `src.app.api_models` |
| `tests/test_agent_control_flow.py` | Delete | **UPDATE** — remove `src.agent` imports, keep file | Also imports `src.models`, `src.models.build` |
| `tests/test_agent_executor.py` | Delete | **UPDATE** — remove `src.agent` import, keep file | Also imports `src.models`, `src.models.build` |
| `tests/test_phase5.py` | Delete | Delete | Only imports from `src.infrastructure.distributed` |
| `tests/test_p6_distributed.py` | Delete | Delete | Only imports from `src.infrastructure.distributed` |
| `tests/test_redis_bus.py` | Delete | Delete | Only imports from `src.infrastructure.distributed` |
| `tests/unit/test_predictive_failure.py` | Delete | Delete | Only imports from `src.infrastructure.fleet` |
| `tests/unit/test_chaos_engineering.py` | Delete | Delete | Only imports from `src.infrastructure.chaos` |
| `tests/test_chaos.py` | Delete | Delete | Already broken — imports non-existent `src.chaos` |
| `tests/integration/production_test.py` | Verify first | **UPDATE** — remove `src.core.checkpoint.snapshot` import, keep file | Imports 9 live packages |

**Tests to delete: 9** (was ~15).
**Tests to update (remove dead imports, keep file): 4.**
**Tests already broken (delete as cleanup): 2** (test_p9, test_chaos).

---

## 3. Do-Not-Delete List

| File / Directory | Reason | Evidence |
|-----------------|--------|----------|
| `src/domains/` | **LIVE** — 49 production importers | `src/hardware_engine/`, `src/core/agent/`, `src/application/`, `src/infrastructure/mcp/` |
| `src/infrastructure/hsm/` | **LIVE** — domain layer depends on it | `src/domain/hardware/flash/ab_partition.py`, `src/domain/ports/hardware_security.py` |
| `src/infrastructure/performance/rust/` | **UNCLEAR** — defer | Optional Rust acceleration; `rust_bridge.py` has graceful fallback |
| `tests/test_aikicad_agent.py` | **LIVE TEST** — covers `src.domains` | 14 live domain imports |
| `tests/test_embedded_agent_regression.py` | **LIVE TEST** — covers `src.config`, `src.llm`, `src.models` | 4 live module imports beyond `src.app` |
| `tests/test_agent_control_flow.py` | **LIVE TEST** — covers `src.models` | Imports `src.models.build`, `src.models` |
| `tests/test_agent_executor.py` | **LIVE TEST** — covers `src.models` | Imports `src.models`, `src.models.build` |
| `tests/integration/production_test.py` | **LIVE TEST** — covers 9 production packages | Core agent, multi-agent, session, hardware, resilience, vector_db |
| `src/core/orchestration/` | PR-003 scope | — |
| `src/core/multi_agent/` | PR-003 scope | — |
| `src/core/events/` | PR-004 scope | — |
| All live infrastructure | Production code | `retrieval/`, `mcp/`, `indexing/`, `completion/`, `llm/`, `embeddings/` |
| `src/domain/` | Live domain layer | — |
| `src/application/` | Live application layer | — |

---

## 4. Revised Scope

### Deletions: 32 source files + 11 test files

| Category | Files | Tests Deleted | Tests Updated |
|----------|-------|---------------|---------------|
| Tier 1 (zero importers) | 8 | 0 | 0 |
| Tier 2 (test-only) | 24 | 9 | 4 |
| Broken tests (cleanup) | 0 | 2 | 0 |
| **Total** | **32** | **11** | **4** |

**Percentage of codebase**: 32 / 1509 = ~2.1%

### Modifications: 4 test files + up to 3 `__init__.py` files

Test files requiring update (remove dead imports only):
1. `tests/test_aikicad_agent.py` — remove `src.app` imports
2. `tests/test_embedded_agent_regression.py` — remove `src.app` import
3. `tests/test_agent_control_flow.py` — remove `src.agent` imports
4. `tests/test_agent_executor.py` — remove `src.agent` import
5. `tests/integration/production_test.py` — remove `src.core.checkpoint.snapshot` import

**PRECONDITION**: After removing dead imports from these test files, verify remaining test logic still makes sense. If a test function depends entirely on the removed import, delete that function but keep the file.

---

## 5. Revised Success Criteria

| Criterion | Metric |
|-----------|--------|
| All confirmed-dead packages deleted | 8 Tier 1 + 24 Tier 2 = 32 source files removed |
| Server starts without import errors | `from interfaces.server.main import app` succeeds |
| All production workflows unaffected | Chat, tools, indexing, completion unchanged |
| Test suite improved | Error count reduced; pass count unchanged for surviving tests |
| No live code deleted | `src/domains/`, `src/infrastructure/hsm/` untouched |
| No live test coverage lost | 4 test files updated, not deleted; `production_test.py` preserved |
| Each deletion evidenced | Zero-importer status verified per package |

### Revised Postconditions

| Original (pr002_design.md) | Revised | Reason |
|---------------------------|---------|--------|
| 59 files deleted | 32 files deleted | File counts were inflated by 2x |
| ~15 test files deleted | 11 test files deleted, 4 updated | 5 test files have live imports |
| ~3.9% reduction | ~2.1% reduction | Corrected file counts |

---

## 6. Revised Rollback Strategy

### Structure: 3 commits (was 2)

| Commit | Content | Risk | Independently Revertable |
|--------|---------|------|--------------------------|
| 1 | Delete Tier 1 (8 zero-importer stubs) | Zero | Yes |
| 2 | Update 5 test files (remove dead imports only) | Low — tests may need function-level cleanup | Yes |
| 3 | Delete Tier 2 packages (24 files) + delete 11 test files | Medium | Yes |

**Rationale for 3 commits**: Commit 2 (test updates) must land before Commit 3 (Tier 2 deletion). If Commit 3 is reverted, the test updates in Commit 2 are harmless (they remove imports for code that would be restored, but those imports were only used in now-simplified tests).

### Trigger

- Server fails to start (ImportError)
- Any previously passing test fails unexpectedly
- Any test file in the do-not-delete list is missing

### Procedure

1. `git revert <commit-hash>` — start with Commit 3 if Tier 2 broke something
2. Verify: `python -m pytest tests/` — same pass/skip/error counts as baseline
3. Verify: server starts without import errors

---

## 7. Diff from pr002_design.md

| Section | What Changed | Why |
|---------|-------------|-----|
| File counts (Tier 2) | 48 → 24 | Actual file counts are half of claimed |
| Total deletions | 59 → 32 | Cascading from file count correction |
| Tier 1 file count | 11 → 8 | `core/health/` has 4 files not 7 |
| Test deletions | ~15 → 11 | 5 tests import live code and must be updated, not deleted |
| Test updates | 0 → 4-5 | New category: tests needing dead import removal |
| Commit structure | 2 → 3 | Separate commit for test updates |
| Codebase reduction | ~3.9% → ~2.1% | Corrected arithmetic |

---

## STOP

Revision complete.APPROVED FOR IMPLEMENTATION 
