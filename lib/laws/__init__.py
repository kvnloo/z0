"""Shared formal-laws tooling. Proofs are evidence, never permission."""
from pathlib import Path
import re

TOOLCHAIN = 'bend-2.0.34'


def file_sha256(path):
    import hashlib
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else hashlib.sha256(stream.read()).hexdigest()


def validate_cache(directory, expected):
    """Reject stale input identities, missing metadata, links and changed artifacts."""
    import json
    directory = Path(directory)
    try:
        meta = json.loads((directory/'cache.json').read_text())
        if directory.is_symlink() or meta['input_sha256'] != expected or not meta['files']:
            raise ValueError('stale input hash')
        for name, digest in meta['files'].items():
            path = directory/name
            if Path(name).is_absolute() or '..' in Path(name).parts or path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError('unsafe artifact path')
            if file_sha256(path) != digest:
                raise ValueError('artifact hash mismatch')
        links = meta.get('links', {})
        for name, target in links.items():
            path = directory/name
            if (Path(name).is_absolute() or '..' in Path(name).parts
                    or not path.is_symlink() or path.readlink().as_posix() != target
                    or not path.resolve().is_relative_to(directory.resolve())
                    or not path.exists()):
                raise ValueError('cache symlink changed or escaped')
        actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*')
                  if p.is_file() or p.is_symlink()}
        if actual != set(meta['files']) | set(links) | {'cache.json'}:
            raise ValueError('unlisted cache artifacts')
        return meta
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise RuntimeError(f'cache rejected: {exc}') from exc


def load_manifest(root):
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    root = Path(root).resolve()
    try:
        data = tomllib.loads((root/'laws.toml').read_text())
    except (OSError, ValueError) as exc:
        raise ValueError(f'invalid laws.toml: {exc}') from exc
    if data.get('toolchain') != TOOLCHAIN:
        raise ValueError('unknown toolchain; requires bend-2.0.34')
    domains = data.get('domain')
    if not isinstance(domains, list) or not domains:
        raise ValueError('laws.toml requires at least one [[domain]]')
    names = set()
    for domain in domains:
        if not isinstance(domain, dict):
            raise ValueError('domain must be a TOML table')
        name = domain.get('name')
        if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_]*', name) or name in names:
            raise ValueError('domain names must be unique lowercase identifiers')
        names.add(name)
        for key in ('dir', 'twin', 'parity', 'mutation'):
            value = domain.get(key)
            if not isinstance(value, str) or not value or Path(value).is_absolute():
                raise ValueError(f'domain {name}: required relative path {key}')
            path = (root/value).resolve()
            if not path.is_relative_to(root) or '..' in Path(value).parts:
                raise ValueError(f'domain {name}: path escapes repository')
        gates = domain.get('gate', [])
        if not isinstance(gates, list) or any(not isinstance(p, str) or Path(p).is_absolute()
                or '..' in Path(p).parts or not (root/p).resolve().is_relative_to(root) for p in gates):
            raise ValueError('gate must contain repository-relative paths')
        if domain.get('critic') not in (None, 'gdp'):
            raise ValueError('unknown critic')
    return data


def write_json(path, data):
    """Atomic same-directory replacement, never a system-temp staging file."""
    import json
    import os
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name+'.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, indent=2)
            stream.write('\n')
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def prove(root, domains, *, verify=None, all_domains=False):
    """Lock files are local optimization receipts, not trusted CI attestations."""
    import hashlib
    import json
    from datetime import datetime, timezone
    from .cache import PINS, cache_lock, safe_directory
    if verify is None:
        from .verifier import verdict
        verify = verdict
    root = Path(root).resolve()
    state = safe_directory(root/'.z0')
    receipts = []
    with cache_lock(state, 'laws-state'):
        lock = state/'laws.lock'
        try:
            previous = json.loads(lock.read_text()) if lock.exists() else {}
            if not isinstance(previous, dict) or any(not isinstance(entry, dict) for entry in previous.values()):
                raise ValueError('lock must map domain names to receipt objects')
        except (ValueError, OSError) as exc:
            raise RuntimeError('invalid laws.lock; refusing unchanged skip') from exc
        for domain in domains:
            folder = root/domain['dir']
            for name in ('MODEL.bend', 'LAWS.bend', 'PROOF.bend'):
                if not (folder/name).is_file():
                    raise RuntimeError(f'missing {domain["name"]}/{name}')
            inputs = {p.relative_to(root).as_posix():file_sha256(p) for p in sorted(folder.rglob('*.bend'))}
            # Include shared verifier and cache implementation so verifier changes invalidate skips.
            inputs['toolchain'] = file_sha256(PINS)
            for name in ('__init__.py', 'verifier.py', 'cache.py'):
                inputs['verifier/'+name] = file_sha256(Path(__file__).parent/name)
            key = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
            old = previous.get(domain['name'], {})
            unchanged = (not all_domains and old.get('sha256') == key
                         and old.get('verdict') == 'ALL PROOFS CHECK'
                         and old.get('toolchain') == TOOLCHAIN)
            if not unchanged:
                previous.pop(domain['name'], None)
                write_json(lock, previous)  # failed forced recheck must invalidate an old success
                try:
                    result = verify(folder)
                    if result != 'ALL PROOFS CHECK':
                        raise RuntimeError('verifier did not return ALL PROOFS CHECK')
                except Exception:
                    write_json(state/'laws.receipt.json', receipts+[dict(domain=domain['name'], status='failed', sha256=key, proof_is_permission=False)])
                    raise
                previous[domain['name']] = dict(domain=domain['name'], sha256=key,
                    toolchain=TOOLCHAIN, verdict=result, date=datetime.now(timezone.utc).isoformat())
                write_json(lock, previous)
            receipts.append(dict(domain=domain['name'], status='unchanged' if unchanged else 'proven',
                sha256=key, toolchain=TOOLCHAIN, verdict='ALL PROOFS CHECK',
                date=datetime.now(timezone.utc).isoformat(), proof_is_permission=False,
                source_semantics_attested=False))
        write_json(state/'laws.receipt.json', receipts)
    return receipts
