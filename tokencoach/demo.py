"""Sample data for `tokencoach --demo` and the README screenshots.

Builds a believable six-week history for a fictional developer in a separate
data folder (TOKENCOACH_DATA_DIR), so nothing of the person's own is read or
written. Deterministic: the same seed gives the same story.

The story: long, sprawling sessions and broad asks dominate the bill until a
"keep sessions to one task" lesson is applied twelve days ago; after that,
sessions are shorter and cheaper, which the before/after panel shows.
"""

import json
import os
import random
import time

from tokencoach import ledger

PROJECTS = {
    "storefront":    ("claude_code", "~/code/storefront"),
    "payments-api":  ("claude_code", "~/code/payments-api"),
    "data-pipeline": ("codex",       "~/code/data-pipeline"),
    "mobile-app":    ("claude_code", "~/code/mobile-app"),
    "docs-site":     ("codex",       "~/code/docs-site"),
    "infra":         ("cowork",      None),
}
MODELS = {
    "claude_code": [("claude-sonnet-5", 0.62), ("claude-opus-5", 0.30), ("claude-haiku-4-5", 0.08)],
    "cowork":      [("claude-sonnet-5", 1.0)],
    "codex":       [("gpt-5.6-sol", 0.55), ("gpt-5.6-terra", 0.3), ("gpt-6-astra", 0.15)],
}
FOCUSED = [
    "Add pagination to the orders endpoint in src/api/orders.ts (cursor based, 50 per page)",
    "Fix the flaky test in tests/checkout.spec.ts; it times out waiting for the payment iframe",
    "Rename getUserCart to loadCart across src/store and update the imports",
    "Write a migration that adds an index on payments(created_at)",
    "Why does `npm run build` fail with 'Cannot find module @app/ui'?",
    "Add retry with exponential backoff to the webhook sender in lib/webhooks.py",
    "Convert the settings screen in app/screens/Settings.tsx to the new form components",
    "Explain what the reconcile job in jobs/reconcile.py does, in five bullets",
    "Add a dark mode toggle to the docs header (docs/components/Header.vue)",
    "Bump the Terraform AWS provider to 6.x in infra/main.tf and fix the plan errors",
    "Write unit tests for the currency formatter in src/lib/money.ts",
    "What's the quickest way to profile the slow /search query?",
]
BROAD = [
    "Implement all the remaining items from the roadmap and commit",
    "Review the whole codebase and fix everything you find",
    "ok continue, do everything that's left",
    "Clean up the entire project: types, tests, lint, docs",
]


def _pick(rng, weighted):
    r, acc = rng.random(), 0.0
    for item, w in weighted:
        acc += w
        if r <= acc:
            return item
    return weighted[-1][0]


def build(conn, now: float | None = None, days: int = 70, seed: int = 5) -> dict:
    """Fill an empty ledger with sample history. Returns a few facts about it."""
    rng = random.Random(seed)
    now = now or time.time()
    lesson_day = now - 12 * 86400
    prompts, calls, samples = [], [], []
    n_session = 0
    for d in range(days, -1, -1):
        day0 = time.mktime(time.localtime(now - d * 86400)[:3] + (0, 0, 0, 0, 0, -1))
        weekday = time.localtime(day0).tm_wday
        after = day0 >= lesson_day
        n_sessions = rng.randint(1, 3) if weekday >= 5 else rng.randint(4, 8)
        for _ in range(n_sessions):
            n_session += 1
            project = rng.choice(list(PROJECTS))
            source, cwd = PROJECTS[project]
            model = _pick(rng, MODELS[source])
            t = day0 + rng.uniform(9, 19) * 3600
            if t > now - 600:
                continue
            session = f"demo-s{n_session}"
            # before the lesson: some runaway sessions; after: mostly focused
            runaway = rng.random() < (0.07 if after else 0.22)
            n_prompts = rng.randint(3, 6) if runaway else rng.randint(1, 3)
            ctx = rng.randint(15_000, 25_000)
            for k in range(n_prompts):
                broad = runaway and k == 0 and rng.random() < 0.7
                text = rng.choice(BROAD if broad else FOCUSED)
                if k > 0 and runaway and rng.random() < 0.5:
                    text = rng.choice(["keep going", "continue", "now also fix the related tests",
                                       "that didn't work, try again"])
                pid = f"demo-p{n_session}-{k}"
                prompts.append({"id": pid, "source": source, "session_id": session, "project": project,
                                "ts": t, "text": text,
                                "cwd": os.path.expanduser(cwd) if cwd else None})
                n_resp = rng.randint(50, 110) if broad else rng.randint(6, 18) if runaway else rng.randint(2, 12)
                for r in range(n_resp):
                    ctx = min(ctx + rng.randint(600, 2_200), 240_000)
                    out = rng.randint(150, 1_800)
                    write = rng.randint(1_000, 4_000)
                    read = ctx - write
                    ts = t + r * rng.uniform(4, 20)
                    if source == "codex":
                        cost = ledger.call_cost(model, 800, out, write, 0, read)
                    else:
                        cost = ledger.call_cost(model, 3, out, 0, write, read)
                    calls.append({"id": f"demo-c{n_session}-{k}-{r}", "source": source,
                                  "session_id": session, "project": project, "model": model,
                                  "ts": ts, "input_tokens": 800 if source == "codex" else 3,
                                  "output_tokens": out, "cache_write_tokens": write,
                                  "cache_read_tokens": read, "reasoning_tokens": out // 3,
                                  "cost_usd": cost})
                t += n_resp * 12 + rng.uniform(60, 900)
    ledger._insert(conn, prompts, calls, [])
    ledger.link_prompts(conn)

    # quota readings: each provider's 5-hour window fills with its spend
    for provider, sources, per_window in (("claude", ("claude_code", "cowork"), 45.0), ("codex", ("codex",), 40.0)):
        rows = conn.execute(
            f"SELECT ts, cost_usd FROM calls WHERE source IN ({','.join('?' * len(sources))}) ORDER BY ts",
            sources).fetchall()
        window_start, used = None, 0.0
        for r in rows:
            if window_start is None or r["ts"] - window_start > 5 * 3600:
                window_start, used = r["ts"], 0.0
            used = min(100.0, used + 100 * (r["cost_usd"] or 0) / per_window)
            samples.append({"provider": provider, "window": "5h", "ts": r["ts"], "pct": round(used, 1)})
    conn.executemany("INSERT OR IGNORE INTO quota_samples (provider, window, ts, pct) "
                     "VALUES (:provider, :window, :ts, :pct)", samples)
    ledger.attribute_quota(conn)
    conn.commit()
    return {"prompts": len(prompts), "calls": len(calls), "lesson_day": lesson_day}


def seed_coach(conn, demo_home: str, lesson_day: float) -> None:
    """Lessons (one applied twelve days ago), nudges, a rewrite and templates."""
    from tokencoach import coach
    coach.detect_lessons(conn, days=30)
    coach.record_analysis_lessons(conn, [{
        "title": "Ask for file paths before searching",
        "rule": ("Before exploring the repository to orient yourself, ask which 3-5 files matter "
                 "for the task; only search the tree if the user can't say."),
        "scope": "global", "tools": "both", "evidence_prompts": [1, 2, 3, 4, 5, 6],
        "confidence": 0.9, "saving": "~15% fewer responses on exploratory tasks"}],
        {i: {"session_id": f"demo-x{i}", "project": "storefront", "source": "claude_code"} for i in range(1, 7)})
    long = conn.execute("SELECT id FROM lessons WHERE title = 'Keep sessions to one task'").fetchone()
    if long:
        coach.apply_lesson(conn, long["id"])
        conn.execute("UPDATE lessons SET applied_ts = ? WHERE id = ?", (lesson_day, long["id"]))
    rng = random.Random(3)
    kinds = [("context", "💡 180k tokens of context: every reply re-reads all of it. /clear and start with a 2-line brief."),
             ("broad", "🎯 Broad asks like this averaged 87 responses in your history, vs 9 overall."),
             ("model", "💡 Quick question on claude-opus-5? /model sonnet is ~2× cheaper and fine for this."),
             ("similar", "🔁 Similar to a prompt last week that took 112 responses ($9.40).")]
    sess = [r[0] for r in conn.execute("SELECT DISTINCT session_id FROM prompts WHERE source='claude_code' "
                                       "AND ts > ? LIMIT 40", (time.time() - 30 * 86400,))]
    for s in sess[:28]:
        kind, msg = rng.choice(kinds[:2] if rng.random() < 0.7 else kinds)
        conn.execute("INSERT INTO nudges (ts, session_id, kind, message, project) VALUES (?, ?, ?, ?, ?)",
                     (time.time() - rng.uniform(1, 29) * 86400, s, kind, msg, "storefront"))
    broad = conn.execute("SELECT p.id FROM prompts p JOIN calls c ON c.prompt_id = p.id "
                         "WHERE p.text LIKE 'Implement all the remaining%' GROUP BY p.id "
                         "ORDER BY SUM(c.cost_usd) DESC LIMIT 1").fetchone()
    if broad:
        conn.execute("INSERT OR REPLACE INTO improvements (prompt_id, ts, rewrite, why) VALUES (?, ?, ?, ?)", (
            broad["id"], time.time(),
            "Implement roadmap items <3>, <5> and <7> from docs/ROADMAP.md.\n"
            "Files: src/api/orders.ts, src/store/cart.ts.\n"
            "Done when: `npm test` passes and each item has its own commit.\n"
            "List your plan first and wait for my OK before editing.",
            json.dumps(["Names the items and files, so the agent doesn't tour the whole repo first",
                        "Gives a done-criterion, so it stops instead of polishing",
                        "Plan-first keeps a wrong guess from costing 100 responses"])))
    coach.save_template(conn, "Scoped change", "Change <what> in <file>. Done when <test/command> passes. Plan first, then wait for OK.")
    coach.save_template(conn, "Fresh-session brief", "Context: <2 lines on what was decided>. Last commit: <hash>. Next: <one task>.")
    conn.commit()


def prepare(data_dir: str) -> str:
    """Create the demo folder with config, ledger and coach data. Returns it."""
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, "config.json"), "w") as f:
        json.dump({"ledger_plans": {"claude": 100, "chatgpt": 20}, "nudges": {"level": "heavy"}}, f)
    for name in ("ledger.db", "ledger.db-wal", "ledger.db-shm"):
        try:
            os.remove(os.path.join(data_dir, name))
        except FileNotFoundError:
            pass
    conn = ledger.open_ledger(os.path.join(data_dir, "ledger.db"))
    facts = build(conn)
    seed_coach(conn, os.path.join(data_dir, "demo-home"), facts["lesson_day"])
    conn.close()
    return data_dir
