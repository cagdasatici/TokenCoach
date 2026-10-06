"""Fail if a bundled Mach-O needs a newer macOS or has the wrong CPU slice."""
from pathlib import Path
import re
import subprocess
import sys

bundle = Path(sys.argv[1])
arch = sys.argv[2]
maximum = tuple(int(v) for v in sys.argv[3].split('.')[:2])
magic = {b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xfe\xed\xfa\xce', b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf'}
seen = set()
for path in bundle.rglob('*'):
    if not path.is_file() or path.resolve() in seen:
        continue
    seen.add(path.resolve())
    with path.open('rb') as stream:
        if stream.read(4) not in magic:
            continue
    subprocess.run(['lipo',str(path),'-verify_arch',arch],check=True,capture_output=True)
    commands = subprocess.run(['otool','-arch',arch,'-l',str(path)],check=True,capture_output=True,text=True).stdout
    versions = re.findall(r'\bminos\s+(\d+(?:\.\d+)+)',commands)
    versions += re.findall(r'cmd LC_VERSION_MIN_MACOSX\s+cmdsize \d+\s+version (\d+(?:\.\d+)+)',commands)
    if not versions:
        raise SystemExit(f'Cannot verify minimum macOS: {path}')
    for version in versions:
        minimum = tuple(int(v) for v in version.split('.')[:2])
        if minimum > maximum:
            raise SystemExit(f'{path.name} requires macOS {version}; rebuild on the supported baseline')
print(f'Bundled Mach-O files verified for {arch}, minimum macOS <= {sys.argv[3]}')
