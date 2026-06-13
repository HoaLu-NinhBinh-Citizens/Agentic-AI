# Blast Radius Analysis

> **Document type**: Read-only planning — no code was modified.
> **Date**: 2026-06-13

---

## Per-PR Blast Radius

### PR-001: Harden Server Defaults

| Dimension | Assessment |
|-----------|-----------|
| **Blast Radius** | **Very Small** |
| **Affected Files** | 2 (`main.py`, `runtime_manager.py`) |
| **Affected Modules** | 2 (server, runtime) |
| **Runtime Impact** | Low — config value changes, additive 403 error code |
| **Deployment Impact** | Low — Electron IDE must be in CORS allowlist |
| **Reasoning** | Config-only changes to 2 files. No schema changes, no new dependencies. Rollback is `git revert`. |

#### Change Budget
- Max subsystems touched: 2
- Max architectural scope: Configuration only
- Max review complexity: Low (security review for path validation logic)
- **Split trigger**: N/A — already minimal

---

### PR-002: Delete Obvious Dead Code Trees

| Dimension | Assessment |
|-----------|-----------|
| **Blast Radius** | **Medium** |
| **Affected Files** | ~500 (deletions) + ~10 `__init__.py` updates |
| **Affected Modules** | ~15 packages deleted |
| **Runtime Impact** | Should be zero — dead code by definition not executed |
| **Deployment Impact** | Low — no data migration, no config changes |
| **Reasoning** | High file count but low risk because deletions are zero-caller packages. Risk from undiscovered callers (scripts, plugins, notebooks). |

#### Change Budget
- Max subsystems touched: 15 (all deletions)
- Max architectural scope: Deletion only — no refactoring
- Max review complexity: Medium (verify zero-caller claim per package)
- **Split trigger**: If any "dead" package has uncertain live/dead status, defer it to a separate PR

---

### PR-003: Consolidate Orchestration System

| Dimension | Assessment |
|-----------|-----------|
| **Blast Radius** | **Small** |
| **Affected Files** | ~20-50 (one orchestration namespace deleted) |
| **Affected Modules** | 1-2 packages deleted, `__init__.py` updates |
| **Runtime Impact** | Low — only if the deleted system was truly unused |
| **Deployment Impact** | None |
| **Reasoning** | Narrower than PR-002. Depends on correctness of orchestration decision. |

#### Change Budget
- Max subsystems touched: 2 (orchestration namespaces)
- Max architectural scope: Deletion of one namespace
- Max review complexity: Medium (verify production path still works)
- **Split trigger**: If `__init__.py` re-export cleanup is complex, split cleanup into follow-up PR

---

### PR-004: Resolve EventEmitter Disposition

| Dimension | Assessment |
|-----------|-----------|
| **Blast Radius** | **Very Small** (delete) / **Small** (wire in) |
| **Affected Files** | 3-5 (delete) or 5-15 (wire in) |
| **Affected Modules** | 1 (`core/events/`) |
| **Runtime Impact** | None (delete) / Low (wire in — new event flow) |
| **Deployment Impact** | None |
| **Reasoning** | Isolated to one package. Delete path is trivial. Wire-in path is small but requires careful testing. |

#### Change Budget
- Max subsystems touched: 1 (events)
- Max architectural scope: Delete one package or add event wiring
- Max review complexity: Low (delete) / Medium (wire in)
- **Split trigger**: N/A

---

### PR-005: Add FTS5 Retrieval Indexing

| Dimension | Assessment |
|-----------|-----------|
| **Blast Radius** | **Small** |
| **Affected Files** | 3-4 (`hybrid.py`, `chunk_store.py`, `vector_index.py`, possibly `incremental.py`) |
| **Affected Modules** | 1 (`infrastructure/retrieval/`) |
| **Runtime Impact** | Medium — retrieval latency changes, ranking order may change |
| **Deployment Impact** | Low — additive SQLite table, auto-migration |
| **Reasoning** | Localized to retrieval subsystem. FTS5 is additive. `get_all()` kept as fallback. |

#### Change Budget
- Max subsystems touched: 1 (retrieval)
- Max architectural scope: Internal retrieval implementation
- Max review complexity: Medium (FTS5 migration, query equivalence)
- **Split trigger**: If VectorIndex disposition requires significant work, split into separate PR

---

### PR-006: Add FileWatcher Fault Recovery

| Dimension | Assessment |
|-----------|-----------|
| **Blast Radius** | **Very Small** |
| **Affected Files** | 1 (`file_watcher.py`) |
| **Affected Modules** | 1 (`infrastructure/indexing/`) |
| **Runtime Impact** | Low — new background loop, must not spin |
| **Deployment Impact** | None |
| **Reasoning** | Additive methods on one file. Rollback is removing the addition. |

#### Change Budget
- Max subsystems touched: 1
- Max architectural scope: Additive methods
- Max review complexity: Low
- **Split trigger**: N/A

---

### PR-007: Add MCP Server Fault Recovery

| Dimension | Assessment |
|-----------|-----------|
| **Blast Radius** | **Very Small** |
| **Affected Files** | 1 (`manager.py`) |
| **Affected Modules** | 1 (`infrastructure/mcp/`) |
| **Runtime Impact** | Low — new heartbeat loop, reconnect logic |
| **Deployment Impact** | None |
| **Reasoning** | Additive methods on one file. Uses existing JSON-RPC for heartbeat. |

#### Change Budget
- Max subsystems touched: 1
- Max architectural scope: Additive methods
- Max review complexity: Low
- **Split trigger**: N/A

---

### PR-008: Add Persistent Idempotency Store

| Dimension | Assessment |
|-----------|-----------|
| **Blast Radius** | **Very Small** |
| **Affected Files** | 1 (`idempotency.py`) + schema |
| **Affected Modules** | 1 (`core/execution/`) |
| **Runtime Impact** | Low — same API, persistent backing store |
| **Deployment Impact** | Low — new SQLite table, auto-created |
| **Reasoning** | Drop-in replacement with same interface. Rollback: revert + drop table. |

#### Change Budget
- Max subsystems touched: 1
- Max architectural scope: Internal store implementation
- Max review complexity: Low (concurrent access concern)
- **Split trigger**: N/A

---

### PR-009: Unify Import Convention

| Dimension | Assessment |
|-----------|-----------|
| **Blast Radius** | **Large** |
| **Affected Files** | ~400+ (every Python file with imports) |
| **Affected Modules** | All |
| **Runtime Impact** | Should be zero — mechanical rename |
| **Deployment Impact** | High — all feature branches need migration script |
| **Reasoning** | Highest file count of any PR. Mechanical change but touches everything. Risk: import-order dependencies, circular imports. Must coordinate with team. |

#### Change Budget
- Max subsystems touched: All (mechanical only)
- Max architectural scope: Import paths only — zero logic changes
- Max review complexity: High (verify all imports resolve; lint rule works)
- **Split trigger**: If circular imports are discovered, STOP and split into smaller fixes

---

### PR-010: Consolidate HTTP Clients to httpx

| Dimension | Assessment |
|-----------|-----------|
| **Blast Radius** | **Medium** |
| **Affected Files** | 5-10 (provider adapters + embedding service + `pyproject.toml`) |
| **Affected Modules** | 2 (`infrastructure/llm/`, `infrastructure/embeddings/`) |
| **Runtime Impact** | High — HTTP client swap affects every LLM and embedding call |
| **Deployment Impact** | Medium — dependency removal from `pyproject.toml` |
| **Reasoning** | Moderate file count but high runtime risk. SSE streaming behavior differences between aiohttp and httpx could break providers. |

#### Change Budget
- Max subsystems touched: 2 (LLM + embedding HTTP layers)
- Max architectural scope: Internal HTTP client implementation
- Max review complexity: High (per-provider streaming verification)
- **Split trigger**: If one provider's SSE is incompatible with httpx, split that provider to a separate PR

---

### PR-011: Implement LLM and Embedding Ports

| Dimension | Assessment |
|-----------|-----------|
| **Blast Radius** | **Small** |
| **Affected Files** | 8-12 (port interfaces + adapter updates + `real_agent.py` + `embeddings.py`) |
| **Affected Modules** | 3 (`core/ports/`, `core/agent/`, `domain/knowledge/`) |
| **Runtime Impact** | Low — same behavior through abstraction layer |
| **Deployment Impact** | None |
| **Reasoning** | New interfaces + adapter wiring. Behavior must be identical. |

#### Change Budget
- Max subsystems touched: 3
- Max architectural scope: Interface definition + adapter wiring
- Max review complexity: Medium (port design review)
- **Split trigger**: If port design requires `main.py` wiring changes that affect WebSocket protocol, STOP

---

### PR-012: Wire Completion to Retrieval Context

| Dimension | Assessment |
|-----------|-----------|
| **Blast Radius** | **Very Small** |
| **Affected Files** | 1-2 (`completion_engine.py`, possibly `main.py` wiring) |
| **Affected Modules** | 1 (`infrastructure/completion/`) |
| **Runtime Impact** | Medium — completion behavior changes (should improve) |
| **Deployment Impact** | None |
| **Reasoning** | Optional parameter addition. Graceful degradation preserves old behavior. |

#### Change Budget
- Max subsystems touched: 1
- Max architectural scope: Optional parameter + FIM prompt change
- Max review complexity: Medium (completion quality assessment)
- **Split trigger**: N/A

---

## Summary Matrix

| PR | Blast Radius | Files | Modules | Runtime Risk | Deploy Risk |
|----|-------------|-------|---------|-------------|------------|
| PR-001 | Very Small | 2 | 2 | Low | Low |
| PR-002 | Medium | ~500 | ~15 | Should be zero | Low |
| PR-003 | Small | ~20-50 | 1-2 | Low | None |
| PR-004 | Very Small | 3-15 | 1 | None-Low | None |
| PR-005 | Small | 3-4 | 1 | Medium | Low |
| PR-006 | Very Small | 1 | 1 | Low | None |
| PR-007 | Very Small | 1 | 1 | Low | None |
| PR-008 | Very Small | 1 | 1 | Low | Low |
| PR-009 | **Large** | ~400+ | All | Should be zero | **High** |
| PR-010 | Medium | 5-10 | 2 | **High** | Medium |
| PR-011 | Small | 8-12 | 3 | Low | None |
| PR-012 | Very Small | 1-2 | 1 | Medium | None |

### Engineering Risk Ranking (highest to lowest)

1. **PR-009** — Large blast radius, all files touched, team coordination required
2. **PR-010** — SSE streaming compatibility risk across all providers
3. **PR-002** — High file count (deletions), undiscovered caller risk
4. **PR-005** — Retrieval quality regression risk
5. **PR-003** — Orchestration decision correctness risk
6. **PR-011** — Port design adequacy risk
7. **PR-012** — Completion quality subjectivity
8. **PR-001** — Minimal (config changes)
9. **PR-004** — Minimal (isolated package)
10. **PR-006, PR-007, PR-008** — Minimal (additive single-file changes)
