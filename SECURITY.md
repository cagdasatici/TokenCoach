# Security policy

Report suspected vulnerabilities through [GitHub private vulnerability reporting](https://github.com/cagdasatici/TokenCoach/security/advisories/new).
Private reporting was enabled and verified through the repository API on 2026-10-05.
A GitHub account is required. Do not put security reports in public issues.
If the form is unavailable, wait and retry; do not publish sensitive details as a fallback.

Describe the affected version/build, installation method, macOS version, impact,
and minimal reproduction steps with synthetic data. Never send credentials, cookies,
API keys, dashboard authentication URLs, prompt contents or account databases.
Coordinate any additional diagnostic sharing privately and redact it first.

This is a volunteer project: there is no guaranteed response time or security SLA.
The current stable release and current main branch are the investigation targets;
older versions may require upgrading for a fix. Development builds are not accepted releases.
Please allow time for investigation and coordinate disclosure through the private report.

## How TokenCoach handles your logins

This describes v1.2.0 and the current `main` channel. Older Homebrew installs (v1.1.0)
predate the sign-in window and the setup guide; `brew upgrade tokencoach` brings them up to date.

**Built-in sign-in window** (`tokencoach/signin.py`). **Sign in to Claude…** opens a window that
loads `https://claude.ai/login` in Apple's WebKit. It uses WebKit's default persistent storage for
the app, so the window keeps its own claude.ai login on your Mac, separate from your browsers.
Google sign-in opens in a pop-up that shares that storage. Once a session exists, TokenCoach takes
only the `sessionKey`, `lastActiveOrg` and `routingHint` cookies set for claude.ai (never Cloudflare
or other cookies), validates them against `claude.ai/api/organizations`, and saves them in
`~/Library/Application Support/TokenCoach/config.json`, which is readable only by your macOS user
(folder 0700, file 0600). Cookie values are never written to the log. The window needs no macOS
permissions.

**Following your browser's login.** **Auto-detect from Browser** (⚙ menu) reads the claude.ai and
chatgpt.com cookies from installed browsers; for Chrome-family browsers macOS asks for Keychain
access to the browser's "Safe Storage" key (choose **Allow**, not **Always Allow**). TokenCoach
looks once at start and again only when you ask or a session expires, and doesn't ask when macOS's
privacy protection keeps it out of the browser's folder.

The guided **Use my browser's login** flow (`_follow_browser_login` in `tokencoach/ui.py`) is offered
only in the packaged TokenCoach.app, whose download is not published yet. It explains and then
triggers macOS's "access data from other apps" prompt and the Keychain prompt, and if macOS still
blocks access, opens Privacy & Security → Full Disk Access with a **Check Again** button. Script and
Homebrew installs don't offer it: they run as the shared Python interpreter, and granting that
interpreter access to other apps' data would expose browser cookies to every Python script on the Mac.

**Where credentials go.** Claude cookies are sent only to claude.ai and ChatGPT cookies only to
chatgpt.com, to read quota. Without a ChatGPT browser session, TokenCoach reads the Codex CLI's
sign-in (`~/.codex/auth.json`) read only, never copies it, and sends it only to chatgpt.com. Saved
cookies and API keys are never pre-filled into dialogs.

**Local dashboard** (`tokencoach/server.py`). The dashboard listener binds to `127.0.0.1` only.
Every request needs the per-install token (in the page URL, or a custom header for actions), and
the Host header must be `127.0.0.1` or `localhost` on that port, which defeats DNS rebinding. It
is standard library only and is never exposed to your network.

**Updates.** Script installs fast-forward only a clean `main` checkout, only to commits signed by a
key in `allowed_signers` as already installed, and install Python packages only when their hashes
match `requirements.txt`. Homebrew installs update through `brew upgrade`.

**Prompt content.** The ledger, including prompt text, stays in a local SQLite file. Prompt
content leaves your Mac only when you click **Analyze deeper** or **Improve**, which run your own
`claude` CLI with tools off.
