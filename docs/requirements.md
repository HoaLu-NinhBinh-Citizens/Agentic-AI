# Requirements - AI_SUPPORT

**Date:** 2026-05-23
**Phase:** 1a.1
**Product:** Embedded CI/HIL Intelligence Platform

---

## Mục tiêu

Build một local AI agent hỗ trợ debug firmware nhúng cho embedded systems.

## Người dùng mục tiêu

- Embedded firmware engineers
- Automotive platform engineers
- Firmware developers working with ARM Cortex-M, RISC-V, ESP32

## Yêu cầu chức năng

### Core Features

1. **Debug Firmware nhúng**
   - Kết nối với hardware probes (J-Link, ST-Link, CMSIS-DAP, pyOCD)
   - Đọc registers, memory, stack traces
   - Parse core dumps
   - Real-time tracing (RTT)

2. **Firmware Analysis**
   - Parse ELF files
   - Symbol analysis
   - Call graph understanding
   - ISR (Interrupt Service Routine) identification

3. **Hardware Understanding**
   - SVD parser cho ARM Cortex-M peripherals
   - Register semantics
   - GPIO/DMA/IRQ reasoning
   - Clock tree analysis

### Supported Platforms

| Platform | Status | Interface |
|----------|--------|-----------|
| ARM Cortex-M | Primary | SWD/JTAG |
| RISC-V | Future | JTAG |
| ESP32 | Future | JTAG |

### Non-Functional Requirements

- **Performance:** Sub-second response for debug queries
- **Reliability:** Deterministic behavior, no hallucinations
- **Usability:** CLI + WebSocket interface
- **Extensibility:** Plugin-based architecture

## Use Cases

1. **HardFault Analysis** — Analyze crash dump, identify root cause
2. **Register State Inspection** — Query peripheral registers during runtime
3. **Memory Dump** — Read memory regions for debugging
4. **Symbol Lookup** — Find function/variable addresses
5. **Peripheral Debug** — Query HAL information for peripherals

## Out of Scope (Phase 1)

- Firmware update/OTA
- Multi-device coordination
- Fleet management
- Symbolic execution
- AI patch generation

---

## Acceptance Criteria

- [ ] Debug interface connects to ARM Cortex-M targets
- [ ] Can read registers and memory
- [ ] Can parse ELF files and extract symbols
- [ ] Provides CLI and WebSocket interfaces
- [ ] No hardcoded values (use config)
