# Roadmap Status

> **Date**: 2026-06-14
> **As of commit**: `a2042cb` (post PR-003)

---

## Phase A — Security Hardening

| Item | PR | Status |
|------|-----|--------|
| Exponential backoff with jitter | PR-001 | **Done** |
| Rate limiter (sliding window) | Pre-existing | **Done** |
| Path traversal guard (`/api/fs/read`, `/api/fs/dir`) | Pre-existing | **Done** |
| CORS configuration | Pre-existing | **Done** |

---

## Phase B — Dead Code Audit & Consolidation (T-01)

| Item | PR | Status | Notes |
|------|-----|--------|-------|
| Tier 1: zero-importer stubs | PR-002 | **Done** | |
| Tier 2: test-only packages | PR-002 | **Done** | |
| Consolidate orchestration (LangGraph, multi-agent, supervisor) | PR-003 | **Done** | Single path: RealAgent + ToolExecutionService |
| Remove `langgraph` dependency | PR-003 | **Done** | |
| Delete dead infrastructure (distributed, chaos, fleet, sharding) | PR-003 | **Done** | Exceeded scope — done opportunistically |
| EventEmitter cleanup (`core/events/`) | PR-004 | **Not started** | Zero importers confirmed |
| Orphan files in `application/api/app/` (`chat_endpoints.py`, `api_server.py`) | — | **Not started** | Orphan but not yet deleted |
| Stale `__pycache__` cleanup | — | **Not started** | Cosmetic — 33 stale .pyc files |

---

## Phase B — Remaining Work

### PR-004: EventEmitter Cleanup
- Delete `src/core/events/` (zero production importers)
- Separate subsystem from orchestration — independent risk profile

### PR-005+: Orphan File Cleanup
- `application/api/app/chat_endpoints.py` — imports deleted `core.multi_agent.agent`
- `application/api/app/api_server.py` — orphan FastAPI app, not wired to production server
- `infrastructure/testing/production_scenarios.py` — zero importers (may already be deleted)

---

## Test Suite Health

| Metric | Pre PR-002 | Post PR-003 | Target |
|--------|-----------|-------------|--------|
| Collection errors | 25 | 16 | 0 |
| Skipped (stub modules) | 5 | 5 | 0 (requires implementations) |
| Passing | — | — | All collected |

### Remaining 16 Test Collection Errors (pre-existing)

| Test File | Broken Import | Root Cause |
|-----------|--------------|------------|
| `test_aikicad_agent.py` | `WriteBoundaryGuard` from `domains.safety` | Symbol not exported |
| `test_embedded_agent_regression.py` | `src.benchmarking` | Module never existed |
| `test_events.py` | `src.events` | Top-level redirect deleted (PR-002) |
| `test_flash_tools.py` | `FlashTool` from `core.tools.flash_tools` | Symbol not exported |
| `test_hardware.py` | `src.hardware` | Module never existed |
| `test_hardware_engine.py` | `HardwareModels` from `domains.hardware_engine.core.models` | Symbol not exported |
| `test_learning.py` | `src.learning` | Module never existed |
| `test_observability.py` | `src.observability` | Module never existed |
| `test_p4_retrieval.py` | `ChunkRecord` from `src.models` | Symbol not exported |
| `test_p5_memory.py` | Various | Broken import chain |
| `test_p7_hardware.py` | Various | Broken import chain |
| `test_p9_production_concepts.py` | Various | Broken import chain |
| `test_phase15.py` | Various | Broken import chain |
| `test_phase4.py` | Various | Broken import chain |
| `test_retrieval_manifest.py` | Various | Broken import chain |
| `test_retrieval_search_cache.py` | Various | Broken import chain |

---

## Architecture Metrics

| Metric | Value | Trend |
|--------|-------|-------|
| Python source files (excl. Electron) | ~1,296 | -108 from PR-003 |
| Test files | ~351 | -24 from PR-003 |
| Orchestration paths | 1 (RealAgent) | Was 4 |
| External LLM dependencies | 4 (openai, anthropic, ollama, langchain) | Was 5 (- langgraph) |
| Production server imports | 10 modules | Unchanged |
| Dead subsystems remaining | 1 (`core/events/`) | Was 5 |

---

## Next Actions (Priority Order)

1. **PR-004**: Delete `core/events/` — zero importers, clean cut
2. **Fix 16 test collection errors** — redirect broken imports or delete dead test files
3. **Clean stale `__pycache__`** — `find . -name __pycache__ -exec rm -rf {} +`
4. **Delete orphan files** — `chat_endpoints.py`, `api_server.py`
5. **Regenerate `egg-info`** — `pip install -e .`
6. **Import convention unification** — PR-009 scope (dual `src.` vs bare imports)
