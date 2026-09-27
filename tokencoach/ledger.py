"""Usage ledger -- per-prompt token and cost accounting from local agent logs.

Reads the transcripts that Claude Code, Cowork and Codex already write to disk,
and stores one row per user prompt and one row per model response in a local
SQLite database. Nothing leaves the machine.

Sources (verified 2026-09-27):
  Claude Code  ~/.claude/projects/**/*.jsonl                  message.usage per response
  Cowork       ~/Library/Application Support/Claude/local-agent-mode-sessions/**/audit.jsonl
  Codex        ~/.codex/sessions/**/*.jsonl                  token_usage_record / token_count

Ingest is incremental: each file's byte offset is remembered, so a pass only
reads lines appended since the previous pass.

Costs are *API-equivalent*: what the same tokens would cost on the provider's
API. Subscription users do not pay this per prompt; it is a yardstick for
comparing prompts, projects and models, not a bill.

Quota attribution: each rise in a provider's used-% between two quota samples
is shared across the calls made in that interval, weighted by cost. Codex logs
a sample after every response, so its attribution is close to per-call; Claude
relies on TokenCoach's own polling samples, so its numbers are estimates.
"""

import glob
import hashlib
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta

from tokencoach.config import log, HISTORY_DB, APP_SUPPORT

LEDGER_DB = os.path.join(APP_SUPPORT, "ledger.db")

CLAUDE_CODE_GLOB = os.path.expanduser("~/.claude/projects/**/*.jsonl")
COWORK_GLOB = os.path.expanduser(
    "~/Library/Application Support/Claude/local-agent-mode-sessions/**/audit.jsonl"
)
CODEX_GLOB = os.path.expanduser("~/.codex/sessions/**/*.jsonl")

# Project name used for the optimizer's own `claude -p` runs, so its digest
# prompts can be excluded from the next digest.
OPTIMIZER_PROJECT = "tokencoach-optimizer"

# ── pricing ──────────────────────────────────────────────────────────────────
# USD per million tokens, first-party Anthropic API list prices as of
# 2026-09-27. Cache writes: 5-minute TTL at 1.25x input, 1-hour TTL at 2x
# input; cache reads at 0.1x input (Opus 5.5 publishes $0.20 read = 0.05x).
# Matched by longest prefix of the model id.
CLAUDE_PRICES = {
    "claude-fable-5":    {"in": 10.0, "out": 50.0},
    "claude-mythos-5":   {"in": 10.0, "out": 50.0},
    "claude-opus-5-5":   {"in": 4.0,  "out": 20.0, "read": 0.20},
    "claude-opus-5":     {"in": 5.0,  "out": 25.0},
    "claude-opus-4":     {"in": 5.0,  "out": 25.0},
    "claude-sonnet-5":   {"in": 2.0,  "out": 10.0},
    "claude-sonnet-4":   {"in": 3.0,  "out": 15.0},
    "claude-haiku-4":    {"in": 1.0,  "out": 5.0},
}

# OpenAI Standard-tier list prices, USD per million tokens, from
# https://developers.openai.com/api/docs/pricing (checked 2026-09-27).
# "read" = cached input, "write" = cache write where published. Requests whose
# prompt exceeds 272K tokens are billed at the "long" rates for the whole
# request. Matched by longest prefix of the model id.
PRICES_CHECKED = "2026-09-27"
LONG_CONTEXT = 272_000
OPENAI_PRICES = {
    "gpt-6-astra":   {"in": 10.0, "read": 1.0,   "write": 12.5, "out": 50.0,
                      "long": {"in": 20.0, "read": 2.0, "write": 25.0, "out": 75.0}},
    "gpt-6-sol":     {"in": 2.0,  "read": 0.2,   "out": 10.0},
    "gpt-6-luna":    {"in": 0.1,  "read": 0.01,  "out": 0.5},
    "gpt-5.6-sol":   {"in": 4.0,  "read": 0.4,   "write": 5.0,  "out": 20.0,
                      "long": {"in": 8.0, "read": 0.8, "write": 10.0, "out": 30.0}},
    "gpt-5.6-terra": {"in": 2.0,  "read": 0.2,   "write": 2.5,  "out": 12.0,
                      "long": {"in": 4.0, "read": 0.4, "write": 5.0, "out": 18.0}},
    "gpt-5.6-luna":  {"in": 0.2,  "read": 0.02,  "write": 0.25, "out": 1.2,
                      "long": {"in": 0.4, "read": 0.04, "write": 0.5, "out": 1.8}},
    "gpt-5.5":       {"in": 5.0,  "read": 0.5,   "out": 30.0,
                      "long": {"in": 10.0, "read": 1.0, "out": 45.0}},
    "gpt-5.4":       {"in": 2.5,  "read": 0.25,  "out": 15.0},
    "gpt-5.4-mini":  {"in": 0.75, "read": 0.075, "out": 4.5},
    "gpt-5.3-codex": {"in": 1.75, "read": 0.175, "out": 14.0},
    "gpt-5.2":       {"in": 1.75, "read": 0.175, "out": 14.0},
}

# Models with no published price are priced like their closest published
# sibling and labelled "estimated" in the dashboard. First match wins.
# Override per model in the config: "ledger_model_equivalents":
# {"codex-auto-review": "gpt-5.6-luna"}, or exact prices with "ledger_prices".
MODEL_EQUIVALENTS = [
    (r"^codex-auto-review", "gpt-5.4-mini"),
    (r"-(mini|nano)\b", "gpt-5.4-mini"),
    (r"-luna\b", "gpt-5.6-luna"),
    (r"-terra\b", "gpt-5.6-terra"),
    (r"-sol\b", "gpt-5.6-sol"),
    (r"-codex\b", "gpt-5.3-codex"),
    (r"^gpt-6", "gpt-6-astra"),
    (r"^gpt-5", "gpt-5.5"),
    (r"^o\d", "gpt-5.5"),
]
EQUIVALENTS_KEY = "=equivalents"      # reserved key inside the overrides dict
LIST_PRICES = {**CLAUDE_PRICES, **OPENAI_PRICES}


def _prefix_lookup(model: str, table: dict):
    best = None
    for prefix in table:
        if model.startswith(prefix) and (best is None or len(prefix) > len(best)):
            best = prefix
    return table[best] if best else None


def _user_prices(overrides: dict | None) -> dict:
    return {k: v for k, v in (overrides or {}).items() if k != EQUIVALENTS_KEY}


def equivalent_model(model: str, overrides: dict | None = None) -> str | None:
    """For a model with no published or user-set price: the model whose
    price stands in for it. None when the model has a real price."""
    if not model or _prefix_lookup(model, _user_prices(overrides)) or _prefix_lookup(model, LIST_PRICES):
        return None
    user = (overrides or {}).get(EQUIVALENTS_KEY) or {}
    hit = _prefix_lookup(model, user)
    if hit:
        return hit
    for pattern, sibling in MODEL_EQUIVALENTS:
        if re.search(pattern, model):
            return sibling
    return None


def _price_for(model: str, overrides: dict | None = None) -> dict | None:
    if not model:
        return None
    for table in (_user_prices(overrides), LIST_PRICES):
        hit = _prefix_lookup(model, table)
        if hit:
            return hit
    eq = equivalent_model(model, overrides)
    return _prefix_lookup(eq, LIST_PRICES) if eq else None


def call_cost(model: str, inp: int, out: int, write_5m: int, write_1h: int,
              read: int, overrides: dict | None = None) -> float | None:
    """API-equivalent USD for one response, or None if the model is unpriced.

    `out` already includes reasoning/thinking tokens on both providers.
    Anthropic cache writes: 5-minute TTL 1.25x input, 1-hour TTL 2x input.
    OpenAI: published cache-write price where there is one; long-context
    rates when the whole prompt exceeds LONG_CONTEXT.
    """
    p = _price_for(model, overrides)
    if not p:
        return None
    if "long" in p and inp + read + write_5m + write_1h > LONG_CONTEXT:
        p = {**p, **p["long"]}
    pin, pout = p["in"], p["out"]
    pread = p.get("read", pin * 0.1)
    pwrite = p.get("write", pin * 1.25)
    return (inp * pin + out * pout + write_5m * pwrite
            + write_1h * pin * 2.0 + read * pread) / 1_000_000


def _weight(row) -> float:
    """Relative weight of a call for sharing quota, when cost is unknown."""
    cost = row["cost_usd"]
    if cost is not None:
        return cost
    return (row["input_tokens"] + 5 * row["output_tokens"]
            + 1.25 * row["cache_write_tokens"] + 0.1 * row["cache_read_tokens"]) / 1e6


# ── database ─────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path   TEXT PRIMARY KEY,
    offset INTEGER NOT NULL,
    state  TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS prompts (
    id         TEXT PRIMARY KEY,
    source     TEXT NOT NULL,
    session_id TEXT NOT NULL,
    project    TEXT NOT NULL,
    ts         REAL NOT NULL,
    text       TEXT NOT NULL,
    estimated  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_prompts_session_ts ON prompts(session_id, ts);
CREATE INDEX IF NOT EXISTS idx_prompts_ts ON prompts(ts);
CREATE TABLE IF NOT EXISTS calls (
    id                 TEXT PRIMARY KEY,
    source             TEXT NOT NULL,
    session_id         TEXT NOT NULL,
    prompt_id          TEXT,
    project            TEXT NOT NULL,
    model              TEXT NOT NULL,
    ts                 REAL NOT NULL,
    input_tokens       INTEGER NOT NULL,
    output_tokens      INTEGER NOT NULL,
    cache_write_tokens INTEGER NOT NULL,
    cache_read_tokens  INTEGER NOT NULL,
    reasoning_tokens   INTEGER NOT NULL DEFAULT 0,
    cost_usd           REAL,
    quota_5h_pct       REAL,
    quota_week_pct     REAL,
    estimated          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_calls_ts ON calls(ts);
CREATE INDEX IF NOT EXISTS idx_calls_prompt ON calls(prompt_id);
CREATE INDEX IF NOT EXISTS idx_calls_session_ts ON calls(session_id, ts);
CREATE TABLE IF NOT EXISTS quota_samples (
    provider TEXT NOT NULL,
    window   TEXT NOT NULL,
    ts       REAL NOT NULL,
    pct      REAL NOT NULL,
    PRIMARY KEY (provider, window, ts)
);
CREATE TABLE IF NOT EXISTS nudges (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         REAL NOT NULL,
    session_id TEXT NOT NULL,
    kind       TEXT NOT NULL,
    message    TEXT NOT NULL,
    project    TEXT
);
CREATE INDEX IF NOT EXISTS idx_nudges_session ON nudges(session_id, ts);
CREATE TABLE IF NOT EXISTS lessons (
    id          TEXT PRIMARY KEY,
    created     REAL NOT NULL,
    updated     REAL NOT NULL,
    origin      TEXT NOT NULL,            -- 'detector' or 'analysis'
    scope       TEXT NOT NULL,            -- 'global' or a project name
    tools       TEXT NOT NULL,            -- 'claude', 'codex' or 'both'
    title       TEXT NOT NULL,
    rule        TEXT NOT NULL,            -- the line written into CLAUDE.md / AGENTS.md
    evidence    TEXT NOT NULL,
    evidence_n  INTEGER NOT NULL,
    confidence  REAL NOT NULL,
    saving      TEXT,
    status      TEXT NOT NULL DEFAULT 'open',   -- open | applied | dismissed
    applied_ts  REAL,
    applied_files TEXT
);
CREATE TABLE IF NOT EXISTS improvements (
    prompt_id  TEXT PRIMARY KEY,
    ts         REAL NOT NULL,
    rewrite    TEXT NOT NULL,
    why        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS templates (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         REAL NOT NULL,
    title      TEXT NOT NULL,
    text       TEXT NOT NULL,
    source_prompt_id TEXT
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Which quota each source draws from.
SOURCE_PROVIDER = {
    "claude_code": "claude", "cowork": "claude", "claude_chat": "claude",
    "codex": "codex", "chatgpt_chat": "codex",
}


def open_ledger(path: str = LEDGER_DB) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    return conn


def _migrate(conn):
    """Add columns introduced after the first release."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(prompts)")}
    if "cwd" not in cols:
        conn.execute("ALTER TABLE prompts ADD COLUMN cwd TEXT")
    lesson_cols = {r[1] for r in conn.execute("PRAGMA table_info(lessons)")}
    if "edited" not in lesson_cols:
        conn.execute("ALTER TABLE lessons ADD COLUMN edited INTEGER NOT NULL DEFAULT 0")
    # the optimizer's own runs were recorded under the pre-rename project name
    for table in ("calls", "prompts"):
        conn.execute(f"UPDATE {table} SET project = ? WHERE project = 'aiquotaleft-optimizer'",
                     (OPTIMIZER_PROJECT,))
    if _meta_get(conn, "cwd_backfilled") is None:
        # Re-read every log once so existing prompts get their folder path.
        conn.execute("UPDATE files SET offset = 0, state = '{}'")
        _meta_set(conn, "cwd_backfilled", "1")


def _meta_get(conn, key, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def _meta_set(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, str(value)))


# ── helpers ──────────────────────────────────────────────────────────────────

def _ts(value) -> float | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def project_name(cwd: str | None) -> str:
    """Short, stable project label from a working directory."""
    if not cwd:
        return "unknown"
    cwd = cwd.rstrip("/")
    if "/scratch-workspaces/" in cwd:
        return "scratch"
    if "/local-agent-mode-sessions/" in cwd:
        return "cowork"
    if cwd == os.path.expanduser("~"):
        return "~"
    return os.path.basename(cwd) or cwd


def _text_of(content) -> str:
    """User-typed text from a message content field (str or block list)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") in ("text", "input_text"):
                parts.append(b.get("text", ""))
        return "\n".join(p for p in parts if p)
    return ""


def _is_real_prompt(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    # Harness-generated user turns, not something the person typed.
    return not (t.startswith("[Request interrupted")
                or t.startswith("<local-command-")
                or t.startswith("Caveat: The messages below were generated"))


def _read_new_lines(path: str, offset: int):
    """Yield complete lines appended after `offset`, then the new offset."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return [], offset
    if size < offset:          # truncated or replaced: start over
        offset = 0
    if size == offset:
        return [], offset
    with open(path, "rb") as f:
        f.seek(offset)
        data = f.read()
    end = data.rfind(b"\n")
    if end < 0:
        return [], offset
    chunk = data[: end + 1]
    lines = chunk.decode("utf-8", errors="replace").splitlines()
    return lines, offset + len(chunk)


# ── parsers ──────────────────────────────────────────────────────────────────
# Each parser takes (lines, state) and returns (prompts, calls, samples, state).
# `state` is a small per-file dict persisted between passes.

def _claude_usage_call(d: dict, source: str, session: str, project: str,
                       overrides: dict | None) -> dict | None:
    msg = d.get("message")
    if not isinstance(msg, dict) or msg.get("role") != "assistant":
        return None
    usage = msg.get("usage")
    model = msg.get("model") or ""
    if not usage or not model or model.startswith("<"):
        return None
    mid = msg.get("id") or d.get("uuid")
    if not mid:
        return None
    inp = int(usage.get("input_tokens") or 0)
    out = int(usage.get("output_tokens") or 0)
    read = int(usage.get("cache_read_input_tokens") or 0)
    write = int(usage.get("cache_creation_input_tokens") or 0)
    cc = usage.get("cache_creation") or {}
    w1h = int(cc.get("ephemeral_1h_input_tokens") or 0)
    w5m = int(cc.get("ephemeral_5m_input_tokens") or 0)
    if w1h + w5m != write:     # no breakdown: assume the 5-minute TTL
        w5m, w1h = write, 0
    reasoning = int((usage.get("output_tokens_details") or {}).get("thinking_tokens") or 0)
    ts = _ts(d.get("timestamp")) or time.time()
    return {
        "id": f"anthropic:{mid}", "source": source, "session_id": session,
        "project": project, "model": model, "ts": ts,
        "input_tokens": inp, "output_tokens": out,
        "cache_write_tokens": write, "cache_read_tokens": read,
        "reasoning_tokens": reasoning,
        "cost_usd": call_cost(model, inp, out, w5m, w1h, read, overrides),
    }


def parse_claude_code(lines, state, overrides=None):
    """Claude Code transcript lines (one JSON object per line)."""
    prompts, calls = [], []
    for line in lines:
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        session = d.get("sessionId") or state.get("session") or "unknown"
        if d.get("cwd"):
            state["cwd"] = d["cwd"]
        project = project_name(state.get("cwd"))
        t = d.get("type")
        if t == "user" and not d.get("isSidechain") and not d.get("isMeta") \
                and not d.get("toolUseResult"):
            text = _text_of((d.get("message") or {}).get("content"))
            if _is_real_prompt(text) and d.get("uuid"):
                prompts.append({
                    "id": f"cc:{d['uuid']}", "source": "claude_code", "cwd": state.get("cwd"),
                    "session_id": session, "project": project,
                    "ts": _ts(d.get("timestamp")) or time.time(), "text": text,
                })
        elif t == "assistant":
            c = _claude_usage_call(d, "claude_code", session, project, overrides)
            if c:
                calls.append(c)
    return prompts, calls, [], state


def parse_cowork(lines, state, overrides=None):
    """Cowork audit log lines (Agent SDK stream format)."""
    prompts, calls = [], []
    for line in lines:
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        session = d.get("session_id") or state.get("session") or "unknown"
        state["session"] = session
        t = d.get("type")
        if t == "system" and d.get("subtype") == "init":
            state["cwd"] = d.get("cwd")
        project = "cowork"
        if t == "user" and not d.get("parent_tool_use_id"):
            text = _text_of((d.get("message") or {}).get("content"))
            if _is_real_prompt(text) and d.get("uuid"):
                prompts.append({
                    "id": f"cowork:{d['uuid']}", "source": "cowork",
                    "session_id": session, "project": project,
                    "ts": _ts(d.get("timestamp")) or time.time(), "text": text,
                })
        elif t == "assistant":
            c = _claude_usage_call(d, "cowork", session, project, overrides)
            if c:
                calls.append(c)
    return prompts, calls, [], state


def _codex_windows(rate_limits: dict) -> list[tuple[str, float]]:
    out = []
    for key in ("primary", "secondary"):
        w = (rate_limits or {}).get(key) or {}
        pct = w.get("used_percent")
        mins = w.get("window_minutes")
        if pct is None or not mins:
            continue
        window = "5h" if mins <= 600 else "week"
        out.append((window, float(pct)))
    return out


def parse_codex(lines, state, overrides=None):
    """Codex rollout lines. Newer logs carry one token_usage_record per
    response; older ones only token_count events. Never count both."""
    prompts, calls, samples = [], [], []
    for line in lines:
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        typ = d.get("type")
        p = d.get("payload") or {}
        ts = _ts(d.get("timestamp")) or time.time()
        if typ == "session_meta":
            state["session"] = p.get("session_id") or p.get("id") or "unknown"
            state["cwd"] = p.get("cwd")
            # Sub-threads (e.g. the auto-review agent) have a parent; their
            # "user" messages are machine-written, not the owner's prompts.
            state["sub"] = bool(p.get("parent_thread_id"))
            continue
        if typ == "turn_context":
            if p.get("model"):
                state["model"] = p["model"]
            if p.get("cwd"):
                state["cwd"] = p["cwd"]
            continue
        session = state.get("session") or "unknown"
        project = project_name(state.get("cwd"))
        model = state.get("model") or "unknown"
        if typ == "event_msg" and p.get("type") == "item_completed":
            item = p.get("item") or {}
            if item.get("type") == "UserMessage" and not state.get("sub"):
                text = _text_of(item.get("content"))
                if _is_real_prompt(text):
                    pid = f"codex:{session}:{p.get('turn_id')}:{item.get('id')}"
                    prompts.append({
                        "id": pid, "source": "codex", "session_id": session, "cwd": state.get("cwd"),
                        "project": project, "ts": ts, "text": text,
                    })
            continue
        usage, cid = None, None
        if typ == "token_usage_record":
            state["records"] = True
            usage = p.get("usage")
            cid = p.get("response_id")
        elif typ == "event_msg" and p.get("type") == "token_count":
            for window, pct in _codex_windows(p.get("rate_limits")):
                samples.append({"provider": "codex", "window": window, "ts": ts, "pct": pct})
            if not state.get("records"):
                usage = (p.get("info") or {}).get("last_token_usage")
                cid = f"{session}:{d.get('ordinal', ts)}"
        if not usage or not cid:
            continue
        total_in = int(usage.get("input_tokens") or 0)
        cached = int(usage.get("cached_input_tokens") or 0)
        cwrite = int(usage.get("cache_write_input_tokens") or 0)
        inp = max(total_in - cached - cwrite, 0)   # OpenAI input includes cached
        out = int(usage.get("output_tokens") or 0)
        reasoning = int(usage.get("reasoning_output_tokens") or 0)
        calls.append({
            "id": f"openai:{cid}", "source": "codex", "session_id": session,
            "project": project, "model": model, "ts": ts,
            "input_tokens": inp, "output_tokens": out,
            "cache_write_tokens": cwrite, "cache_read_tokens": cached,
            "reasoning_tokens": reasoning,
            "cost_usd": call_cost(model, inp, out, cwrite, 0, cached, overrides),
        })
    return prompts, calls, samples, state


SOURCES = [
    ("claude_code", CLAUDE_CODE_GLOB, parse_claude_code),
    ("cowork", COWORK_GLOB, parse_cowork),
    ("codex", CODEX_GLOB, parse_codex),
]


# ── ingest ───────────────────────────────────────────────────────────────────

_CALL_COLS = ("id", "source", "session_id", "project", "model", "ts",
              "input_tokens", "output_tokens", "cache_write_tokens",
              "cache_read_tokens", "reasoning_tokens", "cost_usd", "estimated")


def _insert(conn, prompts, calls, samples):
    conn.executemany(
        "INSERT INTO prompts (id, source, session_id, project, ts, text, estimated, cwd) "
        "VALUES (:id, :source, :session_id, :project, :ts, :text, :estimated, :cwd) "
        "ON CONFLICT(id) DO UPDATE SET cwd = excluded.cwd "
        "WHERE prompts.cwd IS NULL AND excluded.cwd IS NOT NULL",
        [{"estimated": 0, "cwd": None, **p} for p in prompts],
    )
    conn.executemany(
        # A response can be logged more than once (one line per content
        # block); keep the copy with the most output tokens.
        f"INSERT INTO calls ({', '.join(_CALL_COLS)}) "
        f"VALUES ({', '.join(':' + c for c in _CALL_COLS)}) "
        f"ON CONFLICT(id) DO UPDATE SET output_tokens=excluded.output_tokens, "
        f"reasoning_tokens=excluded.reasoning_tokens, cost_usd=excluded.cost_usd "
        f"WHERE excluded.output_tokens > calls.output_tokens",
        [{"estimated": 0, **c} for c in calls],
    )
    conn.executemany(
        "INSERT OR IGNORE INTO quota_samples (provider, window, ts, pct) "
        "VALUES (:provider, :window, :ts, :pct)",
        samples,
    )


def ingest(conn: sqlite3.Connection, sources=None, overrides: dict | None = None,
           time_budget: float | None = None) -> dict:
    """Read new log lines from every source. Returns counts of new rows.

    `time_budget` (seconds) stops early between files; the next pass resumes.
    """
    started = time.time()
    counts = {"prompts": 0, "calls": 0, "files": 0, "complete": True}
    for source, pattern, parser in (sources or SOURCES):
        paths = sorted(glob.glob(pattern, recursive=True), key=_mtime)
        for path in paths:
            if time_budget is not None and time.time() - started > time_budget:
                counts["complete"] = False
                break
            row = conn.execute("SELECT offset, state FROM files WHERE path=?", (path,)).fetchone()
            offset = row["offset"] if row else 0
            state = json.loads(row["state"]) if row else {}
            lines, new_offset = _read_new_lines(path, offset)
            if new_offset == offset:
                continue
            if new_offset < offset or offset == 0:
                state = {}
            try:
                prompts, calls, samples, state = parser(lines, state, overrides)
            except Exception:
                log.exception("ledger: failed to parse %s", path)
                continue
            _insert(conn, prompts, calls, samples)
            conn.execute(
                "INSERT OR REPLACE INTO files (path, offset, state) VALUES (?, ?, ?)",
                (path, new_offset, json.dumps(state)),
            )
            conn.commit()
            counts["files"] += 1
            counts["prompts"] += len(prompts)
            counts["calls"] += len(calls)
    reprice(conn, overrides)
    link_prompts(conn)
    import_claude_samples(conn)
    attribute_quota(conn)
    conn.commit()
    return counts


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0


def link_prompts(conn):
    """Attach each unlinked call to the latest prompt of its session at or
    before the call. Works across files (Claude Code subagent transcripts
    share the parent's session id)."""
    conn.execute("""
        UPDATE calls SET prompt_id = (
            SELECT p.id FROM prompts p
            WHERE p.session_id = calls.session_id AND p.ts <= calls.ts
            ORDER BY p.ts DESC LIMIT 1
        )
        WHERE prompt_id IS NULL
    """)


def import_claude_samples(conn, history_db: str = HISTORY_DB):
    """Copy TokenCoach's own Claude 5-hour samples (used %) into the ledger."""
    if not os.path.exists(history_db):
        return
    last = float(_meta_get(conn, "claude_samples_until", 0))
    try:
        src = sqlite3.connect(f"file:{history_db}?mode=ro", uri=True, timeout=5)
        rows = src.execute(
            "SELECT ts, pct FROM samples WHERE key='claude' AND ts > ? ORDER BY ts",
            (last,),
        ).fetchall()
        src.close()
    except sqlite3.Error:
        log.debug("ledger: could not read history samples", exc_info=True)
        return
    if not rows:
        return
    conn.executemany(
        "INSERT OR IGNORE INTO quota_samples (provider, window, ts, pct) VALUES ('claude', '5h', ?, ?)",
        rows,
    )
    _meta_set(conn, "claude_samples_until", rows[-1][0])


# A gap longer than this between two samples is too coarse to attribute.
MAX_SAMPLE_GAP = 6 * 3600
# A fall of at least this many points means the window reset. Smaller dips are
# noise: parallel sessions report slightly stale readings of the same counter.
RESET_DROP = 30
ATTRIBUTION_VERSION = "2"


def quota_increments(samples, level: float | None = None):
    """Yield (prev_ts, ts, used_delta) for each rise in a used-% series.

    Measures against the highest reading seen in the current window, so a
    stale reading followed by the real one is not counted twice.
    Returns the final level via StopIteration value (see _increments_list).
    """
    prev_ts = None
    for ts, pct in samples:
        if level is None:
            level = pct
        elif level - pct >= RESET_DROP:     # new window
            level = pct
            if prev_ts is not None and pct > 0:
                yield prev_ts, ts, pct
        elif pct > level:
            if prev_ts is not None:
                yield prev_ts, ts, pct - level
            level = pct
        prev_ts = ts
    return level


def _increments_list(samples, level):
    gen = quota_increments(samples, level)
    out = []
    while True:
        try:
            out.append(next(gen))
        except StopIteration as stop:
            return out, stop.value


def attribute_quota(conn):
    """Share each rise in used-% across the calls made in that interval."""
    if _meta_get(conn, "attribution_version") != ATTRIBUTION_VERSION:
        conn.execute("UPDATE calls SET quota_5h_pct = NULL, quota_week_pct = NULL")
        conn.execute("DELETE FROM meta WHERE key LIKE 'attributed_until:%' "
                     "OR key LIKE 'attributed_level:%'")
        _meta_set(conn, "attribution_version", ATTRIBUTION_VERSION)
    for provider, sources in (("claude", ("claude_code", "cowork")), ("codex", ("codex",))):
        for window, col in (("5h", "quota_5h_pct"), ("week", "quota_week_pct")):
            key = f"{provider}:{window}"
            since = float(_meta_get(conn, f"attributed_until:{key}", 0))
            level = _meta_get(conn, f"attributed_level:{key}")
            level = float(level) if level is not None else None
            samples = conn.execute(
                "SELECT ts, pct FROM quota_samples WHERE provider=? AND window=? "
                "AND ts >= ? ORDER BY ts",
                (provider, window, since),
            ).fetchall()
            if len(samples) < 2:
                continue
            # The first sample was the last one of the previous pass; its
            # level is already stored, so start the walk from it.
            increments, level = _increments_list([(r["ts"], r["pct"]) for r in samples], level)
            marks = ",".join("?" * len(sources))
            for a_ts, b_ts, delta in increments:
                if b_ts - a_ts > MAX_SAMPLE_GAP:
                    continue
                rows = conn.execute(
                    f"SELECT id, cost_usd, input_tokens, output_tokens, cache_write_tokens, "
                    f"cache_read_tokens FROM calls WHERE source IN ({marks}) "
                    f"AND ts > ? AND ts <= ? AND estimated = 0",
                    (*sources, a_ts, b_ts),
                ).fetchall()
                total = sum(_weight(r) for r in rows)
                if not rows or total <= 0:
                    continue
                conn.executemany(
                    f"UPDATE calls SET {col} = COALESCE({col}, 0) + ? WHERE id = ?",
                    [(delta * _weight(r) / total, r["id"]) for r in rows],
                )
            _meta_set(conn, f"attributed_until:{key}", samples[-1]["ts"])
            if level is not None:
                _meta_set(conn, f"attributed_level:{key}", level)


# ── queries ──────────────────────────────────────────────────────────────────

def _day_start(days_ago: int = 0) -> float:
    d = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return (d - timedelta(days=days_ago)).timestamp()


def today_summary(conn) -> dict:
    """Numbers for the menu: today's spend, top project, top prompt."""
    since = _day_start()
    tot = conn.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(cost_usd),0) cost, "
        "SUM(input_tokens+output_tokens+cache_write_tokens+cache_read_tokens) tokens "
        "FROM calls WHERE ts >= ? AND estimated = 0", (since,),
    ).fetchone()
    prompts = conn.execute(
        "SELECT COUNT(*) FROM prompts WHERE ts >= ? AND estimated = 0", (since,),
    ).fetchone()[0]
    top_project = conn.execute(
        "SELECT project, SUM(cost_usd) cost FROM calls WHERE ts >= ? AND estimated = 0 "
        "GROUP BY project ORDER BY cost DESC LIMIT 1", (since,),
    ).fetchone()
    top = top_prompts(conn, since, limit=1)
    return {
        "calls": tot["n"], "cost": tot["cost"] or 0.0, "tokens": tot["tokens"] or 0,
        "prompts": prompts,
        "top_project": dict(top_project) if top_project and top_project["project"] else None,
        "top_prompt": top[0] if top else None,
    }


def top_prompts(conn, since: float, limit: int = 50, exclude_project: str | None = None) -> list[dict]:
    rows = conn.execute(
        """
        SELECT p.id, p.source, p.project, p.session_id, p.ts, p.text, p.estimated,
               COUNT(c.id) calls,
               COALESCE(SUM(c.cost_usd), 0) cost,
               SUM(c.input_tokens) input_tokens, SUM(c.output_tokens) output_tokens,
               SUM(c.cache_write_tokens) cache_write_tokens,
               SUM(c.cache_read_tokens) cache_read_tokens,
               MAX(c.input_tokens + c.cache_write_tokens + c.cache_read_tokens) peak_context,
               SUM(c.quota_5h_pct) quota_5h, SUM(c.quota_week_pct) quota_week,
               GROUP_CONCAT(DISTINCT c.model) models
        FROM prompts p JOIN calls c ON c.prompt_id = p.id
        WHERE p.ts >= ? AND (? IS NULL OR p.project != ?)
        GROUP BY p.id
        ORDER BY cost DESC, (SUM(c.input_tokens) + SUM(c.output_tokens)
                             + SUM(c.cache_read_tokens)) DESC
        LIMIT ?
        """,
        (since, exclude_project, exclude_project, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def breakdown(conn, since: float, by: str) -> list[dict]:
    """Totals grouped by 'day', 'project', 'model' or 'source'."""
    expr = {
        "day": "date(ts, 'unixepoch', 'localtime')",
        "project": "project", "model": "model", "source": "source",
    }[by]
    rows = conn.execute(
        f"""
        SELECT {expr} k, COUNT(*) calls, COUNT(DISTINCT prompt_id) prompts,
               COALESCE(SUM(cost_usd), 0) cost,
               SUM(CASE WHEN cost_usd IS NULL THEN 1 ELSE 0 END) unpriced,
               SUM(input_tokens) input_tokens, SUM(output_tokens) output_tokens,
               SUM(cache_write_tokens) cache_write_tokens,
               SUM(cache_read_tokens) cache_read_tokens,
               SUM(quota_5h_pct) quota_5h, MAX(estimated) estimated
        FROM calls WHERE ts >= ?
        GROUP BY k ORDER BY {"k" if by == "day" else "cost DESC, calls DESC"}
        """,
        (since,),
    ).fetchall()
    return [dict(r) for r in rows]


def session_stats(conn, session_ids: list[str]) -> dict[str, dict]:
    if not session_ids:
        return {}
    marks = ",".join("?" * len(session_ids))
    rows = conn.execute(
        f"""
        SELECT session_id, COUNT(*) calls, COALESCE(SUM(cost_usd),0) cost,
               MIN(ts) started, MAX(ts) ended,
               MAX(input_tokens + cache_write_tokens + cache_read_tokens) peak_context,
               (SELECT COUNT(*) FROM prompts p WHERE p.session_id = c.session_id) prompts
        FROM calls c WHERE session_id IN ({marks}) GROUP BY session_id
        """,
        session_ids,
    ).fetchall()
    return {r["session_id"]: dict(r) for r in rows}


def ledger_overrides(config: dict) -> dict:
    """User-supplied per-model prices and price equivalents from the app config."""
    prices = config.get("ledger_prices") or {}
    out = {k: v for k, v in prices.items() if isinstance(v, dict) and "in" in v and "out" in v}
    eq = config.get("ledger_model_equivalents") or {}
    eq = {k: v for k, v in eq.items() if isinstance(v, str) and _prefix_lookup(v, LIST_PRICES)}
    if eq:
        out[EQUIVALENTS_KEY] = eq
    return out


def reprice(conn, overrides: dict | None = None) -> int:
    """Recompute costs of non-Claude calls when the pricing rules change, and
    price any unpriced ones. Claude calls keep their exact ingest-time cost
    (which knew the 5-minute / 1-hour cache split)."""
    version = hashlib.sha1(json.dumps([MODEL_EQUIVALENTS, LIST_PRICES, overrides or {}],
                                      sort_keys=True).encode()).hexdigest()[:12]
    where = "estimated = 0 AND model NOT LIKE 'claude-%'"
    if _meta_get(conn, "pricing_version") == version:
        where += " AND cost_usd IS NULL"
    rows = conn.execute(f"SELECT id, model, input_tokens, output_tokens, cache_write_tokens, "
                        f"cache_read_tokens FROM calls WHERE {where}").fetchall()
    conn.executemany("UPDATE calls SET cost_usd = ? WHERE id = ?", [
        (call_cost(r["model"], r["input_tokens"], r["output_tokens"], r["cache_write_tokens"], 0,
                   r["cache_read_tokens"], overrides), r["id"]) for r in rows])
    _meta_set(conn, "pricing_version", version)
    return len(rows)


def fmt_usd(v: float | None) -> str:
    if v is None:
        return "—"
    if v >= 100:
        return f"${v:,.0f}"
    if v >= 1:
        return f"${v:,.2f}"
    return f"${v:.3f}"


def fmt_tokens(n: int | None) -> str:
    n = n or 0
    if n >= 1_000_000_000:
        return f"{n / 1e9:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1e6:.1f}M"
    if n >= 1_000:
        return f"{n / 1e3:.0f}k"
    return str(n)
