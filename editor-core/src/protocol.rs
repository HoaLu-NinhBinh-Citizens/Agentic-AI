//! JSON-RPC 2.0 message types.
//!
//! We follow the JSON-RPC 2.0 spec and use LSP-style `Content-Length` framing
//! on the wire (see `ipc.rs`) so the editor side can reuse the same
//! `vscode-jsonrpc` library it already uses for the language-server protocol.

use serde::{Deserialize, Serialize};
use serde_json::Value;

/// An incoming message. The editor may send either a request (has `id`,
/// expects a response) or a notification (no `id`, fire-and-forget).
#[derive(Debug, Deserialize)]
pub struct Request {
    #[allow(dead_code)]
    pub jsonrpc: String,
    /// Absent for notifications. Number or string per the spec.
    #[serde(default)]
    pub id: Option<Value>,
    pub method: String,
    #[serde(default)]
    pub params: Value,
}

impl Request {
    /// A notification has no `id` and therefore expects no response.
    pub fn is_notification(&self) -> bool {
        self.id.is_none()
    }
}

#[derive(Debug, Serialize)]
pub struct Response {
    pub jsonrpc: &'static str,
    pub id: Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<RpcError>,
}

impl Response {
    pub fn ok(id: Value, result: Value) -> Self {
        Self { jsonrpc: "2.0", id, result: Some(result), error: None }
    }

    pub fn err(id: Value, error: RpcError) -> Self {
        Self { jsonrpc: "2.0", id, result: None, error: Some(error) }
    }
}

#[derive(Debug, Serialize)]
pub struct RpcError {
    pub code: i64,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data: Option<Value>,
}

impl RpcError {
    pub fn new(code: ErrorCode, message: impl Into<String>) -> Self {
        Self { code: code as i64, message: message.into(), data: None }
    }
}

/// Standard JSON-RPC error codes plus a couple application-specific ones.
#[derive(Debug, Clone, Copy)]
pub enum ErrorCode {
    ParseError = -32700,
    InvalidRequest = -32600,
    MethodNotFound = -32601,
    InvalidParams = -32602,
    InternalError = -32603,
}
