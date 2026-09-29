"""Usage ledger: parsing, dedupe, incremental ingest, quota attribution,
chat-export import, report and optimizer plumbing. Fixtures only - never the
owner's real logs."""
import os as _os
import tempfile as _tempfile

# Isolate from the real data folder before anything imports tokencoach.
_os.environ.setdefault("TOKENCOACH_DATA_DIR", _tempfile.mkdtemp(prefix="tokencoach-test-"))

import json
import os
import pathlib
import stat
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from tokencoach import ledger


def _jl(path, rows, mode="w"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, mode) as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _cc_user(uuid, text, ts, session="s1", cwd="/Users/x/Projects/alpha", **extra):
    return {"type": "user", "uuid": uuid, "sessionId": session, "cwd": cwd,
            "timestamp": ts, "message": {"role": "user", "content": text}, **extra}


def _cc_asst(mid, ts, session="s1", model="claude-sonnet-5", out=100, **usage):
    u = {"input_tokens": 10, "output_tokens": out, "cache_read_input_tokens": 1000,
         "cache_creation_input_tokens": 200,
         "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 200}}
    u.update(usage)
    return {"type": "assistant", "uuid": mid + "-u", "sessionId": session,
            "cwd": "/Users/x/Projects/alpha", "timestamp": ts,
            "message": {"id": mid, "role": "assistant", "model": model, "usage": u,
                        "content": [{"type": "text", "text": "ok"}]}}


def _codex_meta(session="c1", cwd="/Users/x/Projects/beta", parent=None):
    p = {"id": session, "session_id": session, "cwd": cwd}
    if parent:
        p["parent_thread_id"] = parent
    return {"timestamp": "2026-09-27T10:00:00Z", "type": "session_meta", "payload": p}


def _codex_turn(model="gpt-6-astra"):
    return {"timestamp": "2026-09-27T10:00:01Z", "type": "turn_context",
            "payload": {"model": model, "cwd": "/Users/x/Projects/beta", "turn_id": "t1"}}


def _codex_prompt(text, ts="2026-09-27T10:00:02Z", turn="t1", item="i1"):
    return {"timestamp": ts, "type": "event_msg", "payload": {
        "type": "item_completed", "turn_id": turn,
        "item": {"type": "UserMessage", "id": item, "content": [{"type": "text", "text": text}]}}}


def _codex_record(rid, ts, inp=1000, cached=800, out=50):
    return {"timestamp": ts, "type": "token_usage_record", "payload": {
        "response_id": rid, "usage": {"input_tokens": inp, "cached_input_tokens": cached,
                                      "cache_write_input_tokens": 0, "output_tokens": out,
                                      "reasoning_output_tokens": 10}}}


def _codex_count(ts, pct5, pctw, inp=1000, cached=800, out=50, ordinal=0):
    return {"timestamp": ts, "ordinal": ordinal, "type": "event_msg", "payload": {
        "type": "token_count",
        "info": {"last_token_usage": {"input_tokens": inp, "cached_input_tokens": cached,
                                      "output_tokens": out, "reasoning_output_tokens": 0}},
        "rate_limits": {"limit_id": "codex",
                        "primary": {"used_percent": pct5, "window_minutes": 300},
                        "secondary": {"used_percent": pctw, "window_minutes": 10080}}}}


class LedgerTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.conn = ledger.open_ledger(str(self.root / "ledger.db"))
        self.sources = [
            ("claude_code", str(self.root / "claude/**/*.jsonl"), ledger.parse_claude_code),
            ("cowork", str(self.root / "cowork/**/audit.jsonl"), ledger.parse_cowork),
            ("codex", str(self.root / "codex/**/*.jsonl"), ledger.parse_codex),
        ]
        # never touch the owner's real quota history
        patcher = patch.object(ledger, "import_claude_samples", lambda conn: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def ingest(self, **kw):
        return ledger.ingest(self.conn, sources=self.sources, **kw)

    def calls(self):
        return [dict(r) for r in self.conn.execute("SELECT * FROM calls ORDER BY ts, id")]


class Pricing(unittest.TestCase):
    def test_sonnet5_cost_with_1h_cache_write(self):
        # 10 in, 100 out, 200 1h-write, 1000 read at $2/$10
        cost = ledger.call_cost("claude-sonnet-5", 10, 100, 0, 200, 1000)
        expected = (10 * 2 + 100 * 10 + 200 * 4 + 1000 * 0.2) / 1e6
        self.assertAlmostEqual(cost, expected)

    def test_longest_prefix_wins(self):
        self.assertEqual(ledger._price_for("claude-opus-5-5")["in"], 4.0)
        self.assertEqual(ledger._price_for("claude-opus-5")["in"], 5.0)
        self.assertEqual(ledger._price_for("claude-haiku-4-5-20251001")["in"], 1.0)

    def test_openai_list_prices(self):
        # gpt-6-astra: $10 in, $1 cached, $50 out
        self.assertAlmostEqual(ledger.call_cost("gpt-6-astra", 100_000, 10_000, 0, 0, 100_000),
                               (100_000 * 10 + 10_000 * 50 + 100_000 * 1) / 1e6)
        self.assertAlmostEqual(ledger.call_cost("gpt-5.6-terra", 200_000, 0, 0, 0, 0), 0.4)
        self.assertAlmostEqual(ledger.call_cost("gpt-5.4-mini", 0, 1_000_000, 0, 0, 0), 4.5)
        self.assertIsNone(ledger.equivalent_model("gpt-5.6-sol"))      # has a real price
        self.assertIsNone(ledger.call_cost("unknown", 1, 1, 0, 0, 0))

    def test_long_context_rates_apply_to_the_whole_request(self):
        short = ledger.call_cost("gpt-5.6-sol", 200_000, 0, 0, 0, 0)
        long = ledger.call_cost("gpt-5.6-sol", 300_000, 0, 0, 0, 0)
        self.assertAlmostEqual(short, 0.8)          # $4 / M
        self.assertAlmostEqual(long, 2.4)           # $8 / M for all 300k

    def test_unpublished_models_use_a_labelled_sibling(self):
        self.assertEqual(ledger.equivalent_model("codex-auto-review"), "gpt-5.4-mini")
        self.assertEqual(ledger.equivalent_model("gpt-5.7-luna"), "gpt-5.6-luna")
        self.assertEqual(ledger.equivalent_model("gpt-6-nova"), "gpt-6-astra")
        self.assertIsNone(ledger.equivalent_model("claude-sonnet-5"))

    def test_user_prices_and_equivalents_win(self):
        o = ledger.ledger_overrides({
            "ledger_prices": {"gpt-6": {"in": 3.0, "out": 9.0}},
            "ledger_model_equivalents": {"codex-auto-review": "gpt-5.6-luna", "bad": "nope"}})
        self.assertAlmostEqual(ledger.call_cost("gpt-6-astra", 1_000_000, 0, 0, 0, 0, o), 3.0)
        self.assertEqual(ledger.equivalent_model("codex-auto-review", o), "gpt-5.6-luna")
        self.assertNotIn("bad", o[ledger.EQUIVALENTS_KEY])


class Repricing(LedgerTestCase):
    def test_changed_mapping_reprices_codex_but_not_claude(self):
        _jl(self.root / "codex/2026/09/27/rollout-a.jsonl", [
            _codex_meta(), _codex_turn("gpt-5.6-sol"), _codex_prompt("go"),
            _codex_record("r1", "2026-09-27T10:00:05Z", inp=200_000, cached=0, out=0)])
        _jl(self.root / "claude/p/s1.jsonl", [_cc_user("u1", "hi", "2026-09-27T10:00:00Z"),
                                            _cc_asst("m1", "2026-09-27T10:00:01Z")])
        self.ingest()
        cost = lambda i: self.conn.execute("SELECT cost_usd FROM calls WHERE id = ?", (i,)).fetchone()[0]
        self.assertAlmostEqual(cost("openai:r1"), 0.8)          # gpt-5.6-sol list price
        claude_before = cost("anthropic:m1")
        ledger.reprice(self.conn, ledger.ledger_overrides(
            {"ledger_prices": {"gpt-5.6-sol": {"in": 1.0, "out": 1.0}}}))
        self.assertAlmostEqual(cost("openai:r1"), 0.2)          # user price wins
        self.assertEqual(cost("anthropic:m1"), claude_before)

    def cost(self, i):
        return self.conn.execute("SELECT cost_usd FROM calls WHERE id = ?", (i,)).fetchone()[0]

    def test_claude_price_override_reprices_past_calls_with_their_cache_split(self):
        _jl(self.root / "claude/p/s1.jsonl", [_cc_user("u1", "hi", "2026-09-27T10:00:00Z"),
                                            _cc_asst("m1", "2026-09-27T10:00:01Z")])
        self.ingest()
        ledger.reprice(self.conn, ledger.ledger_overrides(
            {"ledger_prices": {"claude-sonnet-5": {"in": 1.0, "out": 1.0}}}))
        # 10 in, 100 out, 200 written with the 1-hour TTL (2x input), 1000 read (0.1x)
        self.assertAlmostEqual(self.cost("anthropic:m1"), (10 + 100 + 200 * 2 + 1000 * 0.1) / 1e6)

    def test_claude_calls_without_a_known_split_keep_their_cost(self):
        _jl(self.root / "claude/p/s1.jsonl", [_cc_user("u1", "hi", "2026-09-27T10:00:00Z"),
                                            _cc_asst("m1", "2026-09-27T10:00:01Z")])
        self.ingest()
        self.conn.execute("UPDATE calls SET cache_write_1h_tokens = NULL")
        before = self.cost("anthropic:m1")
        ledger.reprice(self.conn, ledger.ledger_overrides(
            {"ledger_prices": {"claude-sonnet-5": {"in": 1.0, "out": 1.0}}}))
        self.assertEqual(self.cost("anthropic:m1"), before)

    def test_upgrade_rereads_logs_to_fill_in_the_cache_split(self):
        _jl(self.root / "claude/p/s1.jsonl", [_cc_user("u1", "hi", "2026-09-27T10:00:00Z"),
                                            _cc_asst("m1", "2026-09-27T10:00:01Z", out=5),
                                            _cc_asst("m1", "2026-09-27T10:00:01Z", out=300)])
        self.ingest()
        # a ledger from before the column: split unknown, marker absent
        self.conn.execute("UPDATE calls SET cache_write_1h_tokens = NULL")
        self.conn.execute("DELETE FROM meta WHERE key = 'cache_1h_backfilled'")
        self.conn.execute("PRAGMA user_version = 0")
        self.conn.commit()
        self.conn.close()
        self.conn = ledger.open_ledger(str(self.root / "ledger.db"))
        self.ingest()
        [call] = self.calls()
        self.assertEqual((call["output_tokens"], call["cache_write_1h_tokens"]), (300, 200))


class ClaudeCodeIngest(LedgerTestCase):
    def test_prompts_calls_and_linking(self):
        _jl(self.root / "claude/p/s1.jsonl", [
            _cc_user("u1", "refactor the parser", "2026-09-27T10:00:00Z"),
            _cc_asst("m1", "2026-09-27T10:00:05Z"),
            {"type": "user", "uuid": "u2", "sessionId": "s1", "timestamp": "2026-09-27T10:00:06Z",
             "toolUseResult": {"ok": 1},
             "message": {"role": "user", "content": [{"type": "tool_result", "content": "x"}]}},
            _cc_asst("m2", "2026-09-27T10:00:09Z"),
            _cc_user("u3", "[Request interrupted by user]", "2026-09-27T10:00:10Z"),
            _cc_user("u4", "now add tests", "2026-09-27T10:01:00Z"),
            _cc_asst("m3", "2026-09-27T10:01:05Z"),
        ])
        self.ingest()
        prompts = [r["text"] for r in self.conn.execute("SELECT text FROM prompts ORDER BY ts")]
        self.assertEqual(prompts, ["refactor the parser", "now add tests"])
        calls = self.calls()
        self.assertEqual(len(calls), 3)
        self.assertEqual([c["prompt_id"] for c in calls], ["cc:u1", "cc:u1", "cc:u4"])
        self.assertEqual(calls[0]["project"], "alpha")
        self.assertIsNotNone(calls[0]["cost_usd"])

    def test_duplicate_lines_count_once_keeping_largest(self):
        _jl(self.root / "claude/p/s1.jsonl", [
            _cc_user("u1", "hi", "2026-09-27T10:00:00Z"),
            _cc_asst("m1", "2026-09-27T10:00:01Z", out=5),
            _cc_asst("m1", "2026-09-27T10:00:01Z", out=300),
            _cc_asst("m1", "2026-09-27T10:00:01Z", out=300),
        ])
        self.ingest()
        calls = self.calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["output_tokens"], 300)

    def test_duplicate_lines_keep_one_line_whole(self):
        # tokens and cost must describe the same line, not a mix of two
        _jl(self.root / "claude/p/s1.jsonl", [
            _cc_user("u1", "hi", "2026-09-27T10:00:00Z"),
            _cc_asst("m1", "2026-09-27T10:00:01Z", out=5, input_tokens=1),
            _cc_asst("m1", "2026-09-27T10:00:01Z", out=300, input_tokens=40),
        ])
        self.ingest()
        [call] = self.calls()
        self.assertEqual((call["input_tokens"], call["output_tokens"]), (40, 300))
        self.assertAlmostEqual(call["cost_usd"],
                               ledger.call_cost("claude-sonnet-5", 40, 300, 0, 200, 1000))

    def test_ledger_files_are_private(self):
        path = self.root / "ledger.db"
        for p in (path, pathlib.Path(str(path) + "-wal")):
            if p.exists():
                self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600, p)

    def test_subagent_transcript_links_to_parent_prompt(self):
        _jl(self.root / "claude/p/s1.jsonl", [_cc_user("u1", "research X", "2026-09-27T10:00:00Z")])
        _jl(self.root / "claude/p/s1/subagents/agent-a.jsonl", [
            _cc_user("sub-u", "subagent task", "2026-09-27T10:00:02Z", isSidechain=True),
            _cc_asst("m-sub", "2026-09-27T10:00:05Z"),
        ])
        self.ingest()
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM prompts").fetchone()[0], 1)
        self.assertEqual(self.calls()[0]["prompt_id"], "cc:u1")

    def test_incremental_offsets_and_partial_lines(self):
        path = self.root / "claude/p/s1.jsonl"
        _jl(path, [_cc_user("u1", "one", "2026-09-27T10:00:00Z"),
                   _cc_asst("m1", "2026-09-27T10:00:01Z")])
        self.assertEqual(self.ingest()["calls"], 1)
        self.assertEqual(self.ingest()["calls"], 0)       # nothing new
        with open(path, "a") as f:                        # a line still being written
            f.write(json.dumps(_cc_asst("m2", "2026-09-27T10:00:02Z"))[:40])
        self.assertEqual(self.ingest()["calls"], 0)
        with open(path, "a") as f:
            f.write(json.dumps(_cc_asst("m2", "2026-09-27T10:00:02Z"))[40:] + "\n")
        self.assertEqual(self.ingest()["calls"], 1)
        self.assertEqual(len(self.calls()), 2)

    def test_time_budget_resumes(self):
        for i in range(3):
            _jl(self.root / f"claude/p/s{i}.jsonl", [
                _cc_user(f"u{i}", "x", "2026-09-27T10:00:00Z", session=f"s{i}"),
                _cc_asst(f"m{i}", "2026-09-27T10:00:01Z", session=f"s{i}")])
        first = self.ingest(time_budget=-1)
        self.assertFalse(first["complete"])
        self.ingest()
        self.assertEqual(len(self.calls()), 3)


class CoworkIngest(LedgerTestCase):
    def test_audit_log(self):
        _jl(self.root / "cowork/org/acct/local_1/audit.jsonl", [
            {"type": "system", "subtype": "init", "session_id": "w1",
             "cwd": "/Users/x/Library/Application Support/Claude/local-agent-mode-sessions/a/b"},
            {"type": "user", "uuid": "wu1", "session_id": "w1", "parent_tool_use_id": None,
             "timestamp": "2026-09-27T09:00:00Z", "message": {"role": "user", "content": "plan my week"}},
            {**_cc_asst("wm1", "2026-09-27T09:00:03Z", model="claude-fable-5"), "session_id": "w1"},
            {**_cc_asst("wm1", "2026-09-27T09:00:03Z", model="claude-fable-5"), "session_id": "w1"},
            {"type": "user", "uuid": "wu2", "session_id": "w1", "parent_tool_use_id": "toolu_1",
             "timestamp": "2026-09-27T09:00:04Z", "message": {"role": "user", "content": "subtask"}},
        ])
        self.ingest()
        calls = self.calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["source"], "cowork")
        self.assertEqual(calls[0]["project"], "cowork")
        self.assertEqual(calls[0]["prompt_id"], "cowork:wu1")


class CodexIngest(LedgerTestCase):
    def test_records_are_not_double_counted_with_token_count(self):
        _jl(self.root / "codex/2026/09/27/rollout-a.jsonl", [
            _codex_meta(), _codex_turn(), _codex_prompt("fix the build"),
            _codex_record("r1", "2026-09-27T10:00:05Z"),
            _codex_count("2026-09-27T10:00:05Z", 10, 2),
            _codex_record("r2", "2026-09-27T10:00:09Z"),
            _codex_count("2026-09-27T10:00:09Z", 12, 2),
        ])
        self.ingest()
        calls = self.calls()
        self.assertEqual(len(calls), 2)
        c = calls[0]
        self.assertEqual(c["input_tokens"], 200)        # 1000 total minus 800 cached
        self.assertEqual(c["cache_read_tokens"], 800)
        self.assertEqual(c["model"], "gpt-6-astra")
        self.assertEqual(c["project"], "beta")
        self.assertIsNotNone(c["prompt_id"])
        self.assertIsNotNone(c["cost_usd"])              # priced at the Claude-tier equivalent

    def test_older_logs_use_token_count(self):
        _jl(self.root / "codex/2026/06/01/rollout-old.jsonl", [
            _codex_meta("old"), _codex_turn("gpt-5.5"), _codex_prompt("hello"),
            _codex_count("2026-06-01T10:00:05Z", 5, 1, ordinal=4),
            _codex_count("2026-06-01T10:00:08Z", 6, 1, ordinal=7),
        ])
        self.ingest()
        self.assertEqual(len(self.calls()), 2)

    def test_subthread_prompts_are_not_owner_prompts(self):
        _jl(self.root / "codex/2026/09/27/rollout-review.jsonl", [
            _codex_meta("rev", parent="c1"), _codex_turn("codex-auto-review"),
            _codex_prompt("The following is the Codex agent history..."),
            _codex_record("rr", "2026-09-27T10:00:05Z"),
        ])
        self.ingest()
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM prompts").fetchone()[0], 0)
        self.assertEqual(len(self.calls()), 1)


class QuotaAttribution(unittest.TestCase):
    def _inc(self, pcts, level=None):
        return [d for _, _, d in
                ledger._increments_list(list(enumerate(pcts)), level)[0]]

    def test_rises_are_counted(self):
        self.assertEqual(self._inc([10, 12, 15]), [2, 3])

    def test_stale_dip_is_not_double_counted(self):
        # a parallel session reports 73 after 74; the next real 75 adds only 1
        self.assertEqual(self._inc([72, 74, 73, 75]), [2, 1])

    def test_reset_counts_new_window_usage(self):
        self.assertEqual(self._inc([80, 95, 4, 9]), [15, 4, 5])

    def test_level_carries_over_between_passes(self):
        out, level = ledger._increments_list([(0, 50), (1, 55)], None)
        self.assertEqual(level, 55)
        out, _ = ledger._increments_list([(1, 55), (2, 54), (3, 57)], level)
        self.assertEqual([d for _, _, d in out], [2])


class CodexQuotaEndToEnd(LedgerTestCase):
    def test_each_response_gets_its_quota_delta(self):
        _jl(self.root / "codex/2026/09/27/rollout-a.jsonl", [
            _codex_meta(), _codex_turn(), _codex_prompt("do it"),
            _codex_record("r1", "2026-09-27T10:00:05Z"),
            _codex_count("2026-09-27T10:00:05Z", 10, 2),
            _codex_record("r2", "2026-09-27T10:00:09Z"),
            _codex_count("2026-09-27T10:00:09Z", 13, 3),
            _codex_record("r3", "2026-09-27T10:00:20Z"),
            _codex_count("2026-09-27T10:00:20Z", 12, 3),   # stale dip
        ])
        self.ingest()
        q = {c["id"]: c["quota_5h_pct"] for c in self.calls()}
        self.assertIsNone(q["openai:r1"])        # first sample is the baseline
        self.assertAlmostEqual(q["openai:r2"], 3.0)
        self.assertEqual(q["openai:r3"], 0)     # sampled, no rise: measured as nothing
        # appending more samples later keeps the level; no double count
        _jl(self.root / "codex/2026/09/27/rollout-a.jsonl", [
            _codex_record("r4", "2026-09-27T10:00:30Z"),
            _codex_count("2026-09-27T10:00:30Z", 14, 3),
        ], mode="a")
        self.ingest()
        q = {c["id"]: c["quota_5h_pct"] for c in self.calls()}
        self.assertAlmostEqual(q["openai:r4"], 1.0)
        self.assertAlmostEqual(sum(v or 0 for v in q.values()), 4.0)

    def test_claude_interval_shared_by_cost(self):
        _jl(self.root / "claude/p/s1.jsonl", [
            _cc_user("u1", "go", "2026-09-27T10:00:00Z"),
            _cc_asst("m1", "2026-09-27T10:01:00Z", out=100),
            _cc_asst("m2", "2026-09-27T10:02:00Z", out=300),
        ])
        self.ingest()
        base = ledger._ts("2026-09-27T10:00:30Z")
        self.conn.executemany(
            "INSERT INTO quota_samples VALUES ('claude','5h',?,?)",
            [(base, 20), (base + 300, 30)])
        ledger.attribute_quota(self.conn)
        q = {c["id"]: c["quota_5h_pct"] for c in self.calls()}
        self.assertAlmostEqual(sum(q.values()), 10.0)
        self.assertGreater(q["anthropic:m2"], q["anthropic:m1"])

    def _two_calls_with_samples(self, samples):
        _jl(self.root / "claude/p/s1.jsonl", [
            _cc_user("u1", "go", "2026-09-27T10:00:00Z"),
            _cc_asst("m1", "2026-09-27T10:01:00Z"),
            _cc_asst("m2", "2026-09-27T10:02:00Z"),
        ])
        self.ingest()
        base = ledger._ts("2026-09-27T10:00:00Z")
        self.conn.executemany("INSERT INTO quota_samples VALUES ('claude','5h',?,?)",
                              [(base + dt, pct) for dt, pct in samples])
        ledger.attribute_quota(self.conn)
        return {c["id"]: c["quota_5h_pct"] for c in self.calls()}

    def test_flat_sampled_interval_is_zero_not_unknown(self):
        q = self._two_calls_with_samples([(30, 20), (300, 20)])
        self.assertEqual(q, {"anthropic:m1": 0, "anthropic:m2": 0})

    def test_calls_outside_sampled_intervals_stay_unknown(self):
        # before the first sample, and across a gap too long to attribute
        q = self._two_calls_with_samples([(90, 20), (90 + ledger.MAX_SAMPLE_GAP + 1, 20)])
        self.assertIsNone(q["anthropic:m1"])
        self.assertIsNone(q["anthropic:m2"])

    def test_flat_then_rise_only_the_rise_carries_quota(self):
        q = self._two_calls_with_samples([(30, 20), (90, 20), (150, 25)])
        self.assertEqual(q["anthropic:m1"], 0)
        self.assertAlmostEqual(q["anthropic:m2"], 5.0)

    def test_older_attribution_is_redone(self):
        self._two_calls_with_samples([(30, 20), (300, 20)])
        self.conn.execute("UPDATE calls SET quota_5h_pct = NULL")
        ledger._meta_set(self.conn, "attribution_version", "2")
        ledger.attribute_quota(self.conn)
        self.assertEqual([c["quota_5h_pct"] for c in self.calls()], [0, 0])


class Summaries(LedgerTestCase):
    def test_today_summary_and_top_prompt(self):
        import time as _t
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _jl(self.root / "claude/p/s1.jsonl", [
            _cc_user("u1", "cheap question", now),
            _cc_asst("m1", now, out=10),
            _cc_user("u2", "expensive refactor", now, session="s2"),
            _cc_asst("m2", now, session="s2", model="claude-opus-5", out=5000),
        ])
        self.ingest()
        s = ledger.today_summary(self.conn)
        self.assertEqual(s["prompts"], 2)
        self.assertEqual(s["top_prompt"]["text"], "expensive refactor")
        self.assertEqual(s["top_project"]["project"], "alpha")
        self.assertGreater(s["cost"], 0)
        _ = _t

    def test_menu_lines(self):
        from tokencoach.ui import _ledger_menu_lines
        self.assertIn("Indexing", _ledger_menu_lines(None, "")[0])
        lines = _ledger_menu_lines({
            "cost": 1.5, "prompts": 3, "tokens": 2_000_000, "calls": 4,
            "top_project": {"project": "alpha", "cost": 1.2},
            "top_prompt": {"text": "a very long prompt " * 10, "cost": 0.9},
        }, "")
        self.assertIn("$1.50", lines[0])
        self.assertIn("2.0M", lines[0])
        self.assertIn("alpha", lines[1])
        self.assertLess(len(lines[2]), 70)


class ReportAndOptimizer(LedgerTestCase):
    def _seed(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _jl(self.root / "claude/p/s1.jsonl", [
            _cc_user("u1", "summarise <this> & that", now),
            _cc_asst("m1", now, out=500),
        ])
        self.ingest()

    def test_dashboard_provider_filter_always_starts_on_all(self):
        # The app serves the dashboard on a fixed port, so localStorage outlives
        # every launch. Restoring the saved controls must not bring back an old
        # "Claude" pick, which would hide ChatGPT/Codex and its warnings.
        from tokencoach.ledger_report import DASHBOARD_JS
        restore = DASHBOARD_JS.index("localStorage.getItem('tokencoach-dash')")
        reset = DASHBOARD_JS.index("S.group = DEFAULT.group")
        self.assertGreater(reset, restore)
        self.assertIn("group:'all'", DASHBOARD_JS)

    def test_dashboard_escape_covers_single_quotes(self):
        from tokencoach.ledger_report import DASHBOARD_JS
        esc = next(l for l in DASHBOARD_JS.splitlines() if l.startswith("const esc ="))
        self.assertIn("&#39;", esc)

    def test_dashboard_renders_and_embeds_data_safely(self):
        from tokencoach.ledger_report import build_report, dashboard_data
        empty = build_report(self.conn, {})
        self.assertIn("<title>TokenCoach</title>", empty)
        self._seed()
        _jl(self.root / "claude/p/s1.jsonl", [_cc_user("u9", "</script><b>x", "2026-09-27T10:00:00Z")], mode="a")
        self.ingest()
        page = build_report(self.conn, {"ledger_plans": {"claude": 200}})
        # the JSON blob must not be able to close its <script> tag
        blob = page.split('<script type="application/json" id="data">', 1)[1].split("</script>", 1)[0]
        self.assertNotIn("</", blob)
        data = json.loads(blob.replace("<\\/", "</"))
        self.assertEqual(data["plans"], {"claude": 200})
        self.assertEqual(len(data["prompts"]), 1)          # u9 has no response: not shown
        self.assertEqual(data["prompts"][0][5], "summarise <this> & that")
        self.assertEqual(data["facts"][0][12], 1)          # first fact marks the prompt
        self.assertIn(data["models"][0], ("claude-sonnet-5",))
        _ = dashboard_data

    def test_orphan_calls_get_a_placeholder_prompt(self):
        from tokencoach.ledger_report import dashboard_data
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _jl(self.root / "claude/p/s5.jsonl", [_cc_asst("lone", now, session="s5")])
        self.ingest()
        d = dashboard_data(self.conn)
        self.assertTrue(d["prompts"][0][5].startswith("(no prompt recorded"))
        self.assertEqual(d["facts"][0][12], 0)             # not counted as a prompt

    def test_open_file_prefers_configured_then_chrome(self):
        from tokencoach import ledger_report
        with patch.object(ledger_report.os.path, "exists", side_effect=lambda p: "Google Chrome" in p), \
                patch.object(ledger_report.subprocess, "Popen") as popen:
            ledger_report.open_file("/tmp/x.html")
            popen.assert_called_once_with(["open", "-a", "Google Chrome", "/tmp/x.html"])
        with patch.object(ledger_report.os.path, "exists", return_value=False), \
                patch.object(ledger_report.subprocess, "Popen") as popen:
            ledger_report.open_file("/tmp/x.html")
            popen.assert_called_once_with(["open", "/tmp/x.html"])

    def test_digest_excludes_optimizer_runs(self):
        from tokencoach.optimizer import build_digest
        self._seed()
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _jl(self.root / "claude/o/s9.jsonl", [
            _cc_user("o1", "You are reviewing one person's AI usage", now, session="s9",
                     cwd="/x/" + ledger.OPTIMIZER_PROJECT),
            _cc_asst("om1", now, session="s9", out=9000, model="claude-opus-5"),
        ])
        self.ingest()
        digest = build_digest(self.conn)
        self.assertIn("summarise <this> & that", digest)
        self.assertNotIn("You are reviewing", digest)

    def test_run_optimizer_with_fake_cli(self):
        from tokencoach import optimizer, ledger_report
        self._seed()
        fake = self.root / "fake-claude"
        fake.write_text("#!/bin/sh\ncat > /dev/null\necho '## Biggest wins'\necho '- **Start new sessions** sooner'\n")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        reports = self.root / "reports"
        with patch.object(optimizer, "find_claude_cli", return_value=str(fake)), \
                patch.object(optimizer, "REPORT_DIR", str(reports)), \
                patch.object(optimizer, "OPTIMIZER_DIR", str(self.root / "opt")):
            path = optimizer.run_optimizer(self.conn)
            html = pathlib.Path(path).read_text()
            self.assertIn("<h2>Biggest wins</h2>", html)
            self.assertIn("<strong>Start new sessions</strong>", html)
            self.assertTrue(optimizer.latest_report().endswith(".md"))
        _ = ledger_report

    def test_optimizer_reports_missing_cli(self):
        from tokencoach import optimizer
        with patch.object(optimizer, "find_claude_cli", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "not found"):
                optimizer.run_optimizer(self.conn)


class ChatImport(LedgerTestCase):
    def test_claude_export_zip(self):
        from tokencoach.chat_import import import_export
        conv = [{"uuid": "cv1", "name": "Trip plan", "chat_messages": [
            {"sender": "human", "text": "a" * 400, "created_at": "2026-09-01T10:00:00Z"},
            {"sender": "assistant", "text": "b" * 800, "created_at": "2026-09-01T10:00:10Z"},
            {"sender": "human", "text": "c" * 40, "created_at": "2026-09-01T10:01:00Z"},
            {"sender": "assistant", "text": "d" * 80, "created_at": "2026-09-01T10:01:10Z"},
        ]}]
        zpath = self.root / "export.zip"
        with zipfile.ZipFile(zpath, "w") as z:
            z.writestr("conversations.json", json.dumps(conv))
        res = import_export(self.conn, str(zpath))
        self.assertEqual((res["source"], res["prompts"], res["replies"]), ("claude_chat", 2, 2))
        calls = self.calls()
        self.assertEqual(calls[0]["input_tokens"], 100)          # 400 chars / 4
        self.assertEqual(calls[1]["input_tokens"], 100 + 200 + 10)  # whole history re-read
        self.assertTrue(all(c["estimated"] == 1 for c in calls))
        # estimates stay out of "today"
        self.assertEqual(ledger.today_summary(self.conn)["calls"], 0)
        # re-import is idempotent
        import_export(self.conn, str(zpath))
        self.assertEqual(len(self.calls()), 2)

    def test_chatgpt_export_follows_current_branch(self):
        from tokencoach.chat_import import import_export
        conv = [{"id": "g1", "title": "Code help", "current_node": "a2", "mapping": {
            "root": {"message": None, "parent": None},
            "u1": {"parent": "root", "message": {"author": {"role": "user"}, "create_time": 1.0,
                                                 "content": {"parts": ["hello there"]}}},
            "a1": {"parent": "u1", "message": {"author": {"role": "assistant"}, "create_time": 2.0,
                                               "content": {"parts": ["old branch"]},
                                               "metadata": {"model_slug": "gpt-5"}}},
            "a2": {"parent": "u1", "message": {"author": {"role": "assistant"}, "create_time": 3.0,
                                               "content": {"parts": ["new branch reply"]},
                                               "metadata": {"model_slug": "gpt-5"}}},
        }}]
        path = self.root / "conversations.json"
        path.write_text(json.dumps(conv))
        res = import_export(self.conn, str(path))
        self.assertEqual((res["source"], res["prompts"], res["replies"]), ("chatgpt_chat", 1, 1))
        self.assertEqual(self.calls()[0]["model"], "gpt-5")

    def test_rejects_unknown_file(self):
        from tokencoach.chat_import import import_export
        path = self.root / "other.json"
        path.write_text(json.dumps([{"foo": 1}]))
        with self.assertRaises(ValueError):
            import_export(self.conn, str(path))


class MarkdownRendering(unittest.TestCase):
    def test_basic_blocks_and_escaping(self):
        from tokencoach.optimizer import markdown_to_html
        html = markdown_to_html("## Wins\n1. **Bold** <x>\n2. `code`\n\nplain para")
        self.assertIn("<h2>Wins</h2>", html)
        self.assertIn("<ol>", html)
        self.assertIn("<strong>Bold</strong> &lt;x&gt;", html)
        self.assertIn("<code>code</code>", html)
        self.assertIn("<p>plain para</p>", html)


if __name__ == "__main__":
    unittest.main()
