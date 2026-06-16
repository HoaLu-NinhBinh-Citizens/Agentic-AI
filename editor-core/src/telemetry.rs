//! Async telemetry sink (ADR-001) — opt-in, never on the hot path.
//!
//! The editor emits accept/reject events on a batched `telemetry/log`
//! notification. Those events feed a background-thread JSONL writer through a
//! bounded channel: `log()` is non-blocking and *drops* on a full channel, so
//! recording telemetry can never slow a completion or a query. This is the data
//! flywheel for a future fine-tune — we collect now, train later.

use std::fs::OpenOptions;
use std::io::Write;
use std::path::Path;
use std::sync::mpsc::{sync_channel, SyncSender, TrySendError};
use std::thread::JoinHandle;

use anyhow::Result;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tracing::{debug, warn};

/// Bounded so a stalled disk can never grow memory without limit. Overflow is
/// dropped (telemetry is best-effort), not blocked.
const CHANNEL_CAPACITY: usize = 1024;

/// One interaction record. The exact context provenance is free-form `context`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TelemetryEvent {
    pub ts_ms: i64,
    pub task: String,
    pub outcome: String, // "accepted" | "rejected" | "partial"
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub model: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub latency_ms: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub prompt_token_estimate: Option<usize>,
    #[serde(default, skip_serializing_if = "Value::is_null")]
    pub context: Value,
}

enum Msg {
    Line(String),
    Stop,
}

/// Owns the writer thread. Dropping (or `shutdown`) flushes and joins.
pub struct TelemetrySink {
    tx: Option<SyncSender<Msg>>,
    handle: Option<JoinHandle<()>>,
    dropped: std::sync::Arc<std::sync::atomic::AtomicU64>,
}

impl TelemetrySink {
    /// A disabled sink: `log` is a no-op and nothing is written. Used when the
    /// user has not opted in.
    pub fn disabled() -> Self {
        Self { tx: None, handle: None, dropped: Default::default() }
    }

    /// Open an append-only JSONL sink at `path`, spawning the writer thread.
    pub fn open(path: &Path) -> Result<Self> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).ok();
        }
        let mut file = OpenOptions::new().create(true).append(true).open(path)?;
        let (tx, rx) = sync_channel::<Msg>(CHANNEL_CAPACITY);

        let handle = std::thread::spawn(move || {
            // Drain until Stop; flush after each batch is cheap enough at this
            // volume and keeps data durable if the process is killed.
            while let Ok(msg) = rx.recv() {
                match msg {
                    Msg::Line(line) => {
                        if writeln!(file, "{line}").is_err() {
                            break;
                        }
                        let _ = file.flush();
                    }
                    Msg::Stop => break,
                }
            }
            let _ = file.flush();
        });

        Ok(Self {
            tx: Some(tx),
            handle: Some(handle),
            dropped: Default::default(),
        })
    }

    /// Record an event. Non-blocking: serializes and `try_send`s, dropping the
    /// event if the channel is full. Never touches the hot path's latency.
    pub fn log(&self, event: &TelemetryEvent) {
        let Some(tx) = &self.tx else { return };
        let line = match serde_json::to_string(event) {
            Ok(s) => s,
            Err(e) => {
                debug!(error = %e, "telemetry serialize failed; dropping");
                return;
            }
        };
        match tx.try_send(Msg::Line(line)) {
            Ok(()) => {}
            Err(TrySendError::Full(_)) => {
                let n = self
                    .dropped
                    .fetch_add(1, std::sync::atomic::Ordering::Relaxed)
                    + 1;
                // Surface the drop so silent loss is visible — no silent caps.
                if n.is_power_of_two() {
                    warn!(dropped = n, "telemetry channel full; dropping events");
                }
            }
            Err(TrySendError::Disconnected(_)) => {}
        }
    }

    /// Flush and stop the writer thread.
    pub fn shutdown(&mut self) {
        if let Some(tx) = self.tx.take() {
            let _ = tx.send(Msg::Stop);
        }
        if let Some(handle) = self.handle.take() {
            let _ = handle.join();
        }
    }
}

impl Drop for TelemetrySink {
    fn drop(&mut self) {
        self.shutdown();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn event(outcome: &str) -> TelemetryEvent {
        TelemetryEvent {
            ts_ms: 1,
            task: "completion".into(),
            outcome: outcome.into(),
            model: Some("qwen-3b".into()),
            latency_ms: Some(120),
            prompt_token_estimate: Some(800),
            context: json!({ "included_snippets": [] }),
        }
    }

    #[test]
    fn writes_events_as_jsonl() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("telemetry.jsonl");
        {
            let mut sink = TelemetrySink::open(&path).unwrap();
            sink.log(&event("accepted"));
            sink.log(&event("rejected"));
            sink.shutdown(); // flush + join
        }
        let body = std::fs::read_to_string(&path).unwrap();
        let lines: Vec<_> = body.lines().collect();
        assert_eq!(lines.len(), 2);
        // Each line is valid JSON with the expected fields.
        for line in lines {
            let v: Value = serde_json::from_str(line).unwrap();
            assert_eq!(v["task"], "completion");
            assert!(v["outcome"].is_string());
        }
    }

    #[test]
    fn disabled_sink_is_a_noop() {
        let sink = TelemetrySink::disabled();
        sink.log(&event("accepted")); // must not panic, writes nowhere
    }
}
