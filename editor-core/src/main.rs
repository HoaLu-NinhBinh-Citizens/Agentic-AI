//! aircore — the local editor core daemon.
//!
//! One process per workspace. Speaks JSON-RPC 2.0 over stdio (LSP-style
//! framing) to the editor. Phase 1 exposes the index engine:
//!
//!   initialize   { workspaceRoot }      -> { ok, status }
//!   index/sync   {}                     -> SyncDelta
//!   index/status {}                     -> IndexStatus
//!   shutdown     {}                     -> { ok: true }   (then exits)
//!
//! Logs go to stderr only; stdout is reserved for the framed RPC channel.

use std::io::{self, BufReader};

use anyhow::Result;
use serde_json::{json, Value};
use tracing::{error, info};
use tracing_subscriber::EnvFilter;

use aircore::index::IndexEngine;
use aircore::ipc;
use aircore::protocol::{ErrorCode, Request, Response, RpcError};

/// Daemon state held across requests.
struct Daemon {
    engine: Option<IndexEngine>,
}

impl Daemon {
    fn new() -> Self {
        Self { engine: None }
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

        let engine = IndexEngine::open(workspace_root).map_err(internal)?;
        let status = engine.status();
        self.engine = Some(engine);
        Ok(json!({
            "ok": true,
            "status": serde_json::to_value(status).map_err(internal)?,
        }))
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
