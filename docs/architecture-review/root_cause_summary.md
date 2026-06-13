# Root Cause Summary — Grouped & Deduplicated Findings

> **Document type**: Read-only cross-validation — no code was modified.
> **Date**: 2026-06-13

---

## 1. Cross-Validation Results

### Contradictions Found

**C-1: Architecture diagram places DiffEngine and EditSession in "Domain Layer" (architecture.md §2), but they live in `infrastructure/editing/` and `application/editing/` respectively.**

Resolution: The architecture diagram is inaccurate. DiffEngine belongs in infrastructure, EditSession belongs in application. Not a codebase problem — a documentation error. Corrected in this document's understanding.

**C-2: data_flow.md §3 states completion may go through "Path A: Electron → ollamaClient.ts → Ollama directly" or "Path B: Backend → CompletionEngine." architecture.md §3.4 describes only the backend path.**

Resolution: Both paths likely exist (Electron has `ollamaClient.ts`), but which is primary is unknown. Flagged as NEED MORE EVIDENCE. Not a contradiction — an incomplete observation in architecture.md.

**C-3: dependency_graph.md §5.3 states RealAgent has "no dependency injection," but architecture.md §3.3 describes it as having "LLM provider auto-detection."**

Resolution: Not a contradiction. Auto-detection is about runtime provider selection (env vars), not compile-time DI. The DI violation is about the hard import of infrastructure types. Both statements are correct.

### No other contradictions found.

---

## 2. Root Cause Clusters

After analyzing all 16 problems, they collapse into **6 root causes**:

### RC-1: Speculative Scaffolding Never Pruned

**Description**: During phased development (Phase 1-5), packages were created ahead of implementation. Many were never filled, never wired to the server, or duplicated by later work. No pruning discipline was applied.

**Problems caused**:
| ID | Problem |
|----|---------|
| P-03 | Dual orchestration systems (3 namespaces, 1 wired) |
| P-04 | ~40% dead/orphaned code |
| P-07 | Health probes scaffolded but empty |
| P-12 | EventEmitter built but disconnected from server |

**Why these share a root cause**: All four are instances of "built it, never wired it." The orchestration systems, health packages, and event system were designed in advance, partially or fully implemented, but never integrated into the production server path (`main.py`).

**Merged engineering task**: **T-01: Dead code audit and consolidation** — identify what's live vs dead, delete dead trees, consolidate duplicated orchestration paths.

### RC-2: Phase 1B Defaults Never Updated for Production

**Description**: The server was built as a "minimal viable server" (Phase 1B) with hardcoded defaults for rapid prototyping. When real LLM providers and longer workflows were integrated, these defaults were not revisited.

**Problems caused**:
| ID | Problem |
|----|---------|
| P-02 | 30s stream timeout vs 300s LLM timeout |
| P-11 | 1hr session TTL for IDE sessions |
| P-15 | CORS allow-all |
| P-16 | Unrestricted file read API |

**Why these share a root cause**: All four are "development convenience defaults" that were appropriate for Phase 1B local testing but are unsafe or broken for production. Each is a single-line or few-line configuration change.

**Merged engineering task**: **T-02: Harden server defaults** — review and update all production-sensitive config values.

### RC-3: No FTS Index for Lexical Search

**Description**: The retrieval pipeline's lexical path was implemented as a linear scan. No full-text search index was ever added.

**Problems caused**:
| ID | Problem |
|----|---------|
| P-01 | O(N) lexical scan in HybridRetriever |
| P-13 | Brute-force vector search (VectorIndex, separate issue but same scaling pattern) |

**Why these are related but NOT duplicates**: P-01 is about lexical search (text matching). P-13 is about vector search (cosine similarity). Both are O(N) per query, but they are different code paths solving different problems. However, they share the root cause of "retrieval was built for small datasets and never given indexing infrastructure."

**Note on P-13**: P-13 has medium confidence — it may not be exercised if ChromaDB handles all vector queries. P-01 is definitely exercised (confirmed in two sessions).

**Merged engineering task**: **T-03: Add retrieval indexing** — FTS5 for lexical, and confirm/eliminate the brute-force VectorIndex path.

### RC-4: Subsystems Developed in Isolation Without Integration

**Description**: Multiple subsystems were built independently with their own technology choices, never unified.

**Problems caused**:
| ID | Problem |
|----|---------|
| P-05 | Dual import convention (`from src.` vs bare) |
| P-06 | DI violations (ports scaffolded but unused) |
| P-09 | Three HTTP client libraries (httpx, aiohttp, requests) |
| P-10 | Completion engine not connected to retrieval |

**Why these share a root cause**: Each is a case of "team A built X, team B built Y, nobody wired them together." The import convention split, the HTTP client fragmentation, and the completion↔retrieval disconnect all stem from components developed without cross-cutting integration standards.

**Merged engineering task**: **T-04: Unify infrastructure standards** — single import convention, single HTTP client, wire completion to retrieval, implement LLM port.

### RC-5: No Fault Recovery for Background Processes

**Description**: Background workers (FileWatcher, MCP servers) were designed for happy-path operation. No heartbeat, watchdog, or auto-restart mechanism exists.

**Problems caused**:
| ID | Problem |
|----|---------|
| P-08 | No FileWatcher or MCP server recovery |
| P-14 | In-memory-only idempotency store (lost on restart) |

**Why these are related**: Both involve system state that is lost or degraded after a failure, with no recovery mechanism. P-08 is about process failures; P-14 is about state persistence across restarts. Both stem from "reliability was deferred."

**Merged engineering task**: **T-05: Add fault recovery** — watchdog for background processes, persistent idempotency store.

### RC-6: (Standalone) — Unrestricted File API

**Problem P-16** does not cluster with other root causes. It is a standalone security vulnerability.

**Engineering task**: **T-06: Path restriction on file API** — add workspace scoping and path traversal protection.

---

## 3. Consolidated Issue Inventory (After Merge)

| Task ID | Title | Source Problems | Category | Root Cause | Confidence |
|---------|-------|-----------------|----------|------------|------------|
| T-01 | Dead code audit & consolidation | P-03, P-04, P-07, P-12 | Maintenance / Architecture | RC-1: Speculative scaffolding | High |
| T-02 | Harden server defaults | P-02, P-11, P-15, P-16 | Security / Reliability | RC-2: Phase 1B defaults | High |
| T-03 | Add retrieval indexing (FTS) | P-01, P-13 | Scalability / Performance | RC-3: No FTS index | High (P-01), Medium (P-13) |
| T-04 | Unify infrastructure standards | P-05, P-06, P-09, P-10 | Architecture / Quality | RC-4: Isolated development | High |
| T-05 | Add fault recovery | P-08, P-14 | Reliability | RC-5: No fault recovery | High |
| T-06 | Path restriction on file API | P-16 | Security | Standalone | High |

**Result**: 16 problems → 6 engineering tasks (via root cause clustering).

---

## 4. Problems That Should NOT Be Counted Twice

| Problem | Appears In | Actually |
|---------|-----------|---------|
| P-07 (empty health stubs) | current_problems + architecture dead code list | Same symptom as P-04 (dead scaffolding). Merged into T-01. |
| P-12 (disconnected EventEmitter) | current_problems + data_flow observation | Same symptom as P-03 (built but unwired). Merged into T-01. |
| P-16 (unrestricted file API) | current_problems as standalone + also part of T-02 defaults | Listed in T-02 (server defaults) AND as standalone T-06 because the security severity warrants independent tracking. However, the fix will be applied during T-02 work. **T-06 is a subset of T-02 execution.** |
| P-13 (VectorIndex brute force) | current_problems + retrieval analysis | Related to P-01 by theme (O(N) retrieval) but different code path. Kept as same task T-03 since fix is investigated together. |

---

## 5. Unresolved Evidence Gaps

| Gap | Impact on Planning | Action |
|-----|-------------------|--------|
| Which completion path Electron uses (ollamaClient.ts vs backend) | Affects T-04 scope (completion-retrieval wiring) | Verify before starting T-04 |
| Whether VectorIndex brute-force is actually exercised in HybridRetriever | Affects T-03 scope | Verify during T-03 |
| Whether EventEmitter is used by any subsystem outside main.py | Affects T-01 (delete vs consolidate decision) | Verify during T-01 |
| Whether session TTL causes real issues (P-11) | Affects T-02 urgency | Check Electron keep-alive behavior |
