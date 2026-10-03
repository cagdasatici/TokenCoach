---
phase: active
milestone: v1.2.0 - acceptance on the mini: B, C (brew), E, F pass; A, G partial; D, H, C (git) open
backlog: docs/plans/2026-09-29-remaining-release-work.md
---

## Next
- Re-run A and E quickly on the current main (10abd64 or later): install.sh, doctor and widget changed after they passed
- Path D: rename migration against a simulated AIQuotaBar install (no upstream code)
- Path C, git half: install v1.1.0 with the script, auto-update to a signed main commit
- Path G display and H: need a signed-in provider; owner checks the widget and menu bar
- Then tag v1.2.0, publish the tarball, bump the formula, restore the mini's tapped formula

## Blocked
- Tag and publish v1.2.0: nothing is released until paths A-H pass

## Needs you
- A: look at the menu bar icon, click Open dashboard, log out and in
- H: sign in to Claude in a browser, sign out, network off for a refresh cycle
- Optional TC4: find 3-5 consenting testers, or drop it
