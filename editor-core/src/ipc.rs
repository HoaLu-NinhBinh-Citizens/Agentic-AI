//! LSP-style `Content-Length` framing over stdio.
//!
//! Wire format (identical to the Language Server Protocol so the editor can
//! reuse `vscode-jsonrpc`):
//!
//! ```text
//! Content-Length: <N>\r\n
//! \r\n
//! <N bytes of UTF-8 JSON>
//! ```
//!
//! stdin carries requests from the editor; stdout carries responses. All
//! human-readable logging goes to stderr (see `main.rs`) so it never corrupts
//! the framed channel.

use std::io::{BufRead, Write};

use anyhow::{bail, Context, Result};

use crate::protocol::Response;

/// Reads one framed message from `reader`. Returns `Ok(None)` on clean EOF
/// (editor closed the pipe), which the main loop treats as a shutdown signal.
pub fn read_message<R: BufRead>(reader: &mut R) -> Result<Option<Vec<u8>>> {
    let mut content_length: Option<usize> = None;

    // Parse headers until the blank line that separates them from the body.
    loop {
        let mut line = String::new();
        let n = reader.read_line(&mut line).context("reading header line")?;
        if n == 0 {
            // EOF. If it lands mid-header that's a protocol error, but at the
            // start of a message it just means the peer hung up.
            return Ok(None);
        }

        let trimmed = line.trim_end_matches(['\r', '\n']);
        if trimmed.is_empty() {
            break; // end of headers
        }

        if let Some((key, value)) = trimmed.split_once(':') {
            if key.trim().eq_ignore_ascii_case("content-length") {
                let len = value
                    .trim()
                    .parse::<usize>()
                    .context("parsing Content-Length value")?;
                content_length = Some(len);
            }
            // Other headers (e.g. Content-Type) are accepted and ignored.
        } else {
            bail!("malformed header line: {trimmed:?}");
        }
    }

    let len = content_length.context("message missing Content-Length header")?;
    let mut body = vec![0u8; len];
    reader.read_exact(&mut body).context("reading message body")?;
    Ok(Some(body))
}

/// Writes one framed response to `writer` and flushes immediately so the
/// editor never waits on a buffered reply.
pub fn write_response<W: Write>(writer: &mut W, response: &Response) -> Result<()> {
    let body = serde_json::to_vec(response).context("serializing response")?;
    write!(writer, "Content-Length: {}\r\n\r\n", body.len())
        .context("writing response header")?;
    writer.write_all(&body).context("writing response body")?;
    writer.flush().context("flushing response")?;
    Ok(())
}
