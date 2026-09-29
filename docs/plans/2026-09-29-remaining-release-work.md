# TokenCoach: remaining release work (TC3, TC4 and follow-ups)

Handoff for a fresh session. Written 2026-09-29.

## Done

| Item | Commit | Notes |
|---|---|---|
| Auto-update restarts in a fresh process | `5ba0865` | launchctl kickstart under launchd, new process otherwise. Needs a real check on macOS 26 (TC3, path C). |
| TC1: missing quota is unknown, not zero | `5e28e0e` | `coach._window_stats` averages known prompts only and returns `quota_known`. The Coach panel shows "unavailable" and "N of M prompts measured". |
| TC2: claims match the calculation | `aa6f155` | "Limited / Moderate / Strong evidence · N sessions" (`coach.evidence_level`), no "% confident". Before/after is labelled an observed change, not a controlled test, with dates, prompts and sessions per period. Under 30 prompts on either side shows **small sample**. "Working" is now "Applied". |

None of this is pushed. The working tree also holds a separate, uncommitted **yield** feature from another session (`yield_metrics.py`, `trailer.py`, `test_yield.py`, plus edits in `ledger_report.py`, `ui.py`, `README.md`, `demo.py`, `ledger.py`, `__main__.py`, `uninstall.sh`, `AGENTS.md`, `PROJECT_CONTEXT.md`). Don't commit it with TC work. Stage your own hunks only, and test the staged snapshot with `git checkout-index -a --prefix=<scratch>/idx/`.

## Follow-ups from TC1/TC2 (code, small)

1. **Flat intervals leave quota NULL.** `ledger.attribute_quota()` writes quota only for intervals where used-% rose. Calls in a sampled interval with no rise stay NULL, which now reads as "unknown", so the known-only average skews upward. Fix: write 0 for calls inside sampled intervals (gap ≤ `MAX_SAMPLE_GAP`) with no rise, keep NULL outside them, and bump `ATTRIBUTION_VERSION`. Tests go in `tests/test_ledger.py`.
2. **Other dashboard quota sums treat missing as 0.** `grep -n "q5 || 0" tokencoach/ledger_report.py` finds the quota chart metric, the Claude/Codex quota totals and three breakdown aggregations. Decide per place whether it needs a coverage note or `null` handling. Do this after item 1, since that changes how common NULL is.
3. **README screenshots are stale.** `docs/images/coach-*.png` still show "NN% confident" and "Working". Regenerate with `.venv/bin/python tokencoach.py --screenshots docs/images` (sample data only) *after* the yield work lands, because `demo.py` is being changed there.
4. Checked with nothing left to do: the menu bar (`ui.py`) and notifications make no lesson or savings claims. Nudge text is unchanged.

## TC3: release acceptance on the Mac mini (arrives about 2026-10-02)

Goal: each path below gets a record (template at the end). Existing user data survives supported upgrades and demo use. Record everything against the **exact tested revision**.

### Before starting

- **Decide what "previous version" and "new version" are.** Homebrew installs the release tarball in `Formula/tokencoach.rb` (currently v1.1.0), so testing `brew upgrade` needs a new tag (for example v1.1.1 with the commits above), its tarball, and a formula bump. The git install path can instead be tested by pinning `~/.tokencoach` to v1.1.0 and letting auto-update fast-forward to `main`.
- **On the Mac mini:** a fresh macOS user account created by the owner (not a copy of this Mac's), Xcode installed for path G, and the macOS version recorded (`sw_vers`).
- **Record** `git rev-parse HEAD` of the checkout or tag being tested, and `tokencoach --version` if it exists (otherwise the formula version or `git -C ~/.tokencoach rev-parse HEAD`).
- **Useful probes:**
  - `launchctl list | grep tokencoach`
  - `ls ~/Library/LaunchAgents | grep -i -e tokencoach -e aiquota -e claude_bar`
  - `sqlite3 "$HOME/Library/Application Support/TokenCoach/ledger.db" "PRAGMA user_version; SELECT COUNT(*) FROM prompts; SELECT COUNT(*) FROM calls; SELECT id, status FROM lessons;"`
  - `shasum ~/.claude/CLAUDE.md ~/.claude/settings.json ~/.codex/AGENTS.md 2>/dev/null`
  - Log: `~/Library/Logs/TokenCoach/`

### Paths

**A. Fresh install, one-line installer** (README → Install)
1. `curl -fsSL https://raw.githubusercontent.com/cagdasatici/TokenCoach/main/install.sh | bash`
2. Expect: ◆ in the menu bar, LaunchAgents `io.github.cagdasatici.tokencoach`, `.doctor` and `.widgethost` loaded, `~/.tokencoach` present, data in `~/Library/Application Support/TokenCoach`, the widget app in `/Applications` if Xcode is present, and "Open dashboard" working.
3. Log out and back in: the app comes back.

**B. Fresh install, Homebrew.** Use a second fresh account, or do this after E has cleaned up A.
1. `brew tap cagdasatici/tokencoach https://github.com/cagdasatici/TokenCoach && brew install tokencoach`, then `tokencoach &`
2. Expect: the same as A without the widget (the formula caveat says so), and a login item added on first run.

**C. Upgrade with existing data**
1. Install the previous version (brew: formula at v1.1.0; git: install, then `git -C ~/.tokencoach reset --hard v1.1.0` on `main`).
2. Use it for real: some Claude Code prompts, apply one lesson, turn nudges on. Record the probe output.
3. Upgrade: `brew upgrade tokencoach`, or wait for / trigger the git auto-update.
4. Expect: row counts ≥ before, `user_version` equal to the new `ledger.SCHEMA_VERSION`, the lesson still applied and still in `CLAUDE.md`, nudges still on. After an auto-update the **menu bar icon is still visible** (the reason for `5ba0865`), and exactly one app process runs (`pgrep -fl tokencoach`).

**D. Rename migration (AIQuotaBar → TokenCoach) with existing data**
1. On a fresh account, install upstream AIQuotaBar (https://github.com/yagcioglutoprak/AIQuotaBar) and run it until it has settings and history (`~/.claude_bar_config.json`, `~/.claude_bar_history.json`, `~/Library/Application Support/AIQuotaBar/`).
2. Run the one-line installer (path A step 1).
3. Expect: old launch agents, watchdog and widget stopped; settings and history moved (`tokencoach/config.py` `migrate_legacy_data`); no leftover old agents; no duplicate menu bar items. Also check the auto-update handover (`tokencoach/legacy.py`) if an old fork install is available.

**E. Uninstall**
1. Git install: `bash ~/.tokencoach/uninstall.sh`, then check probes; reinstall; `bash ~/.tokencoach/uninstall.sh --purge`.
2. Homebrew: `tokencoach --cleanup && brew uninstall tokencoach`.
3. Expect: no TokenCoach LaunchAgents, the Claude Code hook gone from `~/.claude/settings.json` with other settings intact, the widget removed, and yield repo hooks removed (once yield ships). Data kept without `--purge` and deleted with it. Applied lessons **stay** in `CLAUDE.md` / `AGENTS.md` inside the marked block, by design (`uninstall.sh` header). Record the actual result.

**F. Demo isolation**
1. With real data present, quit the app and record `shasum` of the instruction and settings files, plus ledger row counts.
2. `tokencoach --demo`. In the demo dashboard click Apply, Remove, Edit and the nudge toggle.
3. Expect: identical checksums and row counts afterwards; demo files only under `~/Library/Application Support/TokenCoach/demo-home` (or the demo data dir).

**G. Widget build and refresh**
1. `bash widget/build_widget.sh` (Xcode 15+, macOS 14+); add the widget to the desktop.
2. Expect: the widget matches the menu bar (quota shown as **remaining**), updates after usage changes within the refresh interval, and after `pkill -f TokenCoachWidget.app` the app relaunches the host (`widget.ensure_widget_host_running`).

**H. Unavailable and stale provider states**
1. A fresh account with no Claude or ChatGPT browser login, and Codex not installed.
2. Then: log in; later log out or clear cookies; disconnect the network for longer than a refresh cycle.
3. Expect in the menu bar, dashboard and widget: "unavailable" or sign-in states, never 0% or 100% presented as real; stale data marked as stale; nothing crashes (check the log).

### Record template (one per path)

```
Path:            A–H
Revision:        <git sha / tag>     Install method: <script | brew | git>
Machine / macOS: Mac mini <model>, macOS <sw_vers>
Steps run:       <exact commands>
Expected:        <from above>
Actual:          <what happened, with probe output>
Result:          pass | fail | partial
Known limits:    <e.g. no AIQuotaBar fork install available>
```

Save the filled records as `docs/release-acceptance-<version>.md`. Tests in `tests/test_release.py` already cover the legacy data move, demo sandboxing, packaging, auto-update and cleanup at unit level. Add a regression test there for any failure found.

## TC4 (optional): does coaching help?

Not a release condition, and an inconclusive result is valid.

- **Setup:** 3–5 consenting testers, a small set of matched tasks (the same task type done once without lessons and once with the lesson applied, order alternated). Written consent covering what TokenCoach records (the prompts stay on their machine; they share numbers only).
- **Record per task:** completion quality (a simple rubric), rework (follow-up fixes; yield's rework rate can help once shipped), elapsed time, usage coverage (share of prompts with quota data, from TC1), cost, and interruptions (nudges shown).
- **Output:** a short note saying which lessons to keep, change or remove. Save as `docs/coaching-experiment-<date>.md`.
