"""Contracts for the shared, fail-closed laws installer/CLI."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT/'lib'))


from laws.cache import scratch_root


def temporary_directory():
    return tempfile.TemporaryDirectory(dir=scratch_root())


class FailClosedRegressions(unittest.TestCase):
    def test_cache_rejects_changed_symlink_and_unlisted_files(self):
        from laws.cache import seal
        from laws import validate_cache
        with temporary_directory() as folder:
            root = Path(folder)
            (root/'artifact').write_text('good')
            (root/'alias').symlink_to('artifact')
            seal(root, 'a'*64, [root/'artifact', root/'alias'])
            validate_cache(root, 'a'*64)
            root.chmod(0o755)  # deliberate tampering bypasses incidental-write protection
            (root/'alias').unlink()
            (root/'alias').symlink_to('missing')
            with self.assertRaises(RuntimeError):
                validate_cache(root, 'a'*64)
            (root/'alias').unlink()
            (root/'alias').symlink_to('artifact')
            (root/'injected').write_text('untrusted')
            with self.assertRaises(RuntimeError):
                validate_cache(root, 'a'*64)

    def test_manifest_rejects_non_table_domain(self):
        from laws import load_manifest
        with temporary_directory() as folder:
            root = Path(folder)
            (root/'laws.toml').write_text('toolchain="bend-2.0.34"\ndomain=[1]\n')
            with self.assertRaises(ValueError):
                load_manifest(root)

    def test_init_scaffolds_runnable_nonvacuous_tests(self):
        from laws.cli import init_domain
        from laws import load_manifest
        import subprocess
        with temporary_directory() as folder:
            root = Path(folder)
            init_domain(root, 'demo')
            domain = load_manifest(root)['domain'][0]
            for key in ('twin', 'parity', 'mutation'):
                self.assertTrue((root/domain[key]).is_file())
            import os
            env = dict(os.environ, PYTHONPATH=str(ROOT/'lib'))
            for key in ('parity', 'mutation'):
                result = subprocess.run([sys.executable, str(root/domain[key])], cwd=root,
                                        env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('Ran 1 test', result.stderr)
            with self.assertRaises(ValueError):
                init_domain(root, 'demo')


class CacheTests(unittest.TestCase):
    def test_checker_identity_covers_source_lean_and_clang_version(self):
        from laws.cache import checker_key
        with temporary_directory() as folder:
            root = Path(folder)
            source, lean = root/'bendtt.lean', root/'lean'
            source.write_bytes(b'checker source')
            lean.write_bytes(b'Lean binary')
            original = checker_key(source, lean, 'clang version one')
            self.assertEqual(original, checker_key(source, lean, 'clang version one'))
            self.assertNotEqual(original, checker_key(source, lean, 'clang version two'))
            source.write_bytes(b'changed checker')
            self.assertNotEqual(original, checker_key(source, lean, 'clang version one'))
            source.write_bytes(b'checker source')
            lean.write_bytes(b'changed Lean')
            self.assertNotEqual(original, checker_key(source, lean, 'clang version one'))

    def test_init_rejects_system_temp_root_and_symlink_escape(self):
        from laws.cli import init_domain
        with temporary_directory() as folder:
            root = Path(folder)
            (root/'redirect').symlink_to('/tmp', target_is_directory=True)
            for target in (Path('/tmp'), root/'redirect'):
                with self.subTest(root=str(target)), self.assertRaises(RuntimeError):
                    init_domain(target, 'demo')

    def test_cache_rejects_stale_input_hash_and_tampered_artifact(self):
        import laws
        self.assertTrue(hasattr(laws, 'validate_cache'), 'cache acceptance missing')
        import hashlib
        import json
        from laws import validate_cache
        with temporary_directory() as folder:
            root = Path(folder)
            (root/'checker').write_bytes(b'kernel')
            meta = {'input_sha256': 'a'*64, 'files': {'checker': hashlib.sha256(b'kernel').hexdigest()}}
            (root/'cache.json').write_text(json.dumps(meta))
            validate_cache(root, 'a'*64)
            with self.assertRaises(RuntimeError):
                validate_cache(root, 'b'*64)
            (root/'checker').write_bytes(b'tampered')
            with self.assertRaises(RuntimeError):
                validate_cache(root, 'a'*64)


class ProveTests(unittest.TestCase):
    def test_invalid_lock_shapes_fail_closed(self):
        import json
        from laws import prove
        with temporary_directory() as folder:
            root = Path(folder)
            (root/'.z0').mkdir()
            domain = {'name': 'demo', 'dir': 'bend/demo'}
            directory = root/domain['dir']
            directory.mkdir(parents=True)
            for name in ('MODEL', 'LAWS', 'PROOF'):
                (directory/(name+'.bend')).write_text(name)
            for invalid in ([], None, {'demo': []}, {'demo': None}):
                with self.subTest(lock=invalid):
                    (root/'.z0/laws.lock').write_text(json.dumps(invalid))
                    with self.assertRaises(RuntimeError):
                        prove(root, [domain], verify=lambda _: self.fail('invalid lock accepted'))

    def test_pins_change_invalidates_unchanged_skip(self):
        from unittest.mock import patch
        from laws import prove
        with temporary_directory() as folder:
            root = Path(folder)
            domain = {'name': 'demo', 'dir': 'bend/demo'}
            directory = root/domain['dir']
            directory.mkdir(parents=True)
            for name in ('MODEL', 'LAWS', 'PROOF'):
                (directory/(name+'.bend')).write_text(name)
            pins = root/'pins.json'
            pins.write_text('first reviewed pins')
            calls = []
            def verify(path):
                calls.append(path)
                return 'ALL PROOFS CHECK'
            with patch('laws.cache.PINS', pins):
                self.assertEqual(prove(root, [domain], verify=verify)[0]['status'], 'proven')
                self.assertEqual(prove(root, [domain], verify=verify)[0]['status'], 'unchanged')
                pins.write_text('new reviewed pins')
                self.assertEqual(prove(root, [domain], verify=verify)[0]['status'], 'proven')
            self.assertEqual(len(calls), 2)

    def test_unchanged_writes_receipt_without_invoking_verifier(self):
        import laws
        self.assertTrue(hasattr(laws, 'prove'), 'prove command missing')
        import json
        from laws import prove
        with temporary_directory() as folder:
            root = Path(folder)
            domain = {'name':'demo','dir':'bend/demo'}
            directory = root/domain['dir']
            directory.mkdir(parents=True)
            for name in ('MODEL','LAWS','PROOF'):
                (directory/(name+'.bend')).write_text(name)
            calls = []
            def verify(path):
                calls.append(path)
                return 'ALL PROOFS CHECK'
            self.assertEqual(prove(root, [domain], verify=verify)[0]['status'], 'proven')
            self.assertEqual(prove(root, [domain], verify=verify)[0]['status'], 'unchanged')
            self.assertEqual(len(calls), 1)
            receipts = json.loads((root/'.z0/laws.receipt.json').read_text())
            self.assertEqual(receipts[0]['status'], 'unchanged')
            self.assertFalse(receipts[0]['proof_is_permission'])
            (directory/'LAWS.bend').write_text('changed')
            self.assertEqual(prove(root, [domain], verify=verify)[0]['status'], 'proven')
            self.assertEqual(len(calls), 2)
            self.assertEqual(prove(root, [domain], verify=verify, all_domains=True)[0]['status'], 'proven')
            def fail(path):
                raise RuntimeError('SOME PROOFS FAIL')
            with self.assertRaises(RuntimeError):
                prove(root, [domain], verify=fail, all_domains=True)
            self.assertEqual(prove(root, [domain], verify=verify)[0]['status'], 'proven')


class ManifestTests(unittest.TestCase):
    def test_parse_domain_and_reject_escape_unknown_toolchain_and_duplicates(self):
        self.assertIsNotNone(importlib.util.find_spec('laws'), 'shared laws library missing')
        from laws import load_manifest
        with temporary_directory() as folder:
            root = Path(folder)
            text = ('toolchain = "bend-2.0.34"\n[[domain]]\nname="demo"\n'
                    'dir="bend/demo"\ntwin="lib/demo.py"\n'
                    'parity="tests/test_demo_parity.py"\nmutation="tests/test_demo_mutation.py"\n')
            manifest = root/'laws.toml'
            manifest.write_text(text)
            parsed = load_manifest(root)
            self.assertEqual(parsed['domain'][0]['name'], 'demo')
            for bad in [text.replace('bend/demo','../escape'),
                        text.replace('bend-2.0.34','ambient'),
                        text+text.split('[[domain]]')[1].join(['[[domain]]',''])]:
                manifest.write_text(bad)
                with self.assertRaises(ValueError):
                    load_manifest(root)
