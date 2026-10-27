"""The benchmark must preserve measured phase results, including failures."""
import importlib.machinery
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BenchmarkTests(unittest.TestCase):
    def test_phase_records_elapsed_status_and_peak(self):
        path = ROOT / 'scripts/laws-bench'
        self.assertTrue(path.exists(), 'missing benchmark executable')
        loader = importlib.machinery.SourceFileLoader('laws_bench', str(path))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            row = module.measure('probe', ['python3', '-c',
                'from pathlib import Path; import os; Path(os.environ["TMPDIR"], "data").write_bytes(b"x"*4096)'],
                Path(folder), {})
            self.assertEqual(row['returncode'], 0)
            self.assertGreater(row['seconds'], 0)
            self.assertGreaterEqual(row['peak_tmp_bytes'], 4096)
