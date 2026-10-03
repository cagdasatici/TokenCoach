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
