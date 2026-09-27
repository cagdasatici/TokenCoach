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

say()  { printf '  %s\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m  %s\n' "$1"; }
warn() { printf '  \033[33m⚠\033[0m  %s\n' "$1"; }
die()  { printf '  \033[31m✗\033[0m  %s\n' "$1"; exit 1; }

echo ""
echo "  TokenCoach — installer"
echo "  ──────────────────────"
echo ""

[ "$(uname)" = "Darwin" ] || die "TokenCoach runs on macOS only."

# ── 1. Python 3.10+ and git ──────────────────────────────────────────────────
BASE_PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" &>/dev/null && \
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    BASE_PYTHON="$candidate"; break
  fi
done
[ -n "$BASE_PYTHON" ] || die "Python 3.10+ not found. Install it (brew install python) and re-run."
ok "Python: $($BASE_PYTHON --version)"
command -v git &>/dev/null || die "git not found. Run: xcode-select --install"

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
  pkill -f "$LEGACY_DIR/claude_bar.py" 2>/dev/null || true
  pkill -f "$LEGACY_DIR/tokencoach.py" 2>/dev/null || true
  pkill -x AIQuotaBarHost 2>/dev/null || true
  pkill -f AIQuotaBarWidgetExtension 2>/dev/null || true
  LSREGISTER=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
  [ -d /Applications/AIQuotaBarHost.app ] && "$LSREGISTER" -u /Applications/AIQuotaBarHost.app 2>/dev/null || true
  rm -rf /Applications/AIQuotaBarHost.app "/Applications/Restart AIQuotaLeft.app"
  rm -f "$HOME"/.claude_bar.log* "$HOME/.aiquotaleft_doctor.log" "$HOME/.aiquotaleft_widgethost.log"
  ok "Old launch agents, watchdog and widget removed (your data is kept)"
fi

# ── 3. Get the code ──────────────────────────────────────────────────────────
if [ -d "$INSTALL_DIR/.git" ]; then
  say "↻  Updating $INSTALL_DIR…"
  git -C "$INSTALL_DIR" fetch --quiet origin
  git -C "$INSTALL_DIR" checkout --quiet "$REF" 2>/dev/null || true
  git -C "$INSTALL_DIR" merge --ff-only --quiet "origin/$REF" 2>/dev/null || \
    git -C "$INSTALL_DIR" reset --quiet --hard "origin/$REF"
else
  say "↓  Downloading TokenCoach…"
  rm -rf "$INSTALL_DIR"
  git clone --quiet --depth 1 --branch "$REF" "$REPO" "$INSTALL_DIR"
fi
ok "Code: $INSTALL_DIR ($(git -C "$INSTALL_DIR" rev-parse --short HEAD))"

# ── 4. Virtual environment ───────────────────────────────────────────────────
[ -d "$VENV_DIR" ] || "$BASE_PYTHON" -m venv "$VENV_DIR"
PYTHON="$VENV_DIR/bin/python3"
say "↓  Installing Python dependencies (first run takes a minute)…"
"$PYTHON" -m pip install --quiet --disable-pip-version-check --upgrade pip
"$PYTHON" -m pip install --quiet --disable-pip-version-check --upgrade -r "$INSTALL_DIR/requirements.txt"
# rumps notifications need a bundle identifier next to the interpreter
[ -f "$VENV_DIR/bin/Info.plist" ] || \
  /usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string $LABEL" "$VENV_DIR/bin/Info.plist" >/dev/null
ok "Dependencies installed"

# Import once: this also moves data from pre-rename folders into
# ~/Library/Application Support/TokenCoach, before anything else touches it.
( cd "$INSTALL_DIR" && "$PYTHON" -c "import tokencoach.config, tokencoach.ledger, tokencoach.ui" ) \
  || die "TokenCoach failed to import — see the error above."
ok "Self-check passed"

if [ "$NO_LAUNCH" = "1" ]; then
  ok "Files installed (TOKENCOACH_NO_LAUNCH=1: nothing started)"
  exit 0
fi

# ── 5. Start at login ────────────────────────────────────────────────────────
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
pkill -f "$INSTALL_DIR/tokencoach.py" 2>/dev/null || true
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
  pgrep -f "$INSTALL_DIR/tokencoach.py" >/dev/null && break
  sleep 1
done
pgrep -f "$INSTALL_DIR/tokencoach.py" >/dev/null && ok "Running — look for the ◆ in your menu bar" \
  || warn "Not running yet. Check $LOG_DIR/tokencoach.log"

echo ""
echo "  Your dashboard opens from the menu bar icon → Open dashboard."
echo "  Uninstall any time: bash $INSTALL_DIR/uninstall.sh"
echo ""
echo "  TokenCoach is built on AIQuotaBar by Toprak Yagcioglu:"
echo "  https://github.com/yagcioglutoprak/AIQuotaBar"
echo ""
