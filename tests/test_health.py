"""Health: the green / amber / red rules shared by the menu bar and dashboard."""

import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone

from tokencoach import health
from tokencoach.health import GOOD, WATCH, CRITICAL, UNKNOWN

NOW = 1_800_000_000.0
H, D = 3600, 86400


def w(provider, kind, left, reset_in, eta=None):
    return {"provider": provider, "kind": kind, "left": left, "reset_ts": NOW + reset_in,
            "reset_str": "", "eta_min": eta}


class WindowStateTest(unittest.TestCase):
    def state(self, win):
        return health.window_state(win, NOW)["state"]

    def test_five_hour_window(self):
        self.assertEqual(self.state(w("claude", "5h", 73, 2 * H)), GOOD)
        self.assertEqual(self.state(w("claude", "5h", 29, 2 * H)), WATCH)      # running low
        self.assertEqual(self.state(w("claude", "5h", 0, 2 * H)), CRITICAL)    # empty
        # on pace to empty 40 min from now, 2 h before the reset
        s = health.window_state(w("codex", "5h", 60, 2 * H, eta=40), NOW)
        self.assertEqual(s["state"], WATCH)
        self.assertAlmostEqual(s["runs_out"], NOW + 40 * 60)
        # the same pace is fine when the window resets first
        self.assertEqual(self.state(w("codex", "5h", 60, 30 * 60, eta=40)), GOOD)

    def test_weekly_pace_needs_margin_and_time(self):
        # half the week gone, 45% used: projects 90%, fine
        self.assertEqual(self.state(w("claude", "week", 55, 3.5 * D)), GOOD)
        # half the week gone, 60% used: projects 120%, runs out before the reset
        self.assertEqual(self.state(w("claude", "week", 40, 3.5 * D)), WATCH)
        # a busy first day doesn't count yet
        self.assertEqual(self.state(w("claude", "week", 80, 6.5 * D)), GOOD)
        # just over 100% is within the noise margin
        self.assertEqual(self.state(w("claude", "week", 47, 3.5 * D)), GOOD)
        self.assertEqual(self.state(w("claude", "week", 0, 2 * D)), CRITICAL)

    def test_quota_is_worst_of_its_windows(self):
        q = health.quota_health([w("claude", "5h", 73, 2 * H), w("codex", "5h", 0, H),
                                 w("claude", "week", 60, 3 * D)], NOW)
        self.assertEqual(q["state"], CRITICAL)
        self.assertEqual(q["now"]["state"], CRITICAL)
        self.assertEqual(q["week"]["state"], GOOD)
        self.assertEqual(q["providers"], {"claude": GOOD, "codex": CRITICAL})
        self.assertEqual(health.quota_health([], NOW)["state"], UNKNOWN)


class OverallTest(unittest.TestCase):
    def test_empty_window_names_the_alternative(self):
        q = health.quota_health([w("claude", "5h", 58, 2 * H), w("codex", "5h", 0, H)], NOW)
        o = health.overall(q, {"state": GOOD, "change": -0.3}, NOW)
        self.assertEqual(o["state"], CRITICAL)
        self.assertTrue(o["headline"].startswith("Codex is out until"))
        self.assertIn("Claude has 58% left", o["detail"])

    def test_an_amber_window_is_still_somewhere_to_work(self):
        q = health.quota_health([w("claude", "5h", 20, 2 * H), w("codex", "5h", 0, H)], NOW)
        self.assertIn("Claude has 20% left", health.overall(q, {"state": UNKNOWN}, NOW)["detail"])

    def test_pace_warning(self):
        q = health.quota_health([w("codex", "5h", 18, 2 * H + 600, eta=40)], NOW)
        o = health.overall(q, {"state": UNKNOWN}, NOW)
        self.assertEqual((o["state"], o["headline"]), (WATCH, "Slow down on Codex"))
        self.assertIn("about 40 min", o["detail"])

    def test_habits_alone_reach_amber_never_red(self):
        q = health.quota_health([w("claude", "5h", 90, 2 * H)], NOW)
        habits = {"state": WATCH, "change": 0.4, "tip": "Start fresh.", "lesson": {"id": "l1", "title": "T"}}
        o = health.overall(q, habits, NOW)
        self.assertEqual(o["state"], WATCH)
        self.assertIn("40% more", o["detail"])
        self.assertEqual(o["action"]["lesson"], "l1")

    def test_good_mentions_improvement(self):
        q = health.quota_health([w("claude", "5h", 90, 2 * H), w("codex", "5h", 80, 3 * H)], NOW)
        o = health.overall(q, {"state": GOOD, "change": -0.29}, NOW)
        self.assertEqual(o["headline"], "You're in good shape")
        self.assertIn("Claude and Codex", o["detail"])
        self.assertIn("29% less", o["detail"])

    def test_menu_line_only_when_quota_needs_attention(self):
        self.assertIsNone(health.menu_line(health.quota_health([w("claude", "5h", 90, H)], NOW), NOW))
        line = health.menu_line(health.quota_health([w("claude", "5h", 10, H)], NOW), NOW)
        self.assertTrue(line.startswith("Claude is running low"))


class WindowsFromAppStateTest(unittest.TestCase):
    def test_reads_claude_and_codex_rows_as_left(self):
        from tokencoach.providers import LimitRow, UsageData, ProviderData
        data = UsageData(session=LimitRow("5-hour", 27, "", NOW + H), weekly_all=LimitRow("Weekly", 40, "", NOW + D))
        chatgpt = ProviderData("ChatGPT")
        chatgpt._rows = [LimitRow("5-hour", 100, "", NOW + H), LimitRow("Weekly", 10, ""),
                         LimitRow("Code Review (5-hour)", 90, "")]
        ws = health.windows_from(data, [chatgpt], {})
        got = {(x["provider"], x["kind"]): x["left"] for x in ws}
        self.assertEqual(got, {("claude", "5h"): 73, ("claude", "week"): 60,
                               ("codex", "5h"): 0, ("codex", "week"): 90})

    def test_reset_epoch_parses_both_api_formats(self):
        from tokencoach.providers import _reset_epoch, _row
        self.assertEqual(_reset_epoch(1_800_000_000), 1_800_000_000.0)
        self.assertEqual(_reset_epoch("2027-01-15T08:00:00Z"),
                         datetime(2027, 1, 15, 8, tzinfo=timezone.utc).timestamp())
        self.assertIsNone(_reset_epoch("garbage"))
        self.assertIsNone(_reset_epoch(None))
        row = _row({"five_hour": {"utilization": 40, "resets_at": "2027-01-15T08:00:00+00:00"}}, "five_hour", "5-hour")
        self.assertEqual(row.reset_ts, datetime(2027, 1, 15, 8, tzinfo=timezone.utc).timestamp())

    def test_read_windows_ignores_stale_or_missing_files(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "usage.json")
            self.assertEqual(health.read_windows(path, NOW), ([], None))
            stamp = datetime.fromtimestamp(NOW - 60, tz=timezone.utc).isoformat()
            with open(path, "w") as f:
                json.dump({"updated_at": stamp, "windows": [w("claude", "5h", 50, H)]}, f)
            ws, ts = health.read_windows(path, NOW)
            self.assertEqual(len(ws), 1)
            self.assertEqual(health.read_windows(path, NOW + health.STALE_AFTER + 120)[0], [])


class HabitsTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("""CREATE TABLE calls (prompt_id, ts, project, estimated, cost_usd,
            input_tokens, cache_write_tokens, cache_read_tokens)""")

    def add(self, n, days_ago, cost, ctx=10_000, responses=1, tag="p"):
        for i in range(n):
            for r in range(responses):
                self.conn.execute("INSERT INTO calls VALUES (?,?,?,?,?,?,?,?)",
                                  (f"{tag}{days_ago}-{i}", NOW - days_ago * D + i + r, "proj", 0,
                                   cost / responses, 0, 0, ctx))

    def test_needs_enough_prompts(self):
        self.add(5, 1, 1.0)
        self.assertEqual(health.habits_health(self.conn, [], NOW)["state"], UNKNOWN)

    def test_cheaper_is_good_pricier_is_amber_with_a_tip(self):
        self.add(40, 20, 1.0, tag="u")
        self.add(20, 2, 0.7, tag="r")
        h = health.habits_health(self.conn, [], NOW)
        self.assertEqual(h["state"], GOOD)
        self.assertAlmostEqual(h["change"], -0.3, places=2)

        self.setUp()
        self.add(40, 20, 1.0, ctx=10_000, tag="u")
        self.add(20, 2, 1.5, ctx=40_000, tag="r")
        lessons = [{"id": "a", "title": "Collecting", "status": "collecting"},
                   {"id": "b", "title": "Keep sessions short", "status": "review"}]
        h = health.habits_health(self.conn, lessons, NOW)
        self.assertEqual(h["state"], WATCH)
        self.assertEqual(h["driver"], "context")
        self.assertEqual(h["lesson"]["id"], "b")
        self.assertEqual(len(h["series"]), 28)


if __name__ == "__main__":
    unittest.main()
