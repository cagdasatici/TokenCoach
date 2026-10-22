# First run: install to first result

This guide describes the current `main` channel. Homebrew currently ships v1.1.0;
yield tracking and other later features require `main`. The DMG is deferred; Homebrew is the primary stable route. See [installation options and requirements](../README.md#install).

## 1. Install and launch

Run the one command at the top of the README's [Install](../README.md#install)
section in Terminal. It numbers its progress ("[1/4] Checking your Mac…"), explains in
plain words anything missing (Python 3.10+, git) and ends by telling you to look for
◆ in the menu bar. Homebrew and the demo are alternatives (Homebrew ships v1.1.0,
which lacks the setup guide). The core app requires macOS 12+; the optional widget needs
macOS 14+ and Xcode.

If the icon is missing, follow [Troubleshooting](../README.md#troubleshooting).

## 2. Setup guide

On the first launch a short guide of native dialogs opens by itself; every step can be
skipped, and nothing is changed until you choose it:

1. **Welcome:** what TokenCoach shows. **Get started** or **Later** (Later brings it back next launch).
2. **ChatGPT / Codex found:** shown only if you are signed in to the Codex CLI; TokenCoach reads that sign-in without prompts.
3. **Claude Code nudges:** shown only if they are off; **Turn on** or **Skip**.
4. **Connect Claude:** **Sign in to Claude…** opens a small sign-in window (no macOS permissions needed). **Skip** keeps local-only tracking. In the downloaded TokenCoach.app, **Use my browser's login** is the first choice: it walks through the two macOS prompts (access to other apps' data, then the browser's Keychain "Safe Storage") and, if macOS still blocks it, opens Privacy & Security → Full Disk Access with a **Check Again** button. Script and Homebrew installs don't offer it: they run as the shared Python, and allowing that would let every Python script read browser cookies. Their sign-in window keeps its own login, so signing in again is usually one click.
5. **All set:** look for ◆ in your menu bar and click it any time.

The guide shows once, and not at all for people who already had a session or finished
the older welcome. Rerun it with **Setup Guide…** in the ⚙ menu. It is unavailable in
`--demo`. Session cookies are credentials and must never be shared in feedback,
screenshots or bug reports.

Without signing in, TokenCoach still reads local Claude Code, Cowork and Codex
transcripts for token counts, API-equivalent costs and habit evidence. Claude quota
attribution needs quota readings, so it can remain unknown even when prompt costs are
present. See [Privacy](../README.md#privacy) for what is read, stored and sent.

## 3. Open the dashboard

Click **Open dashboard** from the menu bar panel. Keep the app running. Use **All**
and the simple view first; select a date range containing your recent activity.
The initial scan runs in the background; large histories may still be indexing.
The app normally scans every five minutes. In development code, the live dashboard fetches data every five minutes while visible and idle, retaining filters, view and scroll. It defers refresh during edits, opened rewrites and actions.
The header reports the last completed usage scan and stale/unavailable state. You can bookmark the live page, but keep its token private. A read-only snapshot means the listener was unavailable; resolve a local port conflict and reopen the app. Repeated opens may create extra tabs depending on your browser.

## 4. Interpret one result

- Quota percentages show what is **left**, including the weekly limit. A zero means
  exhausted; “—” or “No reading” means no usable measurement.
- Dollar amounts are **API-equivalent costs**, a comparison yardstick rather than
  your subscription bill. Models without published prices are labelled estimated.
- Claude quota per prompt is an estimate; unmeasured prompts show “—”.
- Healthy, Watch and Action needed summarize available quota and habits. An absent
  provider reading does not establish that the provider has quota available.
- Lessons need repeated patterns. No suggestions is a valid early result, and a
  before/after comparison needs enough activity on both sides.

There is no need to click **Analyze deeper**, **Improve**, or **Apply** to get a first
result. Analyze and Improve send prompt content to Claude through your CLI when you
click them. Applying a lesson changes a managed block in an instruction file after
backup; uninstall does not remove those blocks.

## 5. Understand an empty or unavailable result

| What you see | What it means and what to try |
|---|---|
| No live quota reading | Choose **Sign in to Claude…** (or **Setup Guide…**) in the ⚙ menu, then **Refresh Now**. Transcript tracking can still work. |
| No prompts or activity in this range | Select **All** and a date range containing your activity. If this Mac has no supported local history, complete a normal task in Claude Code, Cowork or Codex and wait for the next scan. |
| Still indexing older logs | Leave the app running until the background scan finishes; large histories may take longer than five minutes. |
| Browser chats absent | Browser conversations are not automatically imported. An optional data-export import provides estimated tokens, without pricing. See the CLI help linked in the README. |
| No suggestions or no change yet | More sessions or a longer comparison period may be needed. An empty result does not demonstrate savings. |
| Usage ledger unavailable or persistent empty history despite supported logs | Use the README troubleshooting steps. Share only sanitized symptoms, version, macOS and installation method. |

A successful first run means you can explain one available result, or understand
why data is absent and what would make it available. It does not require every
provider to be connected or any claimed savings.

For outside testing, use [the consent and feedback record](first-run-feedback.md).
