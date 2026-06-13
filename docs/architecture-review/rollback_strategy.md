# Rollback Strategy

> **Document type**: Read-only planning — no code was modified.
> **Date**: 2026-06-13
> **Rule**: Every implementation task must be safely revertable without corrupting the system.

---

## 1. T-02 / T-06: Harden Server Defaults

### Rollback Trigger
- Valid file reads returning 403 (false positive path validation)
- Electron IDE cannot connect after CORS restriction
- LLM generation killed prematurely by timeout
- Any existing test regresses

### Rollback Scope
- `src/interfaces/server/main.py` — revert CORS config, file API handler, session TTL
- `src/core/runtime/runtime_manager.py` — revert `STREAM_TIMEOUT_SEC`
- Scope: 2 files, config-only changes

### Rollback Procedure
1. `git revert <commit-hash>` — single commit revert
2. Verify: `python -m pytest tests/` passes
3. Verify: server starts, Electron IDE connects

### Rollback Verification
- [ ] Server starts successfully
- [ ] Electron IDE connects via WebSocket
- [ ] `/api/fs/read` accepts all paths (reverted to unrestricted)
- [ ] Chat completes without timeout
- [ ] Full test suite passes

### Rollback Completion Criteria
- Server behavior identical to pre-T-02 state
- Zero test regressions

### Rollback Owner
- Engineer who merged T-02

### Rollback Dependencies
- None — T-02 has no downstream dependents in the migration plan
- Future phases do not depend on T-02 changes

### Partial Rollback
T-02 contains 4 independent config changes. Any subset can be reverted independently if the commit is structured as separate changes:
1. CORS restriction — revertable alone
2. File API path validation — revertable alone
3. Stream timeout increase — revertable alone
4. Session TTL change — revertable alone

**Recommendation**: Structure T-02 as 4 separate commits within one PR for granular rollback.

---

## 2. T-01: Dead Code Audit & Consolidation

### Rollback Trigger
- Server fails to start after deletion (import error)
- Previously passing test fails unexpectedly (not a test for a deleted module)
- User reports broken workflow (chat, tools, indexing, completion)
- Third-party script or plugin imports deleted module

### Rollback Scope
- All deleted files restored
- Updated `__init__.py` files reverted
- Updated/removed tests reverted
- Scope: ~500 files (mostly restorations)

### Rollback Procedure
1. `git revert <commit-hash>` — restores all deleted files
2. If T-01 was split into sub-phases (B1, B2, B3), revert in reverse order: B3 → B2 → B1
3. Verify: `python -m pytest tests/` passes
4. Verify: server starts, all workflows functional

### Rollback Verification
- [ ] File count returns to pre-T-01 level
- [ ] Server starts successfully
- [ ] Full test suite passes (same pass count as pre-T-01 baseline)
- [ ] Chat, tool execution, indexing all functional
- [ ] `import src.app` succeeds (dead code restored)

### Rollback Completion Criteria
- Codebase identical to pre-T-01 state
- Zero test regressions

### Rollback Owner
- Engineer who merged T-01

### Rollback Dependencies
- If T-03, T-04, or T-05 have already been merged on top of T-01, rollback is **complex**:
  - T-03 may have removed dead retrieval paths that T-01 deletion exposed
  - T-04 may have updated imports in files that T-01 deleted (revert creates conflict)
  - T-05 may have added recovery for processes that T-01 clarified
- **Mitigation**: Do not merge T-03/T-04/T-05 until T-01 is stable (monitoring window passed)

### Partial Rollback
If T-01 is split into B1/B2/B3 sub-phases:
- B1 (obvious dead trees) can be reverted independently — no other phase depends on specific files in `src/app/` or `src/domains/`
- B2 (orchestration consolidation) can be reverted independently — restores the deleted orchestration namespace
- B3 (EventEmitter) can be reverted independently

**Recommendation**: Merge B1, B2, B3 as separate commits. Wait for CI green between each.

---

## 3. T-03: Add Retrieval Indexing (FTS)

### Rollback Trigger
- FTS5 recall regression (golden query set fails)
- FTS5 migration corrupts existing chunk data
- Retrieval latency increases (should decrease)
- SQLite FTS5 not available on target platform

### Rollback Scope
- `src/infrastructure/retrieval/hybrid.py` — revert to `get_all()` scan
- `src/infrastructure/retrieval/chunk_store.py` — remove FTS5 table creation
- SQLite: drop `chunks_fts` virtual table
- Scope: 2-3 files + DB schema

### Rollback Procedure
1. `git revert <commit-hash>`
2. Run down-migration: `DROP TABLE IF EXISTS chunks_fts;`
3. Verify: `python -m pytest tests/` passes
4. Verify: retrieval works with old O(N) scan

### Rollback Verification
- [ ] FTS5 table does not exist
- [ ] `_search_chunk_store()` uses `get_all()` scan
- [ ] Golden query set passes (same results as pre-T-03 baseline)
- [ ] Server starts, indexing works, retrieval works
- [ ] Full test suite passes

### Rollback Completion Criteria
- Retrieval behavior identical to pre-T-03 state
- FTS5 table dropped
- No orphaned shadow tables

### Rollback Owner
- Engineer who merged T-03

### Rollback Dependencies
- If T-04 has been merged (completion-retrieval wiring), the completion engine may expect faster retrieval. Rollback of T-03 degrades performance but does not break T-04 (retrieval still returns same data type).
- FTS5 table must be dropped explicitly — `git revert` alone does not modify the database.

### Data Recovery
- FTS5 is a derived index, not primary data. Dropping it loses no information.
- Primary chunk data in `ChunkStore` is unaffected by FTS5 rollback.
- Re-migration: simply re-run the application and FTS5 table will be recreated (if migration is idempotent).

---

## 4. T-05: Add Fault Recovery

### Rollback Trigger
- Watchdog causes CPU spin at idle
- MCP heartbeat causes excessive subprocess load
- Idempotency DB corruption or locking
- Recovery mechanism interferes with happy-path performance

### Rollback Scope
- `src/infrastructure/indexing/file_watcher.py` — remove watchdog loop
- `src/infrastructure/mcp/manager.py` — remove heartbeat and reconnect
- `src/core/execution/idempotency.py` — revert to in-memory store
- SQLite: drop `idempotency_store` table
- Scope: 3 files + DB schema

### Rollback Procedure
1. `git revert <commit-hash>` (or per sub-task if split)
2. Run down-migration: `DROP TABLE IF EXISTS idempotency_store;`
3. Verify: `python -m pytest tests/` passes
4. Verify: CPU at idle returns to baseline

### Rollback Verification
- [ ] No watchdog loop in FileWatcher
- [ ] No heartbeat in MCPClientManager
- [ ] Idempotency store is in-memory only
- [ ] `idempotency_store` table does not exist
- [ ] CPU at idle matches pre-T-05 baseline
- [ ] All happy-path tests pass

### Rollback Completion Criteria
- System behavior identical to pre-T-05 (no recovery mechanisms)
- No persistent idempotency data
- CPU idle unchanged

### Rollback Owner
- Engineer who merged T-05

### Rollback Dependencies
- T-05 has no downstream dependents. T-04 does not depend on fault recovery.
- If T-05 sub-tasks were merged independently, each can be rolled back independently:
  - FileWatcher recovery: revert alone, no effect on MCP or idempotency
  - MCP recovery: revert alone, no effect on FileWatcher or idempotency
  - Persistent idempotency: revert alone + drop table

### Partial Rollback
Each sub-task (FileWatcher, MCP, idempotency) is independent. If only MCP heartbeat causes issues, revert only the MCP sub-task.

---

## 5. T-04: Unify Infrastructure Standards

### Rollback Trigger
- Import resolution failure after convention change
- LLM provider stops working after HTTP client swap
- SSE streaming breaks with httpx
- Connection pool exhaustion under load
- Completion quality degrades with retrieval context

### Rollback Scope
- Sub-PR 1 (imports): ~400+ files
- Sub-PR 2 (HTTP client): provider adapters + embedding service + pyproject.toml
- Sub-PR 3 (ports): port interfaces + adapter updates + RealAgent + domain/knowledge
- Sub-PR 4 (completion): CompletionEngine constructor
- Scope: varies by sub-PR

### Rollback Procedure
**Sub-PR 1 (imports)**:
1. `git revert <commit-hash>`
2. Remove lint rule from CI config
3. Verify: all imports resolve, tests pass

**Sub-PR 2 (HTTP client)**:
1. `git revert <commit-hash>`
2. Re-add aiohttp/requests to pyproject.toml dependencies
3. `pip install -e .` to restore dependencies
4. Verify: all providers work, embedding works, tests pass

**Sub-PR 3 (ports)**:
1. `git revert <commit-hash>`
2. Verify: RealAgent uses direct LLMManager import, tests pass

**Sub-PR 4 (completion)**:
1. `git revert <commit-hash>`
2. Verify: completion works with local-only context, tests pass

### Rollback Verification
Per sub-PR:
- [ ] Reverted code compiles/imports without error
- [ ] Full test suite passes
- [ ] Affected functionality works (provider-specific, completion, embedding)
- [ ] No dependency conflicts in pyproject.toml

### Rollback Completion Criteria
- Behavior identical to the state before the reverted sub-PR
- No orphaned dependencies or lint rules

### Rollback Owner
- Engineer who merged the sub-PR

### Rollback Dependencies
Sub-PRs must be reverted in reverse merge order:
- Sub-PR 4 → Sub-PR 3 → Sub-PR 2 → Sub-PR 1
- Reverting Sub-PR 2 (HTTP client) without reverting Sub-PR 3 (ports) may cause issues if port adapters were written against httpx.
- Reverting Sub-PR 1 (imports) without reverting Sub-PR 2/3/4 **will** cause import errors in files changed by later sub-PRs.

**Critical risk**: T-04 is the hardest to roll back because sub-PRs are layered. Partial rollback requires reverting in strict reverse order.

**Mitigation**: Allow a stabilization window between each sub-PR merge (minimum: CI green + 24h observation).

---

## 6. Rollback Dependency Graph

```
T-02  (independent, revert anytime)
  │
T-01  (revert before T-03/T-04/T-05 if they're merged)
  │
  ├── T-03  (revert + drop FTS5 table)
  │
  ├── T-05  (revert + drop idempotency table)
  │
  └── T-04  (revert sub-PRs in reverse order: 4→3→2→1)
```

### Cross-Phase Rollback Rules

| Scenario | Procedure |
|----------|-----------|
| Rollback T-02 only | `git revert` — safe at any point |
| Rollback T-01 after T-03 merged | Revert T-03 first, then T-01 (T-03 may reference files T-01 deleted) |
| Rollback T-01 after T-04 merged | Revert T-04 sub-PRs first (imports changed in files T-01 deleted) |
| Rollback T-03 only | `git revert` + `DROP TABLE chunks_fts` — safe |
| Rollback T-05 only | `git revert` + `DROP TABLE idempotency_store` — safe |
| Rollback T-04 sub-PR 1 | Must also revert sub-PRs 2, 3, 4 (they depend on the import convention) |
| Rollback everything | Reverse order: T-04 → T-05 → T-03 → T-01 → T-02, drop all new tables |

---

## 7. Database Rollback Scripts

### FTS5 Table (T-03)

```sql
-- Down-migration for T-03
DROP TABLE IF EXISTS chunks_fts;
-- Verify: SELECT name FROM sqlite_master WHERE name = 'chunks_fts'; → empty
```

### Idempotency Table (T-05)

```sql
-- Down-migration for T-05
DROP TABLE IF EXISTS idempotency_store;
-- Verify: SELECT name FROM sqlite_master WHERE name = 'idempotency_store'; → empty
```

### Rollback Safety
- Both tables are derived/operational data, not primary data. Dropping them loses no user content.
- FTS5 can be rebuilt from existing chunk data by re-running migration.
- Idempotency data is transient by design (TTL-based). Losing it causes at most one duplicate execution.
