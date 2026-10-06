#!/bin/bash
# Build the TokenCoach WidgetKit widget
# Requires: Xcode 15+, macOS 14+

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
BUILD_DIR="$PROJECT_DIR/build"
APP_NAME="TokenCoachWidget.app"

# Replacing the bundle does not retire an extension already hosted by
# WidgetKit. That process can keep serving the previous build's timeline even
# after the new host asks for a reload. Stop only this installed extension;
# the host's reload below lets WidgetKit launch the newly installed build.
retire_installed_extension() {
    local executable="$1/Contents/PlugIns/TokenCoachWidgetExtension.appex/Contents/MacOS/TokenCoachWidgetExtension"
    ps -Ao pid=,comm= | awk -v p="$executable" '$2 == p {print $1}' |
        while read -r pid; do
            kill "$pid" 2>/dev/null || true
        done
}

echo ""
echo "  TokenCoach Widget — builder"
echo "  ───────────────────────────"
echo ""

# ── Check Xcode ──────────────────────────────────────────────────────────────
if ! command -v xcodebuild &>/dev/null; then
    echo "  ✗  Xcode not found. Install from the App Store."
    echo "     The widget is optional — the menu bar app works without it."
    exit 1
fi

XCODE_VER=$(xcodebuild -version 2>/dev/null | head -1 | awk '{print $2}')
echo "  ✓  Xcode: $XCODE_VER"

# ── Check for project ────────────────────────────────────────────────────────
if [ ! -d "$PROJECT_DIR/TokenCoachWidget.xcodeproj" ]; then
    echo ""
    echo "  ✗  No Xcode project found."
    echo ""
    echo "  To create the project:"
    echo "    1. Open Xcode → File → New → Project"
    echo "    2. Choose macOS → App"
    echo "    3. Product Name: TokenCoachWidget"
    echo "    4. Add Widget Extension target: TokenCoachWidgetExtension"
    echo "    5. Set App Group: group.io.github.cagdasatici.tokencoach on both targets"
    echo "    6. Drag the existing Swift files into the project"
    echo ""
    echo "  Alternatively, open this directory in Xcode and it will"
    echo "  detect the source files automatically."
    echo ""
    echo "  For detailed instructions, see the README."
    exit 1
fi

# ── Build ────────────────────────────────────────────────────────────────────
# Every build must carry a distinct CFBundleVersion. chronod treats an
# extension at an unchanged bundle version as unchanged: it keeps serving its
# cached render and never asks for a new timeline, so a rebuild at the same
# version leaves a stale widget - or, on a freshly placed one, a widget stuck
# on its placeholder forever. Restarting chronod, re-registering, and removing
# and re-adding the widget do not clear it; only a version change does.
# A timestamp is monotonic and always differs, which is what matters here.
BUILD_NUMBER=$(date +%s)

echo "  ↓  Building widget… (build $BUILD_NUMBER)"
xcodebuild \
    -project "$PROJECT_DIR/TokenCoachWidget.xcodeproj" \
    -scheme TokenCoachWidget \
    -configuration Release \
    -derivedDataPath "$BUILD_DIR" \
    CODE_SIGN_IDENTITY="-" \
    CODE_SIGNING_REQUIRED=NO \
    CODE_SIGNING_ALLOWED=NO \
    DEVELOPMENT_TEAM="" \
    CURRENT_PROJECT_VERSION="$BUILD_NUMBER" \
    2>&1 | tail -5

# ── Sign ─────────────────────────────────────────────────────────────────────
# The build above runs with CODE_SIGNING_ALLOWED=NO, which leaves a
# linker-signed bundle carrying no entitlements and the wrong identifier.
# macOS refuses to register a widget extension in that state, so the widget
# never shows up in the picker. Ad-hoc sign both bundles with their real
# entitlements: the extension needs the sandbox exception to read usage.json.
BUILT_APP=$(find "$BUILD_DIR" -name "$APP_NAME" -type d | head -1)
if [ -z "$BUILT_APP" ]; then
    echo "  ✗  Build failed — app bundle not found."
    exit 1
fi

echo "  ↓  Signing…"
BUILT_EXT="$BUILT_APP/Contents/PlugIns/TokenCoachWidgetExtension.appex"
codesign --force --sign - --timestamp=none \
    --entitlements "$PROJECT_DIR/TokenCoachWidgetExtension/TokenCoachWidgetExtension.entitlements" \
    "$BUILT_EXT" >/dev/null 2>&1
codesign --force --sign - --timestamp=none \
    --entitlements "$PROJECT_DIR/TokenCoachWidget/TokenCoachWidget.entitlements" \
    "$BUILT_APP" >/dev/null 2>&1
if ! codesign --verify --deep --strict "$BUILT_APP" 2>/dev/null; then
    echo "  ✗  Signing failed — macOS will not register an unsigned widget."
    exit 1
fi
echo "  ✓  Signed (ad-hoc, with entitlements)"

INSTALL_PATH="/Applications/$APP_NAME"
echo "  ↓  Installing to ${INSTALL_PATH}…"
rm -rf "$INSTALL_PATH"
# ditto, not cp -R: preserves extended attributes so the signature stays intact.
ditto "$BUILT_APP" "$INSTALL_PATH"

# Drop the build-directory copy from LaunchServices. Both copies share the
# bundle id, and if the build copy stays registered the system can host the
# widget from there instead of /Applications - which silently serves stale
# code and makes the installed app look broken.
LSREGISTER=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
"$LSREGISTER" -u "$BUILT_APP" 2>/dev/null || true
"$LSREGISTER" -f "$INSTALL_PATH" 2>/dev/null || true

retire_installed_extension "$INSTALL_PATH"

# Launch, and leave it running. Besides registering the widget, the host
# watches usage.json and asks WidgetKit to refresh when the menu bar app
# writes new data. Quitting it freezes the widget on whatever it last drew:
# a widget's own timeline policy is only a request, and the system throttles
# it into hours.
HOST_LABEL="io.github.cagdasatici.tokencoach.widgethost"
if launchctl print "gui/$(id -u)/$HOST_LABEL" >/dev/null 2>&1; then
    launchctl kickstart -k "gui/$(id -u)/$HOST_LABEL" 2>/dev/null   # restart the supervised copy
else
    open -g -j "$INSTALL_PATH"
fi
sleep 2

echo "  ✓  Widget installed!"
echo ""
echo "  Right-click your desktop → Edit Widgets → search \"TokenCoach\""
echo ""
