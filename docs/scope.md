# Scope - AI_SUPPORT MVP

**Date:** 2026-05-23
**Phase:** 1a.1
**Status:** LOCKED

---

## Locked Scope

> ⚠️ **CRITICAL:** This scope is locked. Do not expand without Phase 1a.1 review.

### In Scope

| Category | Items |
|----------|-------|
| **Chip Family** | ARM Cortex-M only |
| **Debug Interface** | SWD only (JTAG future) |
| **View Mode** | Debug view only (no firmware update) |
| **Probe Support** | J-Link, ST-Link, CMSIS-DAP |
| **Analysis** | ELF parsing, symbol analysis, register inspection |

### Out of Scope

| Category | Items | Phase |
|----------|-------|-------|
| Firmware Update | OTA, flash programming | Phase 9+ |
| Multi-device | Fleet coordination | Phase 14+ |
| Symbolic Execution | Path-sensitive analysis | Phase 12+ |
| RISC-V/ESP32 | Other architectures | Future |
| AI Patch Generation | Autonomous fix | Phase 10+ |

---

## MVP Boundaries

```
┌─────────────────────────────────────────────────┐
│                  AI_SUPPORT MVP                  │
├─────────────────────────────────────────────────┤
│  ✅ Debug View (registers, memory, stack)       │
│  ✅ ELF Parsing (symbols, sections)             │
│  ✅ Hardware Probes (J-Link, ST-Link)           │
│  ✅ Real-time Tracing (RTT)                      │
│  ✅ SVD Parser (ARM peripherals)                │
├─────────────────────────────────────────────────┤
│  ❌ Firmware Update                             │
│  ❌ Multi-device Coordination                   │
│  ❌ Symbolic Execution                          │
│  ❌ Fleet Management                           │
└─────────────────────────────────────────────────┘
```

---

## Rationale

**Why ARM Cortex-M only?**
- Dominant in automotive/industrial
- Rich tooling ecosystem (CMSIS-SVD, CMSIS-DAP)
- Clear debug semantics

**Why SWD only?**
- Simpler interface
- Lower pin count
- Sufficient for most debug needs

**Why debug view only?**
- Focus on core competency
- Avoid scope creep
- Ship working MVP first
