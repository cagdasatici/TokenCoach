# TokenCoach v1.2.0: release acceptance

Plan: [remaining release work](plans/2026-09-29-remaining-release-work.md), TC3.
Status: **acceptance in progress on the Mac mini** (started 2026-10-03).

- **Release candidate:** the commit on `main` that gets tagged `v1.2.0`. Nothing is tagged yet. The code has no version string, so the tag and `Formula/tokencoach.rb` are the version. Fill in the real SHA when the mini session starts: `git rev-parse HEAD`.
- **Previous version:** `v1.1.0` (formula at v1.1.0, ledger schema 1).
- **New version:** v1.2.0 (ledger schema 5, yield, quota attribution).
- **Machine:** Mac mini `Mac18,5`, macOS 27.0.1 (26A434), Xcode 27.0, Homebrew; account `cagdas` (the owner's fresh mini account, wiped of TokenCoach by path E before A).
- **Tested revision:** `9a3f5c6` (`git rev-parse HEAD` = `origin/main` on 2026-10-03; the one-line installer fetched this revision).

## Pre-checks on the owner's Mac (2026-09-29, revision `18a3c14`)

These did not touch the running install: scratch `HOME`, scratch data dir.

| Check | Result |
|---|---|
| `python -m unittest discover -s tests` | 259 tests pass |
| Ledger upgrade v1.1.0 → `18a3c14`: build a ledger with v1.1.0's code from synthetic logs (12 prompts, 24 calls, one applied lesson), open it with HEAD's code, refresh twice | `user_version` 1 → 5 (= `ledger.SCHEMA_VERSION`), counts unchanged at 12 and 24, lesson still `applied` |
| `TOKENCOACH_NO_LAUNCH=1 TOKENCOACH_DIR=<scratch> TOKENCOACH_REPO=$PWD bash install.sh` with scratch `HOME` | exit 0, installed `18a3c14`, self-check passed, no LaunchAgents written, repo clean |

Limits: synthetic logs, ledger only. The instruction-file block, nudge setting, menu bar icon, single-process check and everything in A–H still need the mini.

## Building the v1.2.0 tarball locally (paths B and C, brew)

Release process: `git archive` tarball named `TokenCoach-X.Y.Z.tar.gz`. Checked on 2026-09-29: with `--prefix=TokenCoach-1.1.0/` it reproduces the published v1.1.0 hash exactly, so the local tarball for the tested commit will match the one published later from the same commit.

```sh
git clone https://github.com/cagdasatici/TokenCoach && cd TokenCoach
git checkout <tested sha>
git archive --format=tar.gz --prefix=TokenCoach-1.2.0/ HEAD > ~/TokenCoach-1.2.0.tar.gz
shasum -a 256 ~/TokenCoach-1.2.0.tar.gz
```

For `brew upgrade`: install from the tap with the formula at v1.1.0, then change `url` and `sha256` in the tapped formula to the local tarball (`file://…`, or `http://127.0.0.1:<port>/…` from `python3 -m http.server` if brew refuses `file://`), set `HOMEBREW_NO_AUTO_UPDATE=1`, and run `brew upgrade tokencoach`. Not tried yet; record what actually worked.

Publishing (tag, GitHub release asset, formula bump to the real URL and hash) happens after A–H pass, not before.

## Records

Template from the plan. One block per path; replace "not run" as each is done.

```
Path:            A  Fresh install, one-line installer
Revision:        9a3f5c6          Install method: script
Machine / macOS: Mac mini Mac18,5, macOS 27.0.1 (26A434), Xcode 27.0
Steps run:       after path E --purge (no TokenCoach files, agents, data or hook left): curl -fsSL https://raw.githubusercontent.com/cagdasatici/TokenCoach/main/install.sh | bash; probes; doctor; dashboard checked with curl
Expected:        ◆ in menu bar; LaunchAgents .tokencoach, .doctor, .widgethost loaded; ~/.tokencoach; data in ~/Library/Application Support/TokenCoach; widget app in /Applications if Xcode present; "Open dashboard" works; app returns after login
Actual:          installer exit 0 in 22 s, self-check passed, installed 9a3f5c6, widget built. 3 agents loaded, cron watchdog line added, exactly one app process and one widget host. ~/.tokencoach present; data dir created, ledger user_version 5, first index 678 prompts / 13682 calls from existing Claude Code and Codex logs. Nudge hook added to ~/.claude/settings.json (nudges are on by default). The app opened the dashboard itself on first run (GET / 200 in the log); dashboard listener on 127.0.0.1:47821 only, 200 with the token, 403 without it and 403 with a foreign Host header. Doctor after start: all checks ok except "no usage.json yet" (no Claude/ChatGPT session on this account yet, see H).
                 Findings, fixed in 49c5731 with tests in tests/test_release.py: (1) the dashboard access log wrote the URL secret into tokencoach.log, which is 0644 while config.json is 0600; now redacted. (2) The first doctor run under launchd hit "crontab: Operation not permitted" and still reported "cron watchdog installed"; now reported as failed. The installer's own doctor run installed the line, so nothing was missing.
Result:          pass on the probes; owner checks pending: ◆ visible in the menu bar, menu → "Open dashboard", app back after log out and in
Known limits:    the session has no Screen Recording or Accessibility permission, so the menu bar icon could not be seen from here; the doctor's icon check reports "inconclusive" on macOS 27 by design
```

```
Path:            B  Fresh install, Homebrew
Revision:        <sha / formula version>   Install method: brew
Machine / macOS:
Steps run:       brew tap cagdasatici/tokencoach https://github.com/cagdasatici/TokenCoach && brew install tokencoach; tokencoach &
Expected:        as A without the widget; login item added on first run
Actual:
Result:          not run
Known limits:
```

```
Path:            C  Upgrade with existing data
Revision:        from <v1.1.0 sha> to <sha>   Install method: brew | git
Machine / macOS:
Steps run:       install v1.1.0; use it (prompts, apply one lesson, nudges on); record probes; upgrade (brew upgrade, or git auto-update); probes again
Expected:        row counts ≥ before; user_version = 5; lesson still applied and in CLAUDE.md; nudges on; menu bar icon visible after auto-update; exactly one process (pgrep -fl tokencoach)
Actual:
Result:          not run
Known limits:    ledger part pre-checked on 2026-09-29 (see above); restart on macOS 26 (5ba0865) not yet seen
```

```
Path:            D  Rename migration (AIQuotaBar → TokenCoach)
Revision:        <sha>            Install method: script
Machine / macOS:
Steps run:       install upstream AIQuotaBar, run until it has settings and history; run the one-line installer
Expected:        old agents, watchdog, widget stopped; settings and history moved; no leftover old agents; no duplicate menu bar items; legacy.py handover checked if a fork install exists
Actual:
Result:          not run
Known limits:
```

```
Path:            E  Uninstall
Revision:        9a3f5c6          Install method: git (one-line installer)
Machine / macOS: Mac mini Mac18,5, macOS 27.0.1 (26A434)
Steps run:       backup of data, logs, ~/.claude/settings.json, ~/.claude/CLAUDE.md, agents; probes; bash ~/.tokencoach/uninstall.sh; probes; reinstall with the one-line installer; --yield-install on a scratch repo; uninstall.sh --purge; probes
Expected:        no TokenCoach LaunchAgents; hook gone from ~/.claude/settings.json, other settings intact; widget removed; yield repo hooks removed; data kept without --purge, deleted with it; applied lessons stay in the marked block
Actual:          uninstall.sh exit 0: 3 agents booted out and their plists deleted, doctor crontab line removed, app and widget processes gone, TokenCoachWidget.app and "Restart TokenCoach.app" removed, ~/.tokencoach removed. settings.json diff = only the TokenCoach UserPromptSubmit entry; the other UserPromptSubmit hook (iTerm2 cc-status) and all other keys unchanged; settings.json.tokencoach-backup kept. Data kept: ledger user_version 5, prompts 1160 → 1161, calls 22695 → 22701 (Claude Code was in use), 4 applied + 3 open lessons. ~/.claude/CLAUDE.md byte-identical, lesson block intact. Reinstall: exit 0, one app process, agents loaded, nudge hook restored, data intact. --purge: "Git hook removed from <scratch repo>" (prepare-commit-msg gone), data dir and ~/Library/Logs/TokenCoach deleted, CLAUDE.md still identical.
Result:          pass (script install); Homebrew part (tokencoach --cleanup && brew uninstall) recorded under B
Known limits:    the ledger's original yield repo (~/Documents/Projects/investing) no longer exists on the mini, so hook removal was checked on a scratch repo instead
```

```
Path:            F  Demo isolation
Revision:        9a3f5c6          Install method: git (one-line installer)
Machine / macOS: Mac mini Mac18,5, macOS 27.0.1 (26A434)
Steps run:       real data present (path A install); launchctl bootout of the app and the doctor agent, cron watchdog line paused; shasum of ~/.claude/settings.json, ~/.claude/CLAUDE.md, ~/.codex/AGENTS.md, ~/.codex/config.toml, the real config.json and every CLAUDE.md / AGENTS.md under ~/Projects and ~/Documents (24 files), row counts of all 13 ledger tables; tokencoach --demo; in the demo dashboard: Apply "Scope broad requests first", Edit and Save it, Remove it, nudges off, nudges on (all 5 POSTs 200); stop demo; same snapshot
Expected:        identical checksums and counts; demo files only under the demo data dir
Actual:          identical: 24 checksums, 13 row counts, user_version 5. Every write landed in $TMPDIR/tokencoach-demo (config.json, ledger.db, logs, demo-home/.claude/CLAUDE.md and demo-home/.codex/AGENTS.md with the edit, instruction-file backups). The only real file with a new mtime was ledger.db-shm, touched by the snapshot's own sqlite3 reads.
                 First attempt was void: with only the app's job booted out, the cron watchdog reloaded the doctor about a minute later and the doctor restarted the real app, which indexed new Claude Code activity (calls 13682 → 13708). Re-run with the cron line paused, as above.
Result:          pass
Known limits:    Quit lasts until the next watchdog run (≤ 2 min): the cron line reloads the doctor, which bootstraps the app again. By design per _quit_app's docstring, but worth a product decision
```

```
Path:            G  Widget build and refresh
Revision:        9a3f5c6          Install method: git (one-line installer)
Machine / macOS: Mac mini Mac18,5, macOS 27.0.1 (26A434), Xcode 27.0
Steps run:       bash widget/build_widget.sh; pluginkit -m; codesign -dv; pkill -f TokenCoachWidget.app and poll for the host
Expected:        widget matches menu bar (remaining); updates within the refresh interval; host relaunched after pkill
Actual:          build exit 0 in 4 s (installer had already built it once), ad-hoc signed with entitlements, installed to /Applications; extension io.github.cagdasatici.tokencoach.widget.extension(1.2) registered. pkill: host back after ~6 s as a single process (KeepAlive). Matching the menu bar and refresh not checked yet: no provider is signed in on this account, so there is no usage.json to show (see H), and the widget has to be placed on the desktop by hand.
Result:          partial: build and relaunch pass; display and refresh pending provider sign-in and the owner placing the widget
Known limits:    needs Xcode 15+, macOS 14+
```

```
Path:            H  Unavailable and stale provider states
Revision:        <sha>            Install method: git | brew
Machine / macOS:
Steps run:       no Claude/ChatGPT login, no Codex; then log in; log out or clear cookies; network off longer than a refresh cycle
Expected:        menu bar, dashboard and widget show unavailable or sign-in, never a real-looking 0% or 100%; stale data marked stale; no crash in ~/Library/Logs/TokenCoach/
Actual:
Result:          not run
Known limits:
```

Add a regression test in `tests/test_release.py` for any failure found.
