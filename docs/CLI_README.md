# Agentic-AI CLI

Production coding agent CLI inspired by oh-my-pi, with embedded systems focus.

## Features

- **Rich Terminal UI** - ANSI colors, tool cards, markdown rendering
- **LLM Integration** - Ollama, OpenAI, Anthropic support
- **Tool System** - File operations, search, shell execution
- **Session Management** - Persistent sessions with history
- **Hindsight Memory** - retain/recall/reflect for long-term memory

## Quick Start

### Interactive Mode

```bash
# Start interactive CLI
python -m src.interfaces.cli.agentic_cli

# With verbose output
python -m src.interfaces.cli.agentic_cli -v
```

### One-Shot Mode

```bash
# Single prompt
python -m src.interfaces.cli.agentic_cli --one-shot "list Python files"

# With project path
python -m src.interfaces.cli.agentic_cli --project /path/to/project
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_PROVIDER` | `ollama` | Provider: ollama, openai, anthropic |
| `AI_MODEL` | `qwen2.5-coder:7b` | Model name |
| `AI_BASE_URL` | `http://localhost:11434` | API base URL |
| `AI_API_KEY` | - | API key (for OpenAI/Anthropic) |

## Commands

### Built-in Commands

| Command | Description |
|---------|-------------|
| `help` | Show help |
| `tools` | List available tools |
| `session` | Show session info |
| `models` | List available LLM models |
| `clear` | Clear screen |
| `exit` | Exit CLI |

### Slash Commands

| Command | Description |
|---------|-------------|
| `/model <name>` | Switch model |
| `/verbose` | Toggle verbose mode |
| `/memory` | Show memory commands |

## Tools

### File Tools

- `read` - Read files with selectors
- `write` - Write files
- `edit` - Hashline editing
- `find` - Find files by glob

### Search Tools

- `search` - Regex search (uses ripgrep if available)
- `grep` - Alias for search

### Shell Tools

- `bash` - Execute shell commands
- `pwd` - Print working directory
- `cd` - Change directory

## Architecture

```
src/interfaces/cli/agentic_cli.py     # CLI entry point
src/infrastructure/
├── agent/agent_loop.py              # Agent think-act-observe loop
├── llm/client.py                    # LLM provider abstraction
├── session/session_manager.py        # Session persistence
├── memory/hindsight.py              # Hindsight memory system
├── tools/
│   ├── tool_registry.py             # Unified tool registry
│   ├── hashline.py                  # Hashline edit format
│   └── builtin/                    # Built-in tools
└── tui/
    ├── app.py                       # TUI application
    └── components.py                # TUI components
```

## Session Storage

Sessions are stored in `~/.config/ai-support/sessions/`.

## Hindsight Memory

Hindsight memory is stored in `~/.config/ai-support/memory/<project_id>/bank.json`.

Commands:
- `retain <fact>` - Store a fact
- `recall <query>` - Search memory
- `reflect <question>` - Ask about memories

## Embedded Systems Features

Agentic-AI includes special tools for embedded development:

- Hardware target understanding
- Register analysis
- Flash/HIL support (coming soon)
- Deterministic debugging (coming soon)

## Differences from oh-my-pi

| Feature | Agentic-AI | oh-my-pi |
|---------|-----------|----------|
| Language | Python | TypeScript + Rust |
| Target | Embedded/Automotive | General coding |
| Memory | Hindsight | Hindsight |
| Edit | Hashline | Hashline |
| LSP/DAP | Coming soon | Built-in |
| Browser | Coming soon | Built-in |

## Development

```bash
# Run from project root
cd C:\Users\thang\Desktop\Agentic-AI

# Install dependencies
pip install httpx

# Run CLI
python -m src.interfaces.cli.agentic_cli
```
