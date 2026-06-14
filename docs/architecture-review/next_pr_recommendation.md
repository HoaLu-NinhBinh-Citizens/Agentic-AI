# Next PR Recommendation

> **Date**: 2026-06-14
> **As of commit**: `a2042cb` (post PR-003)
> **Author**: Principal Engineer

---

## STEP 9: The One PR

### Name

**PR-004: Delete Remaining Dead Code and Fix Broken Test Suite**

---

### Goal

Delete all remaining dead code (10 legacy redirect packages, `core/events/`, 3 orphan `application/api/app/` files, stale `__pycache__`) and fix every broken test file so the test suite collects and runs without errors.

---

### Why Now

The bottleneck audit identified 14 architectural bottlenecks across the system. Every bottleneck ranked P1 or higher (Anthropic streaming, structured tool calling, lexical search index, context builder integration) **requires a working test suite to validate**.

Current state:
- `python -m pytest tests/` -> 16 collection errors, zero visible passing tests
- 10 legacy redirect packages create dual import paths
- ~85 dead files (~3,576 lines) inflate the codebase
- ~6 dead test files test non-existent modules

Without PR-004:
- No CI/CD regression gating is possible
- No developer can trust the test suite
- Every subsequent PR ships without validation
- Retrieval returns dead code in search results
- New developers discover two import paths for every symbol

With PR-004:
- Test suite collects cleanly (0-4 errors, down from 16)
- 175+ existing tests run and pass
- Single import convention per module
- Dead code removed from retrieval corpus
- Foundation for all P1-P3 work

---

### Why Not the Others

| Task | Why Not Next |
|------|-------------|
| **B: Anthropic streaming** | 1-2 hour fix but cannot be validated without tests. If streaming breaks, no test catches it. Ship B after A. |
| **C: Structured tool calling** | Changes core agent interaction model. Without tests, regressions in tool execution are invisible. Ship C after A. |
| **D: Lexical search index** | Performance optimization. Current O(N) scan works correctly; it's slow, not broken. Tests needed to verify correctness of new index. Ship D after A. |
| **E: Context builder integration** | Quality improvement. Needs tests to measure before/after. Ship E after A. |
| **F-J** | All P3. Lower urgency, same dependency on test suite. |

The pattern is clear: **every feature task depends on the test suite, and the test suite is broken.**

---

### Expected Impact

| Metric | Before | After |
|--------|--------|-------|
| Test collection errors | 16 | 0-4 |
| Legacy redirect packages | 10 | 0 |
| Dead subsystems | 1 (`core/events/`) | 0 |
| Orphan files | 3 | 0 |
| Stale `__pycache__` | 33 .pyc files | 0 |
| Python source files | ~1,296 | ~1,244 |
| "Legacy alias" stubs | 10 | 0 |
| Passing tests visible | 0 (hidden by errors) | 175+ |
| CI/CD regression gating | **Impossible** | **Enabled** |

---

### Risk

**Overall: Medium-Low**

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Redirect has undiscovered production importer | Very Low | Verified by `rg` across entire `src/` for all 10 packages |
| Test import points to wrong canonical module | Medium | Follow each redirect's own `__init__.py` mapping |
| Commit ordering mistake breaks 175 passing tests | Low | Strict sequence: update tests -> delete source |
| Stale `.pyc` shadows new import | Very Low | Delete `__pycache__` in final commit |

---

### Complexity

**Medium-Low** — Mechanical deletion + grep-guided import redirect. No new abstractions. No dependency changes. No production code modifications.

- Estimated time: 2-3 hours including verification
- Estimated commits: 4
- Estimated files: ~85 deleted, ~8 modified (test imports)
- Estimated lines deleted: ~5,500

---

### Dependencies

- PR-001 (merged): Security hardening
- PR-002 (implemented): Tier 1+2 dead code
- PR-003 (implemented): Orchestration consolidation
- No external dependencies

---

### Success Criteria

| # | Criterion | Verification |
|---|-----------|-------------|
| S1 | 10 redirect packages deleted | `python -c "import src.runtime"` -> `ModuleNotFoundError` |
| S2 | `core/events/` deleted | `python -c "import src.core.events"` -> `ModuleNotFoundError` |
| S3 | 3 orphan files deleted | Files don't exist on disk |
| S4 | Zero "Legacy alias" stubs | `rg "Legacy alias" src/ --type py` -> 0 hits |
| S5 | Test errors reduced | `python -m pytest tests/ -q --tb=no` -> <= 4 errors |
| S6 | 175+ tests pass | Previously passing tests still pass |
| S7 | Server starts | `python -c "from interfaces.server.main import app"` -> no error |
| S8 | No live code deleted | Do-not-modify list unchanged |
| S9 | Stale `__pycache__` cleaned | 0 `.pyc` in deleted package dirs |
| S10 | No new files created | `git diff --name-status` shows only D and M |

---

### Failure Criteria

| # | Criterion | Action |
|---|-----------|--------|
| F1 | Server fails to start | Revert immediately |
| F2 | Previously passing test fails | Fix import or revert |
| F3 | Test collection errors increase above 16 | Revert — something deleted that shouldn't have been |
| F4 | Do-not-modify file was modified | Revert the modification |
| F5 | Redirect package has production importer | Remove from scope, do not delete |

---

## Justification Summary

**If we implement only ONE PR, PR-004 (dead code cleanup + test suite fix) gives the highest ROI because:**

1. **It's the foundation.** Every other improvement (streaming, tool calling, search indexing, context building) requires tests to validate. Without tests, improvements are unverifiable.

2. **It has the highest leverage.** 2-3 hours of mechanical work unblocks unlimited future work. No other task has this multiplier effect.

3. **It has the lowest risk.** Pure deletion of verified-dead code. No new abstractions, no production code changes, no dependency modifications.

4. **It eliminates technical debt.** 10 redirect packages, 1 dead subsystem, 3 orphan files, 33 stale `.pyc` files — all confirmed dead by grep. Carrying this debt increases cognitive load on every future PR.

5. **It was already designed.** The PR-004 design documents (design, scope, risks, success criteria) were written and verified against source code. The audit confirms they are accurate. No corrections needed.

**The existing PR-004 design stands. Proceed to implementation.**
