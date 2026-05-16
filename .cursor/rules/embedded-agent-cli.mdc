---
description: Local embedded agent CLI guidance
globs: AI_support/app/embedded_agent.py, AI_support/agent/**, AI_support/llm/**, AI_support/tests/test_embedded_agent*.py
alwaysApply: false
---

# Embedded Agent CLI

- This rule is only for work on `AI_support.app.embedded_agent`.
- Do not run nested agent tasks during normal Cursor work.
- Run the CLI only when the user asks to test the local embedded agent, or when editing/testing that agent.
- Use `--plan-mode` for complex firmware, protocol, build, flash, debugging, or multi-step tasks.
- Do not use `--plan-mode` for simple single-step tasks.
- Respect explicit `--force-model openai` or `--force-model ollama`.

Commands from repo root:

```bash
python -m AI_support.app.embedded_agent smoke
python -m AI_support.app.embedded_agent task "<task>" --plan-mode
python -m AI_support.app.embedded_agent task "<task>" --force-model ollama
python -m AI_support.app.embedded_agent task "<task>" --plan-mode --force-model openai
```
