# v1.2.0 publication procedure

Status on 2026-10-06: **prepared, publication blocked by acceptance**.
The checked-in stable formula remains v1.1.0. No v1.2.0 archive checksum or
DMG checksum is assigned until the actual accepted artifacts exist. The owner has
deferred the DMG; Homebrew is the primary route and PS8/path I is not a v1.2.0 gate.

## Before publishing

PS1 and PS2 in [the sharing checklist](plans/2026-10-05-public-sharing-readiness.md)
must pass. Record the final candidate SHA, both green CI jobs, applicable A–H
results in [release acceptance](release-acceptance-1.2.0.md).
The earlier application candidate alone does not cover subsequent fixes or packaging.
Keep signing credentials outside the repository and logs.

1. Select a clean, signed candidate commit containing all application, packaging
   and documentation changes intended for release, with `VERSION` in
   `tokencoach/version.py` set to `1.2.0` before committing. Validate its signature using
   the already trusted `allowed_signers`; confirm the app version is 1.2.0.
2. Build `TokenCoach-1.2.0.tar.gz` using `git archive --format=tar.gz
   --prefix=TokenCoach-1.2.0/ --output=TokenCoach-1.2.0.tar.gz CANDIDATE_SHA`
   (replace `CANDIDATE_SHA` with the accepted full SHA). Keep outputs outside the
   checkout. Inspect its contents and compare its extracted files with that revision.
   Verify launcher, package, assets, requirements, license and attribution are present.
   Run the extracted launcher with `--version` and verify `1.2.0` and the candidate
   revision (archive substitution must have replaced the placeholder).
3. Compute the SHA-256 hash of the final archive with
   `shasum -a 256`. Save a `SHA256SUMS` file containing the actual asset filenames.
   The DMG remains deferred; do not include a development image in the release.

## Publish and verify

1. Create the signed `v1.2.0` tag at the accepted SHA and verify that it resolves
   to that SHA. Publish the release with the archive, `SHA256SUMS`
   and finalized notes below only after all gates pass.
2. Download the published assets and verify their checksums against the accepted
   local artifacts. Verify the tag and archive correspond to the candidate.
3. Change `Formula/tokencoach.rb` to
   `https://github.com/cagdasatici/TokenCoach/releases/download/v1.2.0/TokenCoach-1.2.0.tar.gz`
   and the verified archive SHA-256. Test the formula using the downloaded archive;
   preserve any existing tapped formula and running installation during checks.
4. Verify fresh installation and upgrade through the published Homebrew route,
   the documented script route on the applicable test environments.
   Record exact revisions, downloaded checksums, data preservation and observations.
   Compare About and `--version` on each route; the archive-based Homebrew build
   and script checkout at the same SHA must report the same version and revision.
   The script still follows signed `main`; publishing a tag does not pin that channel.
5. Update README to the verified Homebrew version and features, remove pending
   v1.2.0 wording, retain stable-versus-`main` guidance and the deferred DMG status.
   Update `PROJECT_CONTEXT.md`, `STATUS.md` and PS3 checkboxes to the verified state.

If an asset or route fails verification, record the failure and correct it before
broad sharing. Do not mark PS3 complete from local tests alone.

Sharing drafts: [sample-data walkthrough](launch/walkthrough.md) and
[announcement](launch/announcement.md). Update their channel and platform wording
from accepted artifacts before posting; retain sample labels and the absence of
proven-savings claims.

## Release notes (published 2026-10-24)

TokenCoach 1.2.0 makes staying connected effortless and the numbers more trustworthy.

**Sign in without copying cookies**
- **Sign in to Claude…** opens a small built-in window on claude.ai. Email and Google sign-in both work (for Google, use *Try another way* if it asks for a passkey). TokenCoach checks the session works before saving it.
- When the session expires, the menu bar shows **◆ !** and one notification, *Claude sign-in expired — click to sign in again*, opens that window. Previously an expired session could leave the bar stuck at **◆ ?** with no way back except pasting a cookie.
- **Paste Session Key…** remains as a fallback and accepts a bare key or a whole `Cookie:` line, saving only a key that works.

**First run**
- A short setup guide on first launch: welcome, optional extras, connect Claude, done. Reopen it any time from **Setup Guide…**.
- `install.sh` shows numbered progress and explains missing Python or git, network and disk problems in plain words.

**Quota you can trust**
- ChatGPT keeps refreshing even when Claude can't; the bar and widget follow the 5-hour limit, and a missing or malformed reading is reported as unknown instead of as full quota.
- Default refresh every minute, with a 30-second option.
- Optional per-repository tracking of what Claude Code spending produced (cost and prompts per accepted change, rework judged after seven days).
- Quota shown as remaining across the menu bar, dashboard and widget; health combines quota pressure with observed habits.

**Safety**
- Git installations auto-update only to commits signed by a key the installed copy already trusts. Dependencies are hash-pinned.
- The built-in sign-in window keeps its own login and sends it only to claude.ai; nothing is logged.

**Upgrading**
- Script installs follow signed `main` automatically when the checkout is clean.
- Homebrew: `brew update && brew upgrade tokencoach`, then start `tokencoach &` once to repair the old login item.
- The standalone app download is not part of this release; use the script or Homebrew.

**Good to know**
API-equivalent costs are estimates, not your subscription bill; Claude quota per prompt is estimated, and missing measurements stay unknown. Codex gets coaching through AGENTS.md lessons and has no prompt nudge. The Homebrew package excludes the optional widget.

Built on AIQuotaBar by Toprak Yagcioglu.
