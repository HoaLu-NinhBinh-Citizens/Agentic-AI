# PR-004 Affected Files

> **Date**: 2026-06-14
> **PR**: PR-004 — Delete Remaining Dead Code and Fix Broken Test Suite
> **Total files affected**: ~76 deleted, ~19 modified, 1 moved

---

## Files to DELETE

### Group A: Redirect Packages (48 files)

#### `src/runtime/` (3 files + 1 top-level)
```
DELETE  src/runtime/__init__.py
DELETE  src/runtime/journal.py
DELETE  src/runtime/replayer.py
DELETE  src/runtime.py
```

#### `src/tools/` (9 files)
```
DELETE  src/tools/__init__.py
DELETE  src/tools/audit.py
DELETE  src/tools/cache.py
DELETE  src/tools/context.py
DELETE  src/tools/executor.py
DELETE  src/tools/flash_tools.py
DELETE  src/tools/registry.py
DELETE  src/tools/sandbox.py
DELETE  src/tools/schema.py
```

#### `src/hardware_engine/` (17 files + 1 top-level)
```
DELETE  src/hardware_engine/__init__.py
DELETE  src/hardware_engine/core/clock_tree.py
DELETE  src/hardware_engine/core/interrupt_model.py
DELETE  src/hardware_engine/core/models.py
DELETE  src/hardware_engine/core/peripheral_graph.py
DELETE  src/hardware_engine/core/pin_map.py
DELETE  src/hardware_engine/core/register_schema.py
DELETE  src/hardware_engine/engine/allocator.py
DELETE  src/hardware_engine/engine/clock_engine.py
DELETE  src/hardware_engine/engine/interrupt_engine.py
DELETE  src/hardware_engine/engine/pinmux_engine.py
DELETE  src/hardware_engine/engine/register_engine.py
DELETE  src/hardware_engine/codegen/assertions.py
DELETE  src/hardware_engine/codegen/templates.py
DELETE  src/hardware_engine/integration/hw_agent.py
DELETE  src/hardware_engine/validator/hw_validator.py
DELETE  src/hardware_engine/validator/rules.py
DELETE  src/hardware_engine.py
```

#### `src/config/` (3 files — after relocating `ai_support_config.py`)
```
DELETE  src/config/__init__.py
DELETE  src/config/output_policy.py
DELETE  src/config/agent_prompts.py
```

#### `src/health/` (2 files)
```
DELETE  src/health/__init__.py
DELETE  src/health/health_check.py
```

#### `src/llm/` (2 files)
```
DELETE  src/llm/__init__.py
DELETE  src/llm/ollama.py
```

#### `src/models/` (2 files + 1 top-level)
```
DELETE  src/models/__init__.py
DELETE  src/models/build.py
DELETE  src/models.py
```

#### `src/parsing/` (2 files)
```
DELETE  src/parsing/__init__.py
DELETE  src/parsing/response_parser.py
```

#### `src/security/` (1 file)
```
DELETE  src/security/tool_permissions.py
```

#### `src/scheduler/` (1 file + 1 top-level)
```
DELETE  src/scheduler/__init__.py
DELETE  src/scheduler.py
```

### Group B: Dead Subsystem (6 files)

```
DELETE  src/core/events/__init__.py
DELETE  src/core/events/emitter.py
DELETE  src/core/events/event.py
DELETE  src/core/events/handlers.py
DELETE  src/core/events/middleware.py
DELETE  src/core/events/types.py
```

### Group C: Orphan Application Files (3 files)

```
DELETE  src/application/api/app/chat_endpoints.py
DELETE  src/application/api/app/api_server.py
DELETE  src/application/api/app/dashboard_websocket.py
```

### Group D: Dead Test Files (7 files)

```
DELETE  tests/test_events.py
DELETE  tests/test_hardware.py
DELETE  tests/test_learning.py
DELETE  tests/test_observability.py
DELETE  tests/test_p5_memory.py
DELETE  tests/test_phase4.py
DELETE  tests/test_p9_production_concepts.py
```

### Group E: Stale `__pycache__` Directories (3 directory trees)

```
DELETE  src/core/multi_agent/          (entire tree — empty dirs + __pycache__/*.pyc)
DELETE  src/core/orchestration/        (entire tree — empty dirs + __pycache__/*.pyc)
DELETE  src/multi_agent/               (entire tree — empty dirs + __pycache__/*.pyc)
```

---

## Files to MOVE (1 file)

```
MOVE    src/config/ai_support_config.py  →  src/core/config/ai_support_config.py
```

**Reason**: This is original code (123 LOC, not a redirect), currently stored inside the `src/config/` redirect package. Must be relocated to canonical location before the redirect package can be deleted.

---

## Files to MODIFY (test import redirects — up to 19 files)

### Commit 1: Passing test import updates (9 files)

| File | Change |
|------|--------|
| `tests/test_output_policy.py` | `src.config.output_policy` → `src.core.config.output_policy` |
| `tests/test_p2_sandbox.py` | `src.tools.sandbox` → `src.core.tools.sandbox` |
| `tests/test_p3_observability.py` | `src.runtime.journal` / `src.runtime.replayer` → `src.core.runtime.journal` / `src.core.runtime.replayer` |
| `tests/test_features_2025.py` | `src.models` → `src.infrastructure.models` |
| `tests/test_runtime.py` | `src.runtime` → `src.core.runtime` |
| `tests/test_sandbox.py` | `src.tools.*` → `src.core.tools.*` |
| `tests/test_tools.py` | `src.tools.*` → `src.core.tools.*` |
| `tests/unit/test_config.py` | `src.config.ai_support_config` → `src.core.config.ai_support_config` |
| `tests/test_pdf_benchmark.py` | Check if it uses redirect imports (verify during implementation) |

### Commit 2: Broken test import fixes (up to 10 files)

| File | Change |
|------|--------|
| `tests/test_flash_tools.py` | `src.tools.*` → `src.core.tools.*` |
| `tests/test_hardware_engine.py` | `src.hardware_engine.*` → `src.domains.hardware_engine.*` |
| `tests/test_p4_retrieval.py` | `src.models` → `src.infrastructure.models` |
| `tests/test_p7_hardware.py` | `src.hardware_engine.*` → `src.domains.hardware_engine.*`, `src.tools.*` → `src.core.tools.*` |
| `tests/test_phase15.py` | `src.runtime` → `src.core.runtime`, `src.scheduler` → `src.core.scheduler` |
| `tests/test_retrieval_manifest.py` | `src.retrieval.manifest` → `src.infrastructure.retrieval.manifest`, `src.config.agent_prompts` → `src.core.config.agent_prompts` |
| `tests/test_retrieval_search_cache.py` | `src.retrieval.search_cache` → `src.infrastructure.retrieval.search_cache` |
| `tests/test_aikicad_agent.py` | Verify collection behavior — may need no change (already has `pytest.skip()`) |
| `tests/test_embedded_agent_regression.py` | Verify collection behavior — already has `pytestmark = pytest.mark.skip` |

---

## Files NOT Modified (Do-Not-Touch List)

```
UNCHANGED  src/interfaces/server/main.py
UNCHANGED  src/core/agent/*
UNCHANGED  src/application/orchestration/tool_execution/*
UNCHANGED  src/application/api/app/embedded_agent.py
UNCHANGED  src/application/api/app/component_factory.py
UNCHANGED  src/domains/*  (source code — tests may be updated)
UNCHANGED  src/domain/*
UNCHANGED  src/infrastructure/*  (except orphan files in Group C)
UNCHANGED  src/shared/*
UNCHANGED  src/schemas/*
UNCHANGED  src/agentic_ai/*
UNCHANGED  pyproject.toml
```

---

## Summary

| Action | Count |
|--------|-------|
| Files deleted (source) | ~57 |
| Files deleted (tests) | 7 |
| Directories deleted (stale) | 3 trees |
| Files moved | 1 |
| Files modified (tests) | up to 19 |
| Files NOT modified | All production source |
| New files created | 0 |
