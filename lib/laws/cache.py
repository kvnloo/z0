"""Content-addressed, sealed toolchain and native-checker caches."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from . import file_sha256, validate_cache

HERE = Path(__file__).resolve().parent
PINS = HERE/'toolchain.json'


def cache_root():
    return safe_directory(Path(os.environ.get('XDG_CACHE_HOME', Path.home()/'.cache'))/'z0')


def safe_directory(path):
    path = Path(path).expanduser().resolve()
    if path == Path('/tmp') or Path('/tmp') in path.parents:
        raise RuntimeError('laws refuses writes under /tmp; set TMPDIR or XDG_CACHE_HOME')
    path.mkdir(parents=True, exist_ok=True)
    return path


def scratch_root():
    return safe_directory(os.environ.get('TMPDIR', cache_root()/'work'))


@contextmanager
def cache_lock(parent, key):
    safe_directory(parent)
    with (parent/(key+'.lock')).open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def seal(directory, key, paths):
    files, links = {}, {}
    for path in sorted(paths):
        name = path.relative_to(directory).as_posix()
        if path.is_symlink():
            if not path.resolve().is_relative_to(directory.resolve()):
                raise RuntimeError('cache symlink escapes installation')
            links[name] = os.readlink(path)
        elif path.is_file():
            files[name] = file_sha256(path)
    (directory/'cache.json').write_text(json.dumps(dict(input_sha256=key, files=files, links=links), sort_keys=True)+'\n')
    freeze(directory)


def freeze(directory):
    """Prevent incidental writes to installed artifacts; hashes still govern reuse."""
    for path in directory.rglob('*'):
        if not path.is_symlink():
            path.chmod(path.stat().st_mode & ~0o222)
    directory.chmod(directory.stat().st_mode & ~0o222)


def ensure_toolchain():
    key = file_sha256(PINS)
    parent = cache_root()/'toolchains'
    target = parent/key
    with cache_lock(parent, key):
        if target.exists():
            validate_cache(target, key)
            return target
        with tempfile.TemporaryDirectory(prefix=key+'-', dir=parent) as folder:
            stage = Path(folder)/'install'
            env = dict(os.environ, TMPDIR=str(scratch_root()))
            subprocess.run(['bash', str(HERE/'bootstrap.sh'), str(stage)], env=env,
                           check=True, stdout=subprocess.PIPE, text=True, timeout=1200)
            pins = json.loads(PINS.read_text())
            for name, expected in pins['files_sha256'].items():
                if file_sha256(stage/'bend'/name) != expected:
                    raise RuntimeError('official Bend package hash mismatch')
            paths = list(stage.rglob('*'))
            seal(stage, key, paths)
            stage.rename(target)
    return target


def checker_key(source, lean, clang_version):
    """Length-framed source + Lean binary + compiler-version identities."""
    values = [file_sha256(source), file_sha256(lean), clang_version]
    return hashlib.sha256(json.dumps(values, separators=(',', ':')).encode()).hexdigest()


def ensure_checker(package, lean_bin, env):
    clang = shutil.which('clang', path=env['PATH'])
    if clang is None:
        raise RuntimeError('host clang is required')
    version = subprocess.run([clang, '--version'], env=env, check=True,
                             capture_output=True, text=True, timeout=30).stdout
    source = package/'bend2/bendtt.lean'
    key = checker_key(source, lean_bin/'lean', version)
    parent = cache_root()/'checker'
    target = parent/key
    with cache_lock(parent, key):
        if target.exists():
            meta = validate_cache(target, key)
            if set(meta['files']) != {'bendtt'}:
                raise RuntimeError('checker cache lacks the expected artifact')
            return target/'bendtt'
        with tempfile.TemporaryDirectory(prefix=key+'-', dir=parent) as folder:
            stage = Path(folder)/'build'
            stage.mkdir()
            shutil.copy2(source, stage/'bendtt.lean')
            subprocess.run([str(lean_bin/'lean'), '-c', 'bendtt.c', 'bendtt.lean'],
                           cwd=stage, env=env, check=True, timeout=600)
            subprocess.run([str(lean_bin/'leanc'), '-O3', '-DNDEBUG', 'bendtt.c',
                            '-L'+str(lean_bin.parent/'lib'), '-o', 'bendtt'],
                           cwd=stage, env=dict(env, LEAN_CC=clang), check=True, timeout=600)
            # Do not retain intermediate C or Lean sources as trusted artifacts.
            (stage/'bendtt.c').unlink()
            (stage/'bendtt.lean').unlink()
            seal(stage, key, [stage/'bendtt'])
            stage.rename(target)
    return target/'bendtt'
