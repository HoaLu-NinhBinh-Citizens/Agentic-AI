# ADR-001: Execution Layer Boundaries

## Status

Accepted

## Context

Phase 2B introduced a tool execution runtime on top of MCP connectivity. During implementation, we identified the need to clearly define boundaries between components to avoid the "god object" anti-pattern and ensure maintainability.

Previous approaches suffered from:
- Single monolithic tool manager handling everything
- Unclear responsibility boundaries
- Difficult to test individual components
- Hard to extend or swap implementations

## Decision

We will decompose the tool execution layer into distinct components with clear responsibilities:

### Component Responsibilities

#### 1. ToolTracker (src/core/execution/tool_tracker.py)

**Responsibility:** State management and history

**What it does:**
- Maintains pending calls queue
- Maintains completed calls history
- Provides async-safe state transitions
- Calculates duration metrics

**What it does NOT do:**
- Execute tools
- Handle timeouts
- Manage concurrency
- Know about MCP protocol

```python
class ToolTracker:
    async def add_pending(record: ToolCallRecord) -> None
    async def update_state(call_id: str, state: ToolCallState, **kwargs) -> bool
    async def get_pending_ids() -> list[str]
    async def close(mark_orphaned: bool = True) -> None
```

#### 2. ToolExecutor (src/infrastructure/tool_execution/executor.py)

**Responsibility:** Actual tool execution

**What it does:**
- Abstract base class for execution
- MCP implementation using MCPClientManager
- Returns raw result dictionaries

**What it does NOT do:**
- Track state
- Handle timeouts
- Manage concurrency
- Broadcast events

```python
class ToolExecutor(ABC):
    @abstractmethod
    async def execute(self, tool_name: str, arguments: dict) -> dict
```

#### 3. ToolRegistry (src/core/agent/tool_registry.py)

**Responsibility:** Dispatch and execution control

**What it does:**
- Wraps executor with semaphore
- Applies timeout via asyncio.wait_for
- Coordinates tracker and executor
- Handles error normalization

**What it does NOT do:**
- Know about WebSocket protocol
- Broadcast events
- Handle session lifecycle
- Manage session registries

```python
class ToolRegistry:
    async def call_tool(
        self,
        tool_name: str,
        arguments: dict,
        call_id: str | None = None,
        trace_id: str | None = None,
        parent_call_id: str | None = None
    ) -> tuple[str, dict]
```

#### 4. ToolExecutionService (src/application/orchestration/tool_execution/service.py)

**Responsibility:** Orchestration and transport separation

**What it does:**
- Looks up registries by session
- Broadcasts events (start/result/error)
- Handles session lifecycle errors
- Single entry point for transport layer

**What it does NOT do:**
- Execute tools directly
- Manage state
- Handle low-level concurrency

```python
class ToolExecutionService:
    async def execute_tool(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict,
        call_id: str | None = None,
        trace_id: str | None = None,
        broadcast_callback: BroadcastCallback | None = None
    ) -> None
```

### Data Flow

```
WebSocket → ToolExecutionService → ToolRegistry → ToolExecutor
                                       ↓
                                  ToolTracker
```

### Error Handling

Each component handles its own error domain:

1. **ToolExecutor**: Raises raw exceptions (network, MCP protocol)
2. **ToolRegistry**: Catches executor errors, normalizes via `normalize_tool_error()`
3. **ToolExecutionService**: Catches registry errors, broadcasts to clients
4. **WebSocket Handler**: Catches service errors, sends error events

## Consequences

### Positive

1. **Testability**: Each component can be tested in isolation
2. **Flexibility**: Easy to swap implementations (e.g., mock executor for testing)
3. **Maintainability**: Clear ownership reduces risk of regression
4. **Extensibility**: New executors (HTTP, gRPC) can be added without modifying other components

### Negative

1. **Indirection**: More files and interfaces to understand
2. **Overhead**: Small additional latency from layer separation

## Alternatives Considered

### Single God Object

Rejected because:
- Difficult to test
- Hard to extend
- Single responsibility violation
- Protocol and execution mixed

### Two-Layer (Registry + Executor)

Considered but rejected because:
- State tracking responsibilities unclear
- Timeout handling would need to be in both places
- Event broadcasting responsibility unclear

## Implementation Notes

- All async operations use `asyncio.Lock` for thread safety
- State transitions are atomic via `update_state()`
- History limit enforced with FIFO eviction
- Timeout uses `asyncio.wait_for` for deterministic behavior
- Concurrency uses `asyncio.Semaphore` for fair scheduling

## References

- Phase 2B specification
- Martin Fowler on Single Responsibility Principle
- Python asyncio patterns
