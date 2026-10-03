"""Configuration constants and persistence."""

import json
import os
import sys
import logging
import logging.handlers

# ── identity ─────────────────────────────────────────────────────────────────
# Display name. TokenCoach began as a fork of AIQuotaBar by Toprak Yagcioglu;
# see README and LICENSE for attribution.
APP_NAME = "TokenCoach"
REPO_URL = "https://github.com/cagdasatici/TokenCoach"
LAUNCH_AGENT_LABEL = "io.github.cagdasatici.tokencoach"
LAUNCH_AGENT_PLIST = os.path.expanduser(f"~/Library/LaunchAgents/{LAUNCH_AGENT_LABEL}.plist")
UPSTREAM_URL = "https://github.com/yagcioglutoprak/AIQuotaBar"


def install_python(root: str) -> str:
    """Interpreter to record in the login agent and the Claude Code hook.

    The install's own venv, reached through `root`: the script install's
    .venv, or Homebrew's venv under opt/tokencoach, a path that survives
    upgrades. Homebrew resolves sys.executable to Cellar/tokencoach/<version>,
    which the next `brew upgrade` deletes.
    """
    for rel in (".venv/bin/python3", "venv/bin/python"):
        py = os.path.join(root, rel)
        if os.path.exists(py):
            return py
    return sys.executable

# ── where things live ────────────────────────────────────────────────────────
# TOKENCOACH_DATA_DIR points everything at another folder (tests, demo data).
# TOKENCOACH_DEMO=1 additionally sandboxes anything that would touch the
# person's real setup (instruction files, Claude Code settings).
DEMO = os.environ.get("TOKENCOACH_DEMO") == "1"
APP_SUPPORT = os.environ.get("TOKENCOACH_DATA_DIR") or os.path.expanduser(
    "~/Library/Application Support/TokenCoach")
LOG_DIR = os.path.join(APP_SUPPORT, "logs") if os.environ.get("TOKENCOACH_DATA_DIR") \
    else os.path.expanduser("~/Library/Logs/TokenCoach")
CONFIG_FILE = os.path.join(APP_SUPPORT, "config.json")
LOG_FILE = os.path.join(LOG_DIR, "tokencoach.log")

# Locations used before the rename (by AIQuotaBar and its fork). Moved once.
_LEGACY_SUPPORT = os.path.expanduser("~/Library/Application Support/AIQuotaBar")
_LEGACY_FILES = {
    os.path.expanduser("~/.claude_bar_config.json"): CONFIG_FILE,
    os.path.expanduser("~/.claude_bar_history.json"): os.path.join(APP_SUPPORT, "history.json"),
}


def _merge_json(src: str, dst: str) -> bool:
    """Fold an old settings file into a newer one; the old file's values win,
    since they are what the person chose (the newer file may only hold
    defaults written before the move). Returns False if either isn't a dict."""
    try:
        with open(src) as f:
            old = json.load(f)
        with open(dst) as f:
            new = json.load(f)
    except (OSError, ValueError):
        return False
    if not isinstance(old, dict) or not isinstance(new, dict):
        return False
    tmp = dst + ".tmp"
    with open(tmp, "w") as f:
        json.dump({**new, **old}, f, indent=2)
    os.replace(tmp, dst)
    return True


def migrate_legacy_data() -> list[str]:
    """Move data from pre-rename locations, once. Safe to call repeatedly;
    never overwrites anything that already exists at the new location."""
    if os.environ.get("TOKENCOACH_DATA_DIR"):
        return []
    moved = []
    try:
        if os.path.isdir(_LEGACY_SUPPORT) and not os.path.exists(APP_SUPPORT):
            os.rename(_LEGACY_SUPPORT, APP_SUPPORT)      # same volume: atomic
            moved.append(_LEGACY_SUPPORT)
        elif os.path.isdir(_LEGACY_SUPPORT):
            for name in os.listdir(_LEGACY_SUPPORT):       # finish a partial move
                src, dst = os.path.join(_LEGACY_SUPPORT, name), os.path.join(APP_SUPPORT, name)
                if not os.path.exists(dst):
                    os.rename(src, dst)
                    moved.append(src)
        os.makedirs(APP_SUPPORT, exist_ok=True)
        old_opt = os.path.join(APP_SUPPORT, "aiquotaleft-optimizer")   # Analyze's work folder
        if os.path.isdir(old_opt) and not os.path.exists(os.path.join(APP_SUPPORT, "tokencoach-optimizer")):
            os.rename(old_opt, os.path.join(APP_SUPPORT, "tokencoach-optimizer"))
        for src, dst in _LEGACY_FILES.items():
            if not os.path.exists(src):
                continue
            if not os.path.exists(dst):
                os.rename(src, dst)
                moved.append(src)
            elif dst == CONFIG_FILE and _merge_json(src, dst):
                os.remove(src)
                moved.append(src)
    except OSError:
        pass                                              # retried on next start
    return moved


_MIGRATED = migrate_legacy_data()
os.makedirs(APP_SUPPORT, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
# Owner-only: the folder holds the dashboard token, session cookies and every
# prompt in the ledger. Files written before this existed are tightened too.
# The log folder as well: old logs can hold the dashboard token or API replies.
for _path, _mode in ((APP_SUPPORT, 0o700), (CONFIG_FILE, 0o600), (LOG_DIR, 0o700)):
    try:
        os.chmod(_path, _mode)
    except OSError:
        pass

# ── logging ──────────────────────────────────────────────────────────────────

_log_handler = logging.handlers.RotatingFileHandler(
    LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3,
)
_log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logging.basicConfig(handlers=[_log_handler], level=logging.DEBUG)
log = logging.getLogger("tokencoach")
if _MIGRATED:
    log.info("moved data from pre-rename locations: %s", ", ".join(_MIGRATED))

# ── paths & thresholds ───────────────────────────────────────────────────────

REFRESH_INTERVALS = {
    "1 min":  60,
    "5 min":  300,
    "15 min": 900,
}
DEFAULT_REFRESH = 300

WARN_THRESHOLD = 80   # notify when any limit crosses this %
CRIT_THRESHOLD = 95   # title turns red emoji above this %

WIDGET_HOST_APP = "/Applications/TokenCoachWidget.app"
# Its own folder: the widget's sandbox exception covers only this, not the
# config (cookies) and ledger (every prompt) next to it.
WIDGET_CACHE_DIR = os.path.join(APP_SUPPORT, "widget")
WIDGET_CACHE_FILE = os.path.join(WIDGET_CACHE_DIR, "usage.json")
WIDGET_LEGACY_CACHE_FILE = os.path.join(APP_SUPPORT, "usage.json")   # read by widgets built before 1.2
os.makedirs(WIDGET_CACHE_DIR, mode=0o700, exist_ok=True)   # the widget host watches it from launch

# ── notification defaults ─────────────────────────────────────────────────────
# Keys stored in config under "notifications": { key: bool }
NOTIF_DEFAULTS = {
    "claude_reset":   True,   # notify when Claude session/weekly resets
    "chatgpt_reset":  True,   # notify when ChatGPT rate-limit resets
    "claude_warning": True,   # notify when Claude usage crosses WARN/CRIT
    "chatgpt_warning":True,   # notify when ChatGPT usage crosses WARN/CRIT
    "claude_pacing":  True,   # predictive alert when Claude ETA < 30 min
    "chatgpt_pacing": True,   # predictive alert when ChatGPT ETA < 30 min
}

# ── usage history + burn rate ────────────────────────────────────────────────

HISTORY_FILE = os.path.join(APP_SUPPORT, "history.json")
HISTORY_MAX_AGE = 24 * 3600  # prune entries older than 24 h
PACING_ALERT_MINUTES = 30    # alert when ETA drops below this

# ── SQLite long-term history ─────────────────────────────────────────────────
HISTORY_DB = os.path.join(APP_SUPPORT, "history.db")
SAMPLES_MAX_DAYS = 7
DAILY_MAX_DAYS = 90
LIMIT_HIT_PCT = 95
BURN_WINDOW = 30 * 60       # regression window: 30 minutes
MIN_SPAN_SECS = 5 * 60      # need >=5 min of data before showing ETA
RESET_DROP_PCT = 30          # pct drop that signals a reset
UPDATE_CHECK_INTERVAL = 4 * 3600   # check for updates every 4 hours

HISTORY_COLORS = {
    "claude": "#D97757", "chatgpt": "#74AA9C",
}


# ── config persistence ───────────────────────────────────────────────────────

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            corrupt = CONFIG_FILE + ".bak"
            log.warning("Config file corrupt (%s), resetting. Backup at %s", e, corrupt)
            try:
                os.replace(CONFIG_FILE, corrupt)
            except OSError:
                pass
    return {}


def save_config(cfg: dict):
    tmp = CONFIG_FILE + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)          # a stale .tmp keeps its old mode otherwise
    with os.fdopen(fd, "w") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, CONFIG_FILE)


def notif_enabled(cfg: dict, key: str) -> bool:
    """Return True if the named notification is enabled (defaults to True)."""
    return cfg.get("notifications", {}).get(key, NOTIF_DEFAULTS.get(key, True))


def set_notif(cfg: dict, key: str, value: bool):
    """Persist a single notification toggle."""
    cfg.setdefault("notifications", {})[key] = value
    save_config(cfg)
