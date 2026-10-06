"""Packaged-app lifecycle helpers. No credentials or account access."""
import os
import sys
from pathlib import Path


def bundled():
    return bool(getattr(sys, "frozen", False))


def app_bundle():
    return Path(sys.executable).resolve().parents[2] if bundled() else None


def launch_args():
    if bundled():
        return [sys.executable]
    from tokencoach.config import install_python
    root = Path(__file__).resolve().parent.parent
    return [install_python(str(root)), str(root / "tokencoach.py")]


def acquire_instance(wait=0):
    """Hold an owner-only advisory lock until process exit. CLI/hooks skip it."""
    import fcntl
    from tokencoach.config import APP_SUPPORT
    os.makedirs(APP_SUPPORT, mode=0o700, exist_ok=True)
    fd = os.open(os.path.join(APP_SUPPORT, "app.lock"), os.O_CREAT | os.O_RDWR, 0o600)
    import time
    deadline = time.monotonic() + wait
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BlockingIOError:
            if time.monotonic() >= deadline:
                os.close(fd)
                return None
            time.sleep(0.1)


def remove_background_agents(stop_main=True):
    """Retire only TokenCoach agents and its exact doctor cron entry; keep data."""
    import subprocess
    from tokencoach.config import LAUNCH_AGENT_LABEL, LAUNCH_AGENT_PLIST
    for suffix in (".doctor", ".widgethost", ""):
        label = LAUNCH_AGENT_LABEL + suffix
        path = Path(LAUNCH_AGENT_PLIST) if not suffix else Path(LAUNCH_AGENT_PLIST).with_name(label + ".plist")
        path.unlink(missing_ok=True)
        if suffix or stop_main:
            subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{label}"], capture_output=True)
    cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if cron.returncode == 0:
        lines = cron.stdout.splitlines(keepends=True)
        # Only the command the script installer owns; don't match arbitrary
        # user entries merely mentioning the name in comments or arguments.
        doctor = str(Path.home() / ".tokencoach/tokencoach-doctor.sh")
        owned = "*/2 * * * * /bin/bash " + doctor + " >> " + str(Path.home() / "Library/Logs/TokenCoach/doctor.log") + " 2>&1"
        kept = [line for line in lines if line.strip() != owned]
        if kept != lines:
            subprocess.run(["crontab", "-"], input="".join(kept), text=True, check=True)


def prepare_bundle():
    """Require installation off the disk image and ask before replacing agents."""
    if not bundled():
        return True
    import plistlib
    import rumps
    from tokencoach.config import LAUNCH_AGENT_PLIST
    bundle = app_bundle()
    if bundle.parent.name != "Applications" or str(bundle).startswith("/Volumes/"):
        rumps.alert(title="Install TokenCoach", message="Drag TokenCoach into Applications, eject the disk image, then open TokenCoach from Applications.")
        return False
    try:
        with open(LAUNCH_AGENT_PLIST, "rb") as f:
            args = plistlib.load(f).get("ProgramArguments")
    except FileNotFoundError:
        args = None
    except (OSError, plistlib.InvalidFileException):
        rumps.alert(title="Existing login item needs review", message="TokenCoach could not read its existing login item. Keep your previous installation until this is resolved.")
        return False
    if args and args != launch_args():
        if rumps.alert(title="Use this TokenCoach installation?", message=(
            "An existing script or Homebrew login item was found. Stop its TokenCoach background "
            "agents and use this app instead? Your history, settings and lessons stay. "
            "Its prompt and existing opt-in git hooks will point to this app. The optional widget host will stop. "
            "You can enable Launch at Login from this app's Settings."
        ), ok="Use this app", cancel="Cancel") != 1:
            return False
        remove_background_agents()
        # Repoint existing opt-in hooks; never create a hook where one was
        # removed or replace a hook the repository owner changed.
        from tokencoach import ledger, trailer, yield_metrics
        conn = ledger.open_ledger()
        failures = 0
        try:
            for repo in yield_metrics.registered(conn):
                if not Path(repo["path"]).exists():
                    continue
                try:
                    where = trailer.locate(repo["path"])
                    if where["ours"]:
                        trailer.install_repo(repo["path"])
                except (trailer.TrailerError, OSError):
                    failures += 1
        finally:
            conn.close()
        if failures:
            rumps.alert(title="Some git hooks need attention", message="An existing tracked repository hook could not be moved. Keep the previous installation until you resolve repository access; the core app can still run.")
    return True
