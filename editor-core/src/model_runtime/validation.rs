//! Response validation — the gate before any mutating action.
//!
//! A model's output is the one untrusted, nondeterministic input in the system.
//! Nothing it produces reaches the workspace until this module accepts it.
//!
//! Validation is **layered**: a [`ValidationPipeline`] runs an ordered list of
//! small, single-concern [`Validator`]s, each returning a [`Verdict`]. The first
//! non-`Pass` verdict short-circuits the pipeline. The layers, in order:
//!
//! 1. [`CompletenessValidator`] — empty vs. present vs. truncated (all output kinds).
//! 2. [`SchemaValidator`] — the response parses into the edit envelope.
//! 3. [`SafetyValidator`] — the edits name nothing forbidden (today: non-empty path).
//! 4. [`SemanticValidator`] — every span is structurally sound.
//! 5. [`PolicyValidator`] — endpoint/policy constraints (seam; passes today).
//!
//! The Execution Runtime's `apply_fix` path re-checks bounds against the real file
//! and the detector diff afterward — this is the *first* of two gates, not the
//! only one. Anything malformed, empty, or truncated is rejected with a reason;
//! the runtime turns a rejection into "no output" (the task is skipped), never a
//! silent apply.

use std::cell::RefCell;

use serde::Deserialize;

use super::dto::{EditSpan, ModelEdit, OutputExpectation};
use super::provider::{FinishReason, ModelResponse};

/// The outcome of validating a model response.
#[derive(Debug, Clone)]
pub enum Validated {
    /// Accepted: structurally sound edits, ready for the verifying apply path.
    Edits(Vec<ModelEdit>),
    /// Accepted free-form text (explain / review / report / plan).
    Text(String),
    /// The model produced no usable output (e.g. the null provider). Not an error.
    Empty,
    /// The output was present but unusable; carries a human-readable reason.
    Rejected(String),
}

/// One validator's verdict. `Pass` lets the pipeline continue to the next layer;
/// `Empty`/`Reject` terminate it.
#[derive(Debug, Clone)]
pub enum Verdict {
    Pass,
    Empty,
    Reject(String),
}

/// The edit envelope the model is instructed to emit.
#[derive(Debug, Clone, Deserialize)]
struct EditEnvelope {
    edits: Vec<FileEditPayload>,
}

#[derive(Debug, Clone, Deserialize)]
struct FileEditPayload {
    file: String,
    edits: Vec<EditSpan>,
}

/// Everything a layer needs to validate a response. The parsed edit envelope is
/// memoized here by [`SchemaValidator`] so downstream layers reuse it instead of
/// re-parsing.
pub struct ValidationCx<'a> {
    pub response: &'a ModelResponse,
    pub expectation: OutputExpectation,
    parsed: RefCell<Option<EditEnvelope>>,
}

impl<'a> ValidationCx<'a> {
    fn new(response: &'a ModelResponse, expectation: OutputExpectation) -> Self {
        Self { response, expectation, parsed: RefCell::new(None) }
    }

    /// The trimmed response text (what every validator reasons over).
    fn text(&self) -> &str {
        self.response.text.trim()
    }
}

/// A single validation concern. Stateless and pure: the same context always
/// yields the same verdict.
pub trait Validator {
    fn name(&self) -> &'static str;
    fn check(&self, cx: &ValidationCx) -> Verdict;
}

/// Layer 1 — completeness. Empty output is `Empty` (not an error); a truncated
/// response is rejected because its tail could be a partial, valid-looking edit.
pub struct CompletenessValidator;
impl Validator for CompletenessValidator {
    fn name(&self) -> &'static str {
        "completeness"
    }
    fn check(&self, cx: &ValidationCx) -> Verdict {
        if matches!(cx.response.finish, FinishReason::Empty) || cx.text().is_empty() {
            return Verdict::Empty;
        }
        if matches!(cx.response.finish, FinishReason::Length) {
            return Verdict::Reject("response was truncated (length limit)".to_string());
        }
        Verdict::Pass
    }
}

/// Layer 2 — schema. The response must parse into the edit envelope. An envelope
/// with no files is `Empty` (the model declined), not a rejection.
pub struct SchemaValidator;
impl Validator for SchemaValidator {
    fn name(&self) -> &'static str {
        "schema"
    }
    fn check(&self, cx: &ValidationCx) -> Verdict {
        let envelope: EditEnvelope = match serde_json::from_str(cx.text()) {
            Ok(e) => e,
            Err(e) => return Verdict::Reject(format!("response is not valid edit JSON: {e}")),
        };
        if envelope.edits.is_empty() {
            return Verdict::Empty;
        }
        *cx.parsed.borrow_mut() = Some(envelope);
        Verdict::Pass
    }
}

/// Layer 3 — safety. The edits must not name anything forbidden. Today that is an
/// empty file path; this is the seam for path allow-lists / write-scope limits.
pub struct SafetyValidator;
impl Validator for SafetyValidator {
    fn name(&self) -> &'static str {
        "safety"
    }
    fn check(&self, cx: &ValidationCx) -> Verdict {
        let parsed = cx.parsed.borrow();
        let Some(envelope) = parsed.as_ref() else { return Verdict::Pass };
        for fe in &envelope.edits {
            if fe.file.trim().is_empty() {
                return Verdict::Reject("edit names an empty file path".to_string());
            }
        }
        Verdict::Pass
    }
}

/// Layer 4 — semantics. Every file must carry at least one edit and every span
/// must have a sane byte range.
pub struct SemanticValidator;
impl Validator for SemanticValidator {
    fn name(&self) -> &'static str {
        "semantic"
    }
    fn check(&self, cx: &ValidationCx) -> Verdict {
        let parsed = cx.parsed.borrow();
        let Some(envelope) = parsed.as_ref() else { return Verdict::Pass };
        for fe in &envelope.edits {
            if fe.edits.is_empty() {
                return Verdict::Reject(format!("no edits for file '{}'", fe.file));
            }
            for span in &fe.edits {
                if span.end_byte < span.start_byte {
                    return Verdict::Reject(format!(
                        "edit on '{}' has end_byte {} before start_byte {}",
                        fe.file, span.end_byte, span.start_byte
                    ));
                }
            }
        }
        Verdict::Pass
    }
}

/// Layer 5 — policy. Endpoint/policy constraints on what the model may return
/// (e.g. forbidding edits outside the workspace under an air-gapped policy). A
/// documented seam; passes today.
pub struct PolicyValidator;
impl Validator for PolicyValidator {
    fn name(&self) -> &'static str {
        "policy"
    }
    fn check(&self, _cx: &ValidationCx) -> Verdict {
        Verdict::Pass
    }
}

/// An ordered list of validators run against one response.
pub struct ValidationPipeline {
    validators: Vec<Box<dyn Validator>>,
}

impl ValidationPipeline {
    /// The full edit-gating pipeline: completeness → schema → safety → semantic →
    /// policy.
    pub fn for_edits() -> Self {
        Self {
            validators: vec![
                Box::new(CompletenessValidator),
                Box::new(SchemaValidator),
                Box::new(SafetyValidator),
                Box::new(SemanticValidator),
                Box::new(PolicyValidator),
            ],
        }
    }

    /// The text pipeline: completeness only (free-form output is never applied, so
    /// there is no schema/safety/semantic gate to run).
    pub fn for_text() -> Self {
        Self { validators: vec![Box::new(CompletenessValidator)] }
    }

    /// Run each layer in order, returning the first non-`Pass` verdict (or `Pass`
    /// if every layer passed).
    fn run(&self, cx: &ValidationCx) -> Verdict {
        for v in &self.validators {
            match v.check(cx) {
                Verdict::Pass => continue,
                other => return other,
            }
        }
        Verdict::Pass
    }
}

/// Validates a [`ModelResponse`] before any mutation. Stateless and pure: the same
/// response + expectation always validates to the same outcome.
pub struct ResponseValidator;

impl ResponseValidator {
    /// Validate a response against what the caller expected. Selects the pipeline
    /// from `expectation`, then builds the typed [`Validated`] from the (already
    /// validated) parse.
    pub fn validate(response: &ModelResponse, expectation: OutputExpectation) -> Validated {
        let cx = ValidationCx::new(response, expectation);
        let pipeline = match expectation {
            OutputExpectation::Edits => ValidationPipeline::for_edits(),
            // No structured tool-call grammar yet; gate on completeness like text.
            OutputExpectation::Text | OutputExpectation::ToolCalls => ValidationPipeline::for_text(),
        };

        match pipeline.run(&cx) {
            Verdict::Empty => Validated::Empty,
            Verdict::Reject(r) => Validated::Rejected(r),
            Verdict::Pass => match expectation {
                OutputExpectation::Edits => Validated::Edits(build_edits(&cx)),
                OutputExpectation::Text => Validated::Text(cx.text().to_string()),
                // A passing tool-call response carries nothing to apply yet.
                OutputExpectation::ToolCalls => Validated::Empty,
            },
        }
    }
}

/// Build the neutral [`ModelEdit`]s from the validated, parsed envelope. Only
/// called after the edit pipeline returned `Pass`, so the envelope is present and
/// structurally sound.
fn build_edits(cx: &ValidationCx) -> Vec<ModelEdit> {
    let parsed = cx.parsed.borrow();
    let Some(envelope) = parsed.as_ref() else { return Vec::new() };
    envelope
        .edits
        .iter()
        .map(|fe| ModelEdit { file: fe.file.clone(), spans: fe.edits.clone() })
        .collect()
}
