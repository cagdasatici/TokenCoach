"""Login agent and hook interpreter paths across upgrades. Temp folders only.

Found on the mini (path C): after `brew upgrade` from 1.1.0 the login agent
still pointed at Cellar/tokencoach/1.1.0, which the upgrade deleted, so the
app no longer started at login; the nudge hook had the same stale path.
"""
import os as _os
import tempfile as _tempfile

_os.environ.setdefault("TOKENCOACH_DATA_DIR", _tempfile.mkdtemp(prefix="tokencoach-test-"))

import os
import pathlib
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


def make_venv(root: pathlib.Path, rel: str) -> str:
    py = root / rel
    py.parent.mkdir(parents=True)
    py.write_text("")
    return str(py)


class InstallPython(unittest.TestCase):
    def test_prefers_the_installs_own_venv(self):
        from tokencoach.config import install_python
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            self.assertEqual(install_python(d), sys.executable)
            brew = make_venv(root, "venv/bin/python")                # Homebrew's opt/…/libexec
            self.assertEqual(install_python(d), brew)
            script = make_venv(root, ".venv/bin/python3")            # one-line installer
            self.assertEqual(install_python(d), script)

    def test_hook_uses_the_stable_path(self):
        from tokencoach import nudge
        with tempfile.TemporaryDirectory() as d:
            py = make_venv(pathlib.Path(d), "venv/bin/python")
            self.assertTrue(nudge.hook_command(d).startswith(f'"{py}" '))


class LoginAgent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plist = os.path.join(self.tmp.name, "agent.plist")
        self.args = ["/opt/homebrew/opt/tokencoach/libexec/venv/bin/python",
                     "/opt/homebrew/opt/tokencoach/libexec/tokencoach.py"]
        from tokencoach import ui
        self.ui = ui
        self.patches = [patch.object(ui, "LAUNCH_AGENT_PLIST", self.plist),
                        patch.object(ui, "_login_item_args", return_value=self.args)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def write(self, args):
        with open(self.plist, "wb") as f:
            plistlib.dump({"Label": "x", "ProgramArguments": args}, f)

    def test_agent_pointing_at_a_deleted_cellar_is_stale(self):
        self.assertFalse(self.ui._login_item_current())                  # missing
        self.write(["/opt/homebrew/Cellar/tokencoach/1.1.0/libexec/venv/bin/python", self.args[1]])
        self.assertFalse(self.ui._login_item_current())
        self.write(self.args)
        self.assertTrue(self.ui._login_item_current())

    def run_add(self, job_pids):
        ok = subprocess.CompletedProcess([], 0, b"", b"")
        with patch.object(self.ui.subprocess, "run", return_value=ok) as run, \
                patch.object(self.ui, "_job_pid", side_effect=job_pids):
            handed_over = self.ui._add_login_item(handoff=True)
        with open(self.plist, "rb") as f:
            self.assertEqual(plistlib.load(f)["ProgramArguments"], self.args)
        return handed_over, [c.args[0][1] for c in run.call_args_list]

    def test_manual_start_reloads_the_job_and_hands_over(self):
        # `tokencoach &` after an upgrade: the job is loaded but cannot spawn
        handed_over, calls = self.run_add([None, os.getpid() + 1])
        self.assertTrue(handed_over)
        self.assertEqual(calls, ["unload", "load"])

    def test_no_handover_when_launchd_did_not_start_a_copy(self):
        handed_over, _ = self.run_add([None, None])
        self.assertFalse(handed_over)

    def test_the_running_job_only_rewrites_the_file(self):
        # reloading would kill this very process
        handed_over, calls = self.run_add([os.getpid()])
        self.assertFalse(handed_over)
        self.assertEqual(calls, [])


class OtherCopies(unittest.TestCase):
    def test_stops_only_plain_copies_of_this_script(self):
        from tokencoach import ui
        script = "/opt/homebrew/opt/tokencoach/libexec/tokencoach.py"
        me = os.getpid()
        ps = "\n".join([
            f"{me} /usr/bin/python {script}",                    # this process
            f"101 /usr/bin/python {script}",                     # stray copy
            f"102 /usr/bin/python {script} --demo",              # the demo stays
            "103 /usr/bin/python /elsewhere/tokencoach.py",      # another install
        ])
        with patch.object(ui, "_script_path", return_value=script), \
                patch.object(ui.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, ps, "")), \
                patch.object(ui.os, "kill") as kill:
            self.assertEqual(ui._stop_other_copies(), [101])
        kill.assert_called_once_with(101, 15)


REPO = pathlib.Path(__file__).resolve().parent.parent
BAR = "io.github.cagdasatici.tokencoach"


class QuitSticks(unittest.TestCase):
    """Quit must last until the next login or a manual start: the doctor's
    watchdog used to bring the app back within two minutes."""

    def test_quit_leaves_the_marker(self):
        from tokencoach import ui
        with tempfile.TemporaryDirectory() as d:
            marker = os.path.join(d, "quit-by-user")
            with patch.object(ui, "QUIT_MARKER", marker), \
                    patch.object(ui.subprocess, "run") as run, \
                    patch.object(ui.rumps, "quit_application"):
                ui._quit_app()
            self.assertTrue(os.path.exists(marker))
            self.assertIn("bootout", run.call_args.args[0])

    def run_doctor(self, quit_by_user):
        """Doctor sections 1-2, 4 and 8 in a scratch HOME; launchctl is a stub
        that logs its arguments and reports nothing loaded or running."""
        script = (REPO / "tokencoach-doctor.sh").read_text()
        cut = lambda a, b: script[script.index(f"# ── {a}."):script.index(f"# ── {b}.")]
        body = script[:script.index("# ── 3.")] + cut(4, 5) + cut(8, 9)
        with tempfile.TemporaryDirectory() as d:
            home, bin_ = pathlib.Path(d, "home"), pathlib.Path(d, "bin")
            agents = home / "Library/LaunchAgents"
            data = home / "Library/Application Support/TokenCoach"
            for p in (agents, data / "widget", bin_):
                p.mkdir(parents=True)
            with open(agents / f"{BAR}.plist", "wb") as f:
                plistlib.dump({"Label": BAR, "KeepAlive": True}, f)
            cache = data / "widget/usage.json"
            cache.write_text("{}")
            os.utime(cache, (0, 0))                                   # stale
            if quit_by_user:
                (data / "quit-by-user").write_text("1\n")
            log = pathlib.Path(d, "launchctl.log")
            for name, text in {
                "launchctl": f'#!/bin/bash\necho "$*" >> "{log}"\n'
                             '[ "$1" = bootstrap ] || [ "$1" = kickstart ] || exit 1\n',
                "crontab": "#!/bin/bash\necho '* * * * * tokencoach-doctor.sh'\n",
            }.items():
                (bin_ / name).write_text(text)
                (bin_ / name).chmod(0o755)
            subprocess.run(["/bin/bash", "-c", body], cwd=d, capture_output=True, text=True,
                           env={"HOME": str(home), "PATH": f"{bin_}:/usr/bin:/bin:/usr/sbin"})
            calls = log.read_text().splitlines() if log.exists() else []
        return [c for c in calls if c.split()[0] in ("bootstrap", "kickstart")
                and (c.endswith(f"/{BAR}") or c.endswith(f"/{BAR}.plist"))]

    def test_watchdog_starts_a_stopped_app(self):
        starts = self.run_doctor(quit_by_user=False)
        self.assertTrue(any(c.startswith("bootstrap") for c in starts))
        self.assertTrue(any(c.startswith("kickstart") for c in starts))

    def test_watchdog_leaves_a_quit_app_alone(self):
        self.assertEqual(self.run_doctor(quit_by_user=True), [])
