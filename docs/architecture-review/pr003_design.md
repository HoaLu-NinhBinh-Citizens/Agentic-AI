# PR-003 Design — Consolidate Orchestration System

> **Document type**: Design — no code modified.
> **Date**: 2026-06-13
> **Author**: Principal Engineer review
> **Status**: READY FOR IMPLEMENTATION
> **Depends on**: PR-001 (merged), PR-002 (implemented)

---

## 1. Goal

Delete all unchosen orchestration namespaces. The production server (`interfaces/server/main.py`) uses **RealAgent** as its sole orchestration path and **ToolExecutionService** from `application/orchestration/tool_execution/` for tool execution. Three other orchestration subsystems exist with zero production callers. Delete them.

### Root Cause Addressed

**RC-1: Speculative scaffolding never pruned.** During phased development, three separate orchestration systems were built (LangGraph-based, multi-agent coordination, application-layer supervisor/agents) but none were wired into the production server. The production path is `RealAgent`, which bypasses all three.

---

## 2. Why PR-003 Is Next in Dependency Order

1. **PR-001** (security hardening) — merged.
2. **PR-002** (delete dead code trees) — implemented (Tier 1 + Tier 2 packages deleted).
3. **PR-003** (consolidate orchestration) — next Phase B item per `pr_breakdown.md`. It is the second sub-phase of T-01 (dead code audit & consolidation).
4. PR-002 reduced file count, making this audit smaller and more confident.

PR-003 should NOT be merged with PR-004 (EventEmitter) because they touch different subsystems with different risk profiles. PR-003 deletes large orchestration trees; PR-004 resolves a small event system. Keeping them separate allows independent rollback.

---

## 3. Decision Gate: Orchestration Path

**Decision**: Keep **RealAgent-only** path.

**Evidence**:

| System | Location | Production Callers from `main.py` | Verdict |
|--------|----------|-----------------------------------|---------|
| RealAgent | `core/agent/real_agent.py` | Yes — `main.py:43,77,135` imports and instantiates it | **KEEP** |
| ToolExecutionService | `application/orchestration/tool_execution/` | Yes — `main.py:41-42` imports config and service | **KEEP** |
| LangGraph orchestration | `core/orchestration/` (6 files) | None — only self-imports + 1 import from `core/multi_agent/__init__.py` | **DELETE** |
| Multi-agent coordination | `core/multi_agent/` (42 files) | None — external callers are all orphans (see §4) | **DELETE** |
| Multi-agent redirect | `src/multi_agent/` (3 files) | None — only test files import it | **DELETE** |
| Application agents/supervisor | `application/orchestration/{agents,supervisor,coordination,recovery,routing}/` (14 files) | None — only self-imports within the subtree | **DELETE** |

---

## 4. Scope

### 4.1 Source Files to Delete

#### Group A: `src/core/orchestration/` — LangGraph orchestration (6 files)

| File | Importers Outside Self | Evidence |
|------|----------------------|----------|
| `__init__.py` | `core/multi_agent/__init__.py` (also being deleted) | Grep verified |
| `langgraph_agent.py` | `core/orchestration/__init__.py` (self) | Grep verified |
| `langgraph_workflow.py` | `langgraph_agent.py`, `__init__.py` (self) | Grep verified |
| `queue.py` | `__init__.py` (self) | Grep verified |
| `rollback.py` | `__init__.py` (self) | Grep verified |
| `task_orchestrator.py` | None | Grep verified |

**Confidence**: High — zero production callers.

#### Group B: `src/core/multi_agent/` — Multi-agent system (42 files)

Sub-packages:
- `core.py`, `agent.py`, `pdf_knowledge_agent.py`, `__init__.py`, `EXPERIMENTAL.md` — Core agent types
- `coordination/` (38 files) — Enterprise coordination subsystem (circuit breaker, leader election, quota, tenant isolation, etc.)

External importers (all non-production):
- `src/multi_agent/` — redirect layer (Group C, also being deleted)
- `application/api/app/chat_endpoints.py` — imported by `api_server.py`, which is an orphan FastAPI app NOT wired into `interfaces/server/main.py`
- `application/api/app/aikicad_orchestrator.py` → imported only by `review_ui.py` → imported only by test
- `infrastructure/testing/production_scenarios.py` → zero importers (lazy import of `AgentCoordinator` inside a function)

**Confidence**: High — zero production callers traced through to `main.py`.

#### Group C: `src/multi_agent/` — Redirect layer (3 files)

| File | External Importers |
|------|-------------------|
| `__init__.py` | Test files only (`test_aikicad_agent.py`, `test_multi_agent.py`) |
| `agent.py` | Test files only (`test_multi_agent.py`, `test_firmware_agent_v2.py`) |
| `pdf_knowledge_agent.py` | Test file only (`test_aikicad_agent.py`) |

**Confidence**: High — zero production callers.

#### Group D: `src/application/orchestration/` dead subtrees (14 files)

All files under `application/orchestration/` EXCEPT `tool_execution/` (which is live):
- `agents/` (5 files: `__init__.py`, `executor_agent/__init__.py`, `planner_agent/__init__.py`, `reviewer_agent/__init__.py`, `verifier_agent/__init__.py`)
- `supervisor/` (5 files: `__init__.py`, `autoscaler/__init__.py`, `escalation/__init__.py`, `monitoring/__init__.py`, `supervisor/__init__.py`)
- `coordination/__init__.py` (1 file)
- `recovery/__init__.py` (1 file)
- `routing/__init__.py` (1 file)
- `__init__.py` (1 file — empty, but re-check before deleting)

External importers: Only self-imports within the subtree (`supervisor/supervisor/__init__.py` → `agents/planner_agent`, `agents/executor_agent/__init__.py` → `agents/planner_agent`). Zero imports from `main.py` or any production path.

**Confidence**: High. Note: `application/orchestration/__init__.py` is empty (1 line). Deleting it does not affect `tool_execution/` which is imported via full path `application.orchestration.tool_execution.config`.

**NEED MORE EVIDENCE**: Verify that deleting `application/orchestration/__init__.py` does not break `from application.orchestration.tool_execution import ...` in Python's import resolution. If `application/orchestration/` becomes a namespace package (no `__init__.py`), Python 3 implicit namespace packages should handle this. Verify during implementation.

#### Summary

| Group | Directory | Files | Risk |
|-------|-----------|-------|------|
| A | `src/core/orchestration/` | 6 | Zero |
| B | `src/core/multi_agent/` | 42 | Low |
| C | `src/multi_agent/` | 3 | Zero |
| D | `application/orchestration/` dead subtrees | 14 | Low |
| **Total** | | **65** | |

### 4.2 Test Files to Delete

| Test File | Imports From | Other Live Imports | Action |
|-----------|-------------|-------------------|--------|
| `tests/test_orchestration.py` | `src.orchestration` (does not exist) | None | **Delete** — already broken |
| `tests/test_multi_agent.py` | `src.multi_agent.agent` | None | **Delete** — only dead imports |
| `tests/test_firmware_agent_v2.py` | `src.multi_agent.agent` | None | **Delete** — only dead imports |
| `tests/test_review_agent.py` | `src.core.multi_agent.agent` | None | **Delete** — only dead imports |
| `tests/phase5d/test_coordination.py` | `src.core.multi_agent.coordination.*` | None | **Delete** — only dead imports |
| `tests/phase5d/test_enhanced_coordination.py` | `src.core.multi_agent.coordination.*` | None | **Delete** — only dead imports |
| `tests/phase5e/test_distributed_execution.py` | `src.core.multi_agent.coordination.*` | None | **Delete** — only dead imports |
| `tests/phase5e/test_extended.py` | `src.core.multi_agent.coordination.*` | None | **Delete** — only dead imports |
| `tests/phase5f/test_reliability_governance.py` | `src.core.multi_agent.coordination.*` | None | **Delete** — only dead imports |
| `tests/phase5f/test_enhanced_reliability.py` | `src.core.multi_agent.coordination.*` | None | **Delete** — only dead imports |

**Tests to delete: 10**

Also delete empty `__init__.py` in test phase directories if they become empty:
- `tests/phase5d/__init__.py` (if no other files remain)
- `tests/phase5f/__init__.py` (if no other files remain)
- Check if `tests/phase5e/` needs an `__init__.py` created or if the directory should just be deleted

### 4.3 Test Files to Update (remove dead imports, keep file)

| Test File | Dead Import | Live Imports | Action |
|-----------|------------|-------------|--------|
| `tests/test_aikicad_agent.py` | `src.multi_agent.pdf_knowledge_agent` (line 23) | `src.domains.*` (14 modules), `src.application.api.app.*` | **UPDATE** — remove line 23 |
| `tests/integration/production_test.py` | `src.core.multi_agent.coordination.coordinator` (line 171, inside function) | 9+ live packages | **UPDATE** — remove function `test_multi_agent_coordination` or remove the dead import and skip the test |

**Tests to update: 2**

### 4.4 Other Files to Modify

| File | Change | Reason |
|------|--------|--------|
| `application/api/app/chat_endpoints.py` | Remove or delete | Imports from `core.multi_agent.agent`. Only imported by orphan `api_server.py`. If `api_server.py` is also orphan, both can be deleted. **NEED MORE EVIDENCE** on whether `api_server.py` is used by any deployment path. |
| `application/api/app/aikicad_orchestrator.py` | Remove line 15 (`from src.core.multi_agent.pdf_knowledge_agent import PDFKnowledgeAgent`) | Dead import after `core/multi_agent/` deletion. File itself is only imported by `review_ui.py` → test. |
| `infrastructure/testing/production_scenarios.py` | Remove function containing `AgentCoordinator` import (line 100) | Lazy import of deleted module. File has zero importers anyway. |
| `pyproject.toml` line 28 | Remove `"langgraph>=0.2.0"` dependency | Zero remaining imports after `core/orchestration/` deletion |

**PRECONDITION for `chat_endpoints.py` and `api_server.py`**: These files are part of `application/api/app/` which also contains live files (`embedded_agent.py` used by `core/agent/autonomous_loop.py`). Do NOT delete the entire `application/api/app/` directory. Only modify/delete individual orphan files that exclusively import from deleted modules. Verify `api_server.py` and `chat_endpoints.py` have zero importers from production code before deleting them.

---

## 5. Out of Scope

| Item | Reason |
|------|--------|
| `src/core/events/` | PR-004 scope. Zero importers confirmed, but separate PR for separate subsystem. |
| `src/application/api/app/` wholesale deletion | Contains live files (`embedded_agent.py`). Only orphan files referencing dead modules can be touched. |
| `application/orchestration/tool_execution/` | Live — used by `main.py` |
| `core/agent/real_agent.py` | Production agent — MUST NOT touch |
| Any enhancement to RealAgent | No refactoring of surviving orchestration |
| `src/domains/` | Live code — PR-002 confirmed 49 production importers |
| `src/infrastructure/hsm/` | Live code — domain layer depends on it |
| Import convention changes | PR-009 scope |
| Any new abstractions or orchestration wrappers | Deletion only |

---

## 6. Files That MUST NOT Be Modified

| File / Directory | Reason |
|-----------------|--------|
| `src/core/agent/` | Production agent code |
| `src/interfaces/server/main.py` | Production server — no dead imports from target packages |
| `src/application/orchestration/tool_execution/` | Live tool execution service used by main.py |
| `src/application/api/app/embedded_agent.py` | Live — imported by `core/agent/autonomous_loop.py` |
| `src/domains/` | Live production code |
| `src/domain/` | Live domain layer |
| `src/infrastructure/` (except `testing/production_scenarios.py`) | Live infrastructure |
| `src/core/events/` | PR-004 scope |
| `pyproject.toml` entry points | Frozen per architecture_freeze.md |
| Any WebSocket/REST protocol | Frozen per architecture_freeze.md |

---

## 7. Runtime Impact

**None.** All deleted code has zero callers from the production server. The production chat path (`main.py` → `RealAgent` → `ToolExecutionService`) is untouched.

---

## 8. API Impact

**None.** No REST endpoints, WebSocket messages, or MCP protocol changes. All frozen APIs preserved.

---

## 9. Storage Impact

**None.** No database schema changes. No new tables, columns, or files.

---

## 10. Test Strategy

### Pre-Implementation

| Check | Method | Pass Criteria |
|-------|--------|---------------|
| Baseline test counts | `python -m pytest tests/` | Record exact pass/skip/error/fail counts |
| Baseline file count | `find src -name "*.py" \| wc -l` | Record exact count |
| Dynamic import audit | Grep for `importlib.import_module`, `__import__` referencing target package names | Zero hits in production code |
| Non-Python reference audit | Grep yaml/toml/json/sh/ps1/md for `core.orchestration`, `core.multi_agent`, `multi_agent` | Zero production-relevant hits |
| `application/orchestration/__init__.py` deletion safety | Verify `from application.orchestration.tool_execution.config import ...` still resolves without `__init__.py` | Import succeeds |

### Post-Implementation

| Check | Method | Pass Criteria |
|-------|--------|---------------|
| Server starts | `python -c "from interfaces.server.main import app"` (from `src/`) | No ImportError from deleted packages |
| Test suite | `python -m pytest tests/` | Pass count >= baseline minus deleted tests. Error count reduced. |
| File count reduced | `find src -name "*.py" \| wc -l` | Reduced by ~65 |
| Dead imports gone | Grep for `core.orchestration`, `core.multi_agent`, `src.multi_agent` in surviving code | Zero hits |
| `import src.core.orchestration` fails | `python -c "import src.core.orchestration"` | `ModuleNotFoundError` |
| `import src.core.multi_agent` fails | `python -c "import src.core.multi_agent"` | `ModuleNotFoundError` |
| langgraph no longer imported | `grep -r "langgraph" src/` | Zero hits |
| ToolExecutionService still works | `python -c "from application.orchestration.tool_execution.config import get_tool_execution_config"` (from `src/`) | No ImportError |

---

## 11. Rollback Strategy

### Structure: 3 commits

| Commit | Content | Risk | Independently Revertable |
|--------|---------|------|--------------------------|
| 1 | Update test files (remove dead imports from 2 surviving test files) | Zero | Yes |
| 2 | Delete `core/orchestration/` (6 files) + `core/multi_agent/` (42 files) + `src/multi_agent/` (3 files) + 10 test files + test phase dirs | Medium | Yes |
| 3 | Delete `application/orchestration/` dead subtrees (14 files) + update orphan files in `application/api/app/` + remove langgraph from pyproject.toml | Low | Yes |

**Rationale**: Commit 1 (test updates) must land before Commit 2. Commit 3 is separated because `application/orchestration/` requires more care (live `tool_execution/` sibling).

### Trigger

- Server fails to start (ImportError)
- Any previously passing test fails unexpectedly
- `ToolExecutionService` import breaks
- Any file in the do-not-delete list is missing

### Procedure

1. `git revert <commit-hash>` — start with latest commit
2. Verify: `python -m pytest tests/` — same counts as baseline
3. Verify: server starts without import errors

---

## 12. Success Criteria

| Criterion | Metric |
|-----------|--------|
| All dead orchestration packages deleted | 65 source files removed |
| Single orchestration path remains | `RealAgent` + `ToolExecutionService` only |
| Server starts without import errors | Import check passes |
| Test suite improved | Error count reduced; pass count unchanged for surviving tests |
| No live code deleted | `core/agent/`, `application/orchestration/tool_execution/`, `embedded_agent.py` untouched |
| No live test coverage lost | 2 test files updated, not deleted |
| `langgraph` dependency removed | Zero remaining imports of `langgraph` in `src/` |

---

## 13. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| R1 | `application/orchestration/__init__.py` deletion breaks `tool_execution` import path | Low | High — server fails to start | Test import resolution before and after. Python 3 namespace packages handle missing `__init__.py`. If broken: keep empty `__init__.py`. |
| R2 | Orphan files in `application/api/app/` (`chat_endpoints.py`, `api_server.py`) are used by an undiscovered deployment path | Low | Medium — breaks alternate deployment | Grep all config files (yaml, toml, json, Dockerfile, docker-compose, sh, ps1) for references. Only delete if zero hits. |
| R3 | `langgraph` removal from `pyproject.toml` breaks installation for external users | Low | Low — additive re-add | Verify zero `import langgraph` in surviving code before removing. |
| R4 | Test phase directories (`phase5d/`, `phase5e/`, `phase5f/`) contain other test files not accounted for | Low | Low — incomplete deletion | Verify directory contents before deleting entire directories. |
| R5 | Undiscovered dynamic import of deleted package | Low | High — runtime ImportError | Grep for `importlib.import_module`, `__import__` targeting deleted packages. Zero hits confirmed. |

---

## 14. Blast Radius

| Dimension | Impact |
|-----------|--------|
| Production server | None — `main.py` does not import from any deleted package |
| REST/WebSocket API | None — no protocol changes |
| Database | None — no schema changes |
| Dependencies | `langgraph>=0.2.0` removed from `pyproject.toml` |
| Test suite | 10 test files deleted, 2 updated. ~6 test phase dir files removed. |
| Source files | ~65 `.py` files deleted (~4.3% of codebase) |
| External integrations | None |

---

## 15. Estimated Implementation Complexity

**Medium-Low.**

- Deletion is mechanical.
- The main complexity is in verifying `application/orchestration/__init__.py` deletion safety and handling orphan files in `application/api/app/`.
- No new code to write.
- Estimated time: 2-4 hours including verification.

---

## 16. Assumption Verification

| Assumption | Verified | Method | Result |
|------------|---------|--------|--------|
| A1: `main.py` uses RealAgent, not LangGraph or multi-agent | **YES** | Read `main.py` lines 43, 77, 135 | RealAgent imported and instantiated |
| A2: `core/orchestration/` has zero external production callers | **YES** | Grep across `src/` | Only self-imports + `core/multi_agent/__init__.py` |
| A3: `core/multi_agent/` has zero production callers reachable from `main.py` | **YES** | Traced all external importers: `src/multi_agent/` (redirect, test-only), `chat_endpoints.py` → `api_server.py` (orphan), `aikicad_orchestrator.py` → `review_ui.py` (test-only), `production_scenarios.py` (zero importers) | None reach `main.py` |
| A4: `src/multi_agent/` has zero production importers | **YES** | Grep `from src.multi_agent` / `from multi_agent` in `src/` | Zero hits |
| A5: `application/orchestration/` dead subtrees have zero external importers | **YES** | Grep for agents/supervisor/coordination/recovery/routing imports | Only self-imports within subtree |
| A6: `api_server.py` is not wired into production server | **YES** | Grep for `api_server` in `src/interfaces/` | Zero hits |
| A7: Phase test directories only test deleted modules | **YES** | Read imports in `phase5d/`, `phase5e/`, `phase5f/` tests | All import exclusively from `core.multi_agent.coordination` |
| A8: No dynamic imports target deleted packages | **YES** | Grep for `importlib.*orchestration`, `importlib.*multi_agent`, `__import__.*orchestration`, `__import__.*multi_agent` | Zero hits |
| A9: Deleting `application/orchestration/__init__.py` won't break tool_execution imports | **NEED MORE EVIDENCE** | Must test during implementation | Python 3 implicit namespace packages should handle this, but verify |
| A10: `chat_endpoints.py` and `api_server.py` have no deployment references | **NEED MORE EVIDENCE** | Need to grep Dockerfiles, CI configs, scripts | Not yet verified |

---

## 17. Conflicts with Planning Documents

| Document Claim | Reality | Impact |
|---------------|---------|--------|
| `pr_breakdown.md` says PR-003 file count depends on orchestration decision | Decision is clear: RealAgent. No ambiguity. | None — proceed. |
| `implementation_contract.md` says "delete unchosen orchestration namespace(s)" | There are FOUR unchosen namespaces, not one or two. Total is larger than expected. | Scope is larger but risk is the same — all have zero production callers. |
| `refactor_strategy.md` Phase B success criterion: "Single orchestration namespace" | After PR-003: `core/agent/` (RealAgent) + `application/orchestration/tool_execution/` (ToolExecutionService). Technically two namespaces, but one is agent orchestration, the other is tool execution. Both are production-used. | Success criterion met in spirit — single agent orchestration path. |
| `implementation_contract.md` PR-002 postcondition "File count reduced by >= 30%" | After PR-002 + PR-003 combined: ~97 files deleted out of ~1509. Still ~6.4%, not 30%. The 30% was based on incorrect assumption that `src/domains/` (125 files) was dead. | Not achievable without deleting live code. Postcondition should be revised. |

---

## STOP

**READY TO PREPARE PR-003 IMPLEMENTATION**

Decision gate passed: RealAgent is the production orchestration path, verified by reading `interfaces/server/main.py`. All other orchestration systems have zero production callers. Evidence is complete for all major assumptions except A9 and A10, which are low-risk and verifiable during implementation.
