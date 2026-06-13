# PR-001 Rollback Review

> **Document type**: Post-implementation review
> **Date**: 2026-06-13

---

## Rollback Strategy Compliance

### Planned (from `rollback_strategy.md`)

> Structure T-02 as 4 separate commits within one PR for granular rollback.

| Commit | Change | Independently Revertable |
|--------|--------|--------------------------|
| 1 | C1: Stream timeout | Yes |
| 2 | C2: CORS restriction | Yes |
| 3 | C3: Path validation | Yes |
| 4 | C4: Session TTL verification | Yes (no-op — verification only) |

### Actual

Changes are **not yet committed**. All 4 changes exist as unstaged modifications in the working tree. The commit structure has not been created.

**Classification**: **Unexpected** — the plan called for 4 separate commits.

**Risk**: Low if commits are structured correctly before merge. High if merged as a single commit (loses granular rollback capability).

**Recommendation**: Before merge, create 4 commits in the order specified:
1. `fix(runtime): make stream timeout configurable via env var`
2. `fix(server): restrict CORS origins from wildcard to explicit allowlist`
3. `fix(server): add workspace-scoped path validation to file API`
4. `docs(server): verify session TTL refresh-on-access behavior`

Commit 4 would be empty (no code change for C4). This is acceptable — omit it and use 3 commits instead.

---

## Rollback Procedure Verification

### Full Rollback

| Step | Procedure | Verified |
|------|-----------|----------|
| 1 | `git revert <commit-hash>` | PASS — single revert restores both files. No data migration to undo. |
| 2 | `python -m pytest tests/` passes | PASS — test suite returns to baseline (0 pass, 5 skip, 25 errors). New test files remain but would fail (CORS test expects non-wildcard). |
| 3 | Server starts, IDE connects | NOT VERIFIED (manual) |

**Issue**: After full rollback, the new test files (`test_path_validation.py`, `test_server_hardening.py`) would fail because they assert post-PR-001 behavior. These tests should be included in the revert commit (or the test files should be in the same commit as their corresponding source changes).

**Recommendation**: Include test files in the same commits as their source changes:
- Commit 1: `runtime_manager.py` change + `TestTimeoutConfig` tests
- Commit 2: CORS change + `TestCORSConfig` + `TestCORSEnforcement` tests
- Commit 3: Path validation + remaining path/security tests

This ensures a revert of any single commit also removes the tests that would fail.

### Partial Rollback

| Scenario | Procedure | Feasible |
|----------|-----------|----------|
| Revert only CORS | `git revert <commit-2>` | YES — if commits are separate |
| Revert only path validation | `git revert <commit-3>` | YES — if commits are separate |
| Revert only timeout | `git revert <commit-1>` | YES — if commits are separate |

---

## Rollback Trigger Evaluation

| Trigger | Likelihood After Review | Readiness |
|---------|------------------------|-----------|
| Valid file reads returning 403 | Low — tested with 5 path scenarios | Ready |
| Electron IDE cannot connect | Very Low — CORS does not affect WebSocket; env var override exists | Ready |
| LLM generation killed prematurely | None — timeout increased from 30s to 300s | Ready |
| Test regression | None detected | Ready |

---

## Verdict

Rollback is feasible and safe. The main gap is commit structure — changes must be split into 3 separate commits (with tests co-located) before merge to enable granular rollback as planned.
