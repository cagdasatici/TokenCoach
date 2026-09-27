"""Static HTML usage report built from the ledger. No server: one self-contained
file written next to the ledger and opened in the default browser."""

import html
import os
import subprocess
from datetime import datetime

from aiquotabar import ledger
from aiquotabar.ledger import fmt_usd, fmt_tokens

REPORT_DIR = os.path.join(os.path.dirname(ledger.LEDGER_DB), "reports")
REPORT_FILE = os.path.join(REPORT_DIR, "usage-report.html")

SOURCE_LABELS = {
    "claude_code": "Claude Code", "cowork": "Cowork", "codex": "Codex",
    "claude_chat": "Claude chat (est.)", "chatgpt_chat": "ChatGPT chat (est.)",
}

CSS = """
:root { color-scheme: light;
  --surface-0:#f5f5f3; --surface-1:#fcfcfb; --border:#e4e3df;
  --text-primary:#0b0b0b; --text-secondary:#52514e; --text-muted:#7a7974;
  --series-1:#2a78d6; --grid:#e9e8e4; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { color-scheme: dark;
  --surface-0:#111110; --surface-1:#1a1a19; --border:#2e2e2c;
  --text-primary:#ffffff; --text-secondary:#c3c2b7; --text-muted:#8f8e86;
  --series-1:#3987e5; --grid:#2a2a28; } }
:root[data-theme="dark"] { color-scheme: dark;
  --surface-0:#111110; --surface-1:#1a1a19; --border:#2e2e2c;
  --text-primary:#ffffff; --text-secondary:#c3c2b7; --text-muted:#8f8e86;
  --series-1:#3987e5; --grid:#2a2a28; }
* { box-sizing: border-box; }
body { margin:0; background:var(--surface-0); color:var(--text-primary);
  font:14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
main { max-width:1120px; margin:0 auto; padding:24px 16px 48px; }
h1 { font-size:22px; margin:0 0 4px; } h2 { font-size:16px; margin:0 0 12px; }
.sub { color:var(--text-secondary); margin:0 0 20px; }
.note { color:var(--text-muted); font-size:12px; margin-top:8px; }
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; margin-bottom:16px; }
.tile, .card { background:var(--surface-1); border:1px solid var(--border); border-radius:10px; padding:14px 16px; }
.tile .k { color:var(--text-secondary); font-size:12px; }
.tile .v { font-size:24px; font-weight:600; margin-top:2px; font-variant-numeric:tabular-nums; }
.tile .d { color:var(--text-muted); font-size:12px; }
.grid2 { display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:16px; margin-bottom:16px; }
.card { margin-bottom:16px; overflow-x:auto; }
svg text { fill:var(--text-muted); font-size:10px; }
.col { fill:var(--series-1); } .col:hover { opacity:.75; }
.gridline { stroke:var(--grid); stroke-width:1; }
table { width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; }
th { text-align:left; color:var(--text-secondary); font-weight:500; font-size:12px;
  border-bottom:1px solid var(--border); padding:6px 8px; white-space:nowrap; }
td { border-bottom:1px solid var(--grid); padding:6px 8px; vertical-align:top; }
td.n, th.n { text-align:right; white-space:nowrap; }
.bar { height:8px; border-radius:0 4px 4px 0; background:var(--series-1); min-width:2px; }
.barcell { width:28%; min-width:90px; }
details summary { cursor:pointer; color:var(--text-primary); }
details pre { white-space:pre-wrap; word-break:break-word; font:12px/1.4 ui-monospace, Menlo, monospace;
  color:var(--text-secondary); max-height:320px; overflow:auto; margin:6px 0 0; }
.tag { display:inline-block; font-size:11px; color:var(--text-secondary);
  border:1px solid var(--border); border-radius:4px; padding:0 5px; margin-right:4px; }
"""


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _pct(v) -> str:
    return "—" if v is None else f"{v:.1f}%"


def _columns_svg(points: list[tuple[str, float]], fmt, title: str) -> str:
    """Single-series column chart, one column per day, native tooltips."""
    if not points or max(v for _, v in points) <= 0:
        return '<p class="note">No data in this period.</p>'
    w, h, pad_l, pad_b, pad_t = 640, 180, 44, 22, 8
    top = max(v for _, v in points)
    n = len(points)
    step = (w - pad_l) / n
    bw = max(step - 2, 1)           # 2px surface gap between columns
    ph = h - pad_b - pad_t
    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{_e(title)}">']
    for frac in (0.5, 1.0):
        y = pad_t + ph * (1 - frac)
        parts.append(f'<line class="gridline" x1="{pad_l}" x2="{w}" y1="{y:.1f}" y2="{y:.1f}"/>')
        parts.append(f'<text x="{pad_l - 6}" y="{y + 3:.1f}" text-anchor="end">{_e(fmt(top * frac))}</text>')
    parts.append(f'<line class="gridline" x1="{pad_l}" x2="{w}" y1="{pad_t + ph}" y2="{pad_t + ph}"/>')
    for i, (label, v) in enumerate(points):
        bh = ph * v / top if top else 0
        x = pad_l + i * step + 1
        y = pad_t + ph - bh
        r = min(4, bw / 2, bh)
        # rounded top, square baseline
        d = (f"M{x:.1f},{pad_t + ph:.1f} L{x:.1f},{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} "
             f"L{x + bw - r:.1f},{y:.1f} Q{x + bw:.1f},{y:.1f} {x + bw:.1f},{y + r:.1f} "
             f"L{x + bw:.1f},{pad_t + ph:.1f} Z")
        parts.append(f'<path class="col" d="{d}"><title>{_e(label)}: {_e(fmt(v))}</title></path>')
        if i % max(n // 6, 1) == 0 or i == n - 1:
            parts.append(f'<text x="{x + bw / 2:.1f}" y="{h - 6}" text-anchor="middle">{_e(label[5:])}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _breakdown_table(rows: list[dict], label: str, key_fmt=lambda k: k, limit: int = 15) -> str:
    rows = rows[:limit]
    top = max([r["cost"] or 0 for r in rows] + [0])
    top_tok = max([(r["input_tokens"] or 0) + (r["output_tokens"] or 0)
                   + (r["cache_read_tokens"] or 0) + (r["cache_write_tokens"] or 0) for r in rows] + [0])
    out = [f'<table><tr><th>{_e(label)}</th><th class="barcell">API-equivalent $</th>'
           '<th class="n">$</th><th class="n">Prompts</th><th class="n">Responses</th>'
           '<th class="n">Tokens</th><th class="n">5h quota</th></tr>']
    for r in rows:
        tokens = ((r["input_tokens"] or 0) + (r["output_tokens"] or 0)
                  + (r["cache_read_tokens"] or 0) + (r["cache_write_tokens"] or 0))
        if top > 0 and r["cost"]:
            width = 100 * r["cost"] / top
        elif top == 0 and top_tok:
            width = 100 * tokens / top_tok
        else:
            width = 0
        cost = fmt_usd(r["cost"]) if not r["unpriced"] or r["cost"] else "unpriced"
        est = ' <span class="tag">est.</span>' if r.get("estimated") else ""
        out.append(
            f'<tr><td>{_e(key_fmt(r["k"]))}{est}</td>'
            f'<td class="barcell"><div class="bar" style="width:{width:.1f}%" '
            f'title="{_e(key_fmt(r["k"]))}: {_e(cost)}"></div></td>'
            f'<td class="n">{_e(cost)}</td><td class="n">{r["prompts"]}</td>'
            f'<td class="n">{r["calls"]}</td><td class="n">{fmt_tokens(tokens)}</td>'
            f'<td class="n">{_pct(r["quota_5h"])}</td></tr>')
    out.append("</table>")
    return "".join(out)


def _prompts_table(prompts: list[dict]) -> str:
    out = ['<table><tr><th>When</th><th>Prompt</th><th class="n">Responses</th>'
           '<th class="n">Tokens</th><th class="n">Peak context</th>'
           '<th class="n">$</th><th class="n">5h quota</th></tr>']
    for p in prompts:
        tokens = ((p["input_tokens"] or 0) + (p["output_tokens"] or 0)
                  + (p["cache_read_tokens"] or 0) + (p["cache_write_tokens"] or 0))
        text = p["text"].strip()
        first = " ".join(text.split())[:140]
        when = datetime.fromtimestamp(p["ts"]).strftime("%b %d %H:%M")
        est = '<span class="tag">est.</span>' if p["estimated"] else ""
        out.append(
            f'<tr><td class="n">{_e(when)}</td><td>'
            f'<span class="tag">{_e(SOURCE_LABELS.get(p["source"], p["source"]))}</span>'
            f'<span class="tag">{_e(p["project"])}</span>'
            f'<span class="tag">{_e(p["models"] or "")}</span>{est}'
            f'<details><summary>{_e(first)}{"…" if len(text) > 140 else ""}</summary>'
            f'<pre>{_e(text)}</pre></details></td>'
            f'<td class="n">{p["calls"]}</td><td class="n">{fmt_tokens(tokens)}</td>'
            f'<td class="n">{fmt_tokens(p["peak_context"])}</td>'
            f'<td class="n">{fmt_usd(p["cost"]) if p["cost"] else "—"}</td>'
            f'<td class="n">{_pct(p["quota_5h"])}</td></tr>')
    out.append("</table>")
    return "".join(out)


def build_report(conn, config: dict | None = None, days: int = 30) -> str:
    config = config or {}
    since = ledger._day_start(days - 1)
    week = ledger._day_start(6)
    by_day = ledger.breakdown(conn, since, "day")
    by_source = ledger.breakdown(conn, since, "source")
    by_project = ledger.breakdown(conn, since, "project")
    by_model = ledger.breakdown(conn, since, "model")
    today = ledger.today_summary(conn)
    week_cost = sum(r["cost"] for r in ledger.breakdown(conn, week, "source"))
    month_cost = sum(r["cost"] for r in by_source)
    prompts = ledger.top_prompts(conn, since, limit=50)

    # daily series: API-equivalent $ (priced models) and Codex 5h quota used
    days_all = [(datetime.fromtimestamp(ledger._day_start(i))).strftime("%Y-%m-%d")
                for i in range(days - 1, -1, -1)]
    cost_by_day = {r["k"]: r["cost"] for r in by_day}
    codex_q = {r["k"]: r["q"] or 0 for r in conn.execute(
        "SELECT date(ts,'unixepoch','localtime') k, SUM(quota_5h_pct) q FROM calls "
        "WHERE source='codex' AND ts >= ? GROUP BY k", (since,)).fetchall()}

    plans = config.get("ledger_plans") or {}
    plan_rows = []
    claude_cost = sum(r["cost"] for r in by_source if ledger.SOURCE_PROVIDER.get(r["k"]) == "claude")
    if plans.get("claude"):
        ratio = claude_cost / plans["claude"] if plans["claude"] else 0
        plan_rows.append(f'<div class="tile"><div class="k">Claude plan value, {days}d</div>'
                         f'<div class="v">{ratio:.1f}×</div><div class="d">{fmt_usd(claude_cost)} API-equivalent '
                         f'vs ${plans["claude"]:,.0f}/mo plan</div></div>')
    unpriced = sum(r["unpriced"] for r in by_source)

    tiles = [
        ("Today", fmt_usd(today["cost"]), f'{today["prompts"]} prompts · {fmt_tokens(today["tokens"])} tokens'),
        ("Last 7 days", fmt_usd(week_cost), "API-equivalent"),
        (f"Last {days} days", fmt_usd(month_cost), "API-equivalent"),
        ("Top project today", _e(today["top_project"]["project"]) if today["top_project"] else "—",
         fmt_usd(today["top_project"]["cost"]) if today["top_project"] else ""),
    ]
    tiles_html = "".join(
        f'<div class="tile"><div class="k">{k}</div><div class="v">{v}</div><div class="d">{d}</div></div>'
        for k, v, d in tiles) + "".join(plan_rows)

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    notes = [
        "“API-equivalent $” is what the same tokens would cost on the provider API at list price. "
        "On a subscription you pay a flat fee; use it to compare prompts, projects and models.",
        "Claude 5-hour quota per prompt is estimated from AIQuotaLeft’s periodic quota readings. "
        "Codex quota comes from Codex’s own reading after every response.",
    ]
    if unpriced:
        notes.append(f"{unpriced} responses use models without a bundled price (Codex/OpenAI). "
                     "Add prices under \"ledger_prices\" in ~/.claude_bar_config.json to include them.")
    if not plans:
        notes.append("Add \"ledger_plans\": {\"claude\": 200, \"chatgpt\": 20} (your monthly plan price) "
                     "to ~/.claude_bar_config.json to see plan value.")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Usage Report</title><style>{CSS}</style></head>
<body><main>
<h1>AI usage report</h1>
<p class="sub">Claude Code, Cowork and Codex · last {days} days · generated {generated}</p>
<div class="tiles">{tiles_html}</div>
<div class="grid2">
  <div class="card"><h2>API-equivalent $ per day</h2>
    {_columns_svg([(d, cost_by_day.get(d, 0)) for d in days_all], fmt_usd, "API-equivalent dollars per day")}</div>
  <div class="card"><h2>Codex 5-hour quota used per day</h2>
    {_columns_svg([(d, codex_q.get(d, 0)) for d in days_all], lambda v: f"{v:.0f}%", "Codex quota percent per day")}
    <p class="note">Sum of 5-hour window % consumed that day; above 100% means more than one full window.</p></div>
</div>
<div class="card"><h2>By tool</h2>{_breakdown_table(by_source, "Tool", lambda k: SOURCE_LABELS.get(k, k))}</div>
<div class="card"><h2>By project</h2>{_breakdown_table(by_project, "Project")}</div>
<div class="card"><h2>By model</h2>{_breakdown_table(by_model, "Model")}</div>
<div class="card"><h2>Most expensive prompts</h2>
  <p class="note">Each prompt includes every response and tool step it triggered. Click a prompt to read it in full.</p>
  {_prompts_table(prompts)}</div>
{"".join(f'<p class="note">{_e(n)}</p>' for n in notes)}
</main></body></html>"""


def write_report(conn, config: dict | None = None, days: int = 30) -> str:
    os.makedirs(REPORT_DIR, exist_ok=True)
    tmp = REPORT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(build_report(conn, config, days))
    os.replace(tmp, REPORT_FILE)
    return REPORT_FILE


def open_file(path: str):
    subprocess.Popen(["open", path])
