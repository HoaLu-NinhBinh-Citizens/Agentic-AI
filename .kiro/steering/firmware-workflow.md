---
inclusion: fileMatch
fileMatchPattern: ['main/software/**']
---

# Firmware Workflow

Run commands from `main/software`.

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

Clean/rebuild:

```bash
python build.py --clean
python clean.py
```

Rules:

- Build outputs are under `main/software/output`.
- `EngineCar` and `RemoteControl` are the valid flash project names.
- Prefer `--verify-only` or `--dry-run` before hardware actions.
- Do not run actual `python flash.py <project>` unless the user explicitly asks to flash or confirms the exact target.
- Do not run hardware tests without `--dry-run` unless the user confirms hardware is connected and powered.
- Before clean commands, confirm the working directory is `main/software` because they delete generated output/cache files.
