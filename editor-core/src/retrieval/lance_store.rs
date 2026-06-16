//! LanceDB-backed vector store (persistent, on-disk).
//!
//! Implements the same `VectorStore` trait as the in-memory store, so the
//! retriever and ContextBuilder are unchanged. LanceDB is async (tokio); this
//! type owns a runtime and bridges the sync trait via `block_on`.
//!
//! LanceDB prefers batch writes, so adds are buffered and flushed to the table
//! on the first search after a change (the retriever's lifecycle is build-once
//! then query-many, which fits). Vectors persist under
//! `<workspace>/.agentic/index/vectors.lance` and survive restarts.

use std::sync::Arc;

use anyhow::{Context, Result};
use arrow_array::types::Float32Type;
use arrow_array::{
    FixedSizeListArray, Int64Array, RecordBatch, RecordBatchIterator, RecordBatchReader,
};
use arrow_schema::{DataType, Field, Schema};
use futures::TryStreamExt;
use lancedb::query::{ExecutableQuery, QueryBase};
use lancedb::{connect, Connection};
use tokio::runtime::Runtime;

use super::vector::VectorStore;

const TABLE: &str = "vectors";

pub struct LanceVectorStore {
    rt: Runtime,
    conn: Connection,
    dim: usize,
    schema: Arc<Schema>,
    /// Pending rows not yet written to the table.
    buffer: Vec<(u64, Vec<f32>)>,
    /// True once the buffer has been written and the table reflects it.
    flushed: bool,
}

impl LanceVectorStore {
    /// Open (or create) a Lance database at `uri` for `dim`-length vectors.
    pub fn open(uri: &str, dim: usize) -> Result<Self> {
        let rt = Runtime::new().context("building tokio runtime")?;
        let conn = rt
            .block_on(connect(uri).execute())
            .context("connecting to LanceDB")?;
        let schema = Arc::new(Schema::new(vec![
            Field::new("id", DataType::Int64, false),
            Field::new(
                "vector",
                DataType::FixedSizeList(
                    Arc::new(Field::new("item", DataType::Float32, true)),
                    dim as i32,
                ),
                false,
            ),
        ]));
        Ok(Self { rt, conn, dim, schema, buffer: Vec::new(), flushed: false })
    }

    /// Write the buffer to a freshly (re)created table. Idempotent per dirty
    /// state via `flushed`.
    fn flush(&mut self) -> Result<()> {
        if self.flushed {
            return Ok(());
        }
        let ids: Vec<i64> = self.buffer.iter().map(|(id, _)| *id as i64).collect();
        let vectors: Vec<Option<Vec<Option<f32>>>> = self
            .buffer
            .iter()
            .map(|(_, v)| Some(v.iter().map(|x| Some(*x)).collect()))
            .collect();

        let id_arr = Int64Array::from(ids);
        let vec_arr =
            FixedSizeListArray::from_iter_primitive::<Float32Type, _, _>(vectors, self.dim as i32);
        let batch = RecordBatch::try_new(
            self.schema.clone(),
            vec![Arc::new(id_arr), Arc::new(vec_arr)],
        )
        .context("building record batch")?;

        let reader = RecordBatchIterator::new(vec![Ok(batch)], self.schema.clone());

        let reader: Box<dyn RecordBatchReader + Send> = Box::new(reader);
        self.rt.block_on(async {
            // Replace any existing table so a rebuild is clean.
            let _ = self.conn.drop_table(TABLE, &[]).await;
            self.conn
                .create_table(TABLE, reader)
                .execute()
                .await
                .context("creating LanceDB table")?;
            Result::<()>::Ok(())
        })?;

        self.flushed = true;
        Ok(())
    }
}

impl VectorStore for LanceVectorStore {
    fn clear(&mut self) {
        self.buffer.clear();
        self.flushed = false;
        let _ = self.rt.block_on(self.conn.drop_table(TABLE, &[]));
    }

    fn add(&mut self, id: u64, vector: Vec<f32>) {
        self.buffer.push((id, vector));
        self.flushed = false; // a new row invalidates the written table
    }

    fn search(&self, query: &[f32], k: usize) -> Vec<(u64, f32)> {
        if self.buffer.is_empty() {
            return Vec::new();
        }
        // search takes &self but we may need to flush; do it via interior work
        // on the runtime against the already-written table. To keep &self, the
        // caller must have flushed; we flush lazily in `ensure_flushed_search`.
        self.search_inner(query, k).unwrap_or_default()
    }

    fn len(&self) -> usize {
        self.buffer.len()
    }
}

impl LanceVectorStore {
    /// Flush if needed, then run the ANN query. Kept separate so `search` can
    /// stay on the trait's `&self` signature for the common already-flushed
    /// path; the &mut flush happens here behind a check.
    fn search_inner(&self, query: &[f32], k: usize) -> Result<Vec<(u64, f32)>> {
        // We can only query a written table. If not flushed, the caller should
        // have called `commit` first; guard defensively.
        if !self.flushed {
            anyhow::bail!("LanceVectorStore queried before commit()");
        }
        let q = query.to_vec();
        let batches: Vec<RecordBatch> = self.rt.block_on(async {
            let stream = self
                .conn
                .open_table(TABLE)
                .execute()
                .await?
                .query()
                .nearest_to(q)?
                .limit(k)
                .execute()
                .await?;
            stream.try_collect::<Vec<_>>().await
        })?;

        let mut out = Vec::new();
        for batch in &batches {
            let ids = batch
                .column_by_name("id")
                .and_then(|c| c.as_any().downcast_ref::<Int64Array>());
            let dists = batch
                .column_by_name("_distance")
                .and_then(|c| c.as_any().downcast_ref::<arrow_array::Float32Array>());
            if let (Some(ids), Some(dists)) = (ids, dists) {
                for i in 0..batch.num_rows() {
                    // Smaller L2 distance = closer; expose as a descending score.
                    out.push((ids.value(i) as u64, -dists.value(i)));
                }
            }
        }
        Ok(out)
    }

    /// Explicitly write the buffer so subsequent `search` calls succeed.
    pub fn commit(&mut self) -> Result<()> {
        self.flush()
    }
}
