# Architecture - AI_SUPPORT

**Date:** 2026-05-23
**Phase:** 1a.5
**Product:** Embedded CI/HIL Intelligence Platform

---

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        AI_SUPPORT Platform                       │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  CLI (TUI)  │  │  WebSocket  │  │    REST     │  Interfaces  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
│         │                │                │                     │
│  ┌──────┴────────────────┴────────────────┴──────┐             │
│  │              API Gateway / Router              │  Gateway   │
│  └──────────────────────┬────────────────────────┘             │
│                         │                                        │
│  ┌──────────────────────┴────────────────────────┐             │
│  │              Agent Runtime Kernel               │  Core       │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐       │             │
│  │  │ Debug    │ │ Test     │ │ Patch    │       │  Agents     │
│  │  │ Agent    │ │ Agent    │ │ Agent    │       │             │
│  │  └──────────┘ └──────────┘ └──────────┘       │             │
│  └──────────────────────┬────────────────────────┘             │
│                         │                                        │
│  ┌──────────┐ ┌──────────┴──────────┐ ┌──────────┐             │
│  │ Memory   │ │    Tool Registry    │ │  Cost    │  Services    │
│  │ Service  │ │                     │ │Governance│             │
│  └──────────┘ └─────────────────────┘ └──────────┘             │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │  LLM     │ │ Hardware │ │ Firmware │ │  Event   │  Ports     │
│  │ Gateway  │ │  Debug   │ │  Loader  │ │   Bus    │             │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘           │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                       │
│  │ PostgreSQL│ │  Redis   │ │  File    │  Storage              │
│  └──────────┘ └──────────┘ └──────────┘                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Architecture Principles

1. **Monolithic for MVP** — Single deployment, in-memory for Phase 1-2
2. **Port/Adapter Pattern** — Decouple core from infrastructure
3. **Event-Driven** — Async communication via event bus
4. **AI-Augmented** — LLM enhances, not replaces, engineering judgment

---

## Core Components

### 1. Interfaces Layer

| Component | Purpose | Tech |
|-----------|---------|------|
| CLI/TUI | Terminal UI | Textual |
| WebSocket | Real-time streaming | FastAPI |
| REST API | CRUD operations | FastAPI |

### 2. Gateway Layer

- **API Gateway** — Routing, auth, rate limiting
- **Session Manager** — WebSocket connection lifecycle
- **Middleware** — Logging, metrics, tracing

### 3. Agent Runtime Kernel

| Component | Purpose |
|-----------|---------|
| Agent Lifecycle | Spawn, suspend, resume, cancel |
| Agent Sandbox | Tool permissions, resource quota |
| Deterministic FSM | Replayable execution |
| Agent Scheduler | Priority, fairness, backpressure |
| Failure Isolation | Crash isolation, retry boundary |

### 4. Agent Types

| Agent | Purpose |
|-------|---------|
| Debug Agent | Firmware analysis, root cause |
| Test Agent | Test generation, execution |
| Patch Agent | Suggest fixes, validate |
| Review Agent | Code review, quality gate |

### 5. Services Layer

| Service | Purpose |
|---------|---------|
| Memory Service | Working + long-term memory |
| Tool Registry | MCP tools, schema, versioning |
| Cost Governance | Token budget, adaptive routing |

### 6. Ports (Interfaces to External)

| Port | Purpose |
|------|---------|
| LLM Gateway | Ollama, OpenAI, Anthropic, Gemini |
| Hardware Debug | J-Link, ST-Link, CMSIS-DAP |
| Firmware Loader | ELF parsing, symbol index |
| Event Bus | Async messaging |

---

## Data Flow

```
User Input → CLI/WS → Gateway → Agent Runtime → Tool Execution
                                              ↓
                                        Hardware Probe
                                              ↓
                                        Response → Gateway → User
```

---

## Technology Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| API | FastAPI | Async, OpenAPI, WebSocket |
| Agents | LangGraph | Stateful, graph-based |
| LLM | Ollama + OpenAI | Local + cloud |
| DB | PostgreSQL | ACID, JSON, mature |
| Cache | Redis | Persistence, pub/sub |
| Hardware | pylink2, pyocd | ARM debug |
| Logging | structlog | Structured |

---

## Migration Path

```
Phase 1-2: Monolithic + in-memory
    ↓
Phase 4: Add PostgreSQL for persistence
    ↓
Phase 6: Extract services if needed
    ↓
Phase 11+: Multi-node, horizontal scaling
```

---

## Architecture Decision Records

See `docs/adr/` for detailed decisions:

- [ADR-001: Architecture Style](adr/001_architecture_style.md)
- [ADR-002: Database Choice](adr/002_database.md)
- [ADR-003: Event Store](adr/003_event_store.md)
- [ADR-004: LLM Provider](adr/004_llm_provider.md)

---

## Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| Latency | <100ms for UI, <5s for analysis |
| Availability | 99.9% |
| Sessions | ≤100 concurrent |
| Memory | ≤500MB per node |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| LLM hallucination | Deterministic validation, hardware constraints |
| Hardware variability | Abstraction layer, plugin system |
| Scale bottleneck | Design for stateless, add caching later |
