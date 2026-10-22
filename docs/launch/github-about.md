# GitHub "About" proposal

Draft, 2026-10-22. **Not applied.** Changing the repository description and topics is public
and needs the owner's approval; nothing here has been set on GitHub.

## Current (read 2026-10-22)

> See what every Claude and ChatGPT prompt costs, and get coached to spend less for the same
> results. macOS menu bar app + local dashboard for Claude Code, Cowork and Codex. Built on AIQuotaBar.

Topics: `claude-code`, `codex`, `developer-tools`, `llm`, `macos`, `menu-bar`, `token-usage`.

Why change it: "spend less for the same results" reads as a savings claim TokenCoach doesn't
measure, it doesn't mention quota left (the first thing people see in the menu bar), and it
doesn't match the social card and README pitch.

## Proposed description (≤ 350 characters)

> macOS menu bar app: see the Claude and ChatGPT quota you have left, what each Claude Code,
> Cowork and Codex prompt would cost at API prices, and get coached out of costly habits.
> Local ledger and dashboard. Built on AIQuotaBar.

Shorter alternative:

> See what your AI prompts cost. Build better habits. macOS menu bar app for Claude Code,
> Cowork and Codex: quota left, API-equivalent cost per prompt, coaching. Built on AIQuotaBar.

## Proposed topics

Keep: `claude-code`, `codex`, `developer-tools`, `llm`, `macos`, `menu-bar`, `token-usage`.

Add: `claude`, `anthropic`, `chatgpt`, `openai-codex`, `ai-coding`, `usage-tracking`,
`quota`, `rumps`, `pyobjc`, `python`.

(GitHub allows up to 20 topics; this is 17.)

## Website field

Leave empty for now, or set it to the README quick start
(`https://github.com/cagdasatici/TokenCoach#quick-start`) once a release page exists.

## To apply (owner only)

```bash
gh repo edit cagdasatici/TokenCoach --description "…chosen text…"
gh repo edit cagdasatici/TokenCoach --add-topic claude,anthropic,chatgpt,openai-codex,ai-coding,usage-tracking,quota,rumps,pyobjc,python
```
