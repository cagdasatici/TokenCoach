"""Rename migration, legacy-install handover, demo sandbox and packaging
checks. Temp folders only."""
import os as _os
import tempfile as _tempfile

# Isolate from the real data folder before anything imports tokencoach.
_os.environ.setdefault("TOKENCOACH_DATA_DIR", _tempfile.mkdtemp(prefix="tokencoach-test-"))

import json
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
                   "tokencoach/ui.py", "docs/plans/2026-09-29-remaining-release-work.md"}
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

    def test_requirements_are_exact(self):
        # auto-update installs these; a range would pull in whatever was published last
        text = (REPO / "requirements.txt").read_text().replace("\\\n", " ")
        reqs = [l.strip() for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]
        loose = [l for l in reqs if "==" not in l]
        self.assertEqual(loose, [])
        # ...and pinned by hash, so a swapped file on PyPI fails the install
        unhashed = [l.split()[0] for l in reqs if "--hash=sha256:" not in l]
        self.assertEqual(unhashed, [])


class PrivateFiles(unittest.TestCase):
    def test_config_is_saved_owner_only(self):
        import stat
        from tokencoach import config
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            pathlib.Path(path + ".tmp").write_text("stale")
            os.chmod(path + ".tmp", 0o644)
            with patch.object(config, "CONFIG_FILE", path):
                config.save_config({"dashboard_token": "t"})
                self.assertEqual(config.load_config(), {"dashboard_token": "t"})
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)


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


class DemoNeverRunsClaude(unittest.TestCase):
    def test_run_claude_refuses_in_demo(self):
        from tokencoach import optimizer
        with patch.dict(os.environ, {"TOKENCOACH_DEMO": "1"}), \
                patch.object(optimizer, "find_claude_cli", return_value="/bin/echo"), \
                patch.object(optimizer.subprocess, "run") as run:
            with self.assertRaises(RuntimeError):
                optimizer.run_claude("hi")
        run.assert_not_called()


class AutoUpdate(unittest.TestCase):
    def git(self, cwd, *args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd,
                              capture_output=True, text=True, check=True).stdout.strip()

    def keygen(self, name):
        key = pathlib.Path(self.tmp.name) / name
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(key)],
                       check=True, capture_output=True)
        return key

    def signed_commit(self, key, msg):
        self.git(self.origin, "-c", "gpg.format=ssh", "-c", f"user.signingkey={key}",
                 "commit", "-S", "-qam", msg)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.trusted, self.stranger = self.keygen("trusted"), self.keygen("stranger")
        self.origin, self.clone = root / "origin", root / "clone"
        self.origin.mkdir()
        self.git(self.origin, "init", "-q", "-b", "main")
        (self.origin / "a.txt").write_text("1\n")
        pub = " ".join(pathlib.Path(f"{self.trusted}.pub").read_text().split()[:2])
        (self.origin / "allowed_signers").write_text(f't@t namespaces="git" {pub}\n')
        self.git(self.origin, "add", ".")
        self.git(self.origin, "commit", "-qm", "one")
        self.git(root, "clone", "-q", str(self.origin), str(self.clone))
        (self.origin / "a.txt").write_text("2\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_commit_signed_by_trusted_key_updates(self):
        from tokencoach.update import _check_and_apply_update
        self.signed_commit(self.trusted, "two")
        self.assertTrue(_check_and_apply_update(str(self.clone)))
        self.assertEqual((self.clone / "a.txt").read_text(), "2\n")

    def test_unsigned_or_untrusted_commits_are_refused(self):
        from tokencoach.update import _check_and_apply_update
        self.git(self.origin, "commit", "-qam", "unsigned")
        self.assertFalse(_check_and_apply_update(str(self.clone)))
        (self.origin / "a.txt").write_text("3\n")
        self.signed_commit(self.stranger, "signed by someone else")
        self.assertFalse(_check_and_apply_update(str(self.clone)))
        self.assertEqual((self.clone / "a.txt").read_text(), "1\n")

    def test_a_push_cannot_trust_its_own_key(self):
        """The signer list comes from the installed copy, not from the update."""
        from tokencoach.update import _check_and_apply_update
        pub = " ".join(pathlib.Path(f"{self.stranger}.pub").read_text().split()[:2])
        (self.origin / "allowed_signers").write_text(f'x@x namespaces="git" {pub}\n')
        self.signed_commit(self.stranger, "trust me")
        self.assertFalse(_check_and_apply_update(str(self.clone)))

    def test_missing_signer_list_refuses(self):
        from tokencoach.update import _check_and_apply_update
        self.signed_commit(self.trusted, "two")
        os.remove(self.clone / "allowed_signers")
        self.git(self.clone, "update-index", "--assume-unchanged", "allowed_signers")
        self.assertFalse(_check_and_apply_update(str(self.clone)))

    def test_shipped_signer_list_is_valid(self):
        lines = [l for l in (REPO / "allowed_signers").read_text().splitlines()
                 if l.strip() and not l.startswith("#")]
        self.assertTrue(lines)
        for l in lines:
            self.assertRegex(l, r'^\S+ namespaces="git" ssh-ed25519 [A-Za-z0-9+/=]+$')

    def test_local_edits_and_branches_are_left_alone(self):
        from tokencoach.update import _check_and_apply_update
        self.signed_commit(self.trusted, "two")
        (self.clone / "a.txt").write_text("my edit\n")
        self.assertFalse(_check_and_apply_update(str(self.clone)))
        self.assertEqual((self.clone / "a.txt").read_text(), "my edit\n")
        self.assertEqual(self.git(self.clone, "stash", "list"), "")
        self.git(self.clone, "checkout", "-q", "--", "a.txt")
        self.git(self.clone, "checkout", "-qb", "feature")
        self.assertFalse(_check_and_apply_update(str(self.clone)))


class AutoUpdateRestart(unittest.TestCase):
    def test_supervised_restart_uses_fresh_launchd_process(self):
        from tokencoach import update
        listed = subprocess.CompletedProcess([], 0, '"PID" = 1234;\n', '')
        restarted = subprocess.CompletedProcess([], 0, b'', b'')
        with patch.object(update.os, "getpid", return_value=1234), \
                patch.object(update.os, "getuid", return_value=501), \
                patch.object(update.subprocess, "run", side_effect=[listed, restarted]) as run, \
                patch.object(update.os, "_exit") as exit_process, \
                patch.object(update.os, "execv") as execv:
            update._restart_app()
        self.assertEqual(run.call_args_list[1].args[0],
                         ["launchctl", "kickstart", "-k",
                          f"gui/501/{update.LAUNCH_AGENT_LABEL}"])
        exit_process.assert_called_once_with(0)
        execv.assert_not_called()

    def test_failed_kickstart_exits_for_launchd_to_respawn(self):
        from tokencoach import update
        listed = subprocess.CompletedProcess([], 0, '"PID" = 1234;\n', '')
        failed = subprocess.CompletedProcess([], 5, b'', b'no such service')
        with patch.object(update.os, "getpid", return_value=1234), \
                patch.object(update.subprocess, "run", side_effect=[listed, failed]), \
                patch.object(update.subprocess, "Popen") as popen, \
                patch.object(update.os, "_exit") as exit_process, \
                patch.object(update.os, "execv") as execv:
            update._restart_app()
        exit_process.assert_called_once_with(1)
        popen.assert_not_called()
        execv.assert_not_called()

    def test_manual_launch_starts_a_fresh_process(self):
        # os.execv keeps the pid, and on macOS 26 the re-exec'd status item
        # stays hidden; a new process gets a visible one.
        from tokencoach import update
        listed = subprocess.CompletedProcess([], 1, '', '')
        with patch.object(update.subprocess, "run", return_value=listed) as run, \
                patch.object(update.subprocess, "Popen") as popen, \
                patch.object(update.os, "_exit") as exit_process, \
                patch.object(update.os, "execv") as execv:
            update._restart_app()
        run.assert_called_once()
        self.assertEqual(popen.call_args.args[0][0], update.sys.executable)
        exit_process.assert_called_once_with(0)
        execv.assert_not_called()


class Cleanup(unittest.TestCase):
    def test_removes_hook_and_login_item_only(self):
        from tokencoach import __main__ as cli, config, nudge
        with tempfile.TemporaryDirectory() as d:
            plist = pathlib.Path(d, "agent.plist")
            plist.write_text("<plist/>")
            with patch.object(config, "LAUNCH_AGENT_PLIST", str(plist)), \
                    patch.object(nudge, "is_installed", return_value=True), \
                    patch.object(nudge, "uninstall") as unhook, \
                    patch("subprocess.run") as run, patch("builtins.print"):
                cli._cleanup()
            unhook.assert_called_once()
            self.assertIn("bootout", run.call_args[0][0])
            self.assertFalse(plist.exists())


class DashboardAccessLog(unittest.TestCase):
    # Found on the mini (path A): the access log wrote the dashboard URL,
    # secret included, into the world-readable app log.
    def test_token_is_not_logged(self):
        from tokencoach import server
        handler = object.__new__(server._Handler)
        with self.assertLogs(server.log, level="DEBUG") as logs:
            handler.log_message('"%s" %s %s', "GET /?t=s3cr3t-Tok_en&x=1 HTTP/1.1", "200", "-")
        self.assertNotIn("s3cr3t-Tok_en", logs.output[0])
        self.assertIn("GET /?t=", logs.output[0])
        self.assertIn("&x=1", logs.output[0])


class CookiesStayOutOfTheLog(unittest.TestCase):
    def test_detected_cookie_values_are_not_logged(self):
        from tokencoach import providers
        jar = '["sessionKey=sk-ant-sid01-SECRETVALUE; lastActiveOrg=org-1"]'
        done = subprocess.CompletedProcess([], 0, stdout=jar, stderr="")
        with patch.object(providers.subprocess, "run", return_value=done), \
                self.assertLogs(providers.log, level="DEBUG") as logs:
            self.assertEqual(len(providers._run_cookie_detection("claude.ai", "sessionKey")), 1)
        self.assertNotIn("SECRETVALUE", "\n".join(logs.output))
        self.assertIn("candidates=1", "\n".join(logs.output))

    def test_browsers_macos_blocks_are_reported(self):
        # Found on the owner's Mac: macOS privacy protection kept the app out of
        # Chrome's folder; the lookup said "nothing found" and nobody knew why.
        from tokencoach import providers
        done = subprocess.CompletedProcess([], 0, stdout="[]", stderr='{"blocked": ["chrome"]}')
        with patch.object(providers.subprocess, "run", return_value=done):
            self.assertEqual(providers._run_cookie_detection("claude.ai", "sessionKey"), [])
        self.assertEqual(providers.last_blocked_browsers, ["chrome"])

    def test_detect_script_flags_unreadable_cookie_stores(self):
        import sys
        from tokencoach import providers
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "browser_cookie3.py").write_text(
                "def chrome(domain_name):\n    raise Exception('Unable to read database file')\n"
                "def safari(domain_name):\n    raise PermissionError(1, 'Operation not permitted')\n"
                "def firefox(domain_name):\n    raise Exception('Could not find Firefox profile directory')\n")
            r = subprocess.run([sys.executable, "-c", providers._DETECT_SCRIPT, "claude.ai", "sessionKey"],
                               capture_output=True, text=True, env={**os.environ, "PYTHONPATH": d})
        self.assertEqual(r.stdout.strip(), "[]")
        self.assertEqual(sorted(json.loads(r.stderr)["blocked"]), ["chrome", "safari"])

    def test_unanswered_keychain_note_does_not_stop_detection(self):
        # Found on the owner's Mac: the note timed out on an idle Mac, the fetch
        # failed, and detection (once per start) never ran.
        from tokencoach import providers
        with patch.object(providers, "_keychain_warned", False), \
                patch.object(providers.subprocess, "run",
                             side_effect=subprocess.TimeoutExpired("osascript", 60)):
            providers._warn_keychain_once()            # must not raise


class DoctorCronRepair(unittest.TestCase):
    # Found on the mini (path A): run by launchd, `crontab -` failed with
    # "Operation not permitted" and the doctor still reported it as repaired.
    def run_cron_check(self, crontab_write_ok):
        script = (REPO / "tokencoach-doctor.sh").read_text()
        start = script.index('CRON_LINE=')
        end = script.index("\nfi\n", script.index('say_failed "cron watchdog missing')) + 4
        with tempfile.TemporaryDirectory() as d:
            fake = pathlib.Path(d, "crontab")
            fake.write_text('#!/bin/bash\n[ "$1" = -l ] && exit 1\ncat >/dev/null\nexit %d\n'
                            % (0 if crontab_write_ok else 1))
            fake.chmod(0o755)
            prelude = ('say_ok() { echo "ok $1"; }; say_fixed() { echo "fixed $1"; }; '
                       'say_failed() { echo "failed $1"; }; repairing() { true; }; APP_DIR=/x\n')
            out = subprocess.run(["/bin/bash", "-c", prelude + script[start:end]],
                                 env={"PATH": d + ":/usr/bin:/bin", "HOME": d},
                                 capture_output=True, text=True)
        return out.stdout

    def test_failed_write_is_reported_as_failed(self):
        self.assertTrue(self.run_cron_check(False).startswith("failed cron watchdog missing"))

    def test_successful_write_is_reported_as_fixed(self):
        self.assertTrue(self.run_cron_check(True).startswith("fixed cron watchdog installed"))
