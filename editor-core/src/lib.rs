//! aircore library crate.
//!
//! The binary (`main.rs`) is a thin stdio/JSON-RPC shell over these modules;
//! exposing them as a library lets integration tests drive the engine directly.

pub mod index;
pub mod ipc;
pub mod protocol;
pub mod symbols;
