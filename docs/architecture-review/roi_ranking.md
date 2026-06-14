# ROI Ranking

> **Date**: 2026-06-14
> **As of commit**: `a2042cb` (post PR-003)

---

## 1. Task Clustering

Each task solves ONE architectural problem. Bottlenecks from [bottleneck_inventory.md](bottleneck_inventory.md) are grouped by causal relationship.

### Task A: Delete Remaining Dead Code + Fix Broken Test Suite

**Bottlenecks addressed**: B-01, B-02, B-03, B-04, B-14

**Problem**: 16 test collection errors, 10 legacy redirect packages, dead `core/events/`, orphan files, stale `__pycache__`. The test suite is unusable.

**Scope**: Delete ~85 files (~3,576 lines), update 8 test import files, delete 6 dead test files, investigate 10 case-by-case test files.

---

### Task B: Implement Anthropic Streaming

**Bottlenecks addressed**: B-05

**Problem**: Anthropic provider returns a single non-streamed chunk. Claude API calls have 5-30x worse perceived latency.

**Scope**: Implement async streaming in `AnthropicProvider` using `anthropic` SDK's `messages.stream()`.

---

### Task C: Add Structured Tool Calling (Function Calling)

**Bottlenecks addressed**: B-09

**Problem**: RealAgent uses free-text tool invocations parsed from LLM output. No function_call schema, no tool_use structured output.

**Scope**: Add OpenAI function calling schema and Anthropic tool_use to RealAgent's LLM calls. Parse structured tool_call responses.

---

### Task D: Add Lexical Search Index (BM25/FTS)

**Bottlenecks addressed**: B-07

**Problem**: Lexical search iterates all chunks per query. O(N) per query.

**Scope**: Replace `get_all()` scan with SQLite FTS5 or in-memory inverted index in `hybrid.py`.

---

### Task E: Integrate Context Builder with Retrieval + Token Budget

**Bottlenecks addressed**: B-08

**Problem**: Context builder ignores retrieval results and token budget. Hard-coded truncation limits.

**Scope**: Wire `context_builder.py` to `retrieval/context_budget.py`. Replace static limits with token-aware packing.

---

### Task F: Add Indexing Dependency Cycle Detection

**Bottlenecks addressed**: B-10

**Problem**: Dependency graph traversal has no cycle detection. Circular imports cause infinite cascade re-indexing.

**Scope**: Add visited-set check in `mark_dirty_with_dependents()`. Cap cascade depth.

---

### Task G: Add Memory Size Limits + TTL Enforcement

**Bottlenecks addressed**: B-11

**Problem**: Agent memory grows unbounded. TTL policies defined but not enforced.

**Scope**: Add LRU eviction to `store.py`. Implement background TTL cleanup.

---

### Task H: Consolidate Agent Implementations

**Bottlenecks addressed**: B-12

**Problem**: 5 agent implementations, only 1 on production path. Others are stubs or hardware-specific.

**Scope**: Delete or archive CodexAgent, mark others as non-production.

---

### Task I: Fix Blocking I/O in Async Indexer

**Bottlenecks addressed**: B-13

**Problem**: `path.read_text()` blocks event loop in async indexing function.

**Scope**: Wrap in `asyncio.to_thread()`.

---

### Task J: Extend Completion Engine to Cloud Providers

**Bottlenecks addressed**: B-06

**Problem**: Completion engine only supports local Ollama models.

**Scope**: Add OpenAI and Anthropic completion adapters.

---

## 2. Task Estimation

| Task | Complexity | Effort | Migration Risk | Rollback Complexity | Latency Improvement | Retrieval Improvement | Edit Accuracy Improvement | Reliability Improvement | Scalability Improvement |
|------|-----------|--------|---------------|--------------------|--------------------|----------------------|--------------------------|------------------------|------------------------|
| **A** | Medium-Low | 2-3 hours | Zero | Low (git revert) | None | None | None | **Critical** (unblocks test suite) | None |
| **B** | Low | 1-2 hours | Low | Low | **Critical** (5-30x perceived latency) | None | Medium | Medium | Low |
| **C** | Medium | 4-8 hours | Medium | Medium | Low | Medium | **High** | **High** | Low |
| **D** | Medium | 4-8 hours | Low | Low | **High** (O(N)->O(log N)) | **High** | Low | Low | **Critical** |
| **E** | Medium | 3-5 hours | Low | Low | Low | **High** | **High** | Low | Low |
| **F** | Low | 1-2 hours | Low | Low | Medium | Medium | None | Medium | Medium |
| **G** | Low | 2-3 hours | Low | Low | Low | None | None | Medium | Medium |
| **H** | Low | 1-2 hours | Low | Low | None | None | None | Low | None |
| **I** | Trivial | 30 min | Zero | Zero | Low | Low | None | Low | Low |
| **J** | Medium-High | 8-16 hours | Medium | Medium | Low | None | Medium | Medium | Low |

---

## 3. Priority Ranking

### P0: Task A — Delete Remaining Dead Code + Fix Broken Test Suite

**Why P0**: Every other task requires a working test suite to validate. With 16 collection errors, no developer can run `python -m pytest tests/` and trust the result. No CI/CD can gate PRs on test passage. Every subsequent PR ships without regression confidence.

- Effort: 2-3 hours
- Risk: Low (mechanical deletion + import redirect, all verified by grep)
- Unlocks: All future PRs (B through J)
- ROI: **Infinite** — it's the denominator. Without it, every other task's ROI is zero because improvements can't be validated.

### P1: Task B — Implement Anthropic Streaming

**Why P1**: Single biggest user-facing improvement. Anthropic/Claude is a primary provider. Without streaming, every Claude response has 5-30x worse perceived latency than OpenAI. This is the most visible gap vs. Cursor.

- Effort: 1-2 hours
- Risk: Low (isolated to one provider adapter)
- Unlocks: Real-time response rendering for Claude
- ROI: **Very High** — small effort, massive perceived quality improvement

### P2: Task C — Add Structured Tool Calling

**Why P2**: Free-text tool parsing is the reliability bottleneck. Tool calls are the core interaction model for a code assistant. Without function_call/tool_use schemas, every tool invocation is fragile and hallucination-prone.

- Effort: 4-8 hours
- Risk: Medium (changes core agent interaction model)
- Unlocks: Reliable tool execution, MCP integration quality
- ROI: **High** — fundamental to code assistant reliability

### P2: Task D — Add Lexical Search Index

**Why P2 (tied)**: O(N) lexical search is the scalability ceiling. On any real-world codebase (10K+ files), retrieval latency becomes unacceptable.

- Effort: 4-8 hours
- Risk: Low (isolated to retrieval internals)
- Unlocks: Large codebase support
- ROI: **High** — removes scalability ceiling

### P2: Task E — Integrate Context Builder with Retrieval

**Why P2 (tied)**: Context quality directly determines LLM output quality. Current hard-coded truncation wastes token budget on irrelevant context while dropping relevant retrieved evidence.

- Effort: 3-5 hours
- Risk: Low
- Unlocks: Better edit suggestions, better analysis
- ROI: **High** — directly improves output quality

### P3: Task F — Indexing Cycle Detection

**Why P3**: Important for correctness but not blocking. Circular imports are uncommon in well-structured code. The indexer works for most real-world projects.

### P3: Task G — Memory Size Limits

**Why P3**: Important for long-running servers but not blocking. Agent memory rarely reaches 10K+ items in current usage.

### P3: Task H — Consolidate Agents

**Why P3**: Cleanup task. Dead agent code confuses developers but doesn't break anything. Can be folded into a future dead code PR.

### P3: Task I — Fix Blocking I/O in Indexer

**Why P3**: Small fix, small impact. Event loop stall during indexing is brief and masked by debouncing.

### P3: Task J — Cloud Completion Providers

**Why P3**: High effort, medium impact. Local Ollama completion works. Cloud providers add cost and latency for marginal quality improvement in completion (vs. chat/edit).

---

## 4. Summary

| Rank | Task | Effort | Key Impact | ROI |
|------|------|--------|-----------|-----|
| **P0** | **A: Dead code + test suite fix** | 2-3h | Unblocks all future work | **Highest** |
| **P1** | B: Anthropic streaming | 1-2h | 5-30x perceived latency fix | Very High |
| **P2** | C: Structured tool calling | 4-8h | Reliability of core interaction | High |
| **P2** | D: Lexical search index | 4-8h | Scalability ceiling removal | High |
| **P2** | E: Context builder integration | 3-5h | Output quality improvement | High |
| **P3** | F: Indexing cycle detection | 1-2h | Correctness edge case | Medium |
| **P3** | G: Memory size limits | 2-3h | Long-running stability | Medium |
| **P3** | H: Consolidate agents | 1-2h | Codebase clarity | Low |
| **P3** | I: Fix blocking I/O | 30min | Minor perf fix | Low |
| **P3** | J: Cloud completions | 8-16h | Completion quality | Medium |
