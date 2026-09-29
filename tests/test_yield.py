"""Yield metrics: the commit trailer hook, commit scanning and the metrics built
on them. Real git in temporary folders; never the owner's repositories or logs."""
import os as _os
import tempfile as _tempfile

# Isolate from the real data folder before anything imports tokencoach.
_os.environ.setdefault("TOKENCOACH_DATA_DIR", _tempfile.mkdtemp(prefix="tokencoach-test-"))

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

from tokencoach import trailer

REPO = pathlib.Path(__file__).resolve().parent.parent
SID = "0a1b2c3d-4e5f-6789-abcd-ef0123456789"
CLAUDE_ENV = {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": SID}


def _git_env(extra=None):
    """A git that ignores the owner's global config, hooks and identity."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("GIT_", "CLAUDE"))}
    env.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"})
    env.update(extra or {})
    return env


def git(cwd, *args, env=None, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, env=_git_env(env), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {r.stderr}")
    return r.stdout.strip()


class TrailerText(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.msg = pathlib.Path(self.tmp.name) / "COMMIT_EDITMSG"

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, text, env=CLAUDE_ENV, source=None):
        self.msg.write_text(text)
        argv = [str(self.msg)] + ([source] if source else [])
        trailer.main(argv, env)
        return self.msg.read_text()

    def test_adds_the_session_trailer_inside_claude_code(self):
        out = self.run_hook("Add pagination\n\nCursor based.\n")
        self.assertIn(f"Claude-Session: {SID}", out)
        self.assertTrue(out.startswith("Add pagination\n\nCursor based.\n"))

    def test_leaves_a_terminal_commit_alone(self):
        text = "Add pagination\n"
        self.assertEqual(self.run_hook(text, env={}), text)
        self.assertEqual(self.run_hook(text, env={"CLAUDECODE": "1"}), text)   # no id to record

    def test_does_not_add_a_second_trailer_on_amend(self):
        once = self.run_hook("Fix it\n")
        twice = self.run_hook(once, env={**CLAUDE_ENV, "CLAUDE_CODE_SESSION_ID": "ffffffff-0000-0000-0000-000000000000"})
        self.assertEqual(twice.count("Claude-Session:"), 1)
        self.assertIn(SID, twice)

    def test_ignores_an_id_that_is_not_a_plain_identifier(self):
        for bad in ("abc; rm -rf ~", "x\nSigned-off-by: someone", "", "a" * 200):
            text = "Fix it\n"
            env = {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": bad}
            self.assertEqual(self.run_hook(text, env=env), text, bad)

    def test_skips_merge_commits(self):
        text = "Merge branch 'x'\n"
        self.assertEqual(self.run_hook(text, source="merge"), text)

    def test_never_raises(self):
        trailer.main([str(self.msg.parent / "missing")], CLAUDE_ENV)      # no such file
        trailer.main([], CLAUDE_ENV)                                       # no arguments

    def test_the_hook_stays_light(self):
        # it runs on every commit made in Claude Code: no config, logging or database
        code = ("import sys, tokencoach.trailer; "
                "heavy = {'tokencoach.config', 'tokencoach.ledger', 'sqlite3'} & set(sys.modules); "
                "sys.exit(1 if heavy else 0)")
        r = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class RepoCase(unittest.TestCase):
    """A throwaway repository on branch main with one commit."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(os.path.realpath(self.tmp.name))
        self.repo = self.root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        self.commit("a.py", "print(1)\n", "Initial commit")

    def tearDown(self):
        self.tmp.cleanup()

    def commit(self, name, text, message, cwd=None, env=None, amend=False):
        cwd = cwd or self.repo
        (pathlib.Path(cwd) / name).write_text(text)
        git(cwd, "add", name)
        args = ["commit", "-q", "-m", message] + (["--amend"] if amend else [])
        git(cwd, *args, env=env)
        return git(cwd, "rev-parse", "HEAD")

    def message(self, ref="HEAD", cwd=None):
        return git(cwd or self.repo, "log", "-1", "--format=%B", ref)


class InstallHook(RepoCase):
    def install(self, **kw):
        return trailer.install_repo(str(self.repo), install_dir=str(REPO), **kw)

    def test_a_commit_made_in_claude_code_gets_the_trailer(self):
        self.install()
        self.commit("b.py", "x\n", "Add b", env=CLAUDE_ENV)
        self.assertIn(f"Claude-Session: {SID}", self.message())

    def test_a_commit_made_in_a_terminal_gets_nothing(self):
        self.install()
        self.commit("b.py", "x\n", "Add b")
        self.assertNotIn("Claude-Session", self.message())

    def test_an_amend_keeps_a_single_trailer(self):
        self.install()
        self.commit("b.py", "x\n", "Add b", env=CLAUDE_ENV)
        self.commit("b.py", "y\n", "Add b, better", env=CLAUDE_ENV, amend=True)
        self.assertEqual(self.message().count("Claude-Session"), 1)

    def test_the_trailer_survives_an_editor_message(self):
        self.install()
        (self.repo / "b.py").write_text("x\n")
        git(self.repo, "add", "b.py")
        git(self.repo, "commit", "-q", "--edit", "-m", "Add b", env={**CLAUDE_ENV, "GIT_EDITOR": "true"})
        msg = self.message()
        self.assertTrue(msg.startswith("Add b"))
        self.assertIn(f"Claude-Session: {SID}", msg)

    def test_a_linked_worktree_shares_the_hook(self):
        self.install()
        wt = self.root / "wt"
        git(self.repo, "worktree", "add", "-q", "-b", "feature", str(wt))
        self.commit("c.py", "x\n", "Add c", cwd=wt, env=CLAUDE_ENV)
        self.assertIn(f"Claude-Session: {SID}", self.message(cwd=wt))

    def test_installing_twice_changes_nothing(self):
        first = self.install()
        hook = pathlib.Path(first["hook"])
        before = hook.read_text()
        self.install()
        self.assertEqual(hook.read_text(), before)
        self.assertTrue(os.access(hook, os.X_OK))
        self.assertTrue(trailer.is_installed(str(self.repo)))

    def test_a_worktree_path_registers_the_main_repository(self):
        wt = self.root / "wt"
        git(self.repo, "worktree", "add", "-q", "-b", "feature", str(wt))
        res = trailer.install_repo(str(wt), install_dir=str(REPO))
        self.assertEqual(res["repo"], str(self.repo))

    def test_someone_elses_hook_is_never_overwritten(self):
        hook = self.repo / ".git" / "hooks" / "prepare-commit-msg"
        hook.write_text("#!/bin/sh\necho mine\n")
        with self.assertRaises(trailer.TrailerError):
            self.install()
        self.assertEqual(hook.read_text(), "#!/bin/sh\necho mine\n")
        self.assertFalse(trailer.is_installed(str(self.repo)))
        trailer.uninstall_repo(str(self.repo))                      # and never removed
        self.assertTrue(hook.exists())

    def test_a_hooks_folder_inside_the_project_is_refused(self):
        (self.repo / ".husky").mkdir()
        git(self.repo, "config", "core.hooksPath", ".husky")
        with self.assertRaises(trailer.TrailerError):
            self.install()
        self.assertFalse((self.repo / ".husky" / "prepare-commit-msg").exists())

    def test_a_shared_hooks_folder_outside_the_project_is_refused(self):
        shared = self.root / "shared-hooks"                     # e.g. a global core.hooksPath
        shared.mkdir()
        git(self.repo, "config", "core.hooksPath", str(shared))
        with self.assertRaises(trailer.TrailerError):
            self.install()
        self.assertEqual(list(shared.iterdir()), [])
        self.assertFalse(trailer.is_installed(str(self.repo)))

    def test_uninstall_removes_only_our_hook(self):
        res = self.install()
        trailer.uninstall_repo(str(self.repo))
        self.assertFalse(pathlib.Path(res["hook"]).exists())
        self.assertFalse(trailer.is_installed(str(self.repo)))
        self.commit("b.py", "x\n", "Add b", env=CLAUDE_ENV)
        self.assertNotIn("Claude-Session", self.message())

    def test_a_missing_install_never_blocks_a_commit(self):
        trailer.install_repo(str(self.repo), install_dir=str(self.root / "gone"))
        self.commit("b.py", "x\n", "Add b", env=CLAUDE_ENV)          # git would raise if the hook failed
        self.assertNotIn("Claude-Session", self.message())

    def test_not_a_repository(self):
        with self.assertRaises(trailer.TrailerError):
            trailer.install_repo(str(self.root), install_dir=str(REPO))


DAY = 86400
NOW = 1_800_000_000.0                       # a fixed "today" for the scans below


def _at(ts: float) -> dict:
    stamp = f"{int(ts)} +0000"
    return {"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}


class ScanCommits(RepoCase):
    def setUp(self):
        super().setUp()
        from tokencoach import ledger
        self.conn = ledger.open_ledger(str(self.root / "ledger.db"))
        self.first = git(self.repo, "rev-parse", "HEAD")

    def tearDown(self):
        self.conn.close()
        super().tearDown()

    def scan(self, now=NOW):
        from tokencoach import yield_metrics
        return yield_metrics.scan_repo(self.conn, str(self.repo), now=now)

    def row(self, sha):
        r = self.conn.execute("SELECT * FROM commits WHERE sha = ?", (sha,)).fetchone()
        return dict(r) if r else None

    def tagged(self, name, text, subject, **kw):
        return self.commit(name, text, f"{subject}\n\nClaude-Session: {SID}", **kw)

    def test_records_a_commit_with_its_session_and_files(self):
        sha = self.tagged("b.py", "x\n", "Add b", env=_at(NOW - DAY))
        self.scan()
        r = self.row(sha)
        self.assertEqual((r["session_id"], r["subject"], r["ts"]), (SID, "Add b", NOW - DAY))
        self.assertEqual(json.loads(r["files"]), ["b.py"])
        self.assertIsNone(self.row(self.first)["session_id"])
        self.assertEqual(self.row(sha)["repo"], str(self.repo))

    def test_the_hook_and_the_scan_work_together(self):
        trailer.install_repo(str(self.repo), install_dir=str(REPO))
        sha = self.commit("b.py", "x\n", "Add b", env={**CLAUDE_ENV, **_at(NOW - DAY)})
        self.scan()
        self.assertEqual(self.row(sha)["session_id"], SID)

    def test_scanning_twice_adds_nothing(self):
        self.tagged("b.py", "x\n", "Add b", env=_at(NOW - DAY))
        self.scan()
        before = self.conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
        self.scan()
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0], before)

    def test_merges_and_stashes_are_not_changes(self):
        git(self.repo, "checkout", "-q", "-b", "feature")
        self.commit("f.py", "x\n", "Feature work", env=_at(NOW - 3 * DAY))
        git(self.repo, "checkout", "-q", "main")
        self.commit("m.py", "x\n", "Main work", env=_at(NOW - 2 * DAY))
        git(self.repo, "merge", "-q", "--no-ff", "-m", "Merge feature", "feature", env=_at(NOW - DAY))
        (self.repo / "a.py").write_text("dirty\n")
        git(self.repo, "stash", env=_at(NOW - DAY))
        self.scan()
        subjects = {r["subject"] for r in self.conn.execute("SELECT subject FROM commits")}
        self.assertEqual(subjects, {"Initial commit", "Feature work", "Main work"})

    def test_only_the_recent_window_is_read(self):
        old = self.commit("old.py", "x\n", "Ancient", env=_at(NOW - 400 * DAY))
        recent = self.commit("new.py", "x\n", "Recent", env=_at(NOW - DAY))
        self.scan()
        self.assertIsNone(self.row(old))
        self.assertIsNotNone(self.row(recent))

    def test_a_revert_marks_the_original_with_the_reverts_time(self):
        sha = self.tagged("b.py", "x\n", "Add b", env=_at(NOW - 5 * DAY))
        git(self.repo, "revert", "--no-edit", sha, env=_at(NOW - 4 * DAY))
        self.scan()
        self.assertEqual(self.row(sha)["reverted_ts"], NOW - 4 * DAY)
        self.assertIsNone(self.row(self.first)["reverted_ts"])

    def test_an_amend_that_changes_the_code_rewrites_the_old_commit(self):
        old = self.tagged("b.py", "x\n", "Add b", env=_at(NOW - 3 * DAY))
        self.scan(now=NOW - 2 * DAY)
        new = self.tagged("b.py", "y\n", "Add b", amend=True, env=_at(NOW - 2 * DAY))
        self.scan(now=NOW - 1 * DAY)
        self.assertEqual((self.row(old)["gone_ts"], self.row(old)["superseded"]), (NOW - DAY, 0))
        self.assertIsNone(self.row(new)["gone_ts"])

    def test_an_amend_of_only_the_message_replaces_rather_than_rewrites(self):
        old = self.tagged("b.py", "x\n", "Add b", env=_at(NOW - 3 * DAY))
        self.scan(now=NOW - 2 * DAY)
        self.tagged("b.py", "x\n", "Add b, reworded", amend=True, env=_at(NOW - 2 * DAY))
        self.scan(now=NOW - 1 * DAY)
        self.assertEqual((self.row(old)["gone_ts"], self.row(old)["superseded"]), (NOW - DAY, 1))

    def test_a_rebase_keeps_the_change(self):
        git(self.repo, "checkout", "-q", "-b", "feature")
        old = self.tagged("f.py", "x\n", "Feature", env=_at(NOW - 3 * DAY))
        git(self.repo, "checkout", "-q", "main")
        self.commit("m.py", "x\n", "Main moves on", env=_at(NOW - 3 * DAY))
        self.scan(now=NOW - 2 * DAY)
        git(self.repo, "checkout", "-q", "feature")
        git(self.repo, "rebase", "-q", "main", env=_at(NOW - 2 * DAY))
        self.scan(now=NOW - 1 * DAY)
        self.assertEqual((self.row(old)["gone_ts"], self.row(old)["superseded"]), (NOW - DAY, 1))

    def test_dropping_a_commit_rewrites_it(self):
        sha = self.tagged("b.py", "x\n", "Add b", env=_at(NOW - 3 * DAY))
        self.scan(now=NOW - 2 * DAY)
        git(self.repo, "reset", "-q", "--hard", "HEAD~1")
        self.scan(now=NOW - 1 * DAY)
        self.assertEqual((self.row(sha)["gone_ts"], self.row(sha)["superseded"]), (NOW - DAY, 0))

    def test_a_commit_that_comes_back_is_live_again(self):
        sha = self.tagged("b.py", "x\n", "Add b", env=_at(NOW - 3 * DAY))
        self.scan(now=NOW - 2 * DAY)
        git(self.repo, "reset", "-q", "--hard", "HEAD~1")
        self.scan(now=NOW - 1 * DAY)
        git(self.repo, "reset", "-q", "--hard", sha)
        self.scan(now=NOW)
        self.assertIsNone(self.row(sha)["gone_ts"])

    def test_a_scan_that_cannot_read_git_changes_nothing(self):
        from tokencoach import yield_metrics
        sha = self.tagged("b.py", "x\n", "Add b", env=_at(NOW - DAY))
        self.scan()
        self.repo.rename(self.root / "moved")
        yield_metrics.scan_all(self.conn, now=NOW)                 # skips the missing repo quietly
        self.assertIsNone(self.row(sha)["gone_ts"])

    def test_a_git_failure_mid_scan_marks_nothing_as_lost(self):
        from unittest.mock import patch
        from tokencoach import yield_metrics
        sha = self.tagged("b.py", "x\n", "Add b", env=_at(NOW - DAY))
        self.scan()
        with patch.object(yield_metrics, "_run", return_value=None):
            res = self.scan(now=NOW + DAY)
        self.assertFalse(res["ok"])
        self.assertIsNone(self.row(sha)["gone_ts"])

    def test_registering_records_when_tracking_began(self):
        from tokencoach import yield_metrics
        yield_metrics.register_repo(self.conn, str(self.repo), now=NOW)
        self.assertEqual(self.conn.execute("SELECT since FROM yield_repos").fetchone()[0], NOW)
        yield_metrics.register_repo(self.conn, str(self.repo), now=NOW + DAY)     # again: keeps the first
        self.assertEqual(self.conn.execute("SELECT since FROM yield_repos").fetchone()[0], NOW)

    def test_a_linked_worktree_is_the_same_repository_not_a_second_one(self):
        from tokencoach import yield_metrics
        wt = self.root / "wt"
        git(self.repo, "worktree", "add", "-q", "-b", "feature", str(wt))
        first = yield_metrics.register_repo(self.conn, str(self.repo))
        second = yield_metrics.register_repo(self.conn, str(wt))
        self.assertEqual(first, second)
        self.assertEqual(len(yield_metrics.registered(self.conn)), 1)

    def test_a_repository_with_its_git_folder_elsewhere_is_found_from_either_side(self):
        from tokencoach import yield_metrics
        work, gitdir, wt = self.root / "sep-work", self.root / "sep.git", self.root / "sep-wt"
        work.mkdir()
        git(work, "init", "-q", "-b", "main", "--separate-git-dir", str(gitdir))
        self.commit("a.py", "1\n", "First", cwd=work)
        git(work, "worktree", "add", "-q", "-b", "feature", str(wt))
        a = yield_metrics.register_repo(self.conn, str(wt))
        b = yield_metrics.register_repo(self.conn, str(work))
        self.assertEqual(a, b)
        self.assertEqual(len(yield_metrics.registered(self.conn)), 1)

    def test_registered_repositories_are_scanned_with_their_worktrees(self):
        from tokencoach import yield_metrics
        wt = self.root / "wt"
        git(self.repo, "worktree", "add", "-q", "-b", "feature", str(wt))
        yield_metrics.register_repo(self.conn, str(self.repo))
        yield_metrics.scan_all(self.conn, now=NOW)
        repos = yield_metrics.registered(self.conn)
        self.assertEqual([r["path"] for r in repos], [str(self.repo)])
        self.assertEqual(sorted(repos[0]["worktrees"]), sorted([str(self.repo), str(wt)]))
        yield_metrics.unregister_repo(self.conn, str(self.repo))
        self.assertEqual(yield_metrics.registered(self.conn), [])


class Snapshot(unittest.TestCase):
    """The metrics, on hand-built ledger rows (no git)."""
    REPO = "/w/antigravity"

    def setUp(self):
        from tokencoach import ledger
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = ledger.open_ledger(os.path.join(self.tmp.name, "ledger.db"))
        self.conn.execute("INSERT INTO yield_repos (path, worktrees, scanned, since) VALUES (?, ?, ?, ?)",
                          (self.REPO, json.dumps([self.REPO, "/w/wt-feature"]), NOW, NOW - 200 * DAY))
        self.n = 0

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def session(self, sid, *, days_ago, cost=1.0, prompts=1, cwd=None, model="claude-sonnet-5",
                source="claude_code"):
        """One session whose last response was `days_ago` days before NOW."""
        from tokencoach import ledger
        cwd = cwd or self.REPO
        last = NOW - days_ago * DAY
        ps = [{"id": f"{sid}-p{i}", "source": source, "session_id": sid, "project": "p",
               "ts": last - 3600 + i, "text": "do it", "cwd": cwd} for i in range(prompts)]
        cs = [{"id": f"{sid}-c{i}", "source": source, "session_id": sid, "project": "p",
               "model": model, "ts": last - 1800 * i, "input_tokens": 1, "output_tokens": 1,
               "cache_write_tokens": 0, "cache_read_tokens": 0, "reasoning_tokens": 0,
               "cost_usd": cost / 2} for i in range(2)]
        ledger._insert(self.conn, ps, cs, [])

    def commit(self, sha, *, session=None, days_ago, files=("a.py",), subject="Change", reverted_after=None,
               gone_after=None, superseded=0):
        ts = NOW - days_ago * DAY
        self.conn.execute(
            "INSERT INTO commits (repo, sha, session_id, ts, subject, files, first_seen, reverted_ts, gone_ts, superseded) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (self.REPO, sha, session, ts, subject, json.dumps(list(files)), ts,
             None if reverted_after is None else ts + reverted_after * DAY,
             None if gone_after is None else ts + gone_after * DAY, superseded))

    def snap(self):
        from tokencoach import yield_metrics
        self.conn.commit()
        return yield_metrics.snapshot(self.conn, now=NOW)

    def test_nothing_is_reported_until_a_repository_is_registered(self):
        from tokencoach import yield_metrics
        self.conn.execute("DELETE FROM yield_repos")
        self.assertIsNone(yield_metrics.snapshot(self.conn, now=NOW))

    def test_cost_and_attention_per_accepted_change(self):
        self.session("s1", days_ago=10, cost=10.0, prompts=6)
        self.commit("c1", session="s1", days_ago=10)
        self.commit("c2", session="s1", days_ago=10, files=("b.py",))
        self.commit("c3", session="s1", days_ago=10, files=("c.py",), reverted_after=1)
        o = self.snap()["overall"]
        self.assertEqual((o["commits"], o["accepted"], o["reverted"]), (3, 2, 1))
        self.assertAlmostEqual(o["cost_per_accepted"], 5.0)
        self.assertAlmostEqual(o["prompts_per_accepted"], 3.0)

    def test_a_young_session_is_pending_not_counted(self):
        self.session("old", days_ago=10, cost=4.0)
        self.commit("c1", session="old", days_ago=10)
        self.session("new", days_ago=2, cost=50.0)
        self.commit("c2", session="new", days_ago=2)
        s = self.snap()
        self.assertEqual(s["overall"]["sessions"], 1)
        self.assertAlmostEqual(s["overall"]["cost"], 4.0)
        self.assertEqual(s["pending"]["sessions"], 1)
        self.assertEqual(s["pending"]["commits"], 1)

    def test_a_late_commit_keeps_its_session_pending(self):
        self.session("s", days_ago=8, cost=4.0)
        self.commit("c1", session="s", days_ago=6)            # committed after the last response
        self.assertEqual(self.snap()["overall"]["sessions"], 0)

    def test_a_commit_dropped_within_a_week_is_not_accepted_but_later_is(self):
        self.session("s", days_ago=20)
        self.commit("early", session="s", days_ago=20, gone_after=2)
        self.commit("late", session="s", days_ago=20, files=("b.py",), gone_after=12)
        o = self.snap()["overall"]
        self.assertEqual((o["commits"], o["accepted"], o["rewritten"]), (2, 1, 1))

    def test_a_replaced_commit_is_not_a_change_of_its_own(self):
        self.session("s", days_ago=20)
        self.commit("old", session="s", days_ago=20, gone_after=1, superseded=1)
        self.commit("new", session="s", days_ago=20, files=("b.py",))
        o = self.snap()["overall"]
        self.assertEqual((o["commits"], o["accepted"]), (1, 1))

    def test_a_late_revert_does_not_undo_acceptance(self):
        self.session("s", days_ago=20)
        self.commit("c1", session="s", days_ago=20, reverted_after=9)
        self.assertEqual(self.snap()["overall"]["accepted"], 1)

    def test_rework_is_a_later_fix_to_the_same_files_within_a_week(self):
        self.session("s", days_ago=20)
        self.commit("c1", session="s", days_ago=20, files=("a.py", "b.py"))          # fixed in 2 days
        self.commit("fix1", days_ago=18, files=("b.py",), subject="Fix off-by-one in b")
        self.commit("c2", session="s", days_ago=20, files=("x.py",))                 # fix touched other file
        self.commit("fix2", days_ago=19, files=("y.py",), subject="Fix y")
        self.commit("c3", session="s", days_ago=20, files=("m.py",))                 # touched again, not a fix
        self.commit("more", days_ago=19, files=("m.py",), subject="Add feature to m")
        self.commit("c4", session="s", days_ago=20, files=("n.py",))                 # fix came too late
        self.commit("fix4", days_ago=10, files=("n.py",), subject="Fix n")
        o = self.snap()["overall"]
        self.assertEqual((o["commits"], o["reworked"]), (4, 1))
        self.assertAlmostEqual(o["rework_rate"], 0.25)

    def test_rework_ignores_a_fix_for_a_commit_that_came_after(self):
        self.session("s", days_ago=20)
        self.commit("fix", days_ago=20, files=("a.py",), subject="Fix a")
        self.commit("c1", session="s", days_ago=19, files=("a.py",))
        self.assertEqual(self.snap()["overall"]["reworked"], 0)

    def test_a_session_with_no_commit_still_counts_its_cost(self):
        self.session("busy", days_ago=10, cost=6.0)
        self.commit("c1", session="busy", days_ago=10)
        self.session("idle", days_ago=10, cost=4.0)
        o = self.snap()["overall"]
        self.assertAlmostEqual(o["cost_per_accepted"], 10.0)
        self.assertEqual(o["idle_sessions"], 1)
        self.assertAlmostEqual(o["idle_cost"], 4.0)

    def test_no_accepted_change_means_no_ratio(self):
        self.session("s", days_ago=10)
        o = self.snap()["overall"]
        self.assertIsNone(o["cost_per_accepted"])
        self.assertIsNone(o["rework_rate"])

    def test_sessions_elsewhere_are_not_counted(self):
        self.session("here", days_ago=10, cost=3.0)
        self.session("there", days_ago=10, cost=99.0, cwd="/w/other-project")
        self.session("codex", days_ago=10, cost=99.0, source="codex")
        self.assertAlmostEqual(self.snap()["overall"]["cost"], 3.0)

    def test_a_worktree_or_subfolder_counts_as_the_repository(self):
        self.session("wt", days_ago=10, cost=2.0, cwd="/w/wt-feature")
        self.session("sub", days_ago=10, cost=3.0, cwd=self.REPO + "/src/engine")
        self.assertAlmostEqual(self.snap()["overall"]["cost"], 5.0)

    def test_sessions_from_before_tracking_began_are_not_judged(self):
        # they could never have been tagged, so they would only inflate the cost per change
        self.conn.execute("UPDATE yield_repos SET since = ?", (NOW - 12 * DAY,))
        self.session("before", days_ago=20, cost=30.0)
        self.session("after", days_ago=10, cost=2.0)
        self.commit("c1", session="after", days_ago=10)
        o = self.snap()["overall"]
        self.assertEqual(o["sessions"], 1)
        self.assertAlmostEqual(o["cost"], 2.0)

    def test_a_repository_without_a_start_time_counts_from_its_first_scan(self):
        self.conn.execute("UPDATE yield_repos SET since = NULL, scanned = ?", (NOW - 12 * DAY,))
        self.session("before", days_ago=20, cost=30.0)
        self.session("after", days_ago=10, cost=2.0)
        self.assertAlmostEqual(self.snap()["overall"]["cost"], 2.0)

    def test_a_tagged_session_is_always_tracked(self):
        self.conn.execute("UPDATE yield_repos SET since = ?", (NOW - 5 * DAY,))
        self.session("early", days_ago=20, cost=3.0)
        self.commit("c1", session="early", days_ago=20)
        self.assertEqual(self.snap()["overall"]["sessions"], 1)

    def test_tracking_since_is_the_earliest_start(self):
        self.assertEqual(self.snap()["tracking_since"], NOW - 200 * DAY)

    def test_a_session_found_only_by_its_trailer_is_included(self):
        self.session("far", days_ago=10, cost=7.0, cwd="/tmp/somewhere-else")
        self.commit("c1", session="far", days_ago=10)
        o = self.snap()["overall"]
        self.assertEqual(o["sessions"], 1)
        self.assertEqual(o["accepted"], 1)

    def test_cuts_by_model_use_the_model_that_cost_most(self):
        from tokencoach import ledger
        self.session("a", days_ago=10, cost=2.0, model="claude-sonnet-5")
        self.session("b", days_ago=10, cost=8.0, model="claude-opus-5")
        self.commit("ca", session="a", days_ago=10)
        self.commit("cb", session="b", days_ago=10, files=("b.py",))
        rows = {r["key"]: r for r in self.snap()["by_model"]}
        self.assertAlmostEqual(rows["claude-sonnet-5"]["cost_per_accepted"], 2.0)
        self.assertAlmostEqual(rows["claude-opus-5"]["cost_per_accepted"], 8.0)

    def test_cuts_by_week_start_on_monday_and_run_oldest_first(self):
        import datetime
        self.session("w1", days_ago=30)
        self.session("w2", days_ago=15)
        self.commit("c1", session="w1", days_ago=30)
        self.commit("c2", session="w2", days_ago=15, files=("b.py",))
        weeks = self.snap()["by_week"]
        self.assertEqual(len(weeks), 2)
        self.assertLess(weeks[0]["key"], weeks[1]["key"])
        for w in weeks:
            self.assertEqual(datetime.date.fromisoformat(w["key"]).weekday(), 0)

    def test_coverage_reports_how_many_commits_carry_a_session(self):
        self.session("s", days_ago=10)
        self.commit("tagged", session="s", days_ago=10)
        self.commit("by-hand", days_ago=10, files=("b.py",))
        cov = self.snap()["coverage"]
        self.assertEqual((cov["commits"], cov["tagged"]), (2, 1))


class Wiring(ScanCommits):
    """Refreshing, reporting, cleanup and the dashboard, on real repos."""

    def test_the_refresh_is_throttled_and_a_forced_one_is_not(self):
        from tokencoach import yield_metrics as ym
        ym.register_repo(self.conn, str(self.repo))
        self.assertTrue(ym.refresh(self.conn, now=NOW, min_interval=600))
        self.assertFalse(ym.refresh(self.conn, now=NOW + 60, min_interval=600))
        self.assertTrue(ym.refresh(self.conn, now=NOW + 700, min_interval=600))
        self.assertTrue(ym.refresh(self.conn, now=NOW + 701, min_interval=0))

    def test_nothing_is_scanned_when_no_repository_is_registered(self):
        from tokencoach import yield_metrics as ym
        self.assertFalse(ym.refresh(self.conn, now=NOW))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0], 0)

    def test_removing_hooks_leaves_history_and_registry_alone(self):
        from tokencoach import yield_metrics as ym
        trailer.install_repo(str(self.repo), install_dir=str(REPO))
        ym.register_repo(self.conn, str(self.repo))
        self.assertEqual(ym.remove_hooks(self.conn), [str(self.repo)])
        self.assertFalse(trailer.is_installed(str(self.repo)))
        self.assertEqual(len(ym.registered(self.conn)), 1)
        self.assertEqual(ym.remove_hooks(self.conn), [])

    def test_the_report_says_how_to_start_when_nothing_is_tracked(self):
        from tokencoach import yield_metrics as ym
        self.assertIn("--yield-install", ym.format_report(None))

    def test_the_report_states_the_numbers_and_what_is_still_pending(self):
        from tokencoach import ledger, yield_metrics as ym
        ym.register_repo(self.conn, str(self.repo), now=NOW - 100 * DAY)
        ledger._insert(self.conn, [{"id": "p1", "source": "claude_code", "session_id": SID, "project": "p",
                                    "ts": NOW - 10 * DAY, "text": "go", "cwd": str(self.repo)}],
                       [{"id": "c1", "source": "claude_code", "session_id": SID, "project": "p",
                         "model": "claude-sonnet-5", "ts": NOW - 10 * DAY, "input_tokens": 1,
                         "output_tokens": 1, "cache_write_tokens": 0, "cache_read_tokens": 0,
                         "reasoning_tokens": 0, "cost_usd": 12.0}], [])
        self.tagged("b.py", "x\n", "Add b", env=_at(NOW - 10 * DAY))
        self.scan()
        text = ym.format_report(ym.snapshot(self.conn, now=NOW))
        for needle in ("1 session", "$12.00", "accepted", "rework", "1 of 2 commits"):
            self.assertIn(needle, text)

    def test_the_dashboard_carries_the_metrics_once_a_repository_is_tracked(self):
        from tokencoach import ledger_report, yield_metrics as ym
        self.assertIsNone(ledger_report.dashboard_data(self.conn)["yield"])
        ym.register_repo(self.conn, str(self.repo))
        data = ledger_report.dashboard_data(self.conn)
        self.assertEqual(data["yield"]["repos"][0]["path"], str(self.repo))
        page = ledger_report.build_report(self.conn)
        self.assertIn('id="card-yield"', page)


class Demo(unittest.TestCase):
    def test_the_sample_history_has_a_yield_story(self):
        from tokencoach import demo, ledger, yield_metrics as ym
        with tempfile.TemporaryDirectory() as d:
            conn = ledger.open_ledger(os.path.join(d, "ledger.db"))
            facts = demo.build(conn)
            demo.seed_yield(conn, facts["now"])
            snap = ym.snapshot(conn, now=facts["now"])
            conn.close()
        o = snap["overall"]
        self.assertGreater(o["sessions"], 20)
        self.assertGreater(o["accepted"], 10)
        self.assertTrue(0 < o["rework_rate"] < 0.5)
        self.assertGreater(len(snap["by_week"]), 4)
        self.assertGreater(len(snap["by_model"]), 1)
        self.assertTrue(all(r["path"].startswith(os.path.expanduser("~/code/")) for r in snap["repos"]))


class Migration(unittest.TestCase):
    def test_a_ledger_from_before_the_start_time_column_gains_it(self):
        import sqlite3
        from tokencoach import ledger
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "ledger.db")
            c = sqlite3.connect(path)
            c.executescript("CREATE TABLE yield_repos (path TEXT PRIMARY KEY, worktrees TEXT NOT NULL "
                            "DEFAULT '[]', scanned REAL); INSERT INTO yield_repos (path, scanned) VALUES ('/r', 5);"
                            "PRAGMA user_version = 2;")
            c.commit()
            c.close()
            conn = ledger.open_ledger(path)
            cols = {r[1] for r in conn.execute("PRAGMA table_info(yield_repos)")}
            row = conn.execute("SELECT path, scanned, since FROM yield_repos").fetchone()
            conn.close()
        self.assertTrue({"since", "git_dir"} <= cols)
        # tracking is dated from the earliest moment we know of, and stays put on later scans
        self.assertEqual((row["path"], row["scanned"], row["since"]), ("/r", 5, 5))


class Cli(RepoCase):
    """The command line, in a process of its own with no access to the owner's data or logs."""

    def run_cli(self, *args):
        home = self.root / "home"
        home.mkdir(exist_ok=True)
        env = {**_git_env(), "HOME": str(home), "TOKENCOACH_DATA_DIR": str(self.root / "data"),
               "PATH": os.environ.get("PATH", "")}
        return subprocess.run([sys.executable, str(REPO / "tokencoach.py"), *args], cwd=REPO, env=env,
                              capture_output=True, text=True, timeout=120)

    def test_install_tags_tracks_and_reports_then_remove_undoes_it(self):
        r = self.run_cli("--yield-install", str(self.repo))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(trailer.is_installed(str(self.repo)))
        r = self.run_cli("--yield")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(str(self.repo), r.stdout)
        r = self.run_cli("--yield-remove", str(self.repo))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(trailer.is_installed(str(self.repo)))
        self.assertNotIn(str(self.repo), self.run_cli("--yield").stdout)

    def test_a_foreign_hook_is_reported_not_overwritten(self):
        hook = self.repo / ".git" / "hooks" / "prepare-commit-msg"
        hook.write_text("#!/bin/sh\necho mine\n")
        r = self.run_cli("--yield-install", str(self.repo))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("already exists", r.stderr)
        self.assertEqual(hook.read_text(), "#!/bin/sh\necho mine\n")

    def test_install_needs_a_path(self):
        self.assertNotEqual(self.run_cli("--yield-install").returncode, 0)


if __name__ == "__main__":
    unittest.main()
