# Compatibility Matrix

> **Document type**: Read-only planning — no code was modified.
> **Date**: 2026-06-13

---

## 1. T-02 / T-06: Harden Server Defaults

| Dimension | Compatibility | Classification | Justification |
|-----------|--------------|----------------|---------------|
| **REST API endpoints** | All endpoints preserved. `/api/fs/read` adds 403 responses for invalid paths. | Partially compatible | New 403 responses are additive error cases. Clients that only request valid workspace paths see no change. Clients that requested out-of-workspace paths will break (intentionally). |
| **WebSocket protocol** | Message types and fields unchanged. Stream duration changes (longer timeout). | Fully compatible | No protocol change. Streams run longer before server-side kill. |
| **Internal Python modules** | `RuntimeManager` constant changes. No API signature changes. | Fully compatible | Constant value change, not API change. |
| **Plugins** | No plugin interface affected. | Fully compatible | Config-only changes. |
| **MCP integration** | Unaffected. | Fully compatible | MCP is independent of server CORS and file API. |
| **Electron IDE** | Must be in CORS allowlist. File reads restricted to workspace. | Partially compatible | IDE must send requests from an allowed origin. File read paths must be workspace-relative. **Risk**: if IDE sends absolute paths outside workspace, those reads will fail. |
| **Storage** | No schema changes. | Fully compatible | No data migration. |
| **Configuration** | `STREAM_TIMEOUT_SEC` value changes. CORS config changes. | Partially compatible | Any deployment that overrides these values in env/config must be aware of new defaults. |
| **Test framework** | Existing tests pass. New tests added. | Fully compatible | No test framework changes. |

---

## 2. T-01: Dead Code Audit & Consolidation

| Dimension | Compatibility | Classification | Justification |
|-----------|--------------|----------------|---------------|
| **REST API endpoints** | Unchanged. Dead code has no production endpoints. | Fully compatible | Dead code is not wired to the server. |
| **WebSocket protocol** | Unchanged. | Fully compatible | Dead code is not in the WebSocket handler path. |
| **Internal Python modules** | Deleted modules no longer importable. Surviving module APIs unchanged. | Breaking change | Any code importing `src.app`, `src.domains`, `src.agent`, or deleted infrastructure stubs will get `ModuleNotFoundError`. This is intentional — these modules are dead — but any undiscovered caller breaks. |
| **Plugins** | Unknown. | Unknown | **NEED MORE EVIDENCE**: Are there external plugins, scripts, or notebooks that import from deleted packages? Must grep all config files, scripts, and documentation for references. |
| **MCP integration** | Unaffected. MCP code is in `infrastructure/mcp/` which is not deleted. | Fully compatible | MCP is live code. |
| **Electron IDE** | Unaffected. IDE communicates via WebSocket/REST, not Python imports. | Fully compatible | IDE has no Python imports. |
| **Storage** | No schema changes. | Fully compatible | Dead code does not own any tables. |
| **Configuration** | `pyproject.toml` entry points may reference deleted modules. | Partially compatible | Must verify `agentic-ai` CLI entry point still resolves. Must verify no test config references deleted packages. |
| **Test framework** | Tests for deleted modules must be removed/updated. | Partially compatible | Test count will decrease. Tests for surviving code must still pass. Framework itself (pytest) is unchanged. |

---

## 3. T-03: Add Retrieval Indexing (FTS)

| Dimension | Compatibility | Classification | Justification |
|-----------|--------------|----------------|---------------|
| **REST API endpoints** | Unchanged. Retrieval is internal, not exposed via REST. | Fully compatible | No endpoint changes. |
| **WebSocket protocol** | Unchanged. | Fully compatible | Retrieval affects response quality, not protocol. |
| **Internal Python modules** | `HybridRetriever.search_docs()` return type preserved. `ChunkStore` gains new methods. `get_all()` deprecated but kept. | Fully compatible | Return type `list[RetrievalHit]` is unchanged. New methods are additive. `get_all()` still works. |
| **Plugins** | Unknown. | Unknown | **NEED MORE EVIDENCE**: Does any plugin call `ChunkStore.get_all()` directly? If so, it still works (method deprecated but present). |
| **MCP integration** | Unaffected. | Fully compatible | MCP does not interact with retrieval. |
| **Electron IDE** | Retrieval quality may change (ranking differences). | Partially compatible | Results returned to IDE via chat may differ in relevance ordering. This is expected improvement, not breakage. |
| **Storage** | New FTS5 virtual table in SQLite. | Partially compatible | New table is additive. Existing tables unchanged. Down-migration: `DROP TABLE chunks_fts`. Older code that doesn't know about FTS5 will simply ignore it. |
| **Configuration** | No config changes. | Fully compatible | FTS5 is auto-created on startup. |
| **Test framework** | New tests added. Existing retrieval tests may need golden-set updates if ranking changes. | Partially compatible | If existing tests assert specific ranking order, they may need updating. Tests asserting result presence (not order) are unaffected. |

---

## 4. T-05: Add Fault Recovery

| Dimension | Compatibility | Classification | Justification |
|-----------|--------------|----------------|---------------|
| **REST API endpoints** | Unchanged. | Fully compatible | Recovery is internal. |
| **WebSocket protocol** | Unchanged. | Fully compatible | Recovery does not add new message types. |
| **Internal Python modules** | New methods added: `FileWatcher.is_alive()`, `MCPClientManager.health_check()`, `MCPClientManager.reconnect()`. Existing signatures unchanged. | Fully compatible | All changes are additive. No existing method signature changes. |
| **Plugins** | Unaffected. | Fully compatible | New methods are internal. |
| **MCP integration** | Heartbeat uses existing JSON-RPC protocol (e.g., `tools/list` as ping). Auto-reconnect re-runs initialization handshake. | Fully compatible | No MCP protocol extension. Uses existing methods for health checking. |
| **Electron IDE** | Unaffected. | Fully compatible | IDE does not interact with recovery mechanisms. |
| **Storage** | New SQLite table `idempotency_store`. | Partially compatible | Additive table. Older code that doesn't know about it will ignore it. Down-migration: `DROP TABLE idempotency_store`. |
| **Configuration** | No config changes. Recovery parameters (intervals, backoff, max retries) may be configurable via new env vars. | Fully compatible | New env vars are additive with sensible defaults. |
| **Test framework** | New tests added. Existing tests unchanged. | Fully compatible | No test framework changes. |

---

## 5. T-04: Unify Infrastructure Standards

### Sub-PR 1: Import Convention

| Dimension | Compatibility | Classification | Justification |
|-----------|--------------|----------------|---------------|
| **Internal Python modules** | All import paths change. | Breaking change | Every file that uses the old convention breaks. This is an all-or-nothing change — partial application causes import errors. |
| **Plugins** | Any external code using `from src.X` or bare imports must match the new convention. | Breaking change | External scripts and notebooks must be updated. |
| **Test framework** | All test imports must be updated. | Breaking change | Mechanical change, but every test file is affected. |
| **All other dimensions** | Unaffected. | Fully compatible | Import convention is internal to Python. |

### Sub-PR 2: HTTP Client Consolidation

| Dimension | Compatibility | Classification | Justification |
|-----------|--------------|----------------|---------------|
| **Internal Python modules** | Provider adapters internal implementation changes. Public API unchanged. | Fully compatible | HTTP client is an implementation detail. `LLMManager` API unchanged. |
| **Plugins** | Unknown. | Unknown | **NEED MORE EVIDENCE**: Do any plugins directly instantiate `aiohttp.ClientSession` or `requests.Session`? If so, they break when these libraries are removed. |
| **Configuration** | `pyproject.toml` dependencies change (remove aiohttp, requests). | Partially compatible | Any deployment pinning these dependencies may need updating. |
| **All other dimensions** | Unaffected. | Fully compatible | HTTP client swap is internal. |

### Sub-PR 3: LLM and Embedding Ports

| Dimension | Compatibility | Classification | Justification |
|-----------|--------------|----------------|---------------|
| **Internal Python modules** | `RealAgent` constructor may change (accepts port instead of direct import). | Partially compatible | If any code directly instantiates `RealAgent` outside `main.py`, it must pass the port. `main.py` is updated as part of this sub-PR. |
| **All other dimensions** | Unaffected. | Fully compatible | Ports are internal architectural changes. |

### Sub-PR 4: Completion-Retrieval Wiring

| Dimension | Compatibility | Classification | Justification |
|-----------|--------------|----------------|---------------|
| **Internal Python modules** | `CompletionEngine` constructor gains optional parameter. | Fully compatible | New parameter is optional with default (no retrieval). Existing callers unchanged. |
| **Electron IDE** | Completion results may include cross-file context, changing ghost text suggestions. | Partially compatible | Quality should improve, but ghost text will differ from before. Not a breakage — a feature change. |
| **All other dimensions** | Unaffected. | Fully compatible | |

---

## 6. Summary Matrix

| Task | APIs | Modules | Plugins | MCP | IDE | Storage | Config | Tests |
|------|------|---------|---------|-----|-----|---------|--------|-------|
| **T-02** | Partial | Full | Full | Full | Partial | Full | Partial | Full |
| **T-01** | Full | **Breaking** | **Unknown** | Full | Full | Full | Partial | Partial |
| **T-03** | Full | Full | Unknown | Full | Partial | Partial | Full | Partial |
| **T-05** | Full | Full | Full | Full | Full | Partial | Full | Full |
| **T-04 SP1** | Full | **Breaking** | **Breaking** | Full | Full | Full | Full | **Breaking** |
| **T-04 SP2** | Full | Full | Unknown | Full | Full | Full | Partial | Full |
| **T-04 SP3** | Full | Partial | Full | Full | Full | Full | Full | Full |
| **T-04 SP4** | Full | Full | Full | Full | Partial | Full | Full | Full |

**Legend**: Full = fully compatible, Partial = partially compatible (additive changes or minor behavior differences), Breaking = breaking change, Unknown = insufficient evidence.

---

## 7. Unknown Compatibility Items

| Item | Task | What is Unknown | How to Resolve |
|------|------|----------------|----------------|
| External plugins importing dead packages | T-01 | Are there plugins/scripts outside `src/` that import from `src/app/`, `src/domains/`, etc.? | Grep all files (including non-Python) for deleted package names |
| Plugins using ChunkStore.get_all() | T-03 | Does any plugin call `get_all()` directly? | Grep for `get_all` across all files |
| Plugins using aiohttp/requests directly | T-04 SP2 | Do any plugins instantiate these HTTP clients? | Grep for `aiohttp` and `requests` imports outside `src/infrastructure/` |
| Electron IDE file path format | T-02 | Does IDE send absolute paths or workspace-relative paths to `/api/fs/read`? | Inspect `aiService.ts` or related IDE code |
| Electron completion path | T-04 SP4 | Does IDE use `ollamaClient.ts` (direct) or backend `CompletionEngine`? | Inspect `useInlineCompletion.ts` |
