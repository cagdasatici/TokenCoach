# TokenCoach announcement draft

Prepared 2026-10-05. Unpublished; broad sharing awaits release acceptance and the
signed, notarized DMG. Recheck the installation page and tested platform support
before posting. The copy below describes the current development channel and
explicitly distinguishes it from the stable release.

---

TokenCoach is a macOS menu bar app for developers using Claude Code, Cowork and
Codex who want to understand where their prompts use tokens and quota.

See quota remaining, compare prompts and projects at API-equivalent prices, and
review coaching lessons you can edit and apply to `CLAUDE.md` or `AGENTS.md`.
Before/after comparisons help you investigate changes in your own habits; we are
not claiming proven savings. The accompanying walkthrough uses visibly labeled
sample data throughout, including synthetic before/after numbers.

The ledger stays on your Mac. Quota refreshes contact the providers; clicking
Analyze deeper or Improve sends prompt content to Claude through your own CLI.
Dollar amounts are API-equivalent comparisons, not subscription charges. Claude
quota per prompt is estimated, and unavailable measurements stay unknown.
Claude Code has prompt nudges; Codex coaching works through `AGENTS.md` lessons.
The providers' private quota endpoints may change.

Current source installation requires macOS 12+ and Python 3.10+; local prompt
tracking needs Claude Code, Cowork or Codex transcripts. The optional widget needs
macOS 14+ and Xcode. Homebrew currently ships v1.1.0; the walkthrough shows newer
features on moving signed `main`. A signed, notarized DMG is planned and is not yet
available.

[Try TokenCoach — installation options and sample-data demo](https://github.com/cagdasatici/TokenCoach#install).

Built on AIQuotaBar by Toprak Yagcioglu. Not affiliated with or endorsed by Anthropic
or OpenAI.
