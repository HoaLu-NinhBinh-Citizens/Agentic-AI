# Agent Instructions

These instructions are shared across coding agents such as Codex, Claude Code, Cursor, and other agentic IDEs.

## Core Behavior

- Read referenced files, folders, symbols, commands, and errors before answering.
- Prefer `rg` and `rg --files` for repository search.
- Search before saying something does not exist.
- Do not guess tool output, code behavior, paths, or facts that can be checked.
- If required evidence is missing, say what is missing and how to verify it.
- If the request is clear, act directly after gathering the needed context.
- Ask only when missing information cannot be recovered from the repo and guessing would be risky.

## Safety

- Reversible actions are allowed: read files, edit code, run tests, inspect build output.
- Before destructive or hardware/system actions, validate target and scope.
- Get confirmation before delete, overwrite, flash, or state-changing operations unless the user explicitly requested that exact action.
- If a tool fails, retry once when reasonable, otherwise report the failure and the next useful step.

## Code Changes

- Keep edits limited to the request.
- Follow existing project patterns before adding new abstractions.
- Do not do unrelated refactors or formatting churn.
- Add comments only to explain non-obvious why: protocol rules, timing, hardware registers, state transitions, workarounds, or derived constants.
- Avoid unexplained magic values in domain logic. Use named constants or existing config for thresholds, timeouts, buffer sizes, paths, URLs, and hardware/protocol values.
- Never hardcode secrets.
- Do not hack around tests. If a test looks wrong, verify and explain.

## Verification

- Run the smallest relevant check when practical.
- Before final response, verify the result matches the request and note any unverified part.
- For complex work, use a short plan, execute step by step, and stop when requirements are satisfied.

## Repository Map

- `src/AI_support/`: Python agent, retrieval, LLM, services, tooling, and tests.
- `tests/`: pytest test suite.
- `main/software/`: STM32 firmware, build/flash/test scripts, tools, and generated outputs.
- `main/hardware/`: PCB, documents, references, and hardware assets.

## AI_support Python

- Follow existing module boundaries.
- Use `pytest`; test files are `test_*.py` under `tests/`.
- Run tests from the repository root with `python -m pytest tests`; for focused tests use `python -m pytest tests/test_name.py`.
- Use `asyncio.run(...)` for async tests unless the project adds an async pytest plugin.
- Prefer `tmp_path`, `monkeypatch`, and small local fakes over real filesystem, network, LLM, or hardware calls.
- Preserve structured return shapes used by tests instead of changing schemas casually.

## Firmware Workflow

Run firmware commands from `main/software`.

Safe checks:

```bash
python build.py --verify-only
python verify_jlink.py
python flash.py EngineCar --dry-run
python flash.py RemoteControl --dry-run
python test.py --dry-run
```

Build:

```bash
python build.py
```

Rules:

- Build outputs are under `main/software/output`.
- `EngineCar` and `RemoteControl` are the valid flash project names.
- Prefer `--verify-only` or `--dry-run` before hardware actions.
- Do not run actual `python flash.py <project>` unless the user explicitly asks to flash or confirms the exact target.
- Do not run hardware tests without `--dry-run` unless the user confirms hardware is connected and powered.
- Before clean commands, confirm the working directory is `main/software` because they delete generated output/cache files.

## Embedded C

- Apply embedded C rules to project-owned firmware code.
- Do not style-edit vendor, generated, SDK, CMSIS, HAL, SEGGER, lwIP, or toolchain files.
- Be careful with interrupts, DMA, shared state, hardware registers, bootloader code, flash, and raw memory access.
- Use named constants for delays, timeouts, buffer sizes, pins, register masks, protocol IDs, frame sizes, and clock-derived values.
- Explain why for hardware registers, protocol logic, timing constraints, state transitions, bit fields, workarounds, and derived constants.
- Prefer existing include guard, status type, handle naming, and file organization patterns.

## Git

Use Conventional Commits when creating commits:

`<type>(<scope>): <subject>`

Allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`.
