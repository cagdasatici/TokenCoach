# TokenCoach

**See the API-equivalent cost of your Claude and ChatGPT prompts, and get coaching
on costly habits.** A macOS menu bar app for people who live in Claude Code and Codex.

Costs compare token use at API prices; they are not your subscription bill. Claude quota
per prompt is estimated from quota readings; unattributed usage is shown as unknown.

[![macOS](https://img.shields.io/badge/macOS-12%2B-black)](#install)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Local ledger](https://img.shields.io/badge/ledger-stored%20locally-blue)](#privacy)

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/dashboard-dark.png">
  <img alt="TokenCoach dashboard: a green, amber or red health state, quota left, habits, coach lessons with before/after, spending and costliest prompts" src="docs/images/dashboard-light.png">
</picture>

<sub>All screenshots use the built-in sample data (`tokencoach --demo`).</sub>

---

## The problem you can't see

A $20–200 subscription feels flat, until you hit the 5-hour limit at 3pm. The cause is rarely
one big question. It's habits that stay invisible:

- **Long sessions.** Every reply re-reads the whole conversation. At 300k tokens of context,
  "one more small thing" costs more than the original task.
- **Broad asks.** "Implement all the open things" sends an agent on a 100-step tour of your
  repository before it writes a line.
- **The wrong model.** A quick question to the most expensive model, because it was selected.

TokenCoach turns those habits into numbers, then helps you change them, and shows what changed afterwards.

## How it works: measure → nudge → coach → compare

### 1. Measure: every prompt, every token, every project

<img align="right" width="340" alt="Menu bar panel" src="docs/images/panel.png">

TokenCoach reads the transcripts that **Claude Code, Cowork and Codex** already write on your
Mac and keeps a local ledger: one row per prompt, with tokens, model, project, what it would
cost at API prices, and its attributed share of your 5-hour quota (estimated for Claude).

The menu bar shows the quota you have **left** for Claude and ChatGPT, today's spend, and your
most expensive prompt. Percentages are bright white when healthy and soft yellow when quota
is low, on pace to run out before reset, or exhausted. The dashboard uses green, amber and red
for its separate health summary.

**Open dashboard** starts with one answer: **healthy, watch or action needed**. It is decided
by the worst of three checks: quota left right now, your weekly pace, and your habits (cost per
prompt against your own usual). Below that is everything by day, project, model and tool, with an
**All / Claude / OpenAI** switch and an **Advanced** mode for the deep dive.

In the current development code, the live dashboard has one authenticated local
address, including across restarts when port 47821 is available. You can bookmark it;
the address contains a private access token, so do not share it. An idle visible page
fetches current data every five minutes, preserving filters, view and scroll. Refresh
waits while you edit lessons, keep an opened rewrite, or run an action, then resumes.
The header shows the last completed usage scan and unavailable/stale state; quota
readings keep their own timestamps. A port conflict produces a labelled read-only
snapshot instead of silently changing the address. Resolve the conflict and restart
the app to restore the live page. Browser opening still uses macOS `open`: repeated
clicks may create duplicate tabs, depending on the browser. Automatic tab reuse is
not implemented and adds no browser automation permission.

<br clear="right">

### 2. Nudge: a heads-up before an expensive prompt runs

<img alt="A TokenCoach nudge in Claude Code (illustration)" src="docs/images/nudge.png">

A Claude Code hook adds a one-line tip at the moment it matters, based on *your own* history:
a session re-reading 300k tokens per reply, a broad ask that historically ran 10× longer, a
quick question on your priciest model, a prompt similar to one that cost $9 last week, or a
nearly empty quota. It never blocks or rewrites what you typed.

### 3. Coach: lessons written into the files your agents read

<img alt="Coach: lessons with their evidence, apply, edit, before/after" src="docs/images/coach-dark.png">

Patterns that repeat across sessions become **lessons**, plain instructions for your coding
agent such as *"when a request is broad, list the concrete items and wait for confirmation"*.

- **Evidence decides.** Each lesson names its evidence by how many separate sessions show the
  pattern: **limited** (1–2), **moderate** (3–7) or **strong** (8+). That is a rule of thumb,
  not a measured accuracy. A clear pattern with strong evidence can be written into `CLAUDE.md` /
  `AGENTS.md` in one click; with moderate evidence you review it and decide; with less it keeps
  collecting.
- **Your words win.** **Edit** any lesson ("warn after 10 responses, not 30"). Edited lessons
  are yours, and later analyses never overwrite them.
- **Safe edits.** Lessons live in one clearly marked block, the original file is backed up
  first, and **Remove** takes them out again.
- **Improve any prompt.** Get a tighter rewrite of a costly prompt to copy or save as a template.
- **Analyze deeper.** Claude reviews your 20 costliest prompts and proposes new lessons.

### 4. Compare: before and after

Every applied lesson shows what changed after it was applied, against the four weeks before:
$ per prompt, agent responses per prompt, session length, peak context and quota per prompt
(with how many prompts had quota data). Both periods show their dates and size, and small
samples are marked. It is an observed change, not a controlled test: other things change too,
so read it as a hint about which habits pay off.

### 5. Yield: what the spend produced (optional, per repository)

Spend says little without what it bought. Track a git repository and TokenCoach ties each Claude
Code session's cost to the commits it made, then judges those commits a week later:

```sh
tokencoach --yield-install ~/code/my-repo    # once per repository
tokencoach --yield                           # the numbers; also in the dashboard
tokencoach --yield-remove ~/code/my-repo     # undo
```

This adds a git `prepare-commit-msg` hook that appends a `Claude-Session: <id>` line to commits
made *inside Claude Code*. Commits you make in a terminal get nothing, and the hook never blocks a
commit. It refuses to touch a hook that isn't its own, and a `core.hooksPath` outside the
repository. The dashboard's **What it produced** shows, by week and by model:

- **Cost per accepted change**: session cost ÷ accepted commits. Sessions that made no commit
  count against it.
- **Prompts per accepted change**: how much of your attention each surviving commit took.
- **Rework**: the share of commits followed within 7 days by a fix (a commit whose subject says
  fix, bug, regression or revert) to one of the same files.

A commit is *accepted* once it is a week old and, in that week, was neither reverted nor dropped
from every branch. Younger work is listed as pending and not judged. Two things to know: "dropped"
is noticed by TokenCoach's own scans, so squash-merging and then deleting a branch counts as
dropped, and on a file that many commits touch, one fix counts against all of them. Compare a
period with an earlier one measured the same way, not with an absolute target.

<details>
<summary><b>Advanced view</b>: quota over time, when you work, breakdowns, sessions</summary>
<br>
<img alt="Advanced view" src="docs/images/advanced-dark.png">
</details>

---

## Install

The documentation below describes the `main` development channel. The Homebrew
formula currently ships **v1.1.0**; features added after that release, including yield
tracking, require `main` until v1.2.0 is accepted and published. A signed, notarized
DMG build is implemented, but signing and clean-Mac acceptance are pending; no public DMG is available.

**DMG — primary path for the upcoming packaged release (pending):** download the
image for Apple Silicon or Intel, drag TokenCoach to Applications, eject the image,
and open the app. The package includes Python and core dependencies; the optional
widget is excluded. macOS 14+ is the release target, pending validation on both CPUs.
Use Settings → Launch at Login if wanted. See [DMG installation, upgrades and removal](docs/macos-distribution.md).
Until a signed/notarized image passes acceptance and is published, use an alternative below.

**Script install — moving `main` channel** (also sets up start-at-login and the optional desktop widget):
```bash
curl -fsSL https://raw.githubusercontent.com/cagdasatici/TokenCoach/main/install.sh | bash
```

The script follows `main`, which can include changes before a stable release. It
automatically updates a clean `main` checkout only to commits signed by a key
trusted by the installed copy. Local tracked edits or a different branch stop
auto-update.

**Homebrew — stable release:**
```bash
brew tap cagdasatici/tokencoach https://github.com/cagdasatici/TokenCoach
brew trust --formula cagdasatici/tokencoach/tokencoach   # Homebrew 7 asks before loading formulae from other taps
brew install tokencoach
tokencoach &          # first run adds it to your login items
```
Homebrew updates through `brew update && brew upgrade tokencoach`; the app does
not run its git updater for Homebrew installations. This currently installs v1.1.0.
When v1.2.0 is published, run `tokencoach &` once after upgrading from v1.1.0 so
it can repair the login item that points at the removed version folder.

Release preparation and acceptance gates are recorded in
[the v1.2.0 publication procedure](docs/release-publication-1.2.0.md).

**Just look first.** The demo uses sample data and doesn't read or change anything of yours:
```bash
git clone https://github.com/cagdasatici/TokenCoach && cd TokenCoach
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python tokencoach.py --demo
```

Requirements: macOS 12+, Python 3.10+. Claude Code and/or Codex for per-prompt tracking;
a claude.ai or chatgpt.com login in your browser for the quota-left bars. The desktop widget
requires macOS 14+ and Xcode (the installer builds it when Xcode is present).

**Uninstall:** `bash ~/.tokencoach/uninstall.sh` (add `--purge` to delete your data too).
With Homebrew: `tokencoach --cleanup && brew uninstall tokencoach` (the first step removes the
login item and the Claude Code hook, which Homebrew can't).
Applied lessons remain in your `CLAUDE.md` / `AGENTS.md` files, even with `--purge`.
Use **Remove** in the dashboard before uninstalling, or delete the marked TokenCoach lesson
block afterwards. Normal uninstall retains local data; `--purge` deletes app data and logs.

**Upgrading from AIQuotaBar or AIQuotaLeft:** run the one-line installer above. It stops the
old launch agents, watchdog and widget, moves your settings and quota history into TokenCoach,
and removes the old `~/.ai-quota-bar` folder. Your data is kept. AIQuotaLeft installs that
auto-update make this move by themselves on their next start.

---

## Your first five minutes

1. **Install and launch.** Choose a route in [Install](#install). The script starts
   the app; with Homebrew, run `tokencoach &`. Look for ◆ in the macOS menu bar.
2. **Connect quota if you want it.** Sign in at claude.ai or chatgpt.com, then choose
   **Auto-detect from Browser** in the ⚙ menu. For a Chrome-family Keychain request,
   choose **Allow**. You can skip browser access: local transcript tracking still works,
   and ChatGPT quota can use an existing Codex CLI sign-in.
3. **Open dashboard** from the menu bar panel. Start with **All** and the simple view.
   Give the first transcript scan time to finish; a large history can take longer.
4. **Read your first result.** Quota percentages mean **remaining**, and dollar amounts
   compare tokens at API prices. They are not charges on your subscription. “—” or
   “No reading” means unavailable or unmeasured, not zero. Health is a summary of the
   available quota and habit signals, not proof that every provider is connected.
5. **If history is empty**, use Claude Code, Cowork or Codex for a normal task on this
   Mac, then check again after the next scan (normally within five minutes). Select a
   date range and provider that include that activity. Browser chats are not collected
   automatically; importing an export is a separate, optional step.

See [the first-run guide](docs/first-run.md) for empty states and recovery steps.
You can inspect the dashboard without running Analyze, Improve or applying lessons.

## What the numbers mean

| | Claude Code / Cowork | Codex | claude.ai / chatgpt.com chats |
|---|---|---|---|
| Tokens per prompt | exact, from local transcripts | exact, from local transcripts | estimated from an imported data export |
| API-equivalent $ | Anthropic list prices (checked 2026-09-27) | OpenAI list prices¹ | not priced |
| Quota per prompt | estimated from TokenCoach's quota readings | from Codex's own reading after each response | — |

**API-equivalent $** is what the same tokens would cost on the provider's API. On a
subscription you pay a flat fee, so treat it as a yardstick for comparing prompts, projects and
models, not as a bill. **Set Plan Prices…** in the menu shows what your plan is worth against it.

¹ Standard-tier prices from OpenAI's pricing page (checked 2026-09-27), including long-context
rates above 272K tokens. A model without a published price (e.g. `codex-auto-review`) is priced
like its closest published sibling and labelled *estimated*. Override anything in
`~/Library/Application Support/TokenCoach/config.json`:

```json
{
  "ledger_prices": {"gpt-6-astra": {"in": 10, "read": 1, "out": 50}},
  "ledger_model_equivalents": {"codex-auto-review": "gpt-5.6-luna"},
  "ledger_plans": {"claude": 100, "chatgpt": 20}
}
```

## Privacy

- **Local storage:** the ledger, including prompt text, is a local SQLite file; the dashboard is served
  only on `127.0.0.1`, behind a per-install key.
- **What is read:** Claude Code transcripts (`~/.claude/projects`), Cowork logs, Codex sessions
  (`~/.codex/sessions`), commit messages, dates and file names (`git log`) of repositories you
  chose to track, and, for the quota bars, your claude.ai / chatgpt.com session cookies
  from your browser. For Chrome-family browsers macOS asks for Keychain access to read them
  (once per browser per lookup); click **Allow**, not **Always Allow**: the request comes from
  Apple's `security` tool, so Always Allow lets any program on your Mac read that key unasked.
  TokenCoach looks once at start and again only when you ask or a session expires, and never
  asks when macOS's privacy protection keeps it out of the browser's folder (then use
  **Set Session Cookie…**). Without a ChatGPT browser session it uses the Codex CLI's own
  sign-in (`~/.codex/auth.json`), read only, never copied, and sent only to chatgpt.com. Cookies
  are only ever sent to claude.ai / chatgpt.com, and never written to the log.
- **Quota requests:** TokenCoach contacts provider usage endpoints to refresh quota and balance
  readings, using the relevant sign-in credentials.
- **Prompt content sent when you click:** **Analyze deeper** and **Improve** send a digest of
  your costliest prompts (or the one prompt) to Claude through *your own* `claude` CLI, running
  Sonnet 5 with all tools off. That counts against your Claude plan like any Claude Code prompt,
  and TokenCoach tracks its API-equivalent cost like any other session. Cost varies with input
  and output size.
- **What changes on your Mac:** a login agent, a small watchdog that restarts the app if it
  dies, the Claude Code hook (a backup of `~/.claude/settings.json` is written first, and you
  can turn nudges off in the menu), lesson blocks you choose to apply, and a git hook in each
  repository you track with `--yield-install`. The script uninstaller removes the app, launch
  agents, widget and installed hooks; applied lesson blocks remain until removed separately.
  Lessons that Analyze proposes are never applied without you reading and confirming the exact rule.
- **Updates and dependencies:** installation and updates contact GitHub and Python package
  sources to download code and dependencies. A script install updates itself only to commits
  on `main` signed by a key in
  [`allowed_signers`](allowed_signers), checked against the copy you already have, and installs
  Python packages only if their hashes match `requirements.txt`. Homebrew installs update with
  `brew upgrade`.

## Troubleshooting

- **No ◆ in the menu bar:** `tail -50 ~/Library/Logs/TokenCoach/tokencoach.log`, then
  `bash ~/.tokencoach/tokencoach-doctor.sh` checks and repairs the moving parts.
- **Quota bars empty:** log in at claude.ai / chatgpt.com in your browser, then
  **Auto-detect from Browser** in the ⚙ menu.
- **Dashboard buttons do nothing:** open it from the menu bar icon; a saved copy is read-only.
- **Command line:** `tokencoach --help` with Homebrew, otherwise
  `~/.tokencoach/.venv/bin/python ~/.tokencoach/tokencoach.py --help` (`--ledger`, `--dashboard`,
  `--optimize`, `--import-export FILE`, `--demo`, `--cleanup`).

## Support and security

Report bugs and usage questions in [GitHub Issues](https://github.com/cagdasatici/TokenCoach/issues).
Include About TokenCoach or `tokencoach --version`, macOS, installation method and
reproduction steps; see [support and contribution guidance](CONTRIBUTING.md). Older
releases may lack version reporting. Support is best effort, with no guaranteed response time.
Never post credentials, cookies, dashboard URLs, prompts, raw logs or personal screenshots.
Report vulnerabilities privately through the [security policy](SECURITY.md).

## Credits

TokenCoach is built on **[AIQuotaBar](https://github.com/yagcioglutoprak/AIQuotaBar)** by
[Toprak Yagcioglu](https://github.com/yagcioglutoprak). The menu bar app, the quota fetching
for claude.ai and ChatGPT, and the desktop widget all started there. TokenCoach adds the ledger,
dashboard, nudges, coaching and before/after measurement. If you like the menu bar part,
please star the original too.

## License

[MIT](LICENSE). Copyright © 2026 Toprak Yagcioglu (AIQuotaBar) and the TokenCoach contributors.

Not affiliated with or endorsed by Anthropic or OpenAI. The quota bars use the same private
usage endpoints as the providers' own settings pages, and may break when those change.
