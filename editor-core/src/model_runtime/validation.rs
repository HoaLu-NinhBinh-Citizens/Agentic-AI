//! Response validation — the gate before any mutating action.
//!
//! A model's output is the one untrusted, nondeterministic input in the system.
//! Nothing it produces reaches the workspace until this module accepts it. For a
//! mutating capability the model must return the edit JSON described in the system
//! prompt; the validator parses it, checks every edit is structurally sound (sane
//! byte range, non-empty file), and only then hands [`FileEdits`] back to the
//! runtime. The Execution Runtime's `apply_fix` path re-checks bounds and the
//! detector diff afterward — this is the *first* of two gates, not the only one.
//!
//! Anything malformed, empty, or truncated is rejected with a reason; the runtime
//! turns a rejection into "no edits" (the task is skipped), never a silent apply.

use serde::Deserialize;

use crate::execution::FileEdits;
use crate::index::Edit;

use super::provider::{FinishReason, ModelResponse};

/// The outcome of validating a model response.
#[derive(Debug, Clone)]
pub enum Validated {
    /// Accepted: structurally sound edits, ready for the verifying apply path.
    Edits(Vec<FileEdits>),
    /// The model produced no output (e.g. the null provider). Not an error.
    Empty,
    /// The output was present but unusable; carries a human-readable reason.
    Rejected(String),
}

/// Validates a [`ModelResponse`] before any mutation. Stateless and pure: the same
/// response always validates to the same outcome.
pub struct ResponseValidator;

/// The edit envelope the model is instructed to emit. Mirrors [`Edit`]'s
/// `camelCase` wire shape so a model response deserializes directly.
#[derive(Debug, Deserialize)]
struct EditEnvelope {
    edits: Vec<FileEditPayload>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct FileEditPayload {
    file: String,
    edits: Vec<Edit>,
}

impl ResponseValidator {
    /// Validate a response that is expected to carry edits (a mutating capability).
    pub fn validate_edits(response: &ModelResponse) -> Validated {
        if matches!(response.finish, FinishReason::Empty) || response.text.trim().is_empty() {
            return Validated::Empty;
        }
        // A truncated response must never be applied — the tail could be a partial,
        // syntactically valid-looking edit.
        if matches!(response.finish, FinishReason::Length) {
            return Validated::Rejected("response was truncated (length limit)".to_string());
        }

        let envelope: EditEnvelope = match serde_json::from_str(response.text.trim()) {
            Ok(e) => e,
            Err(e) => return Validated::Rejected(format!("response is not valid edit JSON: {e}")),
        };

        if envelope.edits.is_empty() {
            return Validated::Empty;
        }

        let mut out = Vec::with_capacity(envelope.edits.len());
        for fe in envelope.edits {
            if fe.file.trim().is_empty() {
                return Validated::Rejected("edit names an empty file path".to_string());
            }
            if fe.edits.is_empty() {
                return Validated::Rejected(format!("no edits for file '{}'", fe.file));
            }
            for ed in &fe.edits {
                if ed.end_byte < ed.start_byte {
                    return Validated::Rejected(format!(
                        "edit on '{}' has end_byte {} before start_byte {}",
                        fe.file, ed.end_byte, ed.start_byte
                    ));
                }
            }
            out.push(FileEdits { file: fe.file, edits: fe.edits });
        }
        Validated::Edits(out)
    }
}
