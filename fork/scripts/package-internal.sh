#!/usr/bin/env bash
# Package an already-built fork into an INTERNAL portable archive (no signing).
# Run AFTER build.sh produced fork/build/VSCode-<target>.
#
# Usage: TARGET=darwin-arm64 fork/scripts/package-internal.sh   (or linux-x64)
set -euo pipefail

FORK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${TARGET:-linux-x64}"
APP_DIR="$FORK_DIR/build/VSCode-$TARGET"
DIST_DIR="$FORK_DIR/dist"

[ -d "$APP_DIR" ] || { echo "Build output not found: $APP_DIR. Run build.sh first."; exit 1; }

VSCODE_VER="$(node -p "require('$FORK_DIR/build/vscode/package.json').version")"
DATE="$(date -u +%Y%m%d)"
SHA="$(git -C "$FORK_DIR" rev-parse --short HEAD)"
NAME="aircode-$TARGET-$VSCODE_VER-$DATE-$SHA"

mkdir -p "$DIST_DIR"
ARCHIVE="$DIST_DIR/$NAME.tar.gz"
echo "Archiving $APP_DIR -> $ARCHIVE"
tar -czf "$ARCHIVE" -C "$APP_DIR" .

# Checksum (sha256sum on Linux, shasum on macOS).
if command -v sha256sum >/dev/null; then HASH="$(sha256sum "$ARCHIVE" | cut -d' ' -f1)"
else HASH="$(shasum -a 256 "$ARCHIVE" | cut -d' ' -f1)"; fi
echo "$HASH  $NAME.tar.gz" > "$DIST_DIR/$NAME.tar.gz.sha256"

echo ""
echo "Internal build ready: $ARCHIVE"
echo "  sha256: $HASH"
echo "macOS note: unsigned app -> right-click > Open the first time (Gatekeeper)."
