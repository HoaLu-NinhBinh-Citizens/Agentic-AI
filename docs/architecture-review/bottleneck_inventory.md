# Bottleneck Inventory

> **Date**: 2026-06-14
> **As of commit**: `a2042cb` (post PR-003)

---

## B-01: Broken Test Suite (16 Collection Errors)

**Root cause**: 16 test files import from modules that don't exist or from symbols that aren't exported. `python -m pytest tests/` aborts with 16 errors and zero passing tests visible.

**Evidence**: `python -m pytest tests/ -q --tb=no` -> `Interrupted: 16 errors during collection`

**Affected modules**: 16 test files in `tests/` root, all CI/CD pipelines

| Impact | Rating |
|--------|--------|
| Scalability | None |
| Latency | None |
| Memory | None |
| Reliability | **Critical** — no regression detection possible |
| Edit quality | **Critical** — cannot validate suggestion engine changes |
| Retrieval quality | **Critical** — cannot validate retrieval changes |

---

## B-02: 10 Legacy Redirect Packages (Dual Import Paths)

**Root cause**: `src/runtime`, `src/tools`, `src/hardware_engine`, `src/config`, `src/health`, `src/llm`, `src/models`, `src/parsing`, `src/security`, `src/scheduler` are "Legacy alias" stubs re-exporting from canonical locations. Zero production importers.

**Evidence**: `rg "Legacy alias" src/ --type py` -> 10 hits. `rg "from src\.<pkg>" src/ --type py` excluding self -> 0 external callers for all 10.

**Affected modules**: ~43 files, ~1,810 lines of dead code; 16 test files using redirect imports

| Impact | Rating |
|--------|--------|
| Scalability | None |
| Latency | None |
| Memory | None |
| Reliability | **High** — two import paths for same symbols cause silent drift |
| Edit quality | **Medium** — developers may edit wrong module |
| Retrieval quality | **Low** — inflates codebase, retrieval returns dead files |

---

## B-03: Dead `core/events/` Subsystem

**Root cause**: EventEmitter (6 files, 1,366 lines) was infrastructure for deleted orchestration systems. Zero production importers.

**Evidence**: `rg "from.*core\.events|import.*core\.events" src/ --type py` -> only self-imports.

**Affected modules**: `src/core/events/` (6 files)

| Impact | Rating |
|--------|--------|
| Scalability | None |
| Latency | None |
| Memory | None |
| Reliability | **Low** — dead code, no runtime risk |
| Edit quality | None |
| Retrieval quality | **Low** — dead code appears in search results |

---

## B-04: Orphan `application/api/app/` Files

**Root cause**: `chat_endpoints.py` imports from deleted `core.multi_agent.agent`. `api_server.py` is an unwired alternative FastAPI app. `dashboard_websocket.py` has zero importers.

**Evidence**: grep confirms zero external importers for all three files.

**Affected modules**: 3 files in `application/api/app/`

| Impact | Rating |
|--------|--------|
| Scalability | None |
| Latency | None |
| Memory | None |
| Reliability | **Low** — broken imports would crash if touched |
| Edit quality | None |
| Retrieval quality | **Low** — dead code in search |

---

## B-05: Anthropic Streaming Not Implemented

**Root cause**: `infrastructure/llm/llm_manager.py` AnthropicProvider streaming stub returns `"Anthropic streaming not yet implemented"` as a single chunk. Claude API calls cannot stream.

**Evidence**: Source code in `llm_manager.py` — `yield StreamChunk(content="Anthropic streaming not yet implemented", done=True)`

**Affected modules**: `infrastructure/llm/llm_manager.py`, `core/agent/real_agent.py`, all Anthropic-backed features

| Impact | Rating |
|--------|--------|
| Scalability | **Medium** — must wait for full response before rendering |
| Latency | **Critical** — perceived latency 5-30x worse without streaming |
| Memory | **Medium** — full response buffered in memory |
| Reliability | **Medium** — no partial results on timeout |
| Edit quality | **High** — no incremental patch preview |
| Retrieval quality | None |

---

## B-06: Completion Engine Ollama-Only

**Root cause**: `infrastructure/completion/completion_engine.py` only supports Ollama models (codellama, deepseek-coder, qwen2.5-coder). No OpenAI or Anthropic completion support.

**Evidence**: Source code — `OllamaCompletionAdapter` is the only adapter. FIM template uses CodeLlama format.

**Affected modules**: `infrastructure/completion/`, all inline completion features

| Impact | Rating |
|--------|--------|
| Scalability | **Low** — limited to local Ollama |
| Latency | **Medium** — local models are fast but quality limited |
| Memory | **Low** |
| Reliability | **Medium** — requires local Ollama running |
| Edit quality | **High** — completion quality limited by local model capability |
| Retrieval quality | None |

---

## B-07: Lexical Search O(N) Full Scan

**Root cause**: `infrastructure/retrieval/hybrid.py` line 55 — `for chunk in self.chunk_store.get_all()` scans entire chunk store per query. No inverted index, no BM25, no FTS.

**Evidence**: Source code — `_search_chunk_store()` iterates all chunks.

**Affected modules**: `infrastructure/retrieval/hybrid.py`, all retrieval-dependent features

| Impact | Rating |
|--------|--------|
| Scalability | **Critical** — O(N*Q) where N=chunks, Q=queries; 100K chunks = 100K iterations per query |
| Latency | **High** — grows linearly with codebase size |
| Memory | **Medium** — all chunks loaded in memory |
| Reliability | **Low** — functional but slow |
| Edit quality | **Medium** — slow retrieval degrades suggestion pipeline |
| Retrieval quality | **Low** — results are correct, just slow |

---

## B-08: Context Builder Minimal (No Retrieval Integration)

**Root cause**: `infrastructure/llm/context_builder.py` builds context from file-local analysis (function name, class, imports, type hints) but doesn't integrate with retrieval pipeline or token budget system. Hard-coded limits (10 imports, 5 call chain, 500 char docstring).

**Evidence**: Source code — `compress_context()` uses static truncation. No reference to `retrieval/` or `context_budget.py`.

**Affected modules**: `infrastructure/llm/context_builder.py`, prompt quality for all LLM calls

| Impact | Rating |
|--------|--------|
| Scalability | **Low** |
| Latency | **Low** |
| Memory | **Low** |
| Reliability | **Low** |
| Edit quality | **High** — LLM sees truncated/irrelevant context |
| Retrieval quality | **High** — retrieved evidence not packed into prompts |

---

## B-09: No Structured Tool Calling (Function Calling)

**Root cause**: `core/agent/real_agent.py` sends free-text prompts and parses responses. No OpenAI function_call schema, no Anthropic tool_use, no structured output enforcement for tool invocations.

**Evidence**: Source code — RealAgent uses `llm_manager.stream()` with plain messages. No tool schemas in request.

**Affected modules**: `core/agent/real_agent.py`, `application/orchestration/tool_execution/`, MCP integration

| Impact | Rating |
|--------|--------|
| Scalability | **Low** |
| Latency | **Medium** — parsing free-text tool calls adds overhead |
| Memory | **Low** |
| Reliability | **High** — free-text parsing is fragile, hallucination-prone |
| Edit quality | **High** — tool call errors degrade edit pipeline |
| Retrieval quality | **Medium** — retrieval tool calls may be malformed |

---

## B-10: Indexing Dependency Graph Explosion

**Root cause**: `infrastructure/indexing/incremental.py` `mark_dirty_with_dependents()` traverses full transitive closure of dependency graph. No cycle detection. Single file change on a widely-imported module triggers cascade re-index of entire codebase.

**Evidence**: Source code — BFS traversal without visited-set cycle guard (no `seen` check before enqueuing).

**Affected modules**: `infrastructure/indexing/incremental.py`, background indexing

| Impact | Rating |
|--------|--------|
| Scalability | **High** — O(V+E) cascade on common imports |
| Latency | **High** — re-indexing blocks retrieval updates |
| Memory | **Medium** — queue grows unbounded |
| Reliability | **Medium** — infinite loop on circular imports |
| Edit quality | **Low** — stale index until re-index completes |
| Retrieval quality | **Medium** — stale chunks served during cascade |

---

## B-11: Memory System Unbounded Growth

**Root cause**: `core/memory/store.py` loads entire `.agent_memory.json` into memory. No size limit, no LRU eviction on the data dict. `governance/governance_engine.py` defines TTL retention policies but no background cleanup enforces them.

**Evidence**: Source code — `_lazy_load()` does `json.load(entire file)`. No size check on `_data`.

**Affected modules**: `core/memory/store.py`, `core/memory/governance/`

| Impact | Rating |
|--------|--------|
| Scalability | **Medium** — OOM on 10K+ memory items |
| Latency | **Medium** — load time grows with memory size |
| Memory | **High** — unbounded growth |
| Reliability | **Medium** — OOM crash |
| Edit quality | **Low** |
| Retrieval quality | **Low** |

---

## B-12: Multiple Competing Agent Implementations

**Root cause**: `core/agent/` contains RealAgent (365 LOC, live), CodexAgent (619 LOC, stub), PlanModeAgent (792 LOC, partial), EnhancedAgentHarness (607 LOC, wrapper), ReasoningLoop (683 LOC, hardware-only). Only RealAgent is on the production path.

**Evidence**: `interfaces/server/main.py` imports only `RealAgent`. CodexAgent has `Action` and `Session` data classes but no execution logic.

**Affected modules**: `core/agent/` (16 files, 7,034 LOC total)

| Impact | Rating |
|--------|--------|
| Scalability | None |
| Latency | None |
| Memory | None |
| Reliability | **Medium** — confusion about which agent to extend |
| Edit quality | **Medium** — features added to wrong agent class |
| Retrieval quality | **Low** — dead agent code in search results |

---

## B-13: Blocking File I/O in Async Indexing Loop

**Root cause**: `infrastructure/indexing/incremental.py` `_index_file()` calls `path.read_text()` synchronously inside an async function, blocking the event loop.

**Evidence**: Source code — `path.read_text()` without `asyncio.to_thread()`.

**Affected modules**: `infrastructure/indexing/incremental.py`

| Impact | Rating |
|--------|--------|
| Scalability | **Medium** — event loop stalls during indexing |
| Latency | **Medium** — blocks other async tasks |
| Memory | **Low** |
| Reliability | **Low** |
| Edit quality | **Low** |
| Retrieval quality | **Low** — stale results while blocked |

---

## B-14: Stale `__pycache__` and Build Artifacts

**Root cause**: PR-003 deleted `.py` files but `.pyc` files remain in `core/multi_agent/`, `core/orchestration/`, `multi_agent/`. Python can import `.pyc` when `.py` is missing.

**Evidence**: 33 stale `.pyc` files on disk in deleted package directories.

**Affected modules**: Build artifacts only

| Impact | Rating |
|--------|--------|
| Scalability | None |
| Latency | None |
| Memory | None |
| Reliability | **Low** — edge case shadow imports |
| Edit quality | None |
| Retrieval quality | None |
