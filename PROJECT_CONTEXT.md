# TokenCoach — current context

A navigation snapshot, not a replacement for requirements or live evidence. Update it after a meaningful milestone.

## Snapshot — 2026-09-27: v1.0.0

- **Product:** macOS menu bar app. Quota left for Claude and ChatGPT (from AIQuotaBar), plus a per-prompt ledger of Claude Code, Cowork and Codex usage, a local dashboard (simple view + Advanced), Claude Code nudges, lessons written into CLAUDE.md / AGENTS.md with before/after, Improve, templates, chat-export import and a sample-data demo.
- **Pricing:** Anthropic and OpenAI list prices in `tokencoach/ledger.py` (checked 2026-09-27; OpenAI long-context rates above 272K). Unpublished models use a labelled sibling price. User overrides: `ledger_prices`, `ledger_model_equivalents`.
- **Layout:** install `~/.tokencoach`; data `~/Library/Application Support/TokenCoach`; logs `~/Library/Logs/TokenCoach`; LaunchAgents `io.github.cagdasatici.tokencoach{,.doctor,.widgethost}`; widget `/Applications/TokenCoachWidget.app`. Pre-rename installs are moved by `install.sh` (started automatically by `tokencoach/legacy.py` after their next auto-update); data folders move on first import of `tokencoach.config`.
- **Distribution:** one-line `install.sh`, Homebrew formula `Formula/tokencoach.rb` (tap = this repo), `uninstall.sh`.
- **Checks:** unit tests in `tests/`; an isolated `install.sh` run (`TOKENCOACH_NO_LAUNCH=1`); a Homebrew build from a local tap; the widget builds with Xcode.

## Where things are

| Task | Entry points |
|---|---|
| Menu bar UI, panel | `tokencoach/ui.py`, `tests/test_remaining.py` |
| Quota providers, reset times, auth | `tokencoach/providers.py`, `tests/test_reset_format.py` |
| Ledger, pricing, quota attribution | `tokencoach/ledger.py`, `tests/test_ledger.py` |
| Dashboard and its listener | `tokencoach/ledger_report.py`, `tokencoach/server.py` |
| Nudges, lessons, Improve | `tokencoach/nudge.py`, `tokencoach/coach.py`, `tokencoach/optimizer.py`, `tests/test_coach.py` |
| Sample data and README images | `tokencoach/demo.py`, `tokencoach/screenshots.py` (`--demo`, `--screenshots docs/images`) |
| Install, repair, remove | `install.sh`, `tokencoach-doctor.sh`, `restart.sh`, `uninstall.sh`, `Formula/tokencoach.rb` |
| Widget | `widget/` (`build_widget.sh`); Python tests don't replace an Xcode build |

## Open

- Nudge display in the interactive Claude Code UI: the hook output is accepted (verified with `claude -p`); confirm how it looks in a normal session.
- Codex has no prompt hook, so Codex gets coaching through AGENTS.md lessons only.
