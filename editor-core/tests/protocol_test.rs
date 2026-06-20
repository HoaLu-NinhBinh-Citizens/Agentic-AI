//! JSON-RPC 2.0 message-type tests: the request/notification distinction,
//! param defaulting, and response/error serialization shape (the wire contract
//! the editor's `vscode-jsonrpc` client depends on).

use aircore::protocol::{ErrorCode, Request, Response, RpcError};
use serde_json::{json, Value};

fn parse(v: Value) -> Request {
    serde_json::from_value(v).unwrap()
}

#[test]
fn request_with_id_is_not_a_notification() {
    let req = parse(json!({"jsonrpc": "2.0", "id": 7, "method": "ping", "params": {}}));
    assert!(!req.is_notification());
    assert_eq!(req.method, "ping");
}

#[test]
fn request_without_id_is_a_notification() {
    // No `id` -> fire-and-forget; the loop must not send a response.
    let req = parse(json!({"jsonrpc": "2.0", "method": "telemetry/log"}));
    assert!(req.is_notification());
}

#[test]
fn missing_params_default_to_null() {
    // `params` is optional in the spec; absence must not fail deserialization.
    let req = parse(json!({"jsonrpc": "2.0", "id": 1, "method": "m"}));
    assert_eq!(req.params, Value::Null);
}

#[test]
fn string_id_is_accepted() {
    // The spec allows string or number ids; both must round-trip.
    let req = parse(json!({"jsonrpc": "2.0", "id": "abc", "method": "m"}));
    assert!(!req.is_notification());
    assert_eq!(req.id, Some(json!("abc")));
}

#[test]
fn ok_response_serializes_result_and_omits_error() {
    let resp = Response::ok(json!(1), json!({"score": 42}));
    let v = serde_json::to_value(&resp).unwrap();
    assert_eq!(v["jsonrpc"], "2.0");
    assert_eq!(v["id"], 1);
    assert_eq!(v["result"]["score"], 42);
    // error must be skipped entirely (not serialized as null).
    assert!(v.get("error").is_none(), "ok response must not carry an error key");
}

#[test]
fn err_response_serializes_error_and_omits_result() {
    let resp = Response::err(json!(2), RpcError::new(ErrorCode::MethodNotFound, "no such method"));
    let v = serde_json::to_value(&resp).unwrap();
    assert_eq!(v["id"], 2);
    assert_eq!(v["error"]["code"], ErrorCode::MethodNotFound as i64);
    assert_eq!(v["error"]["message"], "no such method");
    assert!(v.get("result").is_none(), "err response must not carry a result key");
    // optional `data` is skipped when absent.
    assert!(v["error"].get("data").is_none());
}

#[test]
fn error_codes_match_jsonrpc_spec() {
    // These are the standard JSON-RPC 2.0 codes; the editor branches on them.
    assert_eq!(ErrorCode::ParseError as i64, -32700);
    assert_eq!(ErrorCode::InvalidRequest as i64, -32600);
    assert_eq!(ErrorCode::MethodNotFound as i64, -32601);
    assert_eq!(ErrorCode::InvalidParams as i64, -32602);
    assert_eq!(ErrorCode::InternalError as i64, -32603);
}
