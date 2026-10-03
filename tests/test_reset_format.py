"""Regression tests for reset-time formatting.

Two bugs fixed together:

1. Under-20h resets rendered as a relative countdown ("resets in 4h 12m"),
   inconsistent with the weekly cap's absolute "resets Mon 18:59" - and a
   countdown goes stale the moment it's read.

2. The shared formatter never converted the API's UTC timestamp to local
   time before formatting, so the printed clock time was silently wrong by
   the local UTC offset - not merely relative, wrong. A UTC+2 reader saw a
   21:00 reset labeled 19:00.
"""
import os as _os
import tempfile as _tempfile

# Isolate from the real data folder before anything imports tokencoach.
_os.environ.setdefault("TOKENCOACH_DATA_DIR", _tempfile.mkdtemp(prefix="tokencoach-test-"))

import pathlib
import sys
import unittest
from datetime import datetime, timedelta, timezone

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tokencoach.providers import _fmt_reset  # noqa: E402


def _iso(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).isoformat()


class AlwaysAbsolute(unittest.TestCase):
    """Every horizon must render a clock time, never a countdown."""

    def test_short_horizon_is_not_relative(self):
        out = _fmt_reset(_iso(timedelta(minutes=40)))
        self.assertNotIn("in ", out)
        self.assertNotRegex(out, r"\d+h\s*\d*m?$")

    def test_claude_session_horizon_is_not_relative(self):
        out = _fmt_reset(_iso(timedelta(hours=4, minutes=12)))
        self.assertNotIn("in ", out)

    def test_monthly_horizon_is_not_relative(self):
        out = _fmt_reset(_iso(timedelta(days=27)))
        self.assertNotIn("in ", out)

    def test_past_reads_as_soon_not_a_negative_countdown(self):
        self.assertEqual(_fmt_reset(_iso(timedelta(minutes=-5))), "resets soon")


class LocalTimezone(unittest.TestCase):
    """The printed clock time must be local, not a mislabeled UTC value."""

    def test_matches_local_wall_clock(self):
        target = datetime.now(timezone.utc) + timedelta(hours=3)
        out = _fmt_reset(target.isoformat())
        expected_hhmm = target.astimezone().strftime("%H:%M")
        self.assertIn(expected_hhmm, out)

    def test_does_not_leak_the_utc_clock_time(self):
        # Only meaningful off UTC (this machine is UTC+2); skip if not.
        offset = datetime.now().astimezone().utcoffset()
        if offset is None or offset.total_seconds() == 0:
            self.skipTest("host is UTC; the bug this guards is invisible here")
        target = datetime.now(timezone.utc) + timedelta(hours=3)
        out = _fmt_reset(target.isoformat())
        utc_hhmm = target.strftime("%H:%M")
        self.assertNotIn(utc_hhmm, out)

    def test_across_midnight_reads_as_today_or_tomorrow_locally(self):
        # A UTC time just before midnight may land on the local "today" or
        # "tomorrow" depending on this machine's UTC offset - the label must
        # reflect the LOCAL date, not the UTC one.
        now_utc = datetime.now(timezone.utc)
        near_midnight_utc = now_utc.replace(hour=23, minute=30, second=0, microsecond=0)
        if near_midnight_utc <= now_utc:
            near_midnight_utc += timedelta(days=1)
        out = _fmt_reset(near_midnight_utc.isoformat())
        local_target = near_midnight_utc.astimezone()
        local_today = datetime.now().astimezone().date()
        expected_word = "today" if local_target.date() == local_today else "tomorrow"
        self.assertIn(expected_word, out)
        self.assertIn(local_target.strftime("%H:%M"), out)


class TodayTomorrow(unittest.TestCase):
    """A reset on the local calendar today/tomorrow says so directly -
    shorter than a weekday name and needs no day-of-week arithmetic."""

    def test_same_local_day_reads_as_today(self):
        out = _fmt_reset(_iso(timedelta(minutes=5)))
        self.assertIn("today", out)
        self.assertNotIn("tomorrow", out)

    def test_next_local_day_reads_as_tomorrow(self):
        local_now = datetime.now().astimezone()
        target_local = (local_now + timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        if target_local <= local_now:
            target_local += timedelta(days=1)
        out = _fmt_reset(target_local.astimezone(timezone.utc).isoformat())
        self.assertIn("tomorrow", out)

    def test_two_days_out_is_neither_today_nor_tomorrow(self):
        out = _fmt_reset(_iso(timedelta(days=2)))
        self.assertNotIn("today", out)
        self.assertNotIn("tomorrow", out)


class Disambiguation(unittest.TestCase):
    def test_within_a_week_shows_weekday_only(self):
        out = _fmt_reset(_iso(timedelta(days=2)))
        self.assertNotRegex(out, r"[A-Z][a-z]{2} \d{1,2},")

    def test_beyond_a_week_shows_a_calendar_date(self):
        # A bare weekday this far out is ambiguous - which Wednesday?
        out = _fmt_reset(_iso(timedelta(days=27)))
        self.assertRegex(out, r"[A-Z][a-z]{2} \d{1,2},")


class SharedFormatterSource(unittest.TestCase):
    def test_no_hand_rolled_relative_string_left_in_source(self):
        src = (REPO / "tokencoach" / "providers.py").read_text()
        self.assertNotIn('f"resets in {days}d {hours}h"', src)
        self.assertNotIn('f"resets in {hours}h"', src)

if __name__ == "__main__":
    unittest.main()


class OrgLookup(unittest.TestCase):
    """Found on the owner's Mac: with only a sessionKey (no lastActiveOrg
    cookie), the org came from /api/organizations, whose numeric `id` the
    usage endpoint rejects with HTTP 400. It needs the org's uuid."""

    UUID = "8f2c0d6e-1b4a-4c55-9a7e-3d2b1c0f9e88"

    def test_list_reply_uses_uuid_not_numeric_id(self):
        from unittest.mock import patch
        from tokencoach import providers
        reply = [{"id": 30187357, "uuid": self.UUID, "name": "Personal"}]
        with patch.object(providers, "_get", return_value=reply):
            self.assertEqual(providers._org_id_from_api({"sessionKey": "x"}), self.UUID)

    def test_dict_replies_use_uuid_too(self):
        from unittest.mock import patch
        from tokencoach import providers
        for reply in ({"organizations": [{"id": 1, "uuid": self.UUID}]},
                      {"account": {"memberships": [{"organization": {"id": 1, "uuid": self.UUID}}]}}):
            with patch.object(providers, "_get", return_value=reply):
                self.assertEqual(providers._org_id_from_api({"sessionKey": "x"}), self.UUID)


class ChatGPTFromCodex(unittest.TestCase):
    """Found on the owner's Mac: macOS keeps the app out of the browser's
    cookies, but Codex is signed in to the same ChatGPT account. Its sign-in
    is read (never written) and sent only to chatgpt.com, as Codex does."""

    def setUp(self):
        import tempfile
        from unittest.mock import patch
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        p = patch.dict(_os.environ, {"CODEX_HOME": self.home.name})
        p.start()
        self.addCleanup(p.stop)

    def jwt(self, exp):
        import base64, json
        body = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
        return f"h.{body}.s"

    def write_auth(self, exp):
        import json, time
        token = self.jwt(time.time() + exp)
        with open(_os.path.join(self.home.name, "auth.json"), "w") as f:
            json.dump({"tokens": {"access_token": token, "account_id": "acct-1"}}, f)
        return token

    def test_usage_comes_from_the_codex_sign_in(self):
        from unittest.mock import patch
        from tokencoach import providers
        token = self.write_auth(3600)
        self.assertTrue(providers.codex_signin_available())
        wham = {"rate_limit": {"primary_window": {"used_percent": 40, "reset_at": 2_000_000_000}}}
        with patch.object(providers, "_api_get", return_value=wham) as get:
            pd = providers.fetch_chatgpt_codex()
        self.assertIsNone(pd.error)
        self.assertEqual(pd._rows[0].pct, 40)
        url, headers = get.call_args.args[:2]
        self.assertTrue(url.startswith("https://chatgpt.com/"))
        self.assertEqual(headers["Authorization"], f"Bearer {token}")
        self.assertEqual(headers["ChatGPT-Account-Id"], "acct-1")
        self.assertIsNone(get.call_args.kwargs.get("cookies"))

    def test_expired_sign_in_says_how_to_renew(self):
        from unittest.mock import patch
        from tokencoach import providers
        self.write_auth(-60)
        with patch.object(providers, "_api_get") as get:
            pd = providers.fetch_chatgpt_codex()
        get.assert_not_called()
        self.assertIn("codex", pd.error.lower())

    def test_no_codex_sign_in(self):
        from tokencoach import providers
        self.assertFalse(providers.codex_signin_available())
