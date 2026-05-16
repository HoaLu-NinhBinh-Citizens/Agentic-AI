---
description: Embedded C and STM32 firmware rules
globs: main/software/**/*.c, main/software/**/*.h, main/software/**/*.cpp, main/software/**/*.hpp
alwaysApply: false
---

# Embedded C

- Apply to project-owned firmware code.
- Do not style-edit vendor, generated, SDK, CMSIS, HAL, SEGGER, lwIP, or toolchain files.
- Be careful with interrupts, DMA, shared state, hardware registers, bootloader code, flash, and raw memory access.
- Preserve existing safety assumptions unless the task is to change them.
- Use named constants for delays, timeouts, buffer sizes, pins, register masks, protocol IDs, frame sizes, and clock-derived values.
- Explain why for hardware registers, protocol logic, timing constraints, state transitions, bit fields, workarounds, and derived constants.
- Prefer existing include guard, status type, handle naming, and file organization patterns.
- Keep functions and files small where practical, but do not split existing large files only for style.
