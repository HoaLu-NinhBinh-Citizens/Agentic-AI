# PR-004 Rollback Plan

> **Date**: 2026-06-14
> **PR**: PR-004 — Delete Remaining Dead Code and Fix Broken Test Suite

---

## Rollback Principle

Each commit is independently revertable via `git revert <hash>`. Commits are ordered so that reverting the latest commit never breaks the previous state.

---

## Rollback Triggers

| # | Trigger | Severity | Action |
|---|---------|----------|--------|
| T1 | Server fails to start (`from interfaces.server.main import app` throws) | **Critical** | Revert immediately — start from most recent commit |
| T2 | Previously passing test fails after import redirect | **High** | Fix the specific import; if unfixable within 5 min, revert that test file's change |
| T3 | Test collection errors increase above 16 (baseline) | **High** | Revert Commit 3 (source deletion) — a redirect package was deleted that shouldn't have been |
| T4 | A file in the do-not-modify list was changed | **High** | Revert the specific commit that touched it |
| T5 | A redirect package turns out to have an undiscovered production importer | **Medium** | Remove that package from Commit 3 scope; revert and re-do without it |

---

## Per-Commit Rollback Procedures

### Commit 4: Clean stale `__pycache__`

**Risk**: Zero — deleting `.pyc` files has no code impact.

**Rollback**: Not needed. If reverted, stale `.pyc` files return — cosmetic only.

```bash
git revert <commit-4-hash>
```

---

### Commit 3: Delete redirect packages + `core/events/` + orphan files

**Risk**: Medium — this is the critical deletion commit.

**Rollback procedure**:
```bash
git revert <commit-3-hash>
# Verify:
python -c "from interfaces.server.main import app"
python -m pytest tests/test_tools.py tests/test_sandbox.py tests/test_runtime.py --tb=no
```

**After revert**: Test imports from Commit 1 now point to canonical paths, but the redirect packages are restored. Tests will pass via canonical paths (redirect packages become unused but harmless). The codebase is in a safe state — Commits 1+2 remain valid.

---

### Commit 2: Fix or delete broken test files

**Risk**: Low — only affects test files that were already broken.

**Rollback procedure**:
```bash
git revert <commit-2-hash>
# Verify:
python -m pytest tests/ -q --tb=no
# Expected: 16 collection errors restored (baseline)
```

**After revert**: Broken test files are restored. They were already broken before PR-004 — reverting returns to baseline.

---

### Commit 1: Relocate `ai_support_config.py` + update passing test imports

**Risk**: Low — mechanical import path change.

**Rollback procedure**:
```bash
git revert <commit-1-hash>
# Verify:
python -m pytest tests/test_output_policy.py tests/test_p2_sandbox.py tests/test_p3_observability.py tests/test_features_2025.py tests/test_runtime.py tests/test_sandbox.py tests/test_tools.py tests/unit/test_config.py --tb=no
# Expected: 175 passed, 2 failed (pre-existing baseline)
```

**After revert**: `ai_support_config.py` moves back to `src/config/`. Test imports revert to redirect paths. Tests pass via redirects.

---

## Full PR Rollback

If the entire PR must be reverted:

```bash
# Revert in reverse order (most recent first):
git revert <commit-4-hash>
git revert <commit-3-hash>
git revert <commit-2-hash>
git revert <commit-1-hash>

# Or revert the merge commit if PR was squash-merged:
git revert <merge-commit-hash>

# Verify full baseline:
python -c "from interfaces.server.main import app"
python -m pytest tests/ -q --tb=no
# Expected: 16 collection errors (original baseline)
```

---

## Recovery Scenarios

### Scenario A: Commit 3 deletes a package with a hidden importer

**Symptom**: Runtime `ImportError` in production path, or test that was passing now fails with `ModuleNotFoundError`.

**Recovery**:
1. Identify which deleted package is needed: `python -c "from <module> import <symbol>"` for each deleted package
2. `git revert <commit-3-hash>`
3. Remove the needed package from the deletion list
4. Re-create Commit 3 without that package
5. File a follow-up ticket to investigate the hidden importer

### Scenario B: `ai_support_config.py` relocation breaks something

**Symptom**: `ImportError` for `AISupportConfig` anywhere.

**Recovery**:
1. `git revert <commit-1-hash>` — file returns to `src/config/`
2. Investigate which code imports `AISupportConfig` from `src.config`
3. Update the import path or keep the file in `src/config/`

### Scenario C: Test import update points to wrong canonical module

**Symptom**: `ImportError` or `AttributeError` in a test that was previously passing.

**Recovery**:
1. Check the redirect's `__init__.py` for the correct canonical path
2. Fix the import in the test file
3. If the canonical module doesn't export the symbol: check `__all__` in the canonical `__init__.py`
4. If unfixable: revert the test file change only (the redirect package will handle it)

---

## Post-Rollback Verification Checklist

| # | Check | Command | Pass Criteria |
|---|-------|---------|---------------|
| 1 | Server starts | `python -c "from interfaces.server.main import app"` | No error |
| 2 | Production imports work | `python -c "from core.agent.real_agent import RealAgent"` | No error |
| 3 | Tool execution works | `python -c "from application.orchestration.tool_execution.service import ToolExecutionService"` | No error |
| 4 | Test baseline restored | `python -m pytest tests/ -q --tb=no` | <= 16 errors |
| 5 | No regressions | `python -m pytest tests/test_tools.py tests/test_sandbox.py tests/test_runtime.py --tb=no` | 175 passed |
