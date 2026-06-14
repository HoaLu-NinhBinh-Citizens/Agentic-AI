# Cursor Gap Analysis

> **Date**: 2026-06-14
> **As of commit**: `a2042cb` (post PR-003)
> **Comparison target**: Production-grade AI Code Assistant (Cursor / Codex / Windsurf level)

---

## Maturity Scale

| Level | Definition |
|-------|-----------|
| **Prototype** | Basic structure exists. Core logic is stub or incomplete. Not usable for real work. |
| **Advanced Prototype** | Real implementation with significant gaps. Works for demos or limited use cases. |
| **Production Candidate** | Feature-complete for core scenarios. Needs hardening, optimization, or edge case handling. |
| **Production Grade** | Battle-tested. Scales to real workloads. Handles failures gracefully. Competitive with commercial tools. |

---

## STEP 7: Subsystem Audit

### Completion Engine

| Aspect | Status | Score | Notes |
|--------|--------|-------|-------|
| Inline completion | Ollama FIM only | Advanced Prototype | No cloud provider support |
| Prefix/suffix completion | 2048 char window | Advanced Prototype | No AST-aware boundary detection |
| Cancellation | asyncio.Event | Production Candidate | Works correctly |
| Debounce | 150ms configurable | Production Candidate | Good default |
| Streaming | Ollama token-by-token | Advanced Prototype | REF-5 fixes applied; no OpenAI/Anthropic |
| Scheduling | Single request | Prototype | No parallel/speculative completions |
| Prompt packing | CodeLlama FIM template | Advanced Prototype | Single template, no model-specific formats |
| Token budgeting | None | Prototype | No budget enforcement; can exceed window |
| Cache | LRU 512 entries, in-memory | Advanced Prototype | No persistent cache; no adaptive TTL |
| Reranking | None | **Not implemented** | Single completion returned, no quality filtering |

**Overall: Advanced Prototype**

**Why not higher**: Ollama-only limits quality ceiling. No reranking means first completion is final. No token budgeting risks context window overflow.

---

### Retrieval

| Aspect | Status | Score | Notes |
|--------|--------|-------|-------|
| Vector search | ChromaDB + NumPy fallback | Production Candidate | HNSW index, cosine similarity |
| Lexical search | O(N) full scan | **Prototype** | No inverted index, no BM25, no FTS |
| Hybrid retrieval | Weighted merge (65/35) | Production Candidate | Domain-aware scoring profiles |
| Reranking | Deterministic evidence-quality scoring | Advanced Prototype | Hardcoded weights, no learned reranker |
| Symbol awareness | Via infrastructure/analysis/ | Advanced Prototype | Call graph, imports; not integrated with retrieval |
| Dependency awareness | Indexer tracks imports | Advanced Prototype | Cascade re-index; no retrieval-time use |
| AST awareness | tree-sitter parsing | Advanced Prototype | Chunking doesn't respect function boundaries |

**Overall: Advanced Prototype**

**Why not higher**: O(N) lexical search is a scalability blocker. Symbol/dependency awareness exists in analysis layer but isn't wired into retrieval queries. AST-aware chunking doesn't align to logical blocks.

---

### Context Builder

| Aspect | Status | Score | Notes |
|--------|--------|-------|-------|
| Duplicate retrieval | No dedup between retrieval and context | Prototype | Multiple layers filter independently |
| Duplicate prompt construction | Single path | Advanced Prototype | No redundancy |
| Token waste | Hard-coded truncation (10 imports, 5 call chain) | Prototype | Static limits ignore relevance |
| Context ranking | Priority levels in context_budget.py | Advanced Prototype | Not integrated with context_builder |
| Packing strategy | Truncation only | Prototype | No knapsack-style packing |

**Overall: Prototype**

**Why not higher**: Context builder is 416 LOC of file-local analysis with static truncation. The `context_budget.py` (422 LOC) has priority-based pruning but isn't wired to the builder. Retrieved evidence doesn't flow into prompts through the builder.

---

### Indexing

| Aspect | Status | Score | Notes |
|--------|--------|-------|-------|
| Incremental indexing | Content hash diffing (MD5) | Production Candidate | Delta tracking with SQLite state DB |
| Full indexing | Parallel file hashing (4 workers) | Production Candidate | ThreadPoolExecutor |
| Background indexing | Async with Semaphore concurrency | Advanced Prototype | Blocking read_text() in async loop |
| Watcher architecture | watchdog.Observer + 2s debounce | Production Candidate | Stable, tested |
| Queue | Semaphore-bounded | Advanced Prototype | No priority queue |
| Batching | ChromaDB batch upsert | Production Candidate | Efficient |
| Concurrency | 4 workers default | Advanced Prototype | No adaptive scaling |

**Overall: Production Candidate**

**Why not higher**: Blocking I/O in async loop. No cycle detection in dependency graph. Semantic chunking doesn't respect function boundaries.

---

### Tool Execution

| Aspect | Status | Score | Notes |
|--------|--------|-------|-------|
| Worker pool | Single-threaded async | Advanced Prototype | No parallel tool execution |
| Retry | Exponential backoff + jitter | Production Candidate | PR-001 hardened |
| Timeout | Per-tool configurable | Production Candidate | Enforced |
| Cancellation | Per-call cancellation token | Production Candidate | Client-initiated |
| Queue | No queue; direct dispatch | Advanced Prototype | No admission control |
| Isolation | Capability-based sandbox defined | Advanced Prototype | Defined but not enforced |
| Sandbox | infrastructure/security/plugin_sandbox.py | Advanced Prototype | Unix-only resource limits |

**Overall: Advanced Prototype**

**Why not higher**: No structured tool calling from LLM. No parallel execution. Sandbox defined but enforcement is partial.

---

### Edit Engine

| Aspect | Status | Score | Notes |
|--------|--------|-------|-------|
| Atomic edit | Not implemented | Prototype | No transaction boundary |
| Transaction | Not implemented | **Not implemented** | No multi-file transaction |
| Rollback | Not implemented | **Not implemented** | No undo capability |
| Conflict resolution | Not implemented | **Not implemented** | No concurrent edit handling |
| Compile verification | Not implemented | **Not implemented** | No post-edit validation |
| Deterministic patching | Unified diff generation | Advanced Prototype | `patch_generator.py` (720 LOC) |

**Overall: Prototype**

**Why not higher**: Patch generation exists but there's no transaction model, no rollback, no conflict resolution, no compile verification. This is the weakest subsystem. Cursor has full edit transactions with undo.

---

### Memory

| Aspect | Status | Score | Notes |
|--------|--------|-------|-------|
| Session cache | TTLCache (cachetools) | Production Candidate | W-012 fix, bounded to 1000 |
| TTL | Defined in governance, not enforced | Advanced Prototype | Policy exists but no background cleanup |
| LRU | Experience/proposal caches | Advanced Prototype | Not on main data store |
| Snapshot | Event-sourced state in planner | Advanced Prototype | Separate system |
| Persistence | JSON file + SQLite sessions | Production Candidate | Atomic writes with fsync |
| Cleanup | No automatic cleanup | Prototype | Memory grows unbounded |

**Overall: Advanced Prototype**

**Why not higher**: Unbounded growth. TTL not enforced. No cleanup scheduler.

---

### Performance

| Aspect | Status | Score | Notes |
|--------|--------|-------|-------|
| O(N) scans | Lexical search in hybrid.py | Prototype | Critical scalability issue |
| IPC | stdio for MCP subprocess | Advanced Prototype | Functional but blocking under load |
| Serialization | JSON throughout | Production Candidate | Standard |
| Duplicate copies | Metadata scored twice in retrieval | Advanced Prototype | Redundant evidence quality pass |
| Blocking I/O | read_text() in async indexer | Advanced Prototype | Should use asyncio.to_thread() |
| Thread pool | ThreadPoolExecutor (4 workers) | Advanced Prototype | No adaptive sizing |
| Async model | asyncio throughout | Production Candidate | Consistent pattern |

**Overall: Advanced Prototype**

---

### Reliability

| Aspect | Status | Score | Notes |
|--------|--------|-------|-------|
| Retry | Exponential backoff + jitter | Production Candidate | PR-001 |
| Circuit breaker | Per-MCP-server + LLM | Production Candidate | 5 failures -> open, 30s recovery |
| Idempotency | Session save uses INSERT OR UPDATE | Production Candidate | |
| Rollback | Git-based only | Advanced Prototype | No application-level rollback |
| Recovery | Dead letter queue for failed tasks | Production Candidate | Full context capture |
| Fault isolation | Per-server circuit breakers | Production Candidate | Good design |

**Overall: Production Candidate**

---

## STEP 8: Summary Scorecard

| Subsystem | Score | Cursor-Level Gap |
|-----------|-------|-----------------|
| Completion Engine | **Advanced Prototype** | Needs cloud providers, reranking, token budget |
| Retrieval | **Advanced Prototype** | Needs lexical index (FTS/BM25), symbol integration |
| Context Builder | **Prototype** | Needs retrieval integration, token-aware packing |
| Indexing | **Production Candidate** | Minor: cycle detection, async I/O |
| Tool Execution | **Advanced Prototype** | Needs structured tool calling, parallel execution |
| Edit Engine | **Prototype** | Needs transactions, rollback, conflict resolution |
| Memory | **Advanced Prototype** | Needs size limits, TTL enforcement |
| Performance | **Advanced Prototype** | Needs lexical index, async I/O fixes |
| Reliability | **Production Candidate** | Minor gaps only |
| Server/API | **Production Candidate** | Solid FastAPI + WebSocket architecture |
| Session Management | **Production Candidate** | TTLCache, SQLite persistence |
| MCP Integration | **Production Candidate** | Tool discovery, circuit breakers |
| Router | **Production Candidate** | Semantic + rule-based routing |
| Security | **Advanced Prototype** | Framework exists, enforcement partial |
| Observability | **Production Candidate** | OTel, metrics, tracing, structured logs |
| Planner | **Advanced Prototype** | Feature-rich but not integrated with main agent |

### Aggregate Assessment

**Overall system maturity: Advanced Prototype**

The infrastructure layer (server, sessions, reliability, observability, MCP) is near production-grade. The AI-specific layers (completion, retrieval, context building, edit engine) are the gap. The codebase has enterprise-grade infrastructure wrapped around prototype-level AI capabilities.

### Critical Path to Production Grade

1. Fix test suite (Task A) — prerequisite for all validation
2. Anthropic streaming (Task B) — table-stakes for a Claude-powered assistant
3. Structured tool calling (Task C) — reliability foundation
4. Lexical search index (Task D) — scalability foundation
5. Context builder integration (Task E) — output quality foundation
6. Edit engine transactions (future) — competitive feature parity
