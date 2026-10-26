"""One pinned verifier for CLI consumers and the onboard test suite."""
from contextlib import contextmanager
from contextvars import ContextVar
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from . import file_sha256
from .cache import PINS, ensure_toolchain, ensure_checker, scratch_root

FILES_SHA256 = json.loads(PINS.read_text())['files_sha256']
_ACTIVE: ContextVar[tuple[str, dict[str, str]] | None] = ContextVar('laws_verified_environment', default=None)


@contextmanager
def verifier_environment(domain=None):
    """Reject ambient checkers; accept only sealed, content-addressed artifacts.

    The benchmark-only fresh lane reproduces the original per-entry compilation.
    It still validates official Bend files and the pinned Lean version.
    """
    active = _ACTIVE.get()
    if active is not None:
        # Nested test harnesses share this command's validated, live environment.
        # Never accept an ambient BENDTT or an environment-variable trust marker.
        yield active[0], dict(active[1])
        return
    manifest = json.loads(PINS.read_text())
    if (manifest['source_semantics_attested'] is not False
            or manifest['proof_is_permission'] is not False):
        raise RuntimeError('toolchain trust declaration changed; review its pins')
    fresh = os.environ.get('Z0_LAWS_FRESH_CHECKER') == '1'
    if fresh:
        bend = Path(os.environ['BEND']).resolve(strict=True)
        lean_bin = Path(os.environ['LEAN_BIN']).resolve(strict=True)
        package = bend.parent.parent
    else:
        installation = ensure_toolchain()
        package = installation/'bend'
        bend = package/'bin/bend'
        lean_bin = installation/'lean-4.34.0-linux/bin'
    for relative, expected in FILES_SHA256.items():
        if file_sha256(package/relative) != expected:
            raise RuntimeError('official toolchain hash mismatch: '+relative)
    env = dict(os.environ)
    env.pop('BENDTT', None)
    clang = shutil.which('clang', path=env.get('PATH'))
    if not clang:
        raise RuntimeError('host clang is required to compile the pinned checker')
    # The Lean archive bundles clang. Always select the host compiler first.
    env['PATH'] = os.pathsep.join((str(Path(clang).parent), str(lean_bin), env.get('PATH', '')))
    env['TMPDIR'] = str(scratch_root())
    env['BEND'] = str(bend)
    env['LEAN_BIN'] = str(lean_bin)
    with tempfile.TemporaryDirectory(prefix='bend-verifier-', dir=env['TMPDIR']) as folder:
        env['HOME'] = str(Path(folder)/'home')
        Path(env['HOME']).mkdir()
        version = subprocess.run([str(bend), 'version'], env=env, capture_output=True,
                                 text=True, check=True, timeout=30)
        if version.stdout.strip() != 'bend 2.0.34':
            raise RuntimeError('requires official Bend 2.0.34')
        lean = subprocess.run([str(lean_bin/'lean'), '--version'], env=env,
                              capture_output=True, text=True, check=True, timeout=30)
        if 'version 4.34.0,' not in lean.stdout:
            raise RuntimeError('requires Lean 4.34.0 from the verified archive')
        if not fresh:
            env['BENDTT'] = str(ensure_checker(package, lean_bin, env))
        token = _ACTIVE.set((str(bend), env))
        try:
            yield str(bend), dict(env)
        finally:
            _ACTIVE.reset(token)


def verdict(domain):
    with verifier_environment(domain) as (bend, env):
        result = subprocess.run([bend, 'PROOF.bend', '--verdict'], cwd=domain,
                                env=env, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0 or result.stdout.strip() != 'ALL PROOFS CHECK':
        raise RuntimeError('Bend verdict failed: '+(result.stdout+result.stderr)[-2000:])
    return result.stdout.strip()
