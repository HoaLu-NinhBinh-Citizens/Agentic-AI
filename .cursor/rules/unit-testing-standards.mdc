---
description: Embedded C firmware tests
globs: main/software/**/*test*.c, main/software/**/*test*.cpp, main/software/**/tests/**/*.c, main/software/**/tests/**/*.cpp
alwaysApply: false
---

# Firmware Tests

- Apply only to embedded C/C++ tests, not `AI_support/tests`.
- Use the project's C test framework, usually Unity/Ceedling.
- Test hardware-independent logic with HAL mocks.
- Do not include real `stm32f4xx_hal.h` in logic unit tests.
- Verify state changes and HAL calls instead of physical registers.
- Use Arrange, Act, Assert.
- Keep tests atomic.
- Name files `test_<module>.c` where practical.
