# Architecture Bottleneck Audit

> **Date**: 2026-06-14
> **As of commit**: `a2042cb` (post PR-003)
> **Author**: Principal Engineer
> **Purpose**: Complete engineering audit to determine the highest-ROI next PR

---

## 1. Audit Scope

Every subsystem was inspected against source code as the sole source of truth. Previous PR-004 design documents proposed deleting remaining dead code. This audit re-evaluates that decision against the full bottleneck inventory.

### Systems Audited

| System | Location | Files Read | Verdict |
|--------|----------|-----------|---------|
| Production server | `interfaces/server/main.py` | 677 LOC | Live, functional |
| Core agent | `core/agent/real_agent.py` | 365 LOC | Live, Ollama+OpenAI streaming |
| Completion engine | `infrastructure/completion/completion_engine.py` | 391 LOC | Live, Ollama-only FIM |
| LLM gateway | `infrastructure/llm/llm_manager.py` | 578 LOC | Live, multi-provider |
| Tool execution | `application/orchestration/tool_execution/` | 1,279 LOC | Live, middleware pipeline |
| Retrieval pipeline | `infrastructure/retrieval/` | 9,300+ LOC | Live, hybrid lexical+vector |
| Indexing pipeline | `infrastructure/indexing/` | 2,500+ LOC | Live, incremental+watchdog |
| Memory system | `core/memory/` | 5,600+ LOC | Live, JSON+semantic |
| Context builder | `infrastructure/llm/context_builder.py` | 416 LOC | Live, minimal |
| Session management | `core/session/` | 500+ LOC | Live, SQLite+TTLCache |
| Runtime subsystem | `core/runtime/` | 6,400+ LOC | Live, journal+replayer+backpressure |
| MCP integration | `infrastructure/mcp/manager.py` | 566 LOC | Live, stdio subprocess |
| Router | `infrastructure/router/` | 500+ LOC | Live, semantic+rule |
| Suggestion engine | `application/suggestion/` | 1,679 LOC | Live, patch generation |
| Planner | `application/planner/` | 6,400+ LOC | Live, event-sourced |
| Security | `infrastructure/security/` | 5,965+ LOC | Live, RBAC+sandbox |
| Observability | `infrastructure/observability/` | 1,500+ LOC | Live, OTel+metrics |
| Code analysis | `infrastructure/analysis/` | 1,000+ LOC | Live, AST+rules |
| Workspace | `core/workspace/` | 40 LOC | **Stub** |

### Production Path Verified

```
Client (WebSocket/REST)
  -> interfaces/server/main.py (FastAPI)
     -> core/agent/real_agent.py (RealAgent — LLM orchestration)
     -> application/orchestration/tool_execution/service.py (ToolExecutionService)
     -> core/runtime/runtime_manager.py (stream ownership + cancellation)
     -> core/session/persistent_manager.py (SQLite sessions + TTLCache)
     -> infrastructure/mcp/manager.py (tool discovery via servers.yaml)
     -> infrastructure/llm/llm_manager.py (OpenAI/Anthropic/Ollama)
     -> interfaces/server/websocket/manager.py (ConnectionManager)
```

All imports resolve. No broken chains.

---

## 2. Bottleneck Inventory

See [bottleneck_inventory.md](bottleneck_inventory.md) for the full catalog of 14 architectural bottlenecks.

## 3. ROI Ranking

See [roi_ranking.md](roi_ranking.md) for task clustering, estimation, and priority ranking.

## 4. Cursor Gap Analysis

See [cursor_gap_analysis.md](cursor_gap_analysis.md) for subsystem-by-subsystem maturity scoring.

## 5. Next PR Recommendation

See [next_pr_recommendation.md](next_pr_recommendation.md) for the single highest-ROI PR recommendation.

---

## 6. Key Finding

The previous PR-004 design (delete remaining dead code + fix broken tests) remains the correct next step. The bottleneck audit confirms that **no feature-level improvement can be safely built or validated** while the test suite has 16 collection errors, 10 legacy redirect packages confuse import resolution, and ~85 dead files inflate the codebase.

Every bottleneck identified in this audit (Anthropic streaming, O(N) lexical search, context builder weakness, etc.) requires working tests to validate. The dead code cleanup is the foundation that unblocks all subsequent work.

**Source code confirms**: the existing PR-004 design documents are accurate. No corrections needed.
