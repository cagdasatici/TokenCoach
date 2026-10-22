# Installing, updating and removing TokenCoach

Requirements: macOS 12+ and Python 3.10+. Per-prompt tracking needs Claude Code, Cowork and/or
Codex on this Mac. The quota bars need a claude.ai or chatgpt.com sign-in (the built-in sign-in
window, your browser, or the Codex CLI). The optional desktop widget needs macOS 14+ and Xcode;
the installer builds it when Xcode is present.

## One-line installer (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/cagdasatici/TokenCoach/main/install.sh | bash
```

It numbers its progress, explains anything missing in plain words, installs into
`~/.tokencoach`, sets up start-at-login and (with Xcode) the widget, and ends by telling you to
look for ◆ in the menu bar. The setup guide then opens by itself; see the
[first-run guide](first-run.md).

This follows the moving `main` channel, which can include changes before a stable release. It
updates itself only by fast-forwarding a clean `main` checkout to commits signed by a key in
[`allowed_signers`](../allowed_signers), checked against the copy you already have, and installs
Python packages only if their hashes match `requirements.txt`. Local edits or another branch stop
auto-update.

## Homebrew (stable release)

```bash
brew tap cagdasatici/tokencoach https://github.com/cagdasatici/TokenCoach
brew trust --formula cagdasatici/tokencoach/tokencoach   # Homebrew 7 asks before loading formulae from other taps
brew install tokencoach
tokencoach &          # first run adds it to your login items
```

The formula currently ships **v1.1.0**, which predates the sign-in window, the setup guide and
yield tracking; those need the one-line installer until the next release is published. Homebrew
installs update with `brew update && brew upgrade tokencoach`; the app's git updater does not run.
After upgrading from v1.1.0 to a later release, run `tokencoach &` once so it can repair the login
item that points at the removed version folder. Release procedure:
[v1.2.0 publication procedure](release-publication-1.2.0.md).

## Downloaded app (not available yet)

A packaged TokenCoach.app exists in the source (`packaging/macos/`), but its download is deferred
and no build is published. When it ships it will be the only build that offers **Use my browser's
login**, because macOS then asks about TokenCoach itself rather than the shared Python. See
[macOS distribution](macos-distribution.md).

## Just look first: the sample-data demo

The demo uses made-up data in a separate temporary folder and doesn't read or change anything of yours:

```bash
git clone https://github.com/cagdasatici/TokenCoach && cd TokenCoach
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python tokencoach.py --demo
```

## Uninstall

- Script install: `bash ~/.tokencoach/uninstall.sh` (add `--purge` to delete your data and logs too).
- Homebrew: `tokencoach --cleanup && brew uninstall tokencoach`. The first step removes the login
  item and the Claude Code hook, which Homebrew can't.

Applied lessons remain in your `CLAUDE.md` / `AGENTS.md` files, even with `--purge`. Use
**Remove** in the dashboard before uninstalling, or delete the marked TokenCoach block afterwards.
`--purge` deletes the claude.ai cookies saved in TokenCoach's settings, but uninstalling does not
clear the sign-in window's own login from WebKit's storage on your Mac.

## Upgrading from AIQuotaBar

Run the one-line installer; it moves your settings and quota history into TokenCoach. Details in
the [README FAQ](../README.md#faq).
