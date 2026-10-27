"""Guided-only LaunchAgent previews (design §8.4); never load a service.

A preview is deliberately not installation/health evidence. Paths come from the
plan's stamped release/runtime steps, never the mutable development tree.
"""
from __future__ import annotations

import os
import plistlib
import re

from .actions.base import has_git_ancestor

# launchd lacks flock. Keep the fcntl lock in the supervising Python process for
# the whole child's lifetime; argv stays a list, never shell-interpolated text.
LOCK_WRAPPER = (
    'import fcntl, os, subprocess, sys\n'
    'os.makedirs(os.path.dirname(sys.argv[1]), mode=0o700, exist_ok=True)\n'
    'with open(sys.argv[1], "a") as lock:\n'
    '    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)\n'
    '    sys.exit(subprocess.call(sys.argv[2:]))\n'
)


def render_plist(label, argv, working_directory, lock_path, *, env=None, restart_sec=10):
    """Return well-formed XML, suitable for plistlib or plutil -lint.

    Only explicit environment entries are emitted. Callers must supply public,
    nonsecret config; no inherited environment is copied into the plist.
    """
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', label):
        raise ValueError('invalid launchd label')
    if not argv or not os.path.isabs(argv[0]):
        raise ValueError('launchd needs an absolute interpreter')
    if not os.path.isabs(working_directory) or not os.path.isabs(lock_path):
        raise ValueError('launchd paths must be absolute')
    if has_git_ancestor(argv[0]) or has_git_ancestor(working_directory):
        raise ValueError('launchd cannot run through a checkout (S1)')
    data = {'Label': label, 'ProgramArguments': [argv[0], '-c', LOCK_WRAPPER, lock_path, *argv],
            'WorkingDirectory': working_directory, 'RunAtLoad': True,
            'KeepAlive': {'SuccessfulExit': False}, 'ThrottleInterval': restart_sec,
            'EnvironmentVariables': dict(env or {})}
    return plistlib.dumps(data, fmt=plistlib.FMT_XML, sort_keys=True)


def guided_previews(run, host, plan_obj, *, ui=None, home=None):
    """Render the z0int router from its planned runtime and release, if requested.

    Linux/systemd remains the release mode. No files under Library/LaunchAgents
    are changed and launchctl is never invoked. Component activation is separate.
    """
    if plan_obj.get('mode') != 'guided' or host.get('os', {}).get('os') != 'darwin':
        return []
    from .ui import UI
    from .apply import write_private
    ui = ui or UI()
    if not ui.tty:
        return []
    steps = {e['step']['id']: e for e in plan_obj['steps']}
    router = steps.get('z0intelligence.router.unit')
    if not router or router['step']['consent']['class'] != 'C1':
        return []
    if router['state'].get('reason') in ('host_mismatch', 'intel_mac', 'python_window', 'open_bind'):
        return []
    runtime = steps.get('z0intelligence.runtime', {}).get('step', {}).get('creates', [])
    release = steps.get('z0intelligence.release', {}).get('step', {}).get('creates', [])
    if not runtime or not release:
        return []
    if not ui.confirm('Render a z0intelligence launchd preview (not installed or started)?'):
        return []
    home = home or os.path.expanduser('~')
    expand = lambda p: home + p[1:] if p.startswith('~/') else p
    interpreter = expand(runtime[0]) + '/bin/python'
    root = expand(release[0])
    service = router['step']['service']
    if service.get('bind') != 'loopback':
        raise ValueError('the z0intelligence LaunchAgent requires the loopback bind class')
    data = render_plist('com.z0.z0intelligence',
                        [interpreter, '-m', 'z0int.intelligence_service', '--port', str(service['port'])],
                        root, os.path.join(home, '.z0int', 'locks', 'router.lock'),
                        env={'PATH': ':'.join(expand(p) for p in plan_obj.get('prepared_path') or []),
                             'PYTHONPATH': root + '/src'})
    target = run / 'launchd'
    target.mkdir(mode=0o700, exist_ok=True)
    path = target / 'com.z0.z0intelligence.plist'
    write_private(path, data.decode('utf-8'))
    ui.stdout.write(f'LaunchAgent preview: {path}; review before manual installation.\n')
    return [path]
