# TokenCoach announcement draft

Prepared 2026-10-05, updated 2026-11-09 for the published v1.2.0. Unpublished draft. Recheck the
installation page before posting.

---

TokenCoach is a macOS menu bar app for developers using Claude Code, Cowork and
Codex who want to understand where their prompts use tokens and quota.

Getting started takes one Terminal command. A short setup guide then opens by
itself and offers **Sign in to Claude…**: a small window showing claude.ai's own
login page (Google sign-in works), with no macOS permission prompts. Every step
can be skipped; local transcript tracking works without signing in.

See quota remaining, compare prompts and projects at API-equivalent prices, and
review coaching lessons you can edit and apply to `CLAUDE.md` or `AGENTS.md`.
Before/after comparisons help you investigate changes in your own habits; we are
not claiming proven savings. The accompanying walkthrough uses visibly labeled
sample data throughout, including synthetic before/after numbers.

The ledger stays on your Mac. The sign-in window keeps its own claude.ai login,
and TokenCoach sends those cookies only to claude.ai and never logs them. Quota refreshes contact the providers; clicking
Analyze deeper or Improve sends prompt content to Claude through your own CLI.
Dollar amounts are API-equivalent comparisons, not subscription charges. Claude
quota per prompt is estimated, and unavailable measurements stay unknown.
Claude Code has prompt nudges; Codex coaching works through `AGENTS.md` lessons.
The providers' private quota endpoints may change.

Requires macOS 12+. Install with Homebrew (stable v1.2.0, brings its own Python) or the one-line
script (latest signed `main`, needs Python 3.10+ and git, adds the optional widget on Macs with
Xcode and macOS 14+). Local prompt tracking needs Claude Code, Cowork or Codex on the same Mac.

[Try TokenCoach — quick start and sample-data demo](https://github.com/cagdasatici/TokenCoach#quick-start).

Built on AIQuotaBar by Toprak Yagcioglu. Not affiliated with or endorsed by Anthropic
or OpenAI.
