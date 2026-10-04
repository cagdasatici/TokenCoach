# TokenCoach — current context

A navigation snapshot, not a replacement for requirements or live evidence. Update it after a meaningful milestone.

## Snapshot — 2026-09-29: v1.1.0 + yield metrics, quota coverage fixes (pushed, not tagged)

- **Product:** macOS menu bar app. Quota left for Claude and ChatGPT (from AIQuotaBar), plus a per-prompt ledger of Claude Code, Cowork and Codex usage, a local dashboard (simple view + Advanced), Claude Code nudges, lessons written into CLAUDE.md / AGENTS.md with before/after, Improve, templates, chat-export import and a sample-data demo.
- **Health (v1.1.0):** `tokencoach/health.py` turns quota windows and habits into good / watch / critical. The menu bar shows percentages in bright white when healthy and soft yellow under quota pressure, without trailing markers; the dashboard shows the worst of quota and habits (habits cap at watch). The app writes the windows (with pace) into `usage.json`, which the dashboard reads; `--demo` uses `demo.sample_windows`, and `?health=watch|critical` previews the other states. The dashboard was restyled in the same change (Apple-like grouped layout). Checked with live data on 2026-09-28: the headline matched `health.py` for the real windows.
- **Yield:** `tokencoach --yield-install PATH` adds a git `prepare-commit-msg` hook (`tokencoach/trailer.py`) that tags commits made inside Claude Code with `Claude-Session: <id>` (from `CLAUDE_CODE_SESSION_ID`). `tokencoach/yield_metrics.py` scans tracked repos into the ledger (`commits`, `yield_repos`; `ledger.SCHEMA_VERSION` 5) and computes cost per accepted change, prompts per accepted change and rework, judged 7 days after each commit; the dashboard's "What it produced" and `tokencoach --yield` show them. Design, deviations from the brief and next steps: `docs/plans/2026-09-29-seats-gates-yield-brief.md`.
- **Quota attribution (`ledger.attribute_quota`, `ATTRIBUTION_VERSION` 3):** each rise in used-% is shared across the calls in that interval by weight. An interval that holds at the window's level gives its calls 0; a dip below it (stale reading) and calls outside any sampled interval stay NULL = unknown. A window is new after a fall of `RESET_DROP` points or when a reading comes a full window span (`WINDOW_SPAN`) after the earliest reading known to be in it, so small resets are recognised. The dashboard shows unknown quota as "—" and the 5-hour tile says what share of responses was measured.
- **Pricing:** Anthropic and OpenAI list prices in `tokencoach/ledger.py` (checked 2026-09-27; OpenAI long-context rates above 272K). Unpublished models use a labelled sibling price. User overrides: `ledger_prices`, `ledger_model_equivalents`.
- **Layout:** install `~/.tokencoach`; data `~/Library/Application Support/TokenCoach` (owner-only; the widget reads only its `widget/` subfolder); logs `~/Library/Logs/TokenCoach`; LaunchAgents `io.github.cagdasatici.tokencoach{,.doctor,.widgethost}`; widget `/Applications/TokenCoachWidget.app`. Pre-rename installs are moved by `install.sh` (started automatically by `tokencoach/legacy.py` after their next auto-update); data folders move on first import of `tokencoach.config`.
- **Distribution:** one-line `install.sh`, Homebrew formula `Formula/tokencoach.rb` (tap = this repo), `uninstall.sh`; Homebrew users run `tokencoach --cleanup` before `brew uninstall`. Auto-update (git installs) only fast-forwards a clean `main` checkout, and only to a commit signed by a key in `allowed_signers` as installed (unsigned pushes are never installed: sign commits on `main`); `requirements.txt` is hash-pinned (`--require-hashes`). Release: tag, attach `git archive` tarball as `TokenCoach-X.Y.Z.tar.gz`, then point the formula at it.
- **Checks:** unit tests in `tests/`; `ledger.SCHEMA_VERSION` must be bumped when the schema or `_migrate` changes; an isolated `install.sh` run (`TOKENCOACH_NO_LAUNCH=1`); a Homebrew build from a local tap; the widget builds with Xcode.

## Where things are

| Task | Entry points |
|---|---|
| Menu bar UI, panel | `tokencoach/ui.py`, `tests/test_remaining.py` |
| Quota providers, reset times, auth | `tokencoach/providers.py`, `tests/test_reset_format.py` |
| Ledger, pricing, quota attribution | `tokencoach/ledger.py`, `tests/test_ledger.py` |
| Dashboard and its listener | `tokencoach/ledger_report.py`, `tokencoach/server.py` |
| Health state (menu bar color, dashboard headline) | `tokencoach/health.py`, `tests/test_health.py` |
| Yield: commit trailer, commit scan, metrics | `tokencoach/trailer.py`, `tokencoach/yield_metrics.py`, `tests/test_yield.py` |
| Nudges, lessons, Improve | `tokencoach/nudge.py`, `tokencoach/coach.py`, `tokencoach/optimizer.py`, `tests/test_coach.py` |
| Sample data and README images | `tokencoach/demo.py`, `tokencoach/screenshots.py` (`--demo`, `--screenshots docs/images`) |
| Install, repair, remove | `install.sh`, `tokencoach-doctor.sh`, `restart.sh`, `uninstall.sh`, `Formula/tokencoach.rb` |
| Widget | `widget/` (`build_widget.sh`); Python tests don't replace an Xcode build |

## Open

- Release acceptance (TC3, planned on a fresh Mac mini) and the optional coaching experiment (TC4): `docs/plans/2026-09-29-remaining-release-work.md`. TC1, TC2 and their code follow-ups (flat intervals, dashboard quota gaps, screenshots) are done. The release after TC3 is **v1.2.0**, tagged and published only after TC3 passes (yield bumps the ledger schema to 5). Acceptance records: `docs/release-acceptance-1.2.0.md`.
- Codex has no prompt hook, so Codex gets coaching through AGENTS.md lessons only.
- Seats (WS1) and enforced gates (WS2) from the handoff brief are not started; the brief wants two weeks of yield baseline first. Confirm the trailer once in the terminal CLI (only verified in the desktop app).
- Release: `Formula/tokencoach.rb` needs no change for yield (the hook runs `python -m tokencoach.trailer`), but `uninstall.sh` and `--cleanup` now also remove repo hooks.

## Notes

- 2026-10-03: security audit (report in `.gstack/security-reports/`, local only). Fixed: signed-commit auto-update + hash-pinned deps; no cookie values or account replies in the log, log folder owner-only; Keychain asks for "Allow" and detection runs once per start; Analyze lessons capped at review and Apply-all shows the rules; widget sandbox narrowed to `widget/usage.json` (older widgets keep getting the old file until rebuilt); saved cookie / API keys never pre-filled into osascript; settings backup owner-only.

- 2026-09-28: `brew install` confirmed working end to end on the owner's Mac (1.0.1 from the tap).
- 2026-09-27: nudges confirmed displaying in an interactive Claude Code session.
- 2026-09-27: a demo started after the package was already imported bypassed the sandbox and rewrote the real global lesson files (restored from the ledger). The demo now refuses in that case, checks the demo flag at call time, and refuses to write outside its folder; backups never overwrite each other.
