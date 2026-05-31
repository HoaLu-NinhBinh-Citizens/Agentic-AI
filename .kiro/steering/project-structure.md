---
inclusion: fileMatch
fileMatchPattern: ['AI_support/**']
---

# AI_support Structure

Place new Python code by responsibility:

- `app/`: CLI, UI, orchestration entry points
- `agent/`: planning, execution, agent control flow
- `llm/`: model/provider adapters
- `retrieval/`: indexing, embeddings, RAG query flow
- `memory/`: persistent memory store
- `domains/`: firmware, EDA, validation, knowledge domain logic
- `services/`: shared application services
- `tools/`: build, file, process, and async utilities
- `parsing/`: response parsing and sanitization
- `config/`: config loaders, prompts, policies
- `models/`: schemas and data models
- `tests/`: tests and test fixtures
- `docs/`: AI_support documentation
- `outputs/`, `data/`, `rag_index/`: generated or runtime data

Rules:

- Do not create new top-level folders under `AI_support/` unless the user asks.
- Put tests under `AI_support/tests`.
- Put runtime data in `data/`, `outputs/`, or `rag_index`, not beside source code.
- Prefer `memory/` over legacy `ai_agent_memory/`.
- Prefer `outputs/` over legacy `retrieval_reports/`.
- Use existing `benchmarking/` and `reporting/` only for behavior already located there.
