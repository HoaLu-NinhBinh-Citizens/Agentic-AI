# AI_SUPPORT Configuration

## Configuration File

Create `config.yaml` in project root:

```yaml
# Review Engine
review:
  focus_areas:
    - ml
    - security
    - quality
    - embedded
  confidence_threshold: 0.7
  max_findings: 100

# LLM Settings
llm:
  provider: local  # local, openai, anthropic
  model: llama3:70b
  base_url: http://localhost:11434
  temperature: 0.3
  max_tokens: 2048

# Indexing
indexing:
  incremental: true
  parallel_workers: 4
  chunk_size: 2000
  watch_mode: true

# Fix Engine
fix:
  auto_apply_safe: false
  create_backup: true
  backup_dir: .ai_support/backups
  max_attempts: 3

# Reporting
reporting:
  format: markdown  # markdown, json, cli
  severity_emoji: true
  show_confidence: true
  top_fixes: 3
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_SUPPORT_LLM_MODEL` | llama3 | LLM model name |
| `AI_SUPPORT_LLM_URL` | http://localhost:11434 | Ollama URL |
| `AI_SUPPORT_DATA_DIR` | .ai_support | Data directory |
| `AI_SUPPORT_LOG_LEVEL` | INFO | Log level |
