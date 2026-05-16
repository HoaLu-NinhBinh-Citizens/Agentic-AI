# Phase 2A: MCP Integration

## Overview

Phase 2A adds MCP (Model Context Protocol) connectivity to the runtime. The server can now connect to external MCP servers via stdio transport, discover their tools, and make them available for use by the agent.

## Technology Stack

| Component | Technology |
|-----------|------------|
| MCP Client | `mcp` Python SDK |
| Transport | stdio (subprocess-based) |
| Configuration | YAML + Pydantic validation |
| Tool Registry | In-memory dictionary with namespacing |

## Architecture

```
src/
├── core/
│   ├── agent/
│   │   └── mock_agent.py           # Mock agent with cancellation support
│   ├── session/
│   │   ├── session_manager.py      # Phase 1A in-memory manager
│   │   └── persistent_manager.py   # Phase 1B persistent session manager
│   ├── runtime/
│   │   ├── __init__.py           # Phase 1B RuntimeManager + lazy load Phase 15
│   │   └── runtime_manager.py     # Stream cancellation and timeout
│   └── rate_limiter.py            # Sliding window rate limiter
├── infrastructure/
│   ├── mcp/
│   │   ├── manager.py            # MCPClientManager for server lifecycle
│   │   └── config.py             # MCPConfigLoader and MCPServerConfig
│   └── persistence/
│       └── sqlite/
│           ├── schema.sql          # Database schema
│           └── session_store.py    # SQLite session store
├── interfaces/
│   └── server/
│       ├── main.py               # FastAPI server (Phase 2A)
│       └── websocket/
│           ├── client.py          # WebSocketClient with heartbeat/backpressure
│           └── manager.py          # Connection manager
└── runtime/                      # Stub for backward compatibility
    └── __init__.py                # Redirects to core.runtime
```

## MCP Configuration

### Configuration File

File: `configs/mcp/servers.yaml`

```yaml
servers:
  - name: filesystem
    command: npx
    args:
      - "-y"
      - "@modelcontextprotocol/server-filesystem"
      - "C:\\Users\\thang\\Desktop"
    transport: stdio
    enabled: true
```

### MCPServerConfig Schema

| Field | Type | Required | Description |
|-------|------|---------|-------------|
| `name` | string | Yes | Unique server name (lowercase, alphanumeric + underscore) |
| `command` | string | Yes | Executable (e.g., `npx`, `uvx`, `python`) |
| `args` | list[string] | No | Command-line arguments |
| `transport` | string | No | Only `stdio` supported (default: `stdio`) |
| `enabled` | boolean | No | Whether to start this server (default: `true`) |

## Key Components

### MCPClientManager

`src/infrastructure/mcp/manager.py`

Responsibilities:
- Load MCP server configurations from YAML
- Spawn enabled servers as stdio subprocesses
- Perform MCP initialization handshake
- Discover tools from each server
- Build global namespaced tool registry
- Graceful shutdown of all servers

#### Initialization Flow

```
1. Load configuration from servers.yaml
2. Filter enabled servers
3. For each server:
   a. Spawn subprocess with stdio transport
   b. Create MCP ClientSession
   c. Perform initialize handshake (60s timeout)
   d. List tools (30s timeout)
   e. Normalize tool names and namespace
   f. Add to global registry
4. Mark initialization complete
```

#### Tool Naming

Tools are namespaced by server name to avoid collisions:

```
server_name/tool_name
```

Example:
```
filesystem/read_file
filesystem/write_file
browser/navigate
```

### MCPConfigLoader

`src/infrastructure/mcp/config.py`

Loads and validates MCP server configurations from YAML files.

### Default Configuration

If no `configs/mcp/servers.yaml` exists, the following default is used:

```yaml
servers:
  - name: filesystem
    command: npx
    args:
      - "-y"
      - "@modelcontextprotocol/server-filesystem"
      - "C:\\Users\\thang\\Desktop"
    transport: stdio
    enabled: true
```

## Server Lifecycle

### Startup

1. Create `MCPClientManager` with config path
2. Call `await mcp_manager.initialize()`
3. If no servers can start, log warning and continue (server still runs)
4. MCP manager is attached to `app.state.mcp_manager`

### Shutdown

1. Call `await mcp_manager.shutdown()`
2. Close all write streams
3. Close all read streams
4. Exit stdio context managers (terminates subprocesses)
5. Clear registries

## Error Handling

| Error | Behavior |
|-------|----------|
| Config file not found | Use default configuration |
| YAML parse error | Raise RuntimeError |
| Command not found | Log error, skip server |
| Initialization timeout | Log error, skip server |
| Tool listing timeout | Log error, skip server |
| Tool name collision | Keep first, warn about duplicate |

### Timeout Values

| Operation | Timeout |
|-----------|---------|
| MCP initialization handshake | 60 seconds |
| List tools | 30 seconds |
| Tool execution | Not implemented (Phase 2A) |

## Limitations (Phase 2A)

| Feature | Status |
|---------|--------|
| stdio transport | ✅ Supported |
| Tool discovery | ✅ Supported |
| Tool execution (call_tool) | ❌ Not implemented |
| Tool result handling | ❌ Not implemented |
| Server-to-server communication | ❌ Not implemented |
| Streaming tools | ❌ Not implemented |
| Resource subscriptions | ❌ Not implemented |

## How to Run

### Start the Server

```bash
python -m uvicorn interfaces.server.main:app --reload
```

Or run directly:

```bash
python -m interfaces.server.main
```

### Verify MCP Status

Check server logs for MCP initialization:

```
INFO: MCP client manager initialized, servers=1, total_tools=5
```

Or check the warning if MCP fails:

```
WARNING: MCP initialization failed: No MCP servers could be started. Check that required commands (npx, uvx) are installed.
```

## Testing

### Run All Phase 2A Tests

```bash
python -m pytest \
  tests/unit/test_mcp_config.py \
  tests/unit/test_mcp_manager.py \
  tests/integration/test_mcp_phase2a.py \
  -v
```

### Run MCP Manager Tests Only

```bash
python -m pytest tests/unit/test_mcp_manager.py -v
```

### Run MCP Config Tests Only

```bash
python -m pytest tests/unit/test_mcp_config.py -v
```

### Run Integration Tests

```bash
python -m pytest tests/integration/test_mcp_phase2a.py -v
```

## Test Files

| File | Description |
|------|-------------|
| `tests/unit/test_mcp_config.py` | MCPConfigLoader and MCPServerConfig tests |
| `tests/unit/test_mcp_manager.py` | MCPClientManager lifecycle tests |
| `tests/integration/test_mcp_phase2a.py` | Full MCP integration tests |

## Definition of Done

- [x] Server loads MCP configuration from YAML
- [x] Servers spawn as stdio subprocesses
- [x] Initialization handshake completes successfully
- [x] Tools are discovered and namespaced correctly
- [x] Timeout handling works for slow servers
- [x] Graceful shutdown closes all servers
- [x] Server runs even if MCP fails to initialize
- [x] All tests pass
- [x] Documentation complete

## Next Phase (Phase 2B - Explicitly NOT in Phase 2A)

- Tool execution (call_tool support)
- Tool result streaming
- Server-to-server communication
- Multiple transport support (sse, http)
- MCP resource management
- MCP prompt templates
- Real agent with LLM integration
