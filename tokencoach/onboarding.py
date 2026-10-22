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
