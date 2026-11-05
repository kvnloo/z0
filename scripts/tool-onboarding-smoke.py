#!/usr/bin/env python3
"""Bounded, credential-free onboarding evidence. Never installs or repairs services."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
from datetime import datetime, timezone


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True,
                        help='New evidence directory, never overwritten')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    records = []

    def run(name, argv, env=None, seconds=10):
        log = output / (name + '.log')
        with log.open('w') as stream:
            stream.write('$ ' + shlex.join(map(str, argv)) + '\n')
            stream.flush()
            try:
                result = subprocess.run(list(map(str, argv)), cwd=root, env=env,
                                        stdout=stream, stderr=subprocess.STDOUT,
                                        timeout=seconds, check=False)
                code = result.returncode
            except subprocess.TimeoutExpired:
                code = 124
                stream.write('\nTimed out. No success inferred.\n')
            except OSError as exc:
                code = 127
                stream.write(str(exc) + '\n')
            stream.write(f'\nEXIT_CODE={code}\n')
        records.append({'name': name, 'argv': list(map(str, argv)),
                        'exit_code': code, 'log': str(log)})
        return code

    inventory = {}
    for name in ('hermes', 't3', 'hf', 'z0', 'rtk', 'ctx', 'agentsview', 'git', 'rg', 'uv', 'jq'):
        entry = shutil.which(name)
        inventory[name] = {'path': entry, 'resolved': str(Path(entry).resolve()) if entry else None}
    (output / 'entrypoints.json').write_text(json.dumps(inventory, indent=2) + '\n')
    run('t3-doctor', ['t3', 'doctor', '--dry-run'])
    run('hf-version', ['hf', 'version'])
    run('rtk-version', ['rtk', '--version'])
    run('z0-native-doctor', [root / 'z0', 'doctor'])
    isolated = ['uv', 'run', '--offline', '--no-project', '--with', 'PyYAML',
                '--with', 'ruamel.yaml', '--with', 'tomlkit', str(root / 'z0')]
    run('z0-isolated-doctor', isolated + ['doctor'])
    receipt = output / 'native-bindings.json'
    run('z0-native-bindings', isolated + ['doctor', '--bindings', '--harness', 'hermes',
                                        '--harness-profile', 'clean', '--receipt', str(receipt)])
    findings = None
    if receipt.exists():
        observation = json.loads(receipt.read_text())
        findings = [finding for config in observation['configs'] for finding in config['findings']]

    # An isolated HF home and disabled implicit auth prevent token lookup or refresh.
    # See huggingface_hub/utils/_headers.py:get_token_to_send.
    env = os.environ.copy()
    env.update({'HF_ENDPOINT': 'https://huggingface.co',
                'HF_HOME': str(output / 'hf-home'), 'HF_TOKEN': '',
                'HUGGING_FACE_HUB_TOKEN': '', 'HF_HUB_DISABLE_IMPLICIT_TOKEN': '1',
                'HF_HUB_DISABLE_TELEMETRY': '1', 'HF_HUB_DISABLE_UPDATE_CHECK': '1',
                'HF_HUB_ETAG_TIMEOUT': '5', 'HF_HUB_DOWNLOAD_TIMEOUT': '5'})
    repo = 'google-bert/bert-base-uncased'
    revision = '86b5e0934494bd15c9632b12f734a8a67f723594'
    artifact = output / 'download' / 'config.json'
    download = run('hf-public-download', ['hf', 'download', repo, 'config.json', '--revision',
                   revision, '--local-dir', artifact.parent, '--max-workers', '1'], env=env)
    workflow = False
    digest = None
    if download == 0 and artifact.is_file():
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        parsed = json.loads(artifact.read_text())
        rtk = run('rtk-consume-hf', ['rtk', 'json', '--keys-only', artifact])
        jq = run('jq-consume-hf', ['jq', '-e', '.model_type == "bert" and .hidden_size == 768', artifact])
        witness = output / 'http-config.json'
        url = f'https://huggingface.co/{repo}/resolve/{revision}/config.json'
        http = run('hf-http-witness', ['curl', '--disable', '--location', '--fail', '--silent',
                   '--show-error', '--max-time', '8', '--max-filesize', '4096', '--output', witness,
                   '--write-out', 'HTTP_STATUS=%{http_code}\nURL=%{url_effective}\n', url])
        keys = (output / 'rtk-consume-hf.log').read_text()
        workflow = (rtk == jq == http == 0 and parsed.get('model_type') == 'bert'
                    and 'model_type' in keys and witness.read_bytes() == artifact.read_bytes())
    remaining = [
        'Hermes native doctor not run: canonical launcher enters bws-env-exec; credential handling is forbidden.',
        'No native Hermes/T3 model-plus-tool workflow: no qualified no-spend route was established.',
        'HF intended meaning and target workflow remain unspecified. Public metadata is not authenticated onboarding.',
        'No canonical deployed z0 entrypoint established. Isolated source execution is not deployment.',
        'All-tools inventory and web/memory/history/Serena acceptance remain incomplete.',
    ]
    report = {'schema': 'r10-onboarding-smoke.v1', 'at': datetime.now(timezone.utc).isoformat(),
              'root': str(root), 'checks': records, 'binding_findings': findings,
              'workflow': {'scope': 'anonymous HF pinned config -> RTK keys and jq value checks -> HTTP byte comparison',
                           'passed': workflow, 'artifact': str(artifact), 'sha256': digest,
                           'repo': repo, 'revision': revision},
              'accepted': False, 'remaining': remaining}
    destination = output / 'acceptance.json'
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'acceptance': str(destination), 'workflow_passed': workflow,
                      'accepted': False, 'checks': {r['name']: r['exit_code'] for r in records}}, indent=2))
    return 1  # This bounded smoke cannot establish the full owner acceptance.


if __name__ == '__main__':
    raise SystemExit(main())
