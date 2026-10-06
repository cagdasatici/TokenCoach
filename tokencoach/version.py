"""Build identity shared by the CLI and About; no account/config imports."""
from pathlib import Path
import subprocess
import sys
import json

# Set to the release number before tagging; development builds stay explicit.
VERSION = "1.2.0.dev0"
# git archive fills this in, preserving identity in Homebrew release archives.
ARCHIVE_REVISION = "$Format:%H$"


def version_string():
    if getattr(sys, "frozen", False):
        identity = json.loads((Path(sys._MEIPASS) / "build-identity.json").read_text())
        return identity["version"] + f" ({identity['revision'][:12]}{' dirty' if identity.get('dirty') else ''})"
    root = Path(__file__).resolve().parent.parent
    revision = ARCHIVE_REVISION
    dirty = False
    if revision.startswith("$"):
        revision = ""
        # Never describe an unrelated enclosing repository after installation.
        if (root / ".git").exists():
            try:
                result = subprocess.run(
                    ["git", "-C", str(root), "rev-parse", "HEAD"],
                    capture_output=True, text=True, timeout=2, check=True,
                )
                revision = result.stdout.strip()
                status = subprocess.run(
                    ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=normal"],
                    capture_output=True, text=True, timeout=2, check=True,
                )
                dirty = bool(status.stdout.strip())
            except (OSError, subprocess.SubprocessError):
                revision = ""
    suffix = f" ({revision[:12]}{' dirty' if dirty else ''})" if revision else " (revision unavailable)"
    return VERSION + suffix
