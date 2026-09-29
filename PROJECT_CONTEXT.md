# TokenCoach — current context

A navigation snapshot, not a replacement for requirements or live evidence. Update it after a meaningful milestone.

## Snapshot — 2026-09-28: v1.1.0

- **Product:** macOS menu bar app. Quota left for Claude and ChatGPT (from AIQuotaBar), plus a per-prompt ledger of Claude Code, Cowork and Codex usage, a local dashboard (simple view + Advanced), Claude Code nudges, lessons written into CLAUDE.md / AGENTS.md with before/after, Improve, templates, chat-export import and a sample-data demo.
- **Health (v1.1.0):** `tokencoach/health.py` turns quota windows and habits into good / watch / critical. The menu bar colors its percentages from quota only; the dashboard shows the worst of quota and habits (habits cap at watch). The app writes the windows (with pace) into `usage.json`, which the dashboard reads; `--demo` uses `demo.sample_windows`, and `?health=watch|critical` previews the other states. The dashboard was restyled in the same change (Apple-like grouped layout). Checked with live data on 2026-09-28: the headline matched `health.py` for the real windows.
- **Pricing:** Anthropic and OpenAI list prices in `tokencoach/ledger.py` (checked 2026-09-27; OpenAI long-context rates above 272K). Unpublished models use a labelled sibling price. User overrides: `ledger_prices`, `ledger_model_equivalents`.
- **Layout:** install `~/.tokencoach`; data `~/Library/Application Support/TokenCoach`; logs `~/Library/Logs/TokenCoach`; LaunchAgents `io.github.cagdasatici.tokencoach{,.doctor,.widgethost}`; widget `/Applications/TokenCoachWidget.app`. Pre-rename installs are moved by `install.sh` (started automatically by `tokencoach/legacy.py` after their next auto-update); data folders move on first import of `tokencoach.config`.
- **Distribution:** one-line `install.sh`, Homebrew formula `Formula/tokencoach.rb` (tap = this repo), `uninstall.sh`; Homebrew users run `tokencoach --cleanup` before `brew uninstall`. Auto-update (git installs) only fast-forwards a clean `main` checkout. Release: tag, attach `git archive` tarball as `TokenCoach-X.Y.Z.tar.gz`, then point the formula at it.
- **Checks:** unit tests in `tests/`; `ledger.SCHEMA_VERSION` must be bumped when the schema or `_migrate` changes; an isolated `install.sh` run (`TOKENCOACH_NO_LAUNCH=1`); a Homebrew build from a local tap; the widget builds with Xcode.

## Where things are

| Task | Entry points |
|---|---|
| Menu bar UI, panel | `tokencoach/ui.py`, `tests/test_remaining.py` |
| Quota providers, reset times, auth | `tokencoach/providers.py`, `tests/test_reset_format.py` |
| Ledger, pricing, quota attribution | `tokencoach/ledger.py`, `tests/test_ledger.py` |
| Dashboard and its listener | `tokencoach/ledger_report.py`, `tokencoach/server.py` |
| Health state (menu bar color, dashboard headline) | `tokencoach/health.py`, `tests/test_health.py` |
| Nudges, lessons, Improve | `tokencoach/nudge.py`, `tokencoach/coach.py`, `tokencoach/optimizer.py`, `tests/test_coach.py` |
| Sample data and README images | `tokencoach/demo.py`, `tokencoach/screenshots.py` (`--demo`, `--screenshots docs/images`) |
| Install, repair, remove | `install.sh`, `tokencoach-doctor.sh`, `restart.sh`, `uninstall.sh`, `Formula/tokencoach.rb` |
| Widget | `widget/` (`build_widget.sh`); Python tests don't replace an Xcode build |

## Open

- Codex has no prompt hook, so Codex gets coaching through AGENTS.md lessons only.

- Release acceptance (TC3, planned on a fresh Mac mini), the optional coaching experiment (TC4) and follow-ups from TC1/TC2 (quota attribution for flat intervals, stale screenshots): `docs/plans/2026-09-29-remaining-release-work.md`. TC1 (missing quota is unknown) and TC2 (evidence levels, observed before/after) are done.
## Notes

- 2026-09-28: `brew install` confirmed working end to end on the owner's Mac (1.0.1 from the tap).
- 2026-09-27: nudges confirmed displaying in an interactive Claude Code session.
- 2026-09-27: a demo started after the package was already imported bypassed the sandbox and rewrote the real global lesson files (restored from the ledger). The demo now refuses in that case, checks the demo flag at call time, and refuses to write outside its folder; backups never overwrite each other.
