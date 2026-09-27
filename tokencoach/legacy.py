"""Finish moving an install made before the rename to TokenCoach.

Installs from before the rename live in ~/.ai-quota-bar and start from the
com.claudebar LaunchAgent. Their auto-updater pulls this code into that old
folder and keeps running it, so on start-up we hand over to install.sh, which
sets up ~/.tokencoach and its agents, then removes the old ones (stopping this
process, which the new agent replaces). Until then the app runs normally.
"""

import os
import subprocess
import time

from tokencoach.config import APP_SUPPORT, LOG_FILE, log

LEGACY_DIR = os.path.expanduser("~/.ai-quota-bar")
LEGACY_PLIST = os.path.expanduser("~/Library/LaunchAgents/com.claudebar.plist")
MARKER = os.path.join(APP_SUPPORT, "legacy-migration-started")
RETRY_AFTER = 24 * 3600


def is_legacy_install(root: str) -> bool:
    return os.path.realpath(root) == os.path.realpath(LEGACY_DIR) or os.path.exists(LEGACY_PLIST)


def finish_legacy_install(root: str) -> bool:
    """Start the one-time move if this is a pre-rename install. Returns True
    when the caller must not register its own login item (the installer does)."""
    if not is_legacy_install(root):
        return False
    try:
        if os.path.exists(MARKER) and time.time() - os.path.getmtime(MARKER) < RETRY_AFTER:
            return True
        installer = os.path.join(root, "install.sh")
        if not os.path.exists(installer):
            return True
        with open(MARKER, "w") as f:
            f.write(str(time.time()))
        out = open(LOG_FILE, "a")
        subprocess.Popen(["/bin/bash", installer], stdout=out, stderr=out, stdin=subprocess.DEVNULL,
                         env={**os.environ, "TOKENCOACH_MIGRATING": "1"}, start_new_session=True)
        log.info("pre-rename install found in %s: started install.sh to move it", root)
    except OSError:
        log.exception("could not start the move from the pre-rename install")
    return True
