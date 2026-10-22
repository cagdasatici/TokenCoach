import os as _os
import tempfile as _tempfile

# Isolate from the real data folder before anything imports tokencoach.
_os.environ.setdefault("TOKENCOACH_DATA_DIR", _tempfile.mkdtemp(prefix="tokencoach-test-"))

import unittest

from tokencoach.providers import normalize_cookie_input
from tokencoach.signin import available, build_cookie_string, is_google_sso_url


class NormalizeCookieInputTests(unittest.TestCase):
    def test_bare_key(self):
        self.assertEqual(normalize_cookie_input("  sk-ant-abc \n"), "sessionKey=sk-ant-abc")

    def test_session_key_pair(self):
        self.assertEqual(normalize_cookie_input("sessionKey=abc"), "sessionKey=abc")

    def test_cookie_header_drops_cloudflare(self):
        raw = "Cookie: sessionKey=abc;\n cf_clearance=x; __cf_bm=y; _cfuvid=z; lastActiveOrg=org1\n"
        self.assertEqual(normalize_cookie_input(raw), "sessionKey=abc; lastActiveOrg=org1")

    def test_empty(self):
        self.assertEqual(normalize_cookie_input(" \n "), "")
        self.assertEqual(normalize_cookie_input("cookie:"), "")


class BuildCookieStringTests(unittest.TestCase):
    def test_picks_claude_cookies_only(self):
        cookies = [
            ("sessionKey", ".claude.ai", "sk1"),
            ("lastActiveOrg", "claude.ai", "org1"),
            ("cf_clearance", ".claude.ai", "cf"),
            ("sessionKey", ".example.com", "other"),
            ("_ga", ".claude.ai", "ga"),
        ]
        self.assertEqual(build_cookie_string(cookies), "sessionKey=sk1; lastActiveOrg=org1")

    def test_no_session_key(self):
        self.assertEqual(build_cookie_string([("lastActiveOrg", "claude.ai", "o")]), "")
        self.assertEqual(build_cookie_string([("sessionKey", "evil.com", "x")]), "")


class GoogleSsoTests(unittest.TestCase):
    def test_detects_google(self):
        self.assertTrue(is_google_sso_url("https://accounts.google.com/o/oauth2/v2/auth?x=1"))

    def test_ignores_others(self):
        self.assertFalse(is_google_sso_url("https://claude.ai/login"))
        self.assertFalse(is_google_sso_url("https://evil.com/accounts.google.com"))
        self.assertFalse(is_google_sso_url(""))


_LOAD_A_PAGE = r"""
import AppKit
from PyObjCTools import AppHelper
from tokencoach import signin
AppKit.NSApplication.sharedApplication().setActivationPolicy_(AppKit.NSApplicationActivationPolicyProhibited)
w = signin._SignInWindow(lambda c: None, None)
seen = []
orig = w.poll
w.poll = lambda: (seen.append(1), orig())
w._web.loadHTMLString_baseURL_("<p>hi</p>", None)
def stop():
    # poll() leaves _checking set until WebKit calls the cookie block back
    print("PAGE-OK" if seen and not w._checking else "PAGE-MISSING", flush=True)
    w.close(); AppHelper.stopEventLoop()
AppHelper.callLater(3.0, stop)
AppHelper.runEventLoop(installInterrupt=True)
"""


@unittest.skipUnless(available(), "WebKit not installed")
class RealWebViewTests(unittest.TestCase):
    """Found when first trying a real sign-in: a navigation delegate callback
    whose block PyObjC could not call crashed the whole app on the first page
    load. This loads a page in a real WKWebView, in a child process."""

    def test_a_page_loads_without_crashing(self):
        import subprocess
        import sys
        root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
        r = subprocess.run([sys.executable, "-c", _LOAD_A_PAGE], capture_output=True, text=True,
                           timeout=60, cwd=root, env=dict(_os.environ))
        self.assertIn("PAGE-OK", r.stdout, r.stderr[-800:])
        self.assertEqual(r.returncode, 0, r.stderr[-800:])


class NotificationClickTests(unittest.TestCase):
    """rumps hands the click handler a Notification (a Mapping, not a dict);
    an isinstance(dict) check made "click to sign in again" do nothing."""

    def test_reads_the_action_from_a_rumps_notification(self):
        from rumps.notifications import Notification
        from tokencoach.ui import _notification_action
        self.assertEqual(_notification_action(Notification(None, {"action": "signin"})), "signin")
        self.assertIsNone(_notification_action(Notification(None, None)))


if __name__ == "__main__":
    unittest.main()
