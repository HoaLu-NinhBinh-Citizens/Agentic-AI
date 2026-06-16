# fork — packaging aircode as a VS Code fork

Tooling to turn upstream VS Code into a rebranded, self-contained **aircode**
desktop app with the daemon + extension bundled in. This directory is the build
*harness*; it does not contain a VS Code checkout (that's cloned on demand and
git-ignored).

## Honest constraints

- **The clone + full build is heavy and runs on your machine/CI**, not here:
  ~1GB clone, Node + Python + a C++ toolchain (VS Build Tools / Xcode CLT /
  build-essential), node-gyp native builds, ~10GB disk, 30–60 min.
- **Signing needs your certificates** (paid, secret): Windows Authenticode and
  an Apple Developer ID + notarization. The scripts take them via env/secrets —
  none are stored in the repo.
- **Distribution needs a host** you control (static file host is enough).

What *is* verified here: the rebrand merge logic (`scripts/rebrand.test.mjs`,
4 tests) and that the bundled-daemon path is wired into the extension.

## Pipeline

```
clone.mjs      → shallow-clone microsoft/vscode at config/fork.config.json:pinnedTag
cargo build    → aircore daemon (release; PROTOC required, see editor-core)
npm run compile→ aircode extension (editor-extension)
rebrand.mjs    → deep-merge config/product.overrides.json into clone/product.json
bundle.mjs     → copy extension → clone/extensions/aircode + daemon → that ext's bin/
gulp           → clone builds the platform app (vscode-<target>-min)
sign-*.{ps1,sh}→ Authenticode / codesign + notarize
distribute     → upload artifacts + update.json to your host
```

One-shot:

```bash
# Windows
pwsh fork/scripts/build.ps1
# macOS / Linux
TARGET=darwin-arm64 fork/scripts/build.sh
```

## Rebranding

All branding lives in [`config/product.overrides.json`](config/product.overrides.json)
(app name, ids, URL protocol, Open VSX gallery, update URL). `rebrand.mjs`
deep-merges it into the clone's `product.json`. Swap icons by replacing the
clone's `resources/<platform>/` icons before `gulp` (add to `bundle.mjs` when you
have art).

> Gallery is pointed at **Open VSX** — the Microsoft Marketplace ToS forbids use
> by non-Microsoft products. Open VSX is the standard choice for forks.

## Signing

- **Windows** — `sign-win.ps1`, needs `WIN_CERT_PFX` + `WIN_CERT_PASS`. Sign the
  app binaries and the Inno installer.
- **macOS** — `sign-mac.sh`, needs a Developer ID identity + a `notarytool`
  profile; uses `config/entitlements.plist` (hardened runtime + JIT for V8).

## Distribution / auto-update

Set `updateUrl` in `product.overrides.json` to a host you control and serve VS
Code's update manifest. Minimal static layout:

```
https://updates.example.com/
  stable/win32-x64/latest        → { "version": "...", "url": "...", "sha256hash": "..." }
  stable/darwin-arm64/latest
  stable/linux-x64/latest
```

Leave `updateUrl` empty to ship without auto-update (manual downloads).

## CI

[`ci/fork-release.yml`](ci/fork-release.yml) builds all three platforms, signs
when secrets are present, and attaches artifacts to a `fork-v*` tag release.
Move it to `.github/workflows/` to enable it.

## Pinned upstream

`config/fork.config.json` pins the VS Code tag (`pinnedTag`). Bump it
deliberately and re-test the rebrand/bundle after each upstream upgrade — forks
break on upstream churn, so the pin is intentional.
