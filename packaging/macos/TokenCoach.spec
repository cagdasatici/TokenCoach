# Build only on macOS, using a Python/runtime built for the declared minimum OS.
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).parents[1]
identity = os.environ.get('TOKENCOACH_SIGN_IDENTITY')
arch = os.environ['TOKENCOACH_ARCH']
version = os.environ['TOKENCOACH_BUILD_VERSION']
a = Analysis([str(root / 'tokencoach.py')], pathex=[str(root)],
             datas=[(str(root / 'assets'), 'assets'), (str(root / 'LICENSE'), '.'), (str(root / 'build/build-identity.json'), '.')],
             hiddenimports=collect_submodules('tokencoach'),
             excludes=['tkinter', 'pytest'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='TokenCoach',
          console=True, target_arch=arch, codesign_identity=identity,
          entitlements_file=str(root / 'packaging/macos/entitlements.plist'))
coll = COLLECT(exe, a.binaries, a.datas, name='TokenCoach')
app = BUNDLE(coll, name='TokenCoach.app', bundle_identifier='io.github.cagdasatici.tokencoach',
             version=version, icon=str(root / 'build/TokenCoach.icns'), info_plist={
                 'CFBundleShortVersionString': version, 'CFBundleVersion': version,
                 'LSUIElement': True, 'LSMinimumSystemVersion': os.environ['TOKENCOACH_MIN_MACOS'],
                 'NSHighResolutionCapable': True,
                 'NSAppleEventsUsageDescription': 'TokenCoach reads quota from your signed-in browser. You can decline browser access and still track local agent usage.',
                 'NSHumanReadableCopyright': 'TokenCoach, built on AIQuotaBar by Toprak Yagcioglu',
             })
