"""Require the recorded runtime and build-tool versions before packaging."""
from importlib.metadata import version
from pathlib import Path
import re
import sys

if sys.version_info < (3, 10):
    raise SystemExit('Build Python must be 3.10 or newer')
for filename in ('requirements.txt', 'packaging/macos/requirements-build.txt'):
    for name, expected in re.findall(r'^([A-Za-z0-9_-]+)==([^\s\\]+)', Path(filename).read_text(), re.M):
        actual = version(name)
        if actual != expected:
            raise SystemExit(f'{name}: expected {expected}, installed {actual}; install the hash-pinned requirements')
print('Pinned runtime/build versions verified')
