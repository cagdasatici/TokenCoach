"""Live prompt nudges for Claude Code, via its UserPromptSubmit hook.

Claude Code runs this before each prompt is processed and shows our message to
the user. We never block or rewrite the prompt: the person stays in control.

Signals, cheapest first:
  - context size and model of this session, read from the live transcript
  - broad, unscoped asks, compared with the person's own history
  - a short question sent to an expensive model
  - a prompt similar to an earlier expensive one (and its saved rewrite)
  - Claude 5-hour quota nearly gone

Must be fast and silent on any failure: a broken hook must never get in the
way of the person's work.
"""

import json
import os
import re
import sys
import time

from tokencoach import ledger
from tokencoach.config import load_config, install_python, HISTORY_DB, APP_NAME

HOOK_MARKER = "tokencoach_nudge.py"
TAIL_BYTES = 400_000

LEVELS = {
    # context tokens that trigger a mild / strong warning
    "normal": {"ctx_mild": 150_000, "ctx_strong": 300_000, "max_msgs": 1},
    "heavy":  {"ctx_mild": 100_000, "ctx_strong": 200_000, "max_msgs": 2},
}
DEFAULT_LEVEL = "heavy"

BROAD = re.compile(
    r"\b(implement|fix|do|finish|complete|handle|review|check|clean ?up|refactor|update)\s+"
    r"(all|everything|every ?thing|the whole|the entire)\b"
    r"|\ball (the )?(open|remaining|pending|necessary) (things|items|issues|tasks|stuff)\b"
    r"|\b(whole|entire) (project|codebase|repo|repository|app)\b",
    re.I,
)
SPECIFIC = re.compile(r"[\w-]+/[\w./-]+|\b[\w-]+\.(py|ts|tsx|js|md|json|swift|go|rs|java|rb|sh|yml|yaml)\b|:\d+\b")
QUESTION = re.compile(r"^\s*(how|what|why|where|when|which|who|can|could|is|are|does|do|should|explain)\b", re.I)


# ── live session facts ───────────────────────────────────────────────────────

def session_context(transcript_path: str | None) -> tuple[int, str | None]:
    """(tokens in the last request, model) from the tail of the transcript."""
    if not transcript_path or not os.path.exists(transcript_path):
        return 0, None
    try:
        size = os.path.getsize(transcript_path)
        with open(transcript_path, "rb") as f:
            f.seek(max(0, size - TAIL_BYTES))
            lines = f.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return 0, None
    for line in reversed(lines):
        if '"usage"' not in line or '"assistant"' not in line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = d.get("message") or {}
        u = msg.get("usage") or {}
        model = msg.get("model")
        if not u or not model or model.startswith("<"):
            continue
        ctx = (int(u.get("input_tokens") or 0) + int(u.get("cache_read_input_tokens") or 0)
               + int(u.get("cache_creation_input_tokens") or 0))
        return ctx, model
    return 0, None


def default_model() -> str | None:
    """Model for a session's first prompt: Claude Code's configured default."""
    env = os.environ.get("ANTHROPIC_MODEL")
    if env:
        return env
    try:
        with open(os.path.expanduser("~/.claude/settings.json")) as f:
            m = json.load(f).get("model")
    except (OSError, ValueError):
        return None
    aliases = {"opus": "claude-opus-5", "sonnet": "claude-sonnet-5", "haiku": "claude-haiku-4-5",
               "fable": "claude-fable-5"}
    return aliases.get(m, m) if isinstance(m, str) else None


def per_reply_cost(ctx: int, model: str | None) -> float | None:
    """Rough cost of re-reading the context once (cached), per response."""
    p = ledger._price_for(model or "")
    if not p:
        return None
    return ctx * p.get("read", p["in"] * 0.1) / 1e6


def cheaper_ratio(model: str | None) -> tuple[str, float] | None:
    """(cheaper model alias, price ratio) when a clearly cheaper tier exists."""
    p = ledger._price_for(model or "")
    s = ledger.CLAUDE_PRICES["claude-sonnet-5"]
    if not p or not model or not model.startswith("claude-") or "sonnet" in model or "haiku" in model:
        return None
    ratio = p["out"] / s["out"]
    return ("sonnet", ratio) if ratio >= 1.8 else None


def claude_quota_left(max_age: float = 20 * 60) -> int | None:
    import sqlite3
    if not os.path.exists(HISTORY_DB):
        return None
    try:
        c = sqlite3.connect(f"file:{HISTORY_DB}?mode=ro", uri=True, timeout=1)
        row = c.execute("SELECT ts, pct FROM samples WHERE key='claude' ORDER BY ts DESC LIMIT 1").fetchone()
        c.close()
    except sqlite3.Error:
        return None
    if not row or time.time() - row[0] > max_age:
        return None
    return max(0, 100 - int(row[1]))


# ── history-based signals ───────────────────────────────────────────────────

REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S | re.I)


def _words(text: str) -> set[str]:
    # Harness-injected reminders (e.g. the scratch-workspace note on a session's
    # first prompt) are identical across sessions, so they would make unrelated
    # prompts look similar.
    return {w for w in re.findall(r"[a-z0-9]{3,}", REMINDER.sub(" ", text).lower())}


def broad_ask_stats(conn) -> tuple[float, float, float, float] | None:
    """(avg responses, avg $) for broad asks vs all prompts, last 90 days."""
    since = time.time() - 90 * 86400
    rows = conn.execute(
        "SELECT p.text, COUNT(c.id) n, COALESCE(SUM(c.cost_usd),0) cost FROM prompts p "
        "JOIN calls c ON c.prompt_id = p.id WHERE p.ts >= ? AND p.estimated = 0 "
        "AND p.source IN ('claude_code','cowork') GROUP BY p.id", (since,)).fetchall()
    broad = [r for r in rows if BROAD.search(r["text"]) and not SPECIFIC.search(r["text"])]
    if len(broad) < 2 or not rows:
        return None
    avg = lambda rs, k: sum(r[k] for r in rs) / len(rs)
    return avg(broad, "n"), avg(broad, "cost"), avg(rows, "n"), avg(rows, "cost")


def similar_expensive(conn, prompt: str, project: str, min_cost: float = 3.0):
    words = _words(prompt)
    if len(words) < 5:
        return None
    since = time.time() - 120 * 86400
    rows = conn.execute(
        "SELECT p.id, p.ts, p.text, COUNT(c.id) n, SUM(c.cost_usd) cost FROM prompts p "
        "JOIN calls c ON c.prompt_id = p.id WHERE p.ts >= ? AND p.project = ? "
        "GROUP BY p.id HAVING cost >= ? ORDER BY p.ts DESC LIMIT 300",
        (since, project, min_cost)).fetchall()
    best, best_j = None, 0.0
    for r in rows:
        w = _words(r["text"])
        if not w:
            continue
        j = len(words & w) / len(words | w)
        if j > best_j:
            best, best_j = r, j
    if best is None or best_j < 0.45:
        return None
    improved = conn.execute("SELECT 1 FROM improvements WHERE prompt_id = ?", (best["id"],)).fetchone()
    return dict(best), bool(improved)


# ── rate limiting ───────────────────────────────────────────────────────────

def recently_nudged(conn, session: str, kind: str, within_s: float = 20 * 60) -> dict | None:
    row = conn.execute(
        "SELECT ts, message FROM nudges WHERE session_id = ? AND kind = ? ORDER BY ts DESC LIMIT 1",
        (session, kind)).fetchone()
    if row and time.time() - row["ts"] < within_s:
        return dict(row)
    return None


# ── main decision ───────────────────────────────────────────────────────────

def decide(event: dict, conn, level: str = DEFAULT_LEVEL) -> list[tuple[str, str]]:
    """Return [(kind, message)] to show, most useful first."""
    cfg = LEVELS.get(level, LEVELS[DEFAULT_LEVEL])
    prompt = event.get("prompt") or event.get("prompt_text") or ""
    session = event.get("session_id") or "unknown"
    project = ledger.project_name(event.get("cwd"))
    if not prompt.strip() or prompt.strip().startswith("/"):
        return []                               # slash commands: leave alone
    out: list[tuple[str, str]] = []
    ctx, model = session_context(event.get("transcript_path"))
    model = model or default_model()

    # 1. context size — the biggest, most common cost driver
    if ctx >= cfg["ctx_mild"]:
        last = recently_nudged(conn, session, "context", within_s=45 * 60)
        grew = not last or ctx >= _ctx_in(last["message"]) + 100_000
        if grew:
            per = per_reply_cost(ctx, model)
            cost = f" (~${per:.2f} per reply on {model})" if per and per >= 0.01 else ""
            strong = ctx >= cfg["ctx_strong"]
            out.append(("context",
                        f"{'⚠' if strong else '💡'} {ctx // 1000}k tokens of context: every reply "
                        f"re-reads all of it{cost}. If this is a new task, /clear and start with a "
                        f"2-line brief" + (" — this is usually the single biggest saving." if strong else ".")))

    # 2. broad, unscoped ask
    if BROAD.search(prompt) and not SPECIFIC.search(prompt) and not recently_nudged(conn, session, "broad"):
        stats = broad_ask_stats(conn)
        if stats:
            bn, bc, an, ac = stats
            out.append(("broad",
                        f"🎯 Broad asks like this averaged {bn:.0f} responses (${bc:.2f}) in your history, "
                        f"vs {an:.0f} (${ac:.2f}) overall. Naming the files or items to change usually "
                        f"cuts that a lot."))
        else:
            out.append(("broad", "🎯 Broad ask: naming the files or items to change keeps the agent "
                                 "from exploring the whole project first."))

    # 3. short question on an expensive model
    cheaper = cheaper_ratio(model)
    if cheaper and len(prompt) < 200 and not SPECIFIC.search(prompt) and QUESTION.search(prompt) \
            and not recently_nudged(conn, session, "model", within_s=60 * 60):
        alias, ratio = cheaper
        out.append(("model", f"💡 Quick question on {model}? /model {alias} is ~{ratio:.0f}× cheaper "
                             f"per token and fine for this."))

    # 4. similar to an earlier expensive prompt
    if not recently_nudged(conn, session, "similar", within_s=60 * 60):
        sim = similar_expensive(conn, prompt, project)
        if sim:
            past, improved = sim
            when = time.strftime("%b %d", time.localtime(past["ts"]))
            tip = (" A tighter rewrite is saved in the TokenCoach dashboard." if improved
                   else " The dashboard's Improve button can suggest a tighter version.")
            out.append(("similar", f"🔁 Similar to a prompt on {when} that took {past['n']} responses "
                                   f"(${past['cost']:.2f}).{tip}"))

    # 5. quota nearly gone
    left = claude_quota_left()
    if left is not None and left <= 15 and not recently_nudged(conn, session, "quota", within_s=30 * 60):
        out.append(("quota", f"⏳ Only {left}% of your Claude 5-hour quota left."))

    return out[: cfg["max_msgs"]]


def _ctx_in(message: str) -> int:
    m = re.search(r"(\d+)k tokens", message)
    return int(m.group(1)) * 1000 if m else 0


def main():
    try:
        if os.environ.get("TOKENCOACH_INTERNAL"):
            return                              # our own analysis runs
        cfg = load_config()
        level = (cfg.get("nudges") or {}).get("level", DEFAULT_LEVEL)
        if level == "off":
            return
        event = json.loads(sys.stdin.read() or "{}")
        conn = ledger.open_ledger(timeout=2)       # never hold up the prompt for a busy ledger
        try:
            msgs = decide(event, conn, level)
            if not msgs:
                return
            project = ledger.project_name(event.get("cwd"))
            conn.executemany(
                "INSERT INTO nudges (ts, session_id, kind, message, project) VALUES (?, ?, ?, ?, ?)",
                [(time.time(), event.get("session_id") or "unknown", k, m, project) for k, m in msgs])
            conn.commit()
        finally:
            conn.close()
        text = f"{APP_NAME}: " + "\n".join(m for _, m in msgs)
        print(json.dumps({"systemMessage": text}))
    except Exception:
        pass                                    # never interfere with the prompt


# ── install / uninstall in ~/.claude/settings.json ──────────────────────────

CLAUDE_SETTINGS = os.path.expanduser("~/.claude/settings.json")


def hook_command(install_dir: str) -> str:
    return f'"{install_python(install_dir)}" "{os.path.join(install_dir, HOOK_MARKER)}"'


def _load_settings(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def installed_commands(path: str = CLAUDE_SETTINGS) -> list[str]:
    try:
        entries = (_load_settings(path).get("hooks") or {}).get("UserPromptSubmit") or []
    except (OSError, json.JSONDecodeError):
        return []
    return [h.get("command") or "" for e in entries for h in (e.get("hooks") or [])
            if HOOK_MARKER in (h.get("command") or "")]


def is_installed(path: str = CLAUDE_SETTINGS) -> bool:
    try:
        entries = (_load_settings(path).get("hooks") or {}).get("UserPromptSubmit") or []
    except (OSError, json.JSONDecodeError):
        return False
    return any(HOOK_MARKER in (h.get("command") or "")
               for e in entries for h in (e.get("hooks") or []))


def install(install_dir: str, path: str = CLAUDE_SETTINGS) -> None:
    """Add our hook, keeping every other setting. The first time, backs up
    the settings file as it was before TokenCoach."""
    settings = _load_settings(path)
    backup = path + ".tokencoach-backup"
    if os.path.exists(path) and not os.path.exists(backup):
        # Keep the first backup: it holds the settings from before TokenCoach.
        with open(path) as f, open(backup, "w") as b:
            b.write(f.read())
    hooks = settings.setdefault("hooks", {})
    entries = [e for e in hooks.get("UserPromptSubmit") or []
               if not any(HOOK_MARKER in (h.get("command") or "") for h in e.get("hooks") or [])]
    entries.append({"hooks": [{"type": "command", "command": hook_command(install_dir), "timeout": 10}]})
    hooks["UserPromptSubmit"] = entries
    _write_settings(path, settings)


def uninstall(path: str = CLAUDE_SETTINGS) -> None:
    settings = _load_settings(path)
    hooks = settings.get("hooks") or {}
    entries = [e for e in hooks.get("UserPromptSubmit") or []
               if not any(HOOK_MARKER in (h.get("command") or "") for h in e.get("hooks") or [])]
    if entries:
        hooks["UserPromptSubmit"] = entries
    else:
        hooks.pop("UserPromptSubmit", None)
    if not hooks:
        settings.pop("hooks", None)
    _write_settings(path, settings)


def _write_settings(path: str, settings: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


if __name__ == "__main__":
    main()
