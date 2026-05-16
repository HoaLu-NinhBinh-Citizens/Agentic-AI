# Phase 4A: SemanticMemory Core

**Status**: Implementation Complete
**Date**: 2026-05-16

## Overview

Phase 4A implements a production-ready SemanticMemory core enabling persistent semantic storage and retrieval for the AI agent. The system supports conversation memory, tool execution results, semantic retrieval for RAG, and efficient deduplication.

## Architecture

```
LLM Agent
   │
   ▼
SemanticMemory (Phase 4A Core)
   ├── EmbeddingService (Ollama bge-m3, reused session, LRU cache)
   ├── Chunker (JSON-aware + safe fallback)
   ├── Dedup Engine (window cosine + optional Bloom exact-match)
   ├── LanceDB Vector Store (with optional index, FLAT or IVF_FLAT)
   ├── Retriever (ANN → post-filter session_id & score)
   └── RAG Context Builder (score-aware, default threshold 0.5)
```

## Key Features

### 1. EmbeddingService

Async service for generating text embeddings using Ollama bge-m3.

**File**: `src/infrastructure/embeddings/embedding_service.py`

**Features**:
- Async HTTP via reused aiohttp.ClientSession
- LRU cache (default 4096 entries)
- Retry logic (2 attempts, 3s timeout)
- Dynamic dimension handling
- Health checks

```python
service = EmbeddingService(
    ollama_url="http://localhost:11434/api/embeddings",
    model="bge-m3:latest",
    cache_maxsize=4096
)
```

### 2. Chunker

Text chunking with JSON-aware splitting and safe fallback.

**File**: `src/core/memory/chunker.py`

**Strategies**:
| Strategy | Condition | Behavior |
|----------|-----------|----------|
| JSON (single) | Valid JSON ≤ 2000 chars | Store as one chunk |
| JSON (split) | Valid JSON > 2000 chars | Split by keys or array slices |
| JSON fallback | Invalid JSON | Use repr() as one chunk |
| Plain text | Non-JSON | Split by paragraphs/sentences |

### 3. Deduplication Engine

Two-layer deduplication for efficiency and accuracy.

**File**: `src/core/memory/deduplication.py`

**Layers**:
1. **Bloom filter** (optional): Exact-match dedup before embedding API call
2. **Window cosine**: Semantic dedup against last 20 embeddings (threshold 0.95)

### 4. SemanticMemory Core

LanceDB-backed semantic storage and retrieval.

**File**: `src/core/memory/semantic_memory.py`

**Data Schema**:
| Field | Type | Description |
|-------|------|-------------|
| id | str | Unique UUID |
| type | str | conversation or tool_result |
| content | str | Chunk text |
| embedding | List[float] | Vector |
| session_id | str | Top-level field (not in metadata) |
| metadata | dict | role, tool_name, tool_signature |
| created_at | int | Unix timestamp |
| chunk_index | int | 0-based |
| chunk_total | int | Total chunks |
| parent_id | str | UUID linking all chunks |

### 5. RAG Context Builder

Builds formatted context from retrieved memories.

```python
context = await memory.build_rag_context(
    query="weather in Paris",
    min_score=0.5,  # Safe default
    max_results=5
)
```

Output format:
```
[Memory Context]

Use ONLY if relevant. Ignore if not helpful.

1. (score: 0.87 | conversation:user) What's the capital of France?
2. (score: 0.82 | tool_result) Tool: weather_api -> Paris: 18°C
```

## Configuration

**File**: `configs/memory/semantic.yaml`

```yaml
memory:
  db_path: "./data/lancedb"

  embedding:
    ollama_url: http://localhost:11434/api/embeddings
    model: bge-m3:latest
    cache_maxsize: 4096
    timeout_seconds: 3

  chunking:
    max_chunk_size: 500
    max_json_chunk_size: 2000

  dedup:
    enable_bloom: true
    window_size: 20
    similarity_threshold: 0.95

  retrieval:
    default_top_k: 5
    default_min_score: 0.5
```

## Component Map

| Component | File | Description |
|-----------|------|-------------|
| EmbeddingService | `src/infrastructure/embeddings/embedding_service.py` | Ollama embeddings |
| EmbeddingCache | `src/infrastructure/embeddings/embedding_service.py` | LRU cache |
| Chunker | `src/core/memory/chunker.py` | Text splitting |
| DedupEngine | `src/core/memory/deduplication.py` | Deduplication |
| SemanticMemory | `src/core/memory/semantic_memory.py` | Core memory |
| RAGContext | `src/core/memory/semantic_memory.py` | Context builder |

## Usage Example

```python
memory = SemanticMemory(db_path="./data", enable_bloom_dedup=True)
await memory.init_db()

# Store conversation
await memory.store_conversation("sess_1", "user", "What is the capital of France?")
await memory.store_conversation("sess_1", "assistant", "Paris is the capital.")

# Store tool result
await memory.store_tool_result(
    "sess_1",
    "weather",
    {"city": "Paris"},
    "18°C, sunny"
)

# Build RAG context
context = await memory.build_rag_context("weather in Paris")
```

## Testing

**Unit Tests**:
- `tests/unit/test_chunker.py` - 14 tests
- `tests/unit/test_deduplication.py` - 15 tests
- `tests/unit/test_embedding_service.py` - 10 tests

## Definition of Done

- [x] Conversation turns stored as chunked embeddings (JSON-aware, safe fallback)
- [x] Tool results stored & retrievable (atomic batch)
- [x] Retrieval returns semantically relevant results with post-filtering (session_id, min_score)
- [x] RAG context builder outputs score-ranked context with safe default 0.5 threshold
- [x] Deduplication (window cosine + optional Bloom exact) prevents most duplicates
- [x] No blocking in agent loop (async everywhere)
- [x] Embedding dimension handled dynamically
- [x] LanceDB index created safely (only when beneficial, no unnecessary rebuilds)
- [x] Atomic batch insert – no partial parent writes, retry limit 2 attempts
- [x] Trivial content filtering prevents memory pollution

## Known Limitations

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| Window dedup only checks last 20 items | May miss duplicates far in history | Acceptable for Phase 4A |
| Bloom filter is in-memory only | Reset on restart | Acceptable for Phase 4A |
| Post-filtering by session_id may reduce recall | Small sessions may have fewer results | Acceptable for Phase 4A |
| No TTL or automatic expiry | Disk usage grows | Monitor externally |
| Fixed index parameters | May need tuning for >500k vectors | Log recommendations |

## Non-Goals (Phase 4B+)

- Tool caching
- Semantic router
- Compression / summarisation
- Advanced ranking / reranking
- Distributed vector DB
- Global semantic deduplication index
- Automatic index rebuilding
- Backpressure / eviction policies
