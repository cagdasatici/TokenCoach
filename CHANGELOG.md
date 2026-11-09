# Changelog

Release notes for each published version, newest first. Downloads and checksums are on the
[releases page](https://github.com/cagdasatici/TokenCoach/releases).

## 1.2.0 — 2026-10-24

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


## 1.1.0 — 2026-09-28

Health at a glance: TokenCoach now answers "am I OK?" with one state — good, watch or critical.

- **Dashboard headline.** The dashboard opens with one line and a short explanation based on your live quota and your habits, for example "Slow down on Claude: at this pace you'll reach the 5-hour limit before it resets. Codex has 96% left." It suggests where to keep working when one tool runs low.
- **Pace, not just percentage.** A 5-hour or weekly window turns amber when you're on pace to run out before it resets, not only when it's nearly empty. Red is kept for an empty window.
- **Habits.** Cost per prompt over the last 7 days is compared with the 4 weeks before; when it grows, the dashboard names the likely cause (long sessions, more back-and-forth, pricier work) and points to a waiting Coach lesson. Habits never turn the state red.
- **Menu bar colors.** Like the battery icon, the percentage stays in the normal menu bar color while healthy and turns orange or red only when the quota needs attention. The menu shows the same one-line explanation on top.
- **Redesigned dashboard** with a cleaner grouped layout, in light and dark.
- `--demo` shows the new headline with sample data; add `?health=watch` or `?health=critical` to the dashboard URL to preview the other states.


## 1.0.2 — 2026-09-27

Fixes from a pre-sharing review.

- **The demo never uses your Claude account.** With sample data, Improve shows the saved sample rewrites and no longer runs your `claude` CLI.
- **Faster, safer nudges.** The Claude Code hook no longer runs database set-up on every prompt and never waits more than 2 seconds for a busy ledger.
- **Your original `~/.claude/settings.json` backup is kept.** Turning nudges on and off, or re-running the installer, no longer overwrites it.
- **Homebrew uninstall:** run `tokencoach --cleanup` before `brew uninstall tokencoach` to remove the login item and the Claude Code hook.
- **Auto-update leaves working copies alone.** Git installs update only when they are a clean checkout of `main`.
- **Lessons:** rules proposed by Analyze are kept to one line and can't break the managed block; a CLAUDE.md / AGENTS.md that only held lessons is removed with the last one (a backup is kept).
- Clear message on Python older than 3.10; `--help` shows the `tokencoach` command; README notes the upgrade from AIQuotaBar / AIQuotaLeft.


## 1.0.1 — 2026-09-27

Fixes for people moving from AIQuotaBar / AIQuotaLeft: settings are now merged into the new data folder instead of being left behind when that folder already had a config file, and duplicate widget processes are cleaned up. See v1.0.0 for everything TokenCoach does.

## 1.0.0 — 2026-09-27

**TokenCoach shows what every Claude and ChatGPT prompt costs, and coaches you to spend less for the same results.**

- **Measure:** a local ledger of every Claude Code, Cowork and Codex prompt, with tokens, model, project, API-equivalent $ (Anthropic and OpenAI list prices) and quota used. Plus a dashboard with an All / Claude / OpenAI switch and an Advanced mode.
- **Nudge:** one-line tips in Claude Code before an expensive prompt runs (big context, broad asks, pricey model for a quick question, a repeat of a costly prompt, low quota). Never blocks or rewrites.
- **Coach:** lessons from your own history, written into `CLAUDE.md` / `AGENTS.md` at 95%+ confidence or when you confirm. Edit any lesson. Improve any prompt.
- **Prove:** before/after for every applied lesson.
- **Quota left** for Claude and ChatGPT in the menu bar (from AIQuotaBar).

Install: `curl -fsSL https://raw.githubusercontent.com/cagdasatici/TokenCoach/main/install.sh | bash`, or Homebrew (see README). Try it with sample data first: `tokencoach --demo`.

Coming from AIQuotaBar / AIQuotaLeft? Just run the installer, or let the app update itself; your data and settings move over automatically.

TokenCoach is built on [AIQuotaBar](https://github.com/yagcioglutoprak/AIQuotaBar) by Toprak Yagcioglu.

