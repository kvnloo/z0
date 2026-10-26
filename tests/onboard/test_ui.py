"""Guided interaction tests use streams; never touch the host or its stores."""
import contextlib
import io
import unittest
from unittest.mock import Mock, patch

from tests.onboard.support import HAVE_YAML, require_yaml, snapshot, fixture
from z0.onboard.ui import UI, configure, consent
from z0.onboard import cli
from z0.onboard.apply import consent_verdict
from z0.onboard import kernel as k


class TTY(io.StringIO):
    def isatty(self):
        return True


class UITests(unittest.TestCase):
    def test_enter_selects_displayed_default(self):
        out = TTY()
        self.assertEqual(UI(TTY('\n'), out).choice('Mode', ['auto', 'guided'], 'auto'), 'auto')
        self.assertIn('[auto]', out.getvalue())

    def test_invalid_choice_retries_and_eof_uses_default(self):
        out = TTY()
        self.assertEqual(UI(TTY('invalid\nguided\n'), out).choice('Mode', ['auto', 'guided'], 'auto'), 'guided')
        self.assertIn('listed options', out.getvalue())
        self.assertEqual(UI(TTY(), TTY()).choice('Mode', ['auto', 'guided'], 'auto'), 'auto')

    def test_non_tty_never_reads_or_prints(self):
        inp, out = io.StringIO('guided\n'), io.StringIO()
        self.assertEqual(UI(inp, out).choice('Mode', ['auto', 'guided'], 'auto'), 'auto')
        self.assertEqual(inp.tell(), 0)
        self.assertEqual(out.getvalue(), '')

    def test_secret_uses_getpass_only_and_registers_before_store(self):
        events = []
        redactor = Mock()
        redactor.register.side_effect = lambda value: events.append('register')
        store = Mock(side_effect=lambda name, value: events.append('store'))
        out = TTY()
        with patch('z0.onboard.ui.getpass.getpass', return_value='test-value') as prompt:
            self.assertTrue(UI(TTY(), out).secret('EXAMPLE_KEY', store, redactor))
        self.assertEqual(events, ['register', 'store'])
        store.assert_called_once_with('EXAMPLE_KEY', 'test-value')
        self.assertEqual(out.getvalue(), '')
        prompt.assert_called_once()

    def test_secret_empty_non_tty_and_getpass_fallback_never_write(self):
        import getpass
        import warnings
        store = Mock()
        with self.assertRaises(ValueError):
            UI(io.StringIO(), io.StringIO()).secret('KEY', store, Mock())
        with patch('z0.onboard.ui.getpass.getpass', return_value=''):
            self.assertFalse(UI(TTY(), TTY()).secret('KEY', store, Mock()))
        def fallback(*args, **kwargs):
            warnings.warn('no terminal', getpass.GetPassWarning)
        with patch('z0.onboard.ui.getpass.getpass', side_effect=fallback), self.assertRaises(getpass.GetPassWarning):
            UI(TTY(), TTY()).secret('KEY', store, Mock())
        store.assert_not_called()

    def test_explicit_guided_without_tty_is_usage_error(self):
        with patch('sys.stdin', io.StringIO()), patch('sys.stdout', io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()), patch.object(cli, 'run_detect') as detect:
            self.assertEqual(cli.main(['--guided']), 2)
        detect.assert_not_called()

    def test_step_consent_cannot_grant_sibling_in_same_bundle(self):
        entries = [{'step': {'id': sid, 'component': 'example', 'kind': 'write_file',
                            'consent': {'class': 'C1', 'bundle': 'services'}},
                    'state': {'status': 'todo'}} for sid in ['first', 'second']]
        with patch('sys.stdin', TTY('yes\nno\n')), patch('sys.stdout', TTY()):
            grants = consent({'steps': entries})
        obj = {'mode': 'guided', 'grants': grants}
        self.assertEqual(consent_verdict(obj, entries[0]['step']).kind, k.Kind.ALLOW)
        self.assertEqual(consent_verdict(obj, entries[1]['step']).kind, k.Kind.ASK)


class LaunchdTests(unittest.TestCase):
    def test_xml_roundtrip_and_fcntl_wrapper_executes_real_child(self):
        import plistlib
        import subprocess
        import sys
        import tempfile
        from pathlib import Path
        from z0.onboard.launchd import render_plist
        with tempfile.TemporaryDirectory() as tmp:
            lock = str(Path(tmp) / 'locks' / 'service.lock')
            xml = render_plist('com.z0.example', [sys.executable, '-c', 'print("child-ok")'],
                               tmp, lock, env={'EXAMPLE': '<xml & escaping>'})
            data = plistlib.loads(xml)
            self.assertEqual(data['Label'], 'com.z0.example')
            self.assertEqual(data['EnvironmentVariables']['EXAMPLE'], '<xml & escaping>')
            child = subprocess.run(data['ProgramArguments'], capture_output=True, text=True, timeout=10)
            self.assertEqual(child.returncode, 0, child.stderr)
            self.assertEqual(child.stdout.strip(), 'child-ok')
            self.assertTrue(Path(lock).is_file())
            import fcntl
            with open(lock, 'a') as held:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                blocked = subprocess.run(data['ProgramArguments'], capture_output=True, text=True, timeout=10)
                self.assertNotEqual(blocked.returncode, 0)
                self.assertNotIn('child-ok', blocked.stdout)

    def test_checkout_execution_and_relative_paths_refused(self):
        import tempfile
        from pathlib import Path
        from z0.onboard.launchd import render_plist
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / '.git').mkdir()
            with self.assertRaisesRegex(ValueError, 'checkout'):
                render_plist('com.z0.example', ['/usr/bin/python3'], tmp, tmp + '/lock')
        with self.assertRaisesRegex(ValueError, 'absolute'):
            render_plist('com.z0.example', ['python3'], '/opt/example', '/opt/example/lock')

    @unittest.skipUnless(HAVE_YAML, 'PyYAML not installed')
    def test_guided_apple_real_registry_renders_private_preview_only(self):
        import json
        import os
        import plistlib
        import tempfile
        from pathlib import Path
        from z0.onboard.launchd import guided_previews
        from z0.onboard.plan import plan
        host, snap = fixture('apple-m-32g'), snapshot()
        obj = plan(host, snap, mode='guided', profile='personal')
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / 'run'
            run.mkdir()
            out = TTY()
            paths = guided_previews(run, host, obj, ui=UI(TTY('yes\n'), out), home=tmp)
            self.assertEqual(len(paths), 1)
            data = plistlib.loads(paths[0].read_bytes())
            self.assertIn('/z0int-runtime/', data['ProgramArguments'][0])
            self.assertIn('/z0int-shadow/', data['WorkingDirectory'])
            self.assertIn('fcntl', data['ProgramArguments'][2])
            self.assertEqual(paths[0].stat().st_mode & 0o777, 0o600)
            self.assertFalse((Path(tmp) / 'Library').exists())
            self.assertIn('review before manual installation', out.getvalue())

    @unittest.skipUnless(HAVE_YAML, 'PyYAML not installed')
    def test_auto_linux_non_tty_and_decline_never_render(self):
        import tempfile
        from pathlib import Path
        from z0.onboard.launchd import guided_previews
        from z0.onboard.plan import plan
        host, snap = fixture('apple-m-32g'), snapshot()
        obj = plan(host, snap, mode='guided', profile='personal')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases = [(host, dict(obj, mode='auto'), UI(TTY('yes\n'), TTY())),
                     (dict(host, os={'os': 'linux'}), obj, UI(TTY('yes\n'), TTY())),
                     (host, obj, UI(io.StringIO('yes\n'), io.StringIO())),
                     (host, obj, UI(TTY('\n'), TTY()))]
            for h, p, ui in cases:
                self.assertEqual(guided_previews(root, h, p, ui=ui, home=tmp), [])
            self.assertEqual(list(root.iterdir()), [])


@require_yaml
class GuidedPlans(unittest.TestCase):
    def test_configure_displays_hardware_defaults(self):
        host, snap = fixture('apple-m-32g'), snapshot()
        args = cli.build_parser().parse_args(['--guided'])
        with patch('sys.stdin', TTY('\n' * 12)), patch('sys.stdout', TTY()) as out:
            profile = configure(args, host, snap)
        self.assertEqual(profile, 'personal')
        self.assertEqual(args.pin_policy, 'pinned')
        self.assertEqual(args.llm, 'local')
        self.assertIn('[personal]', out.getvalue())
        self.assertIn('Include dash?', out.getvalue())

    def test_auto_keeps_one_enumerated_confirmation(self):
        host, snap = fixture('groot-nvidia-32g'), snapshot()
        args = cli.build_parser().parse_args(['--auto'])
        obj = cli._make_plan(host, snap, args, None)
        with patch.object(cli, '_tty', return_value=True), patch.object(cli, '_confirm', return_value=True) as confirm:
            result, code, abort = cli._consent(args, host, snap, obj['profile'], obj)
        self.assertEqual(confirm.call_count, 1)
        self.assertTrue(any('[services]' in line for line in confirm.call_args.args[0]))
        self.assertIsNone(abort)

    def test_non_tty_implicit_mode_is_auto_without_question(self):
        with patch.object(cli, 'run_detect', return_value=(fixture('apple-m-32g'), snapshot())), \
                patch('sys.stdin', io.StringIO('guided\n')), patch('sys.stdout', io.StringIO()) as out, \
                patch.object(cli, 'write_run_dir', return_value=None):
            self.assertEqual(cli.main(['--plan-only']), 0)
        self.assertIn('mode=auto', out.getvalue())
        self.assertNotIn('auto or guided?', out.getvalue())

    def test_tty_implicit_mode_can_choose_guided(self):
        with patch.object(cli, 'run_detect', return_value=(fixture('apple-m-32g'), snapshot())), \
                patch('sys.stdin', TTY('guided\n' + '\n' * 12)), patch('sys.stdout', TTY()) as out, \
                patch.object(cli, 'write_run_dir', return_value=None):
            self.assertEqual(cli.main(['--plan-only']), 0)
        self.assertIn('mode=guided', out.getvalue())
