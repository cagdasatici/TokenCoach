"""On-demand usage optimizer.

Builds a compact digest of the most expensive recent prompts and asks Claude
(through the owner's own `claude` CLI, so it uses their subscription) for
concrete habit changes and prompt rewrites. Runs only when the owner asks.
The previous report is included so the new one can say whether its advice
was followed.
"""

import glob
import os
import shutil
import subprocess
from datetime import datetime

from aiquotabar import ledger
from aiquotabar.ledger import fmt_usd, fmt_tokens
from aiquotabar.ledger_report import REPORT_DIR, SOURCE_LABELS, CSS

OPTIMIZER_DIR = os.path.join(os.path.dirname(ledger.LEDGER_DB), ledger.OPTIMIZER_PROJECT)
OPTIMIZER_MODEL = "sonnet"
DIGEST_PROMPTS = 20
PROMPT_CHARS = 1500        # per prompt in the digest; the ledger keeps full text
TIMEOUT_SECS = 600

INSTRUCTIONS = """You are reviewing one person's AI assistant usage to help them spend less \
quota and money for the same results. Below is a digest of their most expensive prompts from \
the last {days} days across Claude Code, Cowork and Codex, with measured token counts.

Token terms: "cache read" is conversation history re-read on every response (cheap per token \
but it grows with session length); "peak context" is the largest single request; "responses" \
counts model calls, including every tool step an agent took for that prompt. Claude \
(Claude Code, Cowork) and Codex draw on separate subscriptions with separate quotas, so never \
compare quota % across them; Claude quota % is a coarse estimate. "Unpriced" means no API \
price is configured, not that it was free.

Write a short report in Markdown with exactly these sections:

## Biggest wins
The 3-5 changes that would save the most, ranked. Each: what you saw (cite the prompt number \
and numbers), what to do differently, and a rough saving estimate. Prefer habits \
(new session sooner, cheaper model for simple work, give file paths instead of letting the \
agent search, batch small asks, stop re-pasting context) over wording tweaks.

## Prompt rewrites
For 2-4 of the listed prompts where wording caused waste (vague scope, missing constraints, \
open-ended exploration), give the original gist and a tighter rewrite.

## Model and tool fit
Where a cheaper model or a different tool would have done the job.

{followup}
Be specific and brief. Do not repeat the digest back. No preamble."""

FOLLOWUP = """## Did last time's advice stick?
Compare against the previous report below and say which recommendations were followed, \
judging only from the numbers in this digest.

<previous_report>
{previous}
</previous_report>
"""


def find_claude_cli() -> str | None:
    """The LaunchAgent PATH is minimal, so also look in the usual install spots."""
    found = shutil.which("claude")
    if found:
        return found
    for p in ("/opt/homebrew/bin/claude", "/usr/local/bin/claude",
              os.path.expanduser("~/.local/bin/claude"),
              os.path.expanduser("~/.claude/local/claude")):
        if os.path.exists(p):
            return p
    return None


def build_digest(conn, days: int = 7, limit: int = DIGEST_PROMPTS) -> str:
    since = ledger._day_start(days - 1)
    prompts = ledger.top_prompts(conn, since, limit=limit,
                                 exclude_project=ledger.OPTIMIZER_PROJECT)
    sessions = ledger.session_stats(conn, list({p["session_id"] for p in prompts}))
    lines = []
    totals = ledger.breakdown(conn, since, "source")
    lines.append("# Totals")
    for r in totals:
        lines.append(f"- {SOURCE_LABELS.get(r['k'], r['k'])}: {r['prompts']} prompts, "
                     f"{r['calls']} responses, {fmt_usd(r['cost']) if r['cost'] else 'unpriced'} "
                     f"API-equivalent, 5h quota used {r['quota_5h'] or 0:.0f}%")
    lines.append("\n# By model")
    for r in ledger.breakdown(conn, since, "model")[:8]:
        lines.append(f"- {r['k']}: {r['calls']} responses, "
                     f"{fmt_usd(r['cost']) if r['cost'] else 'unpriced'}")
    lines.append("\n# Most expensive prompts")
    for i, p in enumerate(prompts, 1):
        s = sessions.get(p["session_id"], {})
        text = p["text"].strip()
        if len(text) > PROMPT_CHARS:
            text = text[:PROMPT_CHARS] + f"\n[... {len(p['text']) - PROMPT_CHARS} more characters]"
        when = datetime.fromtimestamp(p["ts"]).strftime("%a %H:%M")
        lines.append(
            f"\n## Prompt {i} — {SOURCE_LABELS.get(p['source'], p['source'])}, project "
            f"{p['project']}, {when}, model {p['models']}\n"
            f"responses {p['calls']}, output {fmt_tokens(p['output_tokens'])}, "
            f"cache read {fmt_tokens(p['cache_read_tokens'])}, "
            f"fresh input {fmt_tokens((p['input_tokens'] or 0) + (p['cache_write_tokens'] or 0))}, "
            f"peak context {fmt_tokens(p['peak_context'])}, "
            f"cost {fmt_usd(p['cost']) if p['cost'] else 'unpriced'}, "
            f"5h quota {p['quota_5h'] or 0:.1f}%\n"
            f"session: {s.get('prompts', '?')} prompts, {s.get('calls', '?')} responses, "
            f"peak context {fmt_tokens(s.get('peak_context'))}\n"
            f"<prompt>\n{text}\n</prompt>")
    return "\n".join(lines)


def latest_report() -> str | None:
    files = sorted(glob.glob(os.path.join(REPORT_DIR, "optimizer-*.md")))
    return files[-1] if files else None


def run_optimizer(conn, days: int = 7) -> str:
    """Run the analysis and return the path of the rendered HTML report.
    Raises RuntimeError with a readable message on failure."""
    cli = find_claude_cli()
    if not cli:
        raise RuntimeError("Claude Code CLI not found. Install it, then try again.")
    digest = build_digest(conn, days)
    if "## Prompt 1" not in digest:
        raise RuntimeError("No prompts in the ledger yet for this period.")
    prev_path = latest_report()
    followup = ""
    if prev_path:
        with open(prev_path, encoding="utf-8") as f:
            followup = FOLLOWUP.format(previous=f.read()[:8000])
    prompt = INSTRUCTIONS.format(days=days, followup=followup) + "\n\n" + digest

    os.makedirs(OPTIMIZER_DIR, exist_ok=True)
    env = dict(os.environ)
    env["PATH"] = env.get("PATH", "") + ":/opt/homebrew/bin:/usr/local/bin"
    proc = subprocess.run(
        [cli, "-p", "--model", OPTIMIZER_MODEL, "--tools", "", "--strict-mcp-config"],
        input=prompt, capture_output=True, text=True, cwd=OPTIMIZER_DIR,
        timeout=TIMEOUT_SECS, env=env,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError((proc.stderr or proc.stdout or "claude exited with no output").strip()[:400])

    os.makedirs(REPORT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    md_path = os.path.join(REPORT_DIR, f"optimizer-{stamp}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(proc.stdout.strip() + "\n")
    html_path = md_path[:-3] + ".html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_markdown_page(proc.stdout, f"Usage advice · {stamp}"))
    return html_path


# ── tiny Markdown renderer (headings, lists, bold, code, paragraphs) ────────

def _inline(s: str) -> str:
    import html as _h
    import re
    s = _h.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    return s


def markdown_to_html(md: str) -> str:
    out, in_list, in_code, para = [], None, False, []

    def flush_para():
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")
            para.clear()

    def close_list():
        nonlocal in_list
        if in_list:
            out.append(f"</{in_list}>")
            in_list = None

    for raw in md.splitlines():
        line = raw.rstrip()
        if line.startswith("```"):
            flush_para(); close_list()
            out.append("</pre>" if in_code else "<pre>")
            in_code = not in_code
            continue
        if in_code:
            import html as _h
            out.append(_h.escape(raw))
            continue
        stripped = line.lstrip()
        if not stripped:
            flush_para(); close_list()
            continue
        if stripped.startswith("#"):
            flush_para(); close_list()
            level = min(len(stripped) - len(stripped.lstrip("#")), 4)
            out.append(f"<h{level}>{_inline(stripped[level:].strip())}</h{level}>")
            continue
        kind = None
        if stripped[:2] in ("- ", "* "):
            kind, item = "ul", stripped[2:]
        elif stripped.split(" ", 1)[0].rstrip(".").isdigit() and ". " in stripped[:5]:
            kind, item = "ol", stripped.split(". ", 1)[1]
        if kind:
            flush_para()
            if in_list != kind:
                close_list()
                out.append(f"<{kind}>")
                in_list = kind
            out.append(f"<li>{_inline(item)}</li>")
            continue
        if stripped.startswith(">"):
            flush_para(); close_list()
            out.append(f"<blockquote>{_inline(stripped.lstrip('> '))}</blockquote>")
            continue
        close_list()
        para.append(stripped)
    flush_para(); close_list()
    if in_code:
        out.append("</pre>")
    return "\n".join(out)


def render_markdown_page(md: str, title: str) -> str:
    import html as _h
    extra = """
    .card h2 { margin-top:18px; } .card h2:first-child { margin-top:0; }
    .card li { margin:4px 0; } code { font:12px ui-monospace, Menlo, monospace; }
    pre { white-space:pre-wrap; background:var(--surface-0); padding:10px; border-radius:6px; }
    blockquote { margin:6px 0; padding-left:10px; border-left:3px solid var(--border);
      color:var(--text-secondary); }
    """
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Usage Advice</title><style>{CSS}{extra}</style></head>
<body><main><h1>{_h.escape(title)}</h1>
<p class="sub">Generated by Claude from your AIQuotaLeft usage ledger.</p>
<div class="card">{markdown_to_html(md)}</div></main></body></html>"""
