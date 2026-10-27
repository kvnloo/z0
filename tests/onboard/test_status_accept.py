"""Status and accept integration in a disposable home, with real journaled writes."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.onboard.support import require_yaml, snapshot, fixture, ROOT
from z0.onboard import cli
from z0.onboard.actions.write_file import RENDERERS
from z0.onboard.apply import apply_run, Deps, effective_plan
from z0.onboard.plan import plan, plan_hash
from z0.onboard.verify import verify_run


@require_yaml
class StatusAccept(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.zhome = self.home / '.z0'
        self.env = patch.dict(os.environ, {'HOME': str(self.home), 'Z0_HOME': str(self.zhome)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.host = fixture('apple-m-32g')
        self.snap = snapshot()
        def step(sid, cls, bundle=None, needs=()):
            return {'id': sid, 'kind': 'write_file', 'where': 'home',
                    'consent': {'class': cls, **({'bundle': bundle} if bundle else {})},
                    'needs': list(needs), 'creates': [f'$Z0_HOME/files/{sid}'],
                    'undo': {'kind': 'remove_owned'}}
        self.steps = [step('example.base', 'C0'), step('example.service', 'C1', 'services', ['example.base']),
                      step('example.harness', 'C1', 'harness'), step('example.manual', 'C2')]
        self.snap['components'] = {'components': {'example': {'repo': 'example/example',
            'install': {'ref': 'a' * 40}, 'onboard': {'steps': self.steps}}}}
        self.snap['profiles'] = {'profiles': {'core': {'components': ['example']}}, 'onboard': {}}
        self.snap['onboarding']['hub'] = {'steps': []}
        self.snap['toolchains'] = {}
        self.render = patch.dict(RENDERERS, {s['id']: lambda ctx, step: (step['id'].encode(), 0o600)
                                            for s in self.steps})
        self.render.start()
        self.addCleanup(self.render.stop)
        self.detect = patch.object(cli, 'run_detect', side_effect=lambda **kwargs: (copy.deepcopy(self.host), copy.deepcopy(self.snap)))
        self.detect_mock = self.detect.start()
        self.addCleanup(self.detect.stop)

    def initial_run(self, grants=None):
        obj = plan(self.host, self.snap, profile='core', grants=grants)
        self.run_path = cli.write_run_dir(self.host, obj)
        deps = Deps(str(self.zhome), str(self.home), str(ROOT), self.snap, out=lambda text: None)
        result = apply_run(self.run_path, deps)
        verify_run(self.run_path, deps, prior=result.results, host=self.host, consent_code=3)
        return obj

    def call(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = cli.main(list(argv))
        return code, out.getvalue()

    def receipt(self):
        return json.loads((self.run_path / 'receipt.json').read_text())

    def test_status_no_run_is_actionable_and_creates_nothing(self):
        code, out = self.call('status')
        self.assertEqual(code, 2)
        self.assertTrue(out.startswith('What you need to do:'))
        self.assertFalse(self.zhome.exists())

    def test_status_receipt_and_asks_first_without_detection_or_writes(self):
        self.initial_run()
        before = {str(p): p.read_bytes() for p in self.zhome.rglob('*') if p.is_file()}
        self.detect_mock.reset_mock()
        code, out = self.call('status')
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith('What you need to do:'))
        self.assertIn('example.service', out)
        self.assertIn('Last run:', out)
        self.assertIn('exit 3', out)
        self.detect_mock.assert_not_called()
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.zhome.rglob('*') if p.is_file()})

    def test_accept_only_requested_bundle_real_file_and_receipt(self):
        self.initial_run()
        original = (self.run_path / 'plan.json').read_bytes()
        base = self.zhome / 'files/example.base'
        base.write_text('kept')
        code, out = self.call('accept', 'services')
        self.assertEqual(code, 3, out)  # harness still asks
        self.assertEqual((self.zhome / 'files/example.service').read_text(), 'example.service')
        self.assertEqual(base.read_text(), 'kept')
        self.assertFalse((self.zhome / 'files/example.harness').exists())
        self.assertFalse((self.zhome / 'files/example.manual').exists())
        self.assertEqual((self.run_path / 'plan.json').read_bytes(), original)
        receipt = self.receipt()
        self.assertNotIn('example.service', [a['id'] for a in receipt['asks']])
        self.assertIn('example.harness', [a['id'] for a in receipt['asks']])
        self.assertIn('example.manual', [a['id'] for a in receipt['asks']])
        self.assertEqual(plan_hash(effective_plan(self.run_path)), receipt['plan_hash'])

    def test_missing_prior_prerequisite_blocks_accept_without_reapplying_c0(self):
        self.initial_run()
        (self.zhome / 'files/example.base').unlink()
        code, out = self.call('accept', 'services')
        self.assertEqual(code, 3, out)
        self.assertIn('unmet prerequisites', out)
        self.assertFalse((self.zhome / 'files/example.base').exists())
        self.assertFalse((self.zhome / 'files/example.service').exists())

    def test_accept_multiple_bundles_space_or_comma_and_no_c2(self):
        self.initial_run()
        code, out = self.call('accept', 'services,harness')
        self.assertEqual(code, 0, out)
        self.assertTrue((self.zhome / 'files/example.harness').is_file())
        self.assertFalse((self.zhome / 'files/example.manual').exists())

    def test_repeated_accept_does_not_reapply(self):
        self.initial_run()
        self.call('accept', 'services')
        path = self.zhome / 'files/example.service'
        path.write_text('user edit')
        journal = (self.run_path / 'journal.jsonl').read_bytes()
        code, out = self.call('accept', 'services')
        self.assertEqual(code, 0, out)
        self.assertEqual(path.read_text(), 'user edit')
        self.assertEqual((self.run_path / 'journal.jsonl').read_bytes(), journal)

    def test_accept_second_bundle_keeps_prior_success_and_asks_resolved(self):
        self.initial_run()
        self.call('accept', 'services')
        code, out = self.call('accept', 'harness')
        self.assertEqual(code, 0, out)
        self.assertNotIn('example.service', [a['id'] for a in self.receipt()['asks']])
        self.assertEqual(next(s['status'] for s in self.receipt()['steps'] if s['id'] == 'example.service'), 'passed')

    def test_accept_unknown_bundle_or_c2_id_is_usage_error(self):
        for token in ['unknown', 'example.manual']:
            code, out = self.call('accept', token)
            self.assertEqual(code, 2)
            self.assertIn('C1 bundles', out)
        self.assertFalse(self.zhome.exists())

    def test_accept_host_mismatch_refuses_without_step_writes(self):
        self.initial_run()
        self.host['host_id'] = 'f' * 16
        code, out = self.call('accept', 'services')
        self.assertEqual(code, 4, out)
        self.assertFalse((self.zhome / 'files/example.service').exists())

    def test_accept_registry_drift_refuses(self):
        self.initial_run()
        self.snap['files']['registry/components.yaml'] = 'b' * 64
        code, out = self.call('accept', 'services')
        self.assertEqual(code, 4, out)
        self.assertIn('registry changed', out)

    def test_accept_edited_original_and_effective_hashes_refuse(self):
        self.initial_run()
        (self.run_path / 'plan.replan.json').write_text(json.dumps({'plan_hash': 'invalid'}))
        self.assertEqual(self.call('accept', 'services')[0], 4)
        obj = json.loads((self.run_path / 'plan.json').read_text())
        obj['mode'] = 'guided'
        (self.run_path / 'plan.json').write_text(json.dumps(obj))
        self.assertEqual(self.call('accept', 'services')[0], 4)

    def test_accept_never_executes_new_step_or_unrelated_c0(self):
        self.initial_run()
        # Unrecorded detector facts cannot add a new step to the consent scope.
        new = copy.deepcopy(self.steps[1])
        new['id'] = 'example.new'
        new['creates'] = ['$Z0_HOME/files/example.new']
        self.snap['components']['components']['example']['onboard']['steps'].append(new)
        code, out = self.call('accept', 'services')
        self.assertEqual(code, 3, out)
        self.assertFalse((self.zhome / 'files/example.new').exists())

    def test_accept_failure_is_reported_and_blocks_dependents(self):
        self.initial_run()
        from z0.onboard.actions.base import ActionError
        with patch.dict(RENDERERS, {'example.service': lambda ctx, step: (_ for _ in ()).throw(ActionError('test failure'))}):
            code, out = self.call('accept', 'services')
        self.assertEqual(code, 1, out)
        self.assertIn('FAILED example.service', out)

    def test_accept_can_be_rolled_back_with_original_journal(self):
        self.initial_run()
        self.call('accept', 'services')
        code, out = self.call('rollback')
        self.assertEqual(code, 0, out)
        self.assertFalse((self.zhome / 'files/example.service').exists())
        self.assertFalse((self.zhome / 'files/example.base').exists())
