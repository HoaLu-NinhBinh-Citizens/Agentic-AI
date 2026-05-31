---
inclusion: fileMatch
fileMatchPattern: ['main/software/**/*.c', 'main/software/**/*.h', 'main/software/**/*.cpp', 'main/software/**/*.hpp', 'AI_support/**/*.py']
---

# C/C++ Formatting

- Follow `.clang-format` if present; otherwise match nearby code.
- Use 4 spaces unless local style differs.
- Keep lines under 120 characters where practical.
- Use braces for `if`, `else`, `for`, and `while`.
- Use `UPPER_SNAKE_CASE` for macros.
- Prefer existing project naming over new naming rules.

# Python Formatting

- Follow `ruff` or `black` if configured; otherwise match nearby code.
- Use 4 spaces for indentation.
- Keep lines under 120 characters.
- Use `snake_case` for functions and variables, `PascalCase` for classes.
- Use type hints for function signatures in new code.
- Prefer f-strings over `.format()` or `%`.

