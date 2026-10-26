"""The z0 laws installer/development commands; no runtime business logic."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from . import TOOLCHAIN, load_manifest, prove
from .cache import scratch_root, safe_directory


def init_domain(root, name):
    if not re.fullmatch(r'[a-z][a-z0-9_]*', name):
        raise ValueError('domain must be a lowercase identifier')
    root = safe_directory(root)
    manifest = root/'laws.toml'
    if manifest.exists():
        data = load_manifest(root)
        if any(d['name'] == name for d in data['domain']):
            raise ValueError('domain already declared')
    domain = f'bend/{name}'
    twin = f'lib/{name}.py'
    parity = f'tests/test_{name}_parity.py'
    mutation = f'tests/test_{name}_mutation.py'
    # A tiny, runnable example, not a claim about the consumer's business laws.
    files = {
        f'{domain}/MODEL.bend': 'import Base\n\ndef decide(x: Bool) -> Bool:\n  x\n',
        f'{domain}/LAWS.bend': 'import Base\nimport ./MODEL.bend as M\n\nlaw identity:\n  for x: Bool\n  {M.decide(x) == x : Bool}\n',
        f'{domain}/PROOF.bend': 'import Base\nimport ./MODEL.bend as M\nimport ./LAWS.bend as Laws\n\ndef Laws.identity(x):\n  {==}\n',
        twin: '"""Example only: replace with the domain choke point and reviewed laws."""\ndef decide(value: bool) -> bool:\n    return value\n',
    }
    header = ("import os\nfrom pathlib import Path\nimport sys\nimport unittest\n"
              "ROOT = Path(__file__).resolve().parents[1]\nsys.path.insert(0, str(ROOT/'lib'))\n"
              f"from {name} import decide\n\n")
    files[parity] = header + f'''class Parity(unittest.TestCase):
    def test_finite_bool_domain(self):
        if not os.environ.get('BEND'):
            self.skipTest('run with z0 laws check for pinned Bend parity')
        from laws.verifier import verifier_environment
        import subprocess
        import tempfile
        import shutil
        with verifier_environment() as (bend, env), tempfile.TemporaryDirectory(dir=env['TMPDIR']) as folder:
            folder = Path(folder)
            shutil.copy2(ROOT/'{domain}/MODEL.bend', folder/'MODEL.bend')
            for value in (False, True):
                constructor = 'True' if value else 'False'
                program = ('import Base\\nimport ./MODEL.bend as M\\n'
                           'def main() -> IO(Unit):\\n  IO.print(Bool.show(M.decide('
                           +constructor+'{{}})))\\n')
                (folder/'cases.bend').write_text(program)
                result = subprocess.run([bend, 'cases.bend'], cwd=folder, env=env,
                                        capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip().lower(), str(decide(value)).lower())

if __name__ == '__main__':
    unittest.main()
'''
    files[mutation] = header + '''class Mutation(unittest.TestCase):
    def test_identity_mutant_is_killed(self):
        def obeys_law(candidate):
            return all(candidate(value) == value for value in (False, True))
        self.assertTrue(obeys_law(decide))
        self.assertFalse(obeys_law(lambda value: not value))

if __name__ == '__main__':
    unittest.main()
'''
    if any((root/p).exists() or (root/p).is_symlink() for p in files):
        raise ValueError('init refuses to overwrite existing domain files')
    # Validate the prospective manifest before creating any files.
    declaration = (f'\n[[domain]]\nname = "{name}"\ndir = "{domain}"\ntwin = "{twin}"\n'
                   f'parity = "{parity}"\nmutation = "{mutation}"\ngate = []\n')
    text = manifest.read_text() if manifest.exists() else f'toolchain = "{TOOLCHAIN}"\n'
    for path, content in files.items():
        destination = root/path
        if not destination.resolve().is_relative_to(root):
            raise ValueError('init path escapes repository')
    for path, content in files.items():
        destination = root/path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content)
    manifest.write_text(text+declaration)
    return name


def check(root, domains):
    from .verifier import verifier_environment
    from .testing import run
    from unittest.mock import patch
    paths = []
    for domain in domains:
        if not (root/domain['twin']).is_file():
            raise RuntimeError('declared twin is missing: '+domain['twin'])
        for kind in ('parity', 'mutation'):
            path = root/domain[kind]
            if not path.is_file():
                raise RuntimeError('declared law test is missing: '+domain[kind])
            paths.append(path)
    # Validate the large toolchain once per command, not once per test entry.
    with verifier_environment() as (_, env):
        env['Z0_REQUIRE_BEND'] = '1'
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        cwd, search_path = Path.cwd(), sys.path[:]
        try:
            os.chdir(root)
            sys.path[:0] = [str(root), str(root/'lib')]
            with patch.dict(os.environ, env, clear=True):
                return run(paths)
        finally:
            os.chdir(cwd)
            sys.path[:] = search_path


def main(argv=None):
    parser = argparse.ArgumentParser(prog='z0 laws', description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd(), help='consumer repository (default: cwd)')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('check', help='exhaustive twin parity and mutation tests (all declared domains)')
    proof = sub.add_parser('prove', help='Bend verdict, or explicit unchanged receipt')
    proof.add_argument('--all', action='store_true', help='ignore local unchanged locks (CI)')
    scaffold = sub.add_parser('init', help='scaffold a runnable example domain')
    scaffold.add_argument('domain')
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()
    try:
        scratch_root()  # refuse unsafe TMPDIR before any command writes
        if args.command == 'init':
            init_domain(root, args.domain)
            print('scaffolded '+args.domain+'; replace example laws before adoption')
            return 0
        domains = load_manifest(root)['domain']
        if args.command == 'check':
            return check(root, domains)
        print(json.dumps(prove(root, domains, all_domains=args.all), indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print('z0 laws: '+str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
