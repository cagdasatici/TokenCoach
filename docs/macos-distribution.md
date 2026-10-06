# macOS DMG distribution

Implementation added 2026-10-05. **No signed, notarized public DMG exists yet.**
The local development image is a test artifact. PS8 acceptance remains open.

## Installation for the packaged release

Once PS3 publishes the accepted assets, the primary download will be the matching
`TokenCoach-X.Y.Z-arm64.dmg` (Apple Silicon) or
`TokenCoach-X.Y.Z-x86_64.dmg` (Intel) from the project's GitHub release.

1. Download the verified image for your Mac, open it, and drag TokenCoach to Applications.
2. Eject the image, then open TokenCoach from Applications normally through Gatekeeper.
3. Find ◆ in the menu bar. Open its panel and choose Open Dashboard; use ⚙ for settings.
4. Sign in to the relevant provider for quota, or use local agent history without quota access.
   Normal Keychain/browser permission prompts remain under your control.
5. Enable Launch at Login in Settings if wanted. The packaged app does not enable it automatically.

The core package contains Python and dependencies and does not download them at launch.
It includes no desktop widget. The optional source widget requires macOS 14+ and Xcode;
the core app works without it. Analyze/Improve require the separate Claude CLI, and
opt-in yield tracking requires Git; neither is needed to launch the app or read its local ledger.

The release target is **macOS 14+**, with separately labelled arm64 and x86_64 images.
Both require clean-account acceptance before that support is advertised as verified.
The initial development build uses this host's macOS **27.0.1 / arm64** baseline.
It provides no evidence for Intel or macOS 14. The build checks every bundled Mach-O
CPU slice and minimum OS, rejecting a release if a dependency requires newer than 14.0.

## Existing installations, upgrades and removal

Quit manually started old copies before opening the bundle. If a script/Homebrew login
item exists, the bundle asks before retiring TokenCoach's main, doctor and widget-host
agents and its exact script-installer cron entry. It retains data, settings and applied
lessons, reuses the dashboard secret, and repoints the nudge and existing opt-in git hooks.
It preserves other applications' agents, unrelated cron entries and git hooks belonging
to the repository owner. Missing tracked repositories are skipped; inaccessible hooks
are reported. Keep the old installation until any hook-access issues are resolved.
Custom watchdog cron commands require separate review; they are not broadly deleted.
Do not run both installation routes' login/watchdog mechanisms together.

Upgrade by quitting TokenCoach, replacing the app in Applications from a newer verified
DMG, and reopening it. Keep the same app location so login and hook paths remain valid.
The signed bundle never runs the git checkout updater. Data stays in
`~/Library/Application Support/TokenCoach`; the bundled executable's version includes its
candidate revision and marks development builds containing working-tree edits.

Before removal choose **⚙ → Prepare for Removal…**, confirm cleanup, and move the app
to Trash after it quits. Cleanup removes TokenCoach agents and its prompt/git hooks.
History, settings, backups and applied instruction-file lesson blocks remain. Remove
lessons from the dashboard first if you want their managed blocks removed. An access
failure reports incomplete cleanup and leaves the app available for retry.

## Build and notarization

Build on each architecture using a Python/runtime compiled for the macOS 14 baseline.
A newer host's Homebrew Python can require that host's OS and fail the release check.
Use a clean checkout of the signed candidate, with the final release `VERSION` set in
`tokencoach/version.py`. Do not put certificates, passwords or account data in the checkout.

Install `requirements.txt` and `packaging/macos/requirements-build.txt` into a dedicated
build environment using `pip install --require-hashes -r ...` for each file. The build
tools are separate from the core app's requirements. Set `TOKENCOACH_BUILD_PYTHON` to
that environment's Python (default: `.venv/bin/python`).

Provision a Developer ID Application identity and a `notarytool` Keychain profile on
the build Mac using Apple's tooling outside this repository. Then run:

```sh
export TOKENCOACH_SIGN_IDENTITY='Developer ID Application: <name> (<team>)'
export TOKENCOACH_NOTARY_PROFILE='<existing Keychain profile name>'
export TOKENCOACH_ARCH=arm64  # or x86_64 on its build Mac
scripts/build-dmg.sh
```

The script refuses missing signing access, a development version, an unsigned candidate
or a dirty checkout. PyInstaller signs executable components; the builder verifies the
bundle, submits and staples the app, checks Gatekeeper, creates the image with an
Applications shortcut and installation instructions, signs/notarizes/staples the image,
and writes a portable SHA-256 sidecar plus build and dependency records. Credentials
are read from Keychain, not command-line passwords or repository files. Hardened-runtime entitlements permit executable memory for Python/FFI and preserve
existing provider browser-quota reads through Apple Events. A purpose description
accompanies the normal per-browser permission prompt; users may decline. This follows
[Apple's Apple Events entitlement documentation](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.automation.apple-events).
No permissions are added solely for dashboard tab reuse.

`.github/workflows/release.yml` is a manual candidate build on isolated, maintainer-owned
macOS signing runners labelled `tokencoach-signing` and `ARM64`/`X64`. Configure the
`macos-release` environment with `BUILD_PYTHON`, `DEVELOPER_ID_APPLICATION` and
`NOTARY_KEYCHAIN_PROFILE` variables. The external Python environment must already have
the hash-pinned runtime/build dependencies. The workflow runs the suite and uploads
candidate artifacts; it does not publish a release. Runner provisioning/CI execution
has not been validated here.

A local development build uses `scripts/build-dmg.sh --development`. It is explicitly
named `DEVELOPMENT`, uses ad-hoc signing, and is never a release substitute. Do not give
Gatekeeper-bypass instructions to users or publish that image as accepted.

The packaging configuration follows [PyInstaller's macOS bundle/signing documentation](https://www.pyinstaller.org/en/stable/usage.html).

## Validation before publication

Record path I in `release-acceptance-1.2.0.md`: candidate SHA, image checksum, macOS/CPU
matrix, browser download, Gatekeeper behavior, ordinary launch/menu/dashboard, permission
choices, empty/unavailable and working data, ejection/relaunch, login startup, app
replacement, script/Homebrew migration, retained data and UI removal. Every declared
target needs passing evidence. The development image and Python tests do not close PS8.
PS3 publishes the accepted images and checksum sidecars alongside the source archive.

Dashboard regression checks use generated sample HTML only. See
`tests/dashboard_refresh.cjs`; install `jsdom@26.1.0` into a temporary tooling directory,
then run it with `NODE_PATH` pointing at that directory's `node_modules`. The fixture
must come from `demo.prepare()` and `build_report(..., live={...})` in a fresh process
with `TOKENCOACH_DEMO=1` and a temporary `TOKENCOACH_DATA_DIR`. Never use personal data.
