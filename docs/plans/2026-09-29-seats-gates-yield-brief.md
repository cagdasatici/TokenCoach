# TokenCoach: Seats, Gates and Yield Metrics

**Handoff brief for implementation. Owner: Çağdaş Atıcı.**

## Context

Inspired by Curia (github.com/harrymunro/curia), a Claude Code harness that runs agents as persistent named roles ("seats") with enforced rules. The goal is not to replicate Curia. The goal is to adopt three patterns and use TokenCoach to prove whether each one earns its cost.

Current setup: Claude Code, Thin Harness / Fat Skills approach, AntiGravity investing dashboard as the dogfood repository, TokenCoach dashboard already implemented.

## Step 0: Verify before building

Confirm what TokenCoach ingests today:

- Per-session or aggregated data?
- Is `session_id` available as a key?
- Does it read Claude Code transcripts (JSONL) directly, or a derived usage export?

Everything below depends on one join key: **session_id → seat → commit**. If TokenCoach lacks session-level data, build that adapter first.

Hook behaviour below reflects the Claude Code hooks reference. Verify against the current docs before implementing: https://docs.claude.com/en/docs/claude-code/hooks

## Workstream 1: Role memory (seats)

**Problem:** Skills and CLAUDE.md give every session shared conventions, but no session knows what its role was doing or why. Every session starts with partial amnesia.

**Build:**

1. Seat folders: `.claude/seats/<seat>/ROLE.md` (references the role skill) and `.claude/seats/<seat>/HANDOFF.md`.
2. Launch convention: `SEAT=<seat> claude`. Default seat if unset: `general`.
3. **SessionStart hook:** read `ROLE.md` and `HANDOFF.md` for `$SEAT`; return them via `hookSpecificOutput.additionalContext`. Append `{session_id, seat, start_ts, cwd}` to `.claude/telemetry/seats.jsonl`. Write `session_id` to `.claude/current_session`.
4. **Stop hook:** Stop fires at the end of every turn, not every session. Block only when files changed after the last `HANDOFF.md` write. Return `decision: "block"` with a reason that instructs the agent to update the handoff. Exit immediately if `stop_hook_active` is true, to prevent loops.
5. Handoff template: Done / In progress / Why / Next / Open questions for Çağdaş.

**TokenCoach views:**

- Cost per seat
- Handoff compliance rate
- **Re-orientation cost:** tokens spent before the first Edit or Write tool call in a session

**Success criterion:** re-orientation cost falls measurably over two weeks versus the prior two-week baseline. If it does not, the handoff notes are decoration; simplify or drop.

## Workstream 2: Rules as enforced gates

**Problem:** Rules written in CLAUDE.md are requests, not checks.

**Build:** Convert the five rules that matter most into hooks. Candidates for AntiGravity:

| Rule ID | Rule | Gate |
|---|---|---|
| G1 | Never push to main | PreToolUse on Bash, pattern `git push.*main`, deny |
| G2 | No edits to secrets or config | PreToolUse on Edit/Write, path match, deny |
| G3 | No "done" with failing tests | Stop hook runs tests when diff is non-empty; block on failure |
| G4 | No new dependencies without approval | PreToolUse on `pip install` / `npm i`, deny |
| G5 | No inference-engine changes without a spec reference | PreToolUse on engine paths, deny unless a spec ID is present |

Every gate appends `{session_id, seat, rule_id, decision, ts}` to `.claude/telemetry/gates.jsonl`.

**TokenCoach views:**

- Fires per rule per week
- Recovery cost: tokens spent after a deny until the next successful action

**Decision rules:**

- A gate with zero fires in four weeks is demoted back to prose.
- A gate that fires constantly indicates a wrong skill or spec; fix the upstream instruction, not the fence.

## Workstream 3: Yield metrics

**Problem:** TokenCoach shows spend. It does not show what the spend produced.

**Build:**

1. Git `prepare-commit-msg` hook reads `.claude/current_session` and appends trailer `Claude-Session: <session_id>`.
2. TokenCoach joins session cost to commits via the trailer.

**Metrics:**

| Metric | Definition |
|---|---|
| Cost per accepted change | Session cost ÷ commits not reverted or rewritten within 7 days |
| Human attention per accepted change | User prompts per surviving commit (from transcript timestamps) |
| Rework rate | Share of commits followed within 7 days by a fix touching the same files |

**Cuts:** by seat, by model, by week.

**Uses:**

- **Model routing:** identify where Sonnet is sufficient and where Opus earns its price.
- **Scaling decision:** add parallelism or more seats only if cost per accepted change and rework rate hold or improve.
- **Work transfer:** once validated on AntiGravity, this metric set becomes a tested template for the AI-native SDLC team.

## Sequencing

1. Step 0 verification and session_id adapter, if needed
2. Workstream 3 telemetry (commit trailer and join): establishes the baseline before any change
3. Workstream 1 (seats)
4. Workstream 2 (gates)

Baseline first; otherwise no before/after comparison is possible.

## Out of scope

- Multi-account orchestration
- Overnight autonomous loops
- Porting Curia itself

## Constraints

- Mac, Claude Code, Python
- One session per git worktree (the commit trailer relies on this)
- Hooks are not a security boundary; treat them as guardrails with telemetry

---

## Status (2026-09-29)

**Done: Step 0 and Workstream 3 (yield metrics).** Code in `tokencoach/trailer.py` (git hook),
`tokencoach/yield_metrics.py` (scan, metrics), dashboard section "What it produced",
`tokencoach --yield-install | --yield | --yield-remove`. Not started: Workstreams 1 and 2.

**Step 0 answers.** TokenCoach ingests Claude Code transcripts (JSONL) directly, per call, with
`session_id` (the transcript's `sessionId`) and `cwd` on every prompt. Session-level data existed;
no adapter was needed. Missing today: tool-call records (needed for re-orientation cost, WS1).

**Where the build differs from the brief, and why**

- **Session id comes from the environment, not `.claude/current_session`.** Claude Code's Bash tool
  exports `CLAUDECODE=1` and `CLAUDE_CODE_SESSION_ID` (checked live: the value equals the
  transcript's `sessionId`, and a commit made from that shell got the matching trailer). A file goes
  stale after the session ends, so a later commit by hand would carry the wrong session; the
  environment cannot. It also removes the "one session per worktree" constraint. Only verified in
  the desktop app: confirm once in the terminal CLI (`git log -1 --format=%B` after a Claude commit).
  WS1's SessionStart hook can still write `.claude/current_session` for its own use.
- **Only the repository's own `.git/hooks` is used.** A `core.hooksPath` elsewhere (global, or
  tracked in the project) is refused, and a hook that isn't ours is never overwritten.
- **"Rewritten" ignores rebases and message-only amends** (same patch-id): the change lived on, so the
  old commit is set aside instead of counted twice. "Reverted" is read from `This reverts commit`.
- **Sessions before a repository was registered are not judged.** They could never have been tagged, so
  counting them as "made no commit" would inflate cost per change during the baseline
  (`yield_repos.since`). A repository reached from several worktrees, or with its git folder elsewhere,
  is one repository (`yield_repos.git_dir`).
- **Metrics only judge settled sessions** (everything, including commits, at least 7 days old), so the
  first numbers appear a week after the first tagged commit.
- **Cuts by seat are not built** (no seats yet). Add a `seat` attribute to the session rows in
  `yield_metrics.snapshot` when `.claude/telemetry/seats.jsonl` exists.

**Known limits.** Squash-merge then branch deletion counts as dropped. Rework flags every recent commit
touching a file that a later fix touched. Both are stated in the dashboard and README.

**Next, in the brief's order.** Let the baseline run for two weeks before WS1 changes anything, then
seats (needs tool-call ingestion for re-orientation cost), then gates. Re-check the hook payloads
against https://docs.claude.com/en/docs/claude-code/hooks before writing them; WS3 needed no Claude
Code hook at all. WS2's `Stop` and `PreToolUse` hooks block, so keep them separate from the nudge
hook, which must never block (AGENTS.md).
