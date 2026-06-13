# PR-002 Design — Delete Obvious Dead Code Trees

> **Document type**: Design — no code modified.
> **Date**: 2026-06-13
> **Author**: Principal Engineer review
> **Status**: READY FOR IMPLEMENTATION (with scope corrections)

---

## 1. Goal

Delete confirmed-dead packages that have **zero live importers** (production or test). Remove test files that exclusively test deleted modules. Reduce codebase noise, grep false positives, and maintenance surface.

### Root Cause Addressed

**RC-1: Speculative scaffolding never pruned.** During phased development (Phase 1-5), packages were created ahead of implementation and never filled, wired, or removed.

---

## 2. Scope Corrections from Planning Documents

**CRITICAL**: The planning documents (`implementation_contract.md`, `files_classification.md`, `current_problems.md`) listed the following as dead code. **Evidence-based audit found some are NOT dead:**

| Package | Planning Classification | Actual Status | Evidence |
|---------|----------------------|---------------|----------|
| `src/domains/` | Dead (shadow of `src/domain/`) | **LIVE — MUST NOT DELETE** | 30+ importers from `src/hardware_engine/`, `src/infrastructure/mcp/`, `src/core/agent/`, `src/application/` |
| `src/infrastructure/hsm/` | Dead stub | **LIVE — MUST NOT DELETE** | Imported by `src/domain/hardware/flash/ab_partition.py`, `src/domain/ports/hardware_security.py` |
| `src/infrastructure/performance/rust/` | Dead (Cargo.toml, no Python) | **UNCLEAR** | `tests/unit/test_rust_bridge.py` imports `rust_bridge` (separate file), not from `rust/` subdirectory. The `rust/` dir contains only `Cargo.toml` + `main.rs`. Likely dead but **NEED MORE EVIDENCE** on whether `rust_bridge.py` depends on compiled output from this directory. |

**These items are REMOVED from PR-002 scope.** Proceeding with them would break production code.

---

## 3. Confirmed Deletion Targets

### Tier 1: Zero Importers (no production, no test)

| Target | File Count | Importers | Confidence |
|--------|-----------|-----------|------------|
| `src/infrastructure/sharding/` | 1 | None | High |
| `src/core/health/` | 7 (empty `__init__.py` stubs) | None | High |
| `src/core/execution/worker_pool/` | 1 (empty stub) | None | High |
| `src/core/execution/executor/` | 1 (empty stub) | None | High |
| `src/core/execution/task_queue/` | 1 (empty stub) | None | High |

**Total Tier 1: 11 files, zero risk.**

### Tier 2: Test-Only Importers (safe to delete with corresponding tests)

| Target | File Count | Test Importers | Production Importers | Confidence |
|--------|-----------|---------------|---------------------|------------|
| `src/app/` | 8 (legacy aliases) | 6 test files | None | High |
| `src/agent/` | 10 (legacy aliases) | 2 test files | None | High |
| `src/infrastructure/distributed/` | 15 | 3 test files | None (self-imports only) | High |
| `src/infrastructure/fleet/` | 3 | 1 test file | None | High |
| `src/infrastructure/chaos/` | 3 | 2 test files | None | High |
| `src/core/checkpoint/` | 9 (empty stubs) | 1 test file (`integration/production_test.py`) | None | High |

**Total Tier 2: 48 files + 15 test files.**

### Test Files to Delete (import exclusively from deleted packages)

| Test File | Imports From | Action |
|-----------|-------------|--------|
| `tests/test_aikicad_agent.py` | `src.app` | Delete |
| `tests/test_api_server.py` | `src.app` | Delete |
| `tests/test_dashboard_e2e.py` | `src.app` | Delete |
| `tests/test_embedded_agent_bootstrap.py` | `src.app` | Delete |
| `tests/test_embedded_agent_regression.py` | `src.app` | Delete |
| `tests/test_p9_production_runtime.py` | `src.app` | Delete |
| `tests/test_agent_control_flow.py` | `src.agent` | Delete |
| `tests/test_agent_executor.py` | `src.agent` | Delete |
| `tests/test_phase5.py` | `src.infrastructure.distributed` | Delete |
| `tests/test_p6_distributed.py` | `src.infrastructure.distributed` | Delete |
| `tests/test_redis_bus.py` | `src.infrastructure.distributed` | Delete |
| `tests/unit/test_predictive_failure.py` | `src.infrastructure.fleet` | Delete |
| `tests/unit/test_chaos_engineering.py` | `src.infrastructure.chaos` | Delete |
| `tests/test_chaos.py` | `src.infrastructure.chaos` | Delete |
| `tests/integration/production_test.py` | `src.core.checkpoint` | **VERIFY FIRST** — may import other live modules too |

**PRECONDITION**: Before deleting `tests/integration/production_test.py`, verify it imports ONLY from deleted packages. If it also imports from live packages, it must be updated, not deleted.

### Summary

| Category | Files Deleted | Tests Deleted |
|----------|-------------|---------------|
| Tier 1 (zero importers) | 11 | 0 |
| Tier 2 (test-only) | 48 | ~15 |
| **Total** | **59** | **~15** |

**Percentage of codebase**: 59 / 1509 Python files = ~3.9%

**Note**: This is significantly less than the "30-40%" estimated in planning documents. The planning estimate included `src/domains/` (125 files) which is **live code**. The 30% figure in `implementation_contract.md` postcondition (`File count reduced by >= 30%`) is **not achievable** in PR-002 without deleting live code. This postcondition must be revised.

---

## 4. Files Likely Modified

| File | Change | Reason |
|------|--------|--------|
| `src/infrastructure/__init__.py` | Remove re-exports of deleted packages | If it re-exports `distributed`, `sharding`, `fleet`, `chaos` |
| `src/core/execution/__init__.py` | Remove re-exports of deleted stubs | If it re-exports `worker_pool`, `executor`, `task_queue` |
| `src/core/__init__.py` | Remove re-exports of `health`, `checkpoint` | If it re-exports them |

**PRECONDITION**: Read each `__init__.py` before modifying. Only remove lines that reference deleted packages. Do not refactor.

---

## 5. Files MUST NOT Touch

| File / Directory | Reason |
|-----------------|--------|
| `src/domains/` | **LIVE CODE** — has production importers |
| `src/infrastructure/hsm/` | **LIVE CODE** — imported by domain layer |
| `src/infrastructure/performance/rust/` | **NEED MORE EVIDENCE** — defer to later PR |
| `src/interfaces/server/main.py` | Production server — no dead imports to remove |
| `src/core/agent/real_agent.py` | Production agent |
| `src/core/orchestration/` | PR-003 scope |
| `src/core/multi_agent/` | PR-003 scope |
| `src/core/events/` | PR-004 scope |
| `src/infrastructure/retrieval/` | Live retrieval code |
| `src/infrastructure/mcp/` | Live MCP code |
| `src/infrastructure/indexing/` | Live indexing code |
| `src/infrastructure/completion/` | Live completion code |
| `src/infrastructure/llm/` | Live LLM code |
| `src/infrastructure/embeddings/` | Live embedding code |
| `src/domain/` | Live domain layer |
| `src/application/` | Live application layer |
| `pyproject.toml` | No entry points reference deleted modules |
| `configs/` | No config references deleted modules |
| Frontend/Electron files | Server-only PR |

---

## 6. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| R1 | Undiscovered dynamic import (`importlib`, `__import__`) of deleted package | Low | High — runtime ImportError | Grep for dynamic imports referencing deleted package names before deletion |
| R2 | External script/notebook imports deleted package | Low | Medium — script breaks | Grep non-Python files (yaml, toml, json, sh, ps1, md) for deleted package names |
| R3 | `__init__.py` modification breaks sibling imports | Low | High — ImportError at startup | Read each `__init__.py` fully. Only remove lines referencing deleted packages. Test server start after. |
| R4 | Test file imports from both dead AND live modules | Medium | Medium — falsely delete test with live coverage | Verify each test file imports ONLY from dead modules before deleting |
| R5 | `src/domains/` is mistakenly included | High (in planning docs) | Critical — breaks production | **MITIGATED**: Removed from scope. This design doc overrides planning docs. |
| R6 | Planning postcondition "30% reduction" not met | Certain | Low — expectation management | Revise postcondition to reflect actual ~4% reduction. Document why. |

---

## 7. Rollback Strategy

### Trigger

- Server fails to start (ImportError)
- Any previously passing test fails unexpectedly
- Production workflow breaks (chat, tools, indexing)

### Procedure

1. `git revert <commit-hash>` — restores all deleted files
2. Verify: `python -m pytest tests/` — same pass/skip/error counts as baseline
3. Verify: server starts without import errors

### Granular Rollback

Structure as 2 commits for partial rollback:

| Commit | Content | Independently Revertable |
|--------|---------|--------------------------|
| 1 | Delete Tier 1 (zero-importer stubs) | Yes — zero risk |
| 2 | Delete Tier 2 (test-only packages + their tests) | Yes — higher risk |

### Rollback Verification

- File count returns to pre-PR-002 level
- Test suite returns to baseline counts
- `python -c "import src.app"` succeeds (if reverted)

---

## 8. Tests Required

### Pre-Implementation

| Check | Method | Pass Criteria |
|-------|--------|---------------|
| Baseline test counts | `python -m pytest tests/` | Record exact pass/skip/error counts |
| Baseline file count | `find src -name "*.py" | wc -l` | Record exact count |
| Dynamic import audit | Grep for `importlib.import_module`, `__import__` referencing target packages | Zero hits |
| Non-Python reference audit | Grep yaml/toml/json/sh/ps1/md for target package names | Zero production-relevant hits |
| `tests/integration/production_test.py` audit | Read file, verify all imports | Only dead-module imports → delete; mixed → update |

### Post-Implementation

| Check | Method | Pass Criteria |
|-------|--------|---------------|
| Server starts | `python -c "from interfaces.server.main import app"` | No ImportError |
| Remaining imports resolve | `python -c "import src; ..."` for all surviving packages | No ImportError |
| Test suite | `python -m pytest tests/` | Pass count >= baseline minus intentionally deleted tests. Skip count same. Error count reduced (deleted test files no longer error). |
| File count reduced | `find src -name "*.py" | wc -l` | Reduced by ~59 |
| Dead imports gone | Grep for deleted package names in surviving code | Zero hits |
| `import src.app` fails | `python -c "import src.app"` | `ModuleNotFoundError` |

### Tests NOT Required

- No new test files needed (deletion-only PR)
- No integration tests needed (no behavior change for surviving code)
- No benchmark tests needed (no performance-sensitive changes)

---

## 9. Success Criteria

| Criterion | Metric |
|-----------|--------|
| All confirmed-dead trees deleted | 11 Tier 1 + 48 Tier 2 files removed |
| Server starts without import errors | `from interfaces.server.main import app` succeeds |
| All production workflows unaffected | Chat, tools, indexing, completion unchanged |
| Test suite improved | Error count reduced (dead test files removed). Pass count unchanged. |
| No live code deleted | `src/domains/`, `src/infrastructure/hsm/` untouched |
| Each deletion evidenced | Zero-importer status verified per package |

### Revised Postconditions (replacing planning doc values)

| Original Postcondition | Revised | Reason |
|----------------------|---------|--------|
| File count reduced by >= 30% | File count reduced by ~59 Python files (~4%) | `src/domains/` (125 files) is live code, not deletable |
| `import src.app` raises `ModuleNotFoundError` | Same | Still valid |
| Server starts without import errors | Same | Still valid |

---

## 10. Conflict with Planning Documents

**This design overrides `implementation_contract.md` and `files_classification.md` on the following points:**

| Document Claim | Reality | Evidence |
|---------------|---------|----------|
| `src/domains/` is dead (shadow of `src/domain/`) | **LIVE** — 30+ importers from production code | `grep -r "from.*domains\." src/` returns hits in `hardware_engine/`, `infrastructure/mcp/`, `core/agent/`, `application/` |
| `src/infrastructure/hsm/` is dead stub | **LIVE** — imported by domain layer | `domain/hardware/flash/ab_partition.py` and `domain/ports/hardware_security.py` import from it |
| File count reduced by >= 30% | ~4% achievable without breaking production | `src/domains/` is 125 files; removing it was the main contributor to the 30% estimate |

**Recommendation**: Update `implementation_contract.md` PR-002 postconditions before implementation begins. The `src/domains/` package should be investigated in a separate future PR to determine if it's a true duplicate of `src/domain/` that should be consolidated (not deleted outright).

---

## STOP

PR-002 design complete. Do NOT implement. Do NOT start PR-003.
