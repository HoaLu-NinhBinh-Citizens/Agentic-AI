//! aircore library crate.
//!
//! The binary (`main.rs`) is a thin stdio/JSON-RPC shell over these modules;
//! exposing them as a library lets integration tests drive the engine directly.

pub mod capability;
pub mod context;
pub mod detector;
pub mod execution;
pub mod inference;
pub mod index;
pub mod ipc;
pub mod model_runtime;
pub mod planner;
pub mod protocol;
pub mod retrieval;
pub mod semantic;
pub mod symbols;
pub mod telemetry;
