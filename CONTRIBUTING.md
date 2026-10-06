# Contributing and support

For setup, start with the [first-run guide](docs/first-run.md) and
[README troubleshooting](README.md#troubleshooting). Report reproducible bugs or
ask usage questions in [GitHub Issues](https://github.com/cagdasatici/TokenCoach/issues).
Use the bug template for problems. Search existing issues first.
For vulnerabilities, follow [SECURITY.md](SECURITY.md).

Include the version/build from About TokenCoach or `tokencoach --version`, macOS
version, Intel/Apple silicon, installation method, and steps with expected/actual
results. For script installs, run
`~/.tokencoach/.venv/bin/python ~/.tokencoach/tokencoach.py --version`.
Older releases may not support it; report the installed release or revision if known.
Only share short diagnostic excerpts you have manually reviewed and redacted.
Never attach raw logs, configuration, data folders, ledger databases, credentials,
cookies, dashboard URLs, prompts, transcripts or personal screenshots.

Support and review are best effort, with no guaranteed response time. Open an issue
before a large change so scope can be agreed; small fixes can go directly to a pull
request with the problem, behavior change and validation explained.

Read [AGENTS.md](AGENTS.md) and [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).
Use Python 3.10 or newer and a virtual environment, install `requirements.txt`, then run
`python -m unittest discover -s tests`. Keep changes focused and preserve attribution,
remaining-quota semantics, local-only dashboard security and demo isolation.
Use `tokencoach.py --screenshots` for public screenshots with sample data.
Do not restart or reinstall a running app just to test source edits.

Version identity lives in `tokencoach/version.py`. Set `VERSION` to the release number
before tagging, and to the next `.dev0` number for development. Publish release sources
with `git archive`: `.gitattributes` embeds the commit in that module, so archive-based
Homebrew builds and script installs from the same revision show the same identity.
A modified checkout also displays `dirty`; missing metadata displays `revision unavailable`.
