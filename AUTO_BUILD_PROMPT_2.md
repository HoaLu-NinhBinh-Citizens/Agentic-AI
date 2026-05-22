# MASTER BUILD PROMPT - Part 2 (Phases 5e-10)

**Tiếp tục từ Phase 5e sau khi hoàn thành Part 1**

## QUY TẮC THỰC HIỆN

1. **Đọc prompt phase** từ `docs/phase*.md`
2. **Tạo/sửa code** đúng cấu trúc thư mục
3. **Viết unit test** (pytest)
4. **Commit** sau mỗi task (Conventional Commits)
5. **Ghi log** vào `build_log.md`
6. **Tự động sửa lỗi** nếu có thể

---

## PHASE 5e: Distributed Execution

### Mục tiêu
Multi-node distributed execution

### Cấu trúc thư mục
```
src/
├── core/orchestration/
│   ├── worker.py           # Worker node
│   ├── scheduler.py        # Task scheduler
│   └── node_registry.py   # Node discovery
└── infrastructure/messaging/
    └── redis_pubsub.py    # Redis pub/sub
```

### Tasks
- [ ] Tạo `src/core/orchestration/worker.py` - WorkerNode
- [ ] Tạo `src/core/orchestration/scheduler.py` - TaskScheduler
- [ ] Tạo `src/core/orchestration/node_registry.py` - NodeRegistry
- [ ] Tạo `src/infrastructure/messaging/redis_pubsub.py` - RedisPubSub
- [ ] Worker registration and heartbeat
- [ ] Task distribution
- [ ] Result collection
- [ ] Unit tests
- [ ] Integration tests

---

## PHASE 5f: Reliability & Governance

### Mục tiêu
Observability, metrics, health checks, circuit breaker

### Cấu trúc thư mục
```
src/
├── infrastructure/observability/
│   ├── metrics.py         # Prometheus metrics
│   ├── tracing.py         # OpenTelemetry tracing
│   └── logging/           # Structured logging
└── core/resilience/
    └── circuit_breaker.py # Circuit breaker pattern
```

### Tasks
- [ ] Tạo `src/infrastructure/observability/metrics.py` - Prometheus metrics
- [ ] Tạo `src/infrastructure/observability/tracing.py` - OpenTelemetry
- [ ] Tạo `src/infrastructure/observability/logging/` - Structured logging
- [ ] Tạo `src/core/resilience/circuit_breaker.py` - CircuitBreaker
- [ ] Health check endpoints
- [ ] Integration tests

---

## PHASE 6.1: Hardware Debug Interface

### Mục tiêu
J-Link/RTT integration, register access, memory read/write

### Cấu trúc thư mục
```
src/
├── domain/hardware/
│   ├── probe.py           # Probe interface
│   ├── registers.py       # Register definitions
│   └── interrupts.py      # Interrupt handling
├── infrastructure/hardware/
│   ├── jlink/
│   │   ├── probe.py      # J-Link implementation
│   │   └── rtt.py        # RTT channels
│   └── probe_manager.py   # Probe management
└── configs/hardware/
    └── targets.yaml       # Target configurations
```

### Tasks
- [ ] Tạo `src/domain/hardware/probe.py` - Probe interface
- [ ] Tạo `src/domain/hardware/registers.py` - Register definitions
- [ ] Tạo `src/infrastructure/hardware/jlink/probe.py` - J-Link implementation
- [ ] Tạo `src/infrastructure/hardware/jlink/rtt.py` - RTT channels
- [ ] Tạo `src/infrastructure/hardware/probe_manager.py` - Probe management
- [ ] Tạo `src/configs/hardware/targets.yaml` - Target configs
- [ ] Memory read/write
- [ ] Register access
- [ ] Unit tests (mock J-Link)
- [ ] Integration tests (with real J-Link if available)

---

## PHASE 6.2: Flash Infrastructure

### Mục tiêu
Firmware flash với transaction, A/B layout, streaming, symbol indexing

### Cấu trúc thư mục
```
src/
├── domain/hardware/flash/
│   ├── flash_transaction.py    # Transaction model
│   ├── flash_layout.py        # A/B layout
│   ├── erase_policy.py        # Erase policies
│   ├── streaming_flash.py     # Streaming flash
│   ├── symbol_index.py        # ELF symbol indexing
│   ├── memory_map_validator.py # Memory validation
│   └── secure_boot.py         # Secure boot
├── infrastructure/hardware/flash/
│   ├── flash_manager.py       # Flash manager
│   ├── flash_driver.py        # Flash driver interface
│   └── storage.py             # Remote storage (HTTP)
└── tests/unit/test_flash*.py
```

### Tasks
- [ ] Tạo `src/domain/hardware/flash/flash_transaction.py` - FlashTransaction, TransactionStatus
- [ ] Tạo `src/domain/hardware/flash/flash_layout.py` - FlashLayout, A/B slot selection
- [ ] Tạo `src/domain/hardware/flash/erase_policy.py` - ErasePolicy (MINIMAL, FULL)
- [ ] Tạo `src/domain/hardware/flash/streaming_flash.py` - StreamingFlash
- [ ] Tạo `src/domain/hardware/flash/symbol_index.py` - SymbolIndex (DWARF parsing)
- [ ] Tạo `src/domain/hardware/flash/memory_map_validator.py` - MemoryMapValidator
- [ ] Tạo `src/domain/hardware/flash/secure_boot.py` - SecureBoot, version enforcement
- [ ] Tạo `src/infrastructure/hardware/flash/flash_manager.py` - FlashManager
- [ ] Tạo `src/infrastructure/hardware/flash/flash_driver.py` - FlashDriver interface
- [ ] Tạo `src/infrastructure/hardware/flash/storage.py` - RemoteStorage (HTTP)
- [ ] Tạo unit tests: test_flash_transaction.py, test_flash_layout.py, etc.
- [ ] Integration tests
- [ ] Chaos tests

### Flash Protocol (J-Link)
```
┌─────────────────────────────────────────────────────────┐
│ Flash Flow                                                │
├─────────────────────────────────────────────────────────┤
│ 1. Load ELF/BIN from file or HTTP                       │
│ 2. Parse ELF symbols (SymbolIndex)                       │
│ 3. Validate memory map (MemoryMapValidator)               │
│ 4. Select target slot (A/B Layout)                       │
│ 5. Create FlashTransaction                               │
│ 6. Capture pre-flash snapshot (Phase 6.1)                 │
│ 7. Apply ErasePolicy                                     │
│ 8. Flash with progress callback                          │
│ 9. Verify checksum                                       │
│ 10. Commit transaction                                   │
│ 11. Update boot selector (A/B swap)                      │
│ 12. On failure: RollbackToSnapshot                        │
└─────────────────────────────────────────────────────────┘
```

---

## PHASE 6.3: Real-Time Tracing

### Mục tiêu
Live register/memory tracing via RTT

### Tasks
- [ ] RTT up-channel reader
- [ ] Real-time register updates
- [ ] Memory watch points
- [ ] Trace buffering
- [ ] Unit tests

---

## PHASE 7: CLI + TUI

### Mục tiêu
Command-line and terminal UI interfaces

### Cấu trúc thư mục
```
src/interfaces/
├── cli/
│   ├── main.py           # CLI entry point
│   └── commands/        # CLI commands
└── tui/
    ├── app.py           # TUI application
    ├── screens/         # TUI screens
    └── widgets/         # TUI widgets
```

### Tasks
- [ ] Tạo `src/interfaces/cli/main.py` - CLI entry point
- [ ] Tạo `src/interfaces/cli/commands/` - Các commands (flash, debug, etc.)
- [ ] Tạo `src/interfaces/tui/app.py` - TUI application
- [ ] Tạo `src/interfaces/tui/screens/` - Các screens
- [ ] Tạo `src/interfaces/tui/widgets/` - Các widgets
- [ ] Unit tests

---

## PHASE 8: VS Code Extension

### Mục tiêu
VS Code extension cho embedded development

### Cấu trúc thư mục
```
vscode-extension/
├── src/
│   ├── extension.ts     # Extension entry
│   ├── debug/           # Debug adapter
│   ├── flash/           # Flash UI
│   └── webview/         # Webview panels
├── package.json
└── tsconfig.json
```

### Tasks
- [ ] Tạo VS Code extension project
- [ ] Debug adapter protocol implementation
- [ ] Flash panel webview
- [ ] Register view
- [ ] Memory view
- [ ] Integration tests

---

## PHASE 9: Distributed Agents

### Mục tiêu
Multi-agent distributed debugging

### Tasks
- [ ] Agent federation
- [ ] Distributed task execution
- [ ] Shared memory spaces
- [ ] Consensus protocols
- [ ] Unit tests

---

## PHASE 10: Advanced Reasoning

### Mục tiêu
Advanced AI reasoning capabilities

### Tasks
- [ ] Tree of Thoughts
- [ ] Self-reflection
- [ ] Plan revision
- [ ] Multi-step reasoning
- [ ] Unit tests

---

## BẮT ĐẦU THỰC HIỆN

**Đọc chi tiết prompts từ `docs/phase*.md` trước khi code.**

Commit format: `feat(phase-N): description`

Cập nhật `build_log.md` sau mỗi phase.
