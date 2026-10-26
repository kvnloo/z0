"""Read the last receipt; accept only C1 steps already named by its plan."""
from __future__ import annotations

import json
import sys

from . import cli
from .apply import (ApplyError, check_hash, effective_plan, load_json, make_ctx,
                    request_from_plan, run_dir_for, execute_plan, workspace_update,
                    write_private)
from . import journal as journal_mod
from .lock import LockHeld, hold
from .plan import plan, plan_hash


def cmd_status(args) -> int:
    try:
        run = run_dir_for(cli._z0_home(), None)
        receipt = load_json(run / 'receipt.json')
    except (ApplyError, OSError, ValueError) as exc:
        print('What you need to do:')
        print('  Run ./z0 onboard to create an applied run and receipt.')
        print(f'z0 onboard status: {exc}', file=sys.stderr)
        return 2
    print('What you need to do:')
    for ask in receipt.get('asks') or []:
        print(f"  [{ask.get('consent', '')}] {ask['id']}: {ask['reason']}")
        print(f"    {ask['command']}")
    if not receipt.get('asks'):
        print('  Nothing.')
    print(f"\nLast run: {receipt['run_id']}; plan {receipt['plan_hash'][:12]}")
    print(cli.receipt_summary(run, receipt))
    for item in receipt.get('installed') or []:
        print(f"  installed {item['component']} @ {item['sha']}")
    print('Drift: not probed (status is read-only); use ./z0 onboard plan.')
    return 0


def acceptance_delta(previous, candidate, receipt, bundles, probe):
    """No C0, C2, changed step definition, or newly discovered step can run here.

    Successful prior results are retained for dependencies and reporting. All other
    nonselected todo steps are blocked, including checks, so VERIFY cannot execute
    unrelated commands. Failed/unfulfilled prerequisites require a normal rerun.
    """
    before = {e['step']['id']: e for e in previous['steps']}
    prior = {s['id']: {k: v for k, v in s.items() if k in ('status', 'reason', 'remediation')}
             for s in receipt.get('steps') or []}
    selected = set()
    for entry in candidate['steps']:
        step, state = entry['step'], entry['state']
        sid = step['id']
        old = before.get(sid)
        done = prior.get(sid, {}).get('status') in ('passed', 'already_satisfied')
        allowed = (old and old['step'] == step and not done
                   and step['consent']['class'] == 'C1'
                   and step['consent'].get('bundle') in bundles)
        if allowed and state['status'] == 'todo':
            selected.add(sid)
            prior.pop(sid, None)
        elif done and old and old['step'] == step and state['status'] in ('todo', 'already_satisfied'):
            if state['status'] == 'todo' and step['kind'] != 'check' and not probe(step):
                entry['state'] = {'status': 'blocked', 'reason': 'prior_artifact_missing'}
                prior.pop(sid, None)
            else:
                entry['state'] = {'status': 'already_satisfied'}
        elif state['status'] == 'todo':
            entry['state'] = {'status': 'blocked', 'reason': 'not_selected_by_accept'}
    # A selected step must not consume an unexecuted C0/new prerequisite.
    bad = {e['step']['id'] for e in candidate['steps']
           if e['state']['status'] not in ('todo', 'already_satisfied')}
    for entry in candidate['steps']:
        sid = entry['step']['id']
        if sid not in selected:
            continue
        blocker = next((n for n in entry['step'].get('needs') or [] if n in bad), None)
        if blocker:
            entry['state'] = {'status': 'blocked', 'reason': 'dependency', 'blocked_by': blocker}
            selected.remove(sid)
            bad.add(sid)
    candidate['plan_hash'] = plan_hash(candidate)
    return candidate, prior, selected


def cmd_accept(args) -> int:
    bundles = {b for text in args.bundles for b in cli._ids(text)}
    if not bundles or bundles - set(cli.BUNDLES):
        print('z0 onboard accept: expected C1 bundles: ' + ','.join(cli.BUNDLES), file=sys.stderr)
        return 2
    try:
        with hold(cli._z0_home()):
            run = run_dir_for(cli._z0_home(), None)
            check_hash(run, load_json(run / 'plan.json'))
            previous = effective_plan(run)
            if plan_hash(previous) != previous.get('plan_hash'):
                raise ApplyError(4, 'last effective plan hash does not match; refused')
            receipt = load_json(run / 'receipt.json')
            host, snap = cli.run_detect(fetch=False)
            if host.get('host_id') != previous.get('host_id'):
                raise ApplyError(4, 'last plan belongs to another host (H1); refused')
            request = request_from_plan(previous, snap)
            grants = {'bundles': sorted(set(previous['grants']['bundles']) | bundles), 'source': 'flag'}
            # Limit grants before planning as well as limiting execution afterwards.
            done = {s['id'] for s in receipt.get('steps') or []
                    if s['status'] in ('passed', 'already_satisfied')}
            grants['steps'] = [e['step']['id'] for e in previous['steps']
                               if e['step']['consent']['class'] == 'C1'
                               and (e['step']['consent'].get('bundle') in bundles
                                    or e['step']['id'] in done)]
            request['grants'] = grants
            candidate = plan(host, snap, **request)
            if candidate['registry'] != previous['registry']:
                raise ApplyError(4, 'registry changed since the last plan; run ./z0 onboard again')
            deps = cli.make_deps(snap, detect=False)
            journal = journal_mod.Journal(run / 'journal.jsonl', run.name)
            ctx = make_ctx(run, candidate, host, deps, journal)
            from .apply import satisfied_now
            candidate, prior, selected = acceptance_delta(
                previous, candidate, receipt, bundles, lambda step: satisfied_now(ctx, step))
            if not selected:
                print('No runnable pending steps in those bundles. Run ./z0 onboard status; '
                      'unmet prerequisites need a normal ./z0 onboard rerun.')
                requested = [e for e in candidate['steps'] if e['step']['consent']['class'] == 'C1'
                             and e['step']['consent'].get('bundle') in bundles]
                return 3 if any(e['state']['status'] not in ('already_satisfied',) for e in requested) else 0
            write_private(run / 'plan.replan.json', json.dumps(candidate, indent=2, sort_keys=True) + '\n')
            journal.write('accept', bundles=sorted(bundles), steps=sorted(selected),
                          plan_hash=candidate['plan_hash'])
            ctx = make_ctx(run, candidate, host, deps, journal)
            results = execute_plan(ctx, candidate, deps)
            results.update(prior)
            workspace_update(ctx, candidate, results)
            from .verify import verify_run
            code, receipt = verify_run(run, deps, prior=results, host=host,
                                      apply_code=1 if any(r['status'] == 'failed' for r in results.values()) else 0,
                                      consent_code=3 if any(a.get('consent') == 'C1' for a in candidate['asks']) else 0)
            print(cli.receipt_summary(run, receipt))
            return code
    except (ApplyError, LockHeld, OSError, ValueError) as exc:
        print(f'z0 onboard accept: {exc}', file=sys.stderr)
        return exc.code if isinstance(exc, ApplyError) else 1
