# Internal dogfooding

How to cut an internal build and start using aircode on real work today. No
signing, no installer — a portable archive teammates unzip and run.

## 1. Package the build you already made

After `build.ps1`/`build.sh` produced `fork/build/VSCode-<target>`:

```powershell
pwsh fork/scripts/package-internal.ps1            # Windows
```
```bash
TARGET=darwin-arm64 fork/scripts/package-internal.sh   # macOS / Linux
```

Output in `fork/dist/`:
- `aircode-<target>-<vscodeVer>-<date>-<sha>.zip` (or `.tar.gz`)
- `.sha256` checksum
- `.version.json` provenance (channel=internal, fork commit, build time)

Share the archive on your internal drive / release channel.

## 2. Run it

- **Windows**: unzip, run `aircode.exe`. SmartScreen on an unsigned build →
  *More info → Run anyway*.
- **macOS**: unzip, first launch → right-click `aircode.app` → *Open* (Gatekeeper).
- **Linux**: extract, run `./aircode`.

Confirm the rebrand: Help → About shows **aircode**; settings/data live under
`.aircode` (not `.vscode`).

## 3. Prereqs for full functionality

| Feature | Needs |
|---|---|
| Indexing, symbol nav, Next-Edit (rename propagation) | nothing — works offline |
| Inline completion | [Ollama](https://ollama.com) running + `ollama pull qwen2.5-coder:3b` |
| Ollama embeddings / LanceDB persistence | enable `aircode.useOllamaEmbeddings` / `aircode.useLance` in settings |

## 4. Dogfood target: this repo

Open the `Agentic-AI` folder in aircode itself — it's a great first test:

1. Output panel → channel **aircode** → expect `initialized + indexed`.
2. Edit a Rust/Python file; with Ollama up, inline ghost text appears.
3. Rename a function and **save** → `⇥ rename` markers at call sites → **Tab**
   applies them across files (mechanical, no model).
4. Hit a rough edge? It's logged in the aircode Output channel — capture it.

## 5. Feedback loop

Turn on telemetry to collect accept/reject for the future fine-tune (ADR-001):
the daemon writes `.aircode/telemetry.jsonl` when telemetry is enabled at
`initialize`. For internal dogfooding, eyeball that file + the Output channel and
file issues. Keep a running list of: missed completions, wrong Next-Edit sites,
daemon crashes, latency that feels off.
