# Validation Checklist — Manual & Automated

> **Document type**: Read-only planning — no code was modified.
> **Date**: 2026-06-13

---

## Per-Phase Checklists

### Phase A: Harden Server Defaults (T-02 / T-06)

#### Automated
- [ ] `python -m pytest tests/` — all existing tests pass
- [ ] CORS config does not contain `"*"` in `allow_origins`
- [ ] `/api/fs/read` rejects paths outside workspace root
- [ ] `/api/fs/read` rejects symlinks escaping workspace
- [ ] `STREAM_TIMEOUT_SEC` >= 120
- [ ] Session TTL refreshes on access

#### Manual
- [ ] Build succeeds (`pip install -e .`)
- [ ] Server starts (`uvicorn interfaces.server.main:app`)
- [ ] Electron IDE connects via WebSocket
- [ ] Chat works — send message, receive streamed response
- [ ] Long prompt (>30s generation) completes without timeout error
- [ ] File read from IDE works for workspace files
- [ ] File read from IDE fails for paths outside workspace
- [ ] Browser DevTools confirms CORS headers restrict to allowed origins

#### Success Conditions
- Zero security vulnerabilities in P-15, P-16
- Zero spurious TIMEOUT errors for normal chat
- All existing functionality preserved

#### Failure Conditions
- Any existing test fails that was passing before
- Electron IDE cannot connect
- Valid file reads are rejected (false positive in path validation)
- LLM generation killed prematurely

#### Acceptance Criteria
- [ ] All automated checks pass
- [ ] All manual checks pass
- [ ] Security review sign-off on path validation logic

---

### Phase B: Dead Code Consolidation (T-01)

#### Automated
- [ ] `python -m pytest tests/` — passing test count >= pre-deletion count minus intentionally removed tests
- [ ] `python -c "from interfaces.server.main import app"` — no import errors
- [ ] Recursive import of all remaining packages — zero `ImportError`
- [ ] `find src -name "*.py" | wc -l` drops by >= 30%
- [ ] Zero empty stub `__init__.py` packages remain (except legitimate namespace packages)
- [ ] Single orchestration namespace (only one of `core/orchestration/` or `core/multi_agent/` exists)
- [ ] No file imports from deleted packages

#### Manual
- [ ] Build succeeds
- [ ] Server starts
- [ ] Chat works end-to-end
- [ ] Tool execution works
- [ ] Indexing works (with `AI_SUPPORT_ENABLE_INDEXING=1`)
- [ ] MCP integration works (if configured)
- [ ] `git diff --stat` confirms only deletions and `__init__.py` updates

#### Success Conditions
- Codebase file count reduced by >= 30%
- Single orchestration path
- All production functionality preserved

#### Failure Conditions
- Server fails to start
- Any production code path breaks (chat, tools, indexing, completion)
- Test suite has unexpected failures (beyond tests for deleted modules)

#### Acceptance Criteria
- [ ] All automated checks pass
- [ ] All manual checks pass
- [ ] Deleted packages documented in commit message
- [ ] Orchestration decision documented

---

### Phase C1: Retrieval FTS (T-03)

#### Automated
- [ ] `python -m pytest tests/` — all tests pass
- [ ] FTS5 table exists after migration
- [ ] Lexical search uses FTS5, not `get_all()` scan
- [ ] Golden query set: all expected results in top-10
- [ ] Benchmark: lexical search < 100ms on 100K chunk dataset

#### Manual
- [ ] Build succeeds
- [ ] Server starts
- [ ] Index a real project (>10K LOC)
- [ ] Chat with retrieval context — responses reference relevant code
- [ ] Modify a file → re-index → search reflects update
- [ ] Search for a function name → correct file returned

#### Success Conditions
- `_search_chunk_store()` is O(log N) or O(1) via FTS5, not O(N)
- Retrieval quality is at least as good as before (golden set passes)
- Migration from existing data works without data loss

#### Failure Conditions
- FTS5 index returns fewer relevant results than the old scan (recall regression)
- Migration fails or loses chunks
- Retrieval latency increases (should decrease)

#### Acceptance Criteria
- [ ] All automated checks pass
- [ ] All manual checks pass
- [ ] Benchmark results documented

---

### Phase C2: Fault Recovery (T-05)

#### Automated
- [ ] `python -m pytest tests/` — all tests pass
- [ ] FileWatcher restarts after simulated thread death
- [ ] MCP server reconnects after subprocess kill
- [ ] Idempotency store survives server restart
- [ ] Idempotency entries expire after TTL

#### Manual
- [ ] Build succeeds
- [ ] Server starts
- [ ] Kill FileWatcher thread → file changes still detected after recovery
- [ ] Kill MCP subprocess → tool calls resume after reconnection
- [ ] Restart server → check idempotency deduplication still works
- [ ] Monitor logs: recovery events are logged with clear messages

#### Success Conditions
- FileWatcher auto-restarts within 10s of thread death
- MCP server reconnects within 10s of subprocess death
- Idempotency store persists across restart
- No infinite restart loops

#### Failure Conditions
- Recovery mechanism causes CPU spin or resource exhaustion
- Reconnection loses tool registry state
- Idempotency DB grows unbounded

#### Acceptance Criteria
- [ ] All automated checks pass
- [ ] All manual checks pass
- [ ] Recovery behavior documented

---

### Phase D: Unify Infrastructure (T-04)

#### Automated
- [ ] `python -m pytest tests/` — all tests pass
- [ ] Linter rule enforces single import convention — zero violations
- [ ] `grep -r "import aiohttp" src/` — zero hits (if httpx chosen)
- [ ] `grep -r "import requests" src/` — zero hits
- [ ] `core/ports/llm_provider/` contains port interface with implementations
- [ ] `domain/knowledge/embeddings.py` imports from port, not infrastructure
- [ ] `CompletionEngine` constructor accepts retrieval dependency

#### Manual
- [ ] Build succeeds
- [ ] Server starts
- [ ] Chat works with each LLM provider (OpenAI, Anthropic, Ollama)
- [ ] Embedding service works
- [ ] Inline completion works
- [ ] Completion shows cross-file awareness (qualitative)
- [ ] No connection pool warnings in logs

#### Success Conditions
- Single import convention enforced by lint
- Single HTTP client library
- LLM port implemented and used
- Completion receives retrieval context
- No DI violations from domain → infrastructure

#### Failure Conditions
- Any LLM provider stops working after HTTP client swap
- Import convention change causes subtle import-order bugs
- Completion quality degrades with retrieval context (unlikely but check)

#### Acceptance Criteria
- [ ] All automated checks pass
- [ ] All manual checks pass
- [ ] Lint rule added to CI

---

## Final Validation (After All Phases)

#### Automated
- [ ] Full test suite passes
- [ ] All benchmarks meet targets
- [ ] Zero lint violations
- [ ] Zero import errors on recursive import

#### Manual
- [ ] Clean build from scratch (`pip install -e .`)
- [ ] Server starts cleanly
- [ ] Electron IDE connects and works
- [ ] Chat works (multiple providers)
- [ ] Tool execution works
- [ ] Inline completion works
- [ ] File read/write from IDE works
- [ ] Indexing works
- [ ] MCP integration works
- [ ] Kill FileWatcher → recovers
- [ ] Kill MCP server → recovers
- [ ] Long chat (>2min generation) completes
- [ ] CORS blocks unauthorized origins
- [ ] File API blocks path traversal

#### Rollback Validation
- [ ] Each phase is in a separate commit/PR — can be reverted independently
- [ ] Reverting Phase D does not break Phase C changes
- [ ] Reverting Phase C does not break Phase B changes
- [ ] Reverting Phase B does not break Phase A changes
- [ ] Database migrations have down-migration scripts (FTS5 table, idempotency table)
