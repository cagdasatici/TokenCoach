## What and why

<!-- The problem, and what this changes for the person using TokenCoach. -->

## How it was checked

- [ ] `python -m unittest discover -s tests` passes
- [ ] For anything visible: tried with `python tokencoach.py --demo` (sample data only)

## Checklist

- [ ] No credentials, cookies, dashboard URLs, prompts or personal screenshots in the diff or description
- [ ] Quota is still shown as remaining; estimates are still labelled as estimates
- [ ] Hooks still never block: the Claude Code nudge and the git trailer exit quietly on failure
- [ ] `--demo` still cannot touch real files or settings
- [ ] Attribution to AIQuotaBar is unchanged
