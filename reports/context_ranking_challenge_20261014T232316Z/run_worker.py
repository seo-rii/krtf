import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

meta = json.loads(Path(sys.argv[1]).read_text())
status_path = Path(meta['status_path'])
status = {'run_id': meta['run_id'], 'state': 'RUNNING', 'pid': os.getpid(),
          'started_at': time.time(), 'source_revision': meta['source_revision'],
          'archive_sha256': meta['archive_sha256'], 'stages': []}


def write_status():
    temporary = status_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(status, indent=2) + '\n')
    temporary.chmod(0o600)
    temporary.replace(status_path)


def stage(name, command):
    log = Path(meta['log_dir']) / (meta['run_id'] + '-' + name + '.log')
    current = {'name': name, 'state': 'RUNNING', 'command': command,
               'log_path': str(log), 'started_at': time.time()}
    status['stages'].append(current)
    write_status()
    with log.open('w') as handle:
        log.chmod(0o600)
        result = subprocess.run(command, cwd=meta['source'], stdout=handle,
                                stderr=subprocess.STDOUT, timeout=1200,
                                env={**os.environ, 'KTRF_CODE_REVISION': meta['source_revision'],
                                     'PYTHONPATH': meta['source'], 'OMP_NUM_THREADS': '4',
                                     'MKL_NUM_THREADS': '4', 'HF_HUB_OFFLINE': '1',
                                     'HF_HUB_DISABLE_PROGRESS_BARS': '1', 'PYTHONHASHSEED': '0'})
    current.update(state='COMPLETED' if result.returncode == 0 else 'FAILED',
                   exit_code=result.returncode, finished_at=time.time())
    write_status()
    if result.returncode:
        raise RuntimeError('stage failed: ' + name)


write_status()
try:
    archive = Path(meta['remote_root']) / 'source.tar.gz'
    if hashlib.sha256(archive.read_bytes()).hexdigest() != meta['archive_sha256']:
        raise RuntimeError('source archive hash mismatch')
    result = Path(meta['remote_root']) / 'results'
    result.mkdir(mode=0o700, exist_ok=True)
    stage('validation', [meta['python'], '-m', 'pytest', '-q'])
    stage('freeze', [meta['model_python'], str(Path(meta['remote_root']) / 'freeze.py'),
                     sys.argv[1]])
    common = ['-m', 'eval.run_context_ranking_challenge', '--cases', str(result / 'cases.jsonl'),
              '--repeats', '1', '--source-revision', meta['source_revision']]
    stage('lexical', [meta['python'], *common, '--backend', 'lexical',
                      '--out', str(result / 'lexical.json')])
    stage('nano', [meta['model_python'], *common, '--backend', 'scalar',
                   '--model-dir', meta['model_dir'], '--model-id', meta['model_id'],
                   '--model-revision', meta['model_revision'], '--device', 'cuda',
                   '--max-length', '1024', '--out', str(result / 'nano.json')])
    manifest = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(result.iterdir()) if path.is_file()}
    (result / 'output_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    status.update(state='COMPLETED', exit_code=0, finished_at=time.time(),
                  output_manifest=manifest)
except BaseException:
    traceback.print_exc()
    status.update(state='FAILED', exit_code=1, finished_at=time.time())
write_status()
raise SystemExit(status['exit_code'])
