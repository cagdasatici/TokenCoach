"""Coaching: lessons learned from the ledger, written into the agent's own
instruction files, with before/after impact; and per-prompt rewrites.

Lesson lifecycle
  detected/proposed -> open (confidence grows as evidence accumulates)
  open + confidence >= READY  -> "ready": one click writes it into the files
  open + REVIEW <= conf < READY -> "review": shown with its evidence; the person decides
  open + conf < REVIEW        -> "collecting": shown with how much evidence is still needed
  applied -> measured before/after; can be removed again

Confidence is never taken on the model's word alone: it is capped by how much
independent evidence (distinct sessions) supports the lesson.

Files are edited only inside a clearly marked block, rebuilt from the applied
lessons each time, with a dated backup of the original first.
"""

import hashlib
import json
import os
import re
import shutil
import time
from datetime import datetime

from tokencoach import ledger
from tokencoach.config import log, APP_NAME
from tokencoach.nudge import BROAD, SPECIFIC

READY = 0.95
REVIEW = 0.70
DETECT_DAYS = 30
BACKUP_DIR = os.path.join(os.path.dirname(ledger.LEDGER_DB), "backups")
def _global_files() -> dict:
    from tokencoach.config import DEMO, APP_SUPPORT
    home = os.path.join(APP_SUPPORT, "demo-home") if DEMO else os.path.expanduser("~")
    return {"claude": os.path.join(home, ".claude", "CLAUDE.md"),
            "codex": os.path.join(home, ".codex", "AGENTS.md")}


GLOBAL_FILES = _global_files()
FILE_FOR_TOOL = {"claude": "CLAUDE.md", "codex": "AGENTS.md"}
BLOCK_START = f"<!-- {APP_NAME} lessons: managed block, edit or remove from the {APP_NAME} dashboard -->"
BLOCK_END = f"<!-- /{APP_NAME} lessons -->"
UNAPPLIABLE_PROJECTS = {"scratch", "cowork", "unknown", "~", ledger.OPTIMIZER_PROJECT}


def evidence_factor(n: int) -> float:
    """Upper bound on confidence from the number of distinct supporting sessions."""
    if n >= 8:
        return 0.99
    return {7: 0.94, 6: 0.93, 5: 0.88, 4: 0.85, 3: 0.75, 2: 0.6, 1: 0.4}.get(n, 0.0)


def status_of(lesson: dict) -> str:
    if lesson["status"] != "open":
        return lesson["status"]
    c = lesson["confidence"]
    return "ready" if c >= READY else "review" if c >= REVIEW else "collecting"


def _lesson_id(*parts) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]


def _upsert(conn, lesson: dict):
    """Insert or refresh an open lesson; never touch applied/dismissed ones."""
    now = time.time()
    row = conn.execute("SELECT status FROM lessons WHERE id = ?", (lesson["id"],)).fetchone()
    if row and row["status"] != "open":
        conn.execute("UPDATE lessons SET evidence = ?, evidence_n = ?, updated = ? WHERE id = ?",
                     (lesson["evidence"], lesson["evidence_n"], now, lesson["id"]))
        return
    conn.execute(
        """INSERT INTO lessons (id, created, updated, origin, scope, tools, title, rule, evidence,
               evidence_n, confidence, saving)
           VALUES (:id, :now, :now, :origin, :scope, :tools, :title, :rule, :evidence,
               :evidence_n, :confidence, :saving)
           ON CONFLICT(id) DO UPDATE SET updated = :now,
               title = CASE WHEN lessons.edited THEN lessons.title ELSE :title END,
               rule = CASE WHEN lessons.edited THEN lessons.rule ELSE :rule END,
               evidence = :evidence, evidence_n = :evidence_n, confidence = :confidence,
               saving = :saving""",
        {"now": now, "saving": None, **lesson})


# ── deterministic detectors ─────────────────────────────────────────────────

def _tools_of(sources: set[str]) -> str:
    c = bool(sources & {"claude_code", "cowork"})
    x = "codex" in sources
    return "both" if c and x else "codex" if x else "claude"


GLOBAL_AFTER = 3         # a pattern in this many projects becomes one global lesson
MIN_SESSIONS = 2         # ignore one-off patterns

DETECTORS = {
    "long-sessions": {
        "title": "Keep sessions to one task",
        "rule": ("Keep each session to one task. When a task is finished, or the conversation "
                 "has grown long (roughly 50+ steps), say so and suggest starting a fresh "
                 "session with a 2-3 line summary instead of continuing here."),
    },
    "broad-asks": {
        "title": "Scope broad requests first",
        "rule": ("When a request is broad (for example 'implement all open things' or 'review "
                 "the whole project'), first reply with a short numbered list of the concrete "
                 "items you would handle and the files involved, and wait for confirmation "
                 "before exploring or editing."),
    },
}


def _share(part, whole) -> float:
    """Cost share, or response share when the tool has no prices (Codex)."""
    pc, wc = sum(r["cost"] for r in part), sum(r["cost"] for r in whole)
    if wc > 0:
        return pc / wc
    return sum(r["calls"] for r in part) / max(sum(r["calls"] for r in whole), 1)


def _find_long_sessions(conn, since, days):
    rows = conn.execute(
        """SELECT project, session_id, MIN(source) source, COUNT(*) calls,
                  COALESCE(SUM(cost_usd), 0) cost,
                  MAX(input_tokens + cache_write_tokens + cache_read_tokens) ctx
           FROM calls WHERE ts >= ? AND estimated = 0 GROUP BY session_id""", (since,)).fetchall()
    by_project: dict[str, list] = {}
    for r in rows:
        by_project.setdefault(r["project"], []).append(r)
    out = {}
    for project, sessions in by_project.items():
        long = [s for s in sessions if s["calls"] >= 80 or s["ctx"] >= 250_000]
        if long:
            out[project] = {
                "k": len(long), "strong": _share(long, sessions) >= 0.4,
                "sources": {s["source"] for s in long},
                "evidence": (f"{len(long)} long session{'s' if len(long) != 1 else ''} (80+ responses "
                             f"or 250k+ context) in {project} over {days} days, "
                             f"{_share(long, sessions):.0%} of its usage."),
            }
    return out


def _find_broad_asks(conn, since, days):
    rows = conn.execute(
        """SELECT p.project, p.session_id, p.text, p.source, COUNT(c.id) calls
           FROM prompts p JOIN calls c ON c.prompt_id = p.id
           WHERE p.ts >= ? AND p.estimated = 0 GROUP BY p.id""", (since,)).fetchall()
    by_project: dict[str, list] = {}
    for r in rows:
        by_project.setdefault(r["project"], []).append(r)
    out = {}
    for project, prompts in by_project.items():
        if len(prompts) < 5:
            continue
        broad = [p for p in prompts if BROAD.search(p["text"]) and not SPECIFIC.search(p["text"])]
        if not broad:
            continue
        avg_all = sum(p["calls"] for p in prompts) / len(prompts)
        avg_broad = sum(p["calls"] for p in broad) / len(broad)
        if avg_broad < 1.5 * avg_all:
            continue
        out[project] = {
            "k": len({p["session_id"] for p in broad}), "strong": avg_broad >= 2 * avg_all,
            "sources": {p["source"] for p in broad},
            "evidence": (f"{len(broad)} broad asks in {project} averaged {avg_broad:.0f} responses "
                         f"vs {avg_all:.0f} for all prompts there ({days} days)."),
        }
    return out


def detect_lessons(conn, days: int = DETECT_DAYS) -> int:
    """Refresh detector lessons from the last `days`. A pattern seen in several
    projects becomes one global lesson; otherwise one lesson per project with
    at least MIN_SESSIONS supporting sessions. Returns how many were refreshed."""
    since = time.time() - days * 86400
    n = 0
    for key, finder in (("long-sessions", _find_long_sessions), ("broad-asks", _find_broad_asks)):
        spec = DETECTORS[key]
        found = {p: f for p, f in finder(conn, since, days).items() if p not in UNAPPLIABLE_PROJECTS}
        multi = [p for p, f in found.items() if f["k"] >= 1]
        if len(multi) >= GLOBAL_AFTER:
            k = sum(found[p]["k"] for p in multi)
            strong = sum(found[p]["strong"] for p in multi) >= len(multi) / 2
            top = sorted(multi, key=lambda p: -found[p]["k"])[:4]
            _upsert(conn, {
                "id": _lesson_id("detector", key, "global"), "origin": "detector",
                "scope": "global", "tools": _tools_of(set().union(*(found[p]["sources"] for p in multi))),
                "title": spec["title"], "rule": spec["rule"],
                "evidence": (f"{k} sessions across {len(multi)} projects in {days} days "
                             f"(most in {', '.join(top)})."),
                "evidence_n": k, "confidence": round(min(0.97 if strong else 0.9, evidence_factor(k)), 3),
            })
            # project-level duplicates of a global lesson are clutter
            for p in found:
                conn.execute("DELETE FROM lessons WHERE id = ? AND status = 'open'",
                             (_lesson_id("detector", key, p),))
            n += 1
            continue
        for project, f in found.items():
            if f["k"] < MIN_SESSIONS:
                continue
            _upsert(conn, {
                "id": _lesson_id("detector", key, project), "origin": "detector",
                "scope": project, "tools": _tools_of(f["sources"]),
                "title": spec["title"], "rule": spec["rule"], "evidence": f["evidence"],
                "evidence_n": f["k"],
                "confidence": round(min(0.97 if f["strong"] else 0.88, evidence_factor(f["k"])), 3),
            })
            n += 1
    conn.commit()
    return n


def record_analysis_lessons(conn, lessons: list[dict], scopes: dict[int, dict]) -> int:
    """Store lessons proposed by the Analyze run, with calibrated confidence."""
    known_projects = {s["project"] for s in scopes.values()}
    count = 0
    for l in lessons:
        rule = (l.get("rule") or "").strip()
        if not rule:
            continue
        cited = [scopes[i] for i in l.get("evidence_prompts") or [] if isinstance(i, int) and i in scopes]
        k = len({c["session_id"] for c in cited})
        scope = (l.get("scope") or "global").strip()
        if scope != "global" and scope not in known_projects:
            scope = "global"
        tools = l.get("tools") if l.get("tools") in ("claude", "codex", "both") else \
            _tools_of({c["source"] for c in cited}) if cited else "both"
        try:
            model_conf = float(l.get("confidence") or 0)
        except (TypeError, ValueError):
            model_conf = 0.0
        conf = min(max(model_conf, 0.0), evidence_factor(k))
        norm = re.sub(r"\W+", " ", rule.lower()).strip()
        _upsert(conn, {
            "id": _lesson_id("analysis", scope, norm),
            "origin": "analysis", "scope": scope, "tools": tools,
            "title": (l.get("title") or rule[:60]).strip()[:80], "rule": rule,
            "evidence": f"Seen in {k} session{'s' if k != 1 else ''} of your costliest prompts (Analyze run).",
            "evidence_n": k, "confidence": round(conf, 3),
            "saving": (l.get("saving") or None),
        })
        count += 1
    conn.commit()
    return count


# ── applying lessons to instruction files ──────────────────────────────────

def project_dir(conn, project: str, sources: tuple[str, ...]) -> str | None:
    marks = ",".join("?" * len(sources))
    row = conn.execute(
        f"SELECT cwd, COUNT(*) n FROM prompts WHERE project = ? AND cwd IS NOT NULL "
        f"AND source IN ({marks}) GROUP BY cwd ORDER BY n DESC LIMIT 1",
        (project, *sources)).fetchone()
    if row and os.path.isdir(row["cwd"]):
        return row["cwd"]
    return None


def target_files(conn, lesson: dict) -> list[str]:
    tools = ["claude", "codex"] if lesson["tools"] == "both" else [lesson["tools"]]
    out = []
    for t in tools:
        if lesson["scope"] == "global":
            out.append(_global_files()[t])
            continue
        if lesson["scope"] in UNAPPLIABLE_PROJECTS:
            continue
        src = ("claude_code", "cowork") if t == "claude" else ("codex",)
        d = project_dir(conn, lesson["scope"], src) or project_dir(conn, lesson["scope"], ("claude_code", "cowork", "codex"))
        if d:
            out.append(os.path.join(d, FILE_FOR_TOOL[t]))
    return out


def render_block(rules: list[tuple[str, str]]) -> str:
    lines = [BLOCK_START, f"## Lessons from your usage ({APP_NAME})", ""]
    lines += [f"- {rule} <!-- {lid} -->" for lid, rule in rules]
    lines.append(BLOCK_END)
    return "\n".join(lines)


def write_block(path: str, rules: list[tuple[str, str]]) -> None:
    """Replace (or add, or remove) our managed block, leaving the rest untouched."""
    existing = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            existing = f.read()
        os.makedirs(BACKUP_DIR, exist_ok=True)
        safe = re.sub(r"[^\w.-]+", "_", path.strip("/"))
        backup = os.path.join(BACKUP_DIR, f"{datetime.now():%Y%m%d-%H%M%S}-{safe}")
        shutil.copy2(path, backup)
    pattern = re.compile(re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END) + r"\n?", re.S)
    body = pattern.sub("", existing).rstrip("\n")
    if rules:
        body = (body + "\n\n" if body else "") + render_block(rules) + "\n"
    elif body:
        body += "\n"
    if not body and not os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + f".{APP_NAME.lower()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(body)
    os.replace(tmp, path)


def _rules_for_file(conn, path: str) -> list[tuple[str, str]]:
    rows = conn.execute("SELECT id, rule, applied_files FROM lessons WHERE status = 'applied' "
                        "ORDER BY applied_ts").fetchall()
    return [(r["id"], r["rule"]) for r in rows if path in json.loads(r["applied_files"] or "[]")]


def apply_lesson(conn, lesson_id: str, allow_review: bool = False) -> list[str]:
    row = conn.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
    if not row:
        raise ValueError("Unknown lesson.")
    lesson = dict(row)
    st = status_of(lesson)
    if st == "applied":
        return json.loads(lesson["applied_files"] or "[]")
    # Your own wording is yours to apply; otherwise evidence decides.
    confirmed_by_you = allow_review and (st == "review" or lesson.get("edited"))
    if st == "dismissed" or (st in ("review", "collecting") and not confirmed_by_you):
        raise ValueError("This lesson needs more evidence (or your confirmation) before it is applied.")
    files = target_files(conn, lesson)
    if not files:
        raise ValueError("No project folder found for this lesson.")
    conn.execute("UPDATE lessons SET status = 'applied', applied_ts = ?, applied_files = ? WHERE id = ?",
                 (time.time(), json.dumps(files), lesson_id))
    for path in files:
        write_block(path, _rules_for_file(conn, path))
    conn.commit()
    return files


def unapply_lesson(conn, lesson_id: str) -> None:
    row = conn.execute("SELECT applied_files FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
    if not row:
        raise ValueError("Unknown lesson.")
    files = json.loads(row["applied_files"] or "[]")
    conn.execute("UPDATE lessons SET status = 'dismissed', applied_files = NULL WHERE id = ?", (lesson_id,))
    for path in files:
        write_block(path, _rules_for_file(conn, path))
    conn.commit()


MAX_RULE_CHARS = 600


def edit_lesson(conn, lesson_id: str, title: str | None = None, rule: str | None = None,
                scope: str | None = None, tools: str | None = None) -> dict:
    """Let the person reword a lesson (and, before it is applied, retarget it).
    Edited lessons keep their wording when detectors or Analyze refresh them;
    an applied lesson is rewritten in its files immediately."""
    row = conn.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
    if not row:
        raise ValueError("Unknown lesson.")
    lesson = dict(row)
    if rule is not None:
        rule = " ".join(rule.split())           # one line: it becomes a bullet
        if not rule:
            raise ValueError("The rule can't be empty.")
        if len(rule) > MAX_RULE_CHARS:
            raise ValueError(f"Keep the rule under {MAX_RULE_CHARS} characters.")
        lesson["rule"] = rule
    if title is not None:
        title = " ".join(title.split())[:80]
        lesson["title"] = title or lesson["title"]
    if scope is not None or tools is not None:
        if lesson["status"] == "applied":
            raise ValueError("Remove the lesson before changing where it applies.")
        if tools is not None:
            if tools not in ("claude", "codex", "both"):
                raise ValueError("Tools must be claude, codex or both.")
            lesson["tools"] = tools
        if scope is not None:
            scope = scope.strip() or "global"
            known = {r[0] for r in conn.execute("SELECT DISTINCT project FROM prompts")}
            if scope != "global" and scope not in known:
                raise ValueError("Unknown project.")
            lesson["scope"] = scope
    conn.execute("UPDATE lessons SET title = ?, rule = ?, scope = ?, tools = ?, edited = 1, updated = ? "
                 "WHERE id = ?", (lesson["title"], lesson["rule"], lesson["scope"], lesson["tools"],
                                  time.time(), lesson_id))
    if lesson["status"] == "applied":
        for path in json.loads(lesson["applied_files"] or "[]"):
            write_block(path, _rules_for_file(conn, path))
    conn.commit()
    return {"title": lesson["title"], "rule": lesson["rule"]}


def dismiss_lesson(conn, lesson_id: str) -> None:
    conn.execute("UPDATE lessons SET status = 'dismissed' WHERE id = ? AND status = 'open'", (lesson_id,))
    conn.commit()


def apply_ready(conn) -> list[str]:
    """Apply every open lesson at or above READY. Returns the files written."""
    written = []
    for r in conn.execute("SELECT * FROM lessons WHERE status = 'open' AND confidence >= ?", (READY,)).fetchall():
        try:
            written += apply_lesson(conn, r["id"])
        except ValueError:
            log.debug("lesson %s not applicable", r["id"])
    return sorted(set(written))


# ── before / after ─────────────────────────────────────────────────────────

MIN_AFTER_PROMPTS = 5


def _window_stats(conn, lo: float, hi: float, project: str | None, sources: tuple[str, ...]) -> dict:
    marks = ",".join("?" * len(sources))
    params = [lo, hi, *sources]
    proj = ""
    if project:
        proj = " AND c.project = ?"
        params.append(project)
    per_prompt = conn.execute(
        f"""SELECT c.prompt_id, COUNT(*) calls, SUM(c.cost_usd) cost, SUM(c.quota_5h_pct) q
            FROM calls c WHERE c.ts >= ? AND c.ts < ? AND c.source IN ({marks}) AND c.estimated = 0
            AND c.prompt_id IS NOT NULL{proj} GROUP BY c.prompt_id""", params).fetchall()
    sessions = conn.execute(
        f"""SELECT c.session_id, MAX(c.input_tokens + c.cache_write_tokens + c.cache_read_tokens) ctx,
                   COUNT(*) calls
            FROM calls c WHERE c.ts >= ? AND c.ts < ? AND c.source IN ({marks}) AND c.estimated = 0
            {proj} GROUP BY c.session_id""", params).fetchall()
    n = len(per_prompt)
    priced = [r["cost"] for r in per_prompt if r["cost"] is not None]
    return {
        "prompts": n,
        "cost_per_prompt": sum(priced) / len(priced) if priced else None,
        "responses_per_prompt": sum(r["calls"] for r in per_prompt) / n if n else None,
        "quota_per_prompt": sum(r["q"] or 0 for r in per_prompt) / n if n else None,
        "peak_context": sum(s["ctx"] for s in sessions) / len(sessions) if sessions else None,
        "session_length": sum(s["calls"] for s in sessions) / len(sessions) if sessions else None,
    }


def impact(conn, lesson: dict, before_days: int = 28) -> dict:
    """Compare the lesson's scope before and after it was applied."""
    t = lesson["applied_ts"]
    project = None if lesson["scope"] == "global" else lesson["scope"]
    sources = {"claude": ("claude_code", "cowork"), "codex": ("codex",),
               "both": ("claude_code", "cowork", "codex")}[lesson["tools"]]
    before = _window_stats(conn, t - before_days * 86400, t, project, sources)
    after = _window_stats(conn, t, time.time() + 1, project, sources)
    out = {"before": before, "after": after, "ready": after["prompts"] >= MIN_AFTER_PROMPTS
           and before["prompts"] >= MIN_AFTER_PROMPTS, "needed": MIN_AFTER_PROMPTS}
    changes = {}
    for k in ("cost_per_prompt", "responses_per_prompt", "peak_context", "session_length", "quota_per_prompt"):
        b, a = before.get(k), after.get(k)
        if b and a is not None:
            changes[k] = (a - b) / b
    out["changes"] = changes
    return out


def nudge_summary(conn, days: int = 30) -> dict:
    """How often each nudge fired, and how often the context nudge was followed
    (the session ended within one more prompt)."""
    since = time.time() - days * 86400
    kinds = {r["kind"]: r["n"] for r in conn.execute(
        "SELECT kind, COUNT(*) n FROM nudges WHERE ts >= ? GROUP BY kind", (since,))}
    ctx = conn.execute("SELECT session_id, ts FROM nudges WHERE kind = 'context' AND ts >= ?",
                       (since,)).fetchall()
    followed = 0
    for r in ctx:
        later = conn.execute("SELECT COUNT(*) FROM prompts WHERE session_id = ? AND ts > ?",
                             (r["session_id"], r["ts"] + 1)).fetchone()[0]
        followed += later <= 1
    return {"by_kind": kinds, "context_total": len(ctx), "context_followed": followed}


# ── improve one prompt ─────────────────────────────────────────────────────

IMPROVE_INSTRUCTIONS = """Rewrite one prompt a person sent to an AI coding agent so the same \
result costs fewer tokens and fewer agent steps. Measured cost of the original: {stats}.

Common causes of waste to fix: vague or open-ended scope, several tasks in one ask, missing \
file paths or names (so the agent searches), missing done-criteria, asking to "review/implement \
everything", re-explaining context the agent already has.

Keep the person's intent and voice; do not invent facts, file names or requirements that are \
not implied by the original — use <placeholders> where they must fill something in. If the \
original is already efficient, say so and return it nearly unchanged.

Reply with only a JSON object: {{"rewrite": "...", "why": ["short reason", "..."], \
"split": ["optional: separate follow-up prompts if the original bundled several tasks"]}}

<original_prompt project="{project}">
{text}
</original_prompt>"""


def improve_prompt(conn, prompt_id: str, force: bool = False) -> dict:
    if not force:
        row = conn.execute("SELECT * FROM improvements WHERE prompt_id = ?", (prompt_id,)).fetchone()
        if row:
            return {"rewrite": row["rewrite"], "why": json.loads(row["why"]), "cached": True}
    p = conn.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,)).fetchone()
    if not p:
        raise ValueError("Unknown prompt.")
    s = conn.execute(
        "SELECT COUNT(*) n, SUM(cost_usd) cost, MAX(input_tokens + cache_write_tokens + cache_read_tokens) ctx, "
        "GROUP_CONCAT(DISTINCT model) models FROM calls WHERE prompt_id = ?", (prompt_id,)).fetchone()
    stats = (f"{s['n']} agent responses, peak context {ledger.fmt_tokens(s['ctx'])} tokens, "
             f"{ledger.fmt_usd(s['cost']) if s['cost'] else 'unpriced'} API-equivalent, model {s['models']}")
    from tokencoach.optimizer import run_claude
    out = run_claude(IMPROVE_INSTRUCTIONS.format(stats=stats, project=p["project"], text=p["text"][:12000]),
                     timeout=240)
    m = re.search(r"\{.*\}", out, re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except ValueError:
        data = {}
    rewrite = (data.get("rewrite") or "").strip()
    if not rewrite:
        raise RuntimeError("Could not parse a rewrite from Claude's reply.")
    why = [w for w in (data.get("why") or []) if isinstance(w, str)]
    split = [x for x in (data.get("split") or []) if isinstance(x, str) and x.strip()]
    if split:
        why.append("Split into: " + " | ".join(split))
    conn.execute("INSERT OR REPLACE INTO improvements (prompt_id, ts, rewrite, why) VALUES (?, ?, ?, ?)",
                 (prompt_id, time.time(), rewrite, json.dumps(why)))
    conn.commit()
    return {"rewrite": rewrite, "why": why, "cached": False}


def save_template(conn, title: str, text: str, source_prompt_id: str | None = None) -> int:
    cur = conn.execute("INSERT INTO templates (ts, title, text, source_prompt_id) VALUES (?, ?, ?, ?)",
                       (time.time(), title.strip()[:80] or "Untitled", text, source_prompt_id))
    conn.commit()
    return cur.lastrowid


def delete_template(conn, template_id: int) -> None:
    conn.execute("DELETE FROM templates WHERE id = ?", (template_id,))
    conn.commit()


# ── snapshot for the dashboard ─────────────────────────────────────────────

def coach_snapshot(conn) -> dict:
    lessons = []
    for r in conn.execute("SELECT * FROM lessons WHERE status != 'dismissed' ORDER BY confidence DESC").fetchall():
        l = dict(r)
        st = status_of(l)
        item = {k: l[k] for k in ("id", "title", "rule", "scope", "tools", "evidence", "evidence_n",
                                  "confidence", "saving", "origin", "edited")}
        item["status"] = st
        item["needed"] = 8 if st == "collecting" else None
        if st == "applied":
            item["files"] = json.loads(l["applied_files"] or "[]")
            item["applied_ts"] = l["applied_ts"]
            item["impact"] = impact(conn, l)
        else:
            item["files"] = target_files(conn, l)
        lessons.append(item)
    improvements = {r["prompt_id"]: {"rewrite": r["rewrite"], "why": json.loads(r["why"])}
                    for r in conn.execute("SELECT * FROM improvements")}
    templates = [dict(r) for r in conn.execute("SELECT id, ts, title, text FROM templates ORDER BY ts DESC")]
    projects = sorted({r[0] for r in conn.execute(
        "SELECT DISTINCT project FROM prompts WHERE estimated = 0")} - UNAPPLIABLE_PROJECTS)
    return {"lessons": lessons, "improvements": improvements, "templates": templates, "projects": projects,
            "nudges": nudge_summary(conn), "ready_threshold": READY, "review_threshold": REVIEW}
