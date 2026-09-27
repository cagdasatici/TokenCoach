"""TokenCoach dashboard: one self-contained HTML page built from the ledger.

The page embeds its data as JSON and does all filtering in the browser. The app
serves it from its local-only listener (aiquotabar/server.py), which also runs
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

from aiquotabar import ledger
from aiquotabar.config import log

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
  --surface-0:#f5f5f3; --surface-1:#fcfcfb; --border:#e4e3df;
  --text-primary:#0b0b0b; --text-secondary:#52514e; --text-muted:#7a7974;
  --grid:#e9e8e4; --accent:#2a78d6;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100; --s5:#e87ba4; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { color-scheme: dark;
  --surface-0:#111110; --surface-1:#1a1a19; --border:#2e2e2c;
  --text-primary:#ffffff; --text-secondary:#c3c2b7; --text-muted:#8f8e86;
  --grid:#2a2a28; --accent:#3987e5;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181; } }
:root[data-theme="dark"] { color-scheme: dark;
  --surface-0:#111110; --surface-1:#1a1a19; --border:#2e2e2c;
  --text-primary:#ffffff; --text-secondary:#c3c2b7; --text-muted:#8f8e86;
  --grid:#2a2a28; --accent:#3987e5;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181; }
* { box-sizing: border-box; }
body { margin:0; background:var(--surface-0); color:var(--text-primary);
  font:14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
main { max-width:1200px; margin:0 auto; padding:20px 16px 48px; }
h1 { font-size:22px; margin:0; } h2 { font-size:15px; margin:0 0 10px; }
.sub { color:var(--text-secondary); margin:2px 0 16px; font-size:13px; }
.note { color:var(--text-muted); font-size:12px; margin:8px 0 0; }
.card { background:var(--surface-1); border:1px solid var(--border); border-radius:10px;
  padding:14px 16px; margin-bottom:16px; min-width:0; }
table { width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; }
th { text-align:left; color:var(--text-secondary); font-weight:500; font-size:12px;
  border-bottom:1px solid var(--border); padding:6px 8px; white-space:nowrap; }
td { border-bottom:1px solid var(--grid); padding:6px 8px; vertical-align:top; }
"""

DASHBOARD_CSS = """
header { display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:4px; }
.brand { display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; }
.controls { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:0 0 16px;
  position:sticky; top:0; z-index:5; background:var(--surface-0); padding:10px 0; }
.spacer { flex:1; }
.seg { display:inline-flex; border:1px solid var(--border); border-radius:8px; overflow:hidden; }
.seg button { border:0; background:var(--surface-1); color:var(--text-secondary); padding:6px 11px;
  font:inherit; font-size:13px; cursor:pointer; border-right:1px solid var(--border); }
.seg button:last-child { border-right:0; }
.seg button.on { background:var(--text-primary); color:var(--surface-1); }
select, input[type=search] { font:inherit; font-size:13px; padding:6px 8px; border-radius:8px;
  border:1px solid var(--border); background:var(--surface-1); color:var(--text-primary); max-width:220px; }
.switch { display:inline-flex; align-items:center; gap:8px; font-size:13px; color:var(--text-secondary); cursor:pointer; user-select:none; }
.switch i { width:32px; height:18px; border-radius:9px; background:var(--border); position:relative; transition:background .15s; }
.switch i::after { content:""; position:absolute; top:2px; left:2px; width:14px; height:14px; border-radius:50%;
  background:var(--surface-1); transition:left .15s; }
.switch.on i { background:var(--accent); } .switch.on i::after { left:16px; }
body:not(.advanced) .adv { display:none !important; }
.btn { font:inherit; font-size:13px; border-radius:7px; padding:5px 11px; cursor:pointer;
  border:1px solid var(--border); background:var(--surface-1); color:var(--text-primary); white-space:nowrap; }
.btn:hover { border-color:var(--text-muted); }
.btn.primary { background:var(--accent); border-color:var(--accent); color:#fff; }
.btn.link { border:0; background:none; color:var(--accent); padding:0; }
.btn[disabled] { opacity:.55; cursor:default; }
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; margin-bottom:16px; }
.tile { background:var(--surface-1); border:1px solid var(--border); border-radius:10px; padding:12px 14px; }
.tile .k { color:var(--text-secondary); font-size:12px; }
.tile .v { font-size:24px; font-weight:600; margin-top:2px; font-variant-numeric:tabular-nums; }
.tile .d { color:var(--text-muted); font-size:12px; }
.grid2 { display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:16px; }
.cardhead { display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:10px; }
.cardhead h2 { margin:0; }
.legend { display:flex; flex-wrap:wrap; gap:12px; font-size:12px; color:var(--text-secondary); margin:0 0 8px; }
.legend i { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:5px; vertical-align:-1px; }
.chart svg { display:block; width:100%; height:auto; overflow:visible; }
.chart text { fill:var(--text-muted); font-size:11px; }
.gridline { stroke:var(--grid); stroke-width:1; }
.hit { fill:transparent; }
.bucket:hover path, .bucket:hover rect:not(.hit) { opacity:.8; }
#tip { position:fixed; pointer-events:none; background:var(--surface-1); border:1px solid var(--border);
  border-radius:8px; padding:8px 10px; font-size:12px; box-shadow:0 4px 16px rgba(0,0,0,.18);
  display:none; z-index:20; max-width:320px; }
#tip b { font-weight:600; } #tip .row { display:flex; justify-content:space-between; gap:16px; }
#toast { position:fixed; bottom:20px; left:50%; transform:translateX(-50%); background:var(--text-primary);
  color:var(--surface-1); padding:9px 14px; border-radius:8px; font-size:13px; display:none; z-index:30; max-width:90vw; }
td.n, th.n { text-align:right; white-space:nowrap; }
tr.click { cursor:pointer; } tr.click:hover td { background:var(--surface-0); }
.bar { height:8px; border-radius:0 4px 4px 0; background:var(--accent); min-width:2px; }
.barcell { width:26%; min-width:80px; }
.tag { display:inline-block; font-size:11px; color:var(--text-secondary); border:1px solid var(--border);
  border-radius:4px; padding:0 5px; margin:0 4px 2px 0; white-space:nowrap; }
.dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }
details summary { cursor:pointer; }
pre.prompt { white-space:pre-wrap; word-break:break-word; font:12px/1.4 ui-monospace, Menlo, monospace;
  color:var(--text-secondary); max-height:320px; overflow:auto; margin:6px 0 0; }
.scroll { overflow-x:auto; }
.empty { color:var(--text-muted); padding:18px 0; text-align:center; }
.advice h2 { margin-top:14px; } .advice li { margin:3px 0; }
.advice pre { white-space:pre-wrap; background:var(--surface-0); padding:8px; border-radius:6px; }
/* coach */
.coach .lesson { display:flex; gap:14px; justify-content:space-between; align-items:flex-start;
  padding:12px 0; border-top:1px solid var(--grid); }
.coach .lesson:first-of-type { border-top:0; }
.coach .lesson .body { min-width:0; flex:1; }
.coach .lesson .t { font-weight:600; }
.coach .lesson .r { color:var(--text-secondary); font-size:13px; margin:2px 0 4px; }
.coach .lesson .e { color:var(--text-muted); font-size:12px; }
.coach .acts { display:flex; gap:6px; flex-shrink:0; align-items:center; }
.pill { display:inline-block; font-size:11px; border-radius:10px; padding:1px 8px; margin-left:6px;
  border:1px solid var(--border); color:var(--text-secondary); font-weight:500; vertical-align:1px; }
.pill.ready { border-color:var(--accent); color:var(--accent); }
.impact { display:flex; flex-wrap:wrap; gap:6px 14px; font-size:12px; color:var(--text-secondary); margin-top:4px; }
.impact b { color:var(--text-primary); font-weight:600; }
.sect { font-size:12px; color:var(--text-muted); text-transform:uppercase; letter-spacing:.04em; margin:14px 0 2px; }
.nudgebar { display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap;
  background:var(--surface-0); border-radius:8px; padding:10px 12px; margin-top:12px; font-size:13px; color:var(--text-secondary); }
.improve { background:var(--surface-0); border-radius:8px; padding:10px 12px; margin-top:8px; }
.improve pre { white-space:pre-wrap; word-break:break-word; font:13px/1.45 ui-monospace, Menlo, monospace;
  margin:6px 0; color:var(--text-primary); }
.improve ul { margin:4px 0 8px 18px; padding:0; font-size:12px; color:var(--text-secondary); }
.improve .acts { display:flex; gap:6px; flex-wrap:wrap; }
.more { margin-top:8px; }
@media (max-width:600px) { .barcell { display:none; } .coach .lesson { flex-direction:column; } }
"""

DASHBOARD_JS = r"""
const D = JSON.parse(document.getElementById('data').textContent);
const C = D.coach || {lessons: [], improvements: {}, templates: [], nudges: {by_kind: {}}};
const SRC = D.sources, SRC_BY = Object.fromEntries(SRC.map(s => [s.key, s]));
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
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
const save = () => { try { localStorage.setItem('tokencoach-dash', JSON.stringify(S)); } catch (e) {} };
let V = S;   // simple view ignores advanced-only filters and measures
const view = () => S.adv ? S : {...S, metric:'cost', source:'', project:'', model:''};

// ── data: facts = one row per (prompt, model) ─────────────────────────────
const P = D.prompts.map((p, i) => ({i, id: p[0], t: p[1], src: p[2], proj: p[3], sess: p[4], text: p[5], est: p[6], trunc: p[7]}));
const F = D.facts.map(r => ({p: P[r[0]], model: D.models[r[1]], calls: r[2], cost: r[3], tin: r[4], tout: r[5],
  tcw: r[6], tcr: r[7], q5: r[8], qw: r[9], ctx: r[10], t: r[11], first: r[12]}));
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

async function api(path, body) {
  if (!D.live) { toast('Open the dashboard from the TokenCoach menu bar icon to use buttons.'); return null; }
  try {
    const r = await fetch('/api/' + path, {method:'POST', headers:{'Content-Type':'application/json', 'X-TokenCoach': D.live.token}, body: JSON.stringify(body || {})});
    const j = await r.json();
    if (!j.ok) { toast(j.error || 'Something went wrong'); return null; }
    return j;
  } catch (e) { toast('TokenCoach is not running. Start it from the menu bar and reopen the dashboard.'); return null; }
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

// ── totals ────────────────────────────────────────────────────────────────
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
function tiles(rows, prev) {
  const cost = sum(rows, f => f.cost || 0), pcost = sum(prev, f => f.cost || 0);
  const prompts = sum(rows, f => f.first ? 1 : 0), pprompts = sum(prev, f => f.first ? 1 : 0);
  const calls = sum(rows, f => f.calls);
  const inTok = sum(rows, f => f.tin + f.tcw + f.tcr), tokens = inTok + sum(rows, f => f.tout);
  const qc = sum(rows.filter(f => D.provider[f.src] === 'claude'), f => f.q5 || 0);
  const qx = sum(rows.filter(f => D.provider[f.src] === 'codex'), f => f.q5 || 0);
  const delta = (a, b) => b > 0 ? `${a >= b ? '▲' : '▼'} ${Math.abs(Math.round((a - b) / b * 100))}% vs previous ${RANGES[S.range] === 'Today' ? 'day' : 'period'}` : '';
  const mp = monthPace();
  const planName = {claude: 'Claude plan', openai: 'ChatGPT plan', all: 'plans'}[V.group];
  const planLine = mp.plan ? `${(mp.cost / mp.plan).toFixed(1)}× your $${mp.plan} ${planName} this month` : (mp.pace ? `on pace for ${usd(mp.pace)} this month` : '');
  const T = [
    ['Spend (API-equivalent)', usd(cost), [delta(cost, pcost), planLine].filter(Boolean).join(' · ')],
    ['Prompts', prompts.toLocaleString(), delta(prompts, pprompts)],
    ['Per prompt', prompts ? usd(cost / prompts) : '—', prompts ? `${(calls / prompts).toFixed(0)} agent responses on average` : ''],
    V.group === 'claude' ? ['Claude 5-hour quota used', pct(qc), 'in 5-hour windows, estimated']
      : V.group === 'openai' ? ['Codex 5-hour quota used', pct(qx), 'in 5-hour windows']
      : ['5-hour quota used', `${pct(qc)} · ${pct(qx)}`, 'Claude (est.) · Codex, in 5-hour windows'],
  ];
  if (S.adv) {
    T.push(['Tokens', tok(tokens), `${tok(sum(rows, f => f.tout))} output`]);
    T.push(['Cache reuse', inTok ? Math.round(sum(rows, f => f.tcr) / inTok * 100) + '%' : '—', 'input served from cache (cheaper)']);
  }
  $('#tiles').innerHTML = T.map(([k, v, d]) => `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div><div class="d">${d || '&nbsp;'}</div></div>`).join('');
}

// ── coach ─────────────────────────────────────────────────────────────────
const pctConf = c => Math.round(c * 100) + '%';
const scopeLabel = l => (l.scope === 'global' ? 'all projects' : l.scope) + ' · ' + ({claude:'Claude', codex:'Codex', both:'Claude + Codex'}[l.tools]);
const fileList = files => files && files.length ? files.map(f => f.replace(/^\/Users\/[^/]+/, '~')).join(', ') : 'no project folder found';
function impactLine(l) {
  const im = l.impact; if (!im) return '';
  if (!im.ready) return `<div class="impact">Measuring: ${im.after.prompts}/${im.needed} prompts since applied</div>`;
  const lab = {cost_per_prompt:'$ per prompt', responses_per_prompt:'responses per prompt', peak_context:'peak context', session_length:'session length', quota_per_prompt:'quota per prompt'};
  const parts = Object.entries(im.changes).filter(([k]) => lab[k]).map(([k, v]) => `${lab[k]} <b>${v <= 0 ? '▼' : '▲'} ${Math.abs(Math.round(v * 100))}%</b>`);
  return `<div class="impact">Before → after (${im.before.prompts} → ${im.after.prompts} prompts): ${parts.join(' · ') || 'no change yet'}</div>`;
}
function lessonRow(l) {
  const conf = `<span class="pill ${l.status === 'ready' ? 'ready' : ''}">${l.status === 'applied' ? 'applied' : pctConf(l.confidence) + ' confident'}</span>`;
  let acts = '';
  if (l.status === 'ready') acts = `<button class="btn primary" data-act="apply" data-id="${l.id}">Apply</button><button class="btn" data-act="dismiss" data-id="${l.id}">Dismiss</button>`;
  else if (l.status === 'review') acts = `<button class="btn" data-act="apply-confirm" data-id="${l.id}">Apply anyway</button><button class="btn" data-act="dismiss" data-id="${l.id}">Dismiss</button>`;
  else if (l.status === 'applied') acts = `<button class="btn" data-act="unapply" data-id="${l.id}">Remove</button>`;
  const files = l.status === 'applied' ? `Written to ${esc(fileList(l.files))}` : l.status === 'collecting' ? `Needs about ${l.needed} sessions of evidence (${l.evidence_n} so far)` : `Would be written to ${esc(fileList(l.files))}`;
  return `<div class="lesson"><div class="body"><div class="t">${esc(l.title)}${conf}</div>
    <div class="r">“${esc(l.rule)}”</div>
    <div class="e">${esc(l.evidence)} · ${esc(scopeLabel(l))}${l.saving ? ' · ' + esc(l.saving) : ''}<br>${files}</div>${impactLine(l)}</div>
    <div class="acts">${acts}</div></div>`;
}
function coach() {
  const L = C.lessons, by = s => L.filter(l => l.status === s);
  const ready = by('ready'), review = by('review'), applied = by('applied'), collecting = by('collecting');
  const el = $('#coach');
  let h = '';
  if (ready.length) h += `<div class="cardhead"><span class="sect" style="margin:0">Ready to apply — ${Math.round(C.ready_threshold * 100)}%+ confident</span>${ready.length > 1 ? `<button class="btn primary" data-act="apply-ready">Apply all ${ready.length}</button>` : ''}</div>` + ready.map(lessonRow).join('');
  if (review.length) h += `<div class="sect">Needs your call — some evidence, not yet ${Math.round(C.ready_threshold * 100)}%</div>` + review.map(lessonRow).join('');
  if (applied.length) h += `<div class="sect">Applied — before / after</div>` + applied.map(lessonRow).join('');
  if (collecting.length) h += `<details class="adv"><summary class="sect" style="display:list-item">Watching ${collecting.length} more pattern${collecting.length > 1 ? 's' : ''} (collecting data)</summary>${collecting.map(lessonRow).join('')}</details>`;
  if (!h) h = `<div class="empty">No lessons yet. They appear as patterns repeat across sessions; <b>Analyze</b> looks deeper at your costliest prompts.</div>`;
  const nk = C.nudges.by_kind || {}, total = Object.values(nk).reduce((a, b) => a + b, 0);
  const kinds = Object.entries(nk).sort((a, b) => b[1] - a[1]).map(([k, n]) => `${n} ${k}`).join(' · ');
  const follow = C.nudges.context_total ? ` · you started fresh after ${C.nudges.context_followed}/${C.nudges.context_total} context nudges` : '';
  h += `<div class="nudgebar"><span>${D.nudges_on ? `<b>Nudges on</b> in Claude Code · ${total} in 30 days${kinds ? ' (' + kinds + ')' : ''}${follow}` : '<b>Nudges are off.</b> TokenCoach can warn you in Claude Code before an expensive prompt.'}</span>
    <button class="btn ${D.nudges_on ? '' : 'primary'}" data-act="nudges" data-on="${D.nudges_on ? 0 : 1}">${D.nudges_on ? 'Turn off' : 'Turn on nudges'}</button></div>`;
  el.innerHTML = h;
  $('#analyze-meta').textContent = D.last_analysis ? `last run ${D.last_analysis}` : 'never run';
}
document.addEventListener('click', async e => {
  const b = e.target.closest('[data-act]'); if (!b) return;
  const act = b.dataset.act, id = b.dataset.id;
  if (act === 'apply' || act === 'apply-confirm') {
    const l = C.lessons.find(x => x.id === id);
    if (act === 'apply-confirm' && !confirm(`Add this rule to ${fileList(l.files)}?\n\n“${l.rule}”`)) return;
    const r = await busy(b, 'Applying…', () => api('lesson/apply', {id, confirm: act === 'apply-confirm'}));
    if (r) { toast('Written to ' + fileList(r.files)); setTimeout(() => location.reload(), 900); }
  } else if (act === 'apply-ready') {
    const r = await busy(b, 'Applying…', () => api('lessons/apply-ready'));
    if (r) { toast('Written to ' + fileList(r.files)); setTimeout(() => location.reload(), 900); }
  } else if (act === 'unapply' || act === 'dismiss') {
    const r = await busy(b, '…', () => api(act === 'unapply' ? 'lesson/unapply' : 'lesson/dismiss', {id}));
    if (r) location.reload();
  } else if (act === 'nudges') {
    const r = await busy(b, '…', () => api('nudges', {on: b.dataset.on === '1'}));
    if (r) { toast(r.on ? 'Nudges on — you will see them in Claude Code.' : 'Nudges off.'); setTimeout(() => location.reload(), 700); }
  } else if (act === 'analyze') {
    toast('Analyzing your costliest prompts with Claude — about a minute…', 90000);
    const r = await busy(b, 'Analyzing…', () => api('analyze'));
    if (r) { toast('Done.'); setTimeout(() => location.reload(), 600); }
  } else if (act === 'improve' || act === 'improve-again') {
    const box = document.getElementById('imp-' + b.dataset.i);
    if (act === 'improve' && box.innerHTML) { box.innerHTML = ''; return; }
    const p = P[+b.dataset.i];
    const cached = act === 'improve' && C.improvements[p.id];
    const r = cached ? cached : await busy(b, 'Improving… (~30s)', () => api('improve', {prompt_id: p.id, force: act === 'improve-again'}));
    if (!r) return;
    C.improvements[p.id] = {rewrite: r.rewrite, why: r.why};
    box.innerHTML = improveBox(p, r);
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
    <button class="btn link" data-act="improve-again" data-i="${p.i}">Try again</button></div></div>`;
}
function templates() {
  const el = $('#templates-card');
  if (!C.templates.length) { el.style.display = 'none'; return; }
  el.style.display = '';
  $('#templates').innerHTML = C.templates.map(t => `<div class="lesson" style="border-top:1px solid var(--grid)"><div class="body"><div class="t">${esc(t.title)}</div>
    <details><summary class="e">Show</summary><pre class="prompt">${esc(t.text)}</pre></details></div>
    <div class="acts"><button class="btn" data-act="copy-template" data-id="${t.id}">Copy</button><button class="btn link" data-act="delete-template" data-id="${t.id}">Delete</button></div></div>`).join('');
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
function timeline(rows, lo, hi) {
  const M = METRICS[V.metric], B = buckets(lo, hi);
  const srcs = SRC.filter(s => rows.some(f => f.src === s.key));
  const val = B.map(([a, b]) => { const r = rows.filter(f => f.t >= a && f.t < b); return srcs.map(s => sum(r.filter(f => f.src === s.key), M.get)); });
  const top = Math.max(0, ...val.map(v => v.reduce((x, y) => x + y, 0)));
  $('#tl-title').textContent = `${M.label} over time`;
  $('#tl-legend').innerHTML = srcs.map(s => `<span><i style="background:var(--s${s.slot})"></i>${esc(s.label)}</span>`).join('');
  if (!top) { $('#timeline').innerHTML = `<div class="empty">No ${V.metric === 'cost' ? 'priced ' : ''}activity in this range.</div>`; return; }
  const W = Math.max(300, $('#timeline').clientWidth), H = 220, L = 52, BOT = 22, TOP = 6, ph = H - BOT - TOP, step = (W - L) / B.length, bw = Math.max(step - 2, 1);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(M.label)} over time">`;
  for (const fr of [0.5, 1]) { const y = TOP + ph * (1 - fr); s += `<line class="gridline" x1="${L}" x2="${W}" y1="${y}" y2="${y}"/><text x="${L - 6}" y="${y + 4}" text-anchor="end">${esc(M.fmt(top * fr))}</text>`; }
  s += `<line class="gridline" x1="${L}" x2="${W}" y1="${TOP + ph}" y2="${TOP + ph}"/>`;
  const every = Math.max(1, Math.ceil(B.length / Math.max(2, Math.floor((W - L) / 70))));
  B.forEach(([a, b, label], i) => {
    const x = L + i * step + 1; let y = TOP + ph;
    s += `<g class="bucket" data-i="${i}">`;
    const segs = val[i].map((v, k) => [v, k]).filter(([v]) => v > 0);
    segs.forEach(([v, k], j) => {
      const h = ph * v / top; y -= h;
      const isTop = j === segs.length - 1, hh = Math.max(h - (j > 0 ? 2 : 0), 0.5);
      const r = isTop ? Math.min(4, bw / 2, hh) : 0, fill = `var(--s${srcs[k].slot})`;
      s += r > 0 ? `<path d="M${x},${y + hh} L${x},${y + r} Q${x},${y} ${x + r},${y} L${x + bw - r},${y} Q${x + bw},${y} ${x + bw},${y + r} L${x + bw},${y + hh} Z" fill="${fill}"/>`
                 : `<rect x="${x}" y="${y}" width="${bw}" height="${hh}" fill="${fill}"/>`;
    });
    s += `<rect class="hit" x="${L + i * step}" y="${TOP}" width="${step}" height="${ph}"/></g>`;
    if (i % every === 0) s += `<text x="${x + bw / 2}" y="${H - 6}" text-anchor="middle">${esc(label)}</text>`;
  });
  const el = $('#timeline'); el.innerHTML = s + '</svg>';
  el.querySelectorAll('.bucket').forEach(g => {
    const i = +g.dataset.i;
    g.onmousemove = e => showTip(e, `<b>${esc(B[i][2])}</b>` + srcs.map((sr, k) => val[i][k] ? `<div class="row"><span><span class="dot" style="background:var(--s${sr.slot})"></span>${esc(sr.label)}</span><span>${esc(M.fmt(val[i][k]))}</span></div>` : '').join('') + `<div class="row"><span>Total</span><b>${esc(M.fmt(val[i].reduce((p, q) => p + q, 0)))}</b></div>`);
    g.onmouseleave = hideTip;
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
    const k = keyOf(f); if (!g.has(k)) g.set(k, {k, v: 0, cost: 0, priced: false, prompts: 0, tok: 0, q: 0});
    const a = g.get(k); a.v += M.get(f); a.cost += f.cost || 0; a.priced ||= f.cost != null; a.prompts += f.first ? 1 : 0;
    a.tok += f.tin + f.tout + f.tcw + f.tcr; a.q += f.q5 || 0;
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
    const k = f.p.sess; if (!g.has(k)) g.set(k, {src: f.src, proj: f.proj, t0: f.t, t1: f.t, v: 0, cost: 0, priced: false, prompts: new Set(), calls: 0, ctx: 0, q: 0});
    const a = g.get(k); a.t0 = Math.min(a.t0, f.t); a.t1 = Math.max(a.t1, f.t); a.v += M.get(f); a.cost += f.cost || 0;
    a.priced ||= f.cost != null; if (f.first) a.prompts.add(f.p); a.calls += f.calls; a.ctx = Math.max(a.ctx, f.ctx); a.q += f.q5 || 0;
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

// ── prompts (simple: top 5 · advanced: searchable list) ──────────────────
let promptLimit = 30;
function promptAgg(rows) {
  const g = new Map();
  for (const f of rows) {
    if (!g.has(f.p)) g.set(f.p, {p: f.p, cost: 0, priced: false, tok: 0, calls: 0, ctx: 0, q: 0, models: new Set()});
    const a = g.get(f.p); a.cost += f.cost || 0; a.priced ||= f.cost != null; a.tok += f.tin + f.tout + f.tcw + f.tcr;
    a.calls += f.calls; a.ctx = Math.max(a.ctx, f.ctx); a.q += f.q5 || 0; a.models.add(f.model);
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
  $('#top').innerHTML = list.length ? `<table><tr><th>When</th><th>Prompt</th><th class="n">Responses</th><th class="n">$ / quota</th><th></th></tr>${promptRows(list, false)}</table>`
    : '<div class="empty">No prompts in this range.</div>';
}
function prompts(rows) {
  const q = S.q.trim().toLowerCase();
  let list = promptAgg(rows).filter(a => !q || a.p.text.toLowerCase().includes(q));
  const key = {cost: a => a.cost + a.tok / 1e9, tokens: a => a.tok, recent: a => a.p.t, quota: a => a.q}[S.sort];
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
  controls(lo, hi); tiles(rows, prev); coach(); timeline(rows, lo, hi); topPrompts(rows); templates();
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
render();
const age = Math.round((Date.now() / 1000 - D.generated) / 60);
$('#updated').textContent = `updated ${when(D.generated)}` + (!D.live && age > 20 ? ` · ${age} min ago` : '') + (D.live ? '' : ' · read-only copy');
let rz; addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(render, 150); });
// Pick up fresh data every 5 minutes (state persists), unless the person is mid-action.
setInterval(() => { if (!document.querySelector('button[disabled]') && !document.querySelector('.improve')) location.reload(); }, 5 * 60 * 1000);
"""

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TokenCoach</title><style>{css}{dcss}</style></head>
<body><main>
<header><div class="brand"><h1>TokenCoach</h1><span class="sub" style="margin:0">Claude Code · Cowork · Codex{chat} · <span id="updated"></span></span></div></header>
<div class="controls">
  <span class="seg" id="range"></span>
  <span class="seg" id="group" aria-label="Provider"></span>
  <select id="f-source" class="adv" aria-label="Tool"></select>
  <select id="f-project" class="adv" aria-label="Project"></select>
  <select id="f-model" class="adv" aria-label="Model"></select>
  <button class="btn link adv" id="clear">Clear filters</button>
  <span class="spacer"></span>
  <span class="switch" id="adv" role="switch" tabindex="0"><i></i>Advanced</span>
</div>
<div class="tiles" id="tiles"></div>
<div class="card coach"><div class="cardhead"><h2>Coach</h2>
  <span><span class="note" id="analyze-meta" style="margin-right:8px"></span><button class="btn" data-act="analyze">Analyze deeper</button></span></div>
  <div id="coach"></div></div>
<div class="card chart"><div class="cardhead"><h2 id="tl-title"></h2><span class="seg adv" id="metric"></span></div>
  <div class="legend" id="tl-legend"></div><div id="timeline"></div></div>
<div class="card scroll"><div class="cardhead"><h2>Costliest prompts</h2><span class="note" style="margin:0">Improve suggests a tighter version you can copy</span></div><div id="top"></div></div>
<div class="card" id="templates-card" style="display:none"><h2>Your prompt templates</h2><div id="templates"></div></div>
<div class="grid2 adv">
  <div class="card chart"><h2 id="q-title">Quota used</h2><div class="legend" id="q-legend"></div><div id="quota"></div>
    <p class="note">Claude from TokenCoach's readings (estimated); Codex from its own reading after each response. Separate plans.</p></div>
  <div class="card chart"><h2>When you work</h2><div id="heat"></div><p class="note">Selected measure by weekday and hour, local time.</p></div>
</div>
<div class="grid2 adv">
  <div class="card scroll"><h2>By project</h2><div id="by-project"></div></div>
  <div class="card scroll"><h2>By model</h2><div id="by-model"></div></div>
</div>
<div class="card scroll adv"><h2>By tool</h2><div id="by-source"></div><p class="note">Click a row in any table to filter the page.</p></div>
<div class="card scroll adv"><h2>Costliest sessions</h2><div id="sessions"></div></div>
<div class="card scroll adv"><div class="cardhead"><h2>All prompts <span class="sub" id="p-count"></span></h2>
  <span><input type="search" id="search" placeholder="Search prompts" aria-label="Search prompts">
  <select id="sort" aria-label="Sort prompts"><option value="cost">Most expensive</option><option value="tokens">Most tokens</option>
  <option value="quota">Most quota</option><option value="recent">Most recent</option></select></span></div>
  <div id="prompts"></div><button class="btn link more" id="p-more">Show more</button></div>
<div class="adv">{advice}</div>
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
               SUM(quota_5h_pct) q5, SUM(quota_week_pct) qw,
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
        ])

    quota = {}
    for prov in ("claude", "codex"):
        quota[prov] = [[round(t, 1), p] for t, p in conn.execute(
            "SELECT ts, pct FROM quota_samples WHERE provider=? AND window='5h' AND ts >= ? ORDER BY ts",
            (prov, since))]

    present = {p[2] for p in prompts}
    sources = [{"key": k, "label": SOURCE_LABELS[k], "slot": i + 1}
               for i, k in enumerate(SOURCE_ORDER)]
    from aiquotabar import coach, nudge
    try:
        coach_data = coach.coach_snapshot(conn)
    except Exception:
        log.exception("coach snapshot failed")
        coach_data = None
    advice = sorted(glob.glob(os.path.join(REPORT_DIR, "optimizer-*.md")))
    last_analysis = None
    if advice:
        last_analysis = datetime.fromtimestamp(os.path.getmtime(advice[-1])).strftime("%b %d, %H:%M")
    return {
        "generated": round(datetime.now().timestamp()),
        "sources": sources,
        "provider": {k: ("claude" if v == "claude" else "codex") for k, v in ledger.SOURCE_PROVIDER.items()},
        "models": models, "prompts": prompts, "facts": facts, "quota": quota,
        "plans": config.get("ledger_plans") or {},
        "has_chat": bool(present & {"claude_chat", "chatgpt_chat"}),
        "coach": coach_data, "nudges_on": nudge.is_installed(), "last_analysis": last_analysis,
        "equivalents": {m: ledger.equivalent_model(m, ledger.ledger_overrides(config))
                        for m in models if ledger.equivalent_model(m, ledger.ledger_overrides(config))
                        and not _has_exact_price(m, config)},
    }


def _has_exact_price(model: str, config: dict) -> bool:
    prices = config.get("ledger_prices") or {}
    return any(model.startswith(k) for k in prices)


def _latest_advice() -> str:
    """The newest Analyze report, rendered, for the advanced view."""
    files = sorted(glob.glob(os.path.join(REPORT_DIR, "optimizer-*.md")))
    if not files:
        return ""
    from aiquotabar.optimizer import markdown_to_html
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
                    "~/.claude_bar_config.json.")
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return PAGE.format(
        css=CSS, dcss=DASHBOARD_CSS, js=DASHBOARD_JS, data=blob,
        chat=" · chat imports" if data["has_chat"] else "",
        advice=_latest_advice(), unpriced=html.escape(unpriced),
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
