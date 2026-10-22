import os as _os
import tempfile as _tempfile

# Isolate from the real data folder before anything imports tokencoach.
_os.environ.setdefault("TOKENCOACH_DATA_DIR", _tempfile.mkdtemp(prefix="tokencoach-test-"))

import unittest

from tokencoach.onboarding import ONBOARDING_VERSION, plan_steps, should_show


class ShouldShowTests(unittest.TestCase):
    def test_new_user_sees_it(self):
        self.assertTrue(should_show({}))

    def test_existing_signals_skip_it(self):
        for key in ("cookie_str", "chatgpt_cookies", "seen_welcome", "bundle_welcome"):
            self.assertFalse(should_show({key: "x" if "cookie" in key else True}), key)

    def test_done_skips_it_until_version_bump(self):
        self.assertFalse(should_show({"onboarding_done": ONBOARDING_VERSION}))
        self.assertTrue(should_show({"onboarding_done": ONBOARDING_VERSION - 1}))

    def test_demo_never_shows(self):
        self.assertFalse(should_show({}, demo=True))


class PlanStepsTests(unittest.TestCase):
    def test_minimal(self):
        self.assertEqual(plan_steps(False, True), ["welcome", "connect", "done"])

    def test_codex_found(self):
        self.assertIn("codex", plan_steps(True, True))
        self.assertNotIn("codex", plan_steps(False, False))

    def test_nudges_offered_only_when_off(self):
        self.assertIn("nudges", plan_steps(False, False))
        self.assertNotIn("nudges", plan_steps(False, True))

    def test_connect_then_done_last(self):
        self.assertEqual(plan_steps(True, False)[-2:], ["connect", "done"])


class BrowserLoginTests(unittest.TestCase):
    """Following the browser's login needs macOS to let TokenCoach read other
    apps' data. A script install runs as the shared Python, so it is offered
    only in the downloaded app, where macOS asks about TokenCoach itself."""

    def test_only_the_app_build_offers_the_browser(self):
        from tokencoach.onboarding import connect_choices
        self.assertEqual(connect_choices(True)[1], "browser")
        self.assertEqual(connect_choices(True)[-1], "signin")
        script = connect_choices(False)
        self.assertNotIn("browser", script.values())
        self.assertIsNone(script["other"])

    def test_outcomes(self):
        from tokencoach.onboarding import browser_access_outcome
        self.assertEqual(browser_access_outcome(True, ["safari"]), "ok")
        self.assertEqual(browser_access_outcome(False, ["chrome"]), "blocked")
        self.assertEqual(browser_access_outcome(False, []), "none")

    def test_guided_lookup_never_takes_a_dead_cookie(self):
        from unittest.mock import patch
        from tokencoach import providers
        with patch.object(providers, "_BROWSER_COOKIE3_OK", True), \
             patch.object(providers, "_warn_keychain_once"), \
             patch.object(providers, "_run_cookie_detection", return_value=["sessionKey=dead"]), \
             patch.object(providers, "_claude_cookie_is_valid", return_value=False):
            self.assertIsNone(providers._auto_detect_cookies(require_valid=True))
            self.assertEqual(providers._auto_detect_cookies(), "sessionKey=dead")


if __name__ == "__main__":
    unittest.main()
