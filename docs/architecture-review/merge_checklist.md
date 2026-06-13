# Merge Checklist

> **Document type**: Read-only planning — no code was modified.
> **Date**: 2026-06-13
> **Rule**: Every PR must pass this checklist before merge. Items marked per-PR are only required for that PR.

---

## Universal Checklist (All PRs)

### Build & Tests
- [ ] Build succeeds (`pip install -e .`)
- [ ] Server starts without errors
- [ ] Existing test suite passes (zero regressions vs baseline)
- [ ] New tests pass
- [ ] No unrelated test failures introduced

### Architecture Preservation
- [ ] REST endpoint paths unchanged (no removal, no rename)
- [ ] WebSocket message types unchanged (no removal, no rename)
- [ ] WebSocket message fields unchanged (no removal)
- [ ] No SQLite column removed or renamed
- [ ] No environment variable removed or renamed
- [ ] No MCP config format changed
- [ ] No `pyproject.toml` entry point changed
- [ ] Electron IDE works without code changes (manual test)

### Code Quality
- [ ] No unrelated refactoring included
- [ ] No opportunistic cleanup included
- [ ] No formatting-only changes (unless lint rule is the PR's purpose)
- [ ] No hidden scope expansion
- [ ] No duplicated logic introduced
- [ ] No new dependencies added (unless justified and documented)
- [ ] No hardcoded secrets

### Documentation
- [ ] Commit message follows Conventional Commits format
- [ ] PR description documents what changed and why
- [ ] Breaking changes (if any) documented explicitly
- [ ] NEED MORE EVIDENCE items (if encountered) documented

### Rollback
- [ ] Rollback plan verified (commit is revertable)
- [ ] DB down-migration script provided (if schema changed)
- [ ] Rollback does not corrupt data

---

## Per-PR Checklists

### PR-001: Harden Server Defaults
- [ ] `allow_origins` does not contain `"*"`
- [ ] Path validation rejects traversal attempts (unit test evidence)
- [ ] `STREAM_TIMEOUT_SEC` >= 120
- [ ] Symlink escape blocked
- [ ] **Security review** sign-off on path validation logic
- [ ] **Manual QA**: Electron IDE connects and chats successfully
- [ ] **Manual QA**: File read outside workspace returns 403

### PR-002: Delete Obvious Dead Code Trees
- [ ] Import graph analysis confirms zero live importers per deleted package
- [ ] `python -c "from interfaces.server.main import app"` succeeds
- [ ] Recursive import of all remaining packages: zero `ImportError`
- [ ] File count reduced by >= 30%
- [ ] Deleted packages listed in commit message
- [ ] No file outside the deletion list was modified (except `__init__.py` updates)

### PR-003: Consolidate Orchestration System
- [ ] Orchestration decision documented with rationale
- [ ] Single orchestration namespace remains
- [ ] Chat + tool execution work end-to-end
- [ ] **Architecture review** sign-off on orchestration decision

### PR-004: Resolve EventEmitter Disposition
- [ ] Caller audit evidence documented
- [ ] If deleted: zero import errors in surviving code
- [ ] If wired in: events flow through emitter in at least one verified path
- [ ] Decision documented

### PR-005: Add FTS5 Retrieval Indexing
- [ ] FTS5 table created and populated
- [ ] `_search_chunk_store()` uses FTS5, not `get_all()` scan
- [ ] Golden query set: all expected results in top-10
- [ ] **Benchmark review**: latency improved vs baseline
- [ ] Migration is idempotent (safe to re-run)
- [ ] Down-migration script: `DROP TABLE IF EXISTS chunks_fts`
- [ ] **Performance review** on retrieval benchmarks

### PR-006: Add FileWatcher Fault Recovery
- [ ] FileWatcher restarts after simulated thread death
- [ ] CPU at idle unchanged vs baseline
- [ ] Max restart limit prevents infinite loops
- [ ] Backoff increases with consecutive failures

### PR-007: Add MCP Server Fault Recovery
- [ ] MCP server reconnects after subprocess kill
- [ ] Tool registry repopulated after reconnect
- [ ] Exponential backoff on reconnection attempts
- [ ] Happy-path tool call latency unchanged

### PR-008: Add Persistent Idempotency Store
- [ ] Entries survive server restart
- [ ] Expired entries pruned (TTL enforced)
- [ ] No `database is locked` under concurrent access
- [ ] DB size bounded
- [ ] Down-migration script: `DROP TABLE IF EXISTS idempotency_store`

### PR-009: Unify Import Convention
- [ ] Import convention decision documented
- [ ] Lint rule configured and zero violations
- [ ] All imports resolve after rename
- [ ] Migration script provided for feature branches
- [ ] Team notified before merge
- [ ] **Architecture review** on convention choice
- [ ] **Manual QA**: server starts, all workflows functional

### PR-010: Consolidate HTTP Clients to httpx
- [ ] Zero imports of `aiohttp` or `requests` in `src/`
- [ ] `aiohttp` and `requests` removed from `pyproject.toml`
- [ ] All LLM providers work with httpx (per-provider test)
- [ ] SSE streaming works (streaming test)
- [ ] Connection pool stable under 20 concurrent requests
- [ ] **Performance review** on connection pool behavior
- [ ] **Manual QA**: chat with each configured provider

### PR-011: Implement LLM and Embedding Ports
- [ ] `LLMProviderPort` covers all methods used by `RealAgent`
- [ ] All 5 provider adapters implement port
- [ ] `RealAgent` uses port, not direct infrastructure import
- [ ] `EmbeddingPort` defined and used by domain layer
- [ ] Behavior equivalence: same prompt → same response through port
- [ ] **Architecture review** on port interface design

### PR-012: Wire Completion to Retrieval Context
- [ ] `CompletionEngine` accepts optional retrieval parameter
- [ ] Completion works WITH retrieval context
- [ ] Completion works WITHOUT retrieval context (graceful degradation)
- [ ] Completion latency within acceptable range
- [ ] **Manual QA**: ghost text shows cross-file awareness
- [ ] **Performance review** on completion latency

---

## Review Requirements Matrix

| PR | Arch Review | Security Review | Perf Review | Manual QA | Benchmark Review |
|----|-----------|----------------|------------|----------|-----------------|
| PR-001 | No | **Yes** | No | **Yes** | No |
| PR-002 | No | No | No | **Yes** | No |
| PR-003 | **Yes** | No | No | **Yes** | No |
| PR-004 | No | No | No | No | No |
| PR-005 | No | No | **Yes** | **Yes** | **Yes** |
| PR-006 | No | No | No | No | No |
| PR-007 | No | No | No | No | No |
| PR-008 | No | No | No | No | No |
| PR-009 | **Yes** | No | No | **Yes** | No |
| PR-010 | No | No | **Yes** | **Yes** | No |
| PR-011 | **Yes** | No | No | No | No |
| PR-012 | No | No | **Yes** | **Yes** | No |

### Approval Criteria

**Architecture review**: Required when the change affects module boundaries, dependency direction, or introduces new abstractions. Reviewer must verify the change aligns with the architecture documented in `architecture.md` and `architecture_freeze.md`.

**Security review**: Required when the change modifies authentication, authorization, input validation, or CORS configuration. Reviewer must verify the change closes the targeted vulnerability without introducing new ones.

**Performance review**: Required when the change affects latency-sensitive paths (retrieval, completion, HTTP clients). Reviewer must verify benchmark results show no regression beyond documented thresholds.

**Manual QA**: Required when the change affects user-visible behavior (IDE connectivity, chat, file operations, completion). Reviewer must manually verify the affected workflow works end-to-end.

**Benchmark review**: Required when the change adds or modifies indexing or search. Reviewer must verify benchmark results against documented thresholds in `benchmark_plan.md`.

---

## Merge Order Enforcement

| PR | Must Be Merged AFTER |
|----|---------------------|
| PR-001 | (none) |
| PR-002 | PR-001 (soft) |
| PR-003 | PR-002 |
| PR-004 | PR-002 |
| PR-005 | PR-002 (soft), PR-003 (soft) |
| PR-006 | PR-002 (soft) |
| PR-007 | PR-002 (soft) |
| PR-008 | PR-002 (soft) |
| PR-009 | PR-002, PR-003, PR-004 |
| PR-010 | PR-009 |
| PR-011 | PR-010 |
| PR-012 | PR-005, PR-011 |

**Rule**: Do not merge a PR before its dependencies are merged and stable (monitoring window passed, no rollback needed).

---

## Testing Contract Summary

| PR | Unit Tests | Integration Tests | Regression Tests | Benchmark Tests | Security Tests | Manual Validation |
|----|-----------|------------------|-----------------|----------------|---------------|------------------|
| PR-001 | T-02-U01 to U05 | T-02-I01 to I04 | T-02-R01 to R03 | Stream timeout headroom | T-02-S01 to S03 + N01 to N03 | IDE connectivity, file API |
| PR-002 | T-01-U01 to U03 | T-01-I01 to I03 | T-01-R01 to R04 | Startup time, RSS | — | Server start, chat, tools |
| PR-003 | T-01-U03 | Server startup | Chat + tools | — | — | Chat round-trip |
| PR-004 | Import integrity | Server startup | — | — | — | — |
| PR-005 | T-03-U01 to U06 | T-03-I01 to I03 | T-03-R01 to R03 | T-03-B01 to B03 | T-03-N01 to N02 | Index + search + chat |
| PR-006 | T-05-U01 to U02 | T-05-I01 | T-05-R01 | CPU idle | T-05-N01 | — |
| PR-007 | T-05-U03 to U04 | T-05-I02, I04 | T-05-R02 | — | T-05-N02 | — |
| PR-008 | T-05-U05 to U06 | T-05-I03 | T-05-R03 | DB size | T-05-N03 to N04 | — |
| PR-009 | T-04-U01 | T-04-I01 | Full suite | — | — | Server start, all workflows |
| PR-010 | T-04-U05 | T-04-I02 to I04 | T-04-R01, R04 | Connection pool load | — | Chat per provider |
| PR-011 | T-04-U02 to U04 | T-04-I02, I03 | T-04-R01, R02 | — | — | — |
| PR-012 | T-04-U06 | T-04-I05 | T-04-R03 | Completion latency | T-04-N02 | Completion quality |
