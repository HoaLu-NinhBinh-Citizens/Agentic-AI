# PR-004 Risk Assessment

> **Date**: 2026-06-14
> **PR**: PR-004 — Delete Remaining Dead Code and Fix Broken Test Suite

---

## Risks

| # | Risk | Likelihood | Impact | Severity | Mitigation |
|---|------|-----------|--------|----------|------------|
| R1 | Redirect package has undiscovered production importer | Very Low | High — runtime ImportError | High | Verified by `rg` across entire `src/`. All 10 packages return zero external hits. Double-check during implementation by running server import test after each deletion. |
| R2 | Test import redirect points to wrong canonical module | Medium | Medium — test breaks | Medium | Each redirect `__init__.py` explicitly names its canonical source. Follow the redirect's own mapping. Run the test after each update. |
| R3 | Deleting `api_server.py` breaks an undiscovered deployment path | Low | Medium — alternate deployment fails | Medium | Grep all config files (yaml, toml, json, Dockerfile, docker-compose, sh, ps1) for `api_server`. Already verified zero hits. |
| R4 | Deleting `core/events/` breaks a lazy import not caught by grep | Very Low | Medium — runtime error in rarely-used path | Medium | Grep for `importlib.*events`, `__import__.*events` targeting `core.events`. Already verified zero hits. |
| R5 | Commit ordering mistake: redirect deleted before test updated | Low | High — 175 passing tests break | High | Strict commit sequence: tests updated in Commit 1+2, deletions in Commit 3. CI must pass between commits. |
| R6 | Stale `.pyc` shadows new import | Very Low | Low — confusing behavior | Low | Delete `__pycache__` in Commit 4. Python prioritizes `.py` over `.pyc` when both exist, so risk is minimal. |
| R7 | Case-by-case test file investigation takes too long | Medium | Low — scope creep | Low | Hard rule: if a test file's canonical symbol doesn't exist, delete the test. Do not investigate the production code to "make it work." Maximum 5 minutes per test file. |
| R8 | `src/config/agent_prompts.py` is confused with `src/core/config/agent_prompts.py` | Low | Medium — tests import wrong module | Medium | Verify that `src/config/agent_prompts.py` self-imports (it does: `from src.config.agent_prompts import ...` is a circular self-ref). The canonical module is `src/core/config/agent_prompts.py`. Tests must use canonical path. |
| R9 | `src/tools/` contains actual code, not just redirects | Very Low | High — deleting live code | High | Verified: `src/tools/__init__.py` says "Legacy alias", all files in `src/tools/` either re-export or are duplicates of `src/core/tools/`. Cross-check file-by-file during implementation. |

---

## Risk Summary

| Category | Count | Max Severity |
|----------|-------|-------------|
| Very Low likelihood | 4 | High (R1, R9) |
| Low likelihood | 3 | High (R5) |
| Medium likelihood | 2 | Medium (R2, R7) |

**Overall risk**: **Medium-Low**. The main risk is commit ordering (R5), which is procedural and controllable. All high-severity risks have very low likelihood due to thorough grep verification.

---

## Blocking Risks

None of the risks are blocking. All have verified mitigations. The PR can proceed.

---

## Pre-Flight Checks (must pass before implementation starts)

| Check | Command | Expected |
|-------|---------|----------|
| Server starts | `python -c "from interfaces.server.main import app"` (from `src/`) | No error |
| Baseline test count | `python -m pytest tests/ -q --tb=no 2>&1 \| tail -1` | 16 errors |
| Baseline passing count | `python -m pytest tests/test_tools.py tests/test_sandbox.py tests/test_runtime.py tests/test_output_policy.py tests/test_p2_sandbox.py tests/test_p3_observability.py tests/test_features_2025.py tests/unit/test_config.py --tb=no 2>&1 \| tail -1` | 175 passed, 2 failed |
| No production imports of redirect packages | `rg "from src\.(runtime|tools|hardware_engine|config|health|llm|models|parsing|security|scheduler)\b" src/ --type py -l \| grep -v "src/(runtime|tools|hardware_engine|config|health|llm|models|parsing|security|scheduler)/"` | Zero output |
