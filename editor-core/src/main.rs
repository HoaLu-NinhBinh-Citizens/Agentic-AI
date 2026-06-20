//! aircore — the local editor core daemon.
//!
//! One process per workspace. Speaks JSON-RPC 2.0 over stdio (LSP-style
//! framing) to the editor. Phase 1 exposes the index engine:
//!
//!   initialize       { workspaceRoot, telemetry?, retrieval?, detectors? } -> { ok, status }
//!   index/sync       {}                  -> SyncResult (delta + symbols + suggestions)
//!   index/status     {}                  -> IndexStatus
//!   symbol/find      { name }            -> SymbolRow[]
//!   symbol/callSites { name }            -> RefRow[]
//!   symbol/resolve   { name, fromFile }  -> { candidates: ResolvedSymbol[] }
//!   symbol/dependencies { file }         -> { file, edges: ImportEdge[] }
//!   semantic/context { symbol | file+byte, maxTokens?, includeBodies? } -> SemanticContext
//!   context/completion { file, cursorByte, maxTokens?, query? } -> BuiltPrompt
//!   context/build    { file?|focusSymbol?, cursorByte?, query?, task?, maxTokens? } -> BuiltPrompt
//!   diagnostics/file { file }           -> { file, findings: Finding[] }
//!   fix/apply        { file, edits, dryRun? } -> FixOutcome (verified patch)
//!   detectors/list   {}                  -> { detectors: RuleMetadata[] }
//!   plan/create      { goal, focusSymbol?, files?, maxTokens? } -> Plan (DAG + schedule)
//!   retrieve         { query, k? }       -> RetrievedSnippet[]
//!   telemetry/log    TelemetryEvent      -> (notification; opt-in, async sink)
//!   shutdown         {}                  -> { ok: true }   (then exits)
//!
//! Logs go to stderr only; stdout is reserved for the framed RPC channel.

use std::io::{self, BufReader};

use anyhow::Result;
use serde_json::{json, Value};
use tracing::{error, info};
use tracing_subscriber::EnvFilter;

use std::path::Path;

use aircore::detector::DetectorConfig;
use aircore::index::{IndexEngine, RetrievalConfig};
use aircore::ipc;
use aircore::protocol::{ErrorCode, Request, Response, RpcError};
use aircore::telemetry::{TelemetryEvent, TelemetrySink};

const TELEMETRY_FILE: &str = ".agentic/telemetry.jsonl";

/// Daemon state held across requests.
struct Daemon {
    engine: Option<IndexEngine>,
    telemetry: TelemetrySink,
}

impl Daemon {
    fn new() -> Self {
        Self { engine: None, telemetry: TelemetrySink::disabled() }
    }

    /// Dispatch one request to its handler. Returns the JSON result on success
    /// or an `RpcError` to send back to the editor.
    fn handle(&mut self, method: &str, params: Value) -> std::result::Result<Value, RpcError> {
        match method {
            "initialize" => self.initialize(params),
            "index/sync" => self.index_sync(),
            "index/status" => self.index_status(),
            "symbol/find" => self.symbol_find(params),
            "symbol/callSites" => self.symbol_call_sites(params),
            "symbol/resolve" => self.symbol_resolve(params),
            "symbol/dependencies" => self.symbol_dependencies(params),
            "semantic/context" => self.semantic_context(params),
            "context/completion" => self.context_completion(params),
            "context/build" => self.context_build(params),
            "diagnostics/file" => self.diagnostics_file(params),
            "fix/apply" => self.fix_apply(params),
            "detectors/list" => self.detectors_list(),
            "plan/create" => self.plan_create(params),
            "retrieve" => self.retrieve(params),
            "telemetry/log" => self.telemetry_log(params),
            _ => Err(RpcError::new(
                ErrorCode::MethodNotFound,
                format!("unknown method: {method}"),
            )),
        }
    }

    fn initialize(&mut self, params: Value) -> std::result::Result<Value, RpcError> {
        let workspace_root = params
            .get("workspaceRoot")
            .and_then(Value::as_str)
            .ok_or_else(|| {
                RpcError::new(ErrorCode::InvalidParams, "missing 'workspaceRoot' string param")
            })?;

        // Telemetry is opt-in (ADR-001): only spin up the sink if asked.
        if params.get("telemetry").and_then(Value::as_bool).unwrap_or(false) {
            let path = Path::new(workspace_root).join(TELEMETRY_FILE);
            match TelemetrySink::open(&path) {
                Ok(sink) => self.telemetry = sink,
                Err(e) => error!(error = %e, "failed to open telemetry sink; continuing without"),
            }
        }

        let mut engine = IndexEngine::open(workspace_root).map_err(internal)?;

        // Optional retrieval backends: { retrieval: { ollama, lance, ollamaModel,
        // ollamaDim, ollamaHost } }. Absent => offline defaults.
        if let Some(r) = params.get("retrieval") {
            let mut cfg = RetrievalConfig::default();
            cfg.use_ollama = r.get("ollama").and_then(Value::as_bool).unwrap_or(false);
            cfg.use_lance = r.get("lance").and_then(Value::as_bool).unwrap_or(false);
            if let Some(h) = r.get("ollamaHost").and_then(Value::as_str) {
                cfg.ollama_host = h.to_string();
            }
            if let Some(m) = r.get("ollamaModel").and_then(Value::as_str) {
                cfg.ollama_model = m.to_string();
            }
            if let Some(d) = r.get("ollamaDim").and_then(Value::as_u64) {
                cfg.ollama_dim = d as usize;
            }
            engine.set_retrieval_config(cfg);
        }

        // Optional inline detector config overrides the auto-discovered
        // config.toml (e.g. the editor pushing user settings). Shape mirrors the
        // `[detectors]` TOML table: { disabled: [..], rules: { id: {..} } }.
        if let Some(d) = params.get("detectors") {
            let cfg: DetectorConfig = serde_json::from_value(d.clone()).map_err(|e| {
                RpcError::new(ErrorCode::InvalidParams, format!("invalid 'detectors' config: {e}"))
            })?;
            engine.set_detector_config(cfg);
        }

        let status = engine.status();
        self.engine = Some(engine);
        Ok(json!({
            "ok": true,
            "status": serde_json::to_value(status).map_err(internal)?,
        }))
    }

    /// List every registered detector and its effective config (enabled state,
    /// severity, languages, options) so the editor can render a settings panel.
    fn detectors_list(&mut self) -> std::result::Result<Value, RpcError> {
        let engine = self.engine_mut()?;
        let rules = engine.detector_metadata();
        Ok(json!({ "detectors": serde_json::to_value(rules).map_err(internal)? }))
    }

    /// Build a deterministic execution plan for a request. `{ goal, focusSymbol?,
    /// files?, maxTokens? }` -> Plan (intent, task DAG, schedule, per-task
    /// context + verification). The contract the future Execution Engine consumes.
    fn plan_create(&mut self, params: Value) -> std::result::Result<Value, RpcError> {
        use aircore::planner::PlanRequest;
        let req: PlanRequest = serde_json::from_value(params)
            .map_err(|e| RpcError::new(ErrorCode::InvalidParams, e.to_string()))?;
        if req.goal.trim().is_empty() {
            return Err(RpcError::new(ErrorCode::InvalidParams, "missing or empty 'goal'"));
        }
        let engine = self.engine_mut()?;
        serde_json::to_value(engine.plan(&req)).map_err(internal)
    }

    /// Record a batched interaction event (notification, no response). Off the
    /// hot path: the sink's `log` is non-blocking.
    fn telemetry_log(&mut self, params: Value) -> std::result::Result<Value, RpcError> {
        let event: TelemetryEvent = serde_json::from_value(params)
            .map_err(|e| RpcError::new(ErrorCode::InvalidParams, e.to_string()))?;
        self.telemetry.log(&event);
        Ok(Value::Null)
    }

    fn index_sync(&mut self) -> std::result::Result<Value, RpcError> {
        let engine = self.engine_mut()?;
        let delta = engine.sync().map_err(internal)?;
        serde_json::to_value(delta).map_err(internal)
    }

    fn index_status(&mut self) -> std::result::Result<Value, RpcError> {
        let engine = self.engine_mut()?;
        serde_json::to_value(engine.status()).map_err(internal)
    }

    fn symbol_find(&mut self, params: Value) -> std::result::Result<Value, RpcError> {
        let name = Self::name_param(&params)?;
        let engine = self.engine_mut()?;
        let rows = engine.find_symbol(&name).map_err(internal)?;
        serde_json::to_value(rows).map_err(internal)
    }

    fn symbol_call_sites(&mut self, params: Value) -> std::result::Result<Value, RpcError> {
        let name = Self::name_param(&params)?;
        let engine = self.engine_mut()?;
        let rows = engine.call_sites(&name).map_err(internal)?;
        serde_json::to_value(rows).map_err(internal)
    }

    /// Resolve a name used in a file to its definition(s), ranked by scope with
    /// a confidence verdict. `{ name, fromFile }`.
    fn symbol_resolve(&mut self, params: Value) -> std::result::Result<Value, RpcError> {
        let name = Self::name_param(&params)?;
        let from_file = params
            .get("fromFile")
            .and_then(Value::as_str)
            .ok_or_else(|| RpcError::new(ErrorCode::InvalidParams, "missing 'fromFile' string param"))?
            .to_string();
        let engine = self.engine_mut()?;
        let resolved = engine.resolve_symbol(&name, &from_file).map_err(internal)?;
        Ok(json!({ "candidates": serde_json::to_value(resolved).map_err(internal)? }))
    }

    /// File-level dependency edges (resolved imports) for a file. `{ file }`.
    fn symbol_dependencies(&mut self, params: Value) -> std::result::Result<Value, RpcError> {
        let file = params
            .get("file")
            .and_then(Value::as_str)
            .ok_or_else(|| RpcError::new(ErrorCode::InvalidParams, "missing 'file' string param"))?
            .to_string();
        let engine = self.engine_mut()?;
        let edges = engine.file_dependencies(&file).map_err(internal)?;
        Ok(json!({ "file": file, "edges": serde_json::to_value(edges).map_err(internal)? }))
    }

    /// Minimal relevant code for a task. Focus on a symbol by qualified name
    /// (`symbol`) or by cursor (`file` + `byte`). `{ symbol? | file?, byte?,
    /// maxTokens?, includeBodies? }`.
    fn semantic_context(&mut self, params: Value) -> std::result::Result<Value, RpcError> {
        use aircore::semantic::{FocusSpec, SemanticRequest};

        let focus = if let Some(sym) = params.get("symbol").and_then(Value::as_str) {
            FocusSpec::Symbol(sym.to_string())
        } else if let (Some(file), Some(byte)) = (
            params.get("file").and_then(Value::as_str),
            params.get("byte").and_then(Value::as_u64),
        ) {
            FocusSpec::Location { file: file.to_string(), byte: byte as usize }
        } else {
            return Err(RpcError::new(
                ErrorCode::InvalidParams,
                "provide either 'symbol' or both 'file' and 'byte'",
            ));
        };
        let max_tokens = params.get("maxTokens").and_then(Value::as_u64).unwrap_or(2000) as usize;
        let include_bodies =
            params.get("includeBodies").and_then(Value::as_bool).unwrap_or(false);

        let req = SemanticRequest { focus, max_tokens, include_bodies };
        let engine = self.engine_mut()?;
        let ctx = engine.semantic_context(&req).map_err(internal)?;
        serde_json::to_value(ctx).map_err(internal)
    }

    /// Build a FIM completion prompt for a cursor position.
    fn context_completion(&mut self, params: Value) -> std::result::Result<Value, RpcError> {
        let file = params
            .get("file")
            .and_then(Value::as_str)
            .ok_or_else(|| RpcError::new(ErrorCode::InvalidParams, "missing 'file' string param"))?
            .to_string();
        let cursor_byte = params
            .get("cursorByte")
            .and_then(Value::as_u64)
            .ok_or_else(|| {
                RpcError::new(ErrorCode::InvalidParams, "missing 'cursorByte' number param")
            })? as usize;
        let max_tokens = params.get("maxTokens").and_then(Value::as_u64).unwrap_or(2000) as usize;
        let query = params.get("query").and_then(Value::as_str).map(str::to_string);

        let engine = self.engine_mut()?;
        let prompt = engine
            .build_completion_context(&file, cursor_byte, max_tokens, query)
            .map_err(internal)?;
        serde_json::to_value(prompt).map_err(internal)
    }

    /// Task-aware semantic context assembly for chat/agent requests. Centers on
    /// `focusSymbol` (qualified name) or `file`+`cursorByte`, resolves its
    /// callees/imports, and fills leftover budget with retrieval. `{ file?,
    /// cursorByte?, focusSymbol?, query?, task?, maxTokens? }`.
    fn context_build(&mut self, params: Value) -> std::result::Result<Value, RpcError> {
        use aircore::context::{BuildRequest, Task};

        let task = match params.get("task").and_then(Value::as_str).unwrap_or("chat") {
            "completion" => Task::Completion,
            "nextEditSemantic" => Task::NextEditSemantic,
            _ => Task::Chat,
        };
        let file = params.get("file").and_then(Value::as_str).unwrap_or("").to_string();
        let focus_symbol = params.get("focusSymbol").and_then(Value::as_str).map(str::to_string);
        // Either a file or an explicit focus symbol must be given.
        if file.is_empty() && focus_symbol.is_none() {
            return Err(RpcError::new(
                ErrorCode::InvalidParams,
                "provide 'file' (with optional 'cursorByte') or 'focusSymbol'",
            ));
        }
        let cursor_byte = params.get("cursorByte").and_then(Value::as_u64).unwrap_or(0) as usize;
        let query = params.get("query").and_then(Value::as_str).map(str::to_string);
        let max_tokens = params.get("maxTokens").and_then(Value::as_u64).unwrap_or(4000) as usize;

        let engine = self.engine_mut()?;
        let prompt = engine
            .build_context(&BuildRequest { task, file, cursor_byte, query, max_tokens, focus_symbol })
            .map_err(internal)?;
        serde_json::to_value(prompt).map_err(internal)
    }

    /// Run bug detectors over one file and return findings (severity, line,
    /// message, before/after fix). The foundation for `/fix @file:line`.
    fn diagnostics_file(&mut self, params: Value) -> std::result::Result<Value, RpcError> {
        let file = params
            .get("file")
            .and_then(Value::as_str)
            .ok_or_else(|| RpcError::new(ErrorCode::InvalidParams, "missing 'file' string param"))?
            .to_string();
        let engine = self.engine_mut()?;
        let findings = engine.diagnose(&file).map_err(internal)?;
        Ok(json!({ "file": file, "findings": serde_json::to_value(findings).map_err(internal)? }))
    }

    /// Apply byte-range edits to a file and verify by re-running the detectors
    /// on the patched bytes. `{ file, edits: [{ startByte, endByte, newText }],
    /// dryRun? }`. With `dryRun: true` it returns the diff + patched content
    /// without writing — the editor previews, then re-calls without `dryRun` to
    /// commit. Powers the apply step of `/fix @file:line`.
    fn fix_apply(&mut self, params: Value) -> std::result::Result<Value, RpcError> {
        #[derive(serde::Deserialize)]
        #[serde(rename_all = "camelCase")]
        struct Params {
            file: String,
            #[serde(default)]
            edits: Vec<aircore::index::Edit>,
            #[serde(default)]
            dry_run: bool,
        }
        let p: Params = serde_json::from_value(params)
            .map_err(|e| RpcError::new(ErrorCode::InvalidParams, e.to_string()))?;
        if p.edits.is_empty() {
            return Err(RpcError::new(ErrorCode::InvalidParams, "missing or empty 'edits'"));
        }
        let engine = self.engine_mut()?;
        let outcome = engine.apply_fix(&p.file, &p.edits, p.dry_run).map_err(internal)?;
        serde_json::to_value(outcome).map_err(internal)
    }

    /// Retrieve top-k relevant snippets for a query (Cmd+K inline edit / chat).
    fn retrieve(&mut self, params: Value) -> std::result::Result<Value, RpcError> {
        let query = params
            .get("query")
            .and_then(Value::as_str)
            .ok_or_else(|| RpcError::new(ErrorCode::InvalidParams, "missing 'query' string param"))?
            .to_string();
        let k = params.get("k").and_then(Value::as_u64).unwrap_or(5) as usize;
        let engine = self.engine_mut()?;
        let snippets = engine.retrieve(&query, k).map_err(internal)?;
        serde_json::to_value(snippets).map_err(internal)
    }

    fn name_param(params: &Value) -> std::result::Result<String, RpcError> {
        params
            .get("name")
            .and_then(Value::as_str)
            .map(str::to_string)
            .ok_or_else(|| RpcError::new(ErrorCode::InvalidParams, "missing 'name' string param"))
    }

    fn engine_mut(&mut self) -> std::result::Result<&mut IndexEngine, RpcError> {
        self.engine.as_mut().ok_or_else(|| {
            RpcError::new(ErrorCode::InvalidRequest, "not initialized; call 'initialize' first")
        })
    }
}

/// Wrap any internal error as a JSON-RPC InternalError.
fn internal<E: std::fmt::Display>(e: E) -> RpcError {
    RpcError::new(ErrorCode::InternalError, e.to_string())
}

fn main() -> Result<()> {
    // RUST_LOG controls verbosity; default to info. Always to stderr.
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")))
        .with_writer(io::stderr)
        .init();

    info!("aircore daemon starting");

    let stdin = io::stdin();
    let mut reader = BufReader::new(stdin.lock());
    let stdout = io::stdout();
    let mut writer = stdout.lock();

    let mut daemon = Daemon::new();

    loop {
        let body = match ipc::read_message(&mut reader) {
            Ok(Some(b)) => b,
            Ok(None) => {
                info!("stdin closed, shutting down");
                break;
            }
            Err(e) => {
                error!(error = %e, "failed to read message; shutting down");
                break;
            }
        };

        let request: Request = match serde_json::from_slice(&body) {
            Ok(r) => r,
            Err(e) => {
                // Can't recover an id from an unparseable message; reply with a
                // null-id parse error per the JSON-RPC spec.
                let resp = Response::err(
                    Value::Null,
                    RpcError::new(ErrorCode::ParseError, e.to_string()),
                );
                ipc::write_response(&mut writer, &resp)?;
                continue;
            }
        };

        // Handle shutdown explicitly so we can break the loop after replying.
        if request.method == "shutdown" {
            if let Some(id) = request.id.clone() {
                let resp = Response::ok(id, json!({ "ok": true }));
                ipc::write_response(&mut writer, &resp)?;
            }
            info!("shutdown requested");
            break;
        }

        let is_notification = request.is_notification();
        let id = request.id.clone().unwrap_or(Value::Null);
        let result = daemon.handle(&request.method, request.params);

        // Notifications get no response, even on error (we just log).
        if is_notification {
            if let Err(e) = result {
                error!(method = %request.method, error = %e.message, "notification failed");
            }
            continue;
        }

        let resp = match result {
            Ok(value) => Response::ok(id, value),
            Err(err) => Response::err(id, err),
        };
        ipc::write_response(&mut writer, &resp)?;
    }

    Ok(())
}
