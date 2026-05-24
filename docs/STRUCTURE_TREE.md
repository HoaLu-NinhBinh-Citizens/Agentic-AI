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
│   │   ├── memory/
│   │   │   ├── episodic_memory/
│   │   │   ├── long_term_memory/
│   │   │   ├── session_memory/
│   │   │   └── working_memory/
│   │   │
│   │   ├── middleware/
│   │   │   ├── tracing.py
│   │   │   ├── validation.py
│   │   │   └── metrics.py
│   │   │
│   │   ├── metrics/
│   │   │   ├── counters.py
│   │   │   ├── latency.py
│   │   │   ├── token_usage.py
│   │   │   └── tracing.py
│   │   │
│   │   └── prompts/
│   │       ├── system/
│   │       ├── templates/
│   │       ├── versions/
│   │       └── experiments/
│   │
│   ├── multi_agent/                          # Phase 5D-5F Multi-Agent System
│   │   ├── __init__.py
│   │   ├── agent.py
│   │   ├── core.py
│   │   │
│   │   └── coordination/                     # Coordination Layer
│   │       ├── __init__.py
│   │       ├── types.py                  # Shared types
│   │       ├── config.py                 # Configuration
│   │       ├── coordinator.py              # Main facade
│   │       ├── governance.py              # Agent governance
│   │       ├── health.py                 # Health monitoring
│   │       ├── leader_election.py        # HA leader election
│   │       ├── rate_limiter.py           # Rate limiting
│   │       ├── quota.py                  # Resource quotas
│   │       ├── circuit_breaker.py        # Failure isolation
│   │       ├── backpressure.py            # Load protection
│   │       ├── batch_idempotency.py      # Idempotent processing
│   │       ├── message_ordering.py       # Causal ordering
│   │       ├── schema_evolution.py        # API versioning
│   │       ├── dead_letter_alert.py      # DLQ alerting
│   │       ├── tenant_isolation.py       # Multi-tenancy
│   │       ├── deterministic_scheduler.py # Deterministic execution
│   │       │
│   │       └── DEPRECATION_NOTICE.py    # Module cleanup plan
│   │
│   │       # DEPRECATED - Will be removed in cleanup:
│   │       # - byzantine_protection.py
│   │       # - saga_compensation.py
│   │       # - worm_archive.py
│   │       # - safety_formal.py
│   │       # - chaos_secrets.py
│   │       # - cdc_consistency.py
│   │       # - injection_explainer.py
│   │       # - enhanced_*.py modules
│   │
│   ├── runtime/
│   │   ├── __init__.py           # Phase 1B RuntimeManager + lazy load Phase 15
│   │   ├── runtime_manager.py
│   │   ├── dispatcher.py
│   │   ├── controller.py
│   │   ├── kernel.py
│   │   ├── replayer.py
│   │   ├── backpressure.py
│   │   │
│   │   ├── admission_control/
│   │   ├── cancellation/
│   │   ├── dead_letter_queue/
│   │   ├── enterprise/                      # Enterprise features
│   │   │   ├── compensation_saga.py
│   │   │   ├── heartbeat_lease.py
│   │   │   ├── chaos_tests.py
│   │   │   ├── deterministic_values.py
│   │   │   ├── lifecycle_retention.py
│   │   │   ├── multi_tenant.py
│   │   │   ├── planner_versioning.py
│   │   │   ├── poison_defense.py
│   │   │   ├── sticky_execution.py
│   │   │   └── resource_governor.py
│   │   ├── idempotency/
│   │   ├── retry_policy/
│   │   ├── scheduler/
│   │   └── workflow/
│   │       ├── activity_executor.py
│   │       ├── cancellation.py
│   │       ├── migration.py
│   │       ├── replay_optimizer.py
│   │       ├── replay_verifier.py
│   │       ├── signal_manager.py
│   │       ├── strong_query.py
│   │       ├── tool_isolation.py
│   │       └── workflow_context.py
│   │
│   ├── execution/
│   │   ├── executor.py
│   │   ├── execution_graph/
│   │   ├── task_queue/
│   │   ├── worker/
│   │   ├── worker_pool/
│   │   └── code_executor/
│   │
│   ├── workspace/
│   │   ├── workspace_manager.py
│   │   ├── workspace_context.py
│   │   ├── multi_root/
│   │   ├── file_watcher/
│   │   └── ownership/
│   │
│   ├── session/
│   │   ├── session_manager.py      # Phase 1A in-memory manager
│   │   ├── session_state.py
│   │   ├── session_store.py
│   │   ├── lifecycle.py
│   │   └── persistent_manager.py   # Phase 1B SQLite-backed manager
│   │
│   ├── checkpoint/
│   │   ├── checkpoint_manager.py
│   │   ├── checkpoint_manager/
│   │   ├── replay/
│   │   ├── rollback/
│   │   └── snapshot/
│   │
│   ├── versioning/
│   │   ├── schema_version.py
│   │   ├── migration_manager.py
│   │   └── transformers/
│   │
│   ├── background_jobs/
│   │   └── scheduler.py
│   │
│   ├── health/
│   │   ├── runtime_health/
│   │   ├── readiness/
│   │   └── liveness/
│   │
│   ├── memory/
│   │   ├── semantic_memory.py
│   │   ├── store.py
│   │   ├── chunker.py
│   │   ├── deduplication.py
│   │   ├── leak_detector.py
│   │   ├── chroma_db/
│   │   ├── compression/
│   │   │   ├── __init__.py
│   │   │   ├── types.py
│   │   │   ├── decompression.py
│   │   │   ├── migration.py
│   │   │   └── strategies/
│   │   └── decision_traces/
│   │
│   ├── events/
│   │   └── event.py
│   │
│   ├── parsing/
│   │   └── output_sanitizer.py
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   ├── chapter_config.py
│   │   └── output_policy.py
│   │
│   ├── scheduler/
│   │   └── __init__.py
│   │
│   ├── orchestration/
│   │   └── langgraph_workflow.py
│   │
│   ├── middleware/
│   │   └── (middleware modules)
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
│   ├── hardware/                              # Phase 6 - Embedded Target
│   │   ├── chips.py
│   │   ├── peripherals.py
│   │   ├── registers.py
│   │   ├── interrupts.py
│   │   ├── clocks.py
│   │   ├── pinmux.py
│   │   ├── svd_parser.py
│   │   ├── embedded_target.py           # Core target models
│   │   ├── debug_probe.py               # Probe interfaces (JLink, STLink, CMSIS-DAP)
│   │   ├── target_registry.py            # YAML config, auto-detect
│   │   ├── gdb_client.py                # GDB RSP client
│   │   └── serial_monitor.py             # UART monitor
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
│       ├── plan.py
│       └── tool_call.py
│
├── domains/                                   # Extended domain modules
│   │
│   ├── hardware_engine/                       # Hardware Engine v2
│   │   ├── core/
│   │   │   ├── peripheral_graph.py
│   │   │   └── register_schema.py
│   │   ├── engine/
│   │   │   ├── allocator.py
│   │   │   └── pinmux_engine.py
│   │   ├── parser/
│   │   │   └── svd_parser.py
│   │   ├── codegen/
│   │   ├── validator/
│   │   └── integration/
│   │       └── adapter.py
│   │
│   ├── firmware/
│   │   └── (firmware modules)
│   │
│   ├── knowledge/
│   │   └── ocr/
│   │
│   ├── models/
│   │   └── (domain models)
│   │
│   ├── runtime/
│   │   └── journal.py
│   │
│   ├── autonomy/
│   │   ├── fix_mode/
│   │   ├── memory/
│   │   ├── planner/
│   │   └── state/
│   │
│   ├── safety/
│   │
│   ├── review/
│   │
│   ├── schema_validator/
│   │
│   ├── validation/
│   │
│   └── eda/
│       └── kicad.py
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
│   │   ├── routing/
│   │   │
│   │   ├── supervisor/
│   │   │   ├── autoscaler/
│   │   │   ├── escalation/
│   │   │   ├── monitoring/
│   │   │   └── supervisor/
│   │   │
│   │   ├── agents/
│   │   │   ├── executor_agent/
│   │   │   ├── planner_agent/
│   │   │   ├── reviewer_agent/
│   │   │   └── verifier_agent/
│   │   │
│   │   ├── tool_execution/
│   │   │   └── middleware.py
│   │   │
│   │   └── __init__.py
│   │
│   ├── planner/
│   │   ├── task_planner.py
│   │   ├── dependency_graph/
│   │   ├── decomposition/
│   │   ├── semantic_retriever.py
│   │   ├── expansion_guard.py
│   │   ├── schema_validator.py
│   │   └── metrics.py
│   │
│   ├── services/
│   │   └── runtime_support.py
│   │
│   ├── llm/
│   │   └── (LLM application services)
│   │
│   └── api/
│       └── app/
│           ├── api_endpoints.py
│           ├── api_websocket.py
│           ├── agent_logging.py
│           ├── dashboard_api.py
│           ├── hardware_cli.py
│           ├── review_ui.py
│           ├── dashboard/
│           └── templates/
│
├── infrastructure/                            # External systems & adapters
│   │
│   ├── gateway/
│   │   ├── base.py
│   │   ├── auth/
│   │   ├── retry/
│   │   ├── tracing/
│   │   ├── rate_limit/
│   │   └── telemetry/
│   │
│   ├── sandbox/
│   │   ├── docker/
│   │   ├── gvisor/
│   │   ├── seccomp/
│   │   ├── process_isolation/
│   │   └── factory.py
│   │
│   ├── llm/
│   │   ├── gateway.py
│   │   ├── routing.py
│   │   ├── tokenizer.py
│   │   ├── streaming.py
│   │   ├── structured_output.py
│   │   ├── token_tracker.py
│   │   ├── ollama_provider.py
│   │   ├── groq_provider.py
│   │   ├── ollama.py
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
│   │   │   ├── __init__.py
│   │   │   ├── metrics_server.py
│   │   │   └── prometheus_metrics.py
│   │   ├── tracing/
│   │   ├── profiling/
│   │   ├── exporters/
│   │   └── config_manager.py
│   │
│   ├── cache/
│   │   ├── in_memory/
│   │   ├── redis/
│   │   ├── semantic/
│   │   ├── embeddings/
│   │   ├── disk/
│   │   └── tool/                           # Phase 4B - Tool Cache System
│   │       ├── types.py              # KeyState, CacheResponse, VectorClock
│   │       ├── state_machine.py      # KeyStateMachine (FSM)
│   │       ├── normalizer.py        # StrictNormalizer
│   │       ├── key_generator.py     # KeyGenerator (SHA256)
│   │       ├── semantic_hash.py     # SemanticCacheHasher (W-012)
│   │       ├── single_flight.py     # SingleFlightCoordinator
│   │       ├── swr_engine.py       # SWREngine
│   │       ├── rate_limiter.py      # ToolRateLimiter
│   │       ├── threshold_engine.py   # AdaptiveThresholdEngine
│   │       ├── load_shedding.py     # LoadSheddingController
│   │       ├── lru_store.py        # LRUStore + PinManager
│   │       ├── adaptive_ttl.py     # AdaptiveTTLEngine
│   │       ├── validation.py        # PoisonValidationEngine
│   │       ├── warmup.py           # WarmUpManager
│   │       ├── persistence.py       # PersistentStore
│   │       ├── write_back.py       # WriteBackQueue
│   │       ├── metrics.py          # MetricsEngine
│   │       ├── reconciliation.py    # ReconciliationEngine
│   │       ├── backpressure.py     # BackpressureManager
│   │       ├── fragmentation.py    # FragmentationManager + SlabAllocator
│   │       ├── causality.py        # CausalityTracer + AnomalyDetector
│   │       ├── cluster.py          # ClusterCoordinator + PartitionManager
│   │       └── cache.py           # ToolCache (main facade)
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
│   │   ├── discovery/
│   │   ├── registry/
│   │   ├── permissions/
│   │   └── isolation/
│   │
│   ├── mcp/
│   │   ├── manager.py             # MCPClientManager (Phase 2A)
│   │   ├── config.py             # MCPConfigLoader & MCPServerConfig
│   │   ├── client/
│   │   ├── server/
│   │   └── transports/
│   │
│   ├── pty/
│   │   ├── pty_manager.py
│   │   ├── pty_session/
│   │   ├── streaming/
│   │   └── cleanup/
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
│   ├── retrieval/                          # Phase 5C v12 - Advanced Retrieval Engine
│   │   ├── retrieval_types.py              # Data schemas (Snapshot, Plugin, GoldenSet)
│   │   ├── retrieval_config.py            # Configuration classes
│   │   ├── retrieval_components.py       # Core components (7 enterprise features)
│   │   ├── retrieval_engine.py           # AdvancedRetrievalEngine integration
│   │   ├── retrieval_resilience.py       # Production resilience (8 extended features)
│   │   ├── hybrid.py                    # HybridRetriever
│   │   ├── vector_index.py              # VectorIndex
│   │   ├── chunk_store.py               # ChunkStore
│   │   ├── embedding.py                 # OllamaEmbeddingClient
│   │   ├── query_analyzer.py           # QueryAnalyzer
│   │   ├── search_cache.py             # SearchCache
│   │   ├── evidence_builder.py          # EvidenceBuilder
│   │   ├── ingest.py                   # RetrievalIngestor
│   │   ├── rag_evaluation.py          # RetrievalEvaluator
│   │   ├── chroma_store.py              # ChromaVectorStore
│   │   ├── knowledge_base.py           # ReferenceKnowledgeBase
│   │   ├── manifest.py                 # IndexManifest
│   │   ├── page_aware.py              # PageAwareRetrievalSupport
│   │   ├── context_budget.py          # ContextBudget
│   │   └── pdf_ocr.py                 # PdfTableOCR
│   │
│   ├── tool_registry/                         # unified tool system
│   │   ├── registry.py
│   │   ├── builtin.py
│   │   ├── mcp.py
│   │   ├── resolver.py
│   │   ├── namespaces.py
│   │   ├── priority.py
│   │   ├── capabilities.py
│   │   ├── builtin/
│   │   └── priority/
│   │
│   ├── builtin_tools/
│   │   ├── filesystem/
│   │   ├── terminal/
│   │   ├── git/
│   │   └── hardware/
│   │
│   ├── persistence/
│   │   ├── sqlite/
│   │   │   ├── schema.sql         # Session persistence schema
│   │   │   └── session_store.py   # SQLite session store implementation
│   │   ├── postgres/
│   │   ├── checkpoints/
│   │   ├── conversations/
│   │   └── migrations/
│   │
│   ├── workspace_index/
│   │   ├── indexing_service.py
│   │   ├── invalidation/
│   │   ├── ownership/
│   │   └── synchronization/
│   │
│   ├── embeddings/
│   │   ├── __init__.py
│   │   └── embedding_service.py
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   └── retrieval.py
│   │
│   ├── router/
│   │   ├── __init__.py
│   │   ├── types.py
│   │   ├── execution_engine.py
│   │   ├── observation/
│   │   │   ├── exactly_once.py
│   │   │   └── health_monitor.py
│   │   ├── consistency/
│   │   │   └── read_after_write.py
│   │   ├── fairness/
│   │   └── (other router modules)
│   │
│   ├── hardware/                           # Phase 6 - Hardware debugging
│   │   ├── hil_agent.py
│   │   ├── uart_monitor.py
│   │   ├── probes/                        # Probe implementations
│   │   │   ├── jlink.py                 # SEGGER J-Link
│   │   │   ├── stlink.py                # ST-Link
│   │   │   └── cmsis_dap.py             # CMSIS-DAP
│   │   └── gdb/
│   │       ├── rsp_client.py            # GDB Remote Serial Protocol
│   │       └── mi_parser.py            # GDB/MI output parser
│   │
│   ├── security/
│   │
│   ├── metrics/
│   │   └── (metrics infrastructure)
│   │
│   └── tool_execution/
│       └── (tool execution infrastructure)
│
├── interfaces/                               # User-facing interfaces
│   │
│   ├── server/
│   │   ├── main.py
│   │   ├── health.py
│   │   ├── api/
│   │   ├── websocket/
│   │   ├── middleware/
│   │   └── auth/
│   │
│   ├── cli/
│   │   ├── commands/
│   │   ├── interactive/
│   │   └── main.py
│   │
│   ├── tui/
│   │   ├── app.py
│   │   ├── screens/
│   │   ├── widgets/
│   │   └── state/
│   │
│   ├── ide/
│   │   ├── bridge/
│   │   │   ├── websocket_bridge.py
│   │   │   └── stdio_bridge.py
│   │   ├── peripherals.py
│   │   ├── interrupts.py
│   │   ├── reference_manual.py
│   │   └── __init__.py
│   │
│   └── frontend/
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
├── phase5b_test_suite.py                # Phase 5B core tests (31 tests)
├── unit/
│   ├── test_session_store.py
│   ├── test_rate_limiter.py
│   ├── test_websocket_client.py
│   ├── test_mock_agent.py
│   ├── test_connection_manager.py
│   ├── test_runtime_manager.py
│   ├── test_persistent_session_manager.py
│   ├── test_session_manager.py
│   ├── test_mcp_config.py
│   ├── test_mcp_manager.py
│   ├── test_llm_router.py
│   ├── test_tool_registry.py
│   ├── test_health.py
│   ├── test_validation.py
│   ├── test_metrics.py
│   ├── test_tool_executor.py
│   ├── test_tool_accumulator.py
│   ├── test_state_machine.py
│   ├── test_normalizer.py
│   ├── test_idempotency.py
│   ├── test_cache_types.py
│   ├── test_lru_store.py
│   ├── test_rate_limit_store.py
│   ├── test_middleware.py
│   ├── test_embedding_service.py
│   ├── test_chunker.py
│   ├── test_semantic_memory_error_contract.py
│   ├── test_tool_schema.py
│   ├── test_tool_errors.py
│   ├── test_tool_tracker.py
│   ├── test_score_engine.py
│   ├── test_lifecycle.py
│   ├── test_fairness.py
│   ├── test_execution_engine.py
│   ├── compression/
│   │   ├── test_engine.py
│   │   ├── test_adaptive.py
│   │   ├── test_extractive.py
│   │   ├── test_keyvalue.py
│   │   ├── test_truncation.py
│   │   ├── test_worker.py
│   │   └── test_migration.py
│   ├── phase5b/                         # Phase 5B detailed tests
│   │   ├── conftest.py
│   │   ├── test_condition_evaluator.py
│   │   ├── test_schema_validator.py
│   │   ├── test_exactly_once.py
│   │   ├── test_heartbeat_lease.py
│   │   ├── test_compensation_saga.py
│   │   ├── test_history_compaction.py
│   │   ├── test_deadlock_detector.py
│   │   ├── test_expansion_guard.py
│   │   ├── test_multi_tenant_rbac.py
│   │   ├── test_poison_defense.py
│   │   └── test_event_integrity.py
│   ├── phase5c/                        # Phase 5C (Retrieval Engine) tests
│   │   ├── test_phase5c_components.py  # Core components
│   │   └── test_phase5c_extended.py    # Extended features
│   └── workflow/
│       └── test_workflow_runtime.py
├── integration/
│   ├── test_phase1b_features.py
│   ├── test_mcp_phase2a.py
│   ├── test_session_lifecycle.py
│   ├── test_websocket_chat.py
│   ├── test_phase2b_tool_execution.py
│   ├── test_compression_integration.py
│   ├── test_phase2c_reliability.py
│   ├── phase5b/
│   │   ├── test_enterprise_integration.py
│   │   ├── test_chaos_scenarios.py
│   │   └── test_performance_scale.py
│   └── phase5c/
├── e2e/
├── performance/
├── chaos/
│   └── (chaos engineering tests)
├── mocks/
├── fixtures/
├── architecture/
├── router/                              # Router test suite
│   ├── unit/
│   │   ├── test_exactly_once.py
│   │   ├── test_execution_engine.py
│   │   ├── test_fairness.py
│   │   ├── test_lifecycle.py
│   │   ├── test_score_engine.py
│   │   └── test_properties.py
│   ├── integration/
│   │   └── test_pipeline.py
│   ├── chaos/
│   │   └── test_chaos.py
│   └── concurrency/
│       └── test_concurrency.py
├── phase5d/                            # Phase 5D multi-agent tests
│   ├── test_coordination.py
│   └── test_enhanced_coordination.py
├── phase5e/                            # Phase 5E distributed tests
│   ├── test_distributed_execution.py
│   └── test_extended.py
└── phase5f/                            # Phase 5F reliability tests
    ├── test_reliability_governance.py
    └── test_enhanced_reliability.py
├── phase6/                            # Phase 6 embedded target tests
│   ├── test_embedded_target.py
│   ├── test_debug_probe.py
│   ├── test_target_registry.py
│   ├── test_gdb_client.py
│   └── test_serial_monitor.py
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
├── phase1b.md
├── phase2a.md
├── phase2b.md
├── phase2c.md
├── phase2d.md
├── phase2d.1.md
├── phase3.md
├── phase4a.md
├── phase4a_error_handling.md
├── phase4b_tool_cache.md
├── phase4c_semantic_router.md
├── phase4d_compression.md
├── phase4d1_compression.md
├── phase5a_workflow_runtime.md
├── phase5b_planner_enterprise.md
├── phase5b_v10_enterprise.md
├── phase5d_multi_agent_coordination.md
├── phase5d_v2_enhancements.md
├── phase5e_distributed_execution.md
├── phase5f_reliability_governance.md
├── phase5f_v2_reliability_governance.md
├── phase6_embedded_target.md
├── STRUCTURE_TREE.md
└── (other documentation files)
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
├── mcp/
│   └── servers.yaml           # MCP server configurations (Phase 2A)
├── security/
├── observability/
├── policies/
├── environments/
└── targets/                   # Phase 6 - Target configurations
    ├── stm32f4-discovery.yaml
    ├── esp32-devkit.yaml
    └── riscv-hifive1.yaml
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

---

## Production Readiness Status

> **Status**: Advanced Prototype / Architecture Lab (May 2026)
> **Overall Score**: 5.2/10

### P0 Critical Priorities

| Priority | Task | Impact | Status |
|----------|------|--------|--------|
| P0-A | Deterministic Workflow Kernel | 🔴 Critical | ⬜ Not Done |
| P0-B | End-to-End Flash State Machine | 🔴 Critical | ⬜ Not Done |
| P0-C | Fencing Token Lock Model | 🔴 Critical | ⬜ Not Done |
| P0-D | Signed Artifact Manifest | 🔴 Critical | ⬜ Not Done |
| P0-E | Deterministic Replay Contract | 🔴 Critical | ⬜ Not Done |
| P0-F | HIL Fault Injection Tests | 🟡 High | ⬜ Not Done |

### Current Scorecard

| Subsystem | Score | Notes |
|-----------|-------|-------|
| Architecture | 6.0/10 | Prototype tốt |
| Distributed Systems | 4.0/10 | Prototype |
| Embedded Infrastructure | 5.5/10 | Có tiến bộ |
| AI Architecture | 6.0/10 | Đúng hướng |
| Security | 4.5/10 | Thiếu nhiều |
| Reliability | 5.0/10 | Rủi ro cao |
| Observability | 5.5/10 | Khá tốt |
| Scalability | 4.5/10 | Prototype |

### Modules to FREEZE (Architecture Theater)

> **DO NOT ADD FEATURES** to these modules until P0 priorities are addressed:

```bash
# DEPRECATED - Will be removed in cleanup:
- src/core/multi_agent/coordination/byzantine_*.py
- src/core/multi_agent/coordination/quorum*.py
- src/core/runtime/enterprise/cross_region*.py
- src/infrastructure/router/fairness/*.py
- src/domains/autonomy/planner/* (MERGE into core)
- src/application/llm/* (CONSOLIDATE)
```

### Complexity Bombs (Hidden Risks)

```
⚠️ 1. Multi-agent orchestration TRƯỚC deterministic runtime
⚠️ 2. Fleet OTA TRƯỚC bootloader recovery
⚠️ 3. Plugin ecosystem TRƯỚC sandbox/RBAC
⚠️ 4. Hyperscale abstractions TRƯỚC single-node correctness
```

### What Will Kill This Project

> **Guarantee Inflation**: Module names promise enterprise/fleet/deterministic/exactly-once
> nhưng runtime không enforce được → users sẽ lose trust sau bricked board.

### True Moat

**Not**: Generic AI agents, multi-agent orchestration

**Is**: Deterministic, evidence-grounded embedded debugging and recovery

**Breakthrough**: An AI system that can say:
> "This crash came from this firmware build, this PC maps to this inlined source frame,
> this register/peripheral state proves this root cause, this patch fixes it,
> this HIL replay validates it, and this flash transaction can safely deploy or roll back."

---

## References

- `docs/PRODUCTION_READINESS_REVIEW.md` - Detailed review document
- `docs/AGENTS.md` - Agent instructions
- Phase documents: `docs/phase*.md`
