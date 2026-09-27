# Usage ledger, dashboard and prompt optimizer — design

Date: 2026-09-27. Status: implemented 2026-09-27 (all four phases).

## Goal

AIQuotaLeft shows how much quota is left. This adds *where it went*: per prompt,
session, project, model and tool, across Claude Code, Cowork and Codex, plus an
on-demand optimizer that reviews the most expensive sessions and suggests
cheaper habits and tighter prompts.

## Data sources (verified on this machine 2026-09-27)

| Source | Location | Per-message usage | Notes |
|---|---|---|---|
| Claude Code (CLI + desktop Code tab) | `~/.claude/projects/*/*.jsonl` | `message.usage`: input, output, cache create/read, thinking | `cwd`, `timestamp`, `message.model`, `message.id` per line |
| Cowork | `~/Library/Application Support/Claude/local-agent-mode-sessions/**/audit.jsonl` | Same shape as Claude Code | Assistant messages repeat per content block — dedupe on `message.id` |
| Codex (CLI + desktop) | `~/.codex/sessions/YYYY/MM/DD/*.jsonl` | `event_msg` `token_count.info.last_token_usage` | `session_meta.cwd`; `rate_limits.primary/secondary.used_percent` gives exact quota % per turn |
| claude.ai / chatgpt.com chat | not stored locally | — | Phase 2: import official data exports, token counts estimated and labelled as such |

## Components

1. **`aiquotabar/ledger.py`** — incremental ingester into `~/.ai-quota-bar/ledger.db`
   (SQLite). Remembers byte offset per file so each pass reads only new lines.
   Tables: `prompts` (user turn: session, source, project/cwd, timestamp, full
   prompt text), `calls` (per model response: model, token breakdown, API-equivalent
   USD, quota % delta where known), `ingest_state`.
   - Prompt text: stored in full (owner's choice). Local only; never logged,
     never sent anywhere except to the optimizer run the owner triggers.
   - Claude quota attribution: estimate by distributing each observed drop in the
     existing quota history samples across calls in that interval, weighted by
     cost. Labelled "est." in UI. Codex uses the exact `used_percent` deltas.
   - Pricing: a dated table in `ledger.py`, sourced from current provider pricing
     at implementation time, used only for "API-equivalent $".
   - Implementation note: quota attribution walks each used-% series against its
     running maximum; dips under 30 points are stale readings from parallel
     sessions, not resets (the first version counted them and overstated Codex
     usage roughly 2x).
2. **Menu additions** (`ui.py`) — one compact section: today's API-equivalent $,
   top project today, most expensive prompt today (truncated), and
   "Open usage report…" / "Analyze my usage…".
3. **Static dashboard** — `ledger_report.py` writes a self-contained HTML file
   (no server) and opens it: spend by day / project / model / tool, subscription
   value (plan $ vs API-equivalent $), top 50 prompts with drill-down to session.
4. **Optimizer — on demand only** (owner's choice; no background quota use).
   "Analyze my usage…" builds a compact digest of the top-N costly sessions
   (stats + prompt text, large tool outputs elided) and runs `claude -p` on a
   mid-tier model. Output: a dated Markdown/HTML report with habit findings
   (context bloat, long sessions, model overkill, repeated re-pastes) and concrete
   prompt rewrites. Previous reports are kept so the next run can say whether
   last time's advice was followed.

## Constraints kept

Remaining-quota display unchanged; no web server, no Electron; no credentials
touched; ingest must never block the menu refresh (runs on the existing
background timer, time-boxed); tests use fixture JSONL, not live logs.

## Phases

1. Ledger + fixtures/tests (Claude Code, Cowork, Codex parsers, dedupe, offsets).
2. Static dashboard + menu section.
3. On-demand optimizer.
4. Chat export import (estimates).
