---
phase: active
milestone: v1.2.0 - db47d43 candidate: A/D/G/H partial, E recheck passed; C git open; B/C brew/F need applicability review
backlog: docs/plans/2026-09-29-remaining-release-work.md
---

## Next
- A/E candidate rechecks recorded on db47d43: install probes and both uninstall modes pass; A still needs visible/menu/login checks
- Path D synthetic settings/history/agents/cron migration probes pass; visible duplicate check and legacy ledger/widget coverage remain open
- Path C, git half: install v1.1.0 with the script, auto-update to a signed main commit
- Owner confirms restored Homebrew HEAD-b6ac93b menu percentages, dashboard opening and matching widget values; repeat on the candidate and check widget refresh. H transitions remain open
- Candidate db47d43 now running with original data/sign-ins and rebuilt widget for owner observations; original Homebrew setup backed up for restoration after checks
- Owner confirms candidate menu/dashboard and matching widget after the fixed rebuild. Host relaunch passes (1.1 seconds, one process). G automatic refresh after a quota change remains pending; A logout/login closed by owner waiver on 2026-10-06 (not run)
- PS3 channel documentation and release notes/procedure prepared in docs/release-publication-1.2.0.md; publication and formula bump await PS1/PS2/PS8 acceptance
- After acceptance, tag v1.2.0, publish the archive and accepted signed/notarized DMG with checksums, bump the formula, verify published routes, restore the mini's tapped formula

## Blocked
- Tag and publish v1.2.0: nothing is released until PS1 CI, paths A-H and PS8 path I (signed/notarized DMG) pass

## Needs you
- A logout/login is owner-waived; no logout action requested
- H: sign in to Claude in a browser, sign out, network off for a refresh cycle
- Optional TC4: find 3-5 consenting testers, or drop it
