# Phase 2A: MCP Connectivity & Discovery

## Overview

Phase 2A transforms AI_support into an MCP-aware runtime by implementing the foundational MCP connectivity layer. This phase establishes infrastructure connectivity only - no tool execution or runtime orchestration is included.

## Technology Stack

| Component | Technology |
|-----------|------------|
| MCP SDK | `mcp>=1.0.0` |
| Configuration | PyYAML + Pydantic validation |
| Async runtime | asyncio |
| Logging | structlog |

## Architecture

```
src/
├── infrastructure/
│   └── mcp/
│       ├── __init__.py     # Public exports
│       ├── config.py       # Configuration models & loader
│       └── manager.py      # MCP client lifecycle manager
└── interfaces/
    └── server/
        └── main.py         # FastAPI lifespan integration
```

## Components

### 1. MCP Configuration (`config.py`)

#### MCPServerConfig

```python
from infrastructure.mcp.config import MCPServerConfig

config = MCPServerConfig(
    name="filesystem",          # Unique identifier (lowercase, alphanumeric + underscore)
    command="npx",               # Executable command
    args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    transport="stdio",          # Only stdio supported in Phase 2A
    enabled=True,               # Whether to start on initialization
)
```

#### MCPConfigLoader

Loads configuration from YAML with fallback to defaults:

```python
from infrastructure.mcp.config import MCPConfigLoader

loader = MCPConfigLoader("configs/mcp/servers.yaml")
config = loader.load()
```

### 2. MCP Client Manager (`manager.py`)

Manages MCP server lifecycle and tool registry:

```python
from infrastructure.mcp.manager import MCPClientManager

manager = MCPClientManager(config_path="configs/mcp/servers.yaml")
await manager.initialize()

# List discovered tools
tools = await manager.list_tools()
# {'filesystem/read_file': ToolInfo(...), 'filesystem/write_file': ToolInfo(...)}

# Check readiness
if manager.is_ready():
    print(f"Connected to {len(manager._servers)} servers")
    print(f"Total tools: {len(tools)}")

# Graceful shutdown
await manager.shutdown()
```

#### Tool Registry Format

Tools are namespaced as `{server_name}/{tool_name}`:

```python
ToolInfo(
    server="filesystem",
    original_name="read_file",
    definition={
        "name": "read_file",
        "description": "Read a file from the filesystem",
        "inputSchema": {...}
    }
)
```

#### ConnectedServer Structure

```python
@dataclass
class ConnectedServer:
    name: str                          # Server name from config
    config: MCPServerConfig            # Original configuration
    process: asyncio.subprocess.Process # Spawned subprocess (None for stdio)
    session: ClientSession             # MCP session
    read_stream: Any                   # Input stream
    write_stream: Any                  # Output stream
    tools: list[dict]                   # Discovered tool definitions
```

## Configuration File

**File:** `configs/mcp/servers.yaml`

```yaml
servers:
  - name: "filesystem"
    command: "npx"
    args:
      - "-y"
      - "@modelcontextprotocol/server-filesystem"
      - "/tmp"
    transport: "stdio"
    enabled: true

  - name: "git"
    command: "uvx"
    args:
      - "mcp-server-git"
    transport: "stdio"
    enabled: false

  - name: "terminal"
    command: "python"
    args:
      - "-m"
      - "mcp_server_terminal"
    transport: "stdio"
    enabled: false
```

### Adding a New MCP Server

1. Add server configuration to `configs/mcp/servers.yaml`:

```yaml
servers:
  - name: "my_server"
    command: "python"
    args:
      - "-m"
      - "my_mcp_server"
    transport: "stdio"
    enabled: true
```

2. Ensure the server implements MCP protocol (stdio transport)
3. Restart the server - the new server will be automatically discovered

## Startup Lifecycle

1. **Load Configuration** - Parse `configs/mcp/servers.yaml`
2. **Filter Enabled** - Select only `enabled: true` servers
3. **Spawn Servers** - For each server:
   - Spawn subprocess with stdio transport
   - Create MCP session
   - Perform initialize handshake (30s timeout)
   - Discover tools (30s timeout)
   - Normalize tool names (replace `/` and `-` with `_`)
   - Namespace tools as `{server_name}/{tool_name}`
4. **Build Registry** - Populate global tool registry
5. **Mark Ready** - Set `_initialized = True`

## Shutdown Lifecycle

1. Close all MCP sessions
2. Clear server registry
3. Clear tool registry
4. Mark as uninitialized

## Error Handling

| Error | Behavior |
|-------|----------|
| Config file missing | Load default config (filesystem only) |
| Invalid YAML | Raise `RuntimeError` |
| Invalid transport | Pydantic validation error |
| Command spawn failure | Log error, skip server, continue with others |
| Initialize timeout (30s) | Log error, cleanup, skip server |
| list_tools timeout (30s) | Log error, cleanup, skip server |
| Empty tools list | Log info, keep server connected |
| Process exits early | Log error, skip server |

## Testing

### Mock MCP Server

Located at `tests/mocks/mock_mcp_server.py`. Provides deterministic tools:

- `echo` - Echoes input message
- `add` - Adds two numbers
- `sleep` - Sleeps for N seconds (for timeout testing)

### Run Unit Tests

```bash
python -m pytest tests/unit/test_mcp_config.py -v
python -m pytest tests/unit/test_mcp_manager.py -v
```

### Run All Phase 2A Tests

```bash
python -m pytest \
  tests/unit/test_mcp_config.py \
  tests/unit/test_mcp_manager.py \
  -v
```

### Run with Coverage

```bash
python -m pytest \
  tests/unit/test_mcp_config.py \
  tests/unit/test_mcp_manager.py \
  --cov=src.infrastructure.mcp \
  --cov-report=term-missing
```

## Integration

### FastAPI Lifespan

MCP manager is integrated into the FastAPI lifespan:

```python
async with lifespan(app):
    mcp_manager = MCPClientManager()
    await mcp_manager.initialize()
    app.state.mcp_manager = mcp_manager
    yield
    await mcp_manager.shutdown()
```

### Accessing MCP Manager

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/tools")
async def list_mcp_tools():
    mcp_manager = app.state.mcp_manager
    if mcp_manager is None:
        return {"tools": [], "message": "MCP not initialized"}
    tools = await mcp_manager.list_tools()
    return {"tools": list(tools.keys()), "count": len(tools)}
```

## Troubleshooting

### Command Not Found

```
Error: No MCP servers could be started
```

**Cause:** Required command (npx, uvx) not installed.

**Solution:**
```bash
# For npx-based servers
npm install -g npx

# For uvx-based servers
pip install uv
```

### Timeout Errors

```
Error: MCP server initialization timed out
```

**Cause:** Server is slow to respond or hangs.

**Solution:** Check server logs, increase timeout in `manager.py`:
```python
INITIALIZE_TIMEOUT = 30.0  # Increase if needed
LIST_TOOLS_TIMEOUT = 30.0
```

### Empty Tool Registry

**Cause:** Server connected but returned no tools.

**Solution:** Check that the MCP server implements `list_tools` correctly.

## Non-Goals (Phase 2A)

| Category | What NOT implemented |
|----------|---------------------|
| Tool execution | No `call_tool()`, no invocation |
| Runtime orchestration | No per-session tool registries |
| Reliability | No retries, auto-restart, recovery |
| Runtime controls | No cancellation, timeouts, rate limiting |
| WebSocket integration | No tool_call messages |
| Persistence | No database storage |
| Remote transports | Only stdio, no HTTP/SSE/WebSocket |

## Definition of Done

- [x] MCPConfigLoader loads and validates servers.yaml (default config works)
- [x] MCPClientManager spawns each enabled server as a subprocess via stdio
- [x] MCP handshake (initialize) completes successfully (30s timeout)
- [x] list_tools() discovers tools from each server; empty tool list handled gracefully
- [x] Tools are namespaced (server_name/tool_name) and normalized (no `/` in tool name)
- [x] Global tool registry built correctly; duplicate namespaced tools log warning
- [x] is_ready() returns True only after successful initialization of at least one server
- [x] shutdown() closes all sessions, terminates processes, never raises
- [x] FastAPI lifespan integrates manager (startup & shutdown)
- [x] All unit tests pass (including mock MCP server tests)
- [x] Integration test verifies manager accessible via app.state
- [x] Code coverage for new code ≥ 80%
- [x] No regression of Phase 1B features
- [x] Documentation complete

## Next Phase (Phase 2B)

- Tool execution infrastructure
- Per-session tool registries
- Streaming responses
- Error handling for tool calls

---

## Phase 2A Files Summary

| File | Description | Lines |
|------|-------------|-------|
| `pyproject.toml` | Added mcp, pyyaml dependencies | - |
| `configs/mcp/servers.yaml` | MCP server configuration | 26 |
| `src/infrastructure/mcp/__init__.py` | Public exports | 20 |
| `src/infrastructure/mcp/config.py` | Config models & loader | 102 |
| `src/infrastructure/mcp/manager.py` | Client manager | 219 |
| `tests/mocks/mock_mcp_server.py` | Mock MCP server | 67 |
| `tests/unit/test_mcp_config.py` | Config unit tests | 138 |
| `tests/unit/test_mcp_manager.py` | Manager unit tests | 265 |
| `src/interfaces/server/main.py` | FastAPI integration | +30 |
| `docs/phase2a.md` | Documentation | This file |
