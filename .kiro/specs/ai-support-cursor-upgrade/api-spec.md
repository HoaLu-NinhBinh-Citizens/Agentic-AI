# Kiro AI IDE — API Specification

## REST API Endpoints

### Health & Status

#### `GET /health`
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2026-05-31T12:00:00Z"
}
```

#### `GET /api/v1/status`
System status with component states.

**Response:**
```json
{
  "agent": "active",
  "session_manager": "ready",
  "rule_engine": {
    "loaded_rules": 100,
    "categories": ["security", "code_quality", "type_safety", "error_handling", "performance"]
  },
  "call_graph": {
    "indexed_files": 150,
    "total_functions": 1200,
    "total_calls": 3500
  }
}
```

### Analysis

#### `POST /api/v1/analyze`
Analyze source code files.

**Request:**
```json
{
  "files": ["src/main.py", "src/utils.py"],
  "categories": ["security", "code_quality"],
  "incremental": true
}
```

**Response:**
```json
{
  "findings": [
    {
      "file": "src/main.py",
      "line": 42,
      "rule_id": "SEC001",
      "severity": "HIGH",
      "message": "SQL injection vulnerability detected",
      "code_context": "cursor.execute(query)",
      "fix_template": "Use parameterized queries instead"
    }
  ],
  "stats": {
    "files_analyzed": 2,
    "duration_seconds": 0.45,
    "total_findings": 1
  }
}
```

#### `POST /api/v1/analyze/stream`
Streaming analysis with real-time updates.

**Response:** Server-Sent Events (SSE)
```
event: finding
data: {"file": "src/main.py", "line": 42, "rule_id": "SEC001", ...}

event: progress
data: {"files_analyzed": 5, "total_files": 10}

event: complete
data: {"total_findings": 15, "duration_seconds": 2.3}
```

### Call Graph

#### `GET /api/v1/call-graph/{file_path}`
Get call graph for a specific file.

**Response:**
```json
{
  "file": "src/main.py",
  "functions": [
    {
      "name": "main",
      "line": 1,
      "calls": ["process_input", "validate"]
    }
  ],
  "imports": [
    {"alias": "np", "original": "numpy"}
  ]
}
```

#### `GET /api/v1/callers/{function_name}`
Get all callers of a function.

**Query Parameters:**
- `file_path` (optional) — Filter by file

**Response:**
```json
{
  "callee": "validate",
  "callers": [
    {"file": "src/main.py", "line": 45, "arguments": ["user_input"]},
    {"file": "src/utils.py", "line": 12, "arguments": ["data"]}
  ]
}
```

### Data Flow Analysis

#### `POST /api/v1/dataflow/analyze`
Analyze taint tracking in source code.

**Request:**
```json
{
  "file": "src/handler.py",
  "sources": ["input", "request.args"],
  "sinks": ["exec", "eval", "cursor.execute"]
}
```

**Response:**
```json
{
  "findings": [
    {
      "source": {
        "variable": "user_input",
        "function": "input",
        "line": 10,
        "type": "user_input"
      },
      "sink": {
        "function": "exec",
        "line": 25,
        "argument": "user_input"
      },
      "severity": "CRITICAL",
      "path": ["user_input -> line 15 -> cmd -> line 25"]
    }
  ]
}
```

### Sessions

#### `POST /api/v1/sessions`
Create a new analysis session.

**Request:**
```json
{
  "project_path": "/path/to/project",
  "config": {
    "categories": ["security"],
    "exclude_patterns": ["*.test.py"]
  }
}
```

**Response:**
```json
{
  "session_id": "sess_abc123",
  "created_at": "2026-05-31T12:00:00Z",
  "status": "active"
}
```

#### `GET /api/v1/sessions/{session_id}`
Get session state.

#### `DELETE /api/v1/sessions/{session_id}`
Terminate a session.

### Plugins

#### `GET /api/v1/plugins`
List all discovered plugins.

**Response:**
```json
{
  "plugins": [
    {
      "name": "custom-rules",
      "version": "1.0.0",
      "state": "active",
      "description": "Custom security rules"
    }
  ]
}
```

#### `POST /api/v1/plugins/{plugin_name}/reload`
Hot-reload a plugin.

### Collaboration

#### `POST /api/v1/comments`
Create a comment on a finding.

**Request:**
```json
{
  "file": "src/main.py",
  "line": 42,
  "rule_id": "SEC001",
  "body": "This is a critical issue that needs fixing",
  "author": "developer@example.com"
}
```

**Response:**
```json
{
  "comment_id": "cmt_xyz789",
  "thread_id": "thr_abc456",
  "created_at": "2026-05-31T12:00:00Z"
}
```

#### `POST /api/v1/threads/{thread_id}/resolve`
Resolve a review thread.

**Request:**
```json
{
  "state": "resolved",
  "resolver": "lead@example.com"
}
```

#### `GET /api/v1/reports/pr`
Generate PR review report.

**Query Parameters:**
- `format` — `markdown`, `html`, `json`
- `include_threads` — boolean

### Reports

#### `GET /api/v1/reports/download`
Download analysis report.

**Query Parameters:**
- `format` — `cli`, `html`, `json`, `markdown`
- `session_id` — Session to generate report for

## WebSocket API

### Connection
`ws://localhost:8765/ws`

### Authentication
```json
{"type": "auth", "token": "your-token"}
```

### Event Types

#### Client → Server

| Event | Payload | Description |
|-------|---------|-------------|
| `analyze` | `{files: string[], options: object}` | Start analysis |
| `subscribe` | `{events: string[]}` | Subscribe to events |
| `comment` | `{finding: object, body: string}` | Add comment |
| `llm_query` | `{prompt: string, context: object}` | Query LLM |

#### Server → Client

| Event | Payload | Description |
|-------|---------|-------------|
| `finding` | Finding object | New finding detected |
| `progress` | `{current: number, total: number}` | Analysis progress |
| `llm_response` | `{text: string, done: boolean}` | LLM streaming response |
| `error` | `{code: string, message: string}` | Error occurred |

## Error Responses

All API endpoints return errors in this format:

```json
{
  "error": {
    "code": "ANALYSIS_FAILED",
    "message": "Failed to parse file",
    "details": {
      "file": "src/main.py",
      "line": 42,
      "reason": "SyntaxError"
    }
  }
}
```

| HTTP Status | Error Code | Description |
|-------------|------------|-------------|
| 400 | INVALID_REQUEST | Malformed request |
| 401 | UNAUTHORIZED | Missing/invalid auth |
| 404 | NOT_FOUND | Resource not found |
| 422 | VALIDATION_ERROR | Schema validation failed |
| 500 | INTERNAL_ERROR | Server error |
| 503 | SERVICE_UNAVAILABLE | Component unavailable |
