"""Silent auto-update via git pull."""

import os
import re
import subprocess
import sys

from tokencoach.config import LAUNCH_AGENT_LABEL, log


def _check_and_apply_update(install_dir: str | None = None) -> bool:
    """Silently check for updates via git and apply if available. Returns True if updated."""
    install_dir = install_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.isdir(os.path.join(install_dir, ".git")):
        return False  # Not a git install (Homebrew, dev, etc.)
    try:
        run = lambda cmd: subprocess.run(
            cmd, cwd=install_dir, capture_output=True, text=True, timeout=30
        )
        r = run(["git", "fetch", "--quiet", "origin"])
        if r.returncode != 0:
            return False
        local = run(["git", "rev-parse", "HEAD"]).stdout.strip()
        remote = run(["git", "rev-parse", "origin/main"]).stdout.strip()
        if local == remote:
            return False  # Already up to date
        # Only move a clean checkout of main that is simply behind. Anything
        # else is someone's working copy: leave their branch and edits alone.
        branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
        dirty = run(["git", "status", "--porcelain", "--untracked-files=no"]).stdout.strip()
        behind = run(["git", "merge-base", "--is-ancestor", "HEAD", "origin/main"]).returncode == 0
        if branch != "main" or dirty or not behind:
            log.info("auto-update skipped: local changes or not a plain main checkout")
            return False
        r = run(["git", "merge", "--ff-only", "origin/main", "--quiet"])
        if r.returncode != 0:
            log.warning("auto-update merge failed: %s", r.stderr)
            return False
        venv_pip = os.path.join(install_dir, ".venv", "bin", "pip")
        if os.path.exists(venv_pip):
            run([venv_pip, "install", "--quiet", "-r",
                 os.path.join(install_dir, "requirements.txt")])
        log.info("auto-update applied: %s → %s", local[:8], remote[:8])
        return True
    except Exception:
        log.debug("auto-update check failed", exc_info=True)
        return False


def _restart_app():
    """Restart in a fresh process after an update.

    Never os.execv: it keeps the pid, and on macOS 26 the re-exec'd process's
    status item stays hidden, so the menu bar icon vanishes.
    """
    supervised = False
    try:
        job = subprocess.run(
            ["launchctl", "list", LAUNCH_AGENT_LABEL],
            capture_output=True, text=True, timeout=5,
        )
        match = re.search(r'"PID"\s*=\s*(\d+);', job.stdout) if job.returncode == 0 else None
        supervised = bool(match) and int(match.group(1)) == os.getpid()
        if supervised:
            log.info("restarting after auto-update via launchd")
            result = subprocess.run(
                ["launchctl", "kickstart", "-k",
                 f"gui/{os.getuid()}/{LAUNCH_AGENT_LABEL}"],
                capture_output=True, timeout=15,
            )
            if result.returncode == 0:
                # kickstart starts a new process; do not leave this AppKit
                # process running if launchctl returns before killing it.
                os._exit(0)
                return
            log.warning("launchd restart failed: %s", result.stderr.decode(errors="replace"))
    except (OSError, subprocess.TimeoutExpired):
        log.debug("launchd restart unavailable", exc_info=True)
    if supervised:
        # Exit non-zero so launchd respawns us, including under older
        # plists that only restart after an unsuccessful exit.
        os._exit(1)
        return
    # Manual launches have no supervising job: start a new copy, then leave.
    log.info("restarting after auto-update in a new process")
    subprocess.Popen([sys.executable] + sys.argv, stdin=subprocess.DEVNULL,
                     start_new_session=True)
    os._exit(0)
