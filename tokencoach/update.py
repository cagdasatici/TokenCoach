"""Silent auto-update via git, limited to commits signed by a trusted key.

The app holds browser cookies and runs inside every Claude Code prompt (the
nudge hook), so a push to the repository must not be enough to run code on an
install. An update only moves to a `main` commit whose SSH signature verifies
against `allowed_signers` in the copy already installed: a pushed change can't
vouch for itself, and a key change has to be signed by a key trusted before it.
"""

import os
import re
import subprocess
import sys
import tempfile

from tokencoach.config import LAUNCH_AGENT_LABEL, log

SIGNERS_FILE = "allowed_signers"


def _signed_by_trusted_key(run, install_dir: str, commit: str) -> bool:
    """True if `commit` carries a good SSH signature from a key listed in the
    installed checkout's allowed_signers file (read before any update)."""
    signers = os.path.join(install_dir, SIGNERS_FILE)
    if not os.path.isfile(signers):
        log.warning("auto-update skipped: %s is missing, so no update can be trusted", SIGNERS_FILE)
        return False
    r = run(["git", "-c", f"gpg.ssh.allowedSignersFile={signers}",
             "log", "-1", "--format=%G?", commit])
    return r.returncode == 0 and r.stdout.strip() == "G"


def _check_and_apply_update(install_dir: str | None = None) -> bool:
    """Check for a signed update via git and apply it if there is one. Returns True if updated."""
    from tokencoach.runtime import bundled
    if bundled():
        return False  # Signed bundles are replaced from a verified DMG.
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
        if not _signed_by_trusted_key(run, install_dir, remote):
            log.warning("auto-update skipped: %s is not signed by a key in %s", remote[:8], SIGNERS_FILE)
            return False
        # Install the verified candidate's dependencies before moving HEAD. On
        # failure the next refresh can retry, instead of restarting incomplete code.
        venv_pip = os.path.join(install_dir, ".venv", "bin", "pip")
        if os.path.exists(venv_pip):
            requirements = run(["git", "show", f"{remote}:requirements.txt"])
            if requirements.returncode != 0:
                log.warning("auto-update skipped: candidate requirements unavailable")
                return False
            with tempfile.TemporaryDirectory(prefix="tokencoach-update-") as stage:
                path = os.path.join(stage, "requirements.txt")
                with open(path, "w") as f:
                    f.write(requirements.stdout)
                installed = run([venv_pip, "install", "--quiet", "--require-hashes", "-r", path])
                if installed.returncode != 0:
                    log.warning("auto-update skipped: dependency installation failed; will retry")
                    return False
        # Merge the commit that was verified, not whatever origin/main names by now.
        r = run(["git", "merge", "--ff-only", "--quiet", remote])
        if r.returncode != 0:
            log.warning("auto-update merge failed: %s", r.stderr)
            return False
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
