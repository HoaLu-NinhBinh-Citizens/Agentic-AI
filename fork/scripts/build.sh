#!/usr/bin/env bash
# End-to-end fork build (macOS/Linux). Produces a rebranded, aircode-bundled
# VS Code under build/../VSCode-<platform>-<arch>.
#
# Prerequisites (NOT auto-installed): Node 18+, Python 3, a C++ toolchain
# (Xcode CLT on macOS / build-essential on Linux), Rust + protoc (PROTOC).
#
# Usage: TARGET=darwin-arm64 ./fork/scripts/build.sh   (or linux-x64)
set -euo pipefail

FORK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CLONE_DIR="$FORK_DIR/build/vscode"
TARGET="${TARGET:-linux-x64}"   # darwin-arm64 | darwin-x64 | linux-x64

echo "==> 1/5 clone VS Code"
node "$FORK_DIR/scripts/clone.mjs"

echo "==> 2/5 build aircore daemon (release)"
[ -z "${PROTOC:-}" ] && echo "WARN: PROTOC not set; LanceDB build may fail (see editor-core/README.md)"
( cd "$FORK_DIR/../editor-core" && cargo build --release )

echo "==> 3/5 compile aircode extension"
( cd "$FORK_DIR/../editor-extension" && npm ci && npm run compile )

echo "==> 4/5 rebrand + bundle"
node "$FORK_DIR/scripts/rebrand.mjs" --product "$CLONE_DIR/product.json"
node "$FORK_DIR/scripts/bundle.mjs"

echo "==> 5/5 build VS Code (gulp) for $TARGET"
( cd "$CLONE_DIR" && npm ci && npm run gulp -- "vscode-${TARGET}-min" )

echo "DONE. App under $(dirname "$CLONE_DIR")/VSCode-${TARGET}"
echo "Next: sign with fork/scripts/sign-mac.sh (macOS)."
