# AI_support

`AI_support` is the local AI-agent side of the project. It is intentionally
separate from the embedded firmware/application tree.

The source code lives under `src/` with the package name `AI_support`.

The rule is simple:

- Firmware/application code belongs outside this package.
- Agent runtime, RAG indexes, generated drafts, memory, tests, and PDF
  knowledge-base tooling belong inside this package.
- Generated code must be written under `ai_generated/` unless an
  explicit allowlist says otherwise.

## Quick Start

### 1. Frontend (Web UI)

```powershell
# Navigate to frontend
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
# Opens at http://localhost:5173
```

### 2. Backend API Server

```powershell
# From repository root
python -m AI_support.app.api_server
# Runs at http://localhost:8766

# Or with port
python -m AI_support.app.api_server --port 8766
```

### 3. CLI Agent (Terminal)

```powershell
# Basic task
python -m AI_support.app.embedded_agent task "Generate UART driver for STM32F407"

# Smoke test
python -m AI_support.app.embedded_agent smoke

# Benchmark
python -m AI_support.app.embedded_agent benchmark
```

---

## Web UI Routes

| Route | Description |
|-------|-------------|
| `/` | Dashboard - Real-time system monitoring |
| `/path-finder` | File search and browse |
| `/kb-builder` | Build knowledge base from PDF |
| `/agent` | AI Agent chat interface |

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/status` | GET | System status |
| `/api/metrics` | GET/POST | Metrics |
| `/api/logs` | GET/POST | Logs |
| `/api/tools` | GET/POST | Tool status |
| `/api/tasks` | POST | Create task |
| `/api/chat` | POST | Chat with agent |
| `/ws/stream` | WS | WebSocket real-time updates |

---

## Build Commands

### Frontend
```powershell
cd frontend

npm run dev          # Development (http://localhost:5173)
npm run build        # Production build
npm run preview      # Preview production build
npm run test        # Run tests
npm run test:ui      # Run tests with UI
```

### Backend
```powershell
# API Server
python -m AI_support.app.api_server

# Review UI (alternative)
python -m AI_support.app.embedded_agent review-ui --port 8766
```

---

## Knowledge Layer (Call Graph)

### Call Graph Cache

The agent uses persistent caching to avoid rebuilding the call graph on every run:

```powershell
# Cache location (auto-created on first run)
main/callgraph_cache.json

# First run: builds from source (~2 min), then saves cache
# Subsequent runs: loads from cache (~0.2s)
```

### Knowledge Modules

| Module | File | Description |
|--------|------|-------------|
| Call Graph | `knowledge/call_graph_parallel.py` | Function calls, callers/callees relationships |
| Symbol Index | `knowledge/symbol_index.py` | Global symbols, types, defines |
| Semantic Search | `knowledge/semantic_search.py` | Keyword-based code search |
| Architecture Map | `knowledge/architecture_map.py` | File structure, components |

### CLI Commands

```powershell
# Build call graph manually
python -m AI_support.knowledge.call_graph_parallel main/software

# Query call graph
python -m AI_support.app.embedded_agent analyze "How is UART configured?"

# Summary report
python -m AI_support.app.embedded_agent summary
```

---

## CLI Commands

### PDF Knowledge Base
```powershell
# Index PDF
python -m AI_support.app.embedded_agent pdf-index --kb-project stm32_rm --pdf path\to\RM.pdf

# Validate KB
python -m AI_support.app.embedded_agent pdf-validate --kb-project stm32_rm
```

### AI KiCad Agent
```powershell
# Build KB
python -m AI_support.app.embedded_agent aikicad-kb-build --pdf path\to\datasheet.pdf --project-id demo

# Generate Firmware
python -m AI_support.app.embedded_agent aikicad-firmware-generate --file-hash <sha256> --requirement "Use I2C" --target-platform STM32 --language C

# Run Full Pipeline
python -m AI_support.app.embedded_agent aikicad-pipeline-run --pdf path\to\pdf.pdf --project-id demo --requirement "I2C sensor" --hardware-requirement "simple board" --target-platform STM32 --language C

# Autonomy Mode
python -m AI_support.app.embedded_agent autonomy-run --pdf path\to\pdf.pdf --project-id demo --requirement "I2C sensor" --target-platform STM32 --language C
```

### Memory & Learning
```powershell
# View memory
python -m AI_support.app.embedded_agent memory

# Review proposals
python -m AI_support.app.embedded_agent memory-review

# Approve proposal
python -m AI_support.app.embedded_agent memory-approve <proposal_id> --reviewer name --reason "approved"
```

---

## Folder Map

| Path | Responsibility |
| --- | --- |
| `agent/` | Think/Act/Observe loop: planner, executor, core loop. |
| `app/` | CLI, high-level embedded-agent facade, and dependency wiring. |
| `benchmarking/` | Smoke tests and benchmark cases for agent quality. |
| `config/` | Prompt constants, chapter config, and output policy. |
| `domains/` | AI KiCad Agent production domains: knowledge, firmware, EDA, cross-validation. |
| `frontend/` | React + Vite Web UI (Dashboard, Path Finder, KB Builder, Agent Chat) |
| `ide/` | Embedded IDE tools: reference manual, debug assistant, memory map, interrupts, registers |
| `knowledge/` | Code analysis: call graph, symbol index, semantic search, architecture map |
| `llm/` | Ollama/local LLM client abstraction. |
| `memory/` | Persistent lessons and feedback store. |
| `models/` | Dataclasses shared across agent modules. |
| `multi_agent/` | Multi-agent prototypes: BuildAgent, FlashAgent, DevOpsAgent, Orchestrator. |
| `parsing/` | LLM response parsing and output sanitization. |
| `reporting/` | Decision trace and report writers. |
| `retrieval/` | RAG ingestion, chunking, vector search, page-aware retrieval. |
| `services/` | Reviewer, document workers, runtime diagnostics, evidence, experience, and reporting services. |
| `tests/` | Regression, smoke, policy, and PDF-agent tests. |
| `tools/` | Build, flash, shell, and filesystem helper tools. |
| `events/` | Event-driven runtime with emitter, handlers, middleware |
| `orchestration/` | Workflow engine, task queue, state machine, retry |
| `ide/` | Embedded IDE tools: reference manual, debug assistant, memory map, interrupts, registers |
| `health/` | Health monitoring and checks |
| `healing/` | Self-healing runtime recovery |
| `metrics/` | Metrics collection |
| `distributed/` | Multi-agent: registry, load balancer, consensus, Redis event bus |
| `runtime/` | Runtime kernel: controller, journal, DLQ, replayer |
| `hardware/` | HIL: UART monitor, CAN analyzer, HIL agent |
| `observability/` | Structured logging, Prometheus metrics, config manager |
| `chaos/` | Chaos engineering: experiments, failure injection |

---

## Architecture Overview

```
+-------------------------------------------------------------+
|                     Web UI (Frontend)                        |
|  React + Vite + TailwindCSS + Zustand                      |
|  Dashboard | Path Finder | KB Builder | Agent Chat           |
+----------------------------+--------------------------------+
|                      HTTP/WebSocket                          |
+----------------------------+--------------------------------+
|                  API Server (FastAPI)                       |
|  REST Endpoints | WebSocket | Chat API                      |
+----------------------------+--------------------------------+
|                                                                  |
|        +-------------+-------------+             |
|        |             |             |             |
|   +---------+  +----------+  +-----------+  +-----------+
|   |Events/  |  |Orchestrat|  |Introspect |  |  Health   |
|   |Handlers |  |ion/      |  |ion/       |  |  Monitor  |
|   |Middleware| |Workflows |  |Anomalies  |  |           |
|   +---------+  +----------+  +-----------+  +-----------+
|   +---------+  +----------+  +-----------+  +-----------+
|   |Distributed|  | Runtime  |  |Hardware/ |  |Observabil|
|   |Registry, |  |Controller|  |HIL Agent |  |ity/Layout|
|   |LoadBalanc|  |Journal,  |  |UART,CAN  |  |Metrics,  |
|   |Consensus |  |DLQ,Replay|  |           |  |Logging   |
|   +---------+  +----------+  +-----------+  +-----------+
```

---

## Runtime Data

| Path | Meaning |
| --- | --- |
| `memory/` | Learned rules, decision traces, user feedback (ChromaDB vector store). |
| `ai_generated/` | Draft generated firmware/code outputs. |
| `data/kb/` | AI KiCad Agent Approved KB cache keyed by SHA256 PDF hash. |
| `outputs/` | Project-scoped PDF knowledge bases. |
| `rag_index/` | Cached RAG chunks, vectors, and register schema. |
| `retrieval_reports/` | Debug reports for retrieval queries. |
| `main/callgraph_cache.json` | Call graph cache: function definitions + callers/callees (~5MB, 9155 functions) |

These folders are runtime state. They are useful for debugging, but they should
not be confused with source modules.

## Contract Schemas

AI KiCad Agent outputs are guarded by JSON Schema contract files:

| Schema | Purpose |
| --- | --- |
| `domains/knowledge/schemas/approved_kb.schema.json` | Approved KB contract. |
| `domains/firmware/schemas/firmware_output.schema.json` | Firmware output and pin mapping contract. |
| `domains/eda/kicad/schemas/kicad_output.schema.json` | KiCad schematic/BOM/connection output contract. |
| `domains/validation/schemas/cross_validation.schema.json` | Cross-validation result contract. |

Validators run schema checks first, then run domain-specific safety checks.

Agent 1 extracts technical evidence from both text and table-like PDF output:
pin tables, operating voltage ranges, package/footprint/pitch evidence, and
register references. Every extracted technical field must keep citations back to
the source PDF page/table.

The firmware generator is schema-first: it writes `firmware_output.json` and
`firmware_validation.json` before any real source-code generator is allowed to
run. It only uses `approved_kb.json`.

Firmware source generation is a second gate: it only reads validated
`firmware_output.json`, writes C/C++/MicroPython files, then runs a syntax check
with `arm-none-eabi-gcc`, `gcc`, `clang`, or Python when available. Missing
compiler tools report `tool_missing`, not pass.

The KiCad generator is also schema-first: it writes `kicad_output.json` and
`kicad_validation.json` before real `.kicad_sch` or `.kicad_pcb` files are
trusted as final outputs. It only uses `approved_kb.json` plus validated
`firmware_output.json`.

KiCad symbol/footprint binding is explicit. The resolver uses Approved KB
package/land-pattern evidence and does not guess missing component footprints.
KiCad ERC/DRC depends on `kicad-cli`. `aikicad-tool-status` reports whether the
local KiCad and firmware compiler tools are available. Full `aikicad-pipeline-run`
is fail-safe: if ERC/DRC is enabled and `kicad-cli` is missing or violations are
reported, the pipeline blocks at `erc_drc`. Use `--skip-erc-drc` only for
development runs where final approval is not hardware-production ready.

`aikicad-pipeline-run` writes stage reports under
`outputs/projects/<project_id>/reports`. Human review overrides are
append-only records in `data/review/human_overrides.jsonl`.

`autonomy-run` adds a safe deterministic loop on top of the pipeline. It records
plans, observations, decisions, retry attempts, and fix proposals under
`outputs/projects/<project_id>/autonomy/<run_id>`. It can retry
fixable schema/source failures, but safety-critical missing information,
conflicts, and tool/input failures stop with a fix proposal instead of
continuing.

## Root Modules

No Python implementation file should live directly at root. The
agent entrypoint and facade live in `app/embedded_agent.py` under `src/`.

Before moving another module, update imports and run the full test suite.

---

## Testing

```powershell
# Run all tests
python -m pytest tests -q

# Run specific test module
python -m pytest tests/test_chaos.py -v
python -m pytest tests/test_redis_bus.py -v
python -m pytest tests/test_flash_tools.py -v
python -m pytest tests/test_observability.py -v
```

---

## Troubleshooting

### Frontend

**Port already in use:**
```powershell
# Find and kill process using port 5173
netstat -ano | findstr :5173
taskkill /PID <pid> /F
```

**Missing dependencies:**
```powershell
cd frontend
rm -rf node_modules
npm install
```

### Backend

**Module not found:**
```powershell
# Make sure you're in the project root
cd C:\Users\thang\Desktop\Agentic-AI
python -m AI_support.app.api_server
```

**Ollama not responding:**
```powershell
# Check Ollama status
ollama list
ollama serve
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [INDEX](docs/INDEX.md) | **Main index** - All documentation links |
| [AI_SUPPORT_DOCUMENTATION](docs/AI_SUPPORT_DOCUMENTATION.md) | Full documentation |
| [CURRENT_SYSTEM_AUDIT](docs/CURRENT_SYSTEM_AUDIT.md) | System status & metrics |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | System architecture |
| [ARCHITECTURE_RUNTIME](docs/ARCHITECTURE_RUNTIME.md) | Runtime kernel details |
| [EVENT_SPEC](docs/EVENT_SPEC.md) | Event system specification |
| [WORKFLOW_SPEC](docs/WORKFLOW_SPEC.md) | Workflow specification |
| [HIL_SPEC](docs/HIL_SPEC.md) | Hardware-in-the-Loop spec |
| [ROADMAP](docs/ROADMAP.md) | Development roadmap |
| [WEB_UI_GUIDE](docs/WEB_UI_GUIDE.md) | Web UI usage guide |
| [STRUCTURE](docs/STRUCTURE.md) | Code structure guide |

---

## Support

For issues, check:
1. `logs/` - Server logs (from running app)
2. `memory/` - Agent memory traces
3. Run `smoke` command for diagnostics
