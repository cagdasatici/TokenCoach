# TokenCoach

*Formerly AIQuotaLeft.* Tracks every Claude and ChatGPT prompt, coaches you to spend less
quota for the same results, and shows what you have left in the menu bar.

> A fork of [AIQuotaBar](https://github.com/yagcioglutoprak/AIQuotaBar) by
> [Toprak Yagcioglu](https://github.com/yagcioglutoprak), whose work this almost
> entirely is. It reports what you have **left** rather than what you have used —
> see [Changes in this fork](#changes-in-this-fork). Not an official AIQuotaBar release.

**Stop getting rate-limited by surprise.** See how much Claude and ChatGPT quota you have **left**, live in the macOS menu bar.

No Electron. No browser extension. One command to install.

<!-- The demo recordings inherited from upstream show quota USED - bars filling
     as quota is consumed - which is the opposite of what this fork displays.
     Rather than illustrate the wrong behaviour, they are omitted until
     re-recorded. The sample menu under "What it shows" is accurate: its
     numbers and bar widths are taken from real rendered output. -->

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Fork of yagcioglutoprak/AIQuotaBar](https://img.shields.io/badge/fork%20of-yagcioglutoprak%2FAIQuotaBar-blue)](https://github.com/yagcioglutoprak/AIQuotaBar)

---

## Install

**One-line (recommended):**
```bash
curl -fsSL https://raw.githubusercontent.com/cagdasatici/AIQuotaLeft/main/install.sh | bash
```

**Homebrew:**
```bash
brew tap cagdasatici/aiquotaleft https://github.com/cagdasatici/AIQuotaLeft
brew install --HEAD cagdasatici/aiquotaleft/aiquotaleft
aiquotaleft &
```
Homebrew installs the menu bar app only. The desktop widget needs Xcode — use the
one-line installer above, or run `AIQuotaBarWidget/build_widget.sh` yourself.

The app launches immediately and auto-detects your Claude and ChatGPT sessions from Chrome, Arc, Brave, Edge, Firefox, or Safari — no copy-pasting cookies.

---

### Why this fork exists

Toprak Yagcioglu built AIQuotaBar to make AI usage visible in the menu bar. This fork changes the question the interface answers: how much quota is left? My contributions are listed under [Changes in this fork](#changes-in-this-fork).

---

## What it shows

Every percentage is **quota remaining**, not quota used. 100% means a full
tank; 0% means you're out.

| Menu bar | Meaning |
|---|---|
| 🟢 88% | Plenty of session quota left — you're good |
| 🟡 17% | Running low — approaching the 5-hour limit |
| 🔴 0% | Rate-limited — shows time until reset |
| 🔴 0% · | Session is fine but weekly quota is gone |

Open the menu for full detail:

```
CLAUDE

  🟢 5-hour
  ████████████░░  88% left
  resets today 15:41

  🟡 Weekly
  ██░░░░░░░░░░░░  17% left
  resets Wed 23:00

  🟢 Weekly (Sonnet)
  ███████████░░░  78% left
  resets Wed 23:00

CHATGPT

  🟢 5-hour
  ██████████████  100% left
  resets Thu 05:38

  🟢 Weekly
  ██████████████  100% left
  resets Wed 23:00
```

---

## Desktop Widget (NEW)

Native macOS WidgetKit widget — see how much AI quota you have left, right on your desktop or in Notification Center.

**Small widget:** Claude + ChatGPT percentages at a glance, color-coded by brand.

**Medium widget:** Side-by-side breakdown with session limits, weekly caps, progress bars, and reset times.

The widget syncs automatically with the menu bar app — no extra setup. Data updates every 60 seconds.

```bash
# Build the widget (requires Xcode)
cd AIQuotaBarWidget && ./build_widget.sh
# Then: right-click desktop → Edit Widgets → search "AI Quota"
```

> The widget is entirely optional — the menu bar app works without it. Requires macOS 14+ and Xcode 15+.

---

## Features

- **Zero-setup auth** — reads cookies directly from your browser (Chrome, Arc, Brave, Edge, Firefox, Safari)
- **Claude + ChatGPT** — tracks Claude.ai 5-hour/weekly limits and ChatGPT Codex 5-hour/weekly limits
- **Desktop widget** — native macOS WidgetKit widget with brand-colored progress bars
- **Multi-provider** — add OpenAI, MiniMax, GLM (Zhipu) API keys to see spending alongside usage
- **Burn rate + ETA** — predicts when you'll hit each limit based on your current pace
- **Pacing alerts** — notifies you when you're on track to hit a limit within 30 minutes
- **Auto-refresh on session expiry** — silently grabs fresh cookies when your session expires
- **macOS notifications** — alerts when you drop to 20% and 5% remaining for Claude and ChatGPT
- **Configurable refresh** — 1 / 5 / 15 min
- **Runs at login** — via LaunchAgent, toggle from the menu
- **Tiny footprint** — single-file Python app, no Electron, no background services beyond the app itself

---

## Coach: spend less for the same results

TokenCoach reads the transcripts that **Claude Code, Cowork and Codex** already write on
your Mac and keeps a local ledger of every prompt: tokens, model, project, API-equivalent
cost and how much quota it used. Nothing leaves your machine, except when you ask for an
analysis or a prompt rewrite (sent to Claude through your own `claude` CLI).

- **Nudges in Claude Code.** Before a prompt runs, TokenCoach can show a one-line tip in
  Claude Code: a session that re-reads 300k tokens on every reply, a broad "implement
  everything" ask (compared with your own history), a quick question on an expensive
  model, a prompt similar to an earlier expensive one, or nearly no quota left. It never
  blocks or rewrites your prompt. Toggle it in the menu (**Nudges in Claude Code**).
- **Lessons → your CLAUDE.md / AGENTS.md.** Patterns that repeat across sessions become
  lessons with a confidence score that is capped by how much evidence supports them. At
  **95%+** they can be applied in one click; below that you review the evidence and decide;
  with little evidence they keep collecting. Applied lessons live in a clearly marked
  block (the original file is backed up first) and can be removed from the dashboard.
- **Before / after.** Every applied lesson shows what changed afterwards: $ and agent
  responses per prompt, session length and peak context.
- **Improve.** Any costly prompt gets a tighter rewrite you can copy or save as a template.
- **Dashboard.** Click the menu bar icon → **Open dashboard ↗** (Chrome if installed).
  The simple view shows totals, the coach, a timeline and your costliest prompts;
  **Advanced** adds filters, quota over time, a weekday × hour map, breakdowns, sessions
  and every prompt. It is served only on `127.0.0.1` with a per-install key.
- **Import Chat Export…** — claude.ai and ChatGPT web chats are not stored locally;
  import their data export to include them. Their token counts are **estimates**.

What the numbers mean:

| | Claude Code / Cowork | Codex | Web chat imports |
|---|---|---|---|
| Tokens per prompt | exact, from logs | exact, from logs | estimated |
| API-equivalent $ | list price | nearest Claude tier¹ | — |
| Quota used per prompt | estimated from this app's quota readings | from Codex's reading after each response | — |

¹ OpenAI does not publish prices for the Codex models, so each is priced at the nearest
Claude tier, an assumption labelled in the dashboard: `*-sol`, `gpt-6-*` and the plain
`gpt-5.x` flagships ≈ Opus 5, `*-terra` ≈ Sonnet 5, `*-luna` / `*-mini` ≈ Haiku 4.5.
Change a mapping in `~/.claude_bar_config.json` with
`"ledger_model_equivalents": {"gpt-6-astra": "claude-sonnet-5"}`, or set exact prices with
`"ledger_prices": {"gpt-6-astra": {"in": 5, "out": 20, "read": 0.5}}` (USD per million tokens).
Use **Set Plan Prices…** to compare against your plans. The dashboard's **Claude / OpenAI**
switch shows each provider on its own.

"API-equivalent $" is what the same tokens would cost on the provider's API. On a
subscription you pay a flat fee, so treat it as a yardstick, not a bill.

From a terminal: `python3 claude_bar.py --ledger | --dashboard | --optimize | --import-export FILE`
(`--dashboard` writes a read-only copy; buttons work in the copy the app serves).

---

## Why not just check the settings page?

| | AIQuotaBar | Open settings page | Browser extension |
|---|---|---|---|
| Always visible | ✅ Menu bar + desktop widget | ❌ Manual tab switch | ⚠️ Badge only |
| Notifications | ✅ 20% + 5% left + pacing alerts | ❌ None | ⚠️ Varies |
| Claude + ChatGPT | ✅ All in one place | ❌ One at a time | ❌ |
| Desktop widget | ✅ Native WidgetKit | ❌ | ❌ |
| Privacy | ✅ Local only | ✅ | ⚠️ Depends on extension |
| Install | ✅ One command | ✅ Nothing | ❌ Store + permissions |
| No Electron | ✅ Single-file Python | ✅ | ❌ Often Electron |

---

## Requirements

- macOS 12+
- Python 3.10+
- A paid Claude or ChatGPT account
- Chrome, Arc, Brave, Edge, Firefox, or Safari with an active session

---

## Manual install

```bash
git clone https://github.com/cagdasatici/AIQuotaLeft.git
cd AIQuotaLeft
pip install -r requirements.txt
python3 claude_bar.py
```

---

## How it works

The app calls the same private usage API that `claude.ai/settings/usage` uses. It authenticates using your browser's existing session cookies (read locally — never transmitted anywhere except to `claude.ai`).

[`curl_cffi`](https://github.com/yifeikong/curl_cffi) is used to mimic a Chrome TLS fingerprint, which is required to pass Cloudflare's bot protection.

| API field | Displayed as |
|---|---|
| `five_hour` | 5-hour |
| `seven_day` | Weekly |
| `seven_day_sonnet` | Weekly (Sonnet) |
| `extra_usage` | Extra Usage toggle |

---

## Troubleshooting

**App doesn't appear in menu bar**
```bash
tail -50 ~/.claude_bar.log
```

**Cookies not detected**
Make sure you're logged into [claude.ai](https://claude.ai) in your browser, then click **Auto-detect from Browser** in the menu.

**Session expired / showing ◆ !**
The app will try to auto-detect fresh cookies from your browser. If that fails, click **Set Session Cookie…**.

**ChatGPT shows HTTP 401**
The browser can return an expired Codex access token. AIQuotaLeft now uses a fresh local Codex token when it belongs to the same account; if none is available, sign in at chatgpt.com and click **Refresh Now**.

---

## Roadmap

- [x] Homebrew tap (`brew tap cagdasatici/aiquotaleft https://github.com/cagdasatici/AIQuotaLeft`)
- [x] Native macOS desktop widget (WidgetKit)
- [x] Burn rate ETA + pacing alerts
- [ ] Linux system tray support
- [ ] Windows tray app
- [ ] Customizable notification thresholds
- [ ] Usage history graph
- [ ] Multiple Claude account support

---

## Contributing

PRs welcome. Open an issue first for large changes. See [Manual install](#manual-install) for dev setup. Logs: `~/.claude_bar.log`.

---

## Credits

Built on [AIQuotaBar](https://github.com/yagcioglutoprak/AIQuotaBar) by
[Toprak Yagcioglu](https://github.com/yagcioglutoprak) — the app, the provider
fetchers, the widget and the installer are his, under MIT. Issues and PRs that
aren't specific to the changes below belong upstream.

### Changes in this fork

- Menu bar and widget show quota **remaining** instead of used.
- Widget colour thresholds inverted to match (red/orange now mean *nearly out*).
- Widget progress bars drain as quota is consumed.
- Widget config intent no longer relies on an ambiguous `AIProvider.none`, which could
  compile to `Optional.none` and leave the widget blank.
- `build_widget.sh` drops the build-directory copy from LaunchServices, so the system
  can't host the widget from a stale build instead of `/Applications`.
- Renamed TokenCoach: per-prompt ledger for Claude Code, Cowork and Codex; dashboard;
  Claude Code nudges; lessons written to CLAUDE.md / AGENTS.md with before/after;
  prompt rewrites and templates; chat-export import.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Toprak Yagcioglu.

## Disclaimer

Not affiliated with or endorsed by Anthropic. Uses undocumented internal APIs that may change without notice.
