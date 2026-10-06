"""TokenCoach dashboard: one self-contained HTML page built from the ledger.

The page embeds its data as JSON and does all filtering in the browser. The app
serves it from its local-only listener (tokencoach/server.py), which also runs
the page's buttons; the same page written to disk still works read-only.

Simple view by default (totals, coach, timeline, costliest prompts); an
Advanced switch reveals filters, quota, activity, breakdowns, sessions and the
full prompt list.
"""

import glob
import html
import json
import os
import subprocess
from datetime import datetime

from tokencoach import health, ledger
from tokencoach.config import log, DEMO, WIDGET_CACHE_FILE

REPORT_DIR = os.path.join(os.path.dirname(ledger.LEDGER_DB), "reports")
REPORT_FILE = os.path.join(REPORT_DIR, "dashboard.html")
DASHBOARD_DAYS = 180          # history embedded in the page
PROMPT_TEXT_CHARS = 4000      # per prompt in the page; the ledger keeps all of it

SOURCE_LABELS = {
    "claude_code": "Claude Code", "cowork": "Cowork", "codex": "Codex",
    "claude_chat": "Claude chat (est.)", "chatgpt_chat": "ChatGPT chat (est.)",
}
# Fixed order = fixed colour slot; never re-ordered by rank.
SOURCE_ORDER = ["claude_code", "codex", "cowork", "claude_chat", "chatgpt_chat"]

# Shared by the optimizer's advice page.
CSS = """
:root { color-scheme: light;
  --surface-0:#f5f5f7; --surface-1:#ffffff; --border:rgba(0,0,0,.1);
  --text-primary:#1d1d1f; --text-secondary:#6e6e73; --text-muted:#86868b;
  --grid:rgba(0,0,0,.07); --fill:rgba(0,0,0,.045); --fill2:rgba(0,0,0,.08); --accent:#0071e3;
  --good:#34c759; --good-ink:#1f7a35; --warn:#ff9f0a; --warn-ink:#b25000; --bad:#ff3b30; --bad-ink:#c4161c;
  --shadow:0 1px 2px rgba(0,0,0,.04), 0 4px 24px rgba(0,0,0,.04); --seg-on:#ffffff;
  --s1:#0a84ff; --s2:#af52de; --s3:#5ac8fa; --s4:#5e5ce6; --s5:#a2845e; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { color-scheme: dark;
  --surface-0:#000000; --surface-1:#1c1c1e; --border:rgba(255,255,255,.12);
  --text-primary:#f5f5f7; --text-secondary:#a1a1a6; --text-muted:#8e8e93;
  --grid:rgba(255,255,255,.08); --fill:rgba(255,255,255,.06); --fill2:rgba(255,255,255,.12); --accent:#0a84ff;
  --good:#30d158; --good-ink:#30d158; --warn:#ff9f0a; --warn-ink:#ffb340; --bad:#ff453a; --bad-ink:#ff6961;
  --shadow:none; --seg-on:#636366;
  --s1:#0a84ff; --s2:#bf5af2; --s3:#64d2ff; --s4:#7d7aff; --s5:#ac8e68; } }
:root[data-theme="dark"] { color-scheme: dark;
  --surface-0:#000000; --surface-1:#1c1c1e; --border:rgba(255,255,255,.12);
  --text-primary:#f5f5f7; --text-secondary:#a1a1a6; --text-muted:#8e8e93;
  --grid:rgba(255,255,255,.08); --fill:rgba(255,255,255,.06); --fill2:rgba(255,255,255,.12); --accent:#0a84ff;
  --good:#30d158; --good-ink:#30d158; --warn:#ff9f0a; --warn-ink:#ffb340; --bad:#ff453a; --bad-ink:#ff6961;
  --shadow:none; --seg-on:#636366;
  --s1:#0a84ff; --s2:#bf5af2; --s3:#64d2ff; --s4:#7d7aff; --s5:#ac8e68; }
* { box-sizing: border-box; }
body { margin:0; background:var(--surface-0); color:var(--text-primary);
  font:15px/1.45 -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", "Segoe UI", sans-serif;
  -webkit-font-smoothing:antialiased; }
main { max-width:1000px; margin:0 auto; padding:8px 16px 64px; }
h1 { font-size:20px; margin:0; font-weight:700; letter-spacing:-.02em; }
h2 { font-size:17px; margin:0 0 10px; font-weight:600; letter-spacing:-.01em; }
.sub { color:var(--text-secondary); margin:2px 0 16px; font-size:14px; }
.note { color:var(--text-muted); font-size:12px; margin:8px 0 0; }
.card { background:var(--surface-1); border-radius:18px; padding:18px 20px; margin-bottom:16px;
  min-width:0; box-shadow:var(--shadow); }
table { width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; }
th { text-align:left; color:var(--text-secondary); font-weight:500; font-size:12px;
  border-bottom:1px solid var(--grid); padding:6px 8px; white-space:nowrap; }
td { border-bottom:1px solid var(--grid); padding:8px; vertical-align:top; font-size:14px; }
"""

DASHBOARD_CSS = """
.num, .kpi .v, .vital .big, .cost { font-variant-numeric:tabular-nums; }
/* toolbar */
.top { position:sticky; top:0; z-index:10; background:color-mix(in srgb, var(--surface-0) 84%, transparent);
  -webkit-backdrop-filter:saturate(180%) blur(20px); backdrop-filter:saturate(180%) blur(20px); }
.top .in { max-width:1000px; margin:0 auto; padding:12px 16px; display:flex; align-items:center; gap:10px 14px; flex-wrap:wrap; }
.brand { display:flex; align-items:center; gap:9px; }
.mini { width:10px; height:10px; border-radius:50%; background:var(--state, var(--text-muted));
  box-shadow:0 0 0 3px color-mix(in srgb, var(--state, var(--text-muted)) 22%, transparent); }
.pill { font-size:12px; color:var(--text-secondary); background:var(--fill); padding:2px 9px; border-radius:20px; }
.spacer { flex:1; }
.ctl { display:inline-flex; align-items:center; gap:6px; }
.ctl-label { font-size:12px; color:var(--text-secondary); }
.seg { display:inline-flex; background:var(--fill2); border-radius:9px; padding:2px; }
.seg button { font:inherit; font-size:13px; border:0; background:none; color:var(--text-primary);
  padding:4px 11px; border-radius:7px; cursor:pointer; }
.seg button.on { background:var(--seg-on); box-shadow:0 1px 3px rgba(0,0,0,.12); font-weight:500; }
.filters { display:flex; gap:8px; flex-wrap:wrap; align-items:center; max-width:1000px; margin:0 auto; padding:0 16px 10px; }
select, input[type=search] { font:inherit; font-size:13px; padding:5px 8px; border-radius:8px;
  border:1px solid var(--border); background:var(--surface-1); color:var(--text-primary); max-width:220px; }
.switch { display:inline-flex; align-items:center; gap:8px; font-size:13px; color:var(--text-secondary); cursor:pointer; user-select:none; }
.switch i, .toggle { width:38px; height:22px; border-radius:11px; background:var(--fill2); position:relative; flex:none; border:0; padding:0; cursor:pointer; transition:background .15s; }
.switch i::after, .toggle::after { content:""; position:absolute; top:2px; left:2px; width:18px; height:18px; border-radius:50%;
  background:#fff; box-shadow:0 1px 3px rgba(0,0,0,.25); transition:left .15s; }
.switch.on i, .toggle.on { background:var(--good); } .switch.on i::after, .toggle.on::after { left:18px; }
body:not(.advanced) .adv { display:none !important; }
/* buttons */
.btn { font:inherit; font-size:14px; font-weight:500; border:0; border-radius:980px; padding:6px 15px; cursor:pointer;
  background:var(--fill2); color:var(--text-primary); white-space:nowrap; }
.btn:hover { filter:brightness(.96); }
.btn.primary { background:var(--accent); color:#fff; }
.btn.quiet, .btn.link { background:none; color:var(--accent); padding:6px 4px; }
.btn.danger { background:none; color:var(--bad-ink); padding:6px 4px; }
.btn[disabled] { opacity:.55; cursor:default; }
/* health */
.hero { margin-top:6px; border-radius:22px; padding:26px 28px; display:flex; gap:22px; align-items:flex-start;
  background:color-mix(in srgb, var(--state) 11%, var(--surface-1)); box-shadow:var(--shadow); }
.glyph { flex:none; width:60px; height:60px; border-radius:50%; background:var(--state); display:grid; place-items:center;
  box-shadow:0 0 0 8px color-mix(in srgb, var(--state) 18%, transparent); }
.glyph svg { width:30px; height:30px; stroke:#fff; stroke-width:3.2; fill:none; stroke-linecap:round; stroke-linejoin:round; }
.state-word { font-size:13px; font-weight:600; color:var(--state-ink); text-transform:uppercase; letter-spacing:.06em; }
.hero h1 { font-size:28px; line-height:1.15; letter-spacing:-.02em; margin:4px 0 6px; }
.hero p { margin:0; color:var(--text-secondary); font-size:16px; max-width:660px; }
.hero .acts { margin-top:14px; }
details.how { margin-top:12px; font-size:13px; color:var(--text-secondary); }
details.how summary { cursor:pointer; list-style:none; }
details.how summary::-webkit-details-marker { display:none; }
details.how ul { margin:8px 0 0; padding-left:18px; max-width:660px; } details.how li { margin:4px 0; }
.vitals { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:12px; margin-top:12px; }
.vital { margin:0; }
.vital .head { display:flex; align-items:center; gap:8px; font-size:13px; font-weight:600; color:var(--text-secondary); }
.vital .st { margin-left:auto; font-size:12px; display:inline-flex; align-items:center; gap:5px; }
.dot { display:inline-block; width:8px; height:8px; border-radius:50%; flex:none; }
.vital .big { font-size:34px; font-weight:700; letter-spacing:-.02em; margin-top:6px; line-height:1.1; }
.vital .big small { font-size:15px; font-weight:500; color:var(--text-secondary); letter-spacing:0; margin-left:4px; }
.vital .cap { font-size:13px; color:var(--text-secondary); margin-top:3px; }
.wrow { margin-top:12px; }
.wrow .l { display:flex; justify-content:space-between; gap:8px; font-size:13px; margin-bottom:5px; }
.wrow .l span:last-child { color:var(--text-secondary); text-align:right; }
.wrow .l span:first-child { white-space:nowrap; }
.meter { position:relative; height:6px; border-radius:3px; background:var(--fill2); }
.meter > i { position:absolute; left:0; top:0; bottom:0; border-radius:3px; }
.meter .pace { position:absolute; top:-4px; width:2px; height:14px; margin-left:-1px; background:var(--text-primary); opacity:.5; border-radius:1px; }
.spark { display:block; width:100%; height:44px; margin-top:12px; overflow:visible; }
.axis { display:flex; justify-content:space-between; font-size:11px; color:var(--text-muted); margin-top:5px; }
/* sections */
section { margin-top:34px; }
.sh { display:flex; align-items:baseline; gap:6px 10px; margin:0 4px 12px; flex-wrap:wrap; }
.sh h2 { font-size:22px; font-weight:700; letter-spacing:-.015em; margin:0; }
.sh .sub { margin:0; }
.group-label { font-size:13px; font-weight:500; color:var(--text-secondary); margin:18px 4px 8px; }
.list { background:var(--surface-1); border-radius:18px; box-shadow:var(--shadow); overflow:hidden; }
.empty { color:var(--text-muted); padding:22px; text-align:center; font-size:14px; }
/* coach */
.lesson { display:flex; gap:14px; align-items:flex-start; padding:16px 20px; }
.lesson + .lesson, .lesson + .nudge { border-top:1px solid var(--grid); }
.licon { width:32px; height:32px; border-radius:9px; flex:none; display:grid; place-items:center; font-size:15px; font-weight:600; }
.licon.ready { background:color-mix(in srgb, var(--accent) 14%, transparent); color:var(--accent); }
.licon.maybe { background:var(--fill2); color:var(--text-secondary); }
.licon.working { background:color-mix(in srgb, var(--good) 18%, transparent); color:var(--good-ink); }
.lesson .body { flex:1; min-width:0; }
.lesson .t { font-weight:600; }
.lesson .why { color:var(--text-secondary); font-size:14px; margin-top:2px; }
.lesson .acts { display:flex; gap:4px; align-items:center; flex:none; flex-wrap:wrap; }
.lesson details { margin-top:6px; font-size:13px; }
.lesson details > summary { cursor:pointer; color:var(--accent); list-style:none; display:inline-block; }
.lesson details > summary::-webkit-details-marker { display:none; }
.lesson details[open] > summary { margin-bottom:8px; }
.rule { background:var(--fill); border-radius:10px; padding:10px 12px; color:var(--text-primary); font-size:13px; }
.meta { color:var(--text-muted); font-size:12px; margin-top:6px; display:flex; flex-wrap:wrap; gap:4px 10px; align-items:center; }
.meta .btn { font-size:12px; padding:0; }
.gain { display:grid; grid-template-columns:repeat(auto-fit, minmax(120px, 1fr)); gap:8px; margin-top:12px; }
.gain div { background:var(--fill); border-radius:12px; padding:10px 12px; }
.gain b { display:block; font-size:22px; font-weight:700; letter-spacing:-.01em; }
.gain b.better { color:var(--good-ink); } .gain b.worse { color:var(--warn-ink); }
.gain span { font-size:12px; color:var(--text-secondary); }
.lesson.flash { animation:flash 1.6s ease-out; }
@keyframes flash { from { background:color-mix(in srgb, var(--accent) 16%, transparent); } to { background:transparent; } }
.nudge { display:flex; align-items:center; gap:12px; padding:14px 20px; font-size:14px; }
.nudge .txt { flex:1; color:var(--text-secondary); } .nudge .txt b { color:var(--text-primary); font-weight:600; }
.editor input, .editor textarea { border:1px solid var(--border); border-radius:8px; padding:6px 8px;
  background:var(--surface-1); color:var(--text-primary); box-sizing:border-box; }
.editor .acts { display:flex; gap:6px; flex-wrap:wrap; align-items:center; }
.editor label, .editor .e { color:var(--text-muted); font-size:12px; }
/* spending */
.kpis { display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:14px 0; }
.kpi { padding:0 18px; border-left:1px solid var(--grid); }
.kpi:first-child { border-left:0; padding-left:0; }
.kpi .k { font-size:13px; color:var(--text-secondary); }
.kpi .v { font-size:28px; font-weight:700; letter-spacing:-.02em; margin-top:2px; white-space:nowrap; }
.kpi .v .pair { font-size:21px; }   /* two providers in one tile */
.kpi .d { font-size:12px; color:var(--text-muted); }
.chip { display:inline-block; font-size:12px; font-weight:600; padding:1px 7px; border-radius:20px; margin-left:6px;
  vertical-align:5px; letter-spacing:0; }
.chip.good { color:var(--good-ink); background:color-mix(in srgb, var(--good) 15%, transparent); }
.chip.bad { color:var(--bad-ink); background:color-mix(in srgb, var(--bad) 13%, transparent); }
.chip.neutral { color:var(--text-secondary); background:var(--fill2); }
.value-note { font-size:13px; color:var(--text-secondary); margin-top:14px; padding-top:12px; border-top:1px solid var(--grid); }
.value-note:empty { display:none; }
.chart { margin-top:18px; }
.chart svg { display:block; width:100%; height:auto; overflow:visible; }
.chart text { fill:var(--text-muted); font-size:11px; font-family:inherit; }
.chart text.hi { fill:var(--text-primary); font-weight:600; }
.chart text.avg { fill:var(--text-secondary); }
.gridline { stroke:var(--grid); stroke-width:1; }
.avgline { stroke:var(--text-secondary); stroke-dasharray:4 4; stroke-width:1; }
.hit { fill:transparent; }
.chart .dim .bucket { opacity:.45; } .chart .dim .bucket.cur { opacity:1; }
.legend { display:flex; flex-wrap:wrap; gap:6px 16px; font-size:13px; color:var(--text-secondary); margin-top:12px; }
.legend span { display:inline-flex; align-items:center; gap:6px; }
.legend b { color:var(--text-primary); font-weight:600; }
.legend i { display:inline-block; width:9px; height:9px; border-radius:50%; }
/* prompts */
.prompt-row { display:grid; grid-template-columns:minmax(0, 1fr) auto; gap:4px 16px; padding:14px 20px; align-items:start; }
.prompt-row + .prompt-row { border-top:1px solid var(--grid); }
.prompt-row summary { cursor:pointer; list-style:none; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.prompt-row summary::-webkit-details-marker { display:none; }
.prompt-row details[open] summary { white-space:normal; }
.pm { font-size:12px; color:var(--text-secondary); display:flex; gap:4px 10px; align-items:center; flex-wrap:wrap; margin-top:2px; }
.pm .dot { width:7px; height:7px; margin-right:-5px; }
.pact { display:flex; align-items:center; gap:6px; }
.cost { font-size:17px; font-weight:600; text-align:right; }
.cbar { grid-column:1 / -1; height:3px; border-radius:2px; background:var(--fill); overflow:hidden; }
.cbar i { display:block; height:100%; background:var(--text-muted); opacity:.55; border-radius:2px; }
.prompt-row > .imp { grid-column:1 / -1; }
.improve { background:var(--fill); border-radius:12px; padding:12px 14px; margin-top:8px; }
.improve pre { white-space:pre-wrap; word-break:break-word; font:13px/1.5 ui-monospace, "SF Mono", Menlo, monospace;
  margin:6px 0; color:var(--text-primary); }
.improve ul { margin:4px 0 8px 18px; padding:0; font-size:12px; color:var(--text-secondary); }
.improve .acts { display:flex; gap:6px; flex-wrap:wrap; align-items:center; }
pre.prompt { white-space:pre-wrap; word-break:break-word; font:12px/1.45 ui-monospace, "SF Mono", Menlo, monospace;
  color:var(--text-secondary); max-height:320px; overflow:auto; margin:6px 0 0; }
.tag { display:inline-block; font-size:11px; color:var(--text-secondary); background:var(--fill);
  border-radius:5px; padding:1px 6px; margin:0 4px 2px 0; white-space:nowrap; }
/* advanced */
.grid2 { display:grid; grid-template-columns:repeat(auto-fit, minmax(340px, 1fr)); gap:16px; }
.cardhead { display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:10px; }
.cardhead h2 { margin:0; }
td.n, th.n { text-align:right; white-space:nowrap; }
tr.click { cursor:pointer; } tr.click:hover td { background:var(--fill); }
.bar { height:6px; border-radius:3px; background:var(--accent); min-width:2px; }
.barcell { width:26%; min-width:80px; }
.scroll { overflow-x:auto; }
details summary { cursor:pointer; }
.advice h2 { margin-top:14px; } .advice li { margin:3px 0; }
.advice pre { white-space:pre-wrap; background:var(--fill); padding:8px; border-radius:8px; }
.more { margin-top:8px; }
/* feedback */
#tip { position:fixed; pointer-events:none; background:var(--surface-1); border:1px solid var(--grid);
  border-radius:12px; padding:9px 11px; font-size:12px; box-shadow:0 8px 30px rgba(0,0,0,.18);
  display:none; z-index:20; max-width:320px; min-width:160px; }
#tip b { font-weight:600; } #tip .row { display:flex; justify-content:space-between; gap:16px; color:var(--text-secondary); }
#tip .row span { display:inline-flex; align-items:center; gap:6px; }
#tip .row.tot { color:var(--text-primary); font-weight:600; border-top:1px solid var(--grid); margin-top:4px; padding-top:4px; }
#toast { position:fixed; bottom:24px; left:50%; transform:translateX(-50%); background:var(--text-primary);
  color:var(--surface-1); padding:10px 16px; border-radius:12px; font-size:14px; display:none; z-index:30; max-width:90vw; }
@media (max-width:760px) {
  .vitals { grid-template-columns:1fr; }
  .hero { padding:20px; gap:16px; } .hero h1 { font-size:23px; }
  .glyph { width:44px; height:44px; } .glyph svg { width:22px; height:22px; }
  .kpi { border-left:0; padding-left:0; }
  .lesson { flex-wrap:wrap; } .lesson .acts { width:100%; padding-left:46px; }
  .ctl-label, .barcell { display:none; }
  .top { position:static; }
}
@media (prefers-reduced-motion: reduce) { * { transition:none !important; animation:none !important; } }
"""

DASHBOARD_JS = r"""
let D = JSON.parse(document.getElementById('data').textContent);
const QS = new URLSearchParams(location.search);
if (QS.get('theme')) document.documentElement.dataset.theme = QS.get('theme');
let C = D.coach || {lessons: [], improvements: {}, templates: [], nudges: {by_kind: {}}};
const SRC = D.sources, SRC_BY = Object.fromEntries(SRC.map(s => [s.key, s]));
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const usd = v => v == null ? '—' : v >= 100 ? '$' + Math.round(v).toLocaleString() : v >= 1 ? '$' + v.toFixed(2) : '$' + v.toFixed(3);
const tok = n => { n = n || 0; return n >= 1e9 ? (n/1e9).toFixed(1)+'B' : n >= 1e6 ? (n/1e6).toFixed(1)+'M' : n >= 1e3 ? Math.round(n/1e3)+'k' : String(Math.round(n)); };
const pct = v => v == null ? '—' : (v >= 10 ? Math.round(v) : v.toFixed(1)) + '%';
const when = t => new Date(t * 1000).toLocaleString(undefined, {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'});
const METRICS = {
  cost:    {label:'API-equivalent $', fmt: usd, get: f => f.cost || 0},
  tokens:  {label:'Tokens', fmt: tok, get: f => f.tin + f.tout + f.tcw + f.tcr},
  prompts: {label:'Prompts', fmt: v => Math.round(v).toLocaleString(), get: f => f.first ? 1 : 0},
  quota:   {label:'5h quota %', fmt: pct, get: f => f.q5 || 0},
};
const modelLabel = m => D.equivalents && D.equivalents[m] ? `${m} (≈ ${D.equivalents[m]} price)` : m;
const RANGES = {today:'Today', '7d':'7 days', '30d':'30 days', '90d':'90 days', all:'All'};
const DAY = 86400;

// ── state (kept across reloads) and the effective view ──────────────────
const DEFAULT = {range:'30d', group:'all', metric:'cost', source:'', project:'', model:'', q:'', sort:'cost', adv:false};
const GROUPS = {all:'All', claude:'Claude', openai:'OpenAI'};
const grp = src => D.provider[src] === 'claude' ? 'claude' : 'openai';
let S = {...DEFAULT};
try { Object.assign(S, JSON.parse(localStorage.getItem('tokencoach-dash') || '{}')); } catch (e) {}
S.group = DEFAULT.group;   // begin on All; data refresh preserves the current selection
if (QS.get('view')) S.adv = QS.get('view') === 'advanced';     // for links and screenshots
if (QS.get('range')) S.range = QS.get('range');
const save = () => { try { localStorage.setItem('tokencoach-dash', JSON.stringify(S)); } catch (e) {} };
let V = S;   // simple view ignores advanced-only filters and measures
const view = () => S.adv ? S : {...S, metric:'cost', source:'', project:'', model:''};

// ── data: facts = one row per (prompt, model) ─────────────────────────────
let P = D.prompts.map((p, i) => ({i, id: p[0], t: p[1], src: p[2], proj: p[3], sess: p[4], text: p[5], est: p[6], trunc: p[7]}));
let F = D.facts.map(r => ({p: P[r[0]], model: D.models[r[1]], calls: r[2], cost: r[3], tin: r[4], tout: r[5],
  tcw: r[6], tcr: r[7], q5: r[8], qw: r[9], ctx: r[10], t: r[11], first: r[12], qn: r[13] || 0}));
// Quota sums: unmeasured quota is unknown, not 0, so a group with nothing measured stays null ('—').
const addq = (a, v) => v == null ? a : (a || 0) + v;
F.forEach(f => { f.src = f.p.src; f.proj = f.p.proj; });

function startOfDay(ts) { const d = new Date(ts * 1000); d.setHours(0,0,0,0); return d.getTime() / 1000; }
function rangeBounds(r) {
  const now = D.generated, today = startOfDay(now);
  if (r === 'today') return [today, now + 1];
  if (r === 'all') return [Math.min(now, ...F.map(f => f.t)), now + 1];
  return [today - ({'7d':7, '30d':30, '90d':90}[r] - 1) * DAY, now + 1];
}
function filtered(lo, hi) {
  return F.filter(f => f.t >= lo && f.t < hi && (V.group === 'all' || grp(f.src) === V.group) && (!V.source || f.src === V.source)
    && (!V.project || f.proj === V.project) && (!V.model || f.model === V.model));
}
const sum = (rows, get) => { let s = 0; for (const r of rows) s += get(r); return s; };

// ── feedback ──────────────────────────────────────────────────────────────
const tip = $('#tip');
function showTip(e, html) {
  tip.innerHTML = html; tip.style.display = 'block';
  const w = tip.offsetWidth, h = tip.offsetHeight;
  let x = e.clientX + 14, y = e.clientY + 14;
  if (x + w > innerWidth - 8) x = e.clientX - w - 14;
  if (y + h > innerHeight - 8) y = e.clientY - h - 14;
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}
function hideTip() { tip.style.display = 'none'; }
let toastT;
function toast(msg, ms = 4000) { const t = $('#toast'); t.textContent = msg; t.style.display = 'block'; clearTimeout(toastT); toastT = setTimeout(() => t.style.display = 'none', ms); }

let pendingActions = 0;
async function api(path, body) {
  if (!D.live) { toast(D.demo ? 'Buttons work in the live demo: run tokencoach --demo.' : 'Open the dashboard from the TokenCoach menu bar icon to use buttons.'); return null; }
  pendingActions++;
  try {
    const r = await fetch('/api/' + path, {method:'POST', headers:{'Content-Type':'application/json', 'X-TokenCoach': D.live.token}, body: JSON.stringify(body || {})});
    const j = await r.json();
    if (!j.ok) { toast(j.error || 'Something went wrong'); return null; }
    return j;
  } catch (e) { toast('TokenCoach is not running. Start it from the menu bar and reopen the dashboard.'); return null; } finally { pendingActions--; }
}
async function busy(btn, label, fn) {
  const old = btn.textContent; btn.disabled = true; btn.textContent = label;
  try { return await fn(); } finally { btn.disabled = false; btn.textContent = old; }
}

// ── controls ──────────────────────────────────────────────────────────────
function seg(el, opts, key) {
  el.innerHTML = Object.entries(opts).map(([k, v]) => `<button data-k="${k}" class="${S[key] === k ? 'on' : ''}">${v}</button>`).join('');
  el.onclick = e => { const k = e.target.dataset.k; if (!k) return; S[key] = k; save(); render(); };
}
function fillSelect(el, key, values, label, fmt) {
  el.innerHTML = `<option value="">${label}</option>` + values.map(v => `<option value="${esc(v)}" ${v === S[key] ? 'selected' : ''}>${esc(fmt ? fmt(v) : v)}</option>`).join('');
  el.onchange = () => { S[key] = el.value; save(); render(); };
}
function controls(lo, hi) {
  seg($('#range'), RANGES, 'range');
  seg($('#group'), GROUPS, 'group');
  seg($('#metric'), Object.fromEntries(Object.entries(METRICS).map(([k, m]) => [k, m.label])), 'metric');
  const inRange = F.filter(f => f.t >= lo && f.t < hi && (S.group === 'all' || grp(f.src) === S.group));
  if (S.source && S.group !== 'all' && grp(S.source) !== S.group) S.source = '';
  const rank = get => { const m = new Map(); for (const f of inRange) m.set(get(f), (m.get(get(f)) || 0) + (f.cost || 0) + (f.tin + f.tout + f.tcr) / 1e7); return [...m.entries()].sort((a, b) => b[1] - a[1]).map(e => e[0]); };
  fillSelect($('#f-source'), 'source', SRC.map(s => s.key).filter(k => inRange.some(f => f.src === k) || k === S.source), 'All tools', k => SRC_BY[k].label);
  fillSelect($('#f-project'), 'project', rank(f => f.proj), 'All projects');
  fillSelect($('#f-model'), 'model', rank(f => f.model), 'All models', modelLabel);
  $('#clear').style.display = (S.source || S.project || S.model) ? '' : 'none';
  $('#adv').classList.toggle('on', !!S.adv);
  document.body.classList.toggle('advanced', !!S.adv);
}

// ── health: one green / amber / red answer (tokencoach/health.py) ────────
let H = (D.health_samples && D.health_samples[QS.get('health')]) || D.health;
const HV = {good:['--good','--good-ink'], watch:['--warn','--warn-ink'], critical:['--bad','--bad-ink'], unknown:['--text-muted','--text-secondary']};
const HWORD = {good:'Healthy', watch:'Watch', critical:'Action needed', unknown:'No reading'};
const HBADGE = {good:'OK', watch:'Watch', critical:'Out', unknown:'No reading'};
const HICON = {good:'<path d="M5 12.5l4.5 4.5L19 7.5"/>', watch:'<path d="M12 6v7"/><path d="M12 17.5v.01"/>',
  critical:'<path d="M7 7l10 10M17 7L7 17"/>', unknown:'<path d="M7 12h10"/>'};
const hcol = s => `var(${HV[s || 'unknown'][0]})`, hink = s => `var(${HV[s || 'unknown'][1]})`;
const badge = s => `<span class="st" style="color:${hink(s)}"><span class="dot" style="background:${hcol(s)}"></span>${HBADGE[s || 'unknown']}</span>`;
function windowRows(ws, week) {
  return ws.map(w => {
    const pace = week && w.reset_ts ? Math.max(0, Math.min(100, (w.reset_ts - D.generated) / (7 * DAY) * 100)) : null;
    return `<div class="wrow"><div class="l"><span>${esc(w.label)} <b class="num">${w.left}%</b></span><span>${esc(w.reason)}</span></div>
      <div class="meter"><i style="width:${Math.max(w.left, 1)}%;background:${hcol(w.state)}"></i>${pace != null ? `<span class="pace" style="left:${pace}%" title="Where an even pace would put you"></span>` : ''}</div></div>`;
  }).join('');
}
function vitalQuota(el, title, check, cap, week) {
  const ws = (check && check.windows) || [];
  if (!ws.length) { el.innerHTML = `<div class="head">${title}${badge('unknown')}</div><div class="big">—</div><div class="cap">No live reading. TokenCoach reads quota while it runs in the menu bar.</div>`; return; }
  const tight = Math.min(...ws.map(w => w.left));
  el.innerHTML = `<div class="head">${title}${badge(check.state)}</div><div class="big">${tight}%<small>left</small></div>
    <div class="cap">${cap}</div>${windowRows(ws, week)}${week ? '<div class="axis"><span></span><span>The tick marks where an even pace would put you</span></div>' : ''}`;
}
function spark(series, usual, color) {
  const pts = series.map((v, i) => [i, v]).filter(p => p[1] != null);
  if (pts.length < 3) return '';
  const W = 300, Hh = 44, vals = pts.map(p => p[1]).concat(usual ? [usual] : []);
  const max = Math.max(...vals) * 1.08, min = Math.min(...vals) * .9, n = series.length - 1;
  const x = i => i / n * W, y = v => Hh - (v - min) / ((max - min) || 1) * Hh;
  const d = pts.map((p, k) => `${k ? 'L' : 'M'}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join('');
  const last = pts[pts.length - 1];
  return `<svg class="spark" viewBox="0 0 ${W} ${Hh}" preserveAspectRatio="none" aria-hidden="true">
    <path d="${d}L${x(last[0])},${Hh}L${x(pts[0][0])},${Hh}Z" fill="${color}" opacity=".12"/>
    ${usual ? `<line x1="0" x2="${W}" y1="${y(usual)}" y2="${y(usual)}" stroke="var(--text-muted)" stroke-dasharray="3 3" vector-effect="non-scaling-stroke"/>` : ''}
    <path d="${d}" fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round"/>
    <circle cx="${x(last[0])}" cy="${y(last[1])}" r="3" fill="${color}"/></svg>
    <div class="axis"><span>4 weeks ago</span>${usual ? '<span>- - your usual</span>' : ''}<span>Today</span></div>`;
}
function vitalHabits(el, h) {
  let cap;
  const u = h.usual != null ? '$' + h.usual.toFixed(2) : '';
  if (h.change == null) cap = `Needs about a week of prompts to compare with your usual (${h.recent_prompts} in the last 7 days).`;
  else if (h.state === 'watch') cap = `Last 7 days: ${Math.round(h.change * 100)}% above your usual ${u}. ${esc(h.tip)}`;
  else if (h.change <= -0.1) cap = `Last 7 days: ${Math.abs(Math.round(h.change * 100))}% below your usual ${u}. Keep it up.`;
  else cap = `Last 7 days: about your usual ${u}.`;
  const link = h.lesson ? `<div style="margin-top:6px"><button class="btn quiet" data-act="goto-lesson" data-id="${h.lesson.id}">Lesson: ${esc(h.lesson.title)} ›</button></div>` : '';
  el.innerHTML = `<div class="head">Habits${badge(h.state)}</div>
    <div class="big">${h.cpp != null ? '$' + h.cpp.toFixed(2) : '—'}<small>per prompt</small></div>
    <div class="cap">${cap}</div>${link}${spark(h.series || [], h.usual, hcol(h.state === 'unknown' ? 'good' : h.state))}`;
}
function health() {
  if (!H) { $('#health').style.display = 'none'; return; }
  $('#health').style.display = '';
  const rs = document.documentElement.style;
  rs.setProperty('--state', hcol(H.state)); rs.setProperty('--state-ink', hink(H.state));
  const stale = H.read_at && D.generated - H.read_at > 15 * 60 ? ` Quota as of ${when(H.read_at)}.` : '';
  const act = H.action && H.action.lesson ? `<div class="acts"><button class="btn primary" data-act="goto-lesson" data-id="${H.action.lesson}">${esc(H.action.label)}</button></div>` : '';
  $('#hero').innerHTML = `<div class="glyph" aria-hidden="true"><svg viewBox="0 0 24 24">${HICON[H.state]}</svg></div>
    <div><div class="state-word">${HWORD[H.state]}</div><h1>${esc(H.headline)}</h1><p>${esc(H.detail)}${stale}</p>${act}
    <details class="how"><summary>ⓘ How is this decided?</summary><ul>
      <li><b>Right now</b>: amber when a 5-hour window has less than 30% left, or you're on pace to empty it before it resets. Red when it's empty.</li>
      <li><b>This week</b>: amber when you're on pace to use the weekly limit before it resets, or less than 15% is left. Red when it's used up.</li>
      <li><b>Habits</b>: your cost per prompt over the last 7 days against the 4 weeks before. Amber when it's 25% or more above your usual, with a tip on what to change. Habits never turn red: red means you can't work.</li>
      <li>The overall state is the worst of the three. The menu bar colors its percentages from the first two.</li></ul></details></div>`;
  const q = H.quota || {};
  vitalQuota($('#v-now'), 'Right now', q.now, 'In your tightest 5-hour window');
  vitalQuota($('#v-week'), 'This week', q.week, 'Of your tightest weekly limit', true);
  vitalHabits($('#v-habits'), H.habits || {});
}

// ── spending: totals, change vs the previous period ─────────────────────
function monthPace() {
  const now = new Date(D.generated * 1000);
  const m0 = new Date(now.getFullYear(), now.getMonth(), 1).getTime() / 1000;
  const m1 = new Date(now.getFullYear(), now.getMonth() + 1, 1).getTime() / 1000;
  const frac = (D.generated - m0) / (m1 - m0);
  const rows = F.filter(f => f.t >= m0 && !f.p.est && (V.group === 'all' || grp(f.src) === V.group));
  const cost = sum(rows, f => f.cost || 0), plans = D.plans || {};
  const plan = V.group === 'claude' ? plans.claude : V.group === 'openai' ? plans.chatgpt
    : (plans.claude || 0) + (plans.chatgpt || 0) || null;
  return {cost, pace: frac > 0.03 ? cost / frac : null, plan};
}
// down is good for $ (goodDown=true), neutral for counts (goodDown=null)
function chip(a, b, goodDown) {
  if (!(b > 0)) return '';
  const ch = Math.round((a - b) / b * 100), cls = goodDown == null || ch === 0 ? 'neutral' : (ch < 0) === goodDown ? 'good' : 'bad';
  return `<span class="chip ${cls}" title="vs the previous ${S.range === 'today' ? 'day' : 'period'}">${ch < 0 ? '↓' : '↑'} ${Math.abs(ch)}%</span>`;
}
function tiles(rows, prev) {
  const cost = sum(rows, f => f.cost || 0), pcost = sum(prev, f => f.cost || 0);
  const prompts = sum(rows, f => f.first ? 1 : 0), pprompts = sum(prev, f => f.first ? 1 : 0);
  const calls = sum(rows, f => f.calls);
  const inTok = sum(rows, f => f.tin + f.tcw + f.tcr), tokens = inTok + sum(rows, f => f.tout);
  const T = [
    ['Spent', usd(cost) + chip(cost, pcost, true), 'at API prices'],
    ['Prompts', prompts.toLocaleString() + chip(prompts, pprompts, null), prompts ? `${(calls / prompts).toFixed(0)} agent responses each on average` : ''],
    ['Per prompt', (prompts ? usd(cost / prompts) : '—') + (prompts && pprompts ? chip(cost / prompts, pcost / pprompts, true) : ''), ''],
  ];
  if (S.adv) {
    const quotaOf = prov => {
      const rs = rows.filter(f => D.provider[f.src] === prov && !f.p.est), n = sum(rs, f => f.calls), known = sum(rs, f => f.qn);
      return {v: known ? sum(rs, f => f.q5 || 0) : null, cover: n ? known / n : 1};
    };
    const qc = quotaOf('claude'), qx = quotaOf('codex');
    const shown = V.group === 'openai' ? [qx] : V.group === 'claude' ? [qc] : [qc, qx];
    const cover = Math.min(...shown.map(q => q.cover));
    const qv = shown.map(q => pct(q.v)).join(' · ');
    T.push(['5-hour quota used', shown.length > 1 ? `<span class="pair">${qv}</span>` : qv,
      (V.group === 'all' ? 'Claude (est.) · Codex, summed over windows' : 'summed over 5-hour windows') +
      (cover < 0.995 ? `; measured for ${Math.round(cover * 100)}% of responses` : '')]);
    T.push(['Tokens', tok(tokens), `${tok(sum(rows, f => f.tout))} output`]);
    T.push(['Cache reuse', inTok ? Math.round(sum(rows, f => f.tcr) / inTok * 100) + '%' : '—', 'input served from cache (cheaper)']);
  }
  $('#tiles').innerHTML = T.map(([k, v, d]) => `<div class="kpi"><div class="k">${k}</div><div class="v">${v}</div>${d ? `<div class="d">${d}</div>` : ''}</div>`).join('');
  const mp = monthPace(), planName = {claude: 'Your Claude plan costs', openai: 'Your ChatGPT plan costs', all: 'Your plans cost'}[V.group];
  $('#value-note').textContent = mp.plan && mp.cost
    ? `${planName} $${mp.plan} a month. At API prices, this month's usage so far would cost ${(mp.cost / mp.plan).toFixed(1)}× that.`
    : mp.pace ? `At API prices, this month is on pace for ${usd(mp.pace)}.` : '';
}

// ── coach ─────────────────────────────────────────────────────────────────
// Evidence is named from the number of separate sessions that show the pattern (coach.evidence_level):
// a rule of thumb, not a measured accuracy, so no percentage is shown.
const EVIDENCE_HELP = 'Based on how many separate sessions show the pattern: 1-2 limited, 3-7 moderate, 8 or more strong. A rule of thumb, not a measured accuracy.';
const evidenceLabel = l => `${{none: 'No', limited: 'Limited', moderate: 'Moderate', strong: 'Strong'}[l.evidence_level] || 'No'} evidence · ${l.evidence_n} session${l.evidence_n === 1 ? '' : 's'}`;
const dayLabel = t => new Date(t * 1000).toLocaleDateString(undefined, {month: 'short', day: 'numeric'});
const period = s => `${dayLabel(s.from)} – ${dayLabel(s.to)}, ${s.prompts} prompt${s.prompts === 1 ? '' : 's'} in ${s.sessions} session${s.sessions === 1 ? '' : 's'}`;
const scopeLabel = l => (l.scope === 'global' ? 'all projects' : l.scope) + ' · ' + ({claude:'Claude', codex:'Codex', both:'Claude + Codex'}[l.tools]);
const fileList = files => files && files.length ? files.map(f => f.startsWith(D.home + '/') ? '~' + f.slice(D.home.length) : f).join(', ') : 'no project folder found';
const ago = t => { const d = Math.round((D.generated - t) / DAY); return d < 1 ? 'today' : d === 1 ? 'yesterday' : `${d} days ago`; };
function impactBlock(l) {
  const im = l.impact; if (!im) return '';
  if (!im.ready) return `<div class="why">Measuring: ${im.after.prompts} of ${im.needed} prompts since it was applied.</div>`;
  const lab = {cost_per_prompt:'cost per prompt', responses_per_prompt:'responses per prompt', peak_context:'peak context', session_length:'session length'};
  const cells = Object.entries(im.changes).filter(([k]) => lab[k]).slice(0, 4).map(([k, v]) =>
    `<div><b class="${Math.round(v * 100) < 0 ? 'better' : Math.round(v * 100) > 0 ? 'worse' : ''}">${changeLabel(v)}</b><span>${lab[k]}</span></div>`);
  const caveat = `<div class="why">Observed change since it was applied, not a controlled test: other things changed too.${im.small_sample ? ' This is a <b>small sample</b>, so treat it as a hint.' : ''}</div>`;
  return caveat + (cells.length ? `<div class="gain num">${cells.join('')}</div>` : '<div class="why">No change yet.</div>') + quotaLine(im) +
    `<div class="why num">Before: ${period(im.before)}. After: ${period(im.after)}.</div>`;
}
function changeLabel(v) {
  const r = Math.round(v * 100);
  return r === 0 ? 'no change' : `${r < 0 ? '−' : '+'}${Math.abs(r)}%`;
}
// Prompts without quota data are left out of the average, so show how many were measured.
function quotaLine(im) {
  const side = s => s.prompts ? `${s.quota_per_prompt == null ? 'unavailable' : pct(s.quota_per_prompt)} (${s.quota_known} of ${s.prompts} prompts measured)` : 'unavailable (no prompts)';
  const ch = im.changes.quota_per_prompt, delta = ch == null ? '' : `, ${changeLabel(ch)}`;
  return `<div class="why num">5-hour quota per prompt: ${side(im.before)} before, ${side(im.after)} after${delta}.</div>`;
}
function lessonRow(l) {
  const kind = l.status === 'applied' ? 'working' : l.status === 'ready' ? 'ready' : 'maybe';
  let acts = '', why;
  if (l.status === 'ready') acts = `<button class="btn quiet" data-act="dismiss" data-id="${l.id}">Not now</button><button class="btn primary" data-act="apply" data-id="${l.id}">Apply</button>`;
  else if (l.status === 'review' || (l.status === 'collecting' && l.edited)) acts = `<button class="btn quiet" data-act="dismiss" data-id="${l.id}">Not now</button><button class="btn" data-act="apply-confirm" data-id="${l.id}">Try it</button>`;
  if (l.status === 'applied') {
    const im = l.impact;
    why = `Applied ${ago(l.applied_ts)}.`;
  } else if (l.status === 'collecting') why = `Watching: needs about ${l.needed} sessions of evidence (${l.evidence_n} so far).`;
  else why = [l.evidence, l.saving && `Analyze's own estimate: ${l.saving}`].filter(Boolean).map(esc).join(' ');
  const files = l.status === 'applied' ? `Written to ${esc(fileList(l.files))}` : `Adds one rule to ${esc(fileList(l.files))}`;
  const conf = `<span title="${EVIDENCE_HELP}">${evidenceLabel(l)}</span>`;
  return `<div class="lesson" id="lesson-${l.id}"><div class="licon ${kind}" aria-hidden="true">${{working:'✓', ready:'✦', maybe:'?'}[kind]}</div>
    <div class="body"><div class="t">${esc(l.title)}${l.edited ? ' <span class="tag">edited by you</span>' : ''}</div><div class="why">${why}</div>
    ${l.status === 'applied' ? impactBlock(l) : ''}
    <details><summary>Details</summary><div class="rule">“${esc(l.rule)}”</div>
      <div class="meta">${conf}<span>${esc(scopeLabel(l))}</span><span>${files}</span>
      <button class="btn link" data-act="edit" data-id="${l.id}">Edit</button>${l.status === 'applied' ? `<button class="btn danger" data-act="unapply" data-id="${l.id}">Remove</button>` : ''}</div></details></div>
    ${acts ? `<div class="acts">${acts}</div>` : ''}</div>`;
}
function coach() {
  const L = C.lessons, by = s => L.filter(l => l.status === s);
  const ready = by('ready'), review = by('review'), applied = by('applied'), collecting = by('collecting');
  let h = '';
  const sugg = ready.concat(review);
  if (sugg.length) h += `${ready.length > 1 ? `<div class="group-label" style="display:flex;justify-content:space-between;align-items:center">Suggested<button class="btn quiet" data-act="apply-ready">Apply all ${ready.length} ready</button></div>` : ''}<div class="list">${sugg.map(lessonRow).join('')}</div>`;
  else h += `<div class="list"><div class="empty">No suggestions right now. They appear as patterns repeat across your sessions; <b>Analyze deeper</b> looks at your costliest prompts.</div></div>`;
  const nk = C.nudges.by_kind || {}, total = Object.values(nk).reduce((a, b) => a + b, 0);
  const follow = C.nudges.context_total ? ` You started fresh after ${C.nudges.context_followed} of ${C.nudges.context_total} long-context nudges.` : '';
  const nudge = `<div class="nudge"><div class="txt">${D.nudges_on ? `<b>Nudges in Claude Code</b> · ${total} in the last 30 days.${follow}` : '<b>Nudges are off.</b> TokenCoach can warn you in Claude Code before an expensive prompt.'}</div>
    <button class="toggle ${D.nudges_on ? 'on' : ''}" role="switch" aria-checked="${D.nudges_on ? 'true' : 'false'}" aria-label="Nudges in Claude Code" data-act="nudges" data-on="${D.nudges_on ? 0 : 1}"></button></div>`;
  h += `<div class="group-label">Applied</div><div class="list">${applied.length ? applied.map(lessonRow).join('') : '<div class="lesson"><div class="why">Lessons you apply show here, with before and after numbers.</div></div>'}${nudge}</div>`;
  if (collecting.length) h += `<details class="adv"><summary class="group-label">Watching ${collecting.length} more pattern${collecting.length > 1 ? 's' : ''} (collecting evidence)</summary><div class="list">${collecting.map(lessonRow).join('')}</div></details>`;
  $('#coach').innerHTML = h;
  $('#analyze-meta').textContent = D.last_analysis ? `last run ${D.last_analysis}` : '';
}
document.addEventListener('click', async e => {
  const b = e.target.closest('[data-act]'); if (!b) return;
  const act = b.dataset.act, id = b.dataset.id;
  if (act === 'close-improve') { b.closest('.improve').remove(); return; }
  if (act === 'apply' || act === 'apply-confirm') {
    const l = C.lessons.find(x => x.id === id);
    if (act === 'apply-confirm' && !confirm(`Add this rule to ${fileList(l.files)}?\n\n“${l.rule}”`)) return;
    const r = await busy(b, 'Applying…', () => api('lesson/apply', {id, confirm: act === 'apply-confirm'}));
    if (r) { toast('Written to ' + fileList(r.files)); setTimeout(() => requestRefresh(), 900); }
  } else if (act === 'apply-ready') {
    // the rules sit in collapsed Details: show exactly what is about to be written
    const ready = C.lessons.filter(l => l.status === 'ready');
    if (!confirm(`Add these rules?\n\n${ready.map(l => `• “${l.rule}”\n   → ${fileList(l.files)}`).join('\n\n')}`)) return;
    const r = await busy(b, 'Applying…', () => api('lessons/apply-ready'));
    if (r) { toast('Written to ' + fileList(r.files)); setTimeout(() => requestRefresh(), 900); }
  } else if (act === 'edit') {
    const l = C.lessons.find(x => x.id === id), row = document.getElementById('lesson-' + id);
    if (row.querySelector('.editor')) return;
    const applied = l.status === 'applied';
    const scopes = ['global', ...(C.projects || [])].map(p => `<option value="${esc(p)}" ${p === l.scope ? 'selected' : ''}>${p === 'global' ? 'All projects' : esc(p)}</option>`).join('');
    const tools = {claude:'Claude', codex:'Codex', both:'Claude + Codex'};
    row.querySelector('.body').insertAdjacentHTML('beforeend', `<div class="editor improve">
      <label class="e">Title</label><input class="ed-title" value="${esc(l.title)}" style="width:100%;margin:2px 0 8px">
      <label class="e">Rule written into ${esc(fileList(l.files))} — the agent reads this every session</label>
      <textarea class="ed-rule" rows="3" style="width:100%;margin:2px 0 8px;font:inherit">${esc(l.rule)}</textarea>
      ${applied ? '<div class="e" style="margin-bottom:8px">Remove the lesson first to change where it applies.</div>' : `<div class="acts" style="margin-bottom:8px">
        <select class="ed-scope" aria-label="Applies to">${scopes}</select>
        <select class="ed-tools" aria-label="Tools">${Object.entries(tools).map(([k, v]) => `<option value="${k}" ${k === l.tools ? 'selected' : ''}>${v}</option>`).join('')}</select></div>`}
      <div class="acts"><button class="btn primary" data-act="edit-save" data-id="${id}">Save</button>
      <button class="btn link" data-act="edit-cancel" data-id="${id}">Cancel</button></div></div>`);
    row.querySelector('.ed-rule').focus();
  } else if (act === 'edit-cancel') {
    document.getElementById('lesson-' + id).querySelector('.editor').remove();
  } else if (act === 'edit-save') {
    const ed = document.getElementById('lesson-' + id).querySelector('.editor');
    const body = {id, title: ed.querySelector('.ed-title').value, rule: ed.querySelector('.ed-rule').value};
    if (ed.querySelector('.ed-scope')) { body.scope = ed.querySelector('.ed-scope').value; body.tools = ed.querySelector('.ed-tools').value; }
    const r = await busy(b, 'Saving…', () => api('lesson/edit', body));
    if (r) { ed.remove(); toast('Saved.'); setTimeout(() => requestRefresh(), 500); }
  } else if (act === 'unapply' || act === 'dismiss') {
    const r = await busy(b, '…', () => api(act === 'unapply' ? 'lesson/unapply' : 'lesson/dismiss', {id}));
    if (r) requestRefresh();
  } else if (act === 'goto-lesson') {
    const row = document.getElementById('lesson-' + id); if (!row) return;
    row.scrollIntoView({behavior: 'smooth', block: 'center'});
    row.classList.remove('flash'); void row.offsetWidth; row.classList.add('flash');
    const d = row.querySelector('details'); if (d) d.open = true;
  } else if (act === 'nudges') {
    const r = await busy(b, '…', () => api('nudges', {on: b.dataset.on === '1'}));
    if (r) { toast(r.on ? 'Nudges on — you will see them in Claude Code.' : 'Nudges off.'); setTimeout(() => requestRefresh(), 700); }
  } else if (act === 'analyze') {
    toast('Analyzing your costliest prompts with Claude — about a minute…', 90000);
    const r = await busy(b, 'Analyzing…', () => api('analyze'));
    if (r) { toast('Done.'); setTimeout(() => requestRefresh(), 600); }
  } else if (act === 'improve' || act === 'improve-again') {
    const box = document.getElementById('imp-' + b.dataset.i);
    if (act === 'improve' && box.innerHTML) { box.innerHTML = ''; return; }
    const p = P[+b.dataset.i];
    const cached = act === 'improve' && C.improvements[p.id];
    const r = cached ? cached : await busy(b, 'Improving… (~30s)', () => api('improve', {prompt_id: p.id, force: act === 'improve-again'}));
    if (!r) return;
    C.improvements[p.id] = {rewrite: r.rewrite, why: r.why};
    box.innerHTML = improveBox(p, r);
    box.querySelector('.improve').dataset.protect = '1';
  } else if (act === 'copy') {
    const p = P[+b.dataset.i], text = (C.improvements[p.id] || {}).rewrite || '';
    try { await navigator.clipboard.writeText(text); toast('Copied — paste it into Claude or Codex.'); } catch (err) { toast('Copy failed; select the text instead.'); }
  } else if (act === 'save-template') {
    const p = P[+b.dataset.i], text = (C.improvements[p.id] || {}).rewrite || '';
    const title = prompt('Name this template', p.text.replace(/\s+/g, ' ').slice(0, 50));
    if (title === null) return;
    const r = await api('template/save', {title, text, prompt_id: p.id});
    if (r) { C.templates.unshift({id: r.id, title, text, ts: Date.now() / 1000}); templates(); toast('Saved to your templates.'); }
  } else if (act === 'copy-template') {
    const t = C.templates.find(x => String(x.id) === id);
    try { await navigator.clipboard.writeText(t.text); toast('Copied.'); } catch (err) { toast('Copy failed.'); }
  } else if (act === 'delete-template') {
    if (!confirm('Delete this template?')) return;
    const r = await api('template/delete', {id: +id});
    if (r) { C.templates = C.templates.filter(x => String(x.id) !== id); templates(); }
  }
});
function improveBox(p, r) {
  return `<div class="improve"><b>Tighter version</b><pre>${esc(r.rewrite)}</pre>
    ${r.why && r.why.length ? `<ul>${r.why.map(w => `<li>${esc(w)}</li>`).join('')}</ul>` : ''}
    <div class="acts"><button class="btn primary" data-act="copy" data-i="${p.i}">Copy</button>
    <button class="btn" data-act="save-template" data-i="${p.i}">Save as template</button>
    <button class="btn link" data-act="close-improve">Close</button>
    <button class="btn link" data-act="improve-again" data-i="${p.i}">Try again</button></div></div>`;
}
function templates() {
  const el = $('#templates-card');
  if (!C.templates.length) { el.style.display = 'none'; return; }
  el.style.display = '';
  $('#templates').innerHTML = C.templates.map(t => `<div class="lesson"><div class="body"><div class="t">${esc(t.title)}</div>
    <details><summary>Show</summary><pre class="prompt">${esc(t.text)}</pre></details></div>
    <div class="acts"><button class="btn quiet" data-act="delete-template" data-id="${t.id}">Delete</button><button class="btn" data-act="copy-template" data-id="${t.id}">Copy</button></div></div>`).join('');
}

// ── timeline: stacked columns by tool ────────────────────────────────────
function buckets(lo, hi) {
  if (S.range === 'today') { const b = []; for (let t = lo; t < lo + DAY; t += 3600) b.push([t, t + 3600, new Date(t * 1000).getHours() + ':00']); return b; }
  const weekly = hi - lo > 120 * DAY, b = [];
  let t = startOfDay(lo);
  while (t < hi) {
    const next = weekly ? t + 7 * DAY : startOfDay(t + DAY + 7200);
    b.push([t, next, (weekly ? 'wk ' : '') + new Date(t * 1000).toLocaleDateString(undefined, {month:'short', day:'numeric'})]);
    t = next;
  }
  return b;
}
// a round number at or above v: 1, 2, 2.5, 5 × 10^n
function niceCeil(v) {
  if (!(v > 0)) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v - 1e-9) return m * p;
  return 10 * p;
}
function timeline(rows, lo, hi) {
  const M = METRICS[V.metric], B = buckets(lo, hi);
  const srcs = SRC.filter(s => rows.some(f => f.src === s.key));
  const val = B.map(([a, b]) => { const r = rows.filter(f => f.t >= a && f.t < b); return srcs.map(s => sum(r.filter(f => f.src === s.key), M.get)); });
  const tot = val.map(v => v.reduce((x, y) => x + y, 0)), max = Math.max(0, ...tot);
  const unit = S.range === 'today' ? 'hour' : hi - lo > 120 * DAY ? 'week' : 'day';
  $('#tl-title').textContent = V.metric === 'cost' ? 'Spending' : M.label;
  $('#tl-sub').textContent = RANGES[S.range] + (V.metric === 'cost' ? ', at API prices' : '');
  const totals = srcs.map((s, k) => sum(val, v => v[k]));
  $('#tl-legend').innerHTML = srcs.map((s, k) => `<span><i style="background:var(--s${s.slot})"></i>${esc(s.label)} <b>${esc(M.fmt(totals[k]))}</b></span>`).join('');
  if (!max) { $('#timeline').innerHTML = `<div class="empty">No ${V.metric === 'cost' ? 'priced ' : ''}activity in this range.</div>`; return; }
  // One outlier shouldn't flatten every other bar: cap the scale near the
  // 90th percentile and mark the bars that go past it.
  const sorted = tot.filter(v => v > 0).sort((a, b) => a - b), p90 = sorted[Math.floor(sorted.length * .9)] || max;
  const top = B.length >= 7 && max > p90 * 1.8 ? niceCeil(p90 * 1.25) : niceCeil(max);
  const avg = tot.reduce((a, b) => a + b, 0) / B.length;
  const W = Math.max(300, $('#timeline').clientWidth), Hh = 220, L = 44, BOT = 22, TOP = 18, ph = Hh - BOT - TOP, step = (W - L) / B.length;
  const gap = Math.min(Math.max(2, step * .22), 8), bw = Math.max(step - gap, 1);
  const Y = v => TOP + ph * (1 - Math.min(v, top) / top);
  let s = `<svg viewBox="0 0 ${W} ${Hh}" role="img" aria-label="${esc(M.label)} per ${unit}">`;
  const tick = v => V.metric !== 'cost' ? M.fmt(v) : top >= 5 ? '$' + Math.round(v) : '$' + v.toFixed(2);
  for (const fr of [0, 0.5, 1]) s += `<line class="gridline" x1="${L}" x2="${W}" y1="${Y(top * fr)}" y2="${Y(top * fr)}"/><text x="${L - 8}" y="${Y(top * fr) + 4}" text-anchor="end">${esc(tick(top * fr))}</text>`;
  const every = Math.max(1, Math.ceil(B.length / Math.max(2, Math.floor((W - L) / 70))));
  B.forEach(([a, b, label], i) => {
    const x = L + i * step + gap / 2, over = tot[i] > top, k = over ? top / tot[i] : 1;
    let y = TOP + ph;
    s += `<g class="bucket" data-i="${i}">`;
    const segs = val[i].map((v, j) => [v * k, j]).filter(([v]) => v > 0);
    segs.forEach(([v, j], n) => {
      const h = ph * v / top; y -= h;
      const isTop = n === segs.length - 1, hh = Math.max(h - (n > 0 ? 1.5 : 0), 0.5);
      const r = isTop ? Math.min(4, bw / 2, hh) : 0, fill = `var(--s${srcs[j].slot})`;
      s += r > 0 ? `<path d="M${x},${y + hh} L${x},${y + r} Q${x},${y} ${x + r},${y} L${x + bw - r},${y} Q${x + bw},${y} ${x + bw},${y + r} L${x + bw},${y + hh} Z" fill="${fill}"/>`
                 : `<rect x="${x}" y="${y}" width="${bw}" height="${hh}" fill="${fill}"/>`;
    });
    if (over) s += `<path d="M${x - 1},${TOP + 12} l${bw / 2 + 1},-5 l${bw / 2 + 1},5" stroke="var(--surface-1)" stroke-width="3" fill="none"/>`
      + `<text class="hi" x="${x + bw / 2}" y="${TOP - 5}" text-anchor="middle">${esc(M.fmt(tot[i]))}</text>`;
    s += `<rect class="hit" x="${L + i * step}" y="0" width="${step}" height="${TOP + ph}"/></g>`;
    if (i % every === 0 || i === B.length - 1 && i % every > every / 2) s += `<text x="${x + bw / 2}" y="${Hh - 6}" text-anchor="middle">${esc(i === B.length - 1 && S.range !== 'today' && unit === 'day' ? 'Today' : label)}</text>`;
  });
  if (avg > 0 && B.length > 1) {
    s += `<line class="avgline" x1="${L}" x2="${W}" y1="${Y(avg)}" y2="${Y(avg)}"/>`;
    $('#tl-legend').insertAdjacentHTML('beforeend', `<span><svg width="16" height="2" aria-hidden="true"><line class="avgline" x1="0" x2="16" y1="1" y2="1"/></svg>Average <b>${esc(M.fmt(avg))}</b> per ${unit}</span>`);
  }
  const el = $('#timeline'); el.innerHTML = s + '</svg>';
  const svg = el.querySelector('svg');
  el.querySelectorAll('.bucket').forEach(g => {
    const i = +g.dataset.i;
    g.onmousemove = e => { svg.classList.add('dim'); g.classList.add('cur'); showTip(e, `<b>${esc(B[i][2])}</b>` + srcs.map((sr, k) => val[i][k] ? `<div class="row"><span><span class="dot" style="background:var(--s${sr.slot})"></span>${esc(sr.label)}</span><span>${esc(M.fmt(val[i][k]))}</span></div>` : '').join('') + `<div class="row tot"><span>Total</span><span>${esc(M.fmt(tot[i]))}</span></div>`); };
    g.onmouseleave = () => { svg.classList.remove('dim'); g.classList.remove('cur'); hideTip(); };
  });
}

// ── advanced: quota over time ─────────────────────────────────────────────
function quotaChart(lo, hi) {
  const series = [['claude', 'Claude 5-hour', 1], ['codex', 'Codex 5-hour', 2]]
    .filter(([k]) => V.group === 'all' || (k === 'claude') === (V.group === 'claude'))
    .map(([k, label, slot]) => ({label, slot, pts: (D.quota[k] || []).filter(p => p[0] >= lo && p[0] < hi)})).filter(s => s.pts.length);
  const peaks = !['today', '7d'].includes(S.range);
  $('#q-title').textContent = peaks ? 'Peak 5-hour quota used per ' + (hi - lo > 120 * DAY ? 'week' : 'day') : 'Quota used (5-hour windows)';
  $('#q-legend').innerHTML = series.map(s => `<span><i style="background:var(--s${s.slot})"></i>${s.label}</span>`).join('');
  if (!series.length) { $('#quota').innerHTML = '<div class="empty">No quota readings in this range.</div>'; return; }
  const W = Math.max(300, $('#quota').clientWidth), H = 190, L = 40, BOT = 22, TOP = 6, ph = H - BOT - TOP;
  const X = t => L + (t - lo) / (hi - lo) * (W - L), Y = v => TOP + ph * (1 - Math.min(v, 100) / 100);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Quota used over time">`;
  for (const v of [0, 50, 100]) s += `<line class="gridline" x1="${L}" x2="${W}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${v}%</text>`;
  const ticks = buckets(lo, hi), every = Math.max(1, Math.ceil(ticks.length / Math.max(2, Math.floor((W - L) / 80))));
  ticks.forEach(([a, , label], i) => { if (i % every === 0) s += `<text x="${X(a)}" y="${H - 6}" text-anchor="middle">${esc(label)}</text>`; });
  for (const se of series) {
    if (peaks) {
      se.peak = ticks.map(([a, b]) => { let m = null; for (const [t, v] of se.pts) if (t >= a && t < b) m = Math.max(m ?? 0, v); return [a + (b - a) / 2, m]; });
      let d = ''; se.peak.forEach(([t, v], i) => { if (v == null) return; d += `${i && se.peak[i - 1][1] != null ? ' L' : 'M'}${X(t)},${Y(v)}`; });
      s += `<path d="${d}" fill="none" stroke="var(--s${se.slot})" stroke-width="2" stroke-linejoin="round"/>`;
      se.peak.forEach(([t, v]) => { if (v != null) s += `<circle cx="${X(t)}" cy="${Y(v)}" r="4" fill="var(--s${se.slot})" stroke="var(--surface-1)" stroke-width="2"/>`; });
    } else {
      let d = '', prev = null;
      for (const [t, v] of se.pts) { d += !prev ? `M${X(t)},${Y(v)}` : t - prev[0] > 6 * 3600 ? ` M${X(t)},${Y(v)}` : ` L${X(t)},${Y(prev[1])} L${X(t)},${Y(v)}`; prev = [t, v]; }
      s += `<path d="${d}" fill="none" stroke="var(--s${se.slot})" stroke-width="2" stroke-linejoin="round"/>`;
    }
  }
  s += `<line id="q-x" class="gridline" y1="${TOP}" y2="${TOP + ph}" style="display:none"/><rect class="hit" x="${L}" y="${TOP}" width="${W - L}" height="${ph}"/></svg>`;
  const el = $('#quota'); el.innerHTML = s;
  const svg = el.querySelector('svg'), hit = svg.querySelector('.hit'), cx = svg.querySelector('#q-x');
  hit.onmousemove = e => {
    const r = svg.getBoundingClientRect(), t = lo + ((e.clientX - r.left) / r.width * W - L) / (W - L) * (hi - lo);
    cx.setAttribute('x1', X(t)); cx.setAttribute('x2', X(t)); cx.style.display = '';
    const rows = series.map(se => {
      let best = null;
      if (peaks) { for (const p of se.peak) if (p[1] != null && (!best || Math.abs(p[0] - t) < Math.abs(best[0] - t))) best = p; }
      else { for (const p of se.pts) { if (p[0] <= t) best = p; else break; } }
      return best ? `<div class="row"><span><span class="dot" style="background:var(--s${se.slot})"></span>${se.label}</span><span>${pct(best[1])} ${peaks ? 'peak' : 'used'}</span></div>` : '';
    });
    showTip(e, `<b>${new Date(t * 1000).toLocaleString(undefined, {weekday:'short', month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'})}</b>${rows.join('')}`);
  };
  hit.onmouseleave = () => { cx.style.display = 'none'; hideTip(); };
}

// ── advanced: weekday × hour ─────────────────────────────────────────────
function heatmap(rows) {
  const M = METRICS[V.metric], grid = Array.from({length: 7}, () => Array(24).fill(0));
  for (const f of rows) { const d = new Date(f.t * 1000); grid[(d.getDay() + 6) % 7][d.getHours()] += M.get(f); }
  const top = Math.max(...grid.flat());
  if (!top) { $('#heat').innerHTML = '<div class="empty">No activity in this range.</div>'; return; }
  const days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'], W = Math.max(300, $('#heat').clientWidth), L = 36, cw = (W - L) / 24, ch = 22, H = 7 * ch + 18;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Activity by weekday and hour">`;
  grid.forEach((row, r) => {
    s += `<text x="${L - 6}" y="${r * ch + ch / 2 + 4}" text-anchor="end">${days[r]}</text>`;
    row.forEach((v, h) => { const a = v ? 12 + 88 * v / top : 0;
      s += `<rect class="cell" data-r="${r}" data-h="${h}" x="${L + h * cw + 1}" y="${r * ch + 1}" width="${cw - 2}" height="${ch - 2}" rx="3" fill="${v ? `color-mix(in oklab, var(--s1) ${a.toFixed(0)}%, var(--surface-1))` : 'var(--surface-0)'}"/>`; });
  });
  for (let h = 0; h < 24; h += (W < 600 ? 6 : 3)) s += `<text x="${L + h * cw + cw / 2}" y="${H - 4}" text-anchor="middle">${h}:00</text>`;
  const el = $('#heat'); el.innerHTML = s + '</svg>';
  el.querySelectorAll('.cell').forEach(c => {
    c.onmousemove = e => showTip(e, `<b>${days[+c.dataset.r]} ${c.dataset.h}:00–${+c.dataset.h + 1}:00</b><div class="row"><span>${M.label}</span><span>${esc(M.fmt(grid[+c.dataset.r][+c.dataset.h]))}</span></div>`);
    c.onmouseleave = hideTip;
  });
}

// ── advanced: breakdowns (click a row to filter) ─────────────────────────
function breakdown(el, rows, keyOf, filterKey, labelOf, lead) {
  const M = METRICS[V.metric], g = new Map();
  for (const f of rows) {
    const k = keyOf(f); if (!g.has(k)) g.set(k, {k, v: 0, cost: 0, priced: false, prompts: 0, tok: 0, q: null});
    const a = g.get(k); a.v += M.get(f); a.cost += f.cost || 0; a.priced ||= f.cost != null; a.prompts += f.first ? 1 : 0;
    a.tok += f.tin + f.tout + f.tcw + f.tcr; a.q = addq(a.q, f.q5);
  }
  const list = [...g.values()].sort((a, b) => b.v - a.v || b.tok - a.tok).slice(0, 12), top = Math.max(0, ...list.map(a => a.v));
  if (!list.length) { el.innerHTML = '<div class="empty">No data.</div>'; return; }
  el.innerHTML = `<table><tr><th></th><th class="barcell">${M.label}</th><th class="n">$</th><th class="n">Prompts</th><th class="n">Tokens</th><th class="n">5h quota</th></tr>` +
    list.map(a => `<tr class="click" data-k="${esc(a.k)}"><td>${lead ? lead(a.k) : ''}${esc(labelOf ? labelOf(a.k) : a.k)}${S[filterKey] === a.k ? ' <span class="tag">filtered</span>' : ''}</td>
      <td class="barcell"><div class="bar" style="width:${top ? (100 * a.v / top).toFixed(1) : 0}%"></div></td>
      <td class="n">${a.priced ? usd(a.cost) : 'unpriced'}</td><td class="n">${a.prompts}</td><td class="n">${tok(a.tok)}</td><td class="n">${pct(a.q)}</td></tr>`).join('') + '</table>';
  el.querySelectorAll('tr.click').forEach(tr => tr.onclick = () => { S[filterKey] = S[filterKey] === tr.dataset.k ? '' : tr.dataset.k; save(); render(); });
}

// ── advanced: sessions ───────────────────────────────────────────────────
function sessions(rows) {
  const M = METRICS[V.metric], g = new Map();
  for (const f of rows) {
    const k = f.p.sess; if (!g.has(k)) g.set(k, {src: f.src, proj: f.proj, t0: f.t, t1: f.t, v: 0, cost: 0, priced: false, prompts: new Set(), calls: 0, ctx: 0, q: null});
    const a = g.get(k); a.t0 = Math.min(a.t0, f.t); a.t1 = Math.max(a.t1, f.t); a.v += M.get(f); a.cost += f.cost || 0;
    a.priced ||= f.cost != null; if (f.first) a.prompts.add(f.p); a.calls += f.calls; a.ctx = Math.max(a.ctx, f.ctx); a.q = addq(a.q, f.q5);
  }
  const list = [...g.values()].sort((a, b) => b.v - a.v).slice(0, 25);
  if (!list.length) { $('#sessions').innerHTML = '<div class="empty">No sessions in this range.</div>'; return; }
  const dur = s => { const m = Math.round((s.t1 - s.t0) / 60); return m < 60 ? m + 'm' : (m / 60).toFixed(1) + 'h'; };
  $('#sessions').innerHTML = `<table><tr><th>Started</th><th>Session</th><th class="n">Prompts</th><th class="n">Responses</th><th class="n">Length</th><th class="n">Peak context</th><th class="n">$</th><th class="n">5h quota</th></tr>` +
    list.map(s => { const ps = [...s.prompts].sort((a, b) => a.t - b.t), first = ps[0] ? ps[0].text.replace(/\s+/g, ' ').slice(0, 90) : '(no prompt recorded)';
      return `<tr><td class="n">${when(s.t0)}</td><td><span class="tag"><span class="dot" style="background:var(--s${SRC_BY[s.src].slot})"></span>${esc(SRC_BY[s.src].label)}</span><span class="tag">${esc(s.proj)}</span>
      <details><summary>${esc(first)}${first.length >= 90 ? '…' : ''}</summary><ol>${ps.map(p => `<li>${esc(p.text.replace(/\s+/g, ' ').slice(0, 160))}</li>`).join('')}</ol></details></td>
      <td class="n">${ps.length}</td><td class="n">${s.calls}</td><td class="n">${dur(s)}</td><td class="n">${tok(s.ctx)}</td><td class="n">${s.priced ? usd(s.cost) : '—'}</td><td class="n">${pct(s.q)}</td></tr>`; }).join('') +
    '</table><p class="note">Peak context is the largest single request. A session whose context keeps growing re-reads it on every response.</p>';
}

// ── yield: what the spend produced ────────────────────────────────────────
function yieldCard() {
  const Y = D.yield, sec = $('#card-yield');
  if (!Y) { sec.style.display = 'none'; return; }
  sec.style.display = '';
  const o = Y.overall, p0 = v => v == null ? '—' : Math.round(v * 100) + '%', r1 = v => v == null ? '—' : v.toFixed(1);
  const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
  $('#y-sub').textContent = `Commits from Claude Code sessions, judged ${Y.settle_days} days after they were made`;
  const notes = [];
  if (!o.sessions) {
    $('#y-tiles').innerHTML = '';
    $('#y-tables').innerHTML = `<div class="empty">Nothing to judge yet: the first numbers appear ${Y.settle_days} days after the first commit tagged with a Claude-Session line.</div>`;
  } else {
    const T = [
      ['Cost per accepted change', usd(o.cost_per_accepted), `${o.accepted} of ${plural(o.commits, 'commit')} held`],
      ['Prompts per accepted change', r1(o.prompts_per_accepted), 'your attention per surviving commit'],
      ['Held', p0(o.accepted_rate), `${o.reverted} reverted, ${o.rewritten} dropped`],
      ['Rework', p0(o.rework_rate), 'commits followed by a fix to the same files'],
    ];
    $('#y-tiles').innerHTML = T.map(([k, v, d]) => `<div class="kpi"><div class="k">${k}</div><div class="v">${v}</div><div class="d">${d}</div></div>`).join('');
    const table = (list, head, name) => `<table><tr><th>${head}</th><th class="n">Sessions</th><th class="n">$</th><th class="n">Commits</th><th class="n">Accepted</th><th class="n">$ / accepted</th><th class="n">Prompts / accepted</th><th class="n">Rework</th></tr>` +
      list.map(r => `<tr><td>${esc(name(r.key))}</td><td class="n">${r.sessions}</td><td class="n">${usd(r.cost)}</td><td class="n">${r.commits}</td><td class="n">${r.accepted}</td><td class="n">${usd(r.cost_per_accepted)}</td><td class="n">${r1(r.prompts_per_accepted)}</td><td class="n">${p0(r.rework_rate)}</td></tr>`).join('') + '</table>';
    const week = k => 'Week of ' + new Date(k + 'T00:00').toLocaleDateString(undefined, {month: 'short', day: 'numeric'});
    $('#y-tables').innerHTML = `<div class="scroll" style="margin-top:18px">${table(Y.by_week, 'Week', week)}</div>` +
      `<div class="adv scroll" style="margin-top:18px">${table(Y.by_model, 'Model (the one that cost most in the session)', modelLabel)}</div>`;
    if (o.idle_sessions) notes.push(`${plural(o.idle_sessions, 'session')} (${usd(o.idle_cost)}) made no commit; their cost is included above.`);
  }
  if (Y.pending.sessions) notes.push(`${plural(Y.pending.sessions, 'session')} and ${plural(Y.pending.commits, 'commit')} are under ${Y.settle_days} days old and not counted yet.`);
  notes.push(`${Y.coverage.tagged} of ${plural(Y.coverage.commits, 'commit')} in the tracked repositories carry a session tag; commits made by hand do not.`);
  notes.push(`Dropped means a commit left every branch within a week, as noticed by TokenCoach's own scans (squash-merging and then deleting a branch counts as dropped). Rework means a later commit whose subject mentions a fix and that touches the same files.`);
  $('#y-note').innerHTML = notes.map(esc).join('<br>');
}

// ── prompts (simple: top 5 · advanced: searchable list) ──────────────────
let promptLimit = 30;
function promptAgg(rows) {
  const g = new Map();
  for (const f of rows) {
    if (!g.has(f.p)) g.set(f.p, {p: f.p, cost: 0, priced: false, tok: 0, calls: 0, ctx: 0, q: null, models: new Set()});
    const a = g.get(f.p); a.cost += f.cost || 0; a.priced ||= f.cost != null; a.tok += f.tin + f.tout + f.tcw + f.tcr;
    a.calls += f.calls; a.ctx = Math.max(a.ctx, f.ctx); a.q = addq(a.q, f.q5); a.models.add(f.model);
  }
  return [...g.values()].filter(a => !a.p.id.startsWith('orphan:'));
}
function promptRows(list, full) {
  return list.map(a => { const t = a.p.text.trim(), one = t.replace(/\s+/g, ' '), imp = C.improvements[a.p.id];
    return `<tr><td class="n">${when(a.p.t)}</td>
      <td><span class="tag"><span class="dot" style="background:var(--s${SRC_BY[a.p.src].slot})"></span>${esc(SRC_BY[a.p.src].label)}</span><span class="tag">${esc(a.p.proj)}</span>${full ? [...a.models].map(m => `<span class="tag">${esc(m)}</span>`).join('') : ''}${a.p.est ? '<span class="tag">estimated</span>' : ''}
      <details><summary>${esc(one.slice(0, 140))}${one.length > 140 ? '…' : ''}</summary><pre class="prompt">${esc(t)}${a.p.trunc ? '\n[… truncated here; the full text is in the ledger]' : ''}</pre></details>
      <div id="imp-${a.p.i}">${imp && !full ? improveBox(a.p, imp) : ''}</div></td>
      <td class="n">${a.calls}</td>${full ? `<td class="n">${tok(a.tok)}</td><td class="n">${tok(a.ctx)}</td>` : ''}
      <td class="n">${a.priced ? usd(a.cost) : pct(a.q)}</td>
      <td class="n">${a.p.est ? '' : `<button class="btn" data-act="improve" data-i="${a.p.i}">${imp ? 'Improved ✓' : 'Improve'}</button>`}</td></tr>`; }).join('');
}
function topPrompts(rows) {
  const list = promptAgg(rows).sort((a, b) => (b.cost - a.cost) || (b.q - a.q) || (b.tok - a.tok)).slice(0, 5);
  if (!list.length) { $('#top').innerHTML = '<div class="empty">No prompts in this range.</div>'; return; }
  const max = Math.max(...list.map(a => a.cost || a.q || 0)) || 1;
  $('#top').innerHTML = list.map(a => {
    const t = a.p.text.trim(), one = t.replace(/\s+/g, ' '), imp = C.improvements[a.p.id], src = SRC_BY[a.p.src];
    return `<div class="prompt-row"><div style="min-width:0"><details><summary>${esc(one.slice(0, 160))}${one.length > 160 ? '…' : ''}</summary>
        <pre class="prompt">${esc(t)}${a.p.trunc ? '\n[… truncated here; the full text is in the ledger]' : ''}</pre></details>
        <div class="pm"><span class="dot" style="background:var(--s${src.slot})"></span><span>${esc(src.label)}</span><span>${esc(a.p.proj)}</span>
        <span>${esc(when(a.p.t))}</span><span>${a.calls} responses</span>${a.p.est ? '<span>estimated</span>' : ''}</div></div>
      <div class="pact"><div class="cost">${a.priced ? usd(a.cost) : pct(a.q)}</div>${a.p.est ? '' : `<button class="btn quiet" data-act="improve" data-i="${a.p.i}">${imp ? 'Tighter version' : 'Improve'}</button>`}</div>
      <div class="cbar"><i style="width:${((a.cost || a.q || 0) / max * 100).toFixed(1)}%"></i></div>
      <div class="imp" id="imp-${a.p.i}"></div></div>`;
  }).join('');
}
function prompts(rows) {
  const q = S.q.trim().toLowerCase();
  let list = promptAgg(rows).filter(a => !q || a.p.text.toLowerCase().includes(q));
  const key = {cost: a => a.cost + a.tok / 1e9, tokens: a => a.tok, recent: a => a.p.t, quota: a => a.q ?? -1}[S.sort];   // unknown quota sorts below a measured 0
  list.sort((a, b) => key(b) - key(a));
  $('#p-count').textContent = `${list.length.toLocaleString()} prompts`;
  $('#prompts').innerHTML = list.length ? `<table><tr><th>When</th><th>Prompt</th><th class="n">Responses</th><th class="n">Tokens</th><th class="n">Peak context</th><th class="n">$ / quota</th><th></th></tr>${promptRows(list.slice(0, promptLimit), true)}</table>`
    : '<div class="empty">No prompts match.</div>';
  $('#p-more').style.display = list.length > promptLimit ? '' : 'none';
}

// ── render ───────────────────────────────────────────────────────────────
function render() {
  V = view();
  const [lo, hi] = rangeBounds(S.range), rows = filtered(lo, hi), prev = filtered(lo - (hi - lo), lo);
  controls(lo, hi); tiles(rows, prev); coach(); yieldCard(); timeline(rows, lo, hi); topPrompts(rows); templates();
  $('#latest-advice').innerHTML = D.advice_html || '';
  if (S.adv) {
    quotaChart(lo, hi); heatmap(rows);
    breakdown($('#by-project'), rows, f => f.proj, 'project');
    breakdown($('#by-model'), rows, f => f.model, 'model', modelLabel);
    breakdown($('#by-source'), rows, f => f.src, 'source', k => SRC_BY[k].label, k => `<span class="dot" style="background:var(--s${SRC_BY[k].slot})"></span>`);
    sessions(rows); prompts(rows);
  }
}
$('#adv').onclick = () => { S.adv = !S.adv; save(); render(); };
$('#search').value = S.q;
$('#search').oninput = e => { S.q = e.target.value; save(); promptLimit = 30; prompts(filtered(...rangeBounds(S.range))); };
$('#sort').value = S.sort;
$('#sort').onchange = e => { S.sort = e.target.value; save(); prompts(filtered(...rangeBounds(S.range))); };
$('#p-more').onclick = () => { promptLimit += 50; prompts(filtered(...rangeBounds(S.range))); };
$('#clear').onclick = () => { S.source = S.project = S.model = ''; save(); render(); };
health(); render();
// ?hide=id,id  hides parts of the page (used for focused screenshots)
for (const id of (QS.get('hide') || '').split(',').filter(Boolean)) { const el = document.getElementById(id); if (el) el.style.display = 'none'; }
const age = Math.round((Date.now() / 1000 - D.generated) / 60);
function freshness(unavailable = false) {
  const indexed = D.live && D.live.indexed_at;
  const stale = indexed && Date.now() / 1000 - indexed > 10 * 60;
  $('#updated').textContent = D.demo ? 'Sample data' : unavailable
    ? 'App unavailable · showing previous data'
    : D.live ? (indexed ? `Usage indexed ${when(indexed)}` + (stale ? ' · stale' : '') : 'Usage index not yet available') + (D.live.index_status ? ' · ' + D.live.index_status : '')
    : `Snapshot ${when(D.generated)} · read-only copy`;
}
freshness();
// On resize redraw only the charts, so an open lesson editor or rewrite survives.
function redrawCharts() {
  const [lo, hi] = rangeBounds(S.range), rows = filtered(lo, hi);
  timeline(rows, lo, hi);
  if (S.adv) { quotaChart(lo, hi); heatmap(rows); }
}
let rz; addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(redrawCharts, 150); });
// Fetch data without navigating away. Never replace an editor, rewrite, or
// active action. A deferred refresh runs as soon as the interaction finishes.
let refreshDue = false, refreshing = false;
function requestRefresh() { refreshDue = true; refreshData(); }
const protectedInteraction = () => pendingActions || document.querySelector('button[disabled], .improve[data-protect], .editor')
  || /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
async function refreshData() {
  if (!D.live || document.hidden || protectedInteraction() || refreshing) return;
  refreshing = true;
  try {
    const url = new URL(location.href); url.pathname = '/data';
    const response = await fetch(url, {cache:'no-store', signal:AbortSignal.timeout(15000)});
    if (!response.ok) throw new Error('unavailable');
    const next = await response.json();
    // An interaction may have started while the network request was pending.
    if (protectedInteraction()) return;
    const x = scrollX, y = scrollY;
    const expanded = [...document.querySelectorAll('details[open]')].map(el => {
      const parent = el.parentElement.closest('[id]');
      return parent ? [parent.id, [...parent.querySelectorAll('details')].indexOf(el)] : null;
    }).filter(Boolean);
    D = next;
    H = (D.health_samples && D.health_samples[QS.get('health')]) || D.health;
    C = D.coach || {lessons: [], improvements: {}, templates: [], nudges: {by_kind: {}}};
    P = D.prompts.map((p, i) => ({i, id:p[0], t:p[1], src:p[2], proj:p[3], sess:p[4], text:p[5], est:p[6], trunc:p[7]}));
    F = D.facts.map(r => ({p:P[r[0]], model:D.models[r[1]], calls:r[2], cost:r[3], tin:r[4], tout:r[5], tcw:r[6], tcr:r[7], q5:r[8], qw:r[9], ctx:r[10], t:r[11], first:r[12], qn:r[13] || 0}));
    F.forEach(f => { f.src = f.p.src; f.proj = f.p.proj; });
    health(); render(); freshness();
    for (const [id, index] of expanded) {
      const parent = document.getElementById(id);
      const detail = parent && parent.querySelectorAll('details')[index];
      if (detail) detail.open = true;
    }
    scrollTo(x, y);
    refreshDue = false;
  } catch (e) { freshness(true); } finally { refreshing = false; }
}
if (D.live) {
  setInterval(() => { refreshDue = true; refreshData(); }, 5 * 60 * 1000);
  setInterval(() => { if (refreshDue) refreshData(); }, 5000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden && refreshDue) refreshData(); });
}
"""

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TokenCoach</title><style>{css}{dcss}</style></head>
<body>
<div class="top"><div class="in">
  <div class="brand"><span class="mini" aria-hidden="true"></span><h1>TokenCoach</h1><span class="pill" id="updated"></span></div>
  <span class="spacer"></span>
  <span class="ctl"><span class="ctl-label">Tools</span><span class="seg" id="group" aria-label="Tools"></span></span>
  <span class="ctl"><span class="ctl-label">Period</span><span class="seg" id="range" aria-label="Period"></span></span>
  <span class="switch" id="adv" role="switch" tabindex="0"><i></i>Advanced</span>
</div>
<div class="filters adv">
  <select id="f-source" aria-label="Tool"></select>
  <select id="f-project" aria-label="Project"></select>
  <select id="f-model" aria-label="Model"></select>
  <button class="btn link" id="clear">Clear filters</button>
</div></div>
<main>
<div id="health"><div class="hero" id="hero"></div>
  <div class="vitals"><div class="card vital" id="v-now"></div><div class="card vital" id="v-week"></div><div class="card vital" id="v-habits"></div></div></div>
<section id="card-coach"><div class="sh"><h2>Coach</h2><span class="sub">Lessons from your own sessions</span><span class="spacer"></span>
  <span class="note" id="analyze-meta" style="margin:0"></span><button class="btn quiet" data-act="analyze">Analyze deeper</button></div>
  <div id="coach"></div></section>
<section id="card-timeline"><div class="sh"><h2 id="tl-title">Spending</h2><span class="sub" id="tl-sub"></span><span class="spacer"></span><span class="seg adv" id="metric"></span></div>
  <div class="card"><div class="kpis" id="tiles"></div><div class="chart" id="timeline"></div>
  <div class="legend" id="tl-legend"></div><div class="value-note" id="value-note"></div></div></section>
<section id="card-yield" style="display:none"><div class="sh"><h2>What it produced</h2><span class="sub" id="y-sub"></span></div>
  <div class="card"><div class="kpis" id="y-tiles"></div><div id="y-tables"></div><div class="value-note" id="y-note"></div></div></section>
<section id="card-top"><div class="sh"><h2>Costliest prompts</h2><span class="sub">Improve rewrites one into a tighter version you can reuse</span></div>
  <div class="list" id="top"></div></section>
<section id="templates-card" style="display:none"><div class="sh"><h2>Your prompt templates</h2></div><div class="list" id="templates"></div></section>
<section class="adv"><div class="grid2">
  <div class="card chart"><h2 id="q-title">Quota used</h2><div class="legend" id="q-legend"></div><div id="quota"></div>
    <p class="note">Claude from TokenCoach's readings (estimated); Codex from its own reading after each response. Separate plans.</p></div>
  <div class="card chart"><h2>When you work</h2><div id="heat"></div><p class="note">Selected measure by weekday and hour, local time.</p></div>
</div>
<div class="grid2">
  <div class="card scroll"><h2>By project</h2><div id="by-project"></div></div>
  <div class="card scroll"><h2>By model</h2><div id="by-model"></div></div>
</div>
<div class="card scroll"><h2>By tool</h2><div id="by-source"></div><p class="note">Click a row in any table to filter the page.</p></div>
<div class="card scroll"><h2>Costliest sessions</h2><div id="sessions"></div></div>
<div class="card scroll"><div class="cardhead"><h2>All prompts <span class="sub" id="p-count"></span></h2>
  <span><input type="search" id="search" placeholder="Search prompts" aria-label="Search prompts">
  <select id="sort" aria-label="Sort prompts"><option value="cost">Most expensive</option><option value="tokens">Most tokens</option>
  <option value="quota">Most quota</option><option value="recent">Most recent</option></select></span></div>
  <div id="prompts"></div><button class="btn link more" id="p-more">Show more</button></div>
<div id="latest-advice">{advice}</div></section>
<p class="note">API-equivalent $ is what the same tokens would cost on the provider's API at list price; on a subscription you pay a flat fee, so use it to compare, not as a bill. {unpriced}</p>
</main><div id="tip" role="tooltip"></div><div id="toast" role="status"></div>
<script type="application/json" id="data">{data}</script>
<script>{js}</script></body></html>"""


def dashboard_data(conn, config: dict | None = None, days: int = DASHBOARD_DAYS) -> dict:
    config = config or {}
    since = ledger._day_start(days - 1)
    rows = conn.execute(
        """
        SELECT COALESCE(prompt_id, 'orphan:' || session_id) pid, model,
               COUNT(*) calls, SUM(cost_usd) cost,
               SUM(input_tokens) tin, SUM(output_tokens) tout,
               SUM(cache_write_tokens) tcw, SUM(cache_read_tokens) tcr,
               SUM(quota_5h_pct) q5, SUM(quota_week_pct) qw, COUNT(quota_5h_pct) qn,
               MAX(input_tokens + cache_write_tokens + cache_read_tokens) ctx,
               MIN(ts) t, MIN(source) source, MIN(session_id) session_id,
               MIN(project) project, MAX(estimated) est
        FROM calls WHERE ts >= ? AND project != ?
        GROUP BY pid, model ORDER BY pid, t
        """, (since, ledger.OPTIMIZER_PROJECT)).fetchall()
    pids = sorted({r["pid"] for r in rows if not r["pid"].startswith("orphan:")})
    texts = {}
    for i in range(0, len(pids), 500):
        chunk = pids[i:i + 500]
        for p in conn.execute(
                f"SELECT id, source, session_id, project, ts, text, estimated FROM prompts "
                f"WHERE id IN ({','.join('?' * len(chunk))})", chunk):
            texts[p["id"]] = dict(p)

    prompts, index, models, model_ix, facts = [], {}, [], {}, []
    seen_first = set()
    for r in rows:
        pid = r["pid"]
        if pid not in index:
            p = texts.get(pid)
            if p is None:     # responses with no recorded prompt (e.g. resumed sessions)
                p = {"id": pid, "source": r["source"], "session_id": r["session_id"],
                     "project": r["project"], "ts": r["t"], "estimated": r["est"],
                     "text": "(no prompt recorded — e.g. a resumed or automated session)"}
            text = p["text"]
            index[pid] = len(prompts)
            prompts.append([pid, round(p["ts"], 1), p["source"], p["project"], p["session_id"],
                            text[:PROMPT_TEXT_CHARS], int(p["estimated"] or 0),
                            int(len(text) > PROMPT_TEXT_CHARS)])
        if r["model"] not in model_ix:
            model_ix[r["model"]] = len(models)
            models.append(r["model"])
        first = pid not in seen_first
        seen_first.add(pid)
        facts.append([
            index[pid], model_ix[r["model"]], r["calls"],
            None if r["cost"] is None else round(r["cost"], 5),
            r["tin"] or 0, r["tout"] or 0, r["tcw"] or 0, r["tcr"] or 0,
            None if r["q5"] is None else round(r["q5"], 3),
            None if r["qw"] is None else round(r["qw"], 3),
            r["ctx"] or 0, round(r["t"], 1), 1 if first and not pid.startswith("orphan:") else 0,
            r["qn"] or 0,     # calls whose 5-hour quota was measured; the rest are unknown, not 0
        ])

    quota = {}
    for prov in ("claude", "codex"):
        quota[prov] = [[round(t, 1), p] for t, p in conn.execute(
            "SELECT ts, pct FROM quota_samples WHERE provider=? AND window='5h' AND ts >= ? ORDER BY ts",
            (prov, since))]

    present = {p[2] for p in prompts}
    sources = [{"key": k, "label": SOURCE_LABELS[k], "slot": i + 1}
               for i, k in enumerate(SOURCE_ORDER)]
    from tokencoach import coach, nudge
    try:
        coach_data = coach.coach_snapshot(conn)
    except Exception:
        log.exception("coach snapshot failed")
        coach_data = None
    now = datetime.now().timestamp()
    samples = None
    try:
        habits = health.habits_health(conn, (coach_data or {}).get("lessons"), now)
        if DEMO:
            from tokencoach import demo
            samples = {k: _health_block(demo.sample_windows(k, now), habits, now)
                       for k in ("good", "watch", "critical")}
            health_data = samples["good"]
        else:
            windows, read_at = health.read_windows(WIDGET_CACHE_FILE, now)
            health_data = _health_block(windows, habits, now)
            health_data["read_at"] = read_at
    except Exception:
        log.exception("health failed")
        health_data = None
    try:
        from tokencoach import yield_metrics
        yield_data = yield_metrics.snapshot(conn, now)
    except Exception:
        log.exception("yield metrics failed")
        yield_data = None
    advice = sorted(glob.glob(os.path.join(REPORT_DIR, "optimizer-*.md")))
    last_analysis = None
    if advice:
        last_analysis = datetime.fromtimestamp(os.path.getmtime(advice[-1])).strftime("%b %d, %H:%M")
    return {
        "generated": round(now),
        "health": health_data, "health_samples": samples,
        "sources": sources,
        "provider": {k: ("claude" if v == "claude" else "codex") for k, v in ledger.SOURCE_PROVIDER.items()},
        "models": models, "prompts": prompts, "facts": facts, "quota": quota,
        "plans": config.get("ledger_plans") or {},
        "has_chat": bool(present & {"claude_chat", "chatgpt_chat"}),
        "coach": coach_data, "yield": yield_data, "last_analysis": last_analysis,
        "advice_html": _latest_advice(),
        "nudges_on": True if DEMO else nudge.is_installed(), "demo": DEMO,
        "home": os.path.join(os.path.dirname(ledger.LEDGER_DB), "demo-home") if DEMO else os.path.expanduser("~"),
        "equivalents": {m: ledger.equivalent_model(m, ledger.ledger_overrides(config))
                        for m in models if ledger.equivalent_model(m, ledger.ledger_overrides(config))
                        and not _has_exact_price(m, config)},
    }


def _health_block(windows: list[dict], habits: dict, now: float) -> dict:
    q = health.quota_health(windows, now)
    return {"quota": q, "habits": habits, **health.overall(q, habits, now)}


def _has_exact_price(model: str, config: dict) -> bool:
    prices = config.get("ledger_prices") or {}
    return any(model.startswith(k) for k in prices)


def _latest_advice() -> str:
    """The newest Analyze report, rendered, for the advanced view."""
    files = sorted(glob.glob(os.path.join(REPORT_DIR, "optimizer-*.md")))
    if not files:
        return ""
    from tokencoach.optimizer import markdown_to_html
    path = files[-1]
    stamp = os.path.basename(path)[len("optimizer-"):-3]
    try:
        with open(path, encoding="utf-8") as f:
            body = markdown_to_html(f.read())
    except OSError:
        return ""
    return (f'<div class="card advice"><details><summary><h2 style="display:inline">'
            f'Latest analysis report · {html.escape(stamp)}</h2></summary>{body}</details></div>')


def build_report(conn, config: dict | None = None, days: int = DASHBOARD_DAYS,
                 live: dict | None = None) -> str:
    """The dashboard page. `live` ({"token": ...}) enables its buttons when it
    is served by the app's local listener."""
    data = dashboard_data(conn, config, days)
    data["live"] = live
    unpriced = ""
    if data["equivalents"]:
        pairs = ", ".join(f"{m} ≈ {c}" for m, c in sorted(data["equivalents"].items()))
        unpriced = ("OpenAI does not publish prices for the Codex models, so they are priced at the "
                    f"nearest Claude tier (an assumption): {pairs}. Change a mapping with "
                    "\"ledger_model_equivalents\" or set exact prices with \"ledger_prices\" in "
                    "~/Library/Application Support/TokenCoach/config.json.")
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return PAGE.format(
        css=CSS, dcss=DASHBOARD_CSS, js=DASHBOARD_JS, data=blob,
        chat=" · chat imports" if data["has_chat"] else "",
        advice=data["advice_html"], unpriced=html.escape(unpriced),
    )


def write_report(conn, config: dict | None = None, days: int = DASHBOARD_DAYS) -> str:
    """Read-only copy on disk, for when the app is not running."""
    os.makedirs(REPORT_DIR, exist_ok=True)
    tmp = REPORT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(build_report(conn, config, days))
    os.replace(tmp, REPORT_FILE)
    return REPORT_FILE


CHROME_APPS = ("Google Chrome", "Arc", "Brave Browser", "Microsoft Edge")


def open_file(path: str, browser: str | None = None):
    """Open a file or URL in the chosen browser, else Chrome if installed,
    else the default browser."""
    for app in ([browser] if browser else []) + list(CHROME_APPS):
        if app and os.path.exists(f"/Applications/{app}.app"):
            try:
                subprocess.Popen(["open", "-a", app, path])
                return
            except OSError:
                log.debug("could not open with %s", app, exc_info=True)
    subprocess.Popen(["open", path])
