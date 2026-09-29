"""Tag commits made by Claude Code with the session that made them.

Git runs `prepare-commit-msg` before a commit message is finalised. Inside a
Claude Code session the shell has CLAUDECODE and CLAUDE_CODE_SESSION_ID set, so
a commit made by Claude gets a `Claude-Session: <id>` trailer and a commit made
by hand in a terminal does not. TokenCoach joins that id to the ledger to show
what a session's spend produced.

Standard library only, and silent on any failure: a broken hook must never get
in the way of a commit.
"""

import os
import re
import subprocess
import sys

TRAILER_KEY = "Claude-Session"
# A UUID today; accept any short plain identifier but nothing that could smuggle
# extra lines or shell syntax into a commit message.
_SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{6,79}")


def session_id(env) -> str | None:
    """The Claude Code session this process runs in, or None outside one."""
    if not env.get("CLAUDECODE"):
        return None
    sid = env.get("CLAUDE_CODE_SESSION_ID") or ""
    return sid if _SESSION_ID.fullmatch(sid) else None


def main(argv=None, env=None) -> None:
    """The prepare-commit-msg hook: argv is git's (message file, source, sha)."""
    try:
        argv = sys.argv[1:] if argv is None else argv
        env = os.environ if env is None else env
        if not argv or (len(argv) > 1 and argv[1] in ("merge", "squash")):
            return
        sid = session_id(env)
        if not sid:
            return
        subprocess.run(
            ["git", "interpret-trailers", "--in-place", "--if-exists", "doNothing",
             "--trailer", f"{TRAILER_KEY}: {sid}", argv[0]],
            capture_output=True, timeout=10, check=False)
    except Exception:
        pass                                    # never interfere with a commit


# ── install / uninstall in a repository ─────────────────────────────────────

HOOK_NAME = "prepare-commit-msg"
HOOK_MARKER = "# tokencoach-managed: Claude-Session trailer"


class TrailerError(Exception):
    """The hook can't be installed here; the message says why."""


def _git(path: str, *args: str) -> str:
    r = subprocess.run(["git", "-C", path, *args], capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise TrailerError(f"{path} is not inside a git repository")
    return r.stdout.strip()


def _inside(child: str, parent: str) -> bool:
    return child == parent or child.startswith(parent.rstrip(os.sep) + os.sep)


def locate(path: str) -> dict:
    """The main worktree, the hook file git will run there, and whether it is
    ours. Works from any linked worktree: hooks live in the shared git folder."""
    path = os.path.realpath(os.path.expanduser(path))
    if not os.path.isdir(path):
        raise TrailerError(f"{path} is not a folder")
    common = os.path.realpath(_git(path, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    top = os.path.realpath(_git(path, "rev-parse", "--show-toplevel"))
    hooks = os.path.realpath(_git(path, "rev-parse", "--path-format=absolute", "--git-path", "hooks"))
    main = os.path.dirname(common) if os.path.basename(common) == ".git" else top
    if not _inside(hooks, common):
        # core.hooksPath points at a folder that isn't this repository's own: one shared by
        # other repositories (a global setting), or tracked inside the project. Either way
        # installing or removing here would reach beyond this repository.
        raise TrailerError(f"this repository's git hooks live outside its .git folder ({hooks}); "
                           "add the hook there by hand instead")
    hook = os.path.join(hooks, HOOK_NAME)
    ours = False
    if os.path.exists(hook):
        try:
            with open(hook, encoding="utf-8") as f:
                ours = HOOK_MARKER in f.read()
        except (OSError, UnicodeDecodeError):
            pass
    return {"repo": main, "git_dir": common, "hook": hook, "exists": os.path.exists(hook), "ours": ours}


def hook_script(install_dir: str) -> str:
    import shlex
    py = os.path.join(install_dir, ".venv", "bin", "python3")
    if not os.path.exists(py):
        py = sys.executable
    return (
        "#!/bin/sh\n"
        f"{HOOK_MARKER} (remove with: tokencoach --yield-remove)\n"
        "# Tags commits made inside Claude Code with their session. Does nothing for\n"
        "# commits made in a terminal, and never stops a commit.\n"
        '[ -n "$CLAUDECODE" ] && [ -n "$CLAUDE_CODE_SESSION_ID" ] || exit 0\n'
        f"PYTHONPATH={shlex.quote(install_dir)} {shlex.quote(py)} -m tokencoach.trailer \"$@\" "
        ">/dev/null 2>&1\n"
        "exit 0\n"
    )


def install_repo(path: str, install_dir: str | None = None) -> dict:
    """Install the hook. Refuses to touch a hook that isn't ours."""
    where = locate(path)
    if where["exists"] and not where["ours"]:
        raise TrailerError(
            f"{where['hook']} already exists and isn't TokenCoach's. To keep both, add this line to it:\n"
            f"  [ -n \"$CLAUDE_CODE_SESSION_ID\" ] && git interpret-trailers --in-place "
            f"--if-exists doNothing --trailer \"{TRAILER_KEY}: $CLAUDE_CODE_SESSION_ID\" \"$1\"")
    install_dir = install_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(os.path.dirname(where["hook"]), exist_ok=True)
    tmp = where["hook"] + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(hook_script(install_dir))
    os.chmod(tmp, 0o755)
    os.replace(tmp, where["hook"])
    return {"repo": where["repo"], "hook": where["hook"]}


def uninstall_repo(path: str) -> bool:
    """Remove our hook; someone else's is left alone. Returns whether we removed one."""
    where = locate(path)
    if where["ours"]:
        os.remove(where["hook"])
        return True
    return False


def is_installed(path: str) -> bool:
    try:
        return locate(path)["ours"]
    except (TrailerError, OSError, subprocess.SubprocessError):
        return False


if __name__ == "__main__":
    main()
