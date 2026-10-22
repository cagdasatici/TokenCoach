import unittest

from tokencoach.providers import normalize_cookie_input
from tokencoach.signin import build_cookie_string, is_google_sso_url


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


if __name__ == "__main__":
    unittest.main()
