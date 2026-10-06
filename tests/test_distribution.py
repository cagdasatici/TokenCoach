"""Bundle paths, lifecycle safety, and fixed dashboard address. No real setup."""
import os
import tempfile
os.environ.setdefault('TOKENCOACH_DATA_DIR', tempfile.mkdtemp(prefix='tokencoach-test-'))
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


class BundleLifecycle(unittest.TestCase):
    def test_frozen_login_and_hooks_use_the_app_executable(self):
        from tokencoach import runtime, nudge, trailer, update
        exe = '/Applications/TokenCoach.app/Contents/MacOS/TokenCoach'
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', exe):
            self.assertEqual(runtime.launch_args(), [exe])
            self.assertEqual(runtime.app_bundle(), Path('/Applications/TokenCoach.app'))
            self.assertIn('--tokencoach_nudge.py', nudge.hook_command('/ignored'))
            hook = trailer.hook_script('/ignored')
            self.assertIn('--commit-trailer', hook)
            self.assertNotIn('-m tokencoach', hook)
            with patch.object(update.subprocess, 'run') as run:
                self.assertFalse(update._check_and_apply_update('/some/.git'))
                run.assert_not_called()

    def test_instance_lock_excludes_second_copy_and_releases(self):
        from tokencoach import runtime, config
        with tempfile.TemporaryDirectory() as d, patch.object(config, 'APP_SUPPORT', d):
            first = runtime.acquire_instance()
            try:
                self.assertIsNone(runtime.acquire_instance())
                self.assertEqual(Path(d, 'app.lock').stat().st_mode & 0o777, 0o600)
            finally:
                os.close(first)
            second = runtime.acquire_instance()
            self.assertIsNotNone(second)
            os.close(second)

    def test_cleanup_retires_owned_agents_and_exact_cron_only(self):
        from tokencoach import runtime, config
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            folder = home / 'Library/LaunchAgents'
            folder.mkdir(parents=True)
            for suffix in ('', '.doctor', '.widgethost'):
                (folder / (config.LAUNCH_AGENT_LABEL + suffix + '.plist')).write_text('owned')
            other = folder / 'other.plist'; other.write_text('keep')
            data = home / 'history'; data.write_text('keep')
            owned = f'*/2 * * * * /bin/bash {home}/.tokencoach/tokencoach-doctor.sh >> {home}/Library/Logs/TokenCoach/doctor.log 2>&1\n'
            unrelated = '# tokencoach-doctor.sh is mentioned here\n0 1 * * * /my/script\n'
            def run(args, **kwargs):
                return subprocess.CompletedProcess(args, 0, owned + unrelated if args == ['crontab', '-l'] else '', '')
            with patch.object(Path, 'home', return_value=home), patch.object(config, 'LAUNCH_AGENT_PLIST', str(folder / (config.LAUNCH_AGENT_LABEL + '.plist'))), patch('subprocess.run', side_effect=run) as calls:
                runtime.remove_background_agents(stop_main=False)
            self.assertTrue(other.exists()); self.assertTrue(data.exists())
            self.assertEqual(list(folder.glob(config.LAUNCH_AGENT_LABEL + '*.plist')), [])
            cron = next(c for c in calls.call_args_list if c.args[0] == ['crontab', '-'])
            self.assertEqual(cron.kwargs['input'], unrelated)
            self.assertFalse(any(c.args[0][-1].endswith('/' + config.LAUNCH_AGENT_LABEL) for c in calls.call_args_list))

    def test_cleanup_uses_configured_agent_folder_not_real_home(self):
        from tokencoach import runtime, config
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d, 'configured'); folder.mkdir()
            fake_home = Path(d, 'home'); real_agents = fake_home / 'Library/LaunchAgents'; real_agents.mkdir(parents=True)
            for suffix in ('', '.doctor', '.widgethost'):
                name = config.LAUNCH_AGENT_LABEL + suffix + '.plist'
                (folder / name).write_text('test agent')
                (real_agents / name).write_text('leave alone')
            with patch.object(Path, 'home', return_value=fake_home), patch.object(config, 'LAUNCH_AGENT_PLIST', str(folder / (config.LAUNCH_AGENT_LABEL+'.plist'))), patch('subprocess.run', return_value=subprocess.CompletedProcess([],1,'','')):
                runtime.remove_background_agents()
            self.assertEqual(list(folder.iterdir()), [])
            self.assertEqual(len(list(real_agents.iterdir())), 3)

    def test_mount_launch_does_not_change_setup(self):
        from tokencoach import runtime
        import rumps
        with patch.object(runtime, 'bundled', return_value=True), patch.object(runtime, 'app_bundle', return_value=Path('/Volumes/TokenCoach/TokenCoach.app')), patch.object(rumps, 'alert'), patch.object(runtime, 'remove_background_agents') as cleanup:
            self.assertFalse(runtime.prepare_bundle())
            cleanup.assert_not_called()

    def test_bundle_version_does_not_need_git(self):
        from tokencoach import version
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'build-identity.json').write_text(json.dumps({'version':'1.2.0', 'revision':'a'*40, 'dirty':False}))
            with patch.object(sys, 'frozen', True, create=True), patch.object(sys, '_MEIPASS', d, create=True), patch.object(version.subprocess, 'run') as run:
                self.assertEqual(version.version_string(), '1.2.0 (aaaaaaaaaaaa)')
                run.assert_not_called()


class DashboardAddress(unittest.TestCase):
    def test_occupied_port_is_not_silently_replaced(self):
        from tokencoach import server
        with patch.object(server, 'ThreadingHTTPServer', side_effect=OSError('occupied')) as bind:
            with self.assertRaises(OSError):
                server.DashboardServer('not-logged')
            bind.assert_called_once()

    def test_token_survives_restart(self):
        from tokencoach import server
        config = {}
        with patch.object(server, 'save_config') as save:
            token = server.get_token(config)
            self.assertEqual(server.get_token(dict(config)), token)
            save.assert_called_once()

class BundleMigration(unittest.TestCase):
    def test_cancel_preserves_existing_installation(self):
        import plistlib
        import rumps
        from tokencoach import runtime, config
        with tempfile.TemporaryDirectory() as d:
            plist = Path(d, 'login.plist')
            with plist.open('wb') as f:
                plistlib.dump({'ProgramArguments':['/old/python','/old/tokencoach.py']}, f)
            with patch.object(runtime, 'bundled', return_value=True), patch.object(runtime, 'app_bundle', return_value=Path('/Applications/TokenCoach.app')), patch.object(config, 'LAUNCH_AGENT_PLIST', str(plist)), patch.object(rumps, 'alert', return_value=0), patch.object(runtime, 'remove_background_agents') as cleanup:
                self.assertFalse(runtime.prepare_bundle())
            cleanup.assert_not_called()
            self.assertTrue(plist.exists())

    def test_migration_repoints_only_existing_owned_hooks(self):
        import plistlib
        import rumps
        from tokencoach import runtime, config, ledger, trailer, yield_metrics
        with tempfile.TemporaryDirectory() as d:
            plist = Path(d, 'login.plist')
            with plist.open('wb') as f:
                plistlib.dump({'ProgramArguments':['/old/python','/old/tokencoach.py']}, f)
            with patch.object(runtime, 'bundled', return_value=True), patch.object(runtime, 'app_bundle', return_value=Path('/Applications/TokenCoach.app')), patch.object(config, 'LAUNCH_AGENT_PLIST', str(plist)), patch.object(rumps, 'alert', return_value=1), patch.object(runtime, 'remove_background_agents') as cleanup, patch.object(ledger, 'open_ledger'), patch.object(yield_metrics, 'registered', return_value=[{'path':d},{'path':d}]), patch.object(trailer, 'locate', side_effect=[{'ours':True},{'ours':False}]), patch.object(trailer, 'install_repo') as install:
                self.assertTrue(runtime.prepare_bundle())
            cleanup.assert_called_once()
            install.assert_called_once_with(d)
