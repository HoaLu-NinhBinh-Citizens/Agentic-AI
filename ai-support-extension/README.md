# AI Support - VSCode Extension

AI-powered embedded engineering assistant for CARV firmware development.

## Features

- **Code Analysis**: Analyze selected C code for embedded systems
- **Driver Generation**: Generate peripheral drivers (UART, SPI, I2C, etc.)
- **Hardware Analysis**: Analyze hardware dependencies and peripheral relationships
- **Register Explanation**: Explain STM32 registers and bit fields
- **Configuration Validation**: Validate MCU configuration code
- **Documentation Search**: Search embedded documentation

## Requirements

- VSCode 1.85+
- Node.js 18+
- [Ollama](https://ollama.ai/) running locally (for AI features)

## Quick Start

### Installation

```bash
cd ai-support-extension
npm install
```

### Run in Development Mode

1. Press **F5** to launch the extension in debug mode
2. The Extension Development Host window will open
3. Use `Ctrl+Shift+P` to open Command Palette

### Commands

| Command | Description |
|---------|-------------|
| `AI Support: Analyze Selected Code` | Analyze highlighted code |
| `AI Support: Explain Register/Peripheral` | Explain a register or peripheral |
| `AI Support: Validate MCU Configuration` | Validate configuration code |
| `AI Support: Search Documentation` | Search embedded docs |

### Configuration

```json
{
    "ai-support.ollamaUrl": "http://localhost:11434",
    "ai-support.model": "llama3.1:latest",
    "ai-support.maxTokens": 2048,
    "ai-support.enableContext": true
}
```

## Build and Package

```bash
# Compile TypeScript
npm run compile

# Package as .vsix
npm run package

# Install locally
code --install-extension ai-support-0.1.0.vsix
```

## Project Structure

```
ai-support-extension/
├── src/
│   ├── extension.ts      # Main entry point
│   ├── ollamaClient.ts   # Ollama API client
│   ├── codeAnalyzer.ts   # Code analysis features
│   ├── hardwareAnalyzer.ts # Hardware analysis
│   ├── contextManager.ts # Project context management
│   ├── treeViews.ts      # Sidebar tree views
│   └── test/
│       └── extension.test.ts
├── package.json
├── tsconfig.json
└── .vscodeignore
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     VSCode Host                          │
├─────────────────────────────────────────────────────────┤
│  extension.ts                                           │
│    ├── CodeAnalyzer                                     │
│    ├── HardwareAnalyzer                                 │
│    ├── ContextManager                                   │
│    └── OllamaClient                                     │
│              │                                          │
│              ▼                                          │
│  ┌─────────────────────────────────────────────────────┐│
│  │           Ollama Local LLM Server                   ││
│  │              (localhost:11434)                       ││
│  └─────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

## License

MIT
