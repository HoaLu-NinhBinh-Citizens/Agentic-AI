# PR-004 Blockers

> **Date**: 2026-06-14
> **Reviewer**: Independent verification against source code
> **Commit**: `a2042cb`

---

## Blocking Risks

**None.** All critical assumptions verified against source code.

---

## Non-Blocking Issues (must address during implementation)

| # | Issue | Impact | Resolution |
|---|-------|--------|------------|
| NB1 | `test_phase15.py` imports ~20 symbols from `src.runtime` — not all may be exported from canonical `core.runtime` | Test may fail after import redirect | Investigate each symbol. If canonical doesn't export them, DELETE the test instead of UPDATE. |
| NB2 | `test_p5_memory.py` was classified as DELETE but `src/core/memory/advanced_memory.py` exists | Potentially deleting a salvageable test | Reclassify to INVESTIGATE. Try `from src.core.memory.advanced_memory import ...` first. |
| NB3 | `test_features_2025.py` line 114 imports `User` from `src.models` | Must verify `User` in canonical `infrastructure.models` before updating | If `User` missing, delete that test class only, keep the rest. |
| NB4 | Design doc says `chat_endpoints.py` imports from `core.multi_agent.agent` — it does not | Document inaccuracy | Correct reason: file references undefined `UnifiedAgent` and is only imported by `api_server.py` (also being deleted). Deletion still correct. |
| NB5 | `src/security/` described as "redirect (1 file)" — it's actually a stub with no `__init__.py` | Document inaccuracy | Not a package at all. Still safe to delete (zero importers). |
| NB6 | File count discrepancy: design says ~43 redirect files, affected_files says 48 | Document inconsistency | Use affected_files.md as authoritative count. |
| NB7 | `test_events.py` imports from `src.events.*` — this is a deleted redirect (PR-002), not `core.events` directly | Clarification | DELETE is still correct since `core/events/` is also being deleted in this PR. |

---

## Pre-Implementation Checklist

All items verified:

| Check | Status |
|-------|--------|
| Zero production importers for all 10 redirect packages | **PASS** |
| Zero external importers for `core/events/` | **PASS** |
| Zero external importers for 3 orphan app files | **PASS** |
| `main.py` does not import from any deleted package | **PASS** |
| `core/agent/` does not import from any deleted package | **PASS** |
| `tool_execution/` does not import from any deleted package | **PASS** |
| All canonical redirect targets exist | **PASS** |
| `ai_support_config.py` is original code (confirmed not a redirect) | **PASS** |
| Rollback is commit-by-commit safe | **PASS** |
| No dynamic imports of deleted packages | **PASS** |

---

## Decision

**No blockers. Implementation may proceed.**
