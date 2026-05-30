# API Reference

## UnifiedReviewEngine

```python
from src.application.workflows.unified import UnifiedReviewEngine, ReviewEngineConfig

config = ReviewEngineConfig(
    focus_areas=["ml", "security"],
    output_format="markdown"
)
engine = UnifiedReviewEngine(config)

result = await engine.review(["src/"])
print(result.output)
```

### UnifiedSuggestionEngine

```python
from src.application.suggestion import UnifiedSuggestionEngine

engine = UnifiedSuggestionEngine()

suggestion = await engine.generate(finding, context)
print(f"Best fix: {suggestion.best_option.new_code}")
```

### LocalLLMProvider

```python
from src.infrastructure.llm import LocalLLMProvider, LLMConfig

config = LLMConfig(model="llama3:70b")
provider = LocalLLMProvider(config)

async with provider as p:
    if await p.is_available():
        response = await p.generate("Explain data leakage in ML")
        print(response)
```

## Classes

### UnifiedReviewEngine

| Method | Description |
|--------|-------------|
| `review(paths)` | Run review on files/directories |
| `get_findings()` | Get all findings |
| `apply_fix(finding_id)` | Apply a specific fix |

### UnifiedSuggestionEngine

| Method | Description |
|--------|-------------|
| `generate(finding, context)` | Generate fix options |
| `generate_batch(findings)` | Generate for multiple findings |

### LocalLLMProvider

| Method | Description |
|--------|-------------|
| `generate(prompt)` | Generate completion |
| `generate_stream(prompt)` | Stream completion |
| `is_available()` | Check if Ollama is running |
| `list_models()` | List available models |
