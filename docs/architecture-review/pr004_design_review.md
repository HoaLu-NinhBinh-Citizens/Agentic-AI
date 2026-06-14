# PR-004 Design Review

> **Date**: 2026-06-14
> **Reviewer**: Independent verification against source code
> **Commit**: `a2042cb` (post PR-003)
> **Verdict**: PROCEED WITH CORRECTIONS — no blockers, 7 findings require document updates

---

## 1. Scope Verification

### IN SCOPE — Verified

| Item | Claimed | Verified | Status |
|------|---------|----------|--------|
| 10 redirect packages, zero production importers | Yes | Yes — `rg` across all `src/` confirms zero external production imports for all 10 | **CONFIRMED** |
| `core/events/` zero external importers | Yes | Yes — only self-imports within `core/events/` | **CONFIRMED** |
| 3 orphan `application/api/app/` files | Yes | Yes — see Finding F2 for minor inaccuracy | **CONFIRMED with correction** |
| Stale `__pycache__` in 3 directories | Yes | Yes — directories exist with stale `.pyc` files | **CONFIRMED** |
| 8 passing test files need import redirect | Yes | Yes — all 8 use redirect packages | **CONFIRMED** |
| 6 dead test files to delete | Yes | Partially — see Finding F3, F4 | **REQUIRES CORRECTION** |

### OUT OF SCOPE — Verified

No scope violations found. The do-not-modify list is correct and complete.

### MUST NOT TOUCH — Verified

All listed files exist and are correctly excluded. Verified that none import from packages being deleted.

**Violations found: 0**

---

## 2. File Movement Verification

### Deletions — Verified

| Group | Claimed Files | Verified | Notes |
|-------|--------------|----------|-------|
| A: Redirect packages | ~43 files | ~48 files (design says 43, affected_files.md says 48) | Count discrepancy is cosmetic — file list is correct |
| B: `core/events/` | 6 files | 6 files | **CONFIRMED** |
| C: Orphan app files | 3 files | 3 files | **CONFIRMED** — but `chat_endpoints.py` does NOT import from `core.multi_agent.agent` (see F2) |
| D: Stale `__pycache__` | 33 `.pyc` | Present | **CONFIRMED** |

### Move — Verified

| File | From | To | Status |
|------|------|----|--------|
| `ai_support_config.py` | `src/config/` | `src/core/config/` | **CORRECT** — file is original code (123 LOC), not a redirect. Zero production importers. |

### Import Updates — Verified

All 8 passing test file redirects map to existing canonical modules. Canonical targets verified:

| Canonical Target | Exists |
|-----------------|--------|
| `src/core/config/output_policy.py` | Yes |
| `src/core/tools/sandbox.py` | Yes |
| `src/core/tools/audit.py` | Yes |
| `src/core/tools/schema.py` | Yes |
| `src/core/tools/registry.py` | Yes |
| `src/core/runtime/journal.py` | Yes |
| `src/core/runtime/replayer.py` | Yes |
| `src/infrastructure/models/__init__.py` | Yes |

---

## 3. Redirect Package Verification

All 10 redirect packages verified:

| Package | Exists | "Legacy alias" | `__init__.py` | Production Importers | Dynamic Importers | Plugin/CLI Usage | Deployment Dependency |
|---------|--------|---------------|---------------|---------------------|-------------------|------------------|-----------------------|
| `src/runtime/` | Yes | Yes | Yes | 0 | 0 | 0 | 0 |
| `src/tools/` | Yes | Yes | Yes | 0 | 0 | 0 | 0 |
| `src/hardware_engine/` | Yes | Yes | Yes | 0 | 0 | 0 | 0 |
| `src/config/` | Yes | Yes | Yes | 0 | 0 | 0 | 0 |
| `src/health/` | Yes | Yes | Yes | 0 | 0 | 0 | 0 |
| `src/llm/` | Yes | Yes | Yes | 0 | 0 | 0 | 0 |
| `src/models/` | Yes | Yes | Yes | 0 | 0 | 0 | 0 |
| `src/parsing/` | Yes | Yes | Yes | 0 | 0 | 0 | 0 |
| `src/security/` | Yes | **No** | **No** | 0 | 0 | 0 | 0 |
| `src/scheduler/` | Yes | Yes | Yes | 0 | 0 | 0 | 0 |

**All safe to delete.** `src/security/` is a stub (no `__init__.py`, not a proper package), not a redirect — but still has zero importers. Deletion is safe regardless.

---

## 4. `ai_support_config.py` Disposition

**Must MOVE** to `src/core/config/ai_support_config.py`.

| Question | Answer | Evidence |
|----------|--------|----------|
| Is it a redirect? | No — original code (dataclasses: `AISupportConfig`, `RuleConfig`, `MLRuleConfig`, `IndexingConfig`, `OutputConfig`) | Read file contents |
| Production importers? | Zero outside `src/config/` | `rg "AISupportConfig\|ai_support_config" src/ --type py` — only `src/config/__init__.py` |
| Test importers? | `tests/unit/test_config.py` | Must update import after move |
| Can it stay? | No — `src/config/` is being deleted | Move is required |
| Can it be duplicated? | No reason to — zero production importers means one copy in canonical location suffices | |

**Implementation plan's D1 resolution is correct.**

---

## 5. Test Classification Verification

### Category 1: DELETE — Corrections needed

| Test File | Design Says | Verified Import | Actual Status | Correction |
|-----------|------------|----------------|---------------|------------|
| `test_events.py` | Imports `src.events.*` (non-existent) | Imports `src.events.*` — `src/events/` redirect was deleted in PR-002 | **DELETE** — correct | None |
| `test_hardware.py` | Imports `src.hardware` (never existed) | Imports `src.hardware` — no such module | **DELETE** — correct | None |
| `test_learning.py` | Imports `src.learning` (never existed) | Imports `src.learning` — no such module | **DELETE** — correct | None |
| `test_observability.py` | Imports `src.observability` (never existed) | Imports `src.observability` — no such module | **DELETE** — correct | None |
| `test_p5_memory.py` | Imports `src.memory.advanced_memory` (never existed) | Imports `src.memory.advanced_memory` — `src/memory/` doesn't exist as a package; `src/core/memory/advanced_memory.py` exists | **DELETE is debatable** — see F3 | Should be INVESTIGATE, not blind DELETE |
| `test_phase4.py` | Imports `src.introspection`, etc. | Confirmed — modules don't exist | **DELETE** — correct | None |

### Category 2: UPDATE — Corrections needed

| Test File | Design Says | Verified | Correction |
|-----------|------------|----------|------------|
| `test_output_policy.py` | `src.config` → `src.core.config` | Correct | None |
| `test_p2_sandbox.py` | `src.tools` → `src.core.tools` | Correct | None |
| `test_p3_observability.py` | `src.runtime` → `src.core.runtime` | Correct | None |
| `test_features_2025.py` | `src.models` → `src.infrastructure.models` | **Line 114 imports `User` from `src.models`** — design is correct about the redirect, but most of the file has no imports at all (pure regex tests) | Verify `User` exists in canonical `infrastructure.models` |
| `test_runtime.py` | `src.runtime` → `src.core.runtime` | Correct | None |
| `test_sandbox.py` | `src.tools` → `src.core.tools` | Correct | None |
| `test_tools.py` | `src.tools` → `src.core.tools` | Correct | None |
| `tests/unit/test_config.py` | `src.config` → `src.core.config` | Correct | None |

### Category 3: CASE-BY-CASE — Verified

All 10 case-by-case test files verified. Implementation plan resolutions are largely correct. Key findings:

- `test_p9_production_concepts.py`: Design correctly identifies this as DELETE — `HealthStatus`, `HealthCheckResult`, `HealthChecks` don't exist at the redirect target
- `test_retrieval_manifest.py` and `test_retrieval_search_cache.py`: Canonical targets verified (`infrastructure/retrieval/manifest.py` has `IndexManifest`, `infrastructure/retrieval/search_cache.py` has `SearchCache`)
- `test_phase15.py`: Many symbols beyond `TaskScheduler` may not be exported from canonical `core.runtime` — investigate during implementation

---

## 6. Runtime Impact Verification

**CONFIRMED: Zero runtime impact.**

| Runtime Component | Imports from deleted packages? | Status |
|-------------------|-------------------------------|--------|
| `interfaces/server/main.py` | No | **SAFE** |
| `core/agent/*` | No | **SAFE** |
| `application/orchestration/tool_execution/*` | No | **SAFE** |
| `application/api/app/embedded_agent.py` | No (has pre-existing `src.benchmarking` bug — out of scope) | **SAFE** |
| `RealAgent` (`core/agent/real_agent.py`) | No | **SAFE** |
| `ToolExecutionService` (`application/orchestration/tool_execution/service.py`) | No | **SAFE** |
| WebSocket server | No | **SAFE** |
| MCP protocol | No | **SAFE** |

---

## 7. Rollback Verification

**CONFIRMED: Each commit is independently revertable.**

| Commit | Revert Safety | Notes |
|--------|--------------|-------|
| 1 (relocate + update imports) | Safe — reverts to redirect imports which still work | Correct |
| 2 (fix/delete broken tests) | Safe — restores already-broken tests | Correct |
| 3 (delete source) | Safe — restores redirect packages; Commit 1 canonical imports still work | Correct |
| 4 (clean `__pycache__`) | Safe — cosmetic only | Correct |

Reverse-order revert (`4→3→2→1`) restores exact baseline. **Verified.**

---

## 8. Risks

### Blocking Risks

**None.**

### Non-Blocking Risks

| # | Risk | Severity | Notes |
|---|------|----------|-------|
| NB1 | `test_phase15.py` imports ~20 symbols from `src.runtime` — many may not be exported from canonical `core.runtime` | Medium | May need to DELETE rather than UPDATE this test |
| NB2 | `test_features_2025.py` line 114 imports `User` from `src.models` — must verify `User` exists in `infrastructure.models` | Low | If missing, delete that one test class |
| NB3 | `test_p5_memory.py` could potentially be UPDATE'd to `src.core.memory.advanced_memory` instead of DELETE'd | Low | Design says DELETE but canonical path exists — investigate during implementation |

### Unknown Risks

| # | Risk | Likelihood |
|---|------|-----------|
| U1 | A deployment script outside `src/` references a redirect package | Very Low — grep of entire repo found nothing |
| U2 | A notebook or script in untracked files imports from redirect packages | Very Low — not in git |

---

## Findings Summary

| # | Finding | Severity | Action Required |
|---|---------|----------|----------------|
| F1 | `src/security/` has no `__init__.py` — not a redirect package, just a stub file | Cosmetic | Update design doc description (deletion still safe) |
| F2 | `chat_endpoints.py` does NOT import from `core.multi_agent.agent` — design doc reason is wrong (the file references `UnifiedAgent` without importing it, and imports from `src.shared.utils`) | Cosmetic | Update design doc reason for deletion (file is still orphan — `api_server.py` is its only importer) |
| F3 | `test_p5_memory.py` imports from `src.memory.advanced_memory` — `src/core/memory/advanced_memory.py` exists as canonical target | Low | Reclassify from "DELETE" to "INVESTIGATE" — could be UPDATE'd |
| F4 | `test_features_2025.py` DOES import `User` from `src.models` at line 114 — agent report claiming "no models imports" was wrong | Low | Verify `User` exists in canonical target during implementation |
| F5 | Design doc file count inconsistency: "~43 files" in design vs "48 files" in affected_files | Cosmetic | Use affected_files.md list as authoritative |
| F6 | `test_phase15.py` imports ~20 symbols that may not all be exported from canonical `core.runtime` | Medium | May need to DELETE instead of UPDATE — investigate during implementation |
| F7 | `test_events.py` imports from `src.events.*` (deleted redirect), NOT from `src.core.events.*` — design is correct that it should be deleted since `core/events/` is also being deleted | None | Confirm: even if redirected to `core.events`, the subsystem itself is dead |

---

## Verdict

**PROCEED WITH CORRECTIONS.** No blockers found. All critical assumptions verified:

1. All 10 redirect packages have zero production importers — **CONFIRMED**
2. `core/events/` has zero external importers — **CONFIRMED**
3. 3 orphan app files are safe to delete — **CONFIRMED**
4. Production runtime path is untouched — **CONFIRMED**
5. Rollback is commit-by-commit safe — **CONFIRMED**

The 7 findings are non-blocking corrections to document accuracy. The implementation plan is sound.
