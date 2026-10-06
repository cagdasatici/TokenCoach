"""Version reporting must work without UI dependencies or personal data."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tokencoach import version


class VersionTests(unittest.TestCase):
    def test_cli_does_not_import_ui_or_config(self):
        script = (
            "import sys; from tokencoach.__main__ import main; "
            "sys.argv=['tokencoach', '--version']; main(); "
            "assert 'tokencoach.config' not in sys.modules; "
            "assert 'tokencoach.ui' not in sys.modules"
        )
        result = subprocess.run([sys.executable, '-c', script],
                                capture_output=True, text=True, check=True)
        self.assertTrue(result.stdout.startswith('TokenCoach ' + version.VERSION))

    def test_checkout_revision_and_dirty_state(self):
        results = [subprocess.CompletedProcess([], 0, 'a' * 40 + '\n'),
                   subprocess.CompletedProcess([], 0, ' M README.md\n')]
        with patch.object(version.Path, 'exists', return_value=True), \
                patch.object(version.subprocess, 'run', side_effect=results):
            self.assertEqual(version.version_string(), version.VERSION + ' (aaaaaaaaaaaa dirty)')

    def test_missing_git_is_honest(self):
        with patch.object(version.Path, 'exists', return_value=True), \
                patch.object(version.subprocess, 'run', side_effect=OSError):
            self.assertIn('revision unavailable', version.version_string())

    def test_installed_copy_ignores_enclosing_repository(self):
        with patch.object(version.Path, 'exists', return_value=False), \
                patch.object(version.subprocess, 'run') as run:
            self.assertIn('revision unavailable', version.version_string())
            run.assert_not_called()

    def test_git_archive_preserves_identity_without_git(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / 'source'
            repo.mkdir()
            (repo / 'tokencoach').mkdir()
            (repo / 'tokencoach/version.py').write_text((root / 'tokencoach/version.py').read_text())
            (repo / '.gitattributes').write_text((root / '.gitattributes').read_text())
            env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
            def git(*args):
                return subprocess.run(['git', '-C', str(repo), *args], env=env,
                                      capture_output=True, check=True)
            git('init')
            git('add', '.')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                '-c', 'commit.gpgsign=false', 'commit', '-m', 'Fixture')
            revision = git('rev-parse', 'HEAD').stdout.decode().strip()
            import io
            import tarfile
            archive = tarfile.open(fileobj=io.BytesIO(git('archive', 'HEAD').stdout))
            source = archive.extractfile('tokencoach/version.py').read().decode()
            namespace = {'__file__': str(Path(tmp) / 'installed/tokencoach/version.py')}
            exec(compile(source, 'version.py', 'exec'), namespace)
            self.assertEqual(namespace['version_string'](), version.VERSION + f' ({revision[:12]})')
