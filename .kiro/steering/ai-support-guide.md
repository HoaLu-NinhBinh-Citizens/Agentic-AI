---
inclusion: fileMatch
fileMatchPattern: ['AI_support/**']
---

# AI_support Guide

`AI_support` is the local AI-agent system for CARV. It is separate from the STM32 firmware tree.

Use `AI_support` for agent runtime, LLM adapters, RAG/PDF knowledge tooling, AI KiCad domains, validators, services, generated/review/runtime support, and tests.

Do not put firmware application source here unless it is a generated draft or fixture.

## Map

- `app/`: CLI entrypoints, orchestration facades, UI launchers
- `agent/`: generic plan/execute/observe loop
- `llm/`: model/provider adapters
- `retrieval/`: RAG ingestion, vector/index/query logic
- `multi_agent/`: prototype agents; Agent 1 PDF Knowledge Agent lives here
- `domains/knowledge/`: AI KiCad Approved KB pipeline
- `domains/firmware/`: firmware JSON/schema/source-generation gates
- `domains/eda/`: KiCad output/schema/ERC/DRC logic
- `domains/validation/`: cross-domain validation
- `services/`: shared runtime, evidence, review, and document services
- `tools/`: file/build/process helpers
- `config/`: prompts, config loaders, output/write policies
- `models/`: shared dataclasses/schemas
- `tests/`: pytest regression and smoke tests
- `data/`, `outputs/`, `rag_index/`, `retrieval_reports/`, `ai_agent_memory/`: runtime or generated state

## Commands

Run tests from the repository root:

```powershell
python -m pytest AI_support\tests\test_pdf_knowledge_agent.py -q
python -m pytest AI_support\tests\test_aikicad_agent.py -q
python -m pytest AI_support\tests -q
```

Useful CLI commands from the repository root:

```powershell
python -m AI_support.app.embedded_agent smoke
python -m AI_support.app.embedded_agent pdf-index --kb-project <name> --pdf <path>
python -m AI_support.app.embedded_agent pdf-validate --kb-project <name>
python -m AI_support.app.embedded_agent aikicad-kb-build --pdf <path> --project-id <id>
python -m AI_support.app.embedded_agent aikicad-tool-status --target-platform STM32 --language C
```

## Invariants

- Schema-first outputs are mandatory.
- Approved KB data must come from cited PDF evidence, not inference.
- Missing information blocks downstream generation.
- Human review overrides are append-only under `AI_support/data/review/`.
- Generated reports belong under `AI_support/outputs/`.
- Runtime caches belong under `AI_support/data/`, `AI_support/rag_index/`, or `AI_support/outputs/`.
- Do not add Python implementation files directly under `AI_support/` root.

## Agent 1

Agent 1 has two related layers:

- `multi_agent/pdf_knowledge_agent.py`: indexes and queries PDFs into a cited local KB.
- `domains/knowledge/agent.py`: builds and validates an AI KiCad Approved KB from PDF evidence.

Rules:

- Every extracted technical field needs a citation with PDF page evidence.
- Tables need row/table citations when table data is used.
- Low-confidence OCR fallback must require human review.
- KiCad generation requires package/footprint evidence when `require_kicad_fields=True`.
- If an approved KB is reused from cache, re-check the current validation requirements.

## Hotspots

- `app/cli.py`: command boundary and exit codes
- `domains/knowledge/validators.py`: Approved KB safety gates
- `domains/schema_validator.py`: JSON Schema contract behavior
- `domains/firmware/`: firmware output must stay schema-first
- `domains/eda/`: KiCad generation must not guess missing footprint/symbol data
- `multi_agent/pdf_knowledge_agent.py`: citation integrity, table extraction, OCR/image metadata

