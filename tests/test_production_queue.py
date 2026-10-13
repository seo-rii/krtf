"""Frozen queue identity, resource waiting and failure accounting."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from eval import run_production_queue as queue


def _plan(tmp_path):
    source = tmp_path / 'source.tar'
    source.write_bytes(b'frozen code')
    proof = tmp_path / 'unit.json'
    proof.write_text(json.dumps({'exit_code': 0, 'code_revision': 'revision'}))
    envelope = {'requests': [{'case_id': 'case', 'task': 'document_qa'}]}
    requests = tmp_path / 'requests.json'
    requests.write_bytes(queue.canonical(envelope))
    request_hash = hashlib.sha256(queue.canonical(envelope['requests'][0])).hexdigest()
    stages = [{'id': track + '_' + model, 'track': track, 'model_key': model,
               'requests_file': str(requests), 'request_count': 1,
               'requests_sha256': request_hash, 'envelope_sha256': queue.file_hash(requests)}
              for track in ('production_synthetic', 'production_real')
              for model in ('gemma12b', 'qwen27b')]
    return {'schema_version': 1, 'stages': stages, 'port': 18104,
            'models': {key: {'gpu_memory_utilization': .5, 'path': str(tmp_path / key),
                             'served_name': key} for key in ('gemma12b', 'qwen27b')},
            'run_id': 'test-queue', 'run_root': str(tmp_path),
            'status_path': str(tmp_path / 'status.json'), 'code_revision': 'revision',
            'source_archive': str(source), 'archive_sha256': queue.file_hash(source),
            'unit_status': str(proof)}


def test_queue_rejects_order_change_or_unpaired_request_sets(tmp_path):
    plan = _plan(tmp_path)
    assert queue.validate_plan(plan) is plan
    swapped = deepcopy(plan)
    swapped['stages'][0], swapped['stages'][1] = swapped['stages'][1], swapped['stages'][0]
    with pytest.raises(ValueError, match='four predeclared'):
        queue.validate_plan(swapped)
    unmatched = deepcopy(plan)
    unmatched['stages'][1]['requests_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='identical frozen requests'):
        queue.validate_plan(unmatched)
    mutable_model = deepcopy(plan)
    mutable_model['models']['qwen27b'].update(repo_id='Qwen/model', revision='main')
    with pytest.raises(ValueError, match='immutable revision'):
        queue.validate_plan(mutable_model)


def test_request_envelope_is_sealed_before_runtime_work(tmp_path):
    plan = _plan(tmp_path)
    stage = plan['stages'][0]
    assert len(queue.validate_requests(stage)['requests']) == 1
    Path(stage['requests_file']).write_text('{}')
    with pytest.raises(ValueError, match='envelope changed'):
        queue.validate_requests(stage)


def test_setup_failure_records_each_stage_and_continues_in_declared_order(tmp_path):
    plan = _plan(tmp_path)
    assert queue.run_queue(plan) == 1
    status = json.loads(Path(plan['status_path']).read_text())
    assert status['phase'] == 'FINISHED' and status['status'] == 'FAILED'
    assert [s['id'] for s in status['stages']] == [s['id'] for s in plan['stages']]
    assert all(s['status'] == 'FAILED' and s['exit_code'] == 1 for s in status['stages'])
    assert all(s['error']['message'] == 'model config is unavailable' for s in status['stages'])
    assert all('finished_at' in s for s in status['stages'])
    with pytest.raises(ValueError, match='duplicate launch'):
        queue.run_queue(plan)


def test_failed_test_proof_blocks_every_model_stage(tmp_path):
    plan = _plan(tmp_path)
    Path(plan['unit_status']).write_text(json.dumps({'exit_code': 1, 'code_revision': 'revision'}))
    assert queue.run_queue(plan) == 1
    status = json.loads(Path(plan['status_path']).read_text())
    assert status['error']['message'] == 'successful tests at the frozen revision are required'
    assert all(s['status'] == 'PENDING' for s in status['stages'])


def test_resource_wait_preserves_other_gpu_work(monkeypatch):
    observations = iter(['81920, 20000', '81920, 70000'])
    commands, sleeps, updates = [], [], []
    def check_output(command, **kwargs):
        commands.append(command)
        return next(observations)
    class Port:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def bind(self, address): assert address == ('127.0.0.1', 18104)
    monkeypatch.setattr(queue.subprocess, 'check_output', check_output)
    monkeypatch.setattr(queue.socket, 'socket', Port)
    monkeypatch.setattr(queue.time, 'sleep', sleeps.append)
    free = queue.wait_for_resources({'port': 18104}, {'gpu_memory_utilization': .72},
                                    lambda **values: updates.append(values))
    assert free == 70000 and sleeps == [60]
    assert [v['phase'] for v in updates] == ['WAITING_FOR_RESOURCE', 'RESOURCE_CHECK']
    assert updates[-1]['required_free_mib'] == int(81920 * .72) + 2048
    assert all(command[0] == 'nvidia-smi' for command in commands)


def test_successful_stages_release_runtime_before_starting_next(tmp_path, monkeypatch):
    from io import BytesIO
    from types import SimpleNamespace
    plan = _plan(tmp_path)
    plan.update(source=str(tmp_path), log_dir=str(tmp_path), python='python',
                model_python='model-python', hf_home=str(tmp_path / 'cache'))
    for model in plan['models'].values():
        Path(model['path']).mkdir()
        (Path(model['path']) / 'config.json').write_text('{}')
    events, live_servers = [], []
    served = {'name': None}
    class Process:
        next_pid = 1000
        def __init__(self, command, **kwargs):
            Process.next_pid += 1
            self.pid = Process.next_pid
            self.returncode = None
            self.server = 'vllm.entrypoints.openai.api_server' in command
            if self.server:
                assert not live_servers, 'previous model runtime must be released first'
                live_servers.append(self)
                served['name'] = command[command.index('--served-model-name') + 1]
                events.append(('start', served['name']))
            else:
                out = Path(command[command.index('--out-dir') + 1])
                out.mkdir(parents=True)
                stage = next(s for s in plan['stages'] if s['id'] == out.name)
                manifest = {'request_corpus_sha256': stage['requests_sha256'],
                    'request_count': 1, 'code_revision': plan['code_revision'],
                    'track': stage['track'], 'requested_model': served['name'],
                    'received_count': 1, 'malformed_count': 0, 'missing_count': 0, 'error_count': 0}
                (out / 'run_manifest.json').write_text(json.dumps(manifest))
                self.returncode = 0
                events.append(('benchmark', served['name']))
        def poll(self): return self.returncode
    def stop(process):
        if process.server:
            live_servers.remove(process)
            events.append(('stop', served['name']))
        process.returncode = 0
    monkeypatch.setattr(queue.subprocess, 'Popen', Process)
    monkeypatch.setattr(queue.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(returncode=0))
    monkeypatch.setattr(queue, 'stop_owned', stop)
    monkeypatch.setattr(queue, 'wait_for_resources', lambda *args: 70000)
    monkeypatch.setattr(queue, 'urlopen', lambda *args, **kwargs:
        BytesIO(json.dumps({'data': [{'id': served['name']}]}).encode()))
    assert queue.run_queue(plan) == 0
    assert not live_servers
    assert events == [(action, model) for model in ('gemma12b', 'qwen27b', 'gemma12b', 'qwen27b')
                      for action in ('start', 'benchmark', 'stop')]
    status = json.loads(Path(plan['status_path']).read_text())
    assert all(s['status'] == 'COMPLETE' and s['received_count'] == 1 for s in status['stages'])
