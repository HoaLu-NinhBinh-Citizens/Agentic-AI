---
description: Core Cursor behavior for this repository
alwaysApply: true
---

# Core Cursor Behavior

This file is self-contained for Cursor.

`AGENTS.md` is the shared source for Codex, Claude, Gemini, and other agents, but Cursor should not rely on opening it automatically.

When rules conflict, follow this order:

1. More specific `.cursor/rules/*.mdc` path rule
2. This `00-core.mdc`
3. `AGENTS.md` if the agent has explicitly read it

## Read First

- If the user references a file, folder, symbol, command, or error, inspect it before answering.
- Prefer `rg` and `rg --files` for repo search.
- Search before saying something does not exist.
- Do not guess tool output, code behavior, paths, or facts that can be checked.
- If evidence is missing, say what is missing and how to verify it.

## Repository Map

- `AI_support/`: Python agent, retrieval, LLM adapters, services, tools, and pytest tests.
- `main/software/`: STM32 firmware, build/flash/test scripts, SEGGER/J-Link tools, and generated output.
- `main/hardware/`: PCB, schematics, hardware documents, and reference assets.
- `.cursor/rules/`: Cursor-specific rules. These may duplicate key `AGENTS.md` guidance because Cursor does not automatically load `AGENTS.md`.

## Execute Safely

- If the request is clear, act directly after gathering the needed context.
- Ask only when missing information cannot be recovered from the repo and guessing would be risky.
- Reversible actions are allowed: read files, edit code, run tests, inspect build output.
- Before destructive or hardware/system actions, validate target and scope.
- For delete, overwrite, flash, or state-changing operations, get confirmation unless the user explicitly requested that exact action.
- If a tool fails, retry once when reasonable, otherwise report the failure and the next useful step.

## Code Changes

- Keep edits limited to the request.
- Follow existing project patterns before adding new abstractions.
- Do not do unrelated refactors or formatting churn.
- Add comments only to explain non-obvious why: protocol rules, timing, hardware registers, state transitions, workarounds, or derived constants.
- Never hardcode secrets.
- Do not hack around tests. If a test looks wrong, verify and explain.

### No Hard-Coding

Never hardcode values directly in logic. Use named constants, config files, defines, or environment variables.

- ❌ `if (speed > 1500)` → ✅ `if (speed > MOTOR_MAX_RPM)`
- ❌ `HAL_Delay(200)` → ✅ `HAL_Delay(DEBOUNCE_DELAY_MS)`
- ❌ `model = "gpt-4o"` → ✅ `model = config.get("openai_model")`
- ❌ `path = "C:/Users/thang/..."` → ✅ `path = os.getenv("PROJECT_DATA_DIR")`

This applies to: timeouts, buffer sizes, pin assignments, paths, URLs, API keys, and any domain-specific threshold.

### File Size Limit

- A single source file must not exceed **500 lines** (including comments and blanks).
- A single function must not exceed **50 lines**.
- If a file approaches 500 lines, split by responsibility.
- Applies to all languages: `.c`, `.h`, `.py`, `.js`, `.ts`.

## Verification

- Run the smallest relevant check when practical.
- Before final response, verify the result matches the request and note any unverified part.
- For complex work, use a short plan, execute step by step, and stop when requirements are satisfied.

## Output

- Always respond in the same language the user uses (e.g., Vietnamese prompt → Vietnamese reply, English prompt → English reply).
- Be concise and direct.
- Lead with the result.
- Mention changed files and verification.
- If blocked, state the blocker and the next concrete step.
