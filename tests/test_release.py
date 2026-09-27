"""Rename migration, legacy-install handover, demo sandbox and packaging
checks. Temp folders only."""
import os as _os
import tempfile as _tempfile

# Isolate from the real data folder before anything imports tokencoach.
_os.environ.setdefault("TOKENCOACH_DATA_DIR", _tempfile.mkdtemp(prefix="tokencoach-test-"))

import os
import pathlib
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

REPO = pathlib.Path(__file__).resolve().parent.parent


class LegacyDataMove(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.old = self.root / "AIQuotaBar"
        self.new = self.root / "TokenCoach"
        self.old.mkdir()
        (self.old / "ledger.db").write_text("ledger")
        (self.old / "history.db").write_text("history")
        self.cfg_old = self.root / ".claude_bar_config.json"
        self.cfg_old.write_text("{}")

    def tearDown(self):
        self.tmp.cleanup()

    def run_move(self):
        from tokencoach import config
        with patch.object(config, "_LEGACY_SUPPORT", str(self.old)), \
                patch.object(config, "APP_SUPPORT", str(self.new)), \
                patch.object(config, "_LEGACY_FILES", {str(self.cfg_old): str(self.new / "config.json")}), \
                patch.object(config, "CONFIG_FILE", str(self.new / "config.json")), \
                patch.dict(os.environ, {"TOKENCOACH_DATA_DIR": ""}):
            return config.migrate_legacy_data()

    def test_moves_folder_and_config_once(self):
        moved = self.run_move()
        self.assertEqual((self.new / "ledger.db").read_text(), "ledger")
        self.assertTrue((self.new / "config.json").exists())
        self.assertFalse(self.old.exists())
        self.assertEqual(len(moved), 2)
        self.assertEqual(self.run_move(), [])          # idempotent

    def test_settings_merge_when_both_exist(self):
        import json
        self.new.mkdir()
        (self.new / "config.json").write_text(json.dumps({"seen_welcome": True, "dashboard_token": "fresh"}))
        self.cfg_old.write_text(json.dumps({"dashboard_token": "bookmarked", "refresh_interval": 60}))
        self.run_move()
        merged = json.loads((self.new / "config.json").read_text())
        self.assertEqual(merged, {"seen_welcome": True, "dashboard_token": "bookmarked", "refresh_interval": 60})
        self.assertFalse(self.cfg_old.exists())

    def test_finishes_a_partial_move_without_overwriting(self):
        self.new.mkdir()
        (self.new / "ledger.db").write_text("newer")
        self.run_move()
        self.assertEqual((self.new / "ledger.db").read_text(), "newer")
        self.assertEqual((self.new / "history.db").read_text(), "history")


class LegacyInstallHandover(unittest.TestCase):
    def test_starts_installer_once_a_day(self):
        from tokencoach import legacy
        with tempfile.TemporaryDirectory() as d:
            old = pathlib.Path(d) / ".ai-quota-bar"
            old.mkdir()
            (old / "install.sh").write_text("exit 0\n")
            with patch.object(legacy, "LEGACY_DIR", str(old)), \
                    patch.object(legacy, "MARKER", str(pathlib.Path(d) / "marker")), \
                    patch.object(legacy.subprocess, "Popen") as popen:
                self.assertTrue(legacy.finish_legacy_install(str(old)))
                self.assertTrue(legacy.finish_legacy_install(str(old)))
                self.assertEqual(popen.call_count, 1)
                args, kwargs = popen.call_args
                self.assertEqual(args[0], ["/bin/bash", str(old / "install.sh")])
                self.assertTrue(kwargs["start_new_session"])

    def test_new_installs_are_left_alone(self):
        from tokencoach import legacy
        with patch.object(legacy, "LEGACY_PLIST", "/nonexistent.plist"), \
                patch.object(legacy.subprocess, "Popen") as popen:
            self.assertFalse(legacy.finish_legacy_install("/Users/x/.tokencoach"))
            popen.assert_not_called()


class DemoSandbox(unittest.TestCase):
    def test_demo_builds_and_never_targets_real_files(self):
        with tempfile.TemporaryDirectory() as d:
            env = {**os.environ, "TOKENCOACH_DATA_DIR": d, "TOKENCOACH_DEMO": "1"}
            code = ("from tokencoach import demo, ledger, coach\n"
                    "demo.prepare(r'%s')\n"
                    "c = ledger.open_ledger()\n"
                    "snap = coach.coach_snapshot(c)\n"
                    "files = [f for l in snap['lessons'] for f in l['files']]\n"
                    "assert files and all(f.startswith(r'%s') for f in files), files\n"
                    "assert c.execute('select count(*) from prompts').fetchone()[0] > 100\n"
                    "assert any(l['status'] == 'applied' for l in snap['lessons'])\n"
                    "print('ok')" % (d, d))
            out = subprocess.run([os.sys.executable, "-c", code], cwd=REPO, env=env,
                                 capture_output=True, text=True, timeout=120)
            self.assertEqual(out.stdout.strip(), "ok", out.stderr[-2000:])
            real = os.path.expanduser("~/.claude/CLAUDE.md")
            self.assertFalse(any(real in f for f in []))

    def test_screenshots_refuse_real_data(self):
        from tokencoach import screenshots
        with patch.object(screenshots, "DEMO", False):
            with self.assertRaises(RuntimeError):
                screenshots.capture(None, {}, "/tmp/nowhere")


class Packaging(unittest.TestCase):
    def test_no_prerename_names_outside_migration_code(self):
        allowed = {"install.sh", "claude_bar.py", "tokencoach/legacy.py", "tokencoach/config.py",
                   "tokencoach/ledger.py", "tests/test_release.py", "AGENTS.md", "README.md", "LICENSE",
                   "tokencoach/ui.py"}
        files = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True).stdout.split()
        offenders = []
        for f in files:
            p = REPO / f
            if f in allowed or not p.exists() or p.suffix in (".png", ".gif", ".icns"):
                continue
            try:
                text = p.read_text()
            except UnicodeDecodeError:
                continue
            if "aiquotaleft" in text.lower() or "ai-quota-bar" in text or "claude_bar" in text:
                offenders.append(f)
        self.assertEqual(offenders, [])

    def test_formula_ships_the_hook_and_package(self):
        text = (REPO / "Formula" / "tokencoach.rb").read_text()
        for needed in ('"tokencoach.py"', '"tokencoach_nudge.py"', '"tokencoach"', "opt_libexec"):
            self.assertIn(needed, text)

    def test_scripts_parse(self):
        for script in ("install.sh", "uninstall.sh", "restart.sh", "tokencoach-doctor.sh",
                       "make_dock_launcher.sh", "widget/build_widget.sh"):
            r = subprocess.run(["bash", "-n", str(REPO / script)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{script}: {r.stderr}")


if __name__ == "__main__":
    unittest.main()


class DemoCannotTouchRealFiles(unittest.TestCase):
    def test_demo_started_after_a_real_import_refuses(self):
        # the exact mistake that once let sample lessons reach a real CLAUDE.md
        code = ("import sys; sys.argv = ['tokencoach.py', '--demo']\n"
                "import tokencoach.ledger_report\n"
                "from tokencoach import __main__ as m\n"
                "m.main()")
        with tempfile.TemporaryDirectory() as d:
            env = {k: v for k, v in os.environ.items() if k != "TOKENCOACH_DEMO"}
            env["TOKENCOACH_DATA_DIR"] = d
            out = subprocess.run([os.sys.executable, "-c", code], cwd=REPO, env=env,
                                 capture_output=True, text=True, timeout=60)
            self.assertNotEqual(out.returncode, 0)
            self.assertIn("fresh process", out.stderr)

    def test_global_targets_follow_the_demo_env_at_call_time(self):
        from tokencoach import coach
        with patch.dict(os.environ, {"TOKENCOACH_DEMO": "1"}):
            files = coach._global_files()
        self.assertFalse(any(f.startswith(os.path.expanduser("~/.claude")) for f in files.values()))


class Backups(unittest.TestCase):
    def test_same_second_backups_never_overwrite(self):
        from tokencoach import coach
        with tempfile.TemporaryDirectory() as d, patch.object(coach, "BACKUP_DIR", os.path.join(d, "b")):
            f = os.path.join(d, "CLAUDE.md")
            pathlib.Path(f).write_text("original\n")
            coach.write_block(f, [("a", "rule a")])
            coach.write_block(f, [("a", "rule a"), ("b", "rule b")])
            saved = sorted(pathlib.Path(d, "b").iterdir())
            self.assertEqual(len(saved), 2)
            self.assertIn("original", saved[0].read_text() + saved[1].read_text())
