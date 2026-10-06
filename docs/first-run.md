# First run: install to first result

This guide describes the current `main` channel. Homebrew currently ships v1.1.0;
yield tracking and other later features require `main`. The DMG is deferred; Homebrew is the primary stable route. See [installation options and requirements](../README.md#install).

## 1. Install and launch

Use the Homebrew commands in the README for the stable release, or the script
for moving `main`. The script launches TokenCoach;
Homebrew needs `tokencoach &` after installation. The core app requires macOS 12+
and Python 3.10+. The optional widget needs macOS 14+ and Xcode and is not needed to
use the dashboard. Look for ◆ in the menu bar, then click it.

If the icon is missing, follow [Troubleshooting](../README.md#troubleshooting).

## 2. Choose quota access

For quota bars, sign in to claude.ai or chatgpt.com in your browser and select
**Auto-detect from Browser** in the ⚙ menu. When macOS asks for Chrome-family
Keychain access, choose **Allow**. If browser access fails, the menu also offers
**Set Session Cookie…**; session cookies are credentials and must never be shared
in feedback, screenshots or bug reports.

You may skip browser access. TokenCoach still reads local Claude Code, Cowork and
Codex transcripts for token counts, API-equivalent costs and habit evidence. ChatGPT
quota can also use the Codex CLI's existing sign-in. Claude quota attribution needs
quota readings, so it can remain unknown even when prompt costs are present.
See [Privacy](../README.md#privacy) for what is read, stored and sent.

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
| No live quota reading | Check provider sign-in, try **Auto-detect from Browser**, then **Refresh Now**. Transcript tracking can still work. |
| No prompts or activity in this range | Select **All** and a date range containing your activity. If this Mac has no supported local history, complete a normal task in Claude Code, Cowork or Codex and wait for the next scan. |
| Still indexing older logs | Leave the app running until the background scan finishes; large histories may take longer than five minutes. |
| Browser chats absent | Browser conversations are not automatically imported. An optional data-export import provides estimated tokens, without pricing. See the CLI help linked in the README. |
| No suggestions or no change yet | More sessions or a longer comparison period may be needed. An empty result does not demonstrate savings. |
| Usage ledger unavailable or persistent empty history despite supported logs | Use the README troubleshooting steps. Share only sanitized symptoms, version, macOS and installation method. |

A successful first run means you can explain one available result, or understand
why data is absent and what would make it available. It does not require every
provider to be connected or any claimed savings.

For outside testing, use [the consent and feedback record](first-run-feedback.md).
