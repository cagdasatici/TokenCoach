# Acceptance follow-up — 2026-10-06

Base revision: `df0d8cc13bd827f20fd54a20cbb750fb91e3482d` plus the updater
fix described below. Existing owner observations and waivers in
[release acceptance](release-acceptance-1.2.0.md) remain authoritative.
This record does not replace missing human or platform acceptance.

## CI

GitHub reports success for the published base revision:
[test run](https://github.com/cagdasatici/TokenCoach/actions/runs/37508658466)
and [second successful run](https://github.com/cagdasatici/TokenCoach/actions/runs/37508667361).
The test run includes passing Python 3.10 and 3.12 jobs; the second run is the
dependency graph update. PS1 is complete for that revision. Subsequent source
changes require their own CI.

## Git upgrade dependencies

Found and fixed an acceptance defect: the updater ignored pip's exit status
after moving HEAD. It could report success and restart despite missing dependencies,
then skip a retry because HEAD already matched origin.

The updater now reads requirements from the exact trusted, signed candidate and
installs them with hash enforcement before fast-forwarding. Missing requirements,
installation failure or timeout leaves HEAD unchanged and permits a retry. Pip
can partially change the environment before failure; this is not an atomic venv
replacement. No account data or running app is touched by these probes.

Executable regressions cover failure preserving HEAD, successful retry using the
candidate's requirements with `--require-hashes`, and missing requirements.
The full suite passes: **312 tests**, with the existing non-failing unclosed-log-file
ResourceWarning. Loopback permission was required for listener tests.

Real dependency probe: a disposable clone on `main`, reset to `db47d43`, with
a newly created dedicated venv. The changed updater returned true and reached
`df0d8cc13bd827f20fd54a20cbb750fb91e3482d`; real pip installed hash-pinned dependencies.
`pip check` reported no broken requirements; its Python ran the candidate's
`--version`. This closes the dependency probe, not visible app restart acceptance.

Fresh isolated installation also passed: `TOKENCOACH_NO_LAUNCH=1`, a disposable
install directory and the local repository as its source. Installer exit 0,
dependencies installed and self-check passed; nothing started. This is a file-only
probe of `df0d8cc`, not a new visible app or Homebrew acceptance result.

## Dashboard regressions

Generated fresh sample HTML in an isolated `TOKENCOACH_DEMO=1` data directory.
`tests/dashboard_refresh.cjs` passes for fresh data, health, filters, scroll,
deferred and late editors, and outage/recovery. These checks simulate timers.

Real-browser check: Codex in-app browser on this Mac, using the production
`DashboardServer` at an isolated loopback port with a synthetic token and ledger.
The fixture keeps `TOKENCOACH_DEMO=1` for write isolation; its response presents
production freshness wording and synthetic good/critical quota readings. It is
not the owner's running application or a provider request.

At 20:10 local time, loaded the good state, selected Claude and Advanced, and
opened a lesson's Details. Added one synthetic prompt/response and changed the
served quota fixture to critical. Without navigation or simulated timers, the
first five-minute browser refresh changed Healthy to Action needed, showed Codex
exhausted and Claude at 58% remaining, and increased the selected-period prompt
count from 287 to 288. Claude, Advanced and the open Details remained selected.
The page was visible and no input/editor was active. This establishes idle browser
refresh of newly served ledger/quota data, not the app's provider polling cadence.

Stopped/restarted only the isolated listener, then reloaded the same browser URL:
page and data returned, with no browser console errors. Advanced persisted; Tools
returned to All, matching the deliberate startup rule in the dashboard. The group
is preserved during live refresh, not across full page loads. Actual menu opening,
bookmarks across an AppKit restart, other browsers' tab behavior, and browser
editor/outage interaction remain unverified; the latter have jsdom coverage.

## External dependencies

- `security find-identity -v -p codesigning`: **0 valid identities**.
- GitHub Actions runner API: **no registered self-hosted runners**. The signing
  workflow has no runner available; dispatching it would not produce an artifact.
- Local pinned build dependencies verify successfully, but the previously recorded
  runtime requires macOS 27 and cannot establish the macOS 14 release baseline.
- No consenting outside-tester results have been supplied. Prepared guides and
  invitations do not establish PS5 or PS7 human validation.
- Latest published release remains v1.1.0. Publication still requires applicable
  release acceptance; no development image has been published as a release.

Existing working-tree notes record an owner deferral of the DMG and a logout/login
waiver. Preserve those decisions; neither is a passing signing or login test.
