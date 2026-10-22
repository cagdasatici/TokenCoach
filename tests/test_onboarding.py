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


if __name__ == "__main__":
    unittest.main()
