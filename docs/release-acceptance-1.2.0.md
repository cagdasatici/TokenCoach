# TokenCoach v1.2.0: release acceptance

Plan: [remaining release work](plans/2026-09-29-remaining-release-work.md), TC3.
Status: **acceptance in progress on the Mac mini** (started 2026-10-03).

- **Selected application candidate (2026-10-05):** `db47d43e221bbc2ae4a1f236d4c2c4143cae90da`. Its SSH signature verifies against the checkout's `allowed_signers`. Nothing is tagged yet. Application, installer and widget files in the working tree match this commit; uncommitted documentation and packaging-test changes still need inclusion in a final release revision and applicability review. The code has no version string, so the tag and `Formula/tokencoach.rb` are the version.
- **Previous version:** `v1.1.0` (formula at v1.1.0, ledger schema 1).
- **New version:** v1.2.0 (ledger schema 5, yield, quota attribution).
- **Machine:** Mac mini `Mac18,5`, macOS 27.0.1 (26A434), Xcode 27.0, Homebrew; account `cagdas` (the owner's fresh mini account, wiped of TokenCoach by path E before A).
- **Tested revisions:** historical E, A, F, G on `9a3f5c6`; B and C (brew) on `bb1e5b3`. Since then `f459198` (security audit: signed-only auto-update, hashed requirements, narrower widget sandbox), `b0bd3ed` (lessons left in the block are adopted, not dropped) and `10abd64` (Quit sticks: the doctor leaves a quit app stopped). A/E rechecks and D simulation on `db47d43` are recorded below; historical results alone do not establish candidate acceptance.
- **Path D plan:** no upstream AIQuotaBar install. The owner doesn't want third-party code on the machine, so the tap was removed; D runs against a simulated pre-rename install (old LaunchAgent labels, `~/Library/Application Support/AIQuotaBar`, `~/.claude_bar_config.json`, watchdog cron line) built from what `install.sh` and `tokencoach/legacy.py` migrate.

## Pre-checks on the owner's Mac (2026-09-29, revision `18a3c14`)

These did not touch the running install: scratch `HOME`, scratch data dir.

| Check | Result |
|---|---|
| `python -m unittest discover -s tests` | 259 tests pass |
| Ledger upgrade v1.1.0 → `18a3c14`: build a ledger with v1.1.0's code from synthetic logs (12 prompts, 24 calls, one applied lesson), open it with HEAD's code, refresh twice | `user_version` 1 → 5 (= `ledger.SCHEMA_VERSION`), counts unchanged at 12 and 24, lesson still `applied` |
| `TOKENCOACH_NO_LAUNCH=1 TOKENCOACH_DIR=<scratch> TOKENCOACH_REPO=$PWD bash install.sh` with scratch `HOME` | exit 0, installed `18a3c14`, self-check passed, no LaunchAgents written, repo clean |

Limits: synthetic logs, ledger only. The instruction-file block, nudge setting, menu bar icon, single-process check and everything in A–H still need the mini.

## PS2 preparation — 2026-10-05

- Checkout base: `db47d43e221bbc2ae4a1f236d4c2c4143cae90da`, with uncommitted PS1/PS4 documentation and packaging-test changes plus the PS2 procedure corrections. This is not yet a fixed release candidate; historical A–G results do not establish acceptance of this working tree.
- `.venv/bin/python -m unittest discover -s tests`: 292 tests pass with loopback binding permitted. The sandboxed run had four listener-test errors (`PermissionError` when binding); the permitted rerun passed. An existing non-failing unclosed log-file `ResourceWarning` remains.
- The owner subsequently authorized live acceptance on this account. The completed checks and remaining limitations follow below. B/C (brew) and F need applicability review; C (git), visible A/D/G checks, and H transitions remain open.
- Path D's procedure now consistently uses the agreed simulation, without installing upstream code.

## Candidate live rechecks — 2026-10-05

Revision: `db47d43e221bbc2ae4a1f236d4c2c4143cae90da`; Mac mini `Mac18,5`, macOS 27.0.1 (26A434), Xcode 27.0 (27A266a). Original install: Homebrew `HEAD-b6ac93b`, with one supervised app and an existing widget. Private owner-only backup outside the repository; original data parked during tests and restored afterwards.

Installer source was a local bare clone of this repository whose `main` points at the exact signed candidate, created with `git clone --bare --quiet /Users/cagdas/Projects/TokenCoach /private/tmp/tokencoach-ps2-candidate.git`. This tests candidate installer behavior, not the public download route. No upstream third-party installation was used.

| Path | Steps and observations | Result / limitations |
|---|---|---|
| A, recheck | Stop the original brew app with `tokencoach --cleanup`; park original data; `TOKENCOACH_REPO=/private/tmp/tokencoach-ps2-candidate.git bash install.sh`. Exit 0, self-check and widget build succeed. App, doctor and widgethost agents present; app and widgethost have RunAtLoad and KeepAlive; one script app process. Cron watchdog confirmed installed. Dashboard GET with `?t=<private token>` returns 200, missing token and foreign Host return 403. Config mode 0600, ledger schema 5; instruction files unchanged. `tokencoach-doctor.sh --check`: 12 ok, one failure for absent usage cache, icon check inconclusive. | Partial: menu click, visible icon and actual logout/login unobserved. Existing session logs remain available for indexing; this is a fresh TokenCoach data/install check, not a brand-new macOS user. Installer paused in crontab before eventually completing; the later cron probe passed. |
| D, simulation | After non-purge uninstall, park fresh test data. Create synthetic old support directory with `migration-marker.txt`, old config (`refresh_interval=60`, `seen_welcome=true`, `nudges_enabled=false`), old history (`claude: [[1791158400,12]]`), empty old install directory, three old-label agents running `/usr/bin/true`, and a harmless cron fixture containing the old watchdog name. Run the same candidate installer. Marker, refresh setting and exact history survive; old config/history files, support directory, install directory, agent files and cron line are removed. Launchctl lists only new agents; one candidate app process. | Probe pass; visible duplicate-menu check pending. Synthetic fixture contains no old ledger or widget binary; prior unit checks cover ledger/data moves, but this run does not establish legacy ledger upgrade or old widget process shutdown. |
| E, non-purge | Install a yield hook in a disposable git repo with `tokencoach.py --yield-install`; run `bash ~/.tokencoach/uninstall.sh`. Exit 0. App agents, script install, widget and disposable yield hook removed. Data retained; prompts/calls/lessons counts do not decrease; non-hook settings preserved. | Pass for these probes. Earlier record remains the evidence for preservation of other hook entries. |
| E, purge | After D, `bash ~/.tokencoach/uninstall.sh --purge`. Exit 0; synthetic test data and logs, script install, agents and widget removed. Original data remained parked outside the purge paths. | Pass; only test data purged. |
| G, build | Both candidate installer runs build, sign and install the widget; widgethost runs under the new agent. | Build probe pass; remaining-quota display, refresh comparison and candidate host relaunch still unobserved. Restored original widget signature verifies. |
| H, missing sign-in | Fresh candidate config has no Claude cookie; dashboard is reachable; no usage cache is written. App remains running; doctor reports missing cache rather than a measured quota. | Partial: visible unavailable states, ChatGPT/Codex absence, expired access, offline and stale transitions not established. |

Restoration: original data directory moved back, original logs/settings/login plist/widget applications/cron/repository hooks restored, original brew login agent bootstrapped and kickstarted. Verification: original ledger table counts retained (schema 5); settings, CLAUDE.md and AGENTS.md byte-identical to backup; crontab identical; one Homebrew app process; candidate script install removed. Private backup retained for recovery.

Probe correction: the first dashboard request incorrectly used `?token=` and returned 403. That request's accidentally unredacted token was removed from the test log; the correct `?t=` probe produced the results above. No credential values are recorded here.

**Still required:** C git auto-update/data preservation/restart; actual A logout/login and menu opening; D visible duplicate check and remaining fixture coverage; G display/refresh/relaunch; all H transitions; review or repeat B/C (brew) and F against the final revision. PS2 is not signed off.

### Owner observations after restoration — 2026-10-05

The owner confirms that the restored Homebrew installation (`HEAD-b6ac93b`)
shows a visible menu icon with percentages for both Claude and OpenAI, and
clicking **Open dashboard** opens the dashboard. The widget was not placed;
the owner added it and confirms that its values match the menu bar.

These are passing observations for the restored installation's visible menu,
dashboard opening and initial widget display. They do not establish candidate
`db47d43` UI acceptance, widget refresh after a usage change, or logout/login.
Provider authentication transitions also remain untested.

Following that report, the candidate was installed again with the original
data and provider settings retained: `tokencoach --cleanup`, then
`TOKENCOACH_REPO=/private/tmp/tokencoach-ps2-candidate.git bash install.sh`.
Installer exit 0; exact installed SHA is `db47d43e221bbc2ae4a1f236d4c2c4143cae90da`;
one script app process; original ledger table counts retained; dashboard GET
returns 200. The widget cache now contains a Claude session and OpenAI rows,
and the candidate widget was rebuilt. Candidate is left running for owner
observations; the original Homebrew setup remains backed up for restoration.
Visible checks and refresh timing are pending.

Owner then confirms candidate `db47d43` has correct menu percentages, checked
against Codex and Claude, and that **Open dashboard** works. A's visible/menu
checks pass; actual logout/login is still pending. G currently fails display
freshness: owner reports OpenAI remaining 43% / 83% in the menu versus
53% / 85% in the widget (session / weekly). The widget cache contains the
correct 43% / 83%. A widget extension process from before the candidate
rebuild remained alive; it was terminated and the supervised candidate host
restarted with `launchctl kickstart -k`. Owner confirmation after that diagnostic
restart was subsequently confirmed by the owner: widget values now match
the menu. This confirms recovery after retiring the resident extension;
automatic refresh across a subsequent usage change still needs observation.

Fix in the working tree: `widget/build_widget.sh` retires only the installed
TokenCoach extension after replacing/registering the bundle and before the
host reload. `tests/test_release.py` executes the builder with fake system
commands and verifies installation → matching-extension retirement → host
reload, leaving the host, build-directory extension and other executables
untouched. The builder's installation-path message also uses braced variable
expansion to avoid malformed UTF-8 output from macOS Bash.

The fixed builder is an uncommitted overlay on `db47d43`, SHA-256
`9a602941dff085b917b8c922bc62cfa9d5a5a54cb04c333be2fb1956c0e7939f`.
Xcode build/sign/install succeeds and fresh host/extension processes replace
the old ones. Owner confirms the widget still matches the menu after the fixed
rebuild. Final
release revision still needs to include this fix; PS2 remains open.

Verification after the fix: all 293 tests pass with loopback binding permitted;
`git diff --check` passes. Existing non-failing unclosed log-file warning remains.

Widget host recovery on the fixed build: send SIGTERM using
`launchctl kill SIGTERM gui/<uid>/io.github.cagdasatici.tokencoach.widgethost`;
a new PID returns in 1.1 seconds, with exactly one host process. G display and
host recovery now pass for this overlay; automatic refresh after a subsequent
quota change remains pending. A's actual logout/login also remains pending.

**Owner waiver — 2026-10-06:** the owner cannot log out and instructs us to
close that item and move on. Logout/login is closed by explicit owner waiver,
not an executed passing check. Earlier launch-agent configuration and visible
menu/dashboard observations remain the evidence; actual login recovery is
unverified. Do not list logout/login as awaiting further owner action.

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
Revision:        bb1e5b3 (formula 1.2.0, local git-archive tarball sha256 2a7c941b…)   Install method: brew
Machine / macOS: Mac mini Mac18,5, macOS 27.0.1 (26A434), Homebrew 7.0.7
Steps run:       no TokenCoach install or data; brew tap cagdasatici/tokencoach https://github.com/cagdasatici/TokenCoach; brew install tokencoach (tapped formula pointed at file:///…/TokenCoach-1.2.0.tar.gz, HOMEBREW_NO_AUTO_UPDATE=1); tokencoach &; probes
Expected:        as A without the widget; login item added on first run
Actual:          Homebrew 7 refused the tap: "Refusing to load formula … from untrusted tap"; brew trust --formula cagdasatici/tokencoach/tokencoach was needed, and again after every brew uninstall. With that: install exit 0. First run wrote the login agent with the stable interpreter (opt/tokencoach/libexec/venv/bin/python), loaded it and handed over: exactly one process, supervised by launchd, dashboard on 127.0.0.1:47821, nudge hook on the opt path, ledger user_version 5 (684 prompts). First-run cookie dialog shown (no browser session on this account, see H).
                 Findings on the way, fixed with tests in tests/test_login_item.py: 1fbd6b2 (interpreter path, see C), 887d9d9 and bb1e5b3: `tokencoach &` loaded the agent, launchd started a second copy, and both kept running (two processes, two icons; 1.1.0 does the same); now the manual copy hands over before starting its dashboard, and the job stops other plain copies of the same script.
Result:          pass (with the brew trust step now in README)
Known limits:    tarball from the local commit, not the published release asset; the menu bar icon itself not seen from this session (see A)
```

```
Path:            C  Upgrade with existing data
Revision:        from v1.1.0 (brew, published formula) to bb1e5b3 (local 1.2.0 tarball)   Install method: brew
Machine / macOS: Mac mini Mac18,5, macOS 27.0.1 (26A434), Homebrew 7.0.7
Steps run:       brew install tokencoach (1.1.0); tokencoach &; apply lesson 192fe048aa2d through the dashboard API (what the Apply button sends); nudges at default; probes; point the tapped formula at the local 1.2.0 tarball; brew upgrade tokencoach; tokencoach & (new caveat); probes; launchctl bootout + bootstrap of the agent as a stand-in for log out and in. Then 1.2.0 → 1.2.1 (same code, new version) with no manual step, and log-in stand-in again
Expected:        row counts ≥ before; user_version = 5; lesson still applied and in CLAUDE.md; nudges on; menu bar icon visible after auto-update; exactly one process (pgrep -fl tokencoach)
Actual:          first run on 9a3f5c6 code FAILED: after brew upgrade the 1.1.0 login agent pointed at Cellar/tokencoach/1.1.0/libexec/venv/bin/python, which the upgrade deletes; at the next login launchd could not spawn it (exit 78, EX_CONFIG) and the app stayed gone. The nudge hook had the same stale path (silent by design, so nudges just stop). 1.2.0 wrote the same Cellar path, and never rewrote an existing agent.
                 With the fixes (1fbd6b2, 887d9d9, bb1e5b3): user_version 1 → 5; prompts 684 → 684, calls 13917 → 13921; lesson 192fe048aa2d still applied and its line still in ~/.claude/CLAUDE.md; nudges on, hook re-pointed to opt/tokencoach/libexec/venv/bin/python. After `tokencoach &`: agent rewritten to the opt path and reloaded, exactly one process (1.1.0's stray manual copy stopped). Log-in stand-in: app starts. 1.2.0 → 1.2.1: Cellar/1.2.0 deleted, app starts at log-in with no manual step.
Result:          pass on brew, with one manual step for people coming from 1.1.0 (`tokencoach &` once; in the formula caveats and README). Git auto-update half not run yet
Known limits:    the 1.1.0 → 1.2.0 login breakage can't be fixed from 1.2.0 (nothing of 1.2.0 runs until started), hence the caveat. Also found: after `uninstall --purge` the lesson block stays in CLAUDE.md (as documented), but the next Apply rewrites the block from the new ledger and drops the orphaned lines (3 of 4 lessons here; the app keeps a backup). Not fixed; needs a decision. The owner's CLAUDE.md was restored from the pre-test backup afterwards
```

```
Path:            D  Rename migration (AIQuotaBar → TokenCoach)
Revision:        <sha>            Install method: script
Machine / macOS:
Steps run:       pending: create the agreed simulated pre-rename install with synthetic settings/history, old LaunchAgent labels and watchdog cron line; run the candidate installer (no upstream code)
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
Result:          pass (script install and Homebrew)
Homebrew:        tokencoach --cleanup && brew uninstall tokencoach, four times during B and C: hook removed, login agent removed, app stopped, data kept; brew uninstall also drops the formula's tap trust.
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

## Path I — DMG distribution (PS8)

Implementation record — 2026-10-05; **partial, not release acceptance**.
Working tree based on `db47d43e221bbc2ae4a1f236d4c2c4143cae90da` with prior changes
preserved. No final candidate commit exists yet.

| Check | Evidence / outcome |
|---|---|
| Local package | `scripts/build-dmg.sh --development`: self-contained `TokenCoach.app`, Applications shortcut, installation instructions and TokenCoach icon; Python/dependencies bundled; widget excluded. |
| Host | macOS 27.0.1 (26A434), arm64, Homebrew Python 3.12.15. |
| Runtime probes | Packaged `--version` reports `1.2.0.dev0 (db47d43e221b dirty)`; `--bundle-check` imports SQLite, browser_cookie3, curl_cffi and AppKit successfully without account lookup. |
| Binary baseline | Every bundled Mach-O has arm64 and a minimum OS no newer than this development host. The Python component requires macOS 27; the release checker correctly rejects it for the macOS 14 target. |
| Signing access | `security find-identity -v -p codesigning`: **0 valid identities**. Development artifact uses ad-hoc signing; no Developer ID/notarization/Gatekeeper release acceptance is claimed. |
| Automated lifecycle checks | Frozen login/nudge/git-hook/update paths; instance lock exclusion/release; cancellation preserves old install; migration repoints only owned existing git hooks; cleanup preserves unrelated cron/agents/data. |
| Full suite | 310 tests pass with loopback enabled. Existing non-failing unclosed-log-file ResourceWarning remains. |

Final local artifact: `dist/TokenCoach-1.2.0.dev0-arm64-DEVELOPMENT.dmg`.
SHA-256: `2dd81735c87d63757e5f936417836e6e64599957cac488aa65a21f2dec88dd57`.
`hdiutil verify` and the portable checksum sidecar pass. Mounted read-only, the final
image contains the app and correct Applications link; purpose description, deep/strict
ad-hoc signature and packaged runtime imports pass. Packaged empty-event nudge and
git-trailer workers were also exercised with temporary sample files (no menu app or
real account access). Signing identity lookup was repeated outside the sandbox and
still reports zero valid identities. The image remains DEVELOPMENT, not a distributable
accepted release. The older sandbox image-creation failure was resolved with permitted
disk-device access; the build emits a non-failing `hdiutil create` deprecation warning
on macOS 27.

Remaining required evidence: final clean signed SHA; Developer ID + notarytool access;
macOS 14 baseline and Intel builds; browser download and checksum; Gatekeeper opening
without bypass; drag/install and actual menu/dashboard; permission decline/allow and
working/empty/unavailable data; ejection/relaunch; logout/login; replacement upgrade;
script/Homebrew migration and data/lesson preservation; UI cleanup and removal.
No real running app was restarted/reinstalled to test source edits, and no release
workflow was dispatched or asset published. Build and end-user procedure:
[macOS distribution](macos-distribution.md).

## PS9 — dashboard continuity

Implementation record — 2026-10-05; **automated checks pass, live-browser acceptance pending**.
Same working-tree base as path I. The owner's changing-URL report was not reproduced
against their running app. Source's arbitrary-port fallback was verified as a mechanism
that could change the address and removed; authentication was retained.

- Listener integration: occupied port raises rather than relocating/trusting its
  occupant; stopping/restarting on the same available port retains the exact URL;
  token persists; `/data` requires both the correct token and Host. Existing POST
  guards and token-redaction tests still pass. Demo continues using an ephemeral port.
- Current-version instances share an owner-only advisory lock. An old manually
  running copy must be quit explicitly; no unrelated listener is killed.
- Sample-data jsdom test exercises the actual generated dashboard JavaScript:
  new prompt and quota-health data appear, filters/view/scroll stay, an unsaved
  editor defers refresh, an editor started during fetch also survives, pending
  refresh resumes, and network failure keeps previous data with unavailable state.
  These simulated timers are not a five-minute wall-clock browser acceptance run.
- Static copies have a read-only label and no live refresh loop. In the live UI,
  last completed indexing and quota reading timestamps stay distinct; an occupied
  port sends a read-only notification with recovery instructions.
- Tab reuse investigation: the existing opener uses macOS `open` for Chrome-family
  applications or the default browser and has no tab inventory API. Browser-script
  reuse would require automation access. No such permissions/subsystem was added;
  repeated opens can still create duplicate tabs. No specific browser's tab/focus
  behavior was tested or claimed fixed.

Manual checks remain: menu clicks/bookmark across a real app restart; newly indexed
usage visible within five minutes; protected lesson/rewrite/action interactions;
actual port-conflict and read-only recovery UI; outage/stale appearance; and record
actual duplicate-tab/focus behavior per tested browser.

### Cleanup test isolation correction — 2026-10-05

An earlier cleanup test mocked the main agent path but the new cleanup helper used
real home-directory paths for the doctor/widget-host plist files. Those two files
were found missing while their jobs remained loaded. Before a restoration write was
needed they were present again; their contents were verified against the loaded job
definitions. No service was reloaded/restarted by this work, and the main app and
widget kept their original PIDs. Cleanup now derives all agent paths from the
configured main agent directory. A regression uses separate temporary configured
and home directories and verifies that the latter's agent files stay untouched.
The corrected full suite passes 310 tests; the final development image was rebuilt
with this correction. No account data, hooks or instruction files were changed by
this test incident.
