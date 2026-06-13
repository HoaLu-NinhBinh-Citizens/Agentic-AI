# Benchmark Plan — Performance Validation

> **Document type**: Read-only planning — no code was modified.
> **Date**: 2026-06-13
> **Rule**: Defines WHAT to measure. Does NOT estimate values.

---

## 1. Metrics to Measure

### 1.1 Retrieval Latency

| Metric | Description | When to Measure | Task |
|--------|-------------|-----------------|------|
| `lexical_search_latency_ms` | Time for `_search_chunk_store()` from query to ranked results | Before and after T-03 | T-03 |
| `semantic_search_latency_ms` | Time for `_search_vector_index()` from query embedding to results | Before and after T-03 | T-03 |
| `hybrid_search_latency_ms` | Time for full `HybridRetriever.search_docs()` including merge and rerank | Before and after T-03 | T-03 |
| `retrieval_latency_p50_ms` | 50th percentile of `hybrid_search_latency_ms` over 100 queries | After T-03 | T-03 |
| `retrieval_latency_p99_ms` | 99th percentile | After T-03 | T-03 |

**Dataset sizes to benchmark**: 1K chunks, 10K chunks, 100K chunks.

**Query set**: 20 representative queries covering function names, error messages, natural language descriptions, and hardware register names.

### 1.2 Completion Latency

| Metric | Description | When to Measure | Task |
|--------|-------------|-----------------|------|
| `completion_latency_ms` | Time from cursor position to ghost text displayed | Before and after T-04 | T-04 |
| `completion_with_retrieval_latency_ms` | Same, with retrieval context injection enabled | After T-04 | T-04 |
| `completion_cache_hit_ratio` | Fraction of completion requests served from LRU cache | Continuous | T-04 |

**Note**: Completion latency includes 150ms debounce. Measure from after debounce.

### 1.3 Indexing Latency

| Metric | Description | When to Measure | Task |
|--------|-------------|-----------------|------|
| `full_index_time_s` | Time for initial full sync of workspace | Before and after T-03 | T-03 |
| `incremental_index_time_ms` | Time to re-index a single changed file | Before and after T-03 | T-03 |
| `fts5_build_time_s` | Time to build FTS5 index from existing chunk data | After T-03 | T-03 |
| `fts5_update_time_ms` | Time to update FTS5 index for one chunk insert/update/delete | After T-03 | T-03 |

**Dataset sizes**: 100 files, 1K files, 10K files.

### 1.4 LLM Request Latency

| Metric | Description | When to Measure | Task |
|--------|-------------|-----------------|------|
| `llm_time_to_first_token_ms` | Time from request sent to first token received | Before and after T-04 | T-04 |
| `llm_total_generation_time_s` | Time from request to done event | Before and after T-02 | T-02 |
| `stream_timeout_headroom_s` | `STREAM_TIMEOUT_SEC` minus actual `llm_total_generation_time_s` | After T-02 | T-02 |

**Providers to benchmark**: Ollama (local), OpenAI, Anthropic.

### 1.5 Memory Usage

| Metric | Description | When to Measure | Task |
|--------|-------------|-----------------|------|
| `server_rss_mb` | Resident set size of the server process at steady state | Before and after each phase | All |
| `server_rss_after_indexing_mb` | RSS after indexing 10K files | Before and after T-03 | T-03 |
| `session_cache_memory_mb` | Memory consumed by in-memory session cache | Before and after T-02 | T-02 |
| `embedding_cache_memory_mb` | Memory consumed by LRU embedding cache (4096 entries) | Baseline | T-04 |
| `fts5_db_size_mb` | Size of SQLite DB with FTS5 table | After T-03 | T-03 |
| `idempotency_db_size_mb` | Size of persistent idempotency store | After T-05 | T-05 |
| `connection_pool_memory_mb` | Memory consumed by HTTP connection pools | Before and after T-04 | T-04 |

### 1.6 CPU Usage

| Metric | Description | When to Measure | Task |
|--------|-------------|-----------------|------|
| `cpu_during_indexing_pct` | CPU usage during full index sync | Before and after T-03 | T-03 |
| `cpu_idle_pct` | CPU usage at idle (no active requests) | Before and after T-05 | T-05 |
| `cpu_during_recovery_pct` | CPU usage during FileWatcher/MCP recovery | After T-05 | T-05 |

**Important**: `cpu_idle_pct` must not increase after T-05 (watchdog should not spin).

### 1.7 Cache Hit Ratio

| Metric | Description | When to Measure | Task |
|--------|-------------|-----------------|------|
| `embedding_cache_hit_ratio` | Fraction of embedding requests served from LRU cache | Continuous | T-04 |
| `completion_cache_hit_ratio` | Fraction of completion requests served from cache | Continuous | T-04 |
| `fts5_cache_hit_ratio` | SQLite page cache hit ratio for FTS5 queries | After T-03 | T-03 |

---

## 2. Benchmark Methodology

### 2.1 Environment

- **Isolation**: Benchmarks run on a dedicated machine or in a clean container. No other CPU/IO-intensive processes.
- **Warm-up**: 10 warm-up iterations before measurement.
- **Iterations**: Minimum 50 iterations per measurement. Report mean, p50, p95, p99, min, max.
- **Variance**: If coefficient of variation > 10%, investigate and control the source of variance.

### 2.2 Datasets

| Dataset | Size | Purpose |
|---------|------|---------|
| `small` | 100 files, ~5K LOC | Sanity check, fast iteration |
| `medium` | 1K files, ~50K LOC | Typical small project |
| `large` | 10K files, ~500K LOC | Target scale |
| `stress` | 100K chunks (pre-built) | FTS5 scaling test only |

Use the same datasets before and after each change for valid comparison.

### 2.3 Before/After Protocol

For every metric:
1. Measure on the commit BEFORE the change (baseline)
2. Measure on the commit AFTER the change
3. Report: absolute values, delta, percentage change
4. Flag regressions (any metric > 10% worse)

---

## 3. Per-Task Benchmark Schedule

| Task | Metrics to Measure | Dataset |
|------|-------------------|---------|
| T-02 | `llm_total_generation_time_s`, `stream_timeout_headroom_s`, `server_rss_mb` | N/A (config change, use real LLM) |
| T-01 | `server_rss_mb` (should decrease), startup time | `small` |
| T-03 | All retrieval + indexing metrics | `small`, `medium`, `large`, `stress` |
| T-04 | All completion + LLM + memory + cache metrics | `medium` |
| T-05 | `cpu_idle_pct`, `cpu_during_recovery_pct`, `idempotency_db_size_mb` | `small` |

---

## 4. Regression Thresholds

No absolute targets are defined (those require baseline measurements). Instead:

| Condition | Action |
|-----------|--------|
| Any latency metric increases > 10% | Investigate. May be acceptable if offset by quality gain. |
| Any latency metric increases > 50% | Block merge. Must be fixed or justified. |
| Memory usage increases > 20% | Investigate. Document cause. |
| Memory usage increases > 100% | Block merge. |
| CPU idle increases at all | Block merge. Watchdog must not spin. |
| Cache hit ratio decreases > 5% | Investigate. May indicate cache key change. |
