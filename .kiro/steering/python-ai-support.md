---
inclusion: fileMatch
fileMatchPattern: ['AI_support/**/*.py']
---

# AI_support Python

- Follow existing module boundaries in `AI_support`.
- Use `pytest`; test files are `test_*.py` under `AI_support/tests`.
- Run tests from the repository root with `python -m pytest AI_support\tests`; for focused tests use `python -m pytest AI_support\tests\test_name.py`.
- Use `asyncio.run(...)` for async tests unless the project adds an async pytest plugin.
- Prefer `tmp_path`, `monkeypatch`, and small local fakes over real filesystem, network, LLM, or hardware calls.
- Keep tests behavior-focused: one main behavior per test, clear asserts, no sleeps.
- Load config through existing config helpers or environment variables; do not hardcode secrets, absolute user paths, or provider credentials.
- Preserve structured return shapes used by tests instead of changing schemas casually.
