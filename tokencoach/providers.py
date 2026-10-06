"""Data models and API fetch functions for all providers."""

import base64
import json
import math
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

from curl_cffi import requests
from curl_cffi.requests.exceptions import HTTPError as CurlHTTPError

try:
    import browser_cookie3
    _BROWSER_COOKIE3_OK = True
except ImportError:
    _BROWSER_COOKIE3_OK = False

from tokencoach.config import log


# ── data models ───────────────────────────────────────────────────────────────

@dataclass
class LimitRow:
    label: str
    pct: int          # 0–100
    reset_str: str    # e.g. "resets Thu 00:00" or "resets Oct 5, 14:32" - see _fmt_reset
    reset_ts: float | None = None   # the same moment as a Unix timestamp, for pace


@dataclass
class UsageData:
    session: LimitRow | None = None
    weekly_all: LimitRow | None = None
    weekly_sonnet: LimitRow | None = None
    overages_enabled: bool | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class ProviderData:
    """Usage/billing data for a third-party API provider."""
    name: str
    spent: float | None = None    # current period spend
    limit: float | None = None    # hard/soft limit
    balance: float | None = None  # prepaid balance (for credit-based providers)
    currency: str = "USD"
    period: str = "this month"
    error: str | None = None
    _rows: list = field(default_factory=list, repr=False)

    @property
    def pct(self) -> int | None:
        if self.spent is not None and self.limit and self.limit > 0:
            return min(100, round(self.spent / self.limit * 100))
        return None


# ── claude.ai API ─────────────────────────────────────────────────────────────

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://claude.ai/settings/usage",
    "Origin": "https://claude.ai",
}
# Cloudflare fingerprint-checks Chrome aggressively; Safari passes cleanly.
_IMPERSONATE = "safari184"
# Cloudflare-bound cookies are tied to the real browser fingerprint —
# sending them from a different TLS stack causes a mismatch → 403.
CF_COOKIE_KEYS = frozenset({"cf_clearance", "__cf_bm", "_cfuvid"})


def parse_cookie_string(raw: str) -> dict:
    """Parse 'key=val; key2=val2' or just a bare sessionKey value."""
    raw = raw.strip()
    if "=" not in raw:
        return {"sessionKey": raw}
    cookies = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            cookies[k.strip()] = v.strip()
    return cookies


def _strip_cf_cookies(cookies: dict) -> dict:
    return {k: v for k, v in cookies.items() if k not in CF_COOKIE_KEYS}


def _get(url: str, cookies: dict) -> dict | list:
    r = requests.get(
        url, cookies=_strip_cf_cookies(cookies), headers=HEADERS, timeout=15,
        impersonate=_IMPERSONATE,
    )
    # Only error bodies: a successful /api/account or /api/bootstrap reply holds
    # the person's email and organisation, and the log is attached to bug reports.
    log.debug("GET %s  status=%s%s", url, r.status_code,
              f"  body={r.text[:300]}" if r.status_code >= 400 else "")
    r.raise_for_status()
    return r.json()


def _org_id_from_cookies(cookies: dict) -> str | None:
    return cookies.get("lastActiveOrg") or cookies.get("routingHint")


def _org_id_from_api(cookies: dict) -> str | None:
    for path in (
        "/api/organizations",
        "/api/bootstrap",
        "/api/auth/current_account",
        "/api/account",
    ):
        try:
            data = _get(f"https://claude.ai{path}", cookies)
            # The usage endpoint takes the org's uuid; its numeric `id` gets HTTP 400.
            org = lambda o: (o or {}).get("uuid") or (o or {}).get("id")
            if isinstance(data, list) and data:
                return org(data[0])
            if isinstance(data, dict):
                for candidate in (
                    data.get("organization_id"),
                    data.get("org_id"),
                    org((data.get("organizations") or [{}])[0]),
                    org((data.get("account", {}).get("memberships") or [{}])[0]
                        .get("organization")),
                ):
                    if candidate:
                        return candidate
        except Exception as e:
            log.debug("endpoint %s failed: %s", path, e)
    return None



def fetch_raw(cookie_str: str) -> dict:
    cookies = parse_cookie_string(cookie_str)
    log.debug("using cookies keys: %s", list(cookies.keys()))

    org_id = _org_id_from_cookies(cookies)
    log.debug("org_id from cookie: %s", org_id)

    if not org_id:
        org_id = _org_id_from_api(cookies)
        log.debug("org_id from api: %s", org_id)

    if not org_id:
        raise ValueError(
            "Could not find organization id.\n"
            "Make sure you copied ALL cookies (including lastActiveOrg)."
        )

    usage = _get(
        f"https://claude.ai/api/organizations/{org_id}/usage", cookies
    )
    log.debug("usage full response: %s", json.dumps(usage, indent=2))
    return {"usage": usage, "org_id": org_id}


# ── time helpers ──────────────────────────────────────────────────────────────

_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _reset_epoch(val) -> float | None:
    """A reset time as sent by the APIs (Unix seconds or ISO 8601, UTC) as a
    Unix timestamp, or None if it can't be read."""
    if val is None or val == "":
        return None
    try:
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val).rstrip("Z")
        if "+" not in s[10:] and s[-6] != "+":
            s += "+00:00"
        return datetime.fromisoformat(s).timestamp()
    except (ValueError, IndexError):
        log.debug("_reset_epoch failed for %r", val, exc_info=True)
        return None


def _fmt_reset(val) -> str:
    """Format a reset timestamp as an absolute local time, never "in Xh Ym".

    A relative countdown goes stale the moment it's read and forces the
    reader to do arithmetic; every provider now reports an absolute clock
    time instead. The API returns UTC, so it must be converted with
    astimezone() before formatting - printing the UTC wall-clock value
    labeled as local is silently wrong, not just relative (a UTC+2 reader
    would read a 21:00 reset as 19:00).

    A reset landing on the local calendar today or tomorrow says so -
    "resets today 14:32" / "resets tomorrow 09:00" - shorter than a weekday
    name and needs no arithmetic to place. Otherwise, under a week out, a
    weekday name is unambiguous: "resets Wed 14:32". Further out, a bare
    weekday would be ambiguous (which Wednesday?), so the calendar date is used
    instead: "resets Oct 5, 14:32".
    """
    if val is None:
        return ""
    try:
        if isinstance(val, (int, float)):
            dt = datetime.fromtimestamp(val, tz=timezone.utc)
        else:
            s = str(val).rstrip("Z")
            if "+" not in s[10:] and s[-6] != "+":
                s += "+00:00"
            dt = datetime.fromisoformat(s)
        now = datetime.now(timezone.utc)
        secs = (dt - now).total_seconds()
        if secs <= 0:
            return "resets soon"
        local = dt.astimezone()
        now_local = now.astimezone()
        if local.date() == now_local.date():
            return f"resets today {local.strftime('%H:%M')}"
        if local.date() == now_local.date() + timedelta(days=1):
            return f"resets tomorrow {local.strftime('%H:%M')}"
        if secs < 6 * 86400:
            return f"resets {_DAYS[local.weekday()]} {local.strftime('%H:%M')}"
        return f"resets {local.strftime('%b %-d, %H:%M')}"
    except Exception:
        log.debug("_fmt_reset failed for %r", val, exc_info=True)
        return str(val)[:20]


# ── parser ────────────────────────────────────────────────────────────────────

def _row(data: dict, key: str, label: str) -> LimitRow | None:
    bucket = data.get(key)
    if not bucket or not isinstance(bucket, dict):
        return None
    raw = float(bucket.get("utilization", 0))
    # API returns 0-100 percentage for all fields (five_hour, seven_day, etc.)
    pct = min(100, round(raw))
    reset = _fmt_reset(bucket.get("resets_at"))
    return LimitRow(label, pct, reset, _reset_epoch(bucket.get("resets_at")))


def parse_usage(raw: dict) -> UsageData:
    """
    API response shape (confirmed):
      five_hour        -> Plan usage limits / Current session
      seven_day        -> Weekly limits / All models
      seven_day_sonnet -> Weekly limits / Sonnet only
      extra_usage      -> Extra usage toggle (null = off)
    """
    u = raw.get("usage", {})
    extra = u.get("extra_usage")
    overages = bool(extra) if extra is not None else None

    return UsageData(
        session=_row(u, "five_hour", "5-hour"),
        weekly_all=_row(u, "seven_day", "Weekly"),
        weekly_sonnet=_row(u, "seven_day_sonnet", "Weekly (Sonnet)"),
        overages_enabled=overages,
        raw=raw,
    )


# ── third-party provider APIs ────────────────────────────────────────────────

def _api_get(url: str, headers: dict, cookies: dict | None = None) -> dict:
    clean = _strip_cf_cookies(cookies) if cookies else None
    r = requests.get(url, headers=headers, cookies=clean, timeout=10, impersonate=_IMPERSONATE)
    r.raise_for_status()
    return r.json()


_CHATGPT_HEADERS = {
    "Accept": "application/json",
    "Origin": "https://chatgpt.com",
    "Referer": "https://chatgpt.com/codex/settings/usage",
}


def _jwt_claims(token: str) -> dict:
    """Decode JWT claims without validating the signature.

    The token is returned by ChatGPT over the authenticated HTTPS session; we
    only read its account-routing claim and still send the token back to the
    same service that issued it.
    """
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        return claims if isinstance(claims, dict) else {}
    except (IndexError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _chatgpt_account_id(session: dict, access_token: str) -> str | None:
    """Find the account/workspace id needed to route Codex usage requests."""
    for source in (session, session.get("tokens") or {}):
        if isinstance(source, dict):
            account_id = source.get("account_id") or source.get("accountId")
            if account_id:
                return str(account_id)

    tokens = [access_token]
    for key in ("idToken", "id_token", "id_token_value"):
        token = session.get(key)
        if isinstance(token, str):
            tokens.append(token)
    nested = session.get("tokens")
    if isinstance(nested, dict):
        for key in ("access_token", "id_token"):
            token = nested.get(key)
            if isinstance(token, str):
                tokens.append(token)

    for token in tokens:
        claims = _jwt_claims(token)
        auth = claims.get("https://api.openai.com/auth") or {}
        if isinstance(auth, dict):
            account_id = auth.get("chatgpt_account_id") or auth.get("account_id")
            if account_id:
                return str(account_id)
        account_id = claims.get("chatgpt_account_id") or claims.get("account_id")
        if account_id:
            return str(account_id)
    return None


def _chatgpt_token_expired(token: str, leeway_seconds: int = 30) -> bool:
    """Return whether a JWT access token is already expired or about to expire."""
    exp = _jwt_claims(token).get("exp")
    try:
        return exp is not None and float(exp) <= time.time() + leeway_seconds
    except (TypeError, ValueError):
        return False


def _codex_signin() -> tuple[str, str] | None:
    """(access token, account id) from the Codex CLI's ChatGPT sign-in.

    Read-only: Codex owns token refresh and rotation; this app never writes
    its auth file, keeps no copy, and sends the token only to chatgpt.com.
    """
    codex_home = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
    try:
        with open(os.path.join(codex_home, "auth.json")) as f:
            tokens = json.load(f).get("tokens") or {}
        if not isinstance(tokens, dict):
            return None
        account_id = tokens.get("account_id")
        if not account_id and isinstance(tokens.get("id_token"), str):
            account_id = _chatgpt_account_id({}, tokens["id_token"])
        token = tokens.get("access_token")
        if isinstance(token, str) and token and account_id:
            return token, str(account_id)
    except (OSError, ValueError, TypeError, AttributeError):
        log.debug("Could not read the Codex sign-in", exc_info=True)
    return None


def codex_signin_available() -> bool:
    return _codex_signin() is not None


def _codex_access_token(account_id: str) -> str | None:
    """A fresh Codex token, only when its workspace matches this session: the
    fallback for an expired browser-issued token."""
    signin = _codex_signin()
    if not signin or not account_id or signin[1] != str(account_id):
        return None
    return None if _chatgpt_token_expired(signin[0]) else signin[0]


def _chatgpt_session(cookies: dict) -> tuple[str | None, str | None]:
    """Exchange browser cookies for a short-lived token and account id."""
    data = _api_get("https://chatgpt.com/api/auth/session", _CHATGPT_HEADERS, cookies)
    token = data.get("accessToken") or data.get("access_token")
    if not token and isinstance(data.get("tokens"), dict):
        token = data["tokens"].get("access_token")
    if not isinstance(token, str) or not token:
        return None, None
    return token, _chatgpt_account_id(data, token)


def _parse_wham_window(pw: dict | None, label: str) -> LimitRow | None:
    """Parse a single primary/secondary window dict into a LimitRow."""
    if not pw or not isinstance(pw, dict):
        return None
    pct = min(100, int(pw.get("used_percent", 0)))
    reset_str = _fmt_reset(pw.get("reset_at")) if pw.get("reset_at") else ""
    return LimitRow(label, pct, reset_str, _reset_epoch(pw.get("reset_at")))


def _parse_wham_bucket(
    bucket: dict, primary_label: str, weekly_label: str | None = None,
) -> list[LimitRow]:
    """Parse a rate-limit bucket into its 5h and weekly rows.

    Each bucket (`rate_limit`, `code_review_rate_limit`, and any entry in
    `additional_rate_limits`) carries a `primary_window` (5h) and a
    `secondary_window` (7-day/weekly) - Codex's own UI shows both, this app
    used to surface only the primary one.
    """
    if not bucket or not isinstance(bucket, dict):
        return []
    rows = []
    row = _parse_wham_window(bucket.get("primary_window"), primary_label)
    if row is not None:
        rows.append(row)
    row = _parse_wham_window(
        bucket.get("secondary_window"), weekly_label or f"{primary_label} (Weekly)"
    )
    if row is not None:
        rows.append(row)
    return rows


def _parse_wham_usage(data: dict) -> ProviderData:
    """Parse /backend-api/wham/usage response.

    Confirmed shape (2026-02, re-confirmed 2026-09):
      rate_limit.primary_window.used_percent    (0-100, 5h)
      rate_limit.secondary_window.used_percent  (0-100, weekly)
      rate_limit.{primary,secondary}_window.reset_at  (Unix timestamp)
      code_review_rate_limit  -- same structure
    """
    log.debug("wham/usage raw: %s", json.dumps(data, indent=2))

    rows: list[LimitRow] = []

    label_map = {
        "rate_limit":             ("5-hour", "Weekly"),
        "code_review_rate_limit": ("Code Review (5-hour)", "Code Review (Weekly)"),
    }
    for key, labels in label_map.items():
        rows.extend(_parse_wham_bucket(data.get(key), *labels))

    # additional_rate_limits may be a list of extra buckets
    for extra in (data.get("additional_rate_limits") or []):
        if isinstance(extra, dict):
            name = extra.get("name") or extra.get("type") or "Extra"
            rows.extend(_parse_wham_bucket(extra, name.replace("_", " ").title()))

    if not rows:
        return ProviderData("ChatGPT", error="No rate limit data in response")

    worst = max(rows, key=lambda r: r.pct)
    pd = ProviderData("ChatGPT", spent=float(worst.pct), limit=100.0, currency="")
    pd._rows = rows
    return pd


def fetch_chatgpt(cookie_str: str) -> ProviderData:
    """Fetch ChatGPT / Codex usage via /backend-api/wham/usage."""
    cookies = parse_cookie_string(cookie_str)
    try:
        token, account_id = _chatgpt_session(cookies)
        if not token:
            return ProviderData("ChatGPT", error="ChatGPT browser session has expired; sign in again.")
        if _chatgpt_token_expired(token):
            token = _codex_access_token(account_id or "")
            if not token:
                return ProviderData(
                    "ChatGPT",
                    error="ChatGPT access token expired (HTTP 401); sign in at chatgpt.com, then click Refresh.",
                )
        if not account_id:
            return ProviderData(
                "ChatGPT",
                error="ChatGPT account ID is missing; refresh your browser session by signing in again.",
            )
        h = {
            **_CHATGPT_HEADERS,
            "Authorization": f"Bearer {token}",
            "ChatGPT-Account-Id": account_id,
        }
        try:
            data = _api_get("https://chatgpt.com/backend-api/wham/usage", h, cookies)
        except CurlHTTPError as e:
            response = getattr(e, "response", None)
            error_code = ""
            try:
                error_code = (response.json().get("error") or {}).get("code", "")
            except Exception:
                pass
            if getattr(response, "status_code", None) == 401 and error_code == "token_expired":
                fresh_token = _codex_access_token(account_id)
                if fresh_token and fresh_token != token:
                    h["Authorization"] = f"Bearer {fresh_token}"
                    data = _api_get("https://chatgpt.com/backend-api/wham/usage", h, cookies)
                else:
                    raise
            else:
                raise
        return _parse_wham_usage(data)
    except CurlHTTPError as e:
        response = getattr(e, "response", None)
        status = getattr(response, "status_code", None)
        log.debug("fetch_chatgpt failed with HTTP %s", status or "unknown")
        if status == 401:
            error_code = ""
            try:
                error_code = (response.json().get("error") or {}).get("code", "")
            except Exception:
                pass
            if error_code == "token_expired":
                message = "ChatGPT access token expired (HTTP 401); sign in at chatgpt.com, then click Refresh."
            else:
                message = "ChatGPT rejected the session (HTTP 401); sign in again in your browser."
        elif status == 403:
            message = "ChatGPT denied the usage request (HTTP 403)."
        else:
            message = f"ChatGPT request failed (HTTP {status})." if status else "ChatGPT request failed."
        return ProviderData("ChatGPT", error=message)
    except Exception as e:
        log.debug("fetch_chatgpt failed: %s", e)
        return ProviderData("ChatGPT", error=f"ChatGPT request failed: {str(e)[:70]}")


def fetch_chatgpt_codex(_unused=None) -> ProviderData:
    """ChatGPT / Codex usage through the Codex CLI's own sign-in.

    Used when no browser cookie is saved: on recent macOS the app may not read
    another browser's cookies at all, while Codex holds a sign-in to the same
    account that it keeps fresh itself.
    """
    signin = _codex_signin()
    if not signin:
        return ProviderData("ChatGPT", error="No ChatGPT sign-in found; sign in to Codex or chatgpt.com.")
    token, account_id = signin
    if _chatgpt_token_expired(token):
        return ProviderData("ChatGPT", error="The Codex sign-in has expired; run codex once to renew it, "
                                             "then click Refresh.")
    h = {**_CHATGPT_HEADERS, "Authorization": f"Bearer {token}", "ChatGPT-Account-Id": account_id}
    try:
        return _parse_wham_usage(_api_get("https://chatgpt.com/backend-api/wham/usage", h))
    except CurlHTTPError as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        log.debug("fetch_chatgpt_codex failed with HTTP %s", status or "unknown")
        if status == 401:
            return ProviderData("ChatGPT", error="ChatGPT rejected the Codex sign-in (HTTP 401); run codex "
                                                 "once to renew it, then click Refresh.")
        return ProviderData("ChatGPT", error=f"ChatGPT request failed (HTTP {status})." if status
                            else "ChatGPT request failed.")
    except Exception as e:
        log.debug("fetch_chatgpt_codex failed: %s", e)
        return ProviderData("ChatGPT", error=f"ChatGPT request failed: {str(e)[:70]}")


def fetch_openai(api_key: str) -> ProviderData:
    h = {"Authorization": f"Bearer {api_key}"}
    try:
        sub = _api_get(
            "https://api.openai.com/v1/dashboard/billing/subscription", h
        )
        hard_limit = float(
            sub.get("hard_limit_usd") or sub.get("system_hard_limit_usd") or 0
        )
        now = datetime.now()
        start = now.replace(day=1).strftime("%Y-%m-%d")
        end = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        usage = _api_get(
            f"https://api.openai.com/v1/dashboard/billing/usage"
            f"?start_date={start}&end_date={end}", h
        )
        spent = float(usage.get("total_usage", 0)) / 100  # cents -> dollars
        return ProviderData(
            "OpenAI", spent=spent,
            limit=hard_limit or None, currency="USD", period="this month",
        )
    except Exception as e:
        log.debug("fetch_openai failed: %s", e)
        return ProviderData("OpenAI", error=str(e)[:80])


def fetch_minimax(api_key: str) -> ProviderData:
    h = {"Authorization": f"Bearer {api_key}"}
    try:
        data = _api_get("https://api.minimax.chat/v1/account_information", h)
        balance = float(
            data.get("available_balance") or data.get("balance") or 0
        )
        return ProviderData("MiniMax", balance=balance, currency="CNY")
    except Exception as e:
        log.debug("fetch_minimax failed: %s", e)
        return ProviderData("MiniMax", error=str(e)[:80])


def fetch_glm(api_key: str) -> ProviderData:
    h = {"Authorization": f"Bearer {api_key}"}
    try:
        data = _api_get(
            "https://open.bigmodel.cn/api/paas/v4/account/balance", h
        )
        balance = float(
            data.get("total_balance") or data.get("balance") or 0
        )
        return ProviderData("GLM (Zhipu)", balance=balance, currency="CNY")
    except Exception as e:
        log.debug("fetch_glm failed: %s", e)
        return ProviderData("GLM (Zhipu)", error=str(e)[:80])


# Registry: config_key -> (display_name, fetch_fn)
# chatgpt_cookies are cookie-based (auto-detected);
# others are API key-based.
PROVIDER_REGISTRY: dict[str, tuple[str, callable]] = {
    "chatgpt_cookies": ("ChatGPT",     fetch_chatgpt),
    "openai_key":      ("OpenAI",      fetch_openai),
    "minimax_key":     ("MiniMax",     fetch_minimax),
    "glm_key":         ("GLM (Zhipu)", fetch_glm),
}

# Cookie-based providers (auto-detected from browser, not manually entered)
COOKIE_PROVIDERS = {"chatgpt_cookies"}


# ── Claude Code local stats ───────────────────────────────────────────────────

CC_STATS_FILE = os.path.expanduser("~/.claude/stats-cache.json")


def fetch_claude_code_stats() -> dict | None:
    """Read Claude Code usage from ~/.claude/stats-cache.json (no network needed).

    Returns dict with today_messages, today_sessions, week_messages,
    week_sessions, week_tool_calls -- or None if the file doesn't exist.
    """
    if not os.path.exists(CC_STATS_FILE):
        return None
    try:
        with open(CC_STATS_FILE) as f:
            data = json.load(f)
        today = datetime.now().strftime("%Y-%m-%d")
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        entries = data.get("dailyActivity", [])
        today_e = next((e for e in entries if e["date"] == today), None)
        week_e  = [e for e in entries if e["date"] >= week_ago]
        return {
            "today_messages":   today_e["messageCount"]  if today_e else 0,
            "today_sessions":   today_e["sessionCount"]  if today_e else 0,
            "week_messages":    sum(e["messageCount"]  for e in week_e),
            "week_sessions":    sum(e["sessionCount"]  for e in week_e),
            "week_tool_calls":  sum(e["toolCallCount"] for e in week_e),
            "last_date": max((e["date"] for e in entries), default=None),
        }
    except Exception as e:
        log.debug("fetch_claude_code_stats failed: %s", e)
        return None


# ── Cookie detection ──────────────────────────────────────────────────────────

_keychain_warned = False  # show the dialog at most once per session


def _warn_keychain_once():
    """Show a one-time dialog before the macOS Keychain prompt appears."""
    global _keychain_warned
    if _keychain_warned:
        return
    _keychain_warned = True
    try:
        _show_keychain_note()
    except (OSError, subprocess.SubprocessError):
        # Nobody clicked OK in time (the Mac was idle): the note is only a
        # heads-up, so go on to the browser lookup instead of failing the fetch.
        log.debug("keychain note not acknowledged", exc_info=True)


def _show_keychain_note():
    subprocess.run(
        ["osascript", "-e",
         'display dialog "TokenCoach reads your claude.ai sign-in from your '
         'browser to show your Claude usage.\\n\\n'
         'macOS will ask for access to the browser\'s cookie key. Click \\"Allow\\". '
         '\\"Always Allow\\" would hand that key to Apple\'s security tool, which any '
         'program on this Mac can run, without asking again. TokenCoach only looks '
         'again when you choose Auto-detect from Browser or your session expires." '
         'with title "TokenCoach — Browser sign-in" '
         'buttons {"OK"} default button "OK" '
         'with icon note'],
        capture_output=True, timeout=60,
    )


# Script run in a child process — isolates browser_cookie3 C-library crashes
# (libcrypto / sqlite segfaults on Chromium decryption don't kill the main app).
_DETECT_SCRIPT = r"""
import sys, json, os, functools, glob

lookups = json.loads(sys.argv[1])   # [[domain, target cookie], ...], read in one pass

BROWSERS = [
    'firefox', 'librewolf', 'chrome', 'arc', 'brave',
    'edge', 'chromium', 'opera', 'vivaldi', 'safari',
]
# Chromium browsers keep their cookie key in the Keychain, and browser_cookie3
# asks for it (a password prompt) before it even looks for the cookie file. So
# look for the cookie file first: when there is none (a folder some other tool
# left behind), or macOS keeps us out of it (privacy protection for other apps'
# data), a prompt would buy nothing.
CHROMIUM_HOMES = {
    'chrome': 'Google/Chrome', 'arc': 'Arc/User Data', 'brave': 'BraveSoftware/Brave-Browser',
    'edge': 'Microsoft Edge', 'chromium': 'Chromium', 'opera': 'com.operasoftware.Opera',
    'vivaldi': 'Vivaldi',
}
SUPPORT = os.path.expanduser('~/Library/Application Support')
COOKIE_FILES = ('Cookies', 'Network/Cookies', '*/Cookies', '*/Network/Cookies')


def cookie_store(home):
    # 'absent', 'blocked' or 'readable' for a Chromium browser's data folder
    try:
        os.listdir(home)
    except FileNotFoundError:
        return 'absent'
    except OSError:
        return 'blocked'
    files = [f for pat in COOKIE_FILES for f in glob.glob(os.path.join(glob.escape(home), pat))]
    if not files:
        return 'absent'
    for f in files:
        try:
            open(f, 'rb').close()
            return 'readable'
        except OSError:
            pass
    return 'blocked'

# Collect candidates from every browser that has the target cookie.
# Rank by expiry as a hint, but the caller VALIDATES each candidate and
# uses the first that actually authenticates -- a stale session in one
# browser must never mask a valid one in another.
found = {domain: [] for domain, _ in lookups}   # domain -> [(expires_seconds, cookie_str)]
blocked = []     # browsers whose cookie store exists but macOS would not let us read


def unreadable(e):
    # macOS privacy protection surfaces as PermissionError, or as this
    # message from the Chromium reader.
    return isinstance(e, PermissionError) or 'Unable to read database file' in str(e)


try:
    import browser_cookie3
    if hasattr(browser_cookie3, '_get_osx_keychain_password'):
        # one Keychain prompt per browser, however many sites are read
        browser_cookie3._get_osx_keychain_password = functools.lru_cache(maxsize=None)(
            browser_cookie3._get_osx_keychain_password)
    for name in BROWSERS:
        fn = getattr(browser_cookie3, name, None)
        if fn is None:
            continue
        if name in CHROMIUM_HOMES:
            store = cookie_store(os.path.join(SUPPORT, CHROMIUM_HOMES[name]))
            if store == 'blocked':
                blocked.append(name)
            if store != 'readable':
                continue
        for domain, target in lookups:
            try:
                jar = fn(domain_name=domain)
            except Exception as e:
                if unreadable(e):
                    blocked.append(name)
                    break                   # the same store holds every site's cookies
                continue
            cookies = {x.name: x for x in jar}
            if target not in cookies:
                continue
            expires = cookies[target].expires or 0
            # Normalize expiry to seconds. Firefox can report the value in
            # milliseconds (or an overflowed scale), which made a stale
            # session always out-rank a valid Chromium one. Anything past
            # year ~5138 in seconds (1e11) is treated as milliseconds.
            try:
                expires = float(expires)
            except (TypeError, ValueError):
                expires = 0.0
            while expires > 1e11:
                expires /= 1000.0
            cookie_str = '; '.join(f'{k}={c.value}' for k, c in cookies.items())
            found[domain].append((expires, cookie_str))
except Exception:
    pass
sys.stderr.write(json.dumps({'blocked': blocked}))

# Rank best-first: latest (normalized) expiry, tie-break by richest jar.
print(json.dumps({domain: [c for _, c in sorted(cands, key=lambda x: (x[0], len(x[1])), reverse=True)]
                  for domain, cands in found.items()}))
"""

# Every site TokenCoach reads, so one lookup (one Keychain prompt per browser)
# serves both the Claude and the ChatGPT detection of a refresh.
_LOOKUPS = [["claude.ai", "sessionKey"], ["chatgpt.com", "__Secure-next-auth.session-token"]]
_LOOKUP_TTL = 30            # seconds: long enough for one refresh, short enough for a retry
_DETECT_TIMEOUT = 90        # seconds, including time for the person to answer a Keychain prompt
_lookup_cache: tuple[float, dict] = (0.0, {})
last_blocked_browsers: list[str] = []   # from the latest lookup, for the menu's message


def forget_cookie_lookup() -> None:
    """Make the next detection read the browsers again (the person asked)."""
    global _lookup_cache
    _lookup_cache = (0.0, {})


def _run_cookie_detection(domain: str, target_cookie: str) -> list[str]:
    """Run browser_cookie3 in an isolated child process (crash-safe).

    Returns a best-first ranked list of candidate cookie strings (one per
    browser that has the target cookie). Empty list if none are found.
    """
    global last_blocked_browsers, _lookup_cache
    ts, found = _lookup_cache
    if time.time() - ts < _LOOKUP_TTL and domain in found:
        return list(found[domain])
    lookups = _LOOKUPS if [domain, target_cookie] in _LOOKUPS else [[domain, target_cookie]]
    last_blocked_browsers, found = [], {}
    try:
        # Own process group: on a timeout (a Keychain prompt nobody answered)
        # the `security` child it started must go too, or its dialog stays up.
        from tokencoach.runtime import bundled
        args = ([sys.executable, "--cookie-worker", json.dumps(lookups)] if bundled() else
                [sys.executable, "-c", _DETECT_SCRIPT, json.dumps(lookups)])
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
        )
        try:
            out, errout = proc.communicate(timeout=_DETECT_TIMEOUT)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            raise
        r = subprocess.CompletedProcess(proc.args, proc.returncode, out, errout)
        try:
            last_blocked_browsers = list(json.loads(r.stderr.strip().splitlines()[-1])["blocked"])
            err = ""
        except (ValueError, KeyError, IndexError, TypeError):
            err = r.stderr[-300:]          # the script died before reporting
        data = json.loads(r.stdout.strip()) if r.stdout.strip() else {}
        if isinstance(data, dict):
            found = {d: [c for c in v if isinstance(c, str) and c] for d, v in data.items()}
        # stdout is the cookie jars themselves: log counts, never the values
        log.debug("cookie-detect rc=%d candidates=%s blocked=%s err=%r", r.returncode,
                  {d: len(v) for d, v in found.items()}, last_blocked_browsers, err)
    except Exception as e:
        log.debug("_run_cookie_detection failed: %s", e)
    _lookup_cache = (time.time(), found)
    return list(found.get(domain, []))


def _claude_cookie_is_valid(cookie_str: str) -> bool:
    """True if this cookie string authenticates against claude.ai.

    Probes /api/organizations (session-level, no org id needed). A stale or
    logged-out sessionKey returns 403 account_session_invalid here, so this
    cleanly rejects dead sessions that still carry a far-future expiry.
    """
    try:
        _get("https://claude.ai/api/organizations", parse_cookie_string(cookie_str))
        return True
    except Exception as e:
        log.debug("claude cookie candidate rejected: %s", e)
        return False


def _auto_detect_cookies() -> str | None:
    """Detect a *valid* claude.ai session cookie from the browser.

    Returns the first candidate (across all logged-in browsers) that actually
    authenticates, instead of blindly trusting the latest-expiry one. This
    stops a stale session in one browser (e.g. an old Firefox login whose
    cookie still has a far-future expiry) from masking a valid session in
    another (e.g. a fresh Chrome login).
    """
    if not _BROWSER_COOKIE3_OK:
        return None
    _warn_keychain_once()
    candidates = _run_cookie_detection("claude.ai", "sessionKey")
    if not candidates:
        return None
    for cookie_str in candidates:
        if _claude_cookie_is_valid(cookie_str):
            return cookie_str
    # Nothing validated (all logged out / expired). Fall back to the
    # best-ranked candidate so the existing 401/403 handling can surface a
    # "session expired" prompt to the user.
    log.debug("no claude cookie candidate validated; using best-ranked")
    return candidates[0]


def _auto_detect_chatgpt_cookies(exclude: set[str] | None = None) -> str | None:
    """Choose a browser candidate that still yields ChatGPT account credentials."""
    if not _BROWSER_COOKIE3_OK:
        return None
    cands = _run_cookie_detection("chatgpt.com", "__Secure-next-auth.session-token")
    exclude = exclude or set()
    fallback = None
    for candidate in cands:
        if candidate in exclude:
            continue
        if fallback is None:
            fallback = candidate
        try:
            token, account_id = _chatgpt_session(parse_cookie_string(candidate))
            if token and account_id and not _chatgpt_token_expired(token):
                return candidate
        except Exception as e:
            log.debug("ChatGPT cookie candidate rejected: %s", e)
    return fallback
