"""Wrap the shared TokenCoach artwork in a macOS 1024px icon container."""
from pathlib import Path
import struct
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix="tokencoach-icon-") as folder:
    scaled = Path(folder) / "icon.png"
    subprocess.run(["sips", "-z", "1024", "1024",
                    str(root / "assets/tokencoach-logo.png"), "--out", str(scaled)],
                   check=True, capture_output=True)
    png = scaled.read_bytes()
icon = b"ic10" + struct.pack(">I", len(png) + 8) + png
output = root / "build/TokenCoach.icns"
output.parent.mkdir(exist_ok=True)
output.write_bytes(b"icns" + struct.pack(">I", len(icon) + 8) + icon)
