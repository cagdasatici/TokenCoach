"""Nudges, lessons, instruction-file edits, before/after, and the local
listener's guards. Fixtures and temp files only - never the owner's real
Claude settings or CLAUDE.md files."""
import os as _os
import tempfile as _tempfile

# Isolate from the real data folder before anything imports tokencoach.
_os.environ.setdefault("TOKENCOACH_DATA_DIR", _tempfile.mkdtemp(prefix="tokencoach-test-"))

import json
import os
import pathlib
import tempfile
import time
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch

from tokencoach import ledger, nudge, coach


def _transcript(path, ctx, model="claude-opus-5"):
    path.write_text(json.dumps({"type": "assistant", "message": {
        "role": "assistant", "model": model,
        "usage": {"input_tokens": 10, "cache_read_input_tokens": ctx - 10,
                  "cache_creation_input_tokens": 0, "output_tokens": 5}}}) + "\n")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.conn = ledger.open_ledger(str(self.root / "ledger.db"))
        p = patch.object(nudge, "claude_quota_left", return_value=None)
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def add_prompt(self, pid, text, project="alpha", session="s1", calls=3, cost=1.0,
                   ts=None, source="claude_code", cwd=None, ctx=1000):
        ts = ts or time.time() - 3600
        self.conn.execute(
            "INSERT INTO prompts (id, source, session_id, project, ts, text, estimated, cwd) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, ?)", (pid, source, session, project, ts, text, cwd))
        for i in range(calls):
            self.conn.execute(
                "INSERT INTO calls (id, source, session_id, prompt_id, project, model, ts, input_tokens, "
                "output_tokens, cache_write_tokens, cache_read_tokens, cost_usd) "
                "VALUES (?, ?, ?, ?, ?, 'claude-opus-5', ?, 10, 10, 0, ?, ?)",
                (f"{pid}:{i}", source, session, pid, project, ts + i, ctx, cost / calls))
        self.conn.commit()


class Nudges(Base):
    def event(self, prompt, ctx=0, model="claude-opus-5", session="live"):
        t = self.root / f"t-{session}.jsonl"
        if ctx:
            _transcript(t, ctx, model)
        return {"prompt": prompt, "session_id": session, "cwd": "/x/alpha",
                "transcript_path": str(t) if ctx else None}

    def test_big_context_warns_once_until_it_grows(self):
        msgs = nudge.decide(self.event("add a test for the parser in src/p.py", ctx=320_000), self.conn)
        self.assertEqual(msgs[0][0], "context")
        self.assertIn("320k", msgs[0][1])
        self.assertIn("/clear", msgs[0][1])
        self.conn.execute("INSERT INTO nudges (ts, session_id, kind, message) VALUES (?, 'live', 'context', ?)",
                          (time.time(), msgs[0][1]))
        again = nudge.decide(self.event("next step in src/p.py", ctx=330_000), self.conn)
        self.assertFalse([k for k, _ in again if k == "context"])
        grown = nudge.decide(self.event("next step in src/p.py", ctx=450_000), self.conn)
        self.assertEqual(grown[0][0], "context")

    def test_broad_ask_uses_personal_history(self):
        self.add_prompt("b1", "implement all open things", calls=40, session="a")
        self.add_prompt("b2", "fix everything in the whole project", calls=60, session="b")
        self.add_prompt("n1", "rename foo in src/a.py", calls=4, session="c")
        msgs = nudge.decide(self.event("please implement all remaining items"), self.conn)
        self.assertEqual(msgs[0][0], "broad")
        self.assertIn("averaged 50 responses", msgs[0][1])

    def test_specific_prompts_are_left_alone(self):
        self.assertEqual(nudge.decide(self.event("implement all tests in src/parser.py"), self.conn), [])
        self.assertEqual(nudge.decide(self.event("/clear"), self.conn), [])

    def test_quick_question_on_expensive_model(self):
        msgs = nudge.decide(self.event("how do I reverse a list?", ctx=20_000, model="claude-fable-5"), self.conn)
        self.assertEqual(msgs[0][0], "model")
        self.assertIn("/model sonnet", msgs[0][1])
        none = nudge.decide(self.event("how do I reverse a list?", ctx=20_000, model="claude-sonnet-5",
                                       session="s2"), self.conn)
        self.assertEqual(none, [])

    def test_similar_expensive_prompt(self):
        self.add_prompt("old", "migrate the billing service to the new payments api and update tests",
                        calls=90, cost=9.0)
        msgs = nudge.decide(self.event("migrate the billing service to the new payments api"), self.conn)
        self.assertIn("similar", [k for k, _ in msgs])

    def test_main_is_silent_on_errors_and_internal_runs(self):
        import io
        import sys
        out = io.StringIO()
        with patch.object(sys, "stdin", io.StringIO("not json")), patch.object(sys, "stdout", out):
            nudge.main()
        self.assertEqual(out.getvalue(), "")
        with patch.dict(os.environ, {"TOKENCOACH_INTERNAL": "1"}), \
                patch.object(sys, "stdin", io.StringIO("{}")), patch.object(sys, "stdout", out):
            nudge.main()
        self.assertEqual(out.getvalue(), "")


class HookInstall(unittest.TestCase):
    def test_install_keeps_other_settings_and_uninstall_restores(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "settings.json")
            original = {"model": "opus", "hooks": {"UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": "other-hook.sh"}]}]}}
            with open(path, "w") as f:
                json.dump(original, f)
            nudge.install("/opt/tc", path)
            nudge.install("/opt/tc", path)              # idempotent
            with open(path) as f:
                s = json.load(f)
            self.assertEqual(s["model"], "opus")
            cmds = [h["command"] for e in s["hooks"]["UserPromptSubmit"] for h in e["hooks"]]
            self.assertEqual(len(cmds), 2)
            self.assertTrue(nudge.is_installed(path))
            self.assertTrue(os.path.exists(path + ".tokencoach-backup"))
            nudge.uninstall(path)
            with open(path) as f:
                self.assertEqual(json.load(f), original)
            self.assertFalse(nudge.is_installed(path))


class Lessons(Base):
    def test_evidence_caps_confidence(self):
        self.assertLess(coach.evidence_factor(2), coach.REVIEW)
        self.assertLess(coach.evidence_factor(6), coach.READY)
        self.assertGreaterEqual(coach.evidence_factor(8), coach.READY)

    def test_patterns_across_projects_become_one_global_lesson(self):
        for proj in ("a", "b", "c"):
            for s in range(3):
                self.add_prompt(f"{proj}{s}", "keep going", project=proj, session=f"{proj}-{s}", calls=85)
        coach.detect_lessons(self.conn)
        snap = coach.coach_snapshot(self.conn)
        long = [l for l in snap["lessons"] if l["title"] == "Keep sessions to one task"]
        self.assertEqual(len(long), 1)
        self.assertEqual(long[0]["scope"], "global")
        self.assertEqual(long[0]["evidence_n"], 9)
        self.assertEqual(long[0]["status"], "ready")

    def test_single_project_needs_repeated_evidence(self):
        self.add_prompt("x0", "go", project="solo", session="x0", calls=85)
        coach.detect_lessons(self.conn)
        self.assertEqual(coach.coach_snapshot(self.conn)["lessons"], [])
        self.add_prompt("x1", "go", project="solo", session="x1", calls=85)
        coach.detect_lessons(self.conn)
        (l,) = coach.coach_snapshot(self.conn)["lessons"]
        self.assertEqual((l["scope"], l["status"]), ("solo", "collecting"))

    def test_analysis_confidence_is_capped_by_cited_sessions(self):
        scopes = {1: {"session_id": "s1", "project": "alpha", "source": "claude_code"},
                  2: {"session_id": "s1", "project": "alpha", "source": "claude_code"}}
        coach.record_analysis_lessons(self.conn, [
            {"title": "Paths", "rule": "Ask for file paths first.", "scope": "alpha",
             "tools": "claude", "evidence_prompts": [1, 2, 99], "confidence": 0.99},
            {"title": "Unknown scope", "rule": "Be brief.", "scope": "nope", "evidence_prompts": []},
        ], scopes)
        rows = {r["title"]: dict(r) for r in self.conn.execute("SELECT * FROM lessons")}
        self.assertEqual(rows["Paths"]["evidence_n"], 1)              # same session twice, 99 invalid
        self.assertLessEqual(rows["Paths"]["confidence"], coach.evidence_factor(1))
        self.assertEqual(rows["Unknown scope"]["scope"], "global")


class ApplyToFiles(Base):
    def setUp(self):
        super().setUp()
        self.proj = self.root / "proj"
        self.proj.mkdir()
        (self.proj / "CLAUDE.md").write_text("# My project\n\nExisting guidance.\n")
        p = patch.object(coach, "BACKUP_DIR", str(self.root / "backups"))
        p.start()
        self.addCleanup(p.stop)
        # well before any before/after window
        self.add_prompt("p1", "hello", project="proj", cwd=str(self.proj), ts=time.time() - 90 * 86400)

    def lesson(self, lid, conf, rule="Keep sessions short.", tools="claude"):
        coach._upsert(self.conn, {"id": lid, "origin": "detector", "scope": "proj", "tools": tools,
                                  "title": lid, "rule": rule, "evidence": "e", "evidence_n": 9,
                                  "confidence": conf})

    def test_apply_writes_managed_block_and_keeps_user_text(self):
        self.lesson("l1", 0.97)
        files = coach.apply_lesson(self.conn, "l1")
        self.assertEqual(files, [str(self.proj / "CLAUDE.md")])
        text = (self.proj / "CLAUDE.md").read_text()
        self.assertTrue(text.startswith("# My project\n\nExisting guidance.\n"))
        self.assertIn(coach.BLOCK_START, text)
        self.assertIn("- Keep sessions short. <!-- l1 -->", text)
        self.assertTrue(os.listdir(self.root / "backups"))
        # a second lesson joins the same block; removing one keeps the other
        self.lesson("l2", 0.97, rule="Scope broad asks first.")
        coach.apply_lesson(self.conn, "l2")
        text = (self.proj / "CLAUDE.md").read_text()
        self.assertEqual(text.count(coach.BLOCK_START), 1)
        coach.unapply_lesson(self.conn, "l1")
        text = (self.proj / "CLAUDE.md").read_text()
        self.assertNotIn("Keep sessions short.", text)
        self.assertIn("Scope broad asks first.", text)
        coach.unapply_lesson(self.conn, "l2")
        self.assertEqual((self.proj / "CLAUDE.md").read_text(), "# My project\n\nExisting guidance.\n")

    def test_review_needs_confirmation_and_collecting_is_refused(self):
        self.lesson("r", 0.8)
        with self.assertRaises(ValueError):
            coach.apply_lesson(self.conn, "r")
        coach.apply_lesson(self.conn, "r", allow_review=True)
        self.lesson("c", 0.4)
        with self.assertRaises(ValueError):
            coach.apply_lesson(self.conn, "c", allow_review=True)

    def test_apply_ready_only_takes_confident_lessons(self):
        self.lesson("hi", 0.96)
        self.lesson("mid", 0.9, rule="Other.")
        coach.apply_ready(self.conn)
        text = (self.proj / "CLAUDE.md").read_text()
        self.assertIn("Keep sessions short.", text)
        self.assertNotIn("Other.", text)

    def test_codex_lessons_go_to_agents_md(self):
        self.add_prompt("c1", "x", project="proj", source="codex", cwd=str(self.proj))
        self.lesson("cx", 0.97, tools="codex")
        self.assertEqual(coach.apply_lesson(self.conn, "cx"), [str(self.proj / "AGENTS.md")])
        self.assertIn("Keep sessions short.", (self.proj / "AGENTS.md").read_text())

    def test_before_after(self):
        applied = time.time() - 5 * 86400
        for i in range(6):
            self.add_prompt(f"b{i}", "x", project="proj", session=f"b{i}", calls=10, cost=2.0,
                            ts=applied - 86400 - i * 100)
            self.add_prompt(f"a{i}", "x", project="proj", session=f"a{i}", calls=5, cost=1.0,
                            ts=applied + 3600 + i * 100)
        self.lesson("l1", 0.97)
        coach.apply_lesson(self.conn, "l1")
        self.conn.execute("UPDATE lessons SET applied_ts = ? WHERE id = 'l1'", (applied,))
        lesson = dict(self.conn.execute("SELECT * FROM lessons WHERE id = 'l1'").fetchone())
        im = coach.impact(self.conn, lesson)
        self.assertTrue(im["ready"])
        self.assertAlmostEqual(im["changes"]["responses_per_prompt"], -0.5, places=2)
        self.assertAlmostEqual(im["changes"]["cost_per_prompt"], -0.5, places=2)


class ImproveAndTemplates(Base):
    def test_improve_parses_and_caches(self):
        self.add_prompt("p1", "implement all the things", calls=40, cost=5.0)
        reply = 'Sure:\n{"rewrite": "Implement <item> in <file>.", "why": ["scoped"], "split": ["then tests"]}'
        with patch("tokencoach.optimizer.run_claude", return_value=reply) as rc:
            r = coach.improve_prompt(self.conn, "p1")
            self.assertEqual(r["rewrite"], "Implement <item> in <file>.")
            self.assertIn("Split into: then tests", r["why"])
            again = coach.improve_prompt(self.conn, "p1")
            self.assertTrue(again["cached"])
            self.assertEqual(rc.call_count, 1)

    def test_improve_rejects_unparseable_reply(self):
        self.add_prompt("p1", "x")
        with patch("tokencoach.optimizer.run_claude", return_value="no json here"):
            with self.assertRaises(RuntimeError):
                coach.improve_prompt(self.conn, "p1")

    def test_templates(self):
        tid = coach.save_template(self.conn, "Scoped change", "Change <x> in <file>.")
        self.assertEqual(coach.coach_snapshot(self.conn)["templates"][0]["title"], "Scoped change")
        coach.delete_template(self.conn, tid)
        self.assertEqual(coach.coach_snapshot(self.conn)["templates"], [])


class ListenerGuards(unittest.TestCase):
    def setUp(self):
        from tokencoach.server import DashboardServer
        self.srv = DashboardServer("s3cret", app=None, port=0).start()
        self.base = f"http://127.0.0.1:{self.srv.httpd.server_address[1]}"

    def tearDown(self):
        self.srv.stop()

    def req(self, path, method="GET", headers=None, body=None):
        r = urllib.request.Request(self.base + path, method=method, headers=headers or {},
                                   data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(r, timeout=5) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_page_needs_token(self):
        self.assertEqual(self.req("/")[0], 403)
        self.assertEqual(self.req("/?t=wrong")[0], 403)

    def test_actions_need_header_token_and_right_host(self):
        self.assertEqual(self.req("/api/lesson/dismiss", "POST", body={})[0], 403)
        code, _ = self.req("/api/lesson/dismiss", "POST", {"X-TokenCoach": "s3cret", "Host": "evil.test"}, {})
        self.assertEqual(code, 403)

    def test_unknown_action(self):
        code, body = self.req("/api/nope", "POST", {"X-TokenCoach": "s3cret"}, {})
        self.assertEqual(code, 404)

    def test_negative_content_length_is_refused(self):
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", self.srv.httpd.server_address[1], timeout=5)
        c.putrequest("POST", "/api/lesson/dismiss", skip_host=True)
        c.putheader("Host", f"127.0.0.1:{self.srv.httpd.server_address[1]}")
        c.putheader("X-TokenCoach", "s3cret")
        c.putheader("Content-Length", "-1")
        c.endheaders()
        self.assertEqual(c.getresponse().status, 400)     # answered, not left reading to EOF
        c.close()


if __name__ == "__main__":
    unittest.main()


class EditLessons(Base):
    def setUp(self):
        super().setUp()
        self.proj = self.root / "proj"
        self.proj.mkdir()
        p = patch.object(coach, "BACKUP_DIR", str(self.root / "backups"))
        p.start()
        self.addCleanup(p.stop)
        self.add_prompt("p1", "hello", project="proj", cwd=str(self.proj), ts=time.time() - 90 * 86400)
        coach.record_analysis_lessons(self.conn, [{
            "title": "Warn when session exceeds 30 responses",
            "rule": "After your 30th response in a session, suggest a fresh session.",
            "scope": "proj", "tools": "claude", "evidence_prompts": [1], "confidence": 0.75}],
            {1: {"session_id": "s1", "project": "proj", "source": "claude_code"}})
        self.lid = self.conn.execute("SELECT id FROM lessons").fetchone()[0]

    def test_edit_survives_refresh_and_marks_edited(self):
        coach.edit_lesson(self.conn, self.lid, title="Warn after 10 responses",
                          rule="After your 10th response in a session,\n suggest a fresh session.")
        # the same proposal arrives again from a later Analyze run
        coach.record_analysis_lessons(self.conn, [{
            "title": "Warn when session exceeds 30 responses",
            "rule": "After your 30th response in a session, suggest a fresh session.",
            "scope": "proj", "tools": "claude", "evidence_prompts": [1], "confidence": 0.75}],
            {1: {"session_id": "s1", "project": "proj", "source": "claude_code"}})
        (l,) = coach.coach_snapshot(self.conn)["lessons"]
        self.assertEqual(l["rule"], "After your 10th response in a session, suggest a fresh session.")
        self.assertEqual(l["title"], "Warn after 10 responses")
        self.assertEqual(l["edited"], 1)

    def test_editing_an_applied_lesson_rewrites_the_file(self):
        with self.assertRaises(ValueError):             # 1 session of evidence: still collecting
            coach.apply_lesson(self.conn, self.lid, allow_review=True)
        coach.edit_lesson(self.conn, self.lid, rule="After 30 responses, suggest a fresh session.")
        coach.apply_lesson(self.conn, self.lid, allow_review=True)   # your wording, your call
        coach.edit_lesson(self.conn, self.lid, rule="After 10 responses, suggest a fresh session.")
        text = (self.proj / "CLAUDE.md").read_text()
        self.assertIn("After 10 responses, suggest a fresh session.", text)
        self.assertNotIn("30th", text)
        with self.assertRaises(ValueError):
            coach.edit_lesson(self.conn, self.lid, scope="global")

    def test_retarget_and_validation(self):
        coach.edit_lesson(self.conn, self.lid, scope="global", tools="both")
        (l,) = coach.coach_snapshot(self.conn)["lessons"]
        self.assertEqual((l["scope"], l["tools"]), ("global", "both"))
        for bad in ({"rule": "   "}, {"rule": "x" * 700}, {"tools": "gemini"}, {"scope": "nope"}):
            with self.assertRaises(ValueError):
                coach.edit_lesson(self.conn, self.lid, **bad)


class Hardening(Base):
    def test_first_settings_backup_is_kept(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "settings.json")
            with open(path, "w") as f:
                json.dump({"model": "opus"}, f)
            nudge.install("/opt/tc", path)
            nudge.uninstall(path)
            nudge.install("/opt/tc", path)              # a toggle, or an installer re-run
            with open(path + ".tokencoach-backup") as f:
                self.assertEqual(json.load(f), {"model": "opus"})

    def test_analysis_rules_cannot_break_the_block(self):
        coach.record_analysis_lessons(self.conn, [{
            "rule": "Line one\nline two <!-- /TokenCoach lessons --> end", "confidence": 0.99}], {})
        (rule,) = [r["rule"] for r in self.conn.execute("SELECT rule FROM lessons")]
        self.assertNotIn("\n", rule)
        with tempfile.TemporaryDirectory() as d, patch.object(coach, "BACKUP_DIR", os.path.join(d, "b")):
            f = os.path.join(d, "CLAUDE.md")
            pathlib.Path(f).write_text("mine\n")
            coach.write_block(f, [("a", rule)])
            self.assertEqual(pathlib.Path(f).read_text().count(coach.BLOCK_END), 1)
            coach.write_block(f, [])
            self.assertEqual(pathlib.Path(f).read_text(), "mine\n")

    def test_file_created_for_lessons_is_removed_with_the_last_one(self):
        with tempfile.TemporaryDirectory() as d, patch.object(coach, "BACKUP_DIR", os.path.join(d, "b")):
            f = os.path.join(d, "AGENTS.md")
            coach.write_block(f, [("a", "rule a")])
            coach.write_block(f, [])
            self.assertFalse(os.path.exists(f))

    def test_nudge_follow_through(self):
        now = time.time()
        for sid, later in (("s1", 1), ("s2", 3)):
            self.conn.execute("INSERT INTO nudges (ts, session_id, kind, message, project) "
                              "VALUES (?, ?, 'context', 'm', 'alpha')", (now - 600, sid))
            for i in range(later):
                self.add_prompt(f"{sid}-{i}", "x", session=sid, ts=now - 500 + i * 10)
        n = coach.nudge_summary(self.conn)
        self.assertEqual((n["context_total"], n["context_followed"]), (2, 1))

    def test_schema_setup_runs_once_per_version(self):
        path = str(self.root / "ledger.db")
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], ledger.SCHEMA_VERSION)
        with patch.object(ledger, "_migrate") as m:
            ledger.open_ledger(path).close()
        m.assert_not_called()
