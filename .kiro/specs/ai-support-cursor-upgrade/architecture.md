# Kiro AI IDE — System Architecture Specification

## Overview

Kiro AI IDE is a next-generation intelligent development environment that combines traditional IDE capabilities with AI-powered code analysis, generation, and debugging assistance. The system is designed to be modular, extensible, and performant.

## System Components

### 1. Core Engine Layer

#### 1.1 AI Agent Core (`src/core/agent/`)
- **mock_agent.py** — Mock AI agent for Phase 1A streaming responses
- **reasoning_loop.py** — Reasoning loop for AI decision-making
- **reflection.py** — Self-reflection for AI improvement
- **state.py** — Agent state management

#### 1.2 Session Management (`src/core/session/`)
- **session_manager.py** — Main session orchestration
- **session_state.py** — Session state definitions
- **lifecycle.py** — Session lifecycle management
- **session_store.py** — Persistent session storage

#### 1.3 Runtime Management (`src/core/runtime/`)
- **runtime_manager.py** — Runtime orchestration
- **dispatcher.py** — Command/event dispatcher
- **scheduler.py** — Task scheduling

#### 1.4 Execution Engine (`src/core/execution/`)
- **executor.py** — Task executor
- **execution_graph.py** — Execution dependency graph
- **task_queue.py** — Async task queue

### 2. Intelligence Layer (`src/infrastructure/analysis/`)

#### 2.1 Rule Engine
- Static analysis engine with 100+ rules
- Categories: security, code quality, type safety, error handling, performance
- Framework-specific rules for TypeScript, React, FastAPI, Django

#### 2.2 Call Graph Analysis
- AST-based cross-file call graph
- Alias resolution for imports
- Reverse index for caller lookup
- Incremental indexing

#### 2.3 Data Flow Analysis
- Taint tracking from sources to sinks
- Local variable propagation
- Sanitizer recognition

### 3. Interface Layer (`src/interfaces/`)

#### 3.1 CLI (`src/interfaces/cli/`)
- Slash commands
- Autocomplete with prompt_toolkit
- Interactive review workflows
- Syntax highlighting with Pygments

#### 3.2 WebSocket Server (`src/interfaces/server/websocket/`)
- Real-time communication
- Streaming responses
- Event subscriptions

#### 3.3 TUI (`src/interfaces/tui/`)
- Terminal user interface
- Interactive screens
- Widget system

### 4. Plugin System (`src/infrastructure/plugins/`)

- Plugin discovery and loading
- Hot-reload support
- Manifest validation
- Lifecycle management (DISCOVERED → LOADED → ACTIVE → INACTIVE)

### 5. Collaboration Features (`src/application/workflows/collaboration/`)

- Comments and threads on findings
- Resolution state tracking
- PR review report generation

## Data Flow

```
User Input → CLI/TUI → Session Manager → Agent Core
                ↓                           ↓
         WebSocket Server ← → LLM Provider
                ↓
         Rule Engine → Call Graph → Data Flow Analyzer
                ↓
         Report Generator → CLI/HTML/JSON Output
```

## Configuration

### LLM Configuration (`configs/llm.yaml`)
- Provider selection (OpenAI, Ollama, Anthropic)
- Timeout settings
- Context window size
- Model selection

### Plugin Configuration
- Plugin directory path
- Hot-reload interval
- Required manifest fields

### Analysis Configuration
- File extensions to watch
- Ignore patterns
- Debounce duration
- Max dependent files per trigger

## Performance Requirements

| Operation | Target |
|-----------|--------|
| Single file analysis (1000 lines) | < 500ms |
| Incremental re-index | < 200ms |
| Watch mode update | < 3s from save |
| Full scan (500 files) | < 60s |
| Caller query via reverse index | < 5ms |

## Extensibility Points

1. **Custom Rules** — Register new detection rules via plugin system
2. **LLM Providers** — Add new LLM backends
3. **Output Formats** — Extend report generators
4. **Collaboration Backends** — Integrate with external tools
