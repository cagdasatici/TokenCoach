#!/bin/bash
# TokenCoach — one-line installer (macOS)
#   curl -fsSL https://raw.githubusercontent.com/cagdasatici/TokenCoach/main/install.sh | bash
#
# Safe to run again: it updates an existing install in place. It also moves an
# install made before the rename to TokenCoach (see "pre-rename installs").
#
# Environment (all optional):
#   TOKENCOACH_DIR        install folder            (default ~/.tokencoach)
#   TOKENCOACH_REPO       git URL or local path     (default the GitHub repo)
#   TOKENCOACH_REF        branch or tag             (default main)
#   TOKENCOACH_NO_LAUNCH  1 = install files only: no login agent, watchdog,
#                         widget, Claude Code hook or launch (used by tests)

set -e

REPO="${TOKENCOACH_REPO:-https://github.com/cagdasatici/TokenCoach}"
REF="${TOKENCOACH_REF:-main}"
INSTALL_DIR="${TOKENCOACH_DIR:-$HOME/.tokencoach}"
VENV_DIR="$INSTALL_DIR/.venv"
LABEL="io.github.cagdasatici.tokencoach"
AGENTS="$HOME/Library/LaunchAgents"
PLIST="$AGENTS/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs/TokenCoach"
UID_NUM=$(id -u)
NO_LAUNCH="${TOKENCOACH_NO_LAUNCH:-0}"

# PIDs of the menu bar app itself: a Python process whose command line is
# exactly "<python> <script>". Never match on a substring: shells, editors,
# `tail` and `tokencoach.py --demo` mention the same path and must be left alone.
app_pids() { ps -Ao pid=,args= | awk -v s="$1" '$3 == s && NF == 3 && $2 ~ /[Pp]ython[0-9.]*$/ {print $1}'; }
say()  { printf '  %s\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m  %s\n' "$1"; }
warn() { printf '  \033[33m⚠\033[0m  %s\n' "$1"; }
die()  { DIED=1; printf '\n  \033[31m✗\033[0m  %s\n\n' "$1"; exit 1; }
step() { printf '\n  \033[1m[%s/%s] %s\033[0m\n' "$1" "$TOTAL" "$2"; }
TOTAL=4
[ "$NO_LAUNCH" = "1" ] && TOTAL=3
# Plain-language message instead of a raw error if anything unexpected fails.
trap 'rc=$?; [ $rc -ne 0 ] && [ -z "$DIED" ] && printf "\n  \033[31m✗\033[0m  The install stopped early. Nothing is broken: run the same command again.\n  If it keeps failing, see https://github.com/cagdasatici/TokenCoach#troubleshooting\n\n"' EXIT

echo ""
echo "  TokenCoach — installer"
echo "  ──────────────────────"
echo ""

step 1 "Checking your Mac…"
[ "$(uname)" = "Darwin" ] || die "TokenCoach is a Mac menu bar app and can only be installed on macOS."
[ -n "$HOME" ] && [ -w "$HOME" ] || die "Your home folder is not writable, so TokenCoach cannot install. Run this from your normal Mac user account."

# ── 1. Python 3.10+ and git ──────────────────────────────────────────────────
BASE_PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" &>/dev/null && \
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    BASE_PYTHON="$candidate"; break
  fi
done
[ -n "$BASE_PYTHON" ] || die "TokenCoach needs Python 3.10 or newer, and this Mac does not have it.
     Fix: download the macOS installer from https://www.python.org/downloads/macos/
     (or run: brew install python), then run the install command again."
ok "Python: $($BASE_PYTHON --version)"
command -v git &>/dev/null || die "TokenCoach needs git, which comes with Apple's command line tools.
     Fix: run  xcode-select --install  , click Install in the window that appears,
     wait for it to finish, then run the install command again."

# ── 2. Pre-rename installs: stop and remove the old moving parts ─────────────
# TokenCoach began as a fork of AIQuotaBar and was briefly called AIQuotaLeft.
# Those installs lived in ~/.ai-quota-bar with their own launch agents, a cron
# watchdog and a widget host. Stop them first so nothing restarts the old app
# while its data is being moved.
LEGACY_DIR="$HOME/.ai-quota-bar"
LEGACY_LABELS="com.claudebar com.aiquotaleft.doctor com.aiquotaleft.widgethost"
legacy_found=false
for l in $LEGACY_LABELS; do [ -f "$AGENTS/$l.plist" ] && legacy_found=true; done
[ -d "$LEGACY_DIR" ] && legacy_found=true
if [ "$legacy_found" = true ] && [ "$NO_LAUNCH" != "1" ]; then
  say "↻  Moving your existing install to TokenCoach…"
  if crontab -l 2>/dev/null | grep -q "aiquotaleft-doctor.sh"; then
    crontab -l 2>/dev/null | grep -v "aiquotaleft-doctor.sh" | crontab - || true
  fi
  for l in $LEGACY_LABELS; do
    launchctl bootout "gui/$UID_NUM/$l" 2>/dev/null || true
    rm -f "$AGENTS/$l.plist"
  done
  for s in "$LEGACY_DIR/claude_bar.py" "$LEGACY_DIR/tokencoach.py"; do
    app_pids "$s" | xargs kill 2>/dev/null || true
  done
  pkill -x AIQuotaBarHost 2>/dev/null || true
  ps -Ao pid=,comm= | awk '$2 ~ /AIQuotaBarWidgetExtension$/ {print $1}' | xargs kill 2>/dev/null || true
  LSREGISTER=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
  [ -d /Applications/AIQuotaBarHost.app ] && "$LSREGISTER" -u /Applications/AIQuotaBarHost.app 2>/dev/null || true
  rm -rf /Applications/AIQuotaBarHost.app "/Applications/Restart AIQuotaLeft.app"
  rm -f "$HOME"/.claude_bar.log* "$HOME/.aiquotaleft_doctor.log" "$HOME/.aiquotaleft_widgethost.log"
  ok "Old launch agents, watchdog and widget removed (your data is kept)"
fi

# ── 3. Get the code ──────────────────────────────────────────────────────────
step 2 "Downloading TokenCoach…"
if [ -d "$INSTALL_DIR/.git" ]; then
  say "↻  Updating $INSTALL_DIR…"
  git -C "$INSTALL_DIR" fetch --quiet origin
  git -C "$INSTALL_DIR" checkout --quiet "$REF" 2>/dev/null || true
  git -C "$INSTALL_DIR" merge --ff-only --quiet "origin/$REF" 2>/dev/null || \
    git -C "$INSTALL_DIR" reset --quiet --hard "origin/$REF"
else
  say "↓  Downloading TokenCoach…"
  rm -rf "$INSTALL_DIR"
  git clone --quiet --depth 1 --branch "$REF" "$REPO" "$INSTALL_DIR" \
    || die "Could not download TokenCoach. Check that you are online, then run the install command again."
fi
ok "Code: $INSTALL_DIR ($(git -C "$INSTALL_DIR" rev-parse --short HEAD))"

# ── 4. Virtual environment ───────────────────────────────────────────────────
step 3 "Setting it up (about a minute)…"
[ -d "$VENV_DIR" ] || "$BASE_PYTHON" -m venv "$VENV_DIR" \
  || die "Could not create TokenCoach's private Python environment. Check that your disk is not full, then run the install command again."
PYTHON="$VENV_DIR/bin/python3"
say "↓  Installing Python dependencies (first run takes a minute)…"
"$PYTHON" -m pip install --quiet --disable-pip-version-check --upgrade pip
"$PYTHON" -m pip install --quiet --disable-pip-version-check --require-hashes -r "$INSTALL_DIR/requirements.txt" \
  || die "Could not download TokenCoach's components. Check that you are online, then run the install command again."
# rumps notifications need a bundle identifier next to the interpreter
[ -f "$VENV_DIR/bin/Info.plist" ] || \
  /usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string $LABEL" "$VENV_DIR/bin/Info.plist" >/dev/null
ok "Dependencies installed"

# Import once: this also moves data from pre-rename folders into
# ~/Library/Application Support/TokenCoach, before anything else touches it.
( cd "$INSTALL_DIR" && "$PYTHON" -c "import tokencoach.config, tokencoach.ledger, tokencoach.ui" ) \
  || die "TokenCoach installed but failed its self-check. The error above is what to include if you report it."
ok "Self-check passed"

if [ "$NO_LAUNCH" = "1" ]; then
  ok "Files installed (TOKENCOACH_NO_LAUNCH=1: nothing started)"
  trap - EXIT
  exit 0
fi

# ── 5. Start at login ────────────────────────────────────────────────────────
step 4 "Starting TokenCoach…"
mkdir -p "$AGENTS" "$LOG_DIR"
cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$INSTALL_DIR/tokencoach.py</string>
    </array>
    <key>RunAtLoad</key><true/>
    <!-- Restart on any exit; Quit unloads the job first. -->
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$LOG_DIR/tokencoach.log</string>
    <key>StandardErrorPath</key><string>$LOG_DIR/tokencoach.log</string>
</dict>
</plist>
PLIST_EOF
app_pids "$INSTALL_DIR/tokencoach.py" | xargs kill 2>/dev/null || true
launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
sleep 1
launchctl bootstrap "gui/$UID_NUM" "$PLIST" 2>/dev/null || launchctl kickstart -k "gui/$UID_NUM/$LABEL" 2>/dev/null || true
ok "Starts at login"

# ── 6. Claude Code nudges (re-point an existing hook at this install) ────────
( cd "$INSTALL_DIR" && "$PYTHON" -c "
from tokencoach import nudge
if nudge.is_installed():
    nudge.install('$INSTALL_DIR')
" ) 2>/dev/null || true

# ── 7. Desktop widget (optional, needs Xcode) ────────────────────────────────
if command -v xcodebuild &>/dev/null && xcodebuild -version &>/dev/null; then
  say "↓  Building the desktop widget…"
  if bash "$INSTALL_DIR/widget/build_widget.sh" >/dev/null 2>&1; then
    ok "Widget installed — right-click the desktop → Edit Widgets → TokenCoach"
  else
    warn "Widget build failed (optional; the app works without it)"
  fi
else
  say "⊘  Widget skipped (needs Xcode). Later: bash $INSTALL_DIR/widget/build_widget.sh"
fi

# ── 8. Health check, watchdog and Dock launcher ──────────────────────────────
bash "$INSTALL_DIR/tokencoach-doctor.sh" >/dev/null 2>&1 || true
bash "$INSTALL_DIR/make_dock_launcher.sh" >/dev/null 2>&1 || true

# ── 9. Remove the pre-rename folder last ─────────────────────────────────────
if [ -d "$LEGACY_DIR" ] && [ "$LEGACY_DIR" != "$INSTALL_DIR" ]; then
  rm -rf "$LEGACY_DIR"
fi

for _ in 1 2 3 4 5 6 7 8 9 10; do
  [ -n "$(app_pids "$INSTALL_DIR/tokencoach.py")" ] && break
  sleep 1
done
RUNNING=false
[ -n "$(app_pids "$INSTALL_DIR/tokencoach.py")" ] && RUNNING=true

echo ""
if [ "$RUNNING" = true ]; then
  echo "  ✅ TokenCoach is installed and running."
  echo ""
  echo "  What to do now:"
  echo "    1. Look at the top-right of your screen, in the menu bar, for the ◆ symbol."
  echo "    2. A short setup guide opens by itself. Click \"Get started\", then"
  echo "       \"Sign in to Claude…\" to see your remaining quota."
  echo "       (Not there? Click ◆ and choose Setup Guide… in the settings menu.)"
else
  warn "Installed, but not running yet. Open $LOG_DIR/tokencoach.log to see why,"
  say "   or run: bash $INSTALL_DIR/tokencoach-doctor.sh"
fi
echo ""
echo "  Uninstall any time: bash $INSTALL_DIR/uninstall.sh"
echo ""
echo "  TokenCoach is built on AIQuotaBar by Toprak Yagcioglu:"
echo "  https://github.com/yagcioglutoprak/AIQuotaBar"
echo ""
