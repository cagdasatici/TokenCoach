# AIQuotaLeft — working instructions

## Durable constraints

This is a credited fork of AIQuotaBar. The product displays **quota remaining**: provider usage is stored as used; invert exactly once at the display boundary and keep title/menu/widget consistent. Preserve upstream attribution and the README's fork-specific scope. Session limits drive the main percentage; weekly exhaustion remains visible. Modules live in `aiquotabar/`; `claude_bar.py` is the entry point, not the entire app. No direct `rumps.notification()`; use the existing notification wrapper. Do not add a session_key-only field or double-scale 0–100 values. Preserve optional widget behavior and browser detection order. Never print/cache credentials in new locations or commit account data. Keep the app lightweight, no Electron or web server; keep README concise and evidence honest. Growth claims and provider behavior from old planning notes are dated, not current facts. Do not restart/install the user's app merely to test a source edit.

## Efficient working loop

- For orientation or continuation, read [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md), then only the linked section relevant to the task. For a precise edit, inspect the named code and nearby tests first. Historical reviews are references, not a startup reading list.
- Search filenames with `rg --files`, then symbols with scoped `rg -n`. Read bounded sections; exclude dependencies, generated output and runtime/private data unless needed.
- Preserve existing working-tree changes. Use the smallest coherent change and focused verification first; run the full required gate before declaring completion. Do not repeat successful checks without a new change or unresolved concern.
- Default to one agent. Delegate only when requested and the independent work justifies its context cost. Keep completion evidence concise: result, relevant checks, remaining blocker.
- Update the current context when a milestone changes; replace stale summaries and link evidence instead of appending another review essay. Dates and test counts are snapshots, not permanent guarantees. Markdown guidance does not set model, effort, billing or hard token limits.

## Verification

```sh
# Use Python >=3.10 with requirements.txt installed, not macOS Python 3.9.
python3 -m unittest discover -s tests
# On this machine the existing dependency-equipped interpreter is:
/Users/cagdas/.ai-quota-bar/.venv/bin/python3 -m unittest discover -s tests
```

Run only checks relevant to the change, then any required release gate. Report environment limitations and failed checks explicitly.
