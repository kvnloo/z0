"""Characterize the legacy read-only surfaces before routing installation to onboard."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.onboard.support import require_yaml


@require_yaml
class LegacyCommands(unittest.TestCase):
    def test_init_dry_run_lists_profile_without_writes(self):
        from z0 import commands
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'repos'
            out = io.StringIO()
            with patch.object(commands.registry, 'load_workspace', return_value={'root': str(root)}), \
                    patch.object(commands.registry, 'save_workspace') as save, \
                    patch.object(commands, '_run') as run, contextlib.redirect_stdout(out):
                self.assertEqual(commands.cmd_init('core', dry_run=True), 0)
            self.assertIn('Profile: core', out.getvalue())
            self.assertIn('tokenomics', out.getvalue())
            self.assertFalse(root.exists())
            save.assert_not_called()
            run.assert_not_called()

    def test_init_unknown_profile_is_an_error(self):
        from z0 import commands
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(commands.cmd_init('not-a-profile', dry_run=True), 1)

    def test_init_real_install_routes_to_onboard_and_propagates_failure(self):
        from z0 import commands
        with patch('z0.onboard.cli.main', return_value=1) as onboard, \
                patch.object(commands, '_run') as legacy, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(commands.cmd_init('core'), 1)
        onboard.assert_called_once_with(['--profile', 'core'])
        legacy.assert_not_called()

    def test_init_without_profile_keeps_onboard_mode_choice(self):
        from z0 import commands
        with patch('z0.onboard.cli.main', return_value=3) as onboard, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(commands.cmd_init(), 3)
        onboard.assert_called_once_with([])

    def test_doctor_inventory_missing_components_is_read_only(self):
        from z0 import commands
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(commands.registry, 'load_workspace', return_value={}), \
                patch.object(commands.registry, 'components', return_value={'example': {'name': 'Example'}}), \
                patch.object(commands.registry, 'interfaces', return_value={}), \
                patch.object(commands.registry, 'repo_dir', return_value=Path(tmp) / 'absent'), \
                patch.object(commands, '_run') as run, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(commands.cmd_doctor(), 0)
            self.assertIn('○ Example', out.getvalue())
            run.assert_not_called()
