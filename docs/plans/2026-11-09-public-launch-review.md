# TokenCoach: public launch review and implementation spec

Written 2026-11-09 against `main` at `62e2f61` (v1.2.0 published 2026-10-24, four commits after the tag).
Read-only review: no code was changed and the test suite was not run locally. CI for `62e2f61` is green
([run 41706861101](https://github.com/cagdasatici/TokenCoach/actions/runs/41706861101)).

This document has three parts:

1. **Review**: what is good, and findings ranked by severity with evidence.
2. **Slices S1–S9**: implementation steps written for an executor at low effort. One slice per session.
3. **Owner steps M1–M9**: GitHub settings and decisions that only the repository owner can make.

It complements, and does not replace, the backlog in
[2026-09-29-remaining-release-work.md](2026-09-29-remaining-release-work.md) ("Current backlog — 2026-11-08").
Where a slice here makes one of those items executable, the ID is named. `TC-NF2`, `TC-NF4`, `TC-NF5`,
`TC-NF6` and `TC-NF7` (ledger memory, checkpointing, listener limits, dashboard payload, release coverage)
are **not** covered here and stay open in that file.

---

## Part 1: Review

### Verdict

The product is ready to be shared after a small patch release. The engineering is unusually careful for a
solo tool: signed auto-update, hash-pinned dependencies, a token-and-Host-guarded loopback listener,
demo isolation, hooks that never block, and about 330 tests. The gaps are at the edges a stranger meets
first: the installer's two destructive paths, a few places where the documentation promises more than
the code does, and a GitHub page that makes a visitor scroll before they see the product.

### What is already strong (keep as is)

- **Update trust model.** `tokencoach/update.py` only fast-forwards a clean `main` to a commit signed by a
  key in the already-installed `allowed_signers`, and installs dependencies before moving `HEAD`.
- **Dashboard listener.** `tokencoach/server.py` binds `127.0.0.1`, checks the Host header, compares the
  token in constant time, and keeps the token out of the log.
- **Person stays in control.** The nudge hook (`tokencoach/nudge.py`) and commit-trailer hook
  (`tokencoach/trailer.py`) swallow every failure, and the trailer refuses hooks it does not own.
- **Honest numbers.** README, reference and release notes label estimates, API-equivalent cost and unknowns.
- **Trust documents.** `SECURITY.md` explains credential handling concretely; private vulnerability
  reporting is enabled; secret scanning and push protection are on.
- **Release hygiene.** Tagged releases with a `git archive` tarball and `SHA256SUMS`; the formula pins the hash.

### Findings

Severity: **P1** fix before sharing widely, **P2** fix in the same patch if possible, **P3** polish.

| # | Sev | Finding | Evidence | Fixed by |
|---|---|---|---|---|
| F1 | P1 | The installer deletes any existing folder at `TOKENCOACH_DIR` that is not a git checkout. Someone who sets `TOKENCOACH_DIR=~/Documents/tools` loses that folder. | `install.sh:108` `rm -rf "$INSTALL_DIR"` with no check | S1 |
| F2 | P1 | Re-running the installer on an existing install falls back to `git reset --hard`, discarding local edits, and never checks the commit signature. The signed-update guarantee in README and SECURITY.md therefore does not hold for a rerun. | `install.sh:102-105` (same as backlog `TC-NF1`) | S1 |
| F3 | P1 | Commits on `main` show **Unverified** on GitHub (`reason: unknown_key`), although they verify locally. A visitor checking the "signed `main`" claim sees the opposite. `main` has no branch protection and no rulesets. | `gh api repos/cagdasatici/TokenCoach/commits/main` (backlog `TC-GH2`) | M1, M2 |
| F4 | P2 | The Claude usage reply and the organisation id are written to the debug log. `PROJECT_CONTEXT.md` says raw account-response logging was removed, and the bug template tells users to strip account identifiers from log excerpts. | `tokencoach/providers.py:177,181,192` | S2 |
| F5 | P2 | The installer adds things the README privacy section does not list: a **Restart TokenCoach** app in `/Applications`, a crontab entry that runs the doctor every 2 minutes, and (with Xcode) the widget host app in `/Applications`. | `install.sh:188-189`, `make_dock_launcher.sh`, `tokencoach-doctor.sh:171-184`, `README.md:241-244` | S3 |
| F6 | P2 | The Restart app's icon is Anthropic's Claude logo, so a TokenCoach-made app in `/Applications` carries another company's mark. | `make_dock_launcher.sh:19` | S3 |
| F7 | P2 | Model aliases in the nudge are stale: `opus` maps to `claude-opus-5` ($5/$25) and `haiku` to `claude-haiku-4-5` ($1/$5), while the price table already has Opus 5.5 ($4/$20) and Haiku 5 ($0.10/$0.50). First-prompt nudges quote the wrong cost. The optimizer pins `claude-sonnet-5`. | `tokencoach/nudge.py:88-89`, `tokencoach/optimizer.py:21`, `tokencoach/ledger.py:53-64` | S4 |
| F8 | P2 | `VERSION` is still `"1.2.0"` four commits after the tag, so script installs on `main` report themselves as the release. `CONTRIBUTING.md:29-31` says development builds carry `.dev0`. | `tokencoach/version.py:8` | S5 |
| F9 | P2 | Status documents contradict the published state. `STATUS.md` says v1.2.0 is blocked; the `PROJECT_CONTEXT.md` snapshot heading says v1.1.0 is the published release; `docs/launch/announcement.md` says Homebrew ships v1.1.0. | `STATUS.md:3,19`, `PROJECT_CONTEXT.md:5`, `docs/launch/announcement.md:33-35` (backlog `TC-GH3`) | S6 |
| F10 | P2 | The GitHub first screen is logo, badges and a button. The product screenshot starts below the fold and is 3400 px tall. The one-paragraph pitch ("A $20–200 subscription feels flat…") sits under Features, after Quick start. | `README.md:1-47,80-83` (backlog `TC-GH1`) | S7 |
| F11 | P2 | The one-line installer needs Python 3.10+, which macOS does not ship. The README mentions this only inside step 1. The Homebrew route, which brings its own Python, is one link away in another file. | `README.md:53-59`, `install.sh:52-62` | S7 |
| F12 | P2 | The unofficial-endpoint caveat is the last line of the README. A cautious user wants it next to sign-in. | `README.md:268-269` (part of backlog `TC-NF3`) | S7 |
| F13 | P3 | Community profile is 71%: no pull request template, no feature-request form, no code of conduct, no changelog file. Discussions are off, so "ask usage questions" goes to Issues. The empty Wiki and Projects tabs are on. Website field is empty. | `gh api repos/cagdasatici/TokenCoach/community/profile` | S8, M3–M5 |
| F14 | P3 | Workflow actions are pinned by tag, not commit, and nothing watches them for updates. Dependabot security updates are disabled. | `.github/workflows/test.yml:27-28`, `release.yml:25,35` | S8, M6 |
| F15 | P3 | `docs/` mixes user guides with internal acceptance records and plans, with no index. | `docs/` listing | S9 |
| F16 | P3 | README says "macOS 12+", but CI runs only `macos-latest` and the recorded acceptance was on macOS 27. The claim is untested. | `README.md:18,53`, `.github/workflows/test.yml:21` | M8 |
| F17 | P3 | `tokencoach/ui.py` is 3,789 lines with 125 functions; there is no linter or type check in CI. Not a launch blocker. | `wc -l tokencoach/ui.py` | Deferred (see end) |

Two things were checked and are **not** findings: the Homebrew formula installs with hash checking (pip
enforces it because `requirements.txt` carries hashes), and README screenshots contain only sample data.

### Risk the owner should decide on (not an executor task)

The quota bars read `claude.ai` and `chatgpt.com` private endpoints with the user's session cookies, through
`curl_cffi` browser impersonation (`tokencoach/providers.py:116-120`). That is the inherited AIQuotaBar
design and the README discloses it, but it is the part most likely to draw a complaint from a provider or
a security-minded reader. Slice S7 moves the disclosure next to sign-in. Whether to keep sign-in in the
default setup guide or make it an explicit opt-in is decision **M9**.

---

## Part 2: Implementation slices

### Rules for every slice

- One slice per session. Do the slices in order S1 → S9. S6–S9 touch only documentation.
- Before starting: `git status --short`. The file `docs/plans/2026-09-29-remaining-release-work.md` has
  uncommitted owner edits. **Never stage, revert or edit it.** Stage files by name, never `git add -A`.
- Setup once: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` (skip if `.venv` exists).
- Verification for code slices: `.venv/bin/python -m unittest discover -s tests`. Six listener tests need
  loopback; if they fail only with a bind/permission error inside a sandbox, say so and continue.
- Do not restart or reinstall the running app. Do not run `install.sh` except through the tests in S1.
- Do not commit unless the owner says "commit". When they do: commits on `main` must be SSH-signed, or
  script installs stop auto-updating. After committing, run
  `git -c gpg.ssh.allowedSignersFile=allowed_signers log -1 --format=%G?`. If it does not print `G`,
  **stop and report**; do not push.
- **Stop and report** means: make no further edits, and reply with what you found and the exact output.
  Use it whenever the text you are told to replace is not found exactly, or a test fails for a reason
  other than a typo you made.

---

### S1 — Installer never deletes or resets what it does not own (F1, F2, `TC-NF1`)

**Commit subject:** `Installer: refuse foreign folders, fast-forward only to trusted commits`

**Files:** `install.sh`, `tests/test_release.py`

**1. In `install.sh`, add one line to the header comment.** After the line
`#                         widget, Claude Code hook or launch (used by tests)` insert:

```bash
#   TOKENCOACH_CODE_ONLY  1 = stop once the code is in place (used by tests)
```

**2. Replace the whole "Get the code" block.** Find the block that starts with
`# ── 3. Get the code` and ends with the line
`ok "Code: $INSTALL_DIR ($(git -C "$INSTALL_DIR" rev-parse --short HEAD))"` (currently lines 98–112).
Replace it with exactly:

```bash
# ── 3. Get the code ──────────────────────────────────────────────────────────
# An existing install only ever moves forward to a commit signed by a key it
# already trusts (the same rule as tokencoach/update.py). Nothing is reset or
# deleted: local edits, other branches and unrelated folders are left alone.
step 2 "Downloading TokenCoach…"
MOVE_HINT="Fix: move the folder away with  mv \"$INSTALL_DIR\" \"$INSTALL_DIR.old\"  and run the install command again.
     Your data is stored elsewhere and is kept."
if [ -d "$INSTALL_DIR/.git" ]; then
  say "↻  Updating $INSTALL_DIR…"
  git -C "$INSTALL_DIR" fetch --quiet origin \
    || die "Could not check for updates. Check that you are online, then run the install command again."
  [ -z "$(git -C "$INSTALL_DIR" status --porcelain --untracked-files=no)" ] \
    || die "$INSTALL_DIR has local changes, so the installer left it alone.
     $MOVE_HINT"
  [ "$(git -C "$INSTALL_DIR" rev-parse --abbrev-ref HEAD)" = "$REF" ] \
    || die "$INSTALL_DIR is not on the $REF branch, so the installer left it alone.
     $MOVE_HINT"
  TARGET="$(git -C "$INSTALL_DIR" rev-parse --verify --quiet "origin/$REF^{commit}")" \
    || die "The download server has no branch named $REF."
  if [ "$(git -C "$INSTALL_DIR" rev-parse HEAD)" != "$TARGET" ]; then
    git -C "$INSTALL_DIR" merge-base --is-ancestor HEAD "$TARGET" \
      || die "$INSTALL_DIR has commits of its own, so the installer left it alone.
     $MOVE_HINT"
    SIGNERS="$INSTALL_DIR/allowed_signers"
    [ -f "$SIGNERS" ] \
      || die "$INSTALL_DIR is too old to check updates safely, so the installer left it alone.
     $MOVE_HINT"
    [ "$(git -C "$INSTALL_DIR" -c "gpg.ssh.allowedSignersFile=$SIGNERS" log -1 --format='%G?' "$TARGET" 2>/dev/null)" = "G" ] \
      || die "The newest TokenCoach code is not signed by a key this install trusts, so nothing was changed.
     Please report this at https://github.com/cagdasatici/TokenCoach/issues"
    git -C "$INSTALL_DIR" merge --ff-only --quiet "$TARGET" \
      || die "Could not update $INSTALL_DIR. Nothing was changed.
     $MOVE_HINT"
  fi
else
  if [ -e "$INSTALL_DIR" ] && [ -n "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ] && [ ! -f "$INSTALL_DIR/tokencoach.py" ]; then
    die "$INSTALL_DIR already exists and is not a TokenCoach install, so the installer will not touch it.
     Fix: choose another folder with TOKENCOACH_DIR, or move that folder away, then run the install command again."
  fi
  say "↓  Downloading TokenCoach…"
  rm -rf "$INSTALL_DIR"
  git clone --quiet --depth 1 --branch "$REF" "$REPO" "$INSTALL_DIR" \
    || die "Could not download TokenCoach. Check that you are online, then run the install command again."
fi
ok "Code: $INSTALL_DIR ($(git -C "$INSTALL_DIR" rev-parse --short HEAD))"
# Test hook: stop once the code is in place (no venv, no downloads).
if [ "${TOKENCOACH_CODE_ONLY:-0}" = "1" ]; then trap - EXIT; exit 0; fi
```

**3. In `tests/test_release.py`, add this class directly after the end of `class AutoUpdate`** (that is,
immediately before the line `class AutoUpdateRestart(unittest.TestCase):`):

```python
class InstallerRerun(unittest.TestCase):
    """install.sh on an existing folder: fast-forward to a trusted commit, or change nothing."""
    git, keygen, signed_commit = AutoUpdate.git, AutoUpdate.keygen, AutoUpdate.signed_commit
    setUp, tearDown = AutoUpdate.setUp, AutoUpdate.tearDown

    def run_installer(self, target=None):
        env = {**os.environ, "HOME": self.tmp.name, "TOKENCOACH_DIR": str(target or self.clone),
               "TOKENCOACH_REPO": str(self.origin), "TOKENCOACH_NO_LAUNCH": "1", "TOKENCOACH_CODE_ONLY": "1"}
        return subprocess.run(["bash", str(REPO / "install.sh")], env=env, capture_output=True, text=True)

    def test_trusted_update_fast_forwards(self):
        self.signed_commit(self.trusted, "two")
        r = self.run_installer()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.clone / "a.txt").read_text(), "2\n")

    def test_unsigned_and_untrusted_updates_change_nothing(self):
        before = self.git(self.clone, "rev-parse", "HEAD")
        self.git(self.origin, "commit", "-qam", "unsigned")
        self.assertNotEqual(self.run_installer().returncode, 0)
        (self.origin / "a.txt").write_text("3\n")
        self.signed_commit(self.stranger, "signed by someone else")
        self.assertNotEqual(self.run_installer().returncode, 0)
        self.assertEqual(self.git(self.clone, "rev-parse", "HEAD"), before)
        self.assertEqual((self.clone / "a.txt").read_text(), "1\n")

    def test_local_edits_are_kept(self):
        self.signed_commit(self.trusted, "two")
        (self.clone / "a.txt").write_text("my edit\n")
        self.assertNotEqual(self.run_installer().returncode, 0)
        self.assertEqual((self.clone / "a.txt").read_text(), "my edit\n")

    def test_own_commits_are_kept(self):
        self.signed_commit(self.trusted, "two")
        (self.clone / "b.txt").write_text("mine\n")
        self.git(self.clone, "add", "b.txt")
        self.git(self.clone, "commit", "-qm", "local work")
        mine = self.git(self.clone, "rev-parse", "HEAD")
        self.assertNotEqual(self.run_installer().returncode, 0)
        self.assertEqual(self.git(self.clone, "rev-parse", "HEAD"), mine)

    def test_foreign_folder_is_never_deleted(self):
        other = pathlib.Path(self.tmp.name) / "documents"
        other.mkdir()
        (other / "keep.txt").write_text("important\n")
        self.assertNotEqual(self.run_installer(other).returncode, 0)
        self.assertEqual((other / "keep.txt").read_text(), "important\n")

    def test_fresh_folder_is_cloned(self):
        fresh = pathlib.Path(self.tmp.name) / "fresh"
        r = self.run_installer(fresh)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((fresh / "a.txt").exists())
```

**Checks**

```sh
bash -n install.sh
.venv/bin/python -m unittest tests.test_release.InstallerRerun -v
.venv/bin/python -m unittest discover -s tests
```

**Stop and report if:** any `InstallerRerun` test fails after you have confirmed the block was pasted
exactly; or any other existing test starts failing (some may rerun `install.sh` against an unsigned local
repository and now be refused, which is a decision for the owner, not something to patch around).

---

### S2 — Keep account replies and ids out of the log (F4)

**Commit subject:** `Providers: stop logging the Claude usage reply and organisation id`

**Files:** `tokencoach/providers.py`, `tests/test_release.py`

**1. In `tokencoach/providers.py`, function `fetch_raw`**, make three exact replacements:

| Find | Replace with |
|---|---|
| `    log.debug("org_id from cookie: %s", org_id)` | `    log.debug("org_id from cookie: %s", "found" if org_id else "missing")` |
| `        log.debug("org_id from api: %s", org_id)` | `        log.debug("org_id from api: %s", "found" if org_id else "missing")` |
| `    log.debug("usage full response: %s", json.dumps(usage, indent=2))` | `    log.debug("usage reply received: %d fields", len(usage) if isinstance(usage, dict) else 0)` |

Do not remove the `import json` at the top of the file; other code uses it.

**2. In `tests/test_release.py`, add this class directly before `class DoctorCronRepair`:**

```python
class AccountRepliesStayOutOfTheLog(unittest.TestCase):
    def test_usage_reply_and_org_id_are_not_logged(self):
        from tokencoach import providers
        reply = {"five_hour": {"utilization": 41.5, "resets_at": "MARKER-RESET"}}
        with patch.object(providers, "_org_id_from_cookies", return_value="org-MARKER-ID"), \
                patch.object(providers, "_get", return_value=reply), \
                self.assertLogs(providers.log, level="DEBUG") as logs:
            out = providers.fetch_raw("sessionKey=x")
        text = "\n".join(logs.output)
        self.assertEqual(out, {"usage": reply, "org_id": "org-MARKER-ID"})
        self.assertNotIn("MARKER-RESET", text)
        self.assertNotIn("org-MARKER-ID", text)
```

**Checks:** `.venv/bin/python -m unittest tests.test_release.AccountRepliesStayOutOfTheLog -v`, then the
full suite.

**Stop and report if:** `grep -n "org_id" tokencoach/providers.py` shows another `log.` call that prints
the id itself (list the lines; do not change them).

---

### S3 — Restart app uses TokenCoach's own icon; README lists everything the installer adds (F5, F6)

**Commit subject:** `Restart app uses the TokenCoach logo; README lists every change the installer makes`

**Files:** `make_dock_launcher.sh`, `README.md`, `tests/test_release.py`

**1. `make_dock_launcher.sh`:** replace
`ICON_SRC="$SRC_DIR/assets/claude_icon.png"` with
`ICON_SRC="$SRC_DIR/assets/tokencoach-logo.png"`.

**2. `README.md`, Privacy section.** Replace the bullet that starts with
`- **What changes on your Mac:** a login agent and watchdog,` (four lines, ending
`with hash-pinned dependencies.`) with exactly:

```markdown
- **What changes on your Mac:** the script installer adds a login agent, a watchdog that checks every
  two minutes that the app is running (a second launch agent plus one line in your crontab), a small
  **Restart TokenCoach** app in `/Applications` and, when Xcode is present, the widget app
  `/Applications/TokenCoachWidget.app`. Homebrew installs add only the login agent. With your
  agreement the app also adds the Claude Code hook (after a backup of `~/.claude/settings.json`),
  lesson blocks you apply, and git hooks in repositories you track. `uninstall.sh` (or
  `tokencoach --cleanup` for Homebrew) removes all of these except applied lessons.
  Script installs update only to commits signed by a key in [`allowed_signers`](allowed_signers),
  with hash-pinned dependencies.
```

**3. `tests/test_release.py`, inside `class Packaging`, add after `test_scripts_parse`:**

```python
    def test_restart_app_uses_our_own_icon(self):
        script = (REPO / "make_dock_launcher.sh").read_text()
        self.assertIn("assets/tokencoach-logo.png", script)
        self.assertNotIn("claude_icon", script)
        self.assertTrue((REPO / "assets" / "tokencoach-logo.png").exists())
```

**Before editing the README, verify the two factual claims.** Run:

```sh
grep -n "doctor\|cron\|make_dock_launcher\|widget" Formula/tokencoach.rb tokencoach/runtime.py | head -40
```

If the Homebrew path installs a doctor agent, a crontab line or the Restart app, **stop and report**
instead of writing "Homebrew installs add only the login agent".

**Checks:** `bash -n make_dock_launcher.sh`, the new test, then the full suite.

---

### S4 — Current model aliases for nudges and the optimizer (F7)

**Commit subject:** `Nudges and optimizer use current Claude model aliases`

**Files:** `tokencoach/nudge.py`, `tokencoach/optimizer.py`, `tests/test_coach.py`

**1. `tokencoach/nudge.py`.** Directly above `def default_model() -> str | None:` add:

```python
# Claude Code's short model names -> the model each currently selects. Keep in
# step with ledger.CLAUDE_PRICES (tests/test_coach.py checks every one is priced).
MODEL_ALIASES = {"opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-5-5",
                 "fable": "claude-fable-5-1"}
```

In `default_model`, delete the two lines that define the local `aliases = {...}` dict and replace
`return aliases.get(m, m) if isinstance(m, str) else None` with
`return MODEL_ALIASES.get(m, m) if isinstance(m, str) else None`.

**2. `tokencoach/optimizer.py`:** replace `OPTIMIZER_MODEL = "claude-sonnet-5"` with:

```python
OPTIMIZER_MODEL = "sonnet"      # Claude Code's alias, so it follows the current Sonnet
```

**3. `tests/test_coach.py`:** add this class at the end of the file, before any
`if __name__ == "__main__":` line:

```python
class ModelAliases(unittest.TestCase):
    def test_every_alias_is_priced(self):
        from tokencoach import ledger, nudge
        for alias, model in nudge.MODEL_ALIASES.items():
            self.assertIsNotNone(ledger._price_for(model), f"{alias} -> {model} has no price")

    def test_current_opus_still_suggests_sonnet(self):
        from tokencoach import nudge
        self.assertEqual(nudge.cheaper_ratio(nudge.MODEL_ALIASES["opus"])[0], "sonnet")
        self.assertIsNone(nudge.cheaper_ratio(nudge.MODEL_ALIASES["sonnet"]))
```

**Do not change `tokencoach/ledger.py` prices in this slice.** There is no `claude-sonnet-5-5` row, so
Sonnet 5.5 is priced by the `claude-sonnet-5` row ($2/$10). Whether that is still correct is owner step M7.

**Checks:** `.venv/bin/python -m unittest tests.test_coach -v`, then the full suite.

**Stop and report if:** `grep -rn "OPTIMIZER_MODEL\|claude-sonnet-5\"" tokencoach/` shows the optimizer
model used anywhere as a price key or recorded model name (list the lines).

---

### S5 — Development builds say so (F8)

**Commit subject:** `Version: main is 1.2.1.dev0 after the 1.2.0 release`

**Files:** `tokencoach/version.py`

Replace `VERSION = "1.2.0"` with `VERSION = "1.2.1.dev0"`. Change nothing else. `Formula/tokencoach.rb`
keeps pointing at the 1.2.0 tarball, and the README keeps saying Homebrew ships v1.2.0.

**Checks:** `.venv/bin/python tokencoach.py --version` prints `TokenCoach 1.2.1.dev0 (` followed by a
revision; then the full suite.

**Stop and report if:** any test fails. A test that compares `VERSION` with the formula or README is a
release-process decision for the owner.

---

### S6 — Status documents match the published state (F9, `TC-GH3`)

**Commit subject:** `Docs: status, context and announcement reflect the published 1.2.0`

**Files:** `STATUS.md`, `PROJECT_CONTEXT.md`, `docs/launch/announcement.md`. Documentation only; no tests.

**1. Replace the whole of `STATUS.md` with exactly:**

```markdown
---
phase: active
milestone: v1.2.0 published 2026-10-24; patch 1.2.1 in preparation
backlog: docs/plans/2026-11-09-public-launch-review.md
---

## Next
- Work through slices S1–S9 and owner steps M1–M9 in docs/plans/2026-11-09-public-launch-review.md, then tag v1.2.1
- Remaining engineering backlog (TC-NF2, TC-NF4 to TC-NF7): docs/plans/2026-09-29-remaining-release-work.md
- Acceptance paths left open when v1.2.0 was published by owner decision: C (dependencies, visible restart), D (visible duplicate, legacy ledger and widget), G (automatic widget refresh), H (sign-in transitions). Re-run against v1.2.1

## Blocked
- Nothing

## Needs you
- Owner steps M1–M9 (GitHub settings, signing key, price check, launch decision)
- Historical acceptance evidence is kept in docs/release-acceptance-1.2.0.md and docs/acceptance-followup-2026-10-06.md
```

**2. `PROJECT_CONTEXT.md`:** replace the heading line
`## Snapshot — 2026-10-05: v1.1.0 published; v1.2.0 acceptance and sharing readiness open` with
`## Snapshot — 2026-11-09: v1.2.0 published 2026-10-24 (Homebrew and release archive); main is 1.2.1.dev0`.

Then, directly under the heading `## Open`, insert this bullet as the first item, followed by a blank line:

```markdown
- 2026-11-09 status: v1.2.0 was tagged and published on 2026-10-24 by owner decision with acceptance paths C, D, G and H partly open. The bullets below dated 2026-10-05 and 2026-10-06 are the record of that candidate phase; where they say v1.2.0 is unpublished or that Homebrew ships v1.1.0, this bullet supersedes them. Current work: [public launch review](docs/plans/2026-11-09-public-launch-review.md) and the backlog at the top of [remaining release work](docs/plans/2026-09-29-remaining-release-work.md).
```

Do not edit or delete the older bullets.

**3. `docs/launch/announcement.md`.** Replace the first paragraph (the three lines starting
`Prepared 2026-10-05, updated 2026-10-22`) with:

```markdown
Prepared 2026-10-05, updated 2026-11-09 for the published v1.2.0. Unpublished draft. Recheck the
installation page before posting.
```

Replace the paragraph that starts `Current source installation requires macOS 12+` (five lines, ending
`available.`) with:

```markdown
Requires macOS 12+. Install with Homebrew (stable v1.2.0, brings its own Python) or the one-line
script (latest signed `main`, needs Python 3.10+ and git, adds the optional widget on Macs with
Xcode and macOS 14+). Local prompt tracking needs Claude Code, Cowork or Codex on the same Mac.
```

**Checks:** `grep -n "v1.1.0" STATUS.md docs/launch/announcement.md` prints nothing.

---

### S7 — README first screen, install choices and the unofficial-endpoint note (F10, F11, F12, `TC-GH1`)

**Commit subject:** `README: product first, both install routes, unofficial-endpoint note beside sign-in`

**Files:** `tokencoach/screenshots.py`, `docs/images/hero-light.png` (new), `docs/images/hero-dark.png`
(new), `README.md`

**1. Add two short hero screenshots.** In `tokencoach/screenshots.py`, inside the `SHOTS = {` dict, add
these two entries as the first two lines of the dict:

```python
    "hero-light":      ("theme=light&view=simple&range=30d", 1280, 530),
    "hero-dark":       ("theme=dark&view=simple&range=30d", 1280, 530),
```

Then generate into a scratch folder and copy only the two new files (this needs Google Chrome):

```sh
.venv/bin/python tokencoach.py --screenshots /tmp/tc-shots
cp /tmp/tc-shots/hero-light.png /tmp/tc-shots/hero-dark.png docs/images/
```

Open `docs/images/hero-light.png`. It must show the TokenCoach header with the "Sample data" label, the
green "Healthy" banner and the three tiles (Right now, This week, Habits) complete, with nothing cut
through the middle of a tile. **Stop and report if** Chrome is missing, the command fails, or a tile is
cut; report the image height you see needed. Do not regenerate or commit any other image.

**2. Replace the top of `README.md`.** Replace everything from line 1 up to and including the blockquote
that ends `**v1.2.0**, which includes the sign-in window, the setup guide and yield tracking.`
(currently lines 1–76) with exactly:

````markdown
<p align="center">
  <img src="assets/tokencoach-logo.png" alt="TokenCoach logo" width="96" height="96">
</p>

<h1 align="center">TokenCoach</h1>

<p align="center">
  <b>See what your AI prompts cost. Build better habits.</b>
</p>

<p align="center">
  A free, open-source macOS menu bar app for Claude Code, Cowork and Codex:<br>
  quota left, cost per prompt, and coaching on costly habits. Your data stays on your Mac.
</p>

<p align="center">
  <a href="https://github.com/cagdasatici/TokenCoach/actions/workflows/test.yml"><img alt="Tests" src="https://img.shields.io/github/actions/workflow/status/cagdasatici/TokenCoach/test.yml?branch=main&style=flat&label=tests"></a>
  <a href="https://github.com/cagdasatici/TokenCoach/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/cagdasatici/TokenCoach?style=flat&label=release"></a>
  <a href="#quick-start"><img alt="macOS 12+" src="https://img.shields.io/badge/macOS-12%2B-000000?style=flat&logo=apple&logoColor=white"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-2ea44f?style=flat"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> &nbsp;·&nbsp;
  <a href="#features">Features</a> &nbsp;·&nbsp;
  <a href="#privacy">Privacy</a> &nbsp;·&nbsp;
  <a href="#faq">FAQ</a> &nbsp;·&nbsp;
  <a href="docs/install.md">Install options</a>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/hero-dark.png">
    <img alt="TokenCoach dashboard with sample data: a healthy verdict, quota left right now and this week, and cost per prompt against your usual" src="docs/images/hero-light.png" width="880">
  </picture>
  <br>
  <sub><b>Sample data</b> from the built-in demo (<code>tokencoach --demo</code>); every screenshot on this page uses it.</sub>
</p>

A $20–200 subscription feels flat until you hit the 5-hour limit mid-afternoon. The cause is
rarely one big question; it's habits you can't see: long sessions where every reply re-reads
300k tokens of context, broad asks that send an agent on a 100-step tour, or a quick question
sent to the priciest model. TokenCoach makes those visible and helps you change them.

| | |
|---|---|
| **Measure** | Every Claude Code, Cowork and Codex prompt with its tokens, model, project and cost at API prices, plus the Claude and ChatGPT quota you have left. |
| **Nudge** | A one-line heads-up in Claude Code before an expensive prompt runs. It never blocks or rewrites what you typed. |
| **Coach** | Repeated patterns become lessons you can edit and apply to `CLAUDE.md` / `AGENTS.md`, and remove again. |
| **Compare** | Before and after for every applied lesson, with dates and sample sizes. |

<p align="center">
  <sub>Dollar amounts are API-equivalent costs, not your subscription bill. Claude quota per prompt is an estimate; unmeasured prompts show as unknown.</sub>
</p>

---

## Quick start

You need a Mac with macOS 12 or newer. Pick one route:

**One-line installer** — the latest signed `main`, with start-at-login, auto-update and the optional
desktop widget. Needs Python 3.10 or newer and git; the installer checks and tells you in plain words
what is missing. Open Terminal (Cmd+Space, type "Terminal", Return), paste this and press Return:

```bash
curl -fsSL https://raw.githubusercontent.com/cagdasatici/TokenCoach/main/install.sh | bash
```

**Homebrew** — the stable release, **v1.2.0**. Brings its own Python, so nothing else is needed:

```bash
brew tap cagdasatici/tokencoach https://github.com/cagdasatici/TokenCoach
brew trust --formula cagdasatici/tokencoach/tokencoach   # Homebrew 7 asks before loading formulae from other taps
brew install tokencoach
tokencoach &
```

**Just looking?** The [sample-data demo](docs/install.md#just-look-first-the-sample-data-demo) opens the
dashboard with made-up data and reads nothing of yours.

Then:

1. **Look for ◆ in the menu bar**, top right of your screen. Click it any time.
2. **Follow the setup guide** that opens by itself: **Get started**, then **Sign in to Claude…** and
   log in to claude.ai in the small window. Your remaining quota appears in the menu bar.

<p align="center">
  <img width="260" alt="Setup guide, first dialog: Welcome to TokenCoach, with Later and Get started" src="docs/images/setup-1-welcome.png">
  &nbsp;
  <img width="260" alt="Setup guide: Connect Claude, with Sign in to Claude… and Skip" src="docs/images/setup-3-connect.png">
</p>

Signing in is optional: without it, TokenCoach still tracks your local Claude Code, Cowork and
Codex usage. The quota bars are unofficial: they read the same private usage pages your browser
does, with your own sign-in, and can break when Anthropic or OpenAI change them. Reopen the guide
any time from the ⚙ menu → **Setup Guide…**. More detail: [first-run guide](docs/first-run.md) ·
[install, update and uninstall](docs/install.md).
````

**3. In the Features section**, delete the paragraph that starts
`A $20–200 subscription feels flat until you hit the 5-hour limit mid-afternoon.` and the blank line
after it (it now lives above Quick start). The `## Features` heading must then be followed by a blank
line and `### 1. Measure: every prompt, every token, every project`.

**4. Keep the full dashboard, folded.** Directly before the line `### 2. Nudge: a heads-up before an expensive prompt runs`, insert:

```markdown
<details>
<summary><b>The whole dashboard</b>: health, quota, coach, spending</summary>
<br>
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/dashboard-dark.png">
  <img alt="Full TokenCoach dashboard with sample data" src="docs/images/dashboard-light.png" width="880">
</picture>
</details>

```

**5. Add one FAQ entry.** Directly after the line `## FAQ` and its following blank line, insert:

```markdown
<details>
<summary><b>Is this official? Can it get my account in trouble?</b></summary>

TokenCoach is an independent open-source project, not affiliated with or endorsed by Anthropic or
OpenAI. Per-prompt tracking only reads transcript files that Claude Code, Cowork and Codex already
write on your Mac. The quota bars are different: they ask claude.ai and chatgpt.com for the same
usage figures their own settings pages show, using your sign-in, through endpoints that are not a
public API. They can stop working without notice, and you decide whether to use them: skip
**Sign in to Claude…** and everything except the quota bars still works.
</details>

```

**Checks**

```sh
grep -c "hero-light.png" README.md          # 1
grep -c "dashboard-light.png" README.md     # 1
grep -c "A \$20–200 subscription" README.md # 1
grep -n "^## " README.md                    # Quick start, Features, FAQ, Troubleshooting, Privacy, Support, Credits, License
.venv/bin/python -m unittest discover -s tests
```

**Stop and report if:** any grep count differs, or a test that reads `README.md` fails.

---

### S8 — Community files, pinned actions (F13, F14)

**Commit subject:** `Repo: PR and feature templates, changelog, pinned actions, Dependabot for workflows`

**Files (all new unless noted):** `.github/PULL_REQUEST_TEMPLATE.md`, `.github/ISSUE_TEMPLATE/feature_request.yml`,
`.github/dependabot.yml`, `CHANGELOG.md`, `.github/workflows/test.yml` (edit), `.github/workflows/release.yml` (edit),
`CONTRIBUTING.md` (edit), `README.md` (edit)

**1. `.github/PULL_REQUEST_TEMPLATE.md`:**

```markdown
## What and why

<!-- The problem, and what this changes for the person using TokenCoach. -->

## How it was checked

- [ ] `python -m unittest discover -s tests` passes
- [ ] For anything visible: tried with `python tokencoach.py --demo` (sample data only)

## Checklist

- [ ] No credentials, cookies, dashboard URLs, prompts or personal screenshots in the diff or description
- [ ] Quota is still shown as remaining; estimates are still labelled as estimates
- [ ] Hooks still never block: the Claude Code nudge and the git trailer exit quietly on failure
- [ ] `--demo` still cannot touch real files or settings
- [ ] Attribution to AIQuotaBar is unchanged
```

**2. `.github/ISSUE_TEMPLATE/feature_request.yml`:**

```yaml
name: Feature request
description: Suggest something TokenCoach should do, or do differently.
labels: [enhancement]
body:
  - type: markdown
    attributes:
      value: |
        Never post credentials, cookies, dashboard URLs (they contain a secret), prompt text, raw logs or personal screenshots.
  - type: textarea
    id: problem
    attributes:
      label: What are you trying to do?
      description: The situation and what gets in the way today. Use made-up examples.
    validations:
      required: true
  - type: textarea
    id: idea
    attributes:
      label: What would help?
      description: What you would expect TokenCoach to show or do.
    validations:
      required: true
  - type: dropdown
    id: tools
    attributes:
      label: Which tools do you use it with?
      multiple: true
      options:
        - Claude Code
        - Cowork
        - Codex
        - claude.ai / ChatGPT chats
```

**3. `.github/dependabot.yml`:**

```yaml
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: monthly
```

**4. Pin actions to commits** (SHAs resolved from the tags on 2026-11-09):

| File | Find | Replace with |
|---|---|---|
| `.github/workflows/test.yml` | `uses: actions/checkout@v4` | `uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4` |
| `.github/workflows/test.yml` | `uses: actions/setup-python@v5` | `uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5` |
| `.github/workflows/release.yml` | `uses: actions/checkout@v4` | `uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4` |
| `.github/workflows/release.yml` | `uses: actions/upload-artifact@v4` | `uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4` |

Before editing, confirm each SHA: `gh api repos/actions/checkout/commits/v4 --jq .sha` (and the same for
`actions/setup-python` `v5`, `actions/upload-artifact` `v4`). If a value differs from the table, use the
value the command prints and say so in your report.

**5. `CHANGELOG.md`.** Build it from the published release notes; do not write notes yourself.
Start the file with:

```markdown
# Changelog

Release notes for each published version, newest first. Downloads and checksums are on the
[releases page](https://github.com/cagdasatici/TokenCoach/releases).
```

Then, for each tag in this order: `v1.2.0`, `v1.1.0`, `v1.0.2`, `v1.0.1`, `v1.0.0`, run
`gh release view <tag> -R cagdasatici/TokenCoach --json publishedAt,body` and append a section
`## <version without v> — <publishedAt date as YYYY-MM-DD>` followed by a blank line and the `body`
text unchanged. **Stop and report if** a body contains anything that looks like a cookie, token,
email address other than a public maintainer contact, or a `127.0.0.1` URL with `?t=`.

**6. `CONTRIBUTING.md`.** Insert this section directly before the paragraph that starts
`Read [AGENTS.md](AGENTS.md) and [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).`:

````markdown
## Development quick start

```sh
git clone https://github.com/cagdasatici/TokenCoach && cd TokenCoach
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # Python 3.10+
.venv/bin/python -m unittest discover -s tests                        # the whole suite
.venv/bin/python tokencoach.py --demo                                 # dashboard with sample data
```

The demo uses made-up data in a temporary folder, so it is safe to run next to a real install.
Good first contributions: a clearer message or label, a missing model price in
`tokencoach/ledger.py` (cite the provider's pricing page and the date), or a test for a case that
surprised you. Releases are listed in [CHANGELOG.md](CHANGELOG.md).

````

**7. `README.md`, Support section.** After the sentence ending `see [CONTRIBUTING.md](CONTRIBUTING.md).`
add ` Past releases: [CHANGELOG.md](CHANGELOG.md).` on the same line.

**Checks**

```sh
.venv/bin/python -c "import json,sys; print('ok')"
ruby -ryaml -e 'ARGV.each { |f| YAML.load_file(f); puts "ok #{f}" }' .github/dependabot.yml .github/ISSUE_TEMPLATE/feature_request.yml .github/workflows/test.yml .github/workflows/release.yml
.venv/bin/python -m unittest discover -s tests
```

---

### S9 — An index for `docs/` (F15)

**Commit subject:** `Docs: index separating user guides from project records`

**Files:** `docs/README.md` (new). Do not move or rename any existing file; tests and links point at them.

```markdown
# TokenCoach documentation

## Using TokenCoach

- [Install, update and uninstall](install.md)
- [First run: install to first result](first-run.md)
- [User guide](user-guide.md)
- [Reference: what the numbers mean, dashboard, lessons, yield, command line](reference.md)
- [Security and privacy](../SECURITY.md)

## Contributing

- [Contributing and support](../CONTRIBUTING.md)
- [Working instructions for coding agents](../AGENTS.md) and [current project context](../PROJECT_CONTEXT.md)
- [macOS app packaging (not published yet)](macos-distribution.md)

## Project records

Kept for transparency; not needed to use or contribute to TokenCoach.

- [Plans and reviews](plans/)
- [v1.2.0 release acceptance](release-acceptance-1.2.0.md), [follow-up](acceptance-followup-2026-10-06.md) and [publication procedure](release-publication-1.2.0.md)
- [First-run feedback procedure](first-run-feedback.md)
- [Launch drafts](launch/)
```

**Checks:** every link target exists:

```sh
cd docs && for f in install.md first-run.md user-guide.md reference.md ../SECURITY.md ../CONTRIBUTING.md ../AGENTS.md ../PROJECT_CONTEXT.md macos-distribution.md plans release-acceptance-1.2.0.md acceptance-followup-2026-10-06.md release-publication-1.2.0.md first-run-feedback.md launch; do [ -e "$f" ] && echo "ok $f" || echo "MISSING $f"; done
```

**Stop and report if** any line prints `MISSING`.

---

## Part 3: Owner steps

These need the repository owner's account or judgment. Commands change public settings; run them yourself.

| # | Step | How | Done when |
|---|---|---|---|
| M1 | **Make signatures show as Verified** (F3, `TC-GH2`). The key in `allowed_signers` is not registered on GitHub as a *signing* key. | GitHub → Settings → SSH and GPG keys → New SSH key → Key type **Signing Key** → paste the public key from `allowed_signers` (the part starting `ssh-ed25519`). | `gh api repos/cagdasatici/TokenCoach/commits/main --jq .commit.verification.verified` prints `true` |
| M2 | **Protect `main`** (F3). | Settings → Rules → Rulesets → New branch ruleset for `main`: block force pushes, restrict deletions, require signed commits. Do this after M1, or your own pushes are rejected. | `gh api repos/cagdasatici/TokenCoach/rulesets` is no longer `[]` |
| M3 | **Tidy the repository tabs** (F13). | `gh repo edit cagdasatici/TokenCoach --enable-wiki=false --enable-projects=false --enable-discussions --homepage "https://github.com/cagdasatici/TokenCoach#quick-start"` | Wiki and Projects tabs gone, Discussions tab present, Website set (`TC-GH4`) |
| M4 | **Point questions at Discussions.** After M3, in `.github/ISSUE_TEMPLATE/config.yml` add a second `contact_links` entry: name `Ask a question or share feedback`, url `https://github.com/cagdasatici/TokenCoach/discussions`, about `Usage questions and ideas; issues are for reproducible bugs.` Update the first sentence of `CONTRIBUTING.md` to match. | Edit by hand or give this row to an executor. | "New issue" page shows the Discussions link |
| M5 | **Add a code of conduct** (F13). | GitHub → Add file → Create new file → name it `CODE_OF_CONDUCT.md` → choose the Contributor Covenant template. | Community profile lists it |
| M6 | **Turn on Dependabot security updates** (F14). | Settings → Code security → Dependabot security updates → Enable. | `security_and_analysis.dependabot_security_updates.status` is `enabled` |
| M7 | **Recheck prices and date them** (F7). `PRICES_CHECKED` and the README say 2026-09-27, but rows were added on 2026-11-03. Compare `CLAUDE_PRICES` and `OPENAI_PRICES` in `tokencoach/ledger.py` with both pricing pages, confirm whether Sonnet 5.5 needs its own row, then update `PRICES_CHECKED`, the two comments above the tables, `README.md` ("checked 2026-09-27") and `docs/reference.md` (two mentions) to the date you checked. | By hand; prices must come from the provider pages, not from memory. | One date everywhere, matching the day you checked |
| M8 | **Decide the minimum macOS claim** (F16). Either test v1.2.1 on a macOS 12 or 13 machine, or change "macOS 12+" to the oldest version you have actually run it on (README badge and Quick start, `docs/install.md`, `docs/launch/announcement.md`). | Owner decision. | Claim matches evidence |
| M9 | **Decide how prominent sign-in is.** Today the setup guide leads with **Sign in to Claude…**. Keeping it is the better first-run experience; making it a clearly optional second step is the more conservative position on the unofficial endpoints. S7 adds the disclosure either way. | Owner decision; if changed, it is a new slice in `tokencoach/onboarding.py`. | Decision recorded in `PROJECT_CONTEXT.md` |

### Release and launch order

1. Slices S1–S5, each committed signed. CI green on `main`.
2. M1, then M2.
3. Slices S6–S9. M3–M6.
4. M7 and M8.
5. Release **v1.2.1** following `docs/release-publication-1.2.0.md` with the version changed: set
   `VERSION = "1.2.1"`, tag, attach `TokenCoach-1.2.1.tar.gz` and `SHA256SUMS`, bump
   `Formula/tokencoach.rb` (url and sha256), then set `VERSION = "1.2.2.dev0"`. Release notes lead with:
   the installer no longer resets or deletes folders it does not own; account replies no longer reach
   the log; the Restart app has TokenCoach's own icon.
6. Refresh the GitHub description if you want it to fit search results without truncation. Suggested
   (173 characters): `macOS menu bar app: Claude and ChatGPT quota left, what each Claude Code, Cowork and Codex prompt costs at API prices, and coaching on costly habits. Local. Built on AIQuotaBar.`
7. Ask two people who have never seen it to install from the README while you watch
   (`docs/first-run-feedback.md`, `TC-GH4`). Fix what stops them. Then post `docs/launch/announcement.md`.

### Deliberately deferred

- **Splitting `tokencoach/ui.py`** and adding a linter or type checker (F17). Worth doing, but a 3,800-line
  refactor right before launch risks the menu bar behaviour that has been accepted by hand. Revisit after
  v1.2.1, starting with `ruff check --select F` in CI and moving `_UsagePanel` into its own module.
- **A dedicated Homebrew tap repository** (`cagdasatici/homebrew-tokencoach`), which would shorten the
  Homebrew route to `brew install cagdasatici/tokencoach/tokencoach`. Do it when the formula next changes.
- **A short screen recording** for the top of the README. A 15-second clip of clicking ◆ and opening the
  dashboard in demo mode would beat any static image, but it has to be recorded by hand with sample data.
- **Whether the cron watchdog is needed** alongside the launchd watchdog. S3 discloses it; removing it is a
  reliability decision that needs the history behind `tokencoach-doctor.sh:171-184`.
