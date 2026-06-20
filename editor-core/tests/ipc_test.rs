//! `Content-Length` framing tests (the LSP-style wire format over stdio).
//!
//! Framing bugs corrupt every message, so we pin: header parsing, clean-EOF
//! handling, tolerance of extra headers, error paths, and a write→read
//! round-trip.

use std::io::Cursor;

use aircore::ipc::{read_message, write_response};
use aircore::protocol::Response;
use serde_json::json;

fn frame(body: &str) -> Vec<u8> {
    format!("Content-Length: {}\r\n\r\n{}", body.len(), body).into_bytes()
}

#[test]
fn reads_a_well_formed_frame() {
    let mut r = Cursor::new(frame(r#"{"method":"ping"}"#));
    let body = read_message(&mut r).unwrap().expect("expected a message");
    assert_eq!(body, br#"{"method":"ping"}"#);
}

#[test]
fn clean_eof_returns_none() {
    // Editor closed the pipe at a message boundary -> shutdown signal, not error.
    let mut r = Cursor::new(Vec::<u8>::new());
    assert!(read_message(&mut r).unwrap().is_none());
}

#[test]
fn extra_headers_are_ignored() {
    // Content-Type (and any unknown header) must be accepted and skipped.
    let body = r#"{"ok":true}"#;
    let raw = format!(
        "Content-Type: application/vscode-jsonrpc; charset=utf-8\r\nContent-Length: {}\r\n\r\n{}",
        body.len(),
        body
    );
    let mut r = Cursor::new(raw.into_bytes());
    let got = read_message(&mut r).unwrap().unwrap();
    assert_eq!(got, body.as_bytes());
}

#[test]
fn missing_content_length_is_an_error() {
    // Headers terminate but no length was given -> cannot know the body size.
    let mut r = Cursor::new(b"X-Foo: bar\r\n\r\n".to_vec());
    assert!(read_message(&mut r).is_err());
}

#[test]
fn malformed_header_is_an_error() {
    let mut r = Cursor::new(b"this-is-not-a-header\r\n\r\n".to_vec());
    assert!(read_message(&mut r).is_err());
}

#[test]
fn header_name_is_case_insensitive() {
    let body = "{}";
    let raw = format!("content-length: {}\r\n\r\n{}", body.len(), body);
    let mut r = Cursor::new(raw.into_bytes());
    assert_eq!(read_message(&mut r).unwrap().unwrap(), body.as_bytes());
}

#[test]
fn write_response_emits_content_length_framing() {
    let resp = Response::ok(json!(1), json!({"v": 1}));
    let mut out = Vec::new();
    write_response(&mut out, &resp).unwrap();
    let text = String::from_utf8(out).unwrap();

    let (header, body) = text.split_once("\r\n\r\n").expect("framed header/body split");
    let declared: usize = header
        .strip_prefix("Content-Length: ")
        .expect("Content-Length header")
        .trim()
        .parse()
        .unwrap();
    assert_eq!(declared, body.len(), "declared length must match body bytes");
}

#[test]
fn write_then_read_round_trips() {
    // What we write must parse back as one complete message.
    let resp = Response::ok(json!("id-1"), json!({"hello": "world"}));
    let mut buf = Vec::new();
    write_response(&mut buf, &resp).unwrap();

    let mut r = Cursor::new(buf);
    let body = read_message(&mut r).unwrap().unwrap();
    let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(v["id"], "id-1");
    assert_eq!(v["result"]["hello"], "world");
}
