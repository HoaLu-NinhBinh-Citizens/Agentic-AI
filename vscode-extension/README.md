# AI_SUPPORT VS Code Extension (Phase 8 scaffold)

## Setup

```bash
cd vscode-extension
npm install
npm run compile
```

Press F5 in VS Code to launch Extension Development Host.

## Commands

- **AI_SUPPORT: Open Flash Panel** — flash plan webview
- **AI_SUPPORT: Open Register View** — register sidebar
- **AI_SUPPORT: Connect Target** — target picker (wire to CLI)

## Next steps

- Wire `ai-support` debug type to GDB/MI or debugpy-style adapter
- Call `ai-support debug connect` from `connectTarget`
- WebSocket bridge to running AI_SUPPORT server
