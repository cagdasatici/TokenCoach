"""First-run setup guide: when it shows and which steps it contains.

Pure logic only (no AppKit), so it is unit-tested; the dialogs live in ui.py.
"""

# Bump to show the guide again to everyone who finished an older one.
ONBOARDING_VERSION = 1

# Flags and credentials that mean this person already set the app up before the
# guide existed (the old welcome set seen_welcome / bundle_welcome).
_EXISTING_USER_KEYS = ("cookie_str", "chatgpt_cookies", "seen_welcome", "bundle_welcome")


def should_show(config: dict, demo: bool = False) -> bool:
    """True only for a brand-new person; --demo never shows it."""
    if demo:
        return False
    done = config.get("onboarding_done")
    if isinstance(done, int) and not isinstance(done, bool) and done >= ONBOARDING_VERSION:
        return False
    return not any(config.get(k) for k in _EXISTING_USER_KEYS)


def plan_steps(codex_found: bool, nudges_on: bool) -> list[str]:
    """Step ids in order. Extras appear only when relevant; connect comes last
    because the sign-in window is not modal, so nothing should follow it but
    the closing note."""
    steps = ["welcome"]
    if codex_found:
        steps.append("codex")
    if not nudges_on:
        steps.append("nudges")
    steps += ["connect", "done"]
    return steps


def connect_choices(bundled: bool) -> dict:
    """The Connect Claude dialog's buttons. Following the browser's login needs
    macOS to let TokenCoach read another app's data. Only the downloaded app
    asks for that as itself; a script install runs as the shared Python, and
    granting it there would let every Python script read browser cookies."""
    if bundled:
        return {"ok": "Use my browser\u2019s login", "cancel": "Skip",
                "other": "Sign in to Claude\u2026", 1: "browser", -1: "signin"}
    return {"ok": "Sign in to Claude\u2026", "cancel": "Skip", "other": None, 1: "signin"}


def browser_access_outcome(found: bool, blocked: list[str]) -> str:
    """After a guided browser lookup: 'ok', 'blocked' (macOS kept us out of a
    browser, so the person must allow it) or 'none' (readable, not signed in)."""
    if found:
        return "ok"
    return "blocked" if blocked else "none"
