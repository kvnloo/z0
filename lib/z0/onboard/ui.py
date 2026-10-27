"""Small stream-based guided UI; choices never confer execution authority."""
from __future__ import annotations

import getpass
import sys


class UI:
    def __init__(self, stdin=None, stdout=None):
        self.stdin = sys.stdin if stdin is None else stdin
        self.stdout = sys.stdout if stdout is None else stdout

    @property
    def tty(self):
        return self.stdin.isatty() and self.stdout.isatty()

    def choice(self, question, options, default):
        if default not in options:
            raise ValueError('default must be a listed option')
        if not self.tty:
            return default
        while True:
            self.stdout.write(f"{question} ({'/'.join(options)}) [{default}]: ")
            self.stdout.flush()
            answer = self.stdin.readline()
            if not answer:
                return default
            answer = answer.strip() or default
            if answer in options:
                return answer
            self.stdout.write('Choose one of the listed options.\n')

    def confirm(self, question):
        return self.choice(question, ['no', 'yes'], 'no') == 'yes'

    def secret(self, name, store, redactor):
        """The caller supplies the component's owning-store writer, never a run file.

        No fallback to echoed input: getpass warnings are fatal. The writer must not
        return the value, and the value is registered before it leaves this scope.
        """
        import warnings
        if not self.tty:
            raise ValueError('secret entry needs a TTY')
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            value = getpass.getpass(f'{name} (empty to skip): ', stream=self.stdout)
        if value:
            redactor.register(value)
            store(name, value)
        return bool(value)


def configure(args, host, snap):
    from . import regsnap
    from .plan import plan
    ui = UI()
    if not ui.tty:
        raise ValueError('--guided needs a TTY')
    baseline = plan(host, snap, profile=args.profile, mode='guided')
    if not baseline['profile']:
        return None  # retain the hardware refusal; there is no safe default to select
    args.profile = ui.choice('Profile', list(regsnap.profiles(snap)),
                             args.profile or baseline['profile'])
    included = set((args.with_ids or '').split(',')) - {''}
    excluded = set((args.without_ids or '').split(',')) - {''}
    for cid in regsnap.profile_policy(snap).get('auto_supplementals') or []:
        default = 'no' if cid in excluded else 'yes'
        if ui.choice(f'Include {cid}?', ['no', 'yes'], default) == 'yes':
            excluded.discard(cid)
        else:
            excluded.add(cid)
            included.discard(cid)
    args.with_ids, args.without_ids = ','.join(sorted(included)), ','.join(sorted(excluded))
    args.pin_policy = ui.choice('Pin policy', ['pinned', 'tip'], args.pin_policy)
    args.llm = ui.choice('LLM classification (remote quota needs separate consent)',
                         ['none', 'local', 'auto'], args.llm)
    return args.profile


def consent(candidate, already_granted=()):
    """Per-step C1 consent. C2/manual actions stay asks, never shell commands here."""
    from .plan import _c1_reason
    ui = UI()
    selected = []
    bundles = set(already_granted)
    for entry in candidate['steps']:
        step = entry['step']
        if step['consent']['class'] != 'C1' or entry['state']['status'] != 'todo':
            continue
        bundle = step['consent']['bundle']
        if bundle in already_granted or ui.confirm(f"Apply {step['id']}: {_c1_reason(step)}?"):
            bundles.add(bundle)
            selected.append(step['id'])
    return {'bundles': sorted(bundles), 'source': 'tty', 'steps': selected}
