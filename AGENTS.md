# TokenCoach — working instructions

## Durable constraints

- **Attribution.** TokenCoach is built on AIQuotaBar by Toprak Yagcioglu. Keep the credit in README, LICENSE and the app's About box. The old names appear in code only where needed to migrate pre-rename installs (`install.sh`, `tokencoach/legacy.py`, `tokencoach/config.py`, `claude_bar.py`).
- **Quota is shown as remaining.** Providers report usage; invert exactly once at the display boundary and keep title, menu, panel and widget consistent. Session limits drive the main percentage; weekly exhaustion stays visible.
- **Privacy.** Never print or cache credentials in new places, never commit account data, and never put personal data in screenshots: README images come only from `tokencoach.py --screenshots`, which uses the sample data in `tokencoach/demo.py`.
- **Lightweight.** No Electron and no general web server. The one exception is the stdlib dashboard listener in `tokencoach/server.py` (127.0.0.1 only, per-install token, Host check); do not widen it.
- **The person stays in control.** The Claude Code nudge hook must never block or rewrite a prompt and must stay silent on failure. Lessons edit instruction files only inside the managed block, after a backup, and only when confident or confirmed. `--demo` must never touch the person's real files or settings.
- **Honest numbers.** Label estimates as estimates (Claude quota per prompt, chat imports, models without a published price). Date the price tables and cite their source.
- Code lives in `tokencoach/`; `tokencoach.py` is the launcher. Use the notification wrapper, not `rumps.notification()`. Don't restart or reinstall the person's running app just to test a source edit.

## Working loop

- For orientation read [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md), then only the code the task touches and its tests.
- Keep existing working-tree changes. Make the smallest coherent change, verify it, then run the full test suite before calling it done.
- Update PROJECT_CONTEXT.md when a milestone changes; replace stale summaries rather than appending.

## Verification

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # Python >= 3.10
.venv/bin/python -m unittest discover -s tests
.venv/bin/python tokencoach.py --demo          # dashboard with sample data
TOKENCOACH_NO_LAUNCH=1 TOKENCOACH_DIR=/tmp/tc TOKENCOACH_REPO="$PWD" bash install.sh   # install without touching the system
```

Report environment limitations and failed checks explicitly.
