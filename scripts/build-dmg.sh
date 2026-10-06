#!/bin/bash
# A release build fails closed without Developer ID + notarization access.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
MODE="${1:-release}"
[[ "$MODE" == release || "$MODE" == --development ]] || { echo 'Usage: build-dmg.sh [--development]' >&2; exit 2; }
[[ "$(uname -s)" == Darwin ]] || { echo 'Build on macOS.' >&2; exit 1; }
export TOKENCOACH_ARCH="${TOKENCOACH_ARCH:-$(uname -m)}"
[[ "$TOKENCOACH_ARCH" == arm64 || "$TOKENCOACH_ARCH" == x86_64 ]] || { echo 'Use arm64 or x86_64.' >&2; exit 1; }
PYTHON="${TOKENCOACH_BUILD_PYTHON:-$ROOT/.venv/bin/python}"
"$PYTHON" packaging/macos/verify-environment.py
export TOKENCOACH_BUILD_VERSION="$("$PYTHON" -c 'from tokencoach.version import VERSION; print(VERSION)')"
REVISION="$(git rev-parse HEAD)"
if [[ "$MODE" == release ]]; then
  : "${TOKENCOACH_SIGN_IDENTITY:?Set a Developer ID Application identity (not credentials)}"
  : "${TOKENCOACH_NOTARY_PROFILE:?Set the Keychain notarytool profile name}"
  [[ "$TOKENCOACH_BUILD_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'Set a release VERSION first.' >&2; exit 1; }
  [[ -z "$(git status --porcelain)" ]] || { echo 'Release builds require a clean candidate checkout.' >&2; exit 1; }
  git -c gpg.ssh.allowedSignersFile="$ROOT/allowed_signers" verify-commit "$REVISION"
else
  unset TOKENCOACH_SIGN_IDENTITY
fi
if [[ "$MODE" == release ]]; then
  export TOKENCOACH_MIN_MACOS=14.0
else
  # A development image describes the host baseline; it is not acceptance
  # evidence for the public macOS 14 target.
  export TOKENCOACH_MIN_MACOS="$(sw_vers -productVersion)"
fi
export PYINSTALLER_STRICT_BUNDLE_CODESIGN_ERROR=1
export PYINSTALLER_CONFIG_DIR="$ROOT/build/pyinstaller-cache"
mkdir -p "$ROOT/build"
export TOKENCOACH_BUILD_REVISION="$REVISION"
"$PYTHON" -c 'import json, os; from pathlib import Path; Path("build/build-identity.json").write_text(json.dumps({"revision":os.environ["TOKENCOACH_BUILD_REVISION"], "version":os.environ["TOKENCOACH_BUILD_VERSION"], "dirty":bool(os.popen("git status --porcelain").read().strip())}))'
"$PYTHON" packaging/macos/make-icon.py
"$PYTHON" -m PyInstaller --noconfirm --clean packaging/macos/TokenCoach.spec
APP="$ROOT/dist/TokenCoach.app"
"$PYTHON" packaging/macos/verify-bundle.py "$APP" "$TOKENCOACH_ARCH" "$TOKENCOACH_MIN_MACOS"
# Exercise the packaged interpreter without opening UI or account files.
"$APP/Contents/MacOS/TokenCoach" --version
"$APP/Contents/MacOS/TokenCoach" --bundle-check
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
ditto "$APP" "$STAGE/TokenCoach.app"
ln -s /Applications "$STAGE/Applications"
cp packaging/macos/Install.txt "$STAGE/Read me.txt"
if [[ "$MODE" == release ]]; then
  codesign --verify --deep --strict --verbose=2 "$STAGE/TokenCoach.app"
  ditto -c -k --keepParent "$STAGE/TokenCoach.app" "$ROOT/dist/notarization.zip"
  xcrun notarytool submit "$ROOT/dist/notarization.zip" --keychain-profile "$TOKENCOACH_NOTARY_PROFILE" --wait
  xcrun stapler staple "$STAGE/TokenCoach.app"
  xcrun stapler validate "$STAGE/TokenCoach.app"
  spctl --assess --type execute --verbose=2 "$STAGE/TokenCoach.app"
  NAME="TokenCoach-$TOKENCOACH_BUILD_VERSION-$TOKENCOACH_ARCH"
else
  NAME="TokenCoach-$TOKENCOACH_BUILD_VERSION-$TOKENCOACH_ARCH-DEVELOPMENT"
fi
DMG="$ROOT/dist/$NAME.dmg"
hdiutil create -volname TokenCoach -srcfolder "$STAGE" -ov -format UDZO "$DMG"
if [[ "$MODE" == release ]]; then
  codesign --timestamp --sign "$TOKENCOACH_SIGN_IDENTITY" "$DMG"
  xcrun notarytool submit "$DMG" --keychain-profile "$TOKENCOACH_NOTARY_PROFILE" --wait
  xcrun stapler staple "$DMG"
  xcrun stapler validate "$DMG"
  spctl --assess --type open --context context:primary-signature --verbose=2 "$DMG"
fi
(cd "$ROOT/dist" && shasum -a 256 "$NAME.dmg" > "$NAME.dmg.sha256")
"$PYTHON" -m pip freeze > "$ROOT/dist/$NAME.dependencies.txt"
printf 'Revision: %s\nVersion: %s\nArchitecture: %s\nMode: %s\nMinimum macOS: %s\nBuild OS: %s\n' "$REVISION" "$TOKENCOACH_BUILD_VERSION" "$TOKENCOACH_ARCH" "$MODE" "$TOKENCOACH_MIN_MACOS" "$(sw_vers -productVersion)" > "$ROOT/dist/$NAME.build.txt"
echo "Built $DMG; clean-Mac acceptance is still required."
