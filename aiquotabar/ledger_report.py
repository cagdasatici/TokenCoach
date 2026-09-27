"""Usage dashboard: one self-contained HTML file built from the ledger.

No server. The page embeds its data as JSON and does all filtering in the
browser. The app rewrites it after every ledger pass, and the open page reloads
itself every few minutes, keeping its filters.
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
header { display:flex; justify-content:space-between; align-items:flex-end; gap:12px; flex-wrap:wrap; }
.controls { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:0 0 16px;
  position:sticky; top:0; z-index:5; background:var(--surface-0); padding:10px 0; }
.seg { display:inline-flex; border:1px solid var(--border); border-radius:8px; overflow:hidden; }
.seg button { border:0; background:var(--surface-1); color:var(--text-secondary); padding:6px 11px;
  font:inherit; font-size:13px; cursor:pointer; border-right:1px solid var(--border); }
.seg button:last-child { border-right:0; }
.seg button.on { background:var(--text-primary); color:var(--surface-1); }
select, input[type=search] { font:inherit; font-size:13px; padding:6px 8px; border-radius:8px;
  border:1px solid var(--border); background:var(--surface-1); color:var(--text-primary); max-width:220px; }
.clear { font-size:12px; color:var(--accent); cursor:pointer; background:none; border:0; }
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:16px; }
.tile { background:var(--surface-1); border:1px solid var(--border); border-radius:10px; padding:12px 14px; }
.tile .k { color:var(--text-secondary); font-size:12px; }
.tile .v { font-size:22px; font-weight:600; margin-top:2px; font-variant-numeric:tabular-nums; }
.tile .d { color:var(--text-muted); font-size:12px; }
.up { color:var(--text-secondary); } .down { color:var(--text-secondary); }
.grid2 { display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:16px; }
.legend { display:flex; flex-wrap:wrap; gap:12px; font-size:12px; color:var(--text-secondary); margin:0 0 8px; }
.legend i { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:5px; vertical-align:-1px; }
.chart svg { display:block; width:100%; height:auto; overflow:visible; }
.chart text { font-size:11px; }
.chart text { fill:var(--text-muted); font-size:10px; }
.gridline { stroke:var(--grid); stroke-width:1; }
.hit { fill:transparent; }
.hit:hover + g rect, .bucket:hover rect { opacity:.8; }
#tip { position:fixed; pointer-events:none; background:var(--surface-1); border:1px solid var(--border);
  border-radius:8px; padding:8px 10px; font-size:12px; box-shadow:0 4px 16px rgba(0,0,0,.18);
  display:none; z-index:20; max-width:320px; }
#tip b { font-weight:600; } #tip .row { display:flex; justify-content:space-between; gap:16px; }
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
.empty { color:var(--text-muted); padding:24px 0; text-align:center; }
.advice h2 { margin-top:14px; } .advice li { margin:3px 0; }
.advice pre { white-space:pre-wrap; background:var(--surface-0); padding:8px; border-radius:6px; }
.more { margin-top:8px; font-size:13px; color:var(--accent); cursor:pointer; background:none; border:0; padding:0; }
@media (max-width:600px) { .barcell { display:none; } }
"""

DASHBOARD_JS = r"""
const D = JSON.parse(document.getElementById('data').textContent);
const SRC = D.sources;                         // [{key,label,slot}]
const SRC_BY = Object.fromEntries(SRC.map(s => [s.key, s]));
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const usd = v => v == null ? '—' : v >= 100 ? '$' + Math.round(v).toLocaleString() : v >= 1 ? '$' + v.toFixed(2) : '$' + v.toFixed(3);
const tok = n => { n = n || 0; return n >= 1e9 ? (n/1e9).toFixed(1)+'B' : n >= 1e6 ? (n/1e6).toFixed(1)+'M' : n >= 1e3 ? Math.round(n/1e3)+'k' : String(Math.round(n)); };
const pct = v => v == null ? '—' : (v >= 10 ? Math.round(v) : v.toFixed(1)) + '%';
const METRICS = {
  cost:    {label:'API-equivalent $', fmt: usd, get: f => f.cost || 0},
  tokens:  {label:'Tokens', fmt: tok, get: f => f.tin + f.tout + f.tcw + f.tcr},
  prompts: {label:'Prompts', fmt: v => Math.round(v).toLocaleString(), get: f => f.first ? 1 : 0},
  quota:   {label:'5h quota %', fmt: pct, get: f => f.q5 || 0},
};
const RANGES = {today:'Today', '7d':'7 days', '30d':'30 days', '90d':'90 days', all:'All'};
const DAY = 86400;

// ── state (kept across the page's auto-reload) ─────────────────────────────
const DEFAULT = {range:'30d', metric:'cost', source:'', project:'', model:'', q:'', sort:'cost'};
let S = {...DEFAULT};
try { Object.assign(S, JSON.parse(localStorage.getItem('aql-dash') || '{}')); } catch (e) {}
const save = () => { try { localStorage.setItem('aql-dash', JSON.stringify(S)); } catch (e) {} };

// ── data: facts = one row per (prompt, model) ─────────────────────────────
const P = D.prompts.map((p, i) => ({i, id: p[0], t: p[1], src: p[2], proj: p[3], sess: p[4], text: p[5], est: p[6], trunc: p[7]}));
const F = D.facts.map(r => ({p: P[r[0]], model: D.models[r[1]], calls: r[2], cost: r[3], tin: r[4], tout: r[5],
  tcw: r[6], tcr: r[7], q5: r[8], qw: r[9], ctx: r[10], t: r[11], first: r[12]}));
F.forEach(f => { f.src = f.p.src; f.proj = f.p.proj; });

function startOfDay(ts) { const d = new Date(ts * 1000); d.setHours(0,0,0,0); return d.getTime() / 1000; }
function rangeBounds(r) {
  const now = D.generated, today = startOfDay(now);
  if (r === 'today') return [today, now + 1];
  if (r === 'all') return [Math.min(...F.map(f => f.t), now), now + 1];
  const n = {'7d':7, '30d':30, '90d':90}[r];
  return [today - (n - 1) * DAY, now + 1];
}
function filtered(lo, hi, ignore) {
  return F.filter(f => f.t >= lo && f.t < hi
    && (ignore === 'source' || !S.source || f.src === S.source)
    && (ignore === 'project' || !S.project || f.proj === S.project)
    && (ignore === 'model' || !S.model || f.model === S.model));
}
function sum(rows, get) { let s = 0; for (const r of rows) s += get(r); return s; }

// ── tooltip ───────────────────────────────────────────────────────────────
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

// ── controls ──────────────────────────────────────────────────────────────
function seg(el, opts, key) {
  el.innerHTML = Object.entries(opts).map(([k, v]) => `<button data-k="${k}" class="${S[key] === k ? 'on' : ''}">${v}</button>`).join('');
  el.onclick = e => { const k = e.target.dataset.k; if (!k) return; S[key] = k; save(); render(); };
}
function fillSelect(el, key, values, label, fmt) {
  const cur = S[key];
  el.innerHTML = `<option value="">${label}</option>` + values.map(v => `<option value="${esc(v)}" ${v === cur ? 'selected' : ''}>${esc(fmt ? fmt(v) : v)}</option>`).join('');
  el.onchange = () => { S[key] = el.value; save(); render(); };
}
function controls(lo, hi) {
  seg($('#range'), RANGES, 'range');
  seg($('#metric'), Object.fromEntries(Object.entries(METRICS).map(([k, m]) => [k, m.label])), 'metric');
  const inRange = F.filter(f => f.t >= lo && f.t < hi);
  const uniq = (get, by) => { const m = new Map(); for (const f of inRange) m.set(get(f), (m.get(get(f)) || 0) + by(f)); return [...m.entries()].sort((a, b) => b[1] - a[1]).map(e => e[0]); };
  const w = f => (f.cost || 0) + (f.tin + f.tout + f.tcr) / 1e7;
  fillSelect($('#f-source'), 'source', SRC.map(s => s.key).filter(k => inRange.some(f => f.src === k) || k === S.source), 'All tools', k => SRC_BY[k].label);
  fillSelect($('#f-project'), 'project', uniq(f => f.proj, w), 'All projects');
  fillSelect($('#f-model'), 'model', uniq(f => f.model, w), 'All models');
  $('#clear').style.display = (S.source || S.project || S.model || S.q) ? '' : 'none';
}

// ── KPI tiles ─────────────────────────────────────────────────────────────
function tiles(rows, prev) {
  const cost = sum(rows, f => f.cost || 0), pcost = sum(prev, f => f.cost || 0);
  const prompts = sum(rows, f => f.first ? 1 : 0), pprompts = sum(prev, f => f.first ? 1 : 0);
  const calls = sum(rows, f => f.calls);
  const inTok = sum(rows, f => f.tin + f.tcw + f.tcr), tokens = inTok + sum(rows, f => f.tout);
  const reuse = inTok ? sum(rows, f => f.tcr) / inTok * 100 : null;
  const unpriced = rows.some(f => f.cost == null && !f.p.est);
  const qc = sum(rows.filter(f => D.provider[f.src] === 'claude'), f => f.q5 || 0);
  const qx = sum(rows.filter(f => D.provider[f.src] === 'codex'), f => f.q5 || 0);
  const delta = (a, b) => b > 0 ? `${a >= b ? '▲' : '▼'} ${Math.abs(Math.round((a - b) / b * 100))}% vs previous` : 'no previous data';
  const T = [
    ['API-equivalent $', usd(cost), (unpriced ? 'priced models only · ' : '') + delta(cost, pcost)],
    ['Prompts', prompts.toLocaleString(), delta(prompts, pprompts)],
    ['$ per prompt', prompts ? usd(cost / prompts) : '—', `${calls.toLocaleString()} responses · ${prompts ? (calls / prompts).toFixed(1) : 0} per prompt`],
    ['Tokens', tok(tokens), `${tok(sum(rows, f => f.tout))} output`],
    ['Cache reuse', reuse == null ? '—' : Math.round(reuse) + '%', 'input served from cache (cheaper)'],
    ['Claude 5h quota', pct(qc), 'of one 5-hour window, estimated'],
    ['Codex 5h quota', pct(qx), 'of one 5-hour window'],
  ];
  $('#tiles').innerHTML = T.map(([k, v, d]) => `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div><div class="d">${d}</div></div>`).join('');
}

function budget() {
  const plans = D.plans || {};
  const el = $('#budget');
  const now = new Date(D.generated * 1000);
  const mStart = new Date(now.getFullYear(), now.getMonth(), 1).getTime() / 1000;
  const mEnd = new Date(now.getFullYear(), now.getMonth() + 1, 1).getTime() / 1000;
  const frac = (D.generated - mStart) / (mEnd - mStart);
  const mtd = F.filter(f => f.t >= mStart && !f.p.est);
  const out = [];
  for (const [prov, label] of [['claude', 'Claude'], ['codex', 'ChatGPT / Codex']]) {
    const rows = mtd.filter(f => D.provider[f.src] === prov);
    if (!rows.length) continue;
    const cost = sum(rows, f => f.cost || 0), plan = plans[prov === 'codex' ? 'chatgpt' : 'claude'];
    const priced = rows.some(f => f.cost != null);
    const proj = frac > 0.02 ? cost / frac : null;
    let v, d;
    if (plan && priced) { v = (cost / plan).toFixed(1) + '× plan'; d = `${usd(cost)} API-equivalent this month vs ${usd(plan)} plan · on pace for ${usd(proj)}`; }
    else if (priced) { v = usd(cost); d = `API-equivalent this month · on pace for ${usd(proj)} · set your plan price in the menu bar ⚙ → Set Plan Prices`; }
    else { v = pct(sum(rows, f => f.q5 || 0)); d = 'of a 5-hour window used this month · add model prices to see $'; }
    out.push(`<div class="tile"><div class="k">${label} · this month</div><div class="v">${v}</div><div class="d">${d}</div></div>`);
  }
  el.innerHTML = out.join('');
  el.style.display = out.length ? '' : 'none';
}

// ── timeline: stacked columns by tool ────────────────────────────────────
function buckets(lo, hi) {
  const span = hi - lo;
  if (S.range === 'today') { const b = []; for (let t = lo; t < lo + DAY; t += 3600) b.push([t, t + 3600, new Date(t * 1000).getHours() + ':00']); return b; }
  const weekly = span > 120 * DAY, step = weekly ? 7 * DAY : DAY, b = [];
  let t = startOfDay(lo);
  while (t < hi) {
    const next = weekly ? t + step : startOfDay(t + DAY + 7200);
    const d = new Date(t * 1000);
    b.push([t, next, (weekly ? 'wk ' : '') + d.toLocaleDateString(undefined, {month:'short', day:'numeric'})]);
    t = next;
  }
  return b;
}
function timeline(rows, lo, hi) {
  const M = METRICS[S.metric], B = buckets(lo, hi);
  const srcs = SRC.filter(s => rows.some(f => f.src === s.key));
  const val = B.map(([a, b]) => { const r = rows.filter(f => f.t >= a && f.t < b); return srcs.map(s => sum(r.filter(f => f.src === s.key), M.get)); });
  const top = Math.max(0, ...val.map(v => v.reduce((x, y) => x + y, 0)));
  $('#tl-title').textContent = `${M.label} over time`;
  $('#tl-legend').innerHTML = srcs.map(s => `<span><i style="background:var(--s${s.slot})"></i>${esc(s.label)}</span>`).join('');
  if (!top) { $('#timeline').innerHTML = '<div class="empty">No activity in this range.</div>'; return; }
  const W = Math.max(300, $('#timeline').clientWidth), H = 240, L = 52, BOT = 22, TOP = 6, ph = H - BOT - TOP, step = (W - L) / B.length, bw = Math.max(step - 2, 1);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(M.label)} over time">`;
  for (const fr of [0.25, 0.5, 0.75, 1]) { const y = TOP + ph * (1 - fr); s += `<line class="gridline" x1="${L}" x2="${W}" y1="${y}" y2="${y}"/><text x="${L - 6}" y="${y + 3}" text-anchor="end">${esc(M.fmt(top * fr))}</text>`; }
  s += `<line class="gridline" x1="${L}" x2="${W}" y1="${TOP + ph}" y2="${TOP + ph}"/>`;
  const every = Math.max(1, Math.ceil(B.length / Math.max(2, Math.floor((W - L) / 70))));
  B.forEach(([a, b, label], i) => {
    const x = L + i * step + 1; let y = TOP + ph; const vs = val[i], tot = vs.reduce((p, q) => p + q, 0);
    s += `<g class="bucket" data-i="${i}">`;
    const segs = vs.map((v, k) => [v, k]).filter(([v]) => v > 0);
    segs.forEach(([v, k], j) => {
      // stack upward; a 2px surface gap separates segments; only the top is rounded
      const h = ph * v / top; y -= h;
      const isTop = j === segs.length - 1, hh = Math.max(h - (j > 0 ? 2 : 0), 0.5);
      const r = isTop ? Math.min(4, bw / 2, hh) : 0, fill = `var(--s${srcs[k].slot})`;
      s += r > 0
        ? `<path d="M${x},${y + hh} L${x},${y + r} Q${x},${y} ${x + r},${y} L${x + bw - r},${y} Q${x + bw},${y} ${x + bw},${y + r} L${x + bw},${y + hh} Z" fill="${fill}"/>`
        : `<rect x="${x}" y="${y}" width="${bw}" height="${hh}" fill="${fill}"/>`;
    });
    s += `<rect class="hit" x="${L + i * step}" y="${TOP}" width="${step}" height="${ph}"/></g>`;
    if (i % every === 0) s += `<text x="${x + bw / 2}" y="${H - 6}" text-anchor="middle">${esc(label)}</text>`;
  });
  s += '</svg>';
  const el = $('#timeline'); el.innerHTML = s;
  el.querySelectorAll('.bucket').forEach(g => {
    const i = +g.dataset.i;
    g.onmousemove = e => showTip(e, `<b>${esc(B[i][2])}</b>` + srcs.map((sr, k) => val[i][k] ? `<div class="row"><span><span class="dot" style="background:var(--s${sr.slot})"></span>${esc(sr.label)}</span><span>${esc(M.fmt(val[i][k]))}</span></div>` : '').join('') + `<div class="row"><span>Total</span><b>${esc(M.fmt(val[i].reduce((p, q) => p + q, 0)))}</b></div>`);
    g.onmouseleave = hideTip;
  });
}

// ── quota line chart ─────────────────────────────────────────────────────
function quotaChart(lo, hi) {
  const series = [['claude', 'Claude 5-hour', 1], ['codex', 'Codex 5-hour', 2]]
    .map(([k, label, slot]) => ({label, slot, pts: (D.quota[k] || []).filter(p => p[0] >= lo && p[0] < hi)}))
    .filter(s => s.pts.length);
  $('#q-title').textContent = ['today', '7d'].includes(S.range) ? 'Quota used (5-hour windows)' : 'Peak 5-hour quota used per ' + (hi - lo > 120 * DAY ? 'week' : 'day');
  $('#q-legend').innerHTML = series.map(s => `<span><i style="background:var(--s${s.slot})"></i>${s.label}</span>`).join('');
  if (!series.length) { $('#quota').innerHTML = '<div class="empty">No quota readings in this range.</div>'; return; }
  const W = Math.max(300, $('#quota').clientWidth), H = 200, L = 40, BOT = 22, TOP = 6, ph = H - BOT - TOP;
  const X = t => L + (t - lo) / (hi - lo) * (W - L), Y = v => TOP + ph * (1 - Math.min(v, 100) / 100);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Quota used over time">`;
  for (const v of [0, 50, 100]) s += `<line class="gridline" x1="${L}" x2="${W}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${L - 6}" y="${Y(v) + 3}" text-anchor="end">${v}%</text>`;
  const ticks = buckets(lo, hi), every = Math.max(1, Math.ceil(ticks.length / Math.max(2, Math.floor((W - L) / 80))));
  ticks.forEach(([a, , label], i) => { if (i % every === 0) s += `<text x="${X(a)}" y="${H - 6}" text-anchor="middle">${esc(label)}</text>`; });
  const peaks = !['today', '7d'].includes(S.range);
  if (peaks) {
    // long ranges: one point per bucket = the highest reading that day/week
    const B = buckets(lo, hi);
    for (const se of series) {
      se.peak = B.map(([a, b]) => { let m = null; for (const [t, v] of se.pts) if (t >= a && t < b) m = Math.max(m ?? 0, v); return [a + (b - a) / 2, m]; });
      let d = '';
      se.peak.forEach(([t, v], i) => { if (v == null) return; const prevV = i ? se.peak[i - 1][1] : null; d += `${prevV == null ? 'M' : ' L'}${X(t)},${Y(v)}`; });
      s += `<path d="${d}" fill="none" stroke="var(--s${se.slot})" stroke-width="2" stroke-linejoin="round"/>`;
      se.peak.forEach(([t, v]) => { if (v != null) s += `<circle cx="${X(t)}" cy="${Y(v)}" r="4" fill="var(--s${se.slot})" stroke="var(--surface-1)" stroke-width="2"/>`; });
    }
  }
  for (const se of peaks ? [] : series) {
    let d = '', prev = null;
    for (const [t, v] of se.pts) {
      if (prev && t - prev[0] > 6 * 3600) d += ` M${X(t)},${Y(v)}`;       // gap: no readings
      else d += prev ? ` L${X(t)},${Y(prev[1])} L${X(t)},${Y(v)}` : `M${X(t)},${Y(v)}`;
      prev = [t, v];
    }
    s += `<path d="${d}" fill="none" stroke="var(--s${se.slot})" stroke-width="2" stroke-linejoin="round"/>`;
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
      return best ? `<div class="row"><span><span class="dot" style="background:var(--s${se.slot})"></span>${se.label}</span><span>${pct(best[1])} ${peaks ? 'peak' : 'used'}</span></div>` : ''; });
    showTip(e, `<b>${new Date(t * 1000).toLocaleString(undefined, {weekday:'short', hour:'2-digit', minute:'2-digit', month:'short', day:'numeric'})}</b>${rows.join('')}`);
  };
  hit.onmouseleave = () => { cx.style.display = 'none'; hideTip(); };
}

// ── heatmap: weekday × hour ──────────────────────────────────────────────
function heatmap(rows) {
  const M = METRICS[S.metric], grid = Array.from({length: 7}, () => Array(24).fill(0));
  for (const f of rows) { const d = new Date(f.t * 1000); grid[(d.getDay() + 6) % 7][d.getHours()] += M.get(f); }
  const top = Math.max(...grid.flat());
  if (!top) { $('#heat').innerHTML = '<div class="empty">No activity in this range.</div>'; return; }
  const days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'], W = Math.max(300, $('#heat').clientWidth), L = 36, cw = (W - L) / 24, ch = 22, H = 7 * ch + 18;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Activity by weekday and hour">`;
  grid.forEach((row, r) => {
    s += `<text x="${L - 6}" y="${r * ch + ch / 2 + 3}" text-anchor="end">${days[r]}</text>`;
    row.forEach((v, h) => {
      const a = v ? 12 + 88 * v / top : 0;
      s += `<rect class="cell" data-r="${r}" data-h="${h}" x="${L + h * cw + 1}" y="${r * ch + 1}" width="${cw - 2}" height="${ch - 2}" rx="3" fill="${v ? `color-mix(in oklab, var(--s1) ${a.toFixed(0)}%, var(--surface-1))` : 'var(--surface-0)'}"/>`;
    });
  });
  for (let h = 0; h < 24; h += (W < 600 ? 6 : 3)) s += `<text x="${L + h * cw + cw / 2}" y="${H - 4}" text-anchor="middle">${h}:00</text>`;
  s += '</svg>';
  const el = $('#heat'); el.innerHTML = s;
  el.querySelectorAll('.cell').forEach(c => {
    c.onmousemove = e => showTip(e, `<b>${days[+c.dataset.r]} ${c.dataset.h}:00–${+c.dataset.h + 1}:00</b><div class="row"><span>${M.label}</span><span>${esc(M.fmt(grid[+c.dataset.r][+c.dataset.h]))}</span></div>`);
    c.onmouseleave = hideTip;
  });
}

// ── breakdown tables (click a row to filter) ─────────────────────────────
function breakdown(el, rows, keyOf, filterKey, labelOf, extra) {
  const M = METRICS[S.metric], g = new Map();
  for (const f of rows) {
    const k = keyOf(f); if (!g.has(k)) g.set(k, {k, v: 0, cost: 0, priced: false, prompts: 0, calls: 0, tok: 0, q: 0});
    const a = g.get(k); a.v += M.get(f); a.cost += f.cost || 0; a.priced ||= f.cost != null; a.prompts += f.first ? 1 : 0;
    a.calls += f.calls; a.tok += f.tin + f.tout + f.tcw + f.tcr; a.q += f.q5 || 0;
  }
  const list = [...g.values()].sort((a, b) => b.v - a.v || b.tok - a.tok).slice(0, 15), top = Math.max(0, ...list.map(a => a.v));
  if (!list.length) { el.innerHTML = '<div class="empty">No data.</div>'; return; }
  el.innerHTML = `<table><tr><th></th><th class="barcell">${M.label}</th><th class="n">$</th><th class="n">Prompts</th><th class="n">Tokens</th><th class="n">5h quota</th></tr>` +
    list.map(a => `<tr class="click" data-k="${esc(a.k)}"><td>${extra ? extra(a.k) : ''}${esc(labelOf ? labelOf(a.k) : a.k)}${S[filterKey] === a.k ? ' <span class="tag">filtered</span>' : ''}</td>
      <td class="barcell"><div class="bar" style="width:${top ? (100 * a.v / top).toFixed(1) : 0}%"></div></td>
      <td class="n">${a.priced ? usd(a.cost) : 'unpriced'}</td><td class="n">${a.prompts}</td><td class="n">${tok(a.tok)}</td><td class="n">${pct(a.q)}</td></tr>`).join('') + '</table>';
  el.querySelectorAll('tr.click').forEach(tr => tr.onclick = () => { S[filterKey] = S[filterKey] === tr.dataset.k ? '' : tr.dataset.k; save(); render(); });
}

// ── sessions ─────────────────────────────────────────────────────────────
function sessions(rows) {
  const M = METRICS[S.metric], g = new Map();
  for (const f of rows) {
    const k = f.p.sess; if (!g.has(k)) g.set(k, {k, src: f.src, proj: f.proj, t0: f.t, t1: f.t, v: 0, cost: 0, priced: false, prompts: new Set(), calls: 0, ctx: 0, q: 0});
    const a = g.get(k); a.t0 = Math.min(a.t0, f.t); a.t1 = Math.max(a.t1, f.t); a.v += M.get(f); a.cost += f.cost || 0;
    a.priced ||= f.cost != null; a.prompts.add(f.p); a.calls += f.calls; a.ctx = Math.max(a.ctx, f.ctx); a.q += f.q5 || 0;
  }
  const list = [...g.values()].sort((a, b) => b.v - a.v).slice(0, 30);
  if (!list.length) { $('#sessions').innerHTML = '<div class="empty">No sessions in this range.</div>'; return; }
  const dur = s => { const m = Math.round((s.t1 - s.t0) / 60); return m < 60 ? m + 'm' : (m / 60).toFixed(1) + 'h'; };
  $('#sessions').innerHTML = `<table><tr><th>Started</th><th>Session</th><th class="n">Prompts</th><th class="n">Responses</th><th class="n">Length</th><th class="n">Peak context</th><th class="n">$</th><th class="n">5h quota</th></tr>` +
    list.map(s => {
      const ps = [...s.prompts].sort((a, b) => a.t - b.t);
      const first = ps[0] ? ps[0].text.replace(/\s+/g, ' ').slice(0, 90) : '';
      return `<tr><td class="n">${new Date(s.t0 * 1000).toLocaleString(undefined, {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'})}</td>
      <td><span class="tag"><span class="dot" style="background:var(--s${SRC_BY[s.src].slot})"></span>${esc(SRC_BY[s.src].label)}</span><span class="tag">${esc(s.proj)}</span>
      <details><summary>${esc(first)}${first.length >= 90 ? '…' : ''}</summary><ol>${ps.map(p => `<li>${esc(p.text.replace(/\s+/g, ' ').slice(0, 160))}</li>`).join('')}</ol></details></td>
      <td class="n">${ps.length}</td><td class="n">${s.calls}</td><td class="n">${dur(s)}</td><td class="n">${tok(s.ctx)}</td>
      <td class="n">${s.priced ? usd(s.cost) : '—'}</td><td class="n">${pct(s.q)}</td></tr>`;
    }).join('') + '</table><p class="note">Peak context is the largest single request. Sessions whose context keeps growing re-read it on every response — a new session with a short brief is usually cheaper.</p>';
}

// ── prompts ──────────────────────────────────────────────────────────────
let promptLimit = 50;
function prompts(rows) {
  const g = new Map();
  for (const f of rows) {
    if (!g.has(f.p)) g.set(f.p, {p: f.p, cost: 0, priced: false, tok: 0, calls: 0, ctx: 0, q: 0, models: new Set()});
    const a = g.get(f.p); a.cost += f.cost || 0; a.priced ||= f.cost != null; a.tok += f.tin + f.tout + f.tcw + f.tcr;
    a.calls += f.calls; a.ctx = Math.max(a.ctx, f.ctx); a.q += f.q5 || 0; a.models.add(f.model);
  }
  const q = S.q.trim().toLowerCase();
  let list = [...g.values()].filter(a => !q || a.p.text.toLowerCase().includes(q));
  const key = {cost: a => a.cost + a.tok / 1e9, tokens: a => a.tok, recent: a => a.p.t, quota: a => a.q}[S.sort];
  list.sort((a, b) => key(b) - key(a));
  $('#p-count').textContent = `${list.length.toLocaleString()} prompts`;
  const shown = list.slice(0, promptLimit);
  $('#prompts').innerHTML = shown.length ? `<table><tr><th>When</th><th>Prompt</th><th class="n">Responses</th><th class="n">Tokens</th><th class="n">Peak context</th><th class="n">$</th><th class="n">5h quota</th></tr>` +
    shown.map(a => { const t = a.p.text.trim(), one = t.replace(/\s+/g, ' ');
      return `<tr><td class="n">${new Date(a.p.t * 1000).toLocaleString(undefined, {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'})}</td>
      <td><span class="tag"><span class="dot" style="background:var(--s${SRC_BY[a.p.src].slot})"></span>${esc(SRC_BY[a.p.src].label)}</span><span class="tag">${esc(a.p.proj)}</span>${[...a.models].map(m => `<span class="tag">${esc(m)}</span>`).join('')}${a.p.est ? '<span class="tag">estimated</span>' : ''}
      <details><summary>${esc(one.slice(0, 150))}${one.length > 150 ? '…' : ''}</summary><pre class="prompt">${esc(t)}${a.p.trunc ? '\n[… truncated in the dashboard; full text is in the ledger]' : ''}</pre></details></td>
      <td class="n">${a.calls}</td><td class="n">${tok(a.tok)}</td><td class="n">${tok(a.ctx)}</td><td class="n">${a.priced ? usd(a.cost) : '—'}</td><td class="n">${pct(a.q)}</td></tr>`; }).join('') + '</table>'
    : '<div class="empty">No prompts match.</div>';
  $('#p-more').style.display = list.length > promptLimit ? '' : 'none';
}

// ── render ───────────────────────────────────────────────────────────────
function render() {
  const [lo, hi] = rangeBounds(S.range), prevLo = lo - (hi - lo);
  controls(lo, hi);
  const rows = filtered(lo, hi), prev = filtered(prevLo, lo);
  tiles(rows, prev); budget(); timeline(rows, lo, hi); quotaChart(lo, hi); heatmap(rows);
  breakdown($('#by-project'), rows, f => f.proj, 'project');
  breakdown($('#by-model'), rows, f => f.model, 'model');
  breakdown($('#by-source'), rows, f => f.src, 'source', k => SRC_BY[k].label, k => `<span class="dot" style="background:var(--s${SRC_BY[k].slot})"></span>`);
  sessions(rows); prompts(rows);
}
$('#search').value = S.q;
$('#search').oninput = e => { S.q = e.target.value; save(); promptLimit = 50; prompts(filtered(...rangeBounds(S.range))); };
$('#sort').value = S.sort;
$('#sort').onchange = e => { S.sort = e.target.value; save(); prompts(filtered(...rangeBounds(S.range))); };
$('#p-more').onclick = () => { promptLimit += 100; prompts(filtered(...rangeBounds(S.range))); };
$('#clear').onclick = () => { S.source = S.project = S.model = S.q = ''; $('#search').value = ''; save(); render(); };
render();
const age = Math.round((Date.now() / 1000 - D.generated) / 60);
$('#updated').textContent = `Updated ${new Date(D.generated * 1000).toLocaleString(undefined, {hour:'2-digit', minute:'2-digit', month:'short', day:'numeric'})}` + (age > 20 ? ` · ${age} min ago — is AIQuotaLeft running?` : '');
// The app rewrites this file after each refresh; reload to pick it up (filters persist).
setTimeout(() => location.reload(), 5 * 60 * 1000);
let rz; addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(render, 150); });
"""

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Usage Dashboard</title><style>{css}{dcss}</style></head>
<body><main>
<header><div><h1>AI usage</h1>
<p class="sub">Claude Code · Cowork · Codex{chat} · <span id="updated"></span></p></div></header>
<div class="controls">
  <span class="seg" id="range"></span>
  <select id="f-source" aria-label="Tool"></select>
  <select id="f-project" aria-label="Project"></select>
  <select id="f-model" aria-label="Model"></select>
  <button class="clear" id="clear">Clear filters</button>
</div>
<div class="tiles" id="tiles"></div>
<div class="tiles" id="budget"></div>
<div class="card chart"><div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap">
  <h2 id="tl-title"></h2><span class="seg" id="metric"></span></div>
  <div class="legend" id="tl-legend"></div><div id="timeline"></div></div>
<div class="grid2">
  <div class="card chart"><h2 id="q-title">Quota used (5-hour windows)</h2><div class="legend" id="q-legend"></div><div id="quota"></div>
    <p class="note">Claude from AIQuotaLeft's readings; Codex from its own reading after each response. Separate plans.</p></div>
  <div class="card chart"><h2>When you work</h2><div id="heat"></div>
    <p class="note">Selected measure by weekday and hour, local time.</p></div>
</div>
<div class="grid2">
  <div class="card scroll"><h2>By project</h2><div id="by-project"></div></div>
  <div class="card scroll"><h2>By model</h2><div id="by-model"></div></div>
</div>
<div class="card scroll"><h2>By tool</h2><div id="by-source"></div>
  <p class="note">Click a row in any table to filter the whole page.</p></div>
<div class="card scroll"><h2>Most expensive sessions</h2><div id="sessions"></div></div>
<div class="card scroll"><div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
  <h2>Prompts <span class="sub" id="p-count"></span></h2>
  <span><input type="search" id="search" placeholder="Search prompts" aria-label="Search prompts">
  <select id="sort" aria-label="Sort prompts"><option value="cost">Most expensive</option><option value="tokens">Most tokens</option>
  <option value="quota">Most quota</option><option value="recent">Most recent</option></select></span></div>
  <div id="prompts"></div><button class="more" id="p-more">Show more</button></div>
{advice}
<p class="note">API-equivalent $ = what the same tokens would cost on the provider's API at list price. On a subscription you pay a flat fee; use it to compare prompts, projects and models. {unpriced}</p>
</main><div id="tip" role="tooltip"></div>
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
        FROM calls WHERE ts >= ?
        GROUP BY pid, model ORDER BY pid, t
        """, (since,)).fetchall()
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
    return {
        "generated": round(datetime.now().timestamp()),
        "sources": sources,
        "provider": {k: ("claude" if v == "claude" else "codex") for k, v in ledger.SOURCE_PROVIDER.items()},
        "models": models, "prompts": prompts, "facts": facts, "quota": quota,
        "plans": config.get("ledger_plans") or {},
        "has_chat": bool(present & {"claude_chat", "chatgpt_chat"}),
    }


def _latest_advice() -> str:
    """The newest optimizer report, rendered, for the dashboard's advice card."""
    files = sorted(glob.glob(os.path.join(REPORT_DIR, "optimizer-*.md")))
    if not files:
        return ('<div class="card"><h2>Advice</h2><p class="note">No analysis yet. Choose '
                '<b>Analyze My Usage…</b> from the menu bar ⚙ menu to get specific advice '
                'on cutting cost and quota use.</p></div>')
    from aiquotabar.optimizer import markdown_to_html
    path = files[-1]
    stamp = os.path.basename(path)[len("optimizer-"):-3]
    try:
        with open(path, encoding="utf-8") as f:
            body = markdown_to_html(f.read())
    except OSError:
        return ""
    return (f'<div class="card advice"><details><summary><h2 style="display:inline">'
            f'Latest advice · {html.escape(stamp)}</h2></summary>{body}</details>'
            f'<p class="note">Run <b>Analyze My Usage…</b> in the ⚙ menu for a fresh review; '
            f'it checks whether this advice was followed.</p></div>')


def build_report(conn, config: dict | None = None, days: int = DASHBOARD_DAYS) -> str:
    data = dashboard_data(conn, config, days)
    unpriced = ""
    if any(f[3] is None for f in data["facts"]):
        unpriced = ("Codex/OpenAI models have no bundled price; add them under \"ledger_prices\" "
                    "in ~/.claude_bar_config.json to include them in $.")
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return PAGE.format(
        css=CSS, dcss=DASHBOARD_CSS, js=DASHBOARD_JS, data=blob,
        chat=" · chat imports" if data["has_chat"] else "",
        advice=_latest_advice(), unpriced=html.escape(unpriced),
    )


def write_report(conn, config: dict | None = None, days: int = DASHBOARD_DAYS) -> str:
    os.makedirs(REPORT_DIR, exist_ok=True)
    tmp = REPORT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(build_report(conn, config, days))
    os.replace(tmp, REPORT_FILE)
    return REPORT_FILE


CHROME_APPS = ("Google Chrome", "Arc", "Brave Browser", "Microsoft Edge")


def open_file(path: str, browser: str | None = None):
    """Open in the chosen browser, else Chrome if installed, else the default."""
    for app in ([browser] if browser else []) + list(CHROME_APPS):
        if app and os.path.exists(f"/Applications/{app}.app"):
            try:
                subprocess.Popen(["open", "-a", app, path])
                return
            except OSError:
                log.debug("could not open with %s", app, exc_info=True)
    subprocess.Popen(["open", path])
