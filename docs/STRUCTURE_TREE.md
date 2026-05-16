# Project Structure Tree

Root-level files and directories:

```
src/                                       # Source code package (AI_support)
pyproject.toml
README.md
LICENSE
.gitignore
.env
py.typed
.github/
.vscode/
frontend/
tests/
docs/
benchmarks/
loadtests/
examples/
scripts/
configs/
deploy/
```

---

## `src/` — Source Code Package

Source code under `src/` is the `AI_support` Python package.

```
src/
├── core/                                      # Runtime kernel
│   │
│   ├── agent/
│   │   ├── mock_agent.py
│   │   ├── reasoning_loop.py
│   │   ├── reflection.py
│   │   ├── state.py
│   │   │
│   │   ├── prompts/
│   │   │   ├── system/
│   │   │   ├── templates/
│   │   │   ├── versions/
│   │   │   └── experiments/
│   │   │
│   │   ├── memory/
│   │   │   ├── session_memory.py
│   │   │   ├── working_memory.py
│   │   │   ├── episodic_memory.py
│   │   │   └── long_term_memory.py
│   │   │
│   │   ├── middleware/
│   │   │   ├── base.py
│   │   │   ├── logging.py
│   │   │   ├── metrics.py
│   │   │   ├── tracing.py
│   │   │   ├── validation.py
│   │   │   └── rate_limit.py
│   │   │
│   │   └── metrics/
│   │       ├── counters.py
│   │       ├── latency.py
│   │       ├── token_usage.py
│   │       └── tracing.py
│   │
│   ├── runtime/
│   │   ├── runtime_manager.py
│   │   ├── dispatcher.py
│   │   ├── scheduler.py
│   │   ├── retry_policy.py
│   │   ├── admission_control.py
│   │   ├── cancellation.py
│   │   ├── dead_letter_queue.py
│   │   └── idempotency.py
│   │
│   ├── execution/
│   │   ├── executor.py
│   │   ├── execution_graph.py
│   │   ├── task_queue.py
│   │   ├── worker.py
│   │   ├── worker_pool.py
│   │   └── code_executor.py
│   │
│   ├── workspace/
│   │   ├── workspace_manager.py
│   │   ├── workspace_context.py
│   │   ├── multi_root.py
│   │   ├── file_watcher.py
│   │   └── ownership.py
│   │
│   ├── session/
│   │   ├── session_manager.py
│   │   ├── session_state.py
│   │   ├── lifecycle.py
│   │   └── session_store.py
│   │
│   ├── checkpoint/
│   │   ├── checkpoint_manager.py
│   │   ├── replay.py
│   │   ├── rollback.py
│   │   └── snapshot.py
│   │
│   ├── versioning/
│   │   ├── schema_version.py
│   │   ├── migration_manager.py
│   │   └── transformers/
│   │
│   ├── background_jobs/
│   │   ├── scheduler.py
│   │   ├── cleanup.py
│   │   ├── telemetry.py
│   │   ├── maintenance.py
│   │   └── heartbeat.py
│   │
│   ├── health/
│   │   ├── runtime_health.py
│   │   ├── readiness.py
│   │   └── liveness.py
│   │
│   └── ports/                                 # renamed from interfaces
│       ├── event_bus.py
│       ├── llm_provider.py
│       ├── tool_provider.py
│       ├── vector_store.py
│       ├── cache_provider.py
│       └── health_check.py
│
├── domain/                                    # Pure business/domain logic
│   │
│   ├── hardware/
│   │   ├── chips.py
│   │   ├── peripherals.py
│   │   ├── registers.py
│   │   ├── interrupts.py
│   │   ├── clocks.py
│   │   ├── pinmux.py
│   │   └── svd_parser.py
│   │
│   ├── firmware/
│   │   ├── linker.py
│   │   ├── memory_map.py
│   │   ├── bootloader.py
│   │   └── ota.py
│   │
│   ├── knowledge/
│   │   ├── kb.py
│   │   ├── citation.py
│   │   ├── parser.py
│   │   ├── embeddings.py
│   │   └── chunking.py
│   │
│   ├── events/
│   │   ├── runtime_events.py
│   │   ├── hardware_events.py
│   │   ├── firmware_events.py
│   │   ├── workflow_events.py
│   │   ├── codegen_events.py
│   │   └── session_events.py
│   │
│   └── models/
│       ├── task.py
│       ├── artifact.py
│       ├── message.py
│       ├── event.py
│       └── plan.py
│
├── application/                               # Use cases & orchestration
│   │
│   ├── workflows/
│   │   ├── coding/
│   │   ├── debugging/
│   │   ├── planning/
│   │   ├── hardware/
│   │   └── refactor/
│   │
│   ├── orchestration/
│   │   ├── workflow_engine.py
│   │   ├── routing.py
│   │   ├── coordination.py
│   │   ├── recovery.py
│   │
│   │   ├── supervisor/
│   │   │   ├── supervisor.py
│   │   │   ├── autoscaler.py
│   │   │   ├── escalation.py
│   │   │   └── monitoring.py
│   │   │
│   │   └── agents/
│   │       ├── planner_agent.py
│   │       ├── executor_agent.py
│   │       ├── reviewer_agent.py
│   │       └── verifier_agent.py
│   │
│   └── planner/
│       ├── task_planner.py
│       ├── dependency_graph.py
│       └── decomposition.py
│
├── infrastructure/                            # External systems & adapters
│   │
│   ├── gateway/
│   │   ├── base.py
│   │   ├── auth.py
│   │   ├── retry.py
│   │   ├── tracing.py
│   │   ├── rate_limit.py
│   │   └── telemetry.py
│   │
│   ├── sandbox/
│   │   ├── docker.py
│   │   ├── gvisor.py
│   │   ├── seccomp.py
│   │   ├── process_isolation.py
│   │   └── factory.py
│   │
│   ├── llm/
│   │   ├── gateway.py
│   │   ├── routing.py
│   │   ├── tokenizer.py
│   │   ├── streaming.py
│   │   │
│   │   └── providers/
│   │       ├── openai/
│   │       ├── anthropic/
│   │       ├── ollama/
│   │       ├── groq/
│   │       └── openrouter/
│   │
│   ├── resilience/
│   │   ├── circuit_breaker/
│   │   ├── retry/
│   │   ├── timeout/
│   │   └── fallback/
│   │
│   ├── observability/
│   │   ├── logging/
│   │   ├── metrics/
│   │   ├── tracing/
│   │   ├── profiling/
│   │   └── exporters/
│   │
│   ├── cache/
│   │   ├── in_memory/
│   │   ├── redis/
│   │   ├── semantic/
│   │   ├── embeddings/
│   │   └── disk/
│   │
│   ├── health/
│   │   ├── registry.py
│   │   ├── checks/
│   │   └── reporting/
│   │
│   ├── message_bus/
│   │   ├── in_memory/
│   │   ├── redis/
│   │   ├── nats/
│   │   └── kafka/
│   │
│   ├── plugin_loader/
│   │   ├── discovery.py
│   │   ├── registry.py
│   │   ├── permissions.py
│   │   └── isolation.py
│   │
│   ├── mcp/
│   │   ├── client/
│   │   ├── server/
│   │   └── transports/
│   │
│   ├── pty/
│   │   ├── pty_manager.py
│   │   ├── pty_session.py
│   │   ├── streaming.py
│   │   └── cleanup.py
│   │
│   ├── filesystem/
│   │   ├── reader.py
│   │   ├── writer.py
│   │   ├── patcher.py
│   │   ├── workspace.py
│   │   └── sandbox.py
│   │
│   ├── indexing/
│   │   ├── tree_sitter/
│   │   ├── symbol_graph/
│   │   ├── dependency_graph/
│   │   ├── ast_graph/
│   │   └── semantic_search/
│   │
│   ├── vector_db/
│   │   ├── abstraction.py
│   │   ├── lancedb/
│   │   └── chromadb/
│   │
│   ├── tool_registry/                         # unified tool system
│   │   ├── registry.py
│   │   ├── builtin.py
│   │   ├── mcp.py
│   │   ├── resolver.py
│   │   ├── namespaces.py
│   │   ├── priority.py
│   │   └── capabilities.py
│   │
│   ├── builtin_tools/
│   │   ├── filesystem/
│   │   ├── terminal/
│   │   ├── git/
│   │   └── hardware/
│   │
│   ├── persistence/
│   │   ├── sqlite/
│   │   ├── postgres/
│   │   ├── checkpoints/
│   │   ├── conversations/
│   │   └── migrations/
│   │
│   └── workspace_index/
│       ├── indexing_service.py
│       ├── invalidation.py
│       ├── ownership.py
│       └── synchronization.py
│
├── interfaces/                               # User-facing interfaces
│   │
│   ├── server/
│   │   ├── api/
│   │   ├── websocket/
│   │   ├── middleware/
│   │   ├── auth/
│   │   ├── health.py
│   │   └── main.py
│   │
│   ├── cli/
│   │   ├── commands/
│   │   ├── interactive/
│   │   └── main.py
│   │
│   ├── tui/
│   │   ├── screens/
│   │   ├── widgets/
│   │   ├── state/
│   │   └── app.py
│   │
│   └── ide/
│       └── bridge/
│           ├── websocket_bridge.py
│           └── stdio_bridge.py
│
├── schemas/
│   ├── api/
│   ├── websocket/
│   ├── dto/
│   ├── validation/
│   └── idl/
│       ├── protobuf/
│       └── grpc/
│
└── shared/
    ├── config/
    ├── constants/
    ├── enums/
    ├── exceptions/
    ├── protocols/
    ├── validators/
    └── utils/
```

---

## Root-Level Directories

### `frontend/`

React + Vite Web UI.

```
frontend/
├── src/
│   ├── App.tsx
│   ├── main.tsx
│   ├── pages/
│   ├── components/
│   └── hooks/
├── package.json
└── vite.config.ts
```

### `tests/`

pytest test suite.

```
tests/
├── conftest.py
├── unit/
│   ├── core/
│   ├── domain/
│   ├── application/
│   ├── infrastructure/
│   └── interfaces/
├── integration/
│   ├── llm/
│   ├── mcp/
│   ├── websocket/
│   ├── filesystem/
│   ├── pty/
│   └── workspace/
├── e2e/
├── performance/
├── fixtures/
└── mocks/
```

### `docs/`

Project documentation.

```
docs/
├── architecture/
├── runtime/
├── workflows/
├── deployment/
├── api/
├── adr/
├── phase1a.md
└── STRUCTURE_TREE.md
```

### `examples/`

Usage examples.

```
examples/
├── basic_chat.py
├── custom_tool.py
├── workspace_agent.py
├── hardware_analysis.py
├── multi_agent_demo.py
└── server_demo.py
```

### `scripts/`

Build and utility scripts.

```
scripts/
├── lint.sh
├── format.sh
├── typecheck.sh
├── benchmark.sh
├── release.sh
└── migrations/
```

### `configs/`

Configuration files.

```
configs/
├── runtime/
├── llm/
├── security/
├── observability/
├── policies/
└── environments/
```

### `deploy/`

Deployment configurations.

```
deploy/
├── docker/
├── compose/
├── kubernetes/
└── helm/
```

### `benchmarks/`

Performance benchmarks.

```
benchmarks/
├── runtime/
├── latency/
├── throughput/
└── token_streaming/
```

### `loadtests/`

Load test configurations.

```
loadtests/
├── websocket/
├── api/
├── pty/
└── streaming/
```
