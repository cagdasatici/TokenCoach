# v1.2.0 publication procedure

Status on 2026-10-05: **prepared, publication blocked by acceptance**.
The checked-in stable formula remains v1.1.0. No v1.2.0 archive checksum or
DMG checksum is assigned until the actual accepted artifacts exist.

## Before publishing

PS1, PS2 and PS8 in [the sharing checklist](plans/2026-10-05-public-sharing-readiness.md)
must pass. Record the final candidate SHA, both green CI jobs, applicable A–H
results and path I DMG results in [release acceptance](release-acceptance-1.2.0.md).
The earlier application candidate alone does not cover subsequent fixes or packaging.
Keep signing credentials outside the repository and logs.

1. Select a clean, signed candidate commit containing all application, packaging
   and documentation changes intended for release, with `VERSION` in
   `tokencoach/version.py` set to `1.2.0` before committing. Validate its signature using
   the already trusted `allowed_signers`; confirm the app version is 1.2.0.
2. Build the signed/notarized DMG from that exact SHA using the PS8 build procedure.
   Record architecture and macOS support from passing acceptance results. Finalize
   widget inclusion, installation, migration, login startup, upgrade and removal
   instructions from those results. Do not advertise an untested target.
3. Build `TokenCoach-1.2.0.tar.gz` using `git archive --format=tar.gz
   --prefix=TokenCoach-1.2.0/ --output=TokenCoach-1.2.0.tar.gz CANDIDATE_SHA`
   (replace `CANDIDATE_SHA` with the accepted full SHA). Keep outputs outside the
   checkout. Inspect its contents and compare its extracted files with that revision.
   Verify launcher, package, assets, requirements, license and attribution are present.
   Run the extracted launcher with `--version` and verify `1.2.0` and the candidate
   revision (archive substitution must have replaced the placeholder).
4. Compute SHA-256 hashes of the final archive and each accepted DMG with
   `shasum -a 256`. Save a `SHA256SUMS` file containing the actual asset filenames.
   Do not rebuild or modify an accepted DMG after computing its checksum.

## Publish and verify

1. Create the signed `v1.2.0` tag at the accepted SHA and verify that it resolves
   to that SHA. Publish the release with the archive, accepted DMG(s), `SHA256SUMS`
   and finalized notes below only after all gates pass.
2. Download the published assets and verify their checksums against the accepted
   local artifacts. Verify the tag and archive correspond to the candidate.
3. Change `Formula/tokencoach.rb` to
   `https://github.com/cagdasatici/TokenCoach/releases/download/v1.2.0/TokenCoach-1.2.0.tar.gz`
   and the verified archive SHA-256. Test the formula using the downloaded archive;
   preserve any existing tapped formula and running installation during checks.
4. Verify fresh installation and upgrade through the published Homebrew route,
   the documented script route and the DMG route on the applicable test environments.
   Record exact revisions, downloaded checksums, data preservation and observations.
   Compare About and `--version` on each route; the archive-based Homebrew build
   and script checkout at the same SHA must report the same version and revision.
   The script still follows signed `main`; publishing a tag does not pin that channel.
5. Update README installation instructions with the real DMG links and tested
   support matrix, make it the primary route as required by PS8, remove the pending
   v1.2.0 wording, and retain the stable-versus-`main` distinction. Update
   `PROJECT_CONTEXT.md`, `STATUS.md` and PS3 checkboxes to the actual verified state.

If an asset or route fails verification, record the failure and correct it before
broad sharing. Do not mark PS3 complete from local tests alone.

Sharing drafts: [sample-data walkthrough](launch/walkthrough.md) and
[announcement](launch/announcement.md). Update their channel and platform wording
from accepted artifacts before posting; retain sample labels and the absence of
proven-savings claims.

## Release notes draft — finalize after acceptance

TokenCoach 1.2.0 adds optional per-repository tracking of what Claude Code spending
produced: cost and prompts per accepted change, plus rework judged after seven days.
Quota is displayed as remaining across the menu bar, dashboard and widget, with
unknown attribution kept visible. Health combines quota pressure and observed habits.

Git installations accept automatic updates only from commits signed by a key trusted
by the installed copy. Dependencies are hash-pinned. Lesson review and local privacy
protections have been tightened, and widget replacement retires the prior extension
before reloading its host.

For Homebrew upgrades from 1.1.0, run `brew update && brew upgrade tokencoach`, then
start `tokencoach &` once to repair the old login item. Script installations follow
signed `main` automatically when the checkout is clean. Add the accepted DMG upgrade
and migration instructions here before publication.

API-equivalent costs are estimates rather than subscription charges. Quota per prompt
is estimated; missing measurements remain unknown. Yield needs an opt-in repository
hook and seven days before judging commits. Codex receives coaching through AGENTS.md
lessons and has no prompt nudge hook. Applied lesson blocks remain after uninstall
unless removed separately. Add tested DMG platform support and widget delivery here.

Built on the upstream project by Toprak Yagcioglu; credit remains in README, LICENSE
and the app's About box.
