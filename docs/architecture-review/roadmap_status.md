# Roadmap Status

> **Date**: 2026-06-14
> **As of commit**: `01f3d35` (post PR-004)

---

## Phase A — Security Hardening ✓

| Item | PR | Status |
|------|-----|--------|
| Exponential backoff with jitter | PR-001 | **Done** |
| Rate limiter (sliding window) | Pre-existing | **Done** |
| Path traversal guard | Pre-existing | **Done** |
| CORS configuration | Pre-existing | **Done** |

---

## Phase B — Dead Code Audit & Consolidation ✓

| Item | PR | Status |
|------|-----|--------|
| Tier 1: zero-importer stubs | PR-002 | **Done** |
| Tier 2: test-only packages | PR-002 | **Done** |
| Consolidate orchestration (LangGraph, multi-agent, supervisor) | PR-003 | **Done** |
| Remove `langgraph` dependency | PR-003 | **Done** |
| Delete dead infrastructure (distributed, chaos, fleet, sharding) | PR-003 | **Done** |
| Delete 10 legacy redirect packages | PR-004 | **Done** |
| Delete `core/events/` subsystem | PR-004 | **Done** |
| Delete orphan app files | PR-004 | **Done** |
| Fix broken test imports (16 → 2 errors) | PR-004 | **Done** |
| Clean stale `__pycache__` | PR-004 | **Done** |
| Clean stale planning docs | Post PR-004 | **Done** |

---

## Test Suite Health

| Metric | Pre PR-002 | Post PR-003 | Post PR-004 |
|--------|-----------|-------------|-------------|
| Collection errors | 25 | 16 | **2** |
| Skipped (stub modules) | 5 | 5 | **5** |
| Tests collected | — | — | **5,436** |

### Remaining 2 Collection Errors (pre-existing)

| Test File | Broken Import | Root Cause |
|-----------|--------------|------------|
| `test_aikicad_agent.py` | `WriteBoundaryGuard` from `domains.safety` | Symbol not exported — production code bug |
| `test_embedded_agent_regression.py` | `src.benchmarking` via `component_factory.py` | Module never existed — production code bug |

### Remaining 5 Test Failures (pre-existing)

| Test | Issue |
|------|-------|
| `test_p3_observability::test_session_and_request_id` | `AttributeError` — logic bug |
| `test_tools::test_registry_unregister` | `AssertionError` — logic bug |
| `test_flash_tools` ×3 | Pre-existing failures |

---

## Architecture Metrics

| Metric | Value | Trend |
|--------|-------|-------|
| Python source files | ~1,241 | -55 from PR-004 |
| Test files | ~344 | -7 from PR-004 |
| Orchestration paths | 1 (RealAgent) | Unchanged |
| Legacy redirect packages | 0 | Was 10 |
| Dead subsystems | 0 | Was 1 (`core/events/`) |
| External LLM dependencies | 4 (openai, anthropic, ollama, langchain) | `langchain` is orphan |
| Production server imports | 10 modules | Unchanged |

---

## Remaining Work (Future PRs)

| # | Item | Scope | Priority |
|---|------|-------|----------|
| 1 | Fix `WriteBoundaryGuard` export | Production code symbol fix | Medium |
| 2 | Fix `src.benchmarking` reference | Production code bug in `component_factory.py` | Medium |
| 3 | Remove orphan `langchain` dependency | `pyproject.toml` cleanup | Low |
| 4 | Import convention unification (`src.` vs bare) | PR-009 — large blast radius | Low |
| 5 | Fix 5 pre-existing test failures | Logic bugs, not import errors | Low |
| 6 | Regenerate `egg-info` | `pip install -e .` | Trivial |
