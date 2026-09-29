#!/bin/bash
# TokenCoach — uninstaller. Removes the app, its launch agents, watchdog,
# widget, Dock launcher and Claude Code hook.
#
#   bash ~/.tokencoach/uninstall.sh            keep your data (ledger, lessons, config)
#   bash ~/.tokencoach/uninstall.sh --purge    also delete your data
#
# Lessons you applied stay in your CLAUDE.md / AGENTS.md files inside a marked
# "TokenCoach lessons" block; remove them from the dashboard before
# uninstalling, or delete that block by hand.

INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
PURGE=false; [ "$1" = "--purge" ] && PURGE=true
AGENTS="$HOME/Library/LaunchAgents"
UID_NUM=$(id -u)
BASE="io.github.cagdasatici.tokencoach"

echo ""
echo "  TokenCoach — uninstall"
echo ""

# Claude Code hook first, while the code that knows how to remove it exists.
if [ -x "$INSTALL_DIR/.venv/bin/python3" ]; then
  ( cd "$INSTALL_DIR" && "$INSTALL_DIR/.venv/bin/python3" -c "
from tokencoach import nudge
if nudge.is_installed():
    nudge.uninstall()
    print('  ✓  Claude Code nudge hook removed (settings backup kept)')
" ) 2>/dev/null || true
  # git hooks added by --yield-install (commit history and the repository list stay in the data folder)
  ( cd "$INSTALL_DIR" && "$INSTALL_DIR/.venv/bin/python3" -c "
from tokencoach import ledger, yield_metrics
conn = ledger.open_ledger()
for repo in yield_metrics.remove_hooks(conn):
    print('  ✓  Git hook removed from ' + repo)
" ) 2>/dev/null || true
fi

if crontab -l 2>/dev/null | grep -q "tokencoach-doctor.sh"; then
  crontab -l 2>/dev/null | grep -v "tokencoach-doctor.sh" | crontab - || true
fi
for l in "$BASE.doctor" "$BASE.widgethost" "$BASE"; do
  launchctl bootout "gui/$UID_NUM/$l" 2>/dev/null || true
  rm -f "$AGENTS/$l.plist"
done
ps -Ao pid=,args= | awk -v s="$INSTALL_DIR/tokencoach.py" '$3 == s && $2 ~ /[Pp]ython[0-9.]*$/ {print $1}' | xargs kill 2>/dev/null || true
pkill -x TokenCoachWidget 2>/dev/null || true
echo "  ✓  Stopped and removed launch agents and watchdog"

LSREGISTER=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
if [ -d /Applications/TokenCoachWidget.app ]; then
  "$LSREGISTER" -u /Applications/TokenCoachWidget.app 2>/dev/null || true
  rm -rf /Applications/TokenCoachWidget.app
  echo "  ✓  Widget removed"
fi
rm -rf "/Applications/Restart TokenCoach.app"

if [ "$PURGE" = true ]; then
  rm -rf "$HOME/Library/Application Support/TokenCoach" "$HOME/Library/Logs/TokenCoach"
  echo "  ✓  Data and logs deleted"
else
  echo "  ·  Data kept in ~/Library/Application Support/TokenCoach (use --purge to delete)"
fi

case "$INSTALL_DIR" in
  "$HOME/.tokencoach") rm -rf "$INSTALL_DIR"; echo "  ✓  Removed $INSTALL_DIR" ;;
  *) echo "  ·  Left the code in $INSTALL_DIR (not the default install folder)" ;;
esac
echo ""
