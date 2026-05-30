# AI_SUPPORT

**Local Embedded Engineering Intelligence System with Cursor-like Code Review**

AI_SUPPORT is a local embedded engineering intelligence system designed to assist developers with code review, analysis, and fix generation.

## Features

- **AI-Powered Code Review** - ML-specific, security, quality, embedded rules
- **Deep Code Understanding** - AST-based analysis, cross-file references
- **Intelligent Fixes** - Multi-option suggestions, LLM-powered generation
- **Conversational Interface** - Natural language interaction
- **Cursor-Style Reports** - Markdown, JSON, CLI output
- **Local LLM** - Ollama integration, privacy-first

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Start Ollama
ollama serve

# Run review
python -m src.interfaces.cli.main review src/
```

## Documentation

- [Quick Start](docs/QUICKSTART.md)
- [Configuration](docs/CONFIGURATION.md)
- [API Reference](docs/API.md)
- [Architecture](docs/ARCHITECTURE.md)

## Supported Languages

- Python, JavaScript, TypeScript
- C, C++, Rust, Go
- Java, and more...

## License

MIT
