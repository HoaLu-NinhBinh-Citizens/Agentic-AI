//! aircore library crate.
//!
//! The binary (`main.rs`) is a thin stdio/JSON-RPC shell over these modules;
//! exposing them as a library lets integration tests drive the engine directly.

pub mod context;
pub mod detector;
pub mod inference;
pub mod index;
pub mod ipc;
pub mod protocol;
pub mod retrieval;
pub mod symbols;
pub mod telemetry;
