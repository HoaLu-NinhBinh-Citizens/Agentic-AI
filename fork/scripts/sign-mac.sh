#!/usr/bin/env bash
# Codesign + notarize the macOS .app. Requires an Apple Developer ID cert in the
# keychain and a notarytool profile/credentials. No secrets are stored here.
#
# Required env (DO NOT hardcode):
#   SIGN_IDENTITY     e.g. "Developer ID Application: Your Org (TEAMID)"
#   NOTARY_PROFILE    a stored `xcrun notarytool store-credentials` profile name
# Usage: APP=../VSCode-darwin-arm64/aircode.app ./fork/scripts/sign-mac.sh
set -euo pipefail

: "${APP:?set APP to the .app bundle}"
: "${SIGN_IDENTITY:?set SIGN_IDENTITY}"
: "${NOTARY_PROFILE:?set NOTARY_PROFILE}"

ENTITLEMENTS="$(cd "$(dirname "$0")/.." && pwd)/config/entitlements.plist"

echo "==> codesign (deep, hardened runtime)"
codesign --deep --force --options runtime \
  --entitlements "$ENTITLEMENTS" \
  --sign "$SIGN_IDENTITY" "$APP"

echo "==> notarize"
ZIP="${APP%.app}.zip"
ditto -c -k --keepParent "$APP" "$ZIP"
xcrun notarytool submit "$ZIP" --keychain-profile "$NOTARY_PROFILE" --wait

echo "==> staple"
xcrun stapler staple "$APP"
echo "Signed + notarized: $APP"
