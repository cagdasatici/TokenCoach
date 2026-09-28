"""Health: one green / amber / red answer to "am I OK?".

Three checks, each with its own state:
  right now  - every 5-hour window: enough left, and not on pace to run out
               before it resets
  this week  - every weekly window: not on pace to run out before it resets
  habits     - cost per prompt over the last 7 days against the 4 weeks before

Red is kept for "you can't work": only an empty quota window turns a check
red. Habits can reach amber at most; they come with a concrete tip.

The menu bar shows the quota checks only (can I keep working right now?);
the dashboard shows the worst of all three. Both use these functions, so
they never disagree about the quota.

Quota readings arrive as "windows": plain dicts the app writes into the
widget cache (usage.json), which is also where the dashboard reads them.
"""

import json
import os
import time
from datetime import datetime, timedelta

GOOD, WATCH, CRITICAL, UNKNOWN = "good", "watch", "critical", "unknown"
RANK = {UNKNOWN: -1, GOOD: 0, WATCH: 1, CRITICAL: 2}

LOW_LEFT_5H = 30        # % left in a 5-hour window below which it turns amber
LOW_LEFT_WEEK = 15      # % left in a weekly window below which it turns amber
WEEK_PACE_FROM = 0.15   # judge the weekly pace only after this share of the week
WEEK_PACE_MARGIN = 1.1  # ...and only warn when it projects 110% or more (noise)
STALE_AFTER = 30 * 60   # quota readings older than this are not used
HABIT_WORSE = 0.25      # cost per prompt this much above usual turns habits amber
HABIT_BETTER = -0.10    # ...and this much below it is worth saying
HABIT_MIN_RECENT = 15   # prompts needed in the last 7 days to judge habits
HABIT_MIN_USUAL = 30    # prompts needed in the 4 weeks before

WEEK = 7 * 86400
PROVIDER_LABELS = {"claude": "Claude", "codex": "Codex"}


def worst(*states: str) -> str:
    known = [s for s in states if s and s != UNKNOWN]
    return max(known, key=RANK.get) if known else UNKNOWN


# ── quota windows ────────────────────────────────────────────────────────────

def windows_from(data, providers, history: dict | None = None) -> list[dict]:
    """The quota windows that count for health, from the app's latest readings.

    data: providers.UsageData for Claude (or None); providers: ProviderData
    list (ChatGPT rows are Codex's limits); history: the app's pace history,
    used for the minutes-to-empty estimate of each 5-hour window.
    """
    from tokencoach.history import _calc_eta_minutes
    history = history or {}
    out = []

    def add(provider, kind, row, hkey=None):
        if row is None:
            return
        out.append({
            # providers report % used; windows carry % left, like every gauge
            "provider": provider, "kind": kind, "left": max(0, min(100, 100 - row.pct)),
            "reset_ts": row.reset_ts, "reset_str": row.reset_str,
            "eta_min": _calc_eta_minutes(history, hkey) if hkey else None,
        })

    if data is not None:
        add("claude", "5h", data.session, "claude")
        add("claude", "week", data.weekly_all)
    for pd in providers or []:
        if pd.name != "ChatGPT" or pd.error:
            continue
        for row in getattr(pd, "_rows", None) or []:
            if row.label == "5-hour":
                add("codex", "5h", row, "chatgpt_5-hour")
            elif row.label == "Weekly":
                add("codex", "week", row)
    return out


def _clock(ts: float, now: float) -> str:
    """'15:40', 'tomorrow 09:00' or 'Mon 09:00' - an absolute local time."""
    t, n = datetime.fromtimestamp(ts), datetime.fromtimestamp(now)
    if t.date() == n.date():
        return t.strftime("%H:%M")
    if t.date() == n.date() + timedelta(days=1):
        return "tomorrow " + t.strftime("%H:%M")
    return t.strftime("%a %H:%M")


def _mins(m: float) -> str:
    m = max(1, round(m))
    if m < 60:
        return f"{m} min"
    h, r = divmod(m, 60)
    return f"{h} h {r} min" if r else f"{h} h"


def window_state(w: dict, now: float) -> dict:
    """The window with its state and a short reason added."""
    left, reset = w["left"], w.get("reset_ts")
    to_reset = (reset - now) / 60 if reset and reset > now else None
    state, reason, runs_out = GOOD, "", None
    if left <= 0:
        state = CRITICAL
        reason = f"empty until {_clock(reset, now)}" if to_reset else "empty"
    elif w["kind"] == "5h":
        eta = w.get("eta_min")
        if eta is not None and to_reset is not None and eta < to_reset:
            state, runs_out = WATCH, now + eta * 60
            reason = f"on pace to run out in ~{_mins(eta)}"
        elif left < LOW_LEFT_5H:
            state, reason = WATCH, "running low"
    else:
        elapsed = 1 - (reset - now) / WEEK if to_reset else None
        used = 100 - left
        if elapsed and elapsed >= WEEK_PACE_FROM and used / elapsed >= 100 * WEEK_PACE_MARGIN:
            rate = used / (elapsed * WEEK)                  # % per second
            hits = now + left / rate
            if hits < reset:
                state, runs_out = WATCH, hits
                reason = f"on pace to run out {_clock(hits, now)}"
        if state == GOOD and left < LOW_LEFT_WEEK:
            state, reason = WATCH, "running low"
    if state == GOOD and to_reset is not None:
        reason = f"resets {_clock(reset, now)}"
    return {**w, "state": state, "reason": reason, "runs_out": runs_out,
            "label": PROVIDER_LABELS.get(w["provider"], w["provider"])}


def quota_health(windows: list[dict], now: float | None = None) -> dict:
    """{"state", "now": {...}, "week": {...}, "providers": {key: state}}.

    "now" and "week" each hold the state of that check and its windows."""
    now = now or time.time()
    judged = [window_state(w, now) for w in windows]
    out = {"providers": {}}
    for kind, key in (("5h", "now"), ("week", "week")):
        ws = [w for w in judged if w["kind"] == kind]
        out[key] = {"state": worst(*(w["state"] for w in ws)), "windows": ws}
    for w in judged:
        p = w["provider"]
        out["providers"][p] = worst(out["providers"].get(p, UNKNOWN), w["state"])
    out["state"] = worst(out["now"]["state"], out["week"]["state"])
    return out


def read_windows(path: str, now: float | None = None) -> tuple[list[dict], float | None]:
    """Windows the app last wrote to the widget cache, and when; none if the
    file is missing, unreadable or stale (the app isn't running)."""
    now = now or time.time()
    try:
        with open(path) as f:
            payload = json.load(f)
        ts = datetime.fromisoformat(payload["updated_at"]).timestamp()
    except (OSError, ValueError, KeyError, TypeError):
        return [], None
    if now - ts > STALE_AFTER:
        return [], ts
    return [w for w in payload.get("windows") or [] if isinstance(w, dict)], ts


# ── habits ───────────────────────────────────────────────────────────────────

TIPS = {
    "context": ("Sessions are running long, so every reply re-reads a bigger context. "
                "Start a fresh session after each task."),
    "responses": ("Prompts are taking more back-and-forth. Name the files involved and say "
                  "when the task is done."),
    "mix": ("Each prompt is doing more expensive work. Use a smaller model for quick "
            "questions, and check your costliest prompts below."),
}


def _prompt_stats(conn, lo: float, hi: float, optimizer_project: str) -> list[tuple]:
    """(cost, responses, peak context, ts) for each priced, recorded prompt."""
    return conn.execute(
        """SELECT SUM(cost_usd), COUNT(*), MAX(input_tokens + cache_write_tokens + cache_read_tokens),
                  MIN(ts)
           FROM calls WHERE prompt_id IS NOT NULL AND ts >= ? AND ts < ? AND project != ?
             AND estimated = 0 AND cost_usd IS NOT NULL
           GROUP BY prompt_id""", (lo, hi, optimizer_project)).fetchall()


def habits_health(conn, lessons: list[dict] | None = None, now: float | None = None) -> dict:
    """Cost per prompt over the last 7 days against the 4 weeks before.

    Habits reach amber at most. The tip names what grew most and points at a
    Coach lesson when one is waiting."""
    from tokencoach import ledger
    now = now or time.time()
    day = 86400
    recent = _prompt_stats(conn, now - 7 * day, now, ledger.OPTIMIZER_PROJECT)
    usual = _prompt_stats(conn, now - 35 * day, now - 7 * day, ledger.OPTIMIZER_PROJECT)

    def avg(rows, i):
        return sum(r[i] or 0 for r in rows) / len(rows) if rows else None

    # daily cost per prompt for the last 28 days (the trend line)
    series = []
    for d in range(27, -1, -1):
        lo, hi = now - (d + 1) * day, now - d * day
        rows = [r for r in recent + usual if lo <= r[3] < hi]
        series.append(round(avg(rows, 0), 4) if rows else None)

    out = {"state": UNKNOWN, "cpp": avg(recent, 0), "usual": avg(usual, 0), "change": None,
           "recent_prompts": len(recent), "usual_prompts": len(usual),
           "series": series, "tip": "", "driver": None, "lesson": None}
    if len(recent) < HABIT_MIN_RECENT or len(usual) < HABIT_MIN_USUAL or not out["usual"]:
        return out
    change = out["cpp"] / out["usual"] - 1
    out["change"] = round(change, 3)
    if change <= HABIT_WORSE:
        out["state"] = GOOD
        return out
    out["state"] = WATCH
    growth = {
        "context": (avg(recent, 2) or 0) / (avg(usual, 2) or 1) - 1,
        "responses": (avg(recent, 1) or 0) / (avg(usual, 1) or 1) - 1,
    }
    driver = max(growth, key=growth.get)
    out["driver"] = driver if growth[driver] > 0.15 else "mix"
    out["tip"] = TIPS[out["driver"]]
    waiting = [l for l in lessons or [] if l.get("status") in ("ready", "review")]
    if waiting:
        l = sorted(waiting, key=lambda l: l.get("status") != "ready")[0]
        out["lesson"] = {"id": l["id"], "title": l["title"]}
    return out


# ── overall ──────────────────────────────────────────────────────────────────

def _names(labels: list[str]) -> str:
    return " and ".join(labels) if len(labels) < 3 else ", ".join(labels[:-1]) + " and " + labels[-1]


def overall(quota: dict, habits: dict, now: float | None = None) -> dict:
    """The page headline: state, one-line headline, a sentence or two of
    detail, and at most one action (a Coach lesson to look at)."""
    now = now or time.time()
    state = worst(quota.get("state", UNKNOWN), habits.get("state", UNKNOWN))
    ws = quota.get("now", {}).get("windows", []) + quota.get("week", {}).get("windows", [])
    # where to keep working: a healthy window first, else any that isn't empty
    best_5h = sorted((w for w in quota.get("now", {}).get("windows", []) if w["state"] != CRITICAL),
                     key=lambda w: (RANK[w["state"]], -w["left"]))
    alt = lambda p: next((w for w in best_5h if w["provider"] != p), None)   # noqa: E731
    action = None

    empty = [w for w in ws if w["state"] == CRITICAL]
    watch = sorted((w for w in ws if w["state"] == WATCH),
                   key=lambda w: (w["kind"] != "5h", w["runs_out"] or float("inf"), w["left"]))
    if empty:
        w = sorted(empty, key=lambda w: w["kind"] != "5h")[0]
        until = f" until {_clock(w['reset_ts'], now)}" if w.get("reset_ts") else ""
        what = "is out" if w["kind"] == "5h" else "has used its weekly limit"
        headline = f"{w['label']} {what}{until}"
        other = alt(w["provider"])
        detail = (f"{other['label']} has {other['left']}% left, so switch there to keep working."
                  if other else "Nothing to do but wait for the reset.")
    elif watch:
        w = watch[0]
        if w["kind"] == "5h" and w["runs_out"]:
            headline = f"Slow down on {w['label']}"
            spare = (w["reset_ts"] - w["runs_out"]) / 60 if w.get("reset_ts") else None
            detail = (f"At this pace you'll reach the 5-hour limit in about "
                      f"{_mins((w['runs_out'] - now) / 60)}"
                      + (f", {_mins(spare)} before it resets." if spare else "."))
        elif w["kind"] == "5h":
            headline = f"{w['label']} is running low"
            detail = f"{w['left']}% of the 5-hour window is left" + (
                f"; it resets {_clock(w['reset_ts'], now)}." if w.get("reset_ts") else ".")
        else:
            headline = f"Watch {w['label']}'s weekly limit"
            detail = (f"At this pace you'll reach it {_clock(w['runs_out'], now)}, before it resets "
                      f"{_clock(w['reset_ts'], now)}." if w["runs_out"] else
                      f"{w['left']}% of the week is left.")
        other = alt(w["provider"])
        if other:
            detail += f" {other['label']} has {other['left']}% left."
    elif habits.get("state") == WATCH:
        pct = round(habits["change"] * 100)
        headline = "Quota is fine. One habit to work on"
        detail = f"Each prompt costs {pct}% more than your usual. {habits['tip']}"
        if habits.get("lesson"):
            action = {"label": "See the suggested lesson", "lesson": habits["lesson"]["id"]}
    elif state == UNKNOWN:
        headline = "No live quota reading"
        detail = ("Start TokenCoach from the menu bar to see how much quota is left. "
                  "Habits need about a week of prompts before they can be judged.")
    else:
        headline = "You're in good shape"
        tools = _names(sorted({w["label"] for w in ws}))
        detail = f"Quota is fine on {tools}." if tools else "No live quota reading, so this is based on habits."
        ch = habits.get("change")
        if habits.get("state") == GOOD and ch is not None and ch <= HABIT_BETTER:
            detail += f" Each prompt costs {abs(round(ch * 100))}% less than your usual."
    return {"state": state, "headline": headline, "detail": detail, "action": action}


def menu_line(quota: dict, now: float | None = None) -> str | None:
    """One line for the top of the menu when the quota needs attention."""
    if quota.get("state") not in (WATCH, CRITICAL):
        return None
    o = overall(quota, {"state": UNKNOWN}, now)
    return o["headline"] + ". " + o["detail"]
