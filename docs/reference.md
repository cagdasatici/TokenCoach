# TokenCoach reference

Details moved out of the [README](../README.md): what the numbers mean, the live dashboard, yield
measurement and the command line.

## What the numbers mean

| | Claude Code / Cowork | Codex | claude.ai / chatgpt.com chats |
|---|---|---|---|
| Tokens per prompt | exact, from local transcripts | exact, from local transcripts | estimated from an imported data export |
| API-equivalent $ | Anthropic list prices (checked 2026-09-27) | OpenAI list prices¹ | not priced |
| Quota per prompt | estimated from TokenCoach's quota readings | from Codex's own reading after each response | — |

**Quota** percentages show what is **left**, including the weekly limit. Zero means exhausted;
"—" or "No reading" means no usable measurement, not zero.

**API-equivalent $** is what the same tokens would cost on the provider's API. On a subscription
you pay a flat fee, so treat it as a yardstick for comparing prompts, projects and models, not as
a bill. **Set Plan Prices…** in the menu shows what your plan is worth against it.

**Claude quota per prompt** is estimated: each rise in the 5-hour used-% is shared across the
responses in that interval by weight. Responses outside any measured interval stay unknown, and the
dashboard says what share of responses was measured.

**Health** (healthy / watch / action needed) is the worst of quota left now, weekly pace and habits
(cost per prompt against your own usual; habits alone never go past watch). A provider with no
reading does not count as having quota available.

¹ Standard-tier prices from OpenAI's pricing page (checked 2026-09-27), including long-context
rates above 272K tokens. A model without a published price (e.g. `codex-auto-review`) is priced
like its closest published sibling and labelled *estimated*. Override anything in
`~/Library/Application Support/TokenCoach/config.json`:

```json
{
  "ledger_prices": {"gpt-6-astra": {"in": 10, "read": 1, "out": 50}},
  "ledger_model_equivalents": {"codex-auto-review": "gpt-5.6-luna"},
  "ledger_plans": {"claude": 100, "chatgpt": 20}
}
```

## The live dashboard

**Open dashboard** serves the page from `127.0.0.1` only, with a private access token in the
address. It keeps one address across restarts when port 47821 is free, so you can bookmark it, but
don't share it. A visible, idle page fetches fresh data every five minutes and keeps your filters,
view and scroll; it waits while you edit lessons, keep a rewrite open or run an action. The header
shows the last completed usage scan and any stale or unavailable state; quota readings keep their
own timestamps. If the port is taken, you get a labelled read-only snapshot instead of a silently
different address: resolve the conflict and restart the app. Opening uses macOS `open`, so repeated
clicks may create duplicate tabs depending on your browser.

## Coach lessons

Evidence levels count separate sessions showing the pattern: **limited** (1–2), **moderate** (3–7)
or **strong** (8+), a rule of thumb rather than a measured accuracy. A clear pattern with strong
evidence can be written in one click; with moderate evidence you review it and decide; with less
it keeps collecting. Lessons proposed by **Analyze deeper** are never applied without you reading
and confirming the exact rule. Edited lessons are yours, and later analyses never overwrite them.

Before/after compares each applied lesson against the four weeks before: $ per prompt, agent
responses per prompt, session length, peak context and quota per prompt (with how many prompts had
quota data). Both periods show their dates and size, and small samples are marked. Other things
change too, so it is an observed change, not proof that the lesson caused it.

## Yield

```sh
tokencoach --yield-install ~/code/my-repo    # once per repository
tokencoach --yield                           # the numbers; also in the dashboard
tokencoach --yield-remove ~/code/my-repo     # undo
```

This adds a git `prepare-commit-msg` hook that appends a `Claude-Session: <id>` line to commits
made *inside Claude Code*. Commits you make in a terminal get nothing, and the hook never blocks a
commit. It refuses to touch a hook that isn't its own, and a `core.hooksPath` outside the
repository. The dashboard's **What it produced** shows, by week and by model:

- **Cost per accepted change**: session cost ÷ accepted commits. Sessions that made no commit
  count against it.
- **Prompts per accepted change**: how much of your attention each surviving commit took.
- **Rework**: the share of commits followed within 7 days by a fix (a commit whose subject says
  fix, bug, regression or revert) to one of the same files.

A commit is *accepted* once it is a week old and, in that week, was neither reverted nor dropped
from every branch. Younger work is listed as pending. "Dropped" is noticed by TokenCoach's own
scans, so squash-merging and then deleting a branch counts as dropped, and on a file that many
commits touch, one fix counts against all of them. Compare a period with an earlier one measured
the same way, not with an absolute target.

## Command line

`tokencoach --help` with Homebrew, otherwise
`~/.tokencoach/.venv/bin/python ~/.tokencoach/tokencoach.py --help`. Useful options: `--ledger`,
`--dashboard`, `--optimize`, `--import-export FILE` (estimated tokens from a claude.ai / ChatGPT
data export), `--yield`, `--demo`, `--version`, `--cleanup`.
