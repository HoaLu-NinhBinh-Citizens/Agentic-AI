# Phase 3: Hybrid LLM Gateway - Autonomous Tool Calling

**Status**: Implementation Complete
**Date**: 2026-05-16

## Overview

Phase 3 builds a hybrid LLM agent that replaces the MockAgent. The agent can accept natural language messages, automatically select between local Ollama and cloud Groq providers, stream real tokens to clients, and execute tool calls autonomously with proper error handling and observability.

## Key Features

### 1. Unified LLM Provider Interface

All LLM providers implement a common interface with streaming and tool call support.

**File**: `src/infrastructure/llm/provider.py`

```python
class LLMProvider(ABC):
    @property
    def name(self) -> str: ...

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamEvent]: ...
```

**Stream Event Types**:
| Type | Description |
|------|-------------|
| `token` | Text token from LLM response |
| `tool_call_start` | Start of a tool call |
| `tool_call_delta` | Partial arguments for a tool call |
| `done` | Stream completion |
| `error` | Error occurred |

### 2. ToolCallAccumulator

Handles partial JSON arguments during streaming. Tool calls may arrive in multiple chunks.

**File**: `src/infrastructure/llm/tool_accumulator.py`

```python
class ToolCallAccumulator:
    def add_tool_call_start(self, index, call_id, function_name): ...
    def add_tool_call_delta(self, index, call_id, function_name, arguments): ...
    def finalize(self) -> list[ToolCall]: ...
```

**Features**:
- Buffers partial JSON arguments
- Parses complete JSON only at stream end
- Handles multiple tool calls per response
- Validates arguments before returning

### 3. Tool Schema Normalizer

Converts MCP tools to unified format with version tracking.

**File**: `src/infrastructure/llm/tool_schema.py`

```python
UNIFIED_TOOL_SCHEMA_VERSION = "1.0"

def convert_mcp_to_unified(mcp_tool: dict) -> dict | None: ...
def normalize_tools(mcp_tools: list, provider_type: str) -> list: ...
```

**Supported Provider Formats**:
- OpenAI
- Anthropic
- Ollama
- Groq

### 4. LLMRouter with Circuit Breakers

Routes requests based on complexity, availability, and circuit breaker state.

**File**: `src/infrastructure/llm/router.py`

```python
class LLMRouter:
    async def select_provider(
        self,
        message: str,
        tools: list[dict] | None = None,
        client_hint: str | None = None,
    ) -> LLMProvider | None: ...
```

**Routing Logic**:
1. Respect client hint if available and circuit closed
2. Estimate complexity from message and tools
3. Low complexity → local (Ollama)
4. High complexity → cloud (Groq)
5. Fallback to any available provider

**Complexity Estimation**:
- Keyword weights (analyze, design, debug, etc.)
- Tool count factor
- Message length factor

### 5. OllamaProvider

Local LLM inference with streaming support.

**File**: `src/infrastructure/llm/ollama_provider.py`

**Features**:
- Connects to `http://localhost:11434`
- Default model: `qwen2.5-coder:7b`
- Streaming responses
- Tool calling support
- Configurable timeout

### 6. GroqProvider

Cloud LLM inference with OpenAI-compatible API.

**File**: `src/infrastructure/llm/groq_provider.py`

**Features**:
- Uses Groq's fast inference API
- Default model: `llama-3.3-70b-versatile`
- Streaming responses
- Tool calling support
- API key from `GROQ_API_KEY` environment variable

### 7. LLMAgentService

Orchestrates the complete agent flow.

**File**: `src/application/llm/agent_service.py`

```python
class LLMAgentService:
    async def process_message(
        self,
        session_id: str,
        client_id: str,
        trace_id: str,
        messages: list[dict[str, str]],
        event_callback: EventCallback,
        provider_hint: str | None = None,
    ) -> None: ...
```

**Features**:
- Token-based context truncation (8K default)
- Provider selection and fallback
- Parallel tool execution with concurrency limits
- Per-tool timeouts (30s default)
- Consecutive failure tracking
- Maximum tool rounds (10 default)

### 8. LLM Metrics

Comprehensive observability for LLM operations.

**File**: `src/infrastructure/observability/llm_metrics.py`

**Metrics**:
| Metric | Type | Labels |
|--------|------|--------|
| `llm_request_total` | Counter | provider, success |
| `llm_request_duration_ms` | Histogram | provider |
| `llm_token_usage_total` | Counter | provider, type |
| `provider_fallback_total` | Counter | from, to |
| `tool_calls_total` | Counter | tool, success |
| `tool_call_duration_ms` | Histogram | tool |
| `provider_circuit_breaker_total` | Counter | provider, action |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     WebSocket Handler                             │
│  chat message (optional "provider") → LLMAgentService          │
└─────────────────────────────────────────────────────────────────┘
                                 │
┌────────────────────────────────┼────────────────────────────────┐
│                  Hybrid LLM Gateway                             │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Provider Registry & Router                               │  │
│  │   - selects provider per request (content‑based + hint) │  │
│  │   - circuit breakers per provider                       │  │
│  │   - fallback chain with retry & rotation                │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Provider implementations                                 │  │
│  │   - OllamaProvider (local, streaming, tool calls)      │  │
│  │   - GroqProvider (cloud, OpenAI-compatible)            │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ ToolCallAccumulator (handles partial JSON arguments)    │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
                                 │
┌────────────────────────────────┼────────────────────────────────┐
│                     LLMAgentService                             │
│  - selects provider once per request (sticky)                  │
│  - calls LLM with streaming, accumulates tool calls          │
│  - token‑based context truncation                             │
│  - parallel tool execution with per‑tool timeout               │
│  - fallback & circuit breaker integration                     │
│  - emits metrics (latency, token usage, fallback rate)        │
└────────────────────────────────────────────────────────────────┘
```

## Configuration

**File**: `configs/llm/hybrid.yaml`

```yaml
llm:
  router:
    provider_order: ["local", "cloud"]
    fallback_enabled: true
    complexity_threshold: 0.6
    keyword_weights:
      analyze: 0.3
      design: 0.3
      debug: 0.25
      optimize: 0.25

  providers:
    local:
      type: ollama
      base_url: http://localhost:11434
      model: qwen2.5-coder:7b
      temperature: 0.1
      max_tokens: 4096
      timeout_seconds: 120
      circuit_breaker:
        failure_threshold: 3
        window_seconds: 60

    cloud:
      groq:
        enabled: true
        api_key_env: GROQ_API_KEY
        model: llama-3.3-70b-versatile
        temperature: 0.1
        timeout_seconds: 60
        circuit_breaker:
          failure_threshold: 2

  agent:
    max_tool_rounds: 10
    max_concurrent_tools: 5
    max_context_tokens: 8000
    tool_timeout_seconds: 30
    consecutive_failure_limit: 3
```

## Component Map

| Component | File | Description |
|-----------|------|-------------|
| LLMProvider | `src/infrastructure/llm/provider.py` | Abstract provider interface |
| StreamEvent | `src/infrastructure/llm/provider.py` | Unified stream events |
| ToolCall | `src/infrastructure/llm/provider.py` | Parsed tool call |
| ToolCallAccumulator | `src/infrastructure/llm/tool_accumulator.py` | Partial JSON buffer |
| ToolSchemaNormalizer | `src/infrastructure/llm/tool_schema.py` | Schema conversion |
| LLMRouter | `src/infrastructure/llm/router.py` | Provider selection |
| OllamaProvider | `src/infrastructure/llm/ollama_provider.py` | Local inference |
| GroqProvider | `src/infrastructure/llm/groq_provider.py` | Cloud inference |
| LLMAgentService | `src/application/llm/agent_service.py` | Agent orchestration |
| LLMMetrics | `src/infrastructure/observability/llm_metrics.py` | Observability |

## Testing

**Unit Tests**:
- `tests/unit/test_tool_accumulator.py` - 16 tests
- `tests/unit/test_tool_schema.py` - 18 tests
- `tests/unit/test_llm_router.py` - 15 tests

**Test Coverage**: Phase 3 components have comprehensive unit tests.

## Definition of Done

- [x] All providers implement unified stream_chat with tool call accumulation
- [x] Router selects provider per request using heuristics + circuit breaker checks
- [x] Agent uses token-based context window (no truncation by message count)
- [x] Tool calls executed in parallel with concurrency limit and per-call timeout
- [x] Tool results include duration, retry count, and error codes
- [x] Metrics and structured logs emitted for every LLM request and tool call
- [x] Circuit breakers prevent repeated calls to failing providers
- [x] Fallback chain works: cloud fails → local; if local fails → degrade gracefully
- [x] WebSocket streaming sends tokens in real time
- [x] All tests pass, coverage ≥ 80%

## Non-Goals (Phase 4+)

- OpenTelemetry / distributed tracing
- Tool caching and deduplication
- Multi-turn memory management
- Persistent session state for LLM
- Fine-grained token budgeting per user
- Custom tool definitions via API

## Hardware Context

- **RAM**: 16GB (comfortable for 7B models)
- **GPU**: GTX 1660Ti (6GB VRAM)
- **Local Model**: qwen2.5-coder:7b
- **Cloud**: Groq free tier (optional fallback)

## Performance Considerations

| Aspect | Current | Future Improvement |
|--------|---------|-------------------|
| Token counting | Heuristic (4 chars/token) | tiktoken integration |
| Context truncation | Simple reverse truncation | Priority-based (keep system + recent) |
| Provider health | Periodic check | Proactive probe |
| Tool execution | Semaphore concurrency | Per-tool thread pool |
