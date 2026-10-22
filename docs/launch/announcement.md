# TokenCoach announcement draft

Prepared 2026-10-05, updated 2026-10-22 for the sign-in window and setup guide. Unpublished; broad sharing awaits release acceptance through Homebrew and the script route. Recheck the installation page and tested platform support
before posting. The copy below describes the current development channel and
explicitly distinguishes it from the stable release.

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

Current source installation requires macOS 12+ and Python 3.10+; local prompt
tracking needs Claude Code, Cowork or Codex transcripts. The optional widget needs
macOS 14+ and Xcode. Homebrew currently ships v1.1.0, which predates the sign-in window and setup
guide; the walkthrough shows newer features on moving signed `main`. The DMG is deferred and is not
available.

[Try TokenCoach — quick start and sample-data demo](https://github.com/cagdasatici/TokenCoach#quick-start).

Built on AIQuotaBar by Toprak Yagcioglu. Not affiliated with or endorsed by Anthropic
or OpenAI.
