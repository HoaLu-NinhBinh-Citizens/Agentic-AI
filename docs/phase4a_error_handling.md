# Phase 4A – SemanticMemory Agent Error Handling Contract (v6)

**Status**: Implementation Complete
**Date**: 2026-05-17

## Overview

Tài liệu này định nghĩa cách AI Agent tương tác và xử lý lỗi của SemanticMemory system.

## Core Principle

All decisions must be derived from structured API state, not logs.

SemanticMemory là hệ thống:
- **best-effort**
- **silent-failure tolerant**
- **no-exception runtime**

## Agent Contract

Agent chỉ sử dụng **3 nguồn duy nhất**:

| Source | Type | Description |
|--------|------|-------------|
| `return value` | `bool` | `True` = success, `False` = failed/skipped/deduped |
| `memory.last_operation` | `MemoryOperation` | PRIMARY state source |
| `memory.health_check()` | `HealthStatus` | System health |

## NEVER Use Logs for Decision Making

Agents must **NOT** read logs for decision making. All decisions are based on structured state.

## API Contracts

### 1. Store API Contract

```python
success: bool = await memory.store_conversation(session_id, role, content)
```

#### Return Value

| Value | Meaning |
|-------|---------|
| `True` | Stored successfully |
| `False` | Failed OR skipped OR deduped OR no-memory |

#### last_operation State

```python
state = memory.last_operation
{
  "status": "success | failed | skipped | deduped | no_memory",
  "error_code": "string | null",       # e.g., "LIMIT_REACHED"
  "reason": "human readable explanation",
  "retryable": true | false,
  "dedup_parent_id": "string | null",
  "timestamp": 1234567890
}
```

### 2. Status Enum

| Status | Meaning | Agent Action |
|--------|---------|--------------|
| `success` | Write stored | Done |
| `failed` | System error | Check error_code, decide retry |
| `skipped` | Intentionally ignored | Done (non-blocking) |
| `deduped` | Already exists | Treat as SUCCESS |
| `no_memory` | System degraded | Continue without memory |

### 3. Error Code Enum

#### Retryable (TRANSIENT)

| Error Code | Meaning | Agent Action |
|------------|---------|--------------|
| `EMBEDDING_TIMEOUT` | Embedding request timed out | Retry max 2 times |
| `EMBEDDING_NETWORK_ERROR` | Network failure | Retry max 2 times |
| `OLLAMA_UNAVAILABLE` | Ollama service down | Retry max 2 times |
| `DB_CONNECTION_LOST` | Database connection lost | Retry max 2 times |

#### Non-retryable (PERMANENT)

| Error Code | Meaning | Agent Action |
|------------|---------|--------------|
| `DIMENSION_MISMATCH` | Embedding dimension changed | Do NOT retry |
| `LIMIT_REACHED` | Storage limit reached | Do NOT retry, alert system |
| `INVALID_INPUT` | Invalid input provided | Do NOT retry |
| `BLOOM_ERROR` | Bloom filter error | Do NOT retry |

#### Dedup

| Error Code | Meaning | Agent Action |
|------------|---------|--------------|
| `DUPLICATE_CONTENT` | Content already exists | Treat as SUCCESS |

#### System Degraded

| Error Code | Meaning | Agent Action |
|------------|---------|--------------|
| `NO_MEMORY_MODE` | System offline | Continue without memory |

## Store Decision Engine

### Step 1: Call store

```python
success = await memory.store_conversation(...)
```

### Step 2: If success == True

Done.

### Step 3: If success == False

Read the state:

```python
state = memory.last_operation
```

### Decision Rules

#### (A) Dedup Case (SAFE SUCCESS)

```python
if state.status == "deduped" or state.error_code == "DUPLICATE_CONTENT":
    # Treat as SUCCESS
    # Do NOT retry
    # Optionally use state.dedup_parent_id
```

#### (B) Limit Reached (FATAL)

```python
if state.error_code == "LIMIT_REACHED":
    # Do NOT retry
    # Action: stop writes, alert system
```

#### (C) Transient Errors (RETRYABLE)

```python
if state.error_code in {"EMBEDDING_TIMEOUT", "EMBEDDING_NETWORK_ERROR", 
                        "OLLAMA_UNAVAILABLE", "DB_CONNECTION_LOST"}:
    # Retry max 2 times
    # Backoff: 0.1s → 0.3s → 0.7s
```

#### (D) Permanent Errors (NO RETRY)

```python
if state.error_code == "DIMENSION_MISMATCH":
    # Do NOT retry
    # Action: stop memory writes, reinitialize if possible
```

#### (E) No-Memory Mode

```python
if state.status == "no_memory" or state.error_code == "NO_MEMORY_MODE":
    # System degraded
    # Action: continue agent normally, use local context only
```

#### (F) Unknown Failure

```python
# Retry 1 time only
# If still fail → fallback local memory
```

## Retry Policy

### Allowed Retries ONLY if:

```python
error_code in TRANSIENT_ERRORS
# EMBEDDING_TIMEOUT
# EMBEDDING_NETWORK_ERROR
# OLLAMA_UNAVAILABLE
# DB_CONNECTION_LOST
```

### Forbidden Retry Cases:

- `LIMIT_REACHED`
- `DIMENSION_MISMATCH`
- `NO_MEMORY_MODE`
- `DUPLICATE_CONTENT`

## Health Check Contract

```python
health = await memory.health_check()
```

### Response Structure

```python
{
  "status": "healthy | degraded | no_memory",
  "db": true | false,
  "embedding": true | false
}
```

### Status Meanings

| Status | Meaning | Agent Action |
|--------|---------|--------------|
| `healthy` | Full functionality | Proceed normally |
| `degraded` | Partial failure | Use fallback reasoning |
| `no_memory` | System offline | Use local context only |

### Important Rule

Call health check **ONLY before important writes**:

- User input memory
- Tool results
- Structured JSON
- Multi-paragraph content

## Retrieve Contract

```python
results = await memory.retrieve(query)
```

### Empty Result Handling

```python
if results == []:
    health = await memory.health_check()
    
    if health["status"] == "no_memory":
        # System offline
        use_fallback_reasoning()
    elif health["status"] == "healthy":
        # No relevant memory found
        relax_query()  # or proceed normally
    else:
        # degraded
        use_fallback_reasoning()
```

### Important Rule

Empty retrieval **≠ error**. It means "no relevant memory found".

## RAG Context Contract

```python
context = await memory.build_rag_context(query)
```

If empty string returned:
- **NOT an error**
- Means "no relevant context"

Agent behavior:
- Proceed normally
- Use base knowledge

## min_score Policy

| Scenario | min_score |
|----------|----------|
| Factual question | 0.7 |
| Normal RAG | 0.5 |
| Exploration | 0.4 |
| Unknown | 0.5 default |

## last_operation Default State

```python
memory.last_operation = None  # Initially
```

Rule:
- Do NOT retry based on missing state
- Treat as fresh session

## Dedup Semantics

```python
if state.status == "deduped":
    # Equivalent to success
    # No duplicate stored
    # Safe to continue
    # Optional: use state.dedup_parent_id for reference
```

## Retrieval Limitation

`retrieve()` is **probabilistic**. It does NOT guarantee full coverage of memory.

Causes of missing results:
- Small session data
- High min_score
- Embedding mismatch
- ANN approximation

Agent rule:
- Do NOT assume memory absence
- Try relaxed query before concluding

## No-Memory Mode

**Definition**: System is offline or degraded.

**Detection**:
```python
health.status == "no_memory"
```

**Agent behavior**:
- Continue reasoning
- Use local context only
- Avoid retries
- Optional caching

## Safe Patterns

### Pattern A – Safe Store

```python
for i in range(2):
    ok = await memory.store_conversation(...)
    if ok:
        break
    
    state = memory.last_operation
    if not state["retryable"]:
        break
    
    await asyncio.sleep(0.3 * (2 ** i))
```

### Pattern B – Fallback Store

```python
if not await memory.store_conversation(...):
    state = memory.last_operation
    if state.status == "deduped":
        pass  # Safe success
    else:
        local_cache.append(data)
```

### Pattern C – Safe Retrieve

```python
results = await memory.retrieve(query)

if not results:
    health = await memory.health_check()
    
    if health["status"] == "no_memory":
        use_local_context()
    else:
        relax_query()
```

### Pattern D – Health Check Before Write

```python
health = await memory.health_check()

if health["status"] == "no_memory":
    # Skip memory write, use local context
    return

if health["status"] == "degraded":
    # Proceed with caution, may fail
    pass

# Important write with fallback
try:
    await memory.store_conversation(...)
except:
    local_cache.append(data)
```

## Mental Model

SemanticMemory is:

> A probabilistic, best-effort semantic cache with partial recall guarantees

NOT:
- Database of truth
- Complete memory store
- Deterministic retrieval system

## Critical Rules

| Rule | Description |
|------|-------------|
| 1 | Never rely on logs |
| 2 | Always check return value |
| 3 | Always check last_operation when False |
| 4 | Dedup = success |
| 5 | Empty retrieval = valid state |
| 6 | No-memory mode ≠ error |
| 7 | Never block agent execution |

## Summary

This contract ensures:
- Deterministic agent behavior
- Safe failure handling
- Clear retry boundaries
- No silent ambiguity
- Production-grade resilience

## Implementation

| Component | File |
|-----------|------|
| SemanticMemory | `src/core/memory/semantic_memory.py` |
| EmbeddingService | `src/infrastructure/embeddings/embedding_service.py` |
| Tests | `tests/unit/test_semantic_memory_error_contract.py` |
