# Local LLM Setup for AI_SUPPORT

This guide explains how to set up and use local LLM (Ollama) as the default provider for AI_SUPPORT code analysis and fix generation.

## Overview

AI_SUPPORT can use local LLM models via Ollama for:

- **Complex fix generation** - Generate intelligent code fixes
- **Code explanation** - Get detailed explanations of issues
- **Context-aware suggestions** - AI-powered code review and recommendations
- **Security analysis** - Detect vulnerabilities in code
- **ML code review** - Find common ML/Deep Learning bugs

## Installation

### 1. Install Ollama

**macOS/Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Windows:**
Download from https://ollama.com/download

### 2. Pull Recommended Models

```bash
# For best code understanding (requires 40GB+ RAM)
ollama pull llama3.1:70b

# For balanced performance (requires 8GB+ RAM)
ollama pull llama3.1:8b

# For fast local execution (requires 4GB+ RAM)
ollama pull llama3.2:3b

# For code-specialized tasks
ollama pull qwen2.5-coder:7b
ollama pull codellama:13b
```

### 3. Start Ollama

```bash
# Start the Ollama server
ollama serve

# Or run in background
ollama serve &
```

### 4. Verify Installation

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Should return JSON with available models
```

## Configuration

### Environment Variables

```bash
# Set default model
export OLLAMA_MODEL=llama3.1:8b

# Or use a specific model
export OLLAMA_MODEL=qwen2.5-coder:7b
```

### Programmatic Configuration

```python
from src.infrastructure.llm.local_provider import LocalLLMProvider, LLMConfig

# Create provider with custom settings
config = LLMConfig(
    base_url="http://localhost:11434/api",
    model="llama3.1:8b",
    temperature=0.3,
    max_tokens=2048,
    timeout=120.0,
)

provider = LocalLLMProvider(config)
```

## Usage

### Basic Fix Generation

```python
import asyncio
from src.core.llm_fixes import LLMFixEngine, CodeFinding

async def generate_fix():
    engine = LLMFixEngine(model="llama3.1:8b")

    finding = {
        "rule_id": "SEC001",
        "message": "Hardcoded API key detected",
        "severity": "CRITICAL",
        "old_code": "api_key = 'sk-1234567890abcdef'",
        "file_path": "config.py",
        "language": "python"
    }

    fix = await engine.generate_fix(finding, context="")
    if fix:
        print(f"Fix: {fix.new_code}")
        print(f"Explanation: {fix.explanation}")

asyncio.run(generate_fix())
```

### Code Review

```python
from src.core.llm_fixes import LLMFixEngine

async def review_code():
    engine = LLMFixEngine(model="llama3.1:8b")

    code = '''
    import torch
    model = MyModel()
    model.train()
    output = model(torch.randn(1, 10))  # Missing no_grad!
    loss = criterion(output, target)
    loss.backward()
    '''

    result = await engine.review_code(code, review_type="ml", language="python")
    if result:
        for finding in result.findings:
            print(f"[{finding['severity']}] {finding['message']}")
```

### Streaming Fixes

```python
async def stream_fix():
    engine = LLMFixEngine(model="llama3.1:8b")

    finding = {"rule_id": "TEST", "message": "Add error handling"}

    async for chunk in engine.stream_fix(finding):
        print(chunk, end="", flush=True)
```

### Health Check

```python
from src.infrastructure.llm.local_provider import LocalLLMProvider

async def check_availability():
    provider = LocalLLMProvider()

    if await provider.is_available():
        models = await provider.list_models()
        print("Available models:", [m.name for m in models])
    else:
        print("Ollama is not running. Start with: ollama serve")
```

## Model Recommendations

| Model | RAM Required | Best For | Speed |
|-------|--------------|----------|-------|
| `llama3.2:3b` | 4GB | Simple tasks, fast responses | Fastest |
| `llama3.1:8b` | 8GB | General code analysis | Fast |
| `llama3.1:70b` | 40GB | Complex reasoning | Slow |
| `qwen2.5-coder:7b` | 8GB | Code-specific tasks | Fast |
| `codellama:13b` | 12GB | Code generation | Medium |

## Troubleshooting

### Ollama not running

```bash
# Start Ollama server
ollama serve

# Check if running
ps aux | grep ollama
```

### Model not found

```bash
# Pull the model
ollama pull llama3.1:8b

# List installed models
ollama list
```

### Out of memory

Use a smaller model:
```bash
ollama pull llama3.2:3b
```

### Connection refused

1. Make sure Ollama is running: `ollama serve`
2. Check port 11434 is accessible
3. Try: `curl http://localhost:11434/api/tags`

## API Reference

### LocalLLMProvider

```python
class LocalLLMProvider:
    def __init__(self, config: LLMConfig = None)

    async def generate(self, prompt: str, system: str = None) -> str
    async def generate_stream(self, prompt: str, system: str = None) -> AsyncIterator[str]
    async def is_available() -> bool
    async def list_models() -> list[LocalModelInfo]
```

### LLMFixEngine

```python
class LLMFixEngine:
    def __init__(self, model: str = "llama3", ...)
    async def generate_fix(finding, context, fix_type) -> Optional[LLMFix]
    async def explain_finding(finding, context) -> Optional[str]
    async def review_code(code, review_type, language) -> Optional[LLMReviewResult]
    async def stream_fix(finding, context) -> AsyncIterator[str]
    async def is_available() -> bool
```

### LLMFix

```python
@dataclass
class LLMFix:
    old_code: str
    new_code: str
    explanation: str
    confidence: float  # 0.0 - 1.0
    risk_level: str    # LOW, MEDIUM, HIGH
    rule_id: str
    severity: str      # CRITICAL, HIGH, MEDIUM, LOW
```

## Integration with Existing Code

The local LLM module integrates with existing infrastructure:

```python
# Use with existing LLM client
from src.infrastructure.llm import LLMClient, configure_llm, LLMConfig

# Configure to use Ollama
config = LLMConfig(provider=Provider.OLLAMA, model="llama3.1:8b")
configure_llm(config)

# Get the client
client = get_llm_client()
```

## Security Considerations

- **Local processing**: All code stays on your machine
- **No data transmission**: Nothing sent to external APIs
- **Model control**: Full control over which model is used
- **Privacy**: Sensitive code never leaves your environment
