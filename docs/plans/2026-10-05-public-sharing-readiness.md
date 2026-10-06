# TokenCoach public-sharing readiness

Assessment date: 2026-10-05. Reviewed revision: `db47d43e221bbc2ae4a1f236d4c2c4143cae90da`.
Status: **PS1 local fix and PS4 implemented; CI and release gates remain open**.

## Decision and scope

TokenCoach is close to a professional developer launch. A small, explicitly
early-access group is reasonable now; broad promotion should wait for the release
gates below. The strongest assets are the clear product purpose, polished sample-data
screenshots, two installation routes, troubleshooting guidance, and upstream credit.
The principal gaps are release consistency, acceptance evidence, and precise public
claims. A redesign or additional product features are not prerequisites.

This document is the prioritized sharing checklist. The existing
[TC3 plan](2026-09-29-remaining-release-work.md) defines the detailed acceptance
procedures; [v1.2.0 acceptance records](../release-acceptance-1.2.0.md) remain the
source of truth for their results. Do not treat this assessment as acceptance sign-off.
Implementation of PS1 and PS4 was authorized on 2026-10-05. Publication remains gated
by candidate acceptance.
On 2026-10-05 the owner added a signed, notarized DMG with easy installation to the
required launch scope (PS8). The implementation and a development image now exist; release signing and acceptance remain pending.

## Evidence and limitations

| Check on 2026-10-05 | Observed result |
|---|---|
| Local full suite, `.venv/bin/python -m unittest discover -s tests` | 292 tests: 291 passed, one failed. The old-name packaging check flags legitimate migration details in `docs/release-acceptance-1.2.0.md`. |
| Test environment | First sandboxed run also had four loopback-binding errors. A permitted rerun removed those errors and retained the one packaging failure. A non-failing unclosed-log-file warning was also emitted. |
| Live GitHub CI | Latest five runs failed. The [latest run](https://github.com/cagdasatici/TokenCoach/actions/runs/37218289981) showed the same packaging failure on Python 3.12 (292 tests, one failure, one skipped). |
| Distribution | [Latest published release](https://github.com/cagdasatici/TokenCoach/releases/tag/v1.1.0) and `Formula/tokencoach.rb` point to v1.1.0; the script installer defaults to `main`, and the README describes newer functionality. |
| Acceptance records | TC3 remains in progress, with partial or missing checks and older tested revisions. |
| Public presentation | README and the light dashboard sample image reviewed. GitHub is public, has a description and relevant topics, and Issues enabled. No issue templates, security policy, or contribution guide are present in the checkout. |

This was a readiness review, not a new security audit or a complete live UI test.
No live installation, upgrade, logout/login, migration, or widget acceptance was
repeated. Branding and GitHub social-preview artwork were not independently audited.
Live GitHub facts above are dated observations and must be refreshed before release.

## Required before broad sharing

### PS1 — Restore green CI

- [x] Narrowly correct the old-name packaging check to permit legitimate migration
  documentation while continuing to catch accidental old branding.
- [ ] Run the full suite and obtain green CI on the release candidate.

**Files:** `tests/test_release.py`; inspect `.github/workflows/test.yml` only if
workflow changes are necessary. Do not rewrite historical migration evidence merely
to hide the failure.

**Acceptance:** the known failure is resolved; the full local suite passes and both
configured CI Python jobs pass on the candidate. Record the SHA and run URL.

### PS2 — Finish release acceptance on the candidate

- [x] Select and record the exact application candidate SHA: `db47d43e221bbc2ae4a1f236d4c2c4143cae90da` (signed). Uncommitted documentation/test changes still need a final release revision and applicability review.
- [ ] Finish path A's visible menu, dashboard opening, and logout/login checks.
- [ ] Finish path C's git auto-update check, including data preservation, the visible
  menu icon, and exactly one running process.
- [ ] Execute path D using the simulated pre-rename installation already agreed in
  the acceptance record; do not install third-party code against the owner's preference.
- [ ] Complete path G's widget display and refresh comparison with remaining quota.
- [ ] Complete path H's missing sign-in, expired access, offline, and stale-data checks.
- [ ] Recheck A and E after the installer, watchdog, and widget changes; review which
  other earlier results need repeating because candidate code changed.

**Files:** `docs/release-acceptance-1.2.0.md`, the TC3 plan, and only implementation
files implicated by failures. Add meaningful regression coverage when failures arise.

**Acceptance:** A–H have passing records applicable to the candidate, with exact
revisions, steps, observations, and limitations. Probe-only or partial results do not
count as completed visible UI checks. Update stale candidate notes in the record.

**2026-10-05 live progress:** candidate install and rename-migration probes,
widget builds, and both uninstall modes checked on the authorized mini. Original
Homebrew setup restored and verified. See the candidate recheck table in
[release acceptance](../release-acceptance-1.2.0.md) for exact steps and limitations.
PS2 remains open: visible checks, git auto-update, provider transitions and
applicability review are not complete.

### PS3 — Align the release and installation routes

- [ ] After PS1, PS2, and PS8 acceptance pass, publish v1.2.0 from the tested revision
  with its `git archive` tarball, signed/notarized DMG, checksums, and release notes
  covering changes, upgrade steps, and limitations.
- [ ] Update the Homebrew formula to the published archive URL and matching SHA-256.
- [x] Clearly distinguish stable Homebrew releases from the script installer's
  moving `main` channel, including their update behavior.
- [ ] Verify the published installation instructions and artifact, then update
  `PROJECT_CONTEXT.md` to the actual released state.

**Files/surfaces:** `Formula/tokencoach.rb`, `README.md`, `PROJECT_CONTEXT.md`, GitHub
release/tag/assets; `install.sh` only if the chosen distribution behavior changes.

**2026-10-05 preparation:** README now labels stable Homebrew v1.1.0 and moving
`main`, explains each update route, and identifies v1.2.0/DMG as pending.
[Publication procedure and draft notes](../release-publication-1.2.0.md) cover
candidate identity, archive creation, accepted DMG/checksums, formula alignment,
and published-route verification. Formula and publication remain gated by PS1,
PS2 and PS8; PS3 is not complete.

**Acceptance:** release tag, archive contents, checksum, formula, and advertised
features agree. Fresh installation and upgrade through the published routes are
verified. Publication follows acceptance, not the reverse.

### PS4 — Correct trust-sensitive documentation

- [x] Replace the absolute “Everything stays on your Mac” claim with precise local
  storage wording and network exceptions: quota requests, updates/dependencies, and
  user-triggered Analyze/Improve. Explain the latter can send prompt content.
- [x] Explain that applied lesson blocks remain after uninstall unless removed
  separately; preserve the existing distinction between retaining and purging data.
- [x] Replace the stale orange/red menu-bar description with the current white/soft
  yellow behavior, keeping dashboard health semantics distinct.
- [x] State the widget's macOS 14+ requirement as well as its Xcode requirement;
  distinguish those from the main app's requirements.
- [x] Explain API-equivalent cost and estimated quota attribution near the opening
  pitch, so “really costs” is not mistaken for a subscription bill or exact quota use.

**Files:** `README.md`. Verify wording against `tokencoach/providers.py`,
`tokencoach/optimizer.py`, `tokencoach/coach.py`, `tokencoach/update.py`,
`tokencoach/ui.py`, `uninstall.sh`, and the widget deployment target as relevant.

**Acceptance:** a reader can tell what is stored locally, what is sent and when,
what installation/uninstall changes, which platforms support the widget, and which
numbers are estimates. No unsupported privacy or savings guarantees remain.

### PS8 — Ship an easy-install macOS DMG

Status: **implementation added 2026-10-05; signing and distribution acceptance pending**. The numbering preserves
existing PS1–PS7 references. The DMG becomes the primary installation path for ordinary
Mac users; script and Homebrew installations remain supported alternatives.

- [ ] Produce a versioned `TokenCoach-X.Y.Z.dmg` containing `TokenCoach.app` and an
  Applications shortcut, with clear drag-to-Applications instructions and existing branding.
- [ ] Bundle the Python runtime and required dependencies. Installing and launching
  the core app must require no Terminal commands, Python, Homebrew, Git, Xcode, or
  dependency downloads. Optional features may have clearly documented prerequisites.
- [ ] Sign the app and its bundled executable components with the appropriate Developer
  ID identity, notarize the distribution, and staple the applicable tickets. Keep
  signing credentials outside the repository and build logs; record release validation
  evidence without exposing secrets. Missing signing access is a release dependency,
  not grounds to ship an unsigned substitute as complete.
- [ ] Declare the supported macOS versions and CPU architectures; ship and test either
  a universal build or clearly labeled architecture-specific DMGs. Do not claim support
  based only on the source install's requirements.
- [ ] Make first launch, menu-bar discovery, dashboard opening, quota access, and
  start-at-login understandable through the UI. Launch must work after ejecting the DMG
  and after logging out and back in. Preserve normal permission prompts and user control.
- [ ] Define and test installation alongside, or migration from, script/Homebrew installs:
  preserve data, lessons, and settings; prevent duplicate app processes, hooks, and login agents.
- [ ] Provide a documented upgrade and removal flow requiring no Terminal commands.
  For the initial release, replacing the app from a newer verified DMG is sufficient;
  do not run the git checkout updater against the signed bundle. Preserve user data on
  upgrade and explain retained data and lesson blocks on removal. Provide UI cleanup for
  app-managed background agents and hooks before removal.
- [ ] Decide and document widget delivery. If included, ship it prebuilt and signed so
  end users do not need Xcode. If excluded, state that clearly on the download and
  onboarding paths; the core app must remain fully usable without it.
- [ ] Add a repeatable build/release procedure tied to the candidate SHA and version;
  publish the tested DMG and SHA-256 checksum with PS3. Update README and PS5 onboarding
  so downloading, dragging, and opening the app are the primary instructions.

**Files/surfaces:** proposed `packaging/macos/` build configuration and resources,
`scripts/build-dmg.sh`, `.github/workflows/release.yml`, and
`docs/macos-distribution.md`; `README.md`, `tokencoach/` startup/resource-path,
login/cleanup/update code as needed, widget packaging if included, and GitHub assets.
These are proposed entry points, not a mandated packaging library. Preserve the
lightweight architecture, local dashboard protections, attribution, and demo isolation.

**Acceptance:** download the candidate DMG through a browser on a clean Mac/account
without developer prerequisites; drag to Applications and open normally through
Gatekeeper without bypass instructions. Verify signing/notarization and the checksum,
then demonstrate menu bar, dashboard, honest empty/unavailable states, and working
quota/ledger data when the relevant tools/accounts are present. Eject the disk image,
relaunch, test login startup, upgrade from a prior packaged build or recorded fixture,
migrate/coexist with supported existing installs, and remove the app with cleanup.
Record the exact SHA, artifact checksum, macOS/architecture matrix, permission behavior,
data-preservation checks, and outcomes in a new **path I — DMG distribution** section
of `docs/release-acceptance-1.2.0.md`. All declared targets must have passing evidence;
Python unit tests alone do not satisfy this gate. Publishing remains PS3's final step.

## Recommended before the announcement

### PS5 — Make the first five minutes clear

Status: **guide and feedback procedure implemented; outside validation pending**.
See [first-run guide](../first-run.md) and [feedback record](../first-run-feedback.md).

- [x] Add a short install → launch → quota access → dashboard → first result guide.
- [x] Explain what works without browser access and what an empty transcript history means.
- [ ] Ask 3–5 consenting outside testers to follow the guide without live coaching;
  record installation method, platform, outcome, and confusing steps without collecting
  credentials or prompt contents.

**Files:** `README.md`; a focused onboarding document under `docs/` if needed;
`docs/first-run-feedback.md` (proposed results record).

**Acceptance:** several outside users reach and correctly interpret their first
dashboard result, or understand an honest empty/unavailable state. Resolve reproducible
first-run blockers before broad sharing. This is usability validation, not proof of savings.

### PS6 — Provide a support and security-reporting path

- [x] Add a bug-report template asking for version, macOS, installation method,
  reproduction steps, and sanitized diagnostics; warn against posting credentials or prompts.
- [x] Add a security policy with a verified private reporting route.
- [x] Add concise contribution and support guidance with realistic expectations.
- [x] Add a consistent version identifier to About and `--version`, including a useful
  development-build identity, so reports can be tied to the running code.

Implementation verified on 2026-10-05: GitHub private vulnerability reporting is
enabled (`GET /repos/cagdasatici/TokenCoach/private-vulnerability-reporting` returned
`enabled: true`). Bug and security links are provided in README and issue configuration.
About and `--version` share `tokencoach/version.py`; git archives embed the revision
for Homebrew, while checkouts include a dirty marker. Current code is explicitly
`1.2.0.dev0`. Archive identity and account-free CLI reporting have regression coverage.
Verification: all 298 tests pass on a permitted rerun; the sandboxed run had four
loopback-binding errors. The existing non-failing unclosed-log-file warning remains.
`git diff --check` passes. Published-route checks remain part of PS3; the existing
v1.1.0 release lacks this feature.

**Files/surfaces:** `.github/ISSUE_TEMPLATE/` (new), `SECURITY.md` (new),
`CONTRIBUTING.md` (new), `README.md`, and the version/CLI/About implementation in
`tokencoach/` and the launcher as needed. Confirm any GitHub reporting configuration.

**Acceptance:** users can find where to report bugs and privately report security
issues; the requested diagnostic fields are obtainable and safe to share. Version
reporting agrees across script and Homebrew installations.

### PS7 — Prepare the sharing material

- [x] Create a short sample-data walkthrough using existing branding.
- [x] Draft a concise announcement naming the intended audience, concrete benefits,
  platform requirements, limitations, and one clear installation link.
- [x] Keep demonstration numbers visibly labeled as sample data; describe coaching
  savings as something users can investigate, not a proven outcome.

**Status — 2026-10-05:** preparation complete in the working tree based on
`db47d43`. [One-minute walkthrough](../launch/walkthrough.md) reuses the existing
screenshot-command sample assets; both visible Sample data badges were visually
checked. [Announcement draft](../launch/announcement.md) includes audience, benefits,
requirements, limitations and one installation link. Captions identify all comparison
numbers as synthetic and make no measured-savings claim. Stable v1.1.0, development
features and the pending DMG are distinguished. No recording, posting or new-reader
validation is claimed; publication remains subject to release gates. Local document
links and `git diff --check` pass. Full suite: 298 tests pass on a permitted rerun;
the sandboxed attempt had four loopback-binding errors. The existing non-failing
unclosed-log-file warning remains.

**Files/surfaces:** `docs/launch/` (prepared drafts), `docs/images/`, and GitHub release
notes. README images must come from `tokencoach.py --screenshots` and sample data.

**Acceptance:** a new reader understands the product and how to try it without
mistaking synthetic before/after numbers for measured user results. No personal data
appears in public visuals. Draft preparation does not imply posting authorization.

### PS9 — Reopen a stable dashboard and keep it fresh

Status: **implementation added 2026-10-05; live-browser/manual acceptance pending**.
Requested on 2026-10-05: “Open Dashboard” should feel like returning to the same live
page, rather than opening a different URL each time.

**Pre-implementation findings:** `server.get_token` already persists a per-install secret and the
listener prefers port 47821, but falls back to an arbitrary available port on a bind
error. `_open_dashboard` opens the existing listener URL (or a read-only report when
no listener exists). `open_file` delegates to macOS `open` without tab lookup/reuse.
The dashboard already reloads every five minutes unless certain actions are active.
The reported changing URL has not been reproduced; do not assume its cause or remove
authentication because the URL contains a random-looking secret.

- [ ] Reproduce repeated opens and restarts, comparing URL components without logging
  the secret. Distinguish a changing port/token, a static-report fallback, and duplicate
  tabs at the same URL; check for multiple app instances and port conflicts.
- [ ] Keep one stable, bookmarkable authenticated local address during normal use and
  across ordinary restarts. Reuse the app's listener; do not create one per click.
  Handle port conflicts explicitly and safely, never killing an unrelated listener or
  silently trusting it. Explain any unavoidable address change and recovery path.
- [ ] Keep the open page current without another menu click. Verify the existing
  five-minute refresh against newly indexed data and current quota readings; show the
  last successful update and unavailable/stale state. Preserve filters, view, and scroll,
  and do not discard lesson edits, prompt rewrites, or interrupt active actions. Refresh
  after protected interactions finish. A static report must remain labeled read-only.
- [ ] Investigate focusing an existing dashboard tab for explicitly supported browsers
  before opening another. Keep this best-effort: do not add broad browser permissions or
  a large automation subsystem solely for tab reuse. If simple reuse is unavailable,
  retain the stable live URL, document the browser limitation, and record the remaining
  duplicate-tab behavior rather than claim it is fixed.

**Files:** `tokencoach/server.py`, `tokencoach/ui.py`, `tokencoach/ledger_report.py`,
relevant listener/dashboard tests in `tests/test_coach.py` and `tests/test_release.py`,
and `README.md` if opening, refresh, or recovery guidance changes.

**Acceptance:** repeated menu clicks and an ordinary app restart retain the same URL
when its port is available; a bookmarked page works after restart. Newly indexed usage
appears within five minutes on an idle visible page without reopening it. Editing and
view state survive refresh; outages are not shown as fresh data. Exercise occupied-port,
duplicate-instance, and read-only fallback cases. Record actual tab behavior per tested
browser and any scoped limitation. Loopback binding, Host validation, per-install token,
action authentication, token redaction, and demo isolation remain intact. Treat this as
a modest polish task unless reproduction reveals a broader lifecycle defect; document
that finding before expanding implementation scope.

## Release gates and order

1. Resolve PS1 and PS4; implement PS8 and prepare PS5–PS7 and PS9 alongside acceptance work.
2. Complete PS2 and PS8 against the candidate, resolving any real defects they expose.
3. Complete PS3 only after candidate acceptance, including the DMG; check the public artifacts and install routes.
4. Before broad promotion, confirm PS1–PS4 and PS8 are complete, outside first-run validation
   has succeeded, and support instructions and sharing material are ready.

For each item, replace its open status with dated evidence: revision, test/run link or
acceptance record, and remaining limitations. Do not infer completion from code changes
alone. Revalidate checks affected by later changes.

## Deferred scope

A standalone website, distribution formats beyond the required macOS DMG, additional
product features, and the formal TC4 coaching-effectiveness study can wait. The existing seats/gates
backlog is not added to this launch scope. No claim of demonstrated savings should
depend on an experiment that has not been performed.

## Implementation evidence — 2026-10-05

- **Revision:** working-tree changes based on `db47d43e221bbc2ae4a1f236d4c2c4143cae90da`;
  no new candidate commit or CI run is recorded yet.
- **PS1:** `tests/test_release.py` now explicitly permits the historical migration
  evidence in `docs/release-acceptance-1.2.0.md`. Other files retain the existing
  old-name checks; historical evidence was preserved. Full local suite: **292 tests,
  OK** on Python 3.12. The sandboxed attempt had four loopback-binding errors; the
  permitted rerun passed. The existing non-failing unclosed-log-file warning remains.
  Both candidate CI jobs and their run URL remain required.
- **PS4:** README claims checked against `providers.py`, `optimizer.py`, `coach.py`,
  `update.py`, `ui.py`, `uninstall.sh`, and the widget deployment target (14.0).
  Local storage and network exceptions, prompt sharing, retained lesson blocks,
  white/soft-yellow menu percentages, widget requirements, and estimated/API-equivalent
  numbers are now explicit. Removed the unsupported typical Analyze/Improve cost range.
- **PS5:** README first-five-minutes walkthrough, `docs/first-run.md` and
  `docs/first-run-feedback.md` prepared on 2026-10-05. Browser-independent tracking,
  unavailable quota, empty transcripts and number interpretation are explicit.
  Outside recruitment and unassisted validation remain pending; no results are claimed.
  Verification: all 293 tests pass on a permitted rerun; the sandboxed run had four
  loopback-binding errors. The existing non-failing unclosed-log-file warning remains.
  Local documentation links and `git diff --check` pass.
- **Remaining:** PS2–PS3 and PS5 outside validation plus PS8 release acceptance and PS9 manual acceptance remain open; PS7 drafts are prepared. No installation, running-app restart,
  live UI acceptance, outside-user testing, release publication, or CI dispatch was performed.

## PS8–PS9 implementation evidence — 2026-10-05

Working tree based on `db47d43`, preserving prior edits; no new candidate SHA,
CI run, signing identity or publication is claimed.

- **PS8:** self-contained PyInstaller app, architecture-labelled DMG, Applications
  shortcut/instructions and TokenCoach diamond icon; pinned build tools; bundled
  CLI workers, hook/login paths, manual replacement upgrades and UI cleanup.
  Widget excluded. Release builder checks candidate signature/cleanliness and
  every Mach-O architecture/minimum OS, signs/notarizes/staples app and image,
  checks Gatekeeper and emits checksums/build records. Manual workflow awaits
  provisioned signing runners. The arm64 DEVELOPMENT image builds and its
  bundled runtime/dependency/version probes pass on macOS 27.0.1. No valid
  signing identities were found. This host's Python requires macOS 27, so it
  cannot build the macOS 14 release target. Developer ID/notarytool access,
  baseline and Intel builds, and path I acceptance remain required.
- **PS9:** removed arbitrary-port fallback; conflict yields a labelled read-only
  copy with recovery guidance. Per-install token stays unchanged. Instance lock
  prevents current-version duplicate processes. Authenticated JSON refresh keeps
  filters/view/scroll, updates health/advice and records successful indexing;
  protected and late-starting interactions defer updates, then resume. Outage
  state retains prior data. Browser `open` delegation remains: no browser tab
  reuse or browser behavior acceptance is claimed and no additional automation
  permissions are requested. The reported live URL change was not reproduced;
  the fallback-port mechanism was confirmed and removed with regression coverage.
- **Checks:** 310 Python tests pass with loopback permission; sample-data jsdom
  checks pass for fresh data/health, filters, scroll, deferred/late lesson edits,
  and outages/recovery. Initial sandbox runs could not bind loopback/create the
  disk image; permitted runs succeeded. The existing non-failing unclosed-log-file
  ResourceWarning remains. See path I and PS9 records for artifact and limits.
