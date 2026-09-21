# AIQuotaLeft — current context

This is a navigation snapshot, not a replacement for requirements or live evidence. Update it after a meaningful milestone; keep history in existing records.

## Snapshot — 2026-09-20

HEAD `559ca3e`, with existing `scratch.md` preserved. **42 tests passed** using the installed Python 3.12 environment. Default macOS Python 3.9 lacks rumps and cannot parse/evaluate the module's union-type usage; that failed attempt is an environment mismatch, not a passing app check. No GUI, Keychain, live provider, install, or Xcode build was exercised.

Cursor support has now been removed from the menu bar, panel, widget payload/configuration, and provider registry. Claude and Codex usage rows are named `5-hour` and `Weekly` (with Claude's optional `Weekly (Sonnet)` row). The floating menu keeps each row on one line and renders nearby reset times relatively, e.g. `5h · +1d 21:16` and `W · +7d 16:16`, falling back to a short calendar date for more distant resets; when Claude has not started a 5-hour window, it truthfully says `starts on use`. Misleading repeated high-usage sample counts are no longer presented as “limit hits,” and ETA copy clearly marks its result as a pace-based estimate. **45 tests pass** using the installed Python 3.12 environment; `git diff --check` also passes.

Remaining-focused menu/widget, reset formatting, ChatGPT auth fixes and vanished-icon recovery exist. Runtime provider/session compatibility and fresh-install/widget validation remain the key acceptance work. Growth/adoption was not measured.

## Read only for the relevant task

| Task | Entry points / authority |
|---|---|
| Current product/attribution | `README.md`, especially “Changes in this fork” |
| UI/conversion | `aiquotabar/ui.py`, `tests/test_remaining.py` |
| Providers/reset/auth | `aiquotabar/providers.py`, `tests/test_reset_format.py`; fixtures only unless live checks requested |
| Widget | `AIQuotaBarWidget/`; Python source assertions do not replace an Xcode/runtime check |
| Installation/recovery | `install.sh`, `aiquotaleft-doctor.sh`, `restart_aiquotaleft.sh` |
| Historical growth strategy | `docs/AGENT_GUIDANCE_HISTORY.md`, `docs/planning/`; opt in for distribution tasks only |

## Next steps (written 2026-09-21)

Checked 2026-09-21: 45 tests pass; `89fdcf7` is pushed and is the installed copy in `~/.ai-quota-bar`; the menu bar app was restarted after that commit; the widget binaries were rebuilt with the 2026-09-20 changes. The features are done. What is missing is a recorded check that the app holds up in daily use. Only the owner can do it, in about 15 minutes:

1. YOU: Close the lid for at least 10 minutes, then open it and click the menu bar icon. The `Updated` time should become recent within about a minute.
2. YOU: In Terminal, run `pkill -f '.ai-quota-bar/claude_bar.py'`. The icon should come back by itself within about 10 seconds (launchd `KeepAlive`). If it does not, run `bash ~/.ai-quota-bar/aiquotaleft-doctor.sh`.
3. YOU: Remove the widget and add it again. It should show the same numbers as the menu bar.
4. YOU, when it happens naturally: after a Claude or ChatGPT login expires, the app should ask you to sign in rather than keep showing old numbers.
5. YOU, only if other people will install it: run the README install from a second macOS user account.

Agent, afterwards: add one dated line here with what passed or failed, fix any failure with a regression test, and commit. Keep this fork's reliability goal ahead of inherited star-chasing tasks unless the owner asks for distribution work. Never interpret stale percentage data as current quota.
