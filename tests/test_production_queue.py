"""Frozen queue identity, resource waiting and failure accounting."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from eval import run_production_queue as queue


def _plan(tmp_path, *, schema_version=1):
    source = tmp_path / 'source.tar'
    source.write_bytes(b'frozen code')
    proof = tmp_path / 'unit.json'
    proof.write_text(json.dumps({'exit_code': 0, 'code_revision': 'revision'}))
    prefix = 'baseline' if schema_version == 2 else 'production'
    stages = []
    for corpus in ('synthetic', 'real'):
        count = (874 if corpus == 'synthetic' else 120) if schema_version == 2 else 1
        envelope = {'requests': [{'case_id': 'case-' + str(i), 'task': 'document_qa'} for i in range(count)]}
        requests = tmp_path / (corpus + '-requests.json')
        requests.write_bytes(queue.canonical(envelope))
        request_hash = hashlib.sha256(b''.join(queue.canonical(row) for row in envelope['requests'])).hexdigest()
        track = prefix + '_' + corpus
        stages.extend({'id': track + '_' + model, 'track': track, 'model_key': model,
            'requests_file': str(requests), 'request_count': count,
            'requests_sha256': request_hash, 'envelope_sha256': queue.file_hash(requests)}
            for model in ('gemma12b', 'qwen27b'))
    plan = {'schema_version': schema_version, 'stages': stages, 'port': 18104,
            'models': {key: {'gpu_memory_utilization': .5, 'path': str(tmp_path / key),
                             'served_name': key} for key in ('gemma12b', 'qwen27b')},
            'run_id': 'test-queue', 'run_root': str(tmp_path),
            'status_path': str(tmp_path / 'status.json'), 'code_revision': 'revision',
            'source_archive': str(source), 'archive_sha256': queue.file_hash(source),
            'unit_status': str(proof)}
    if schema_version == 5:
        plan['stages'] = stages[:2]
        for stage in plan['stages']:
            stage.update(id='hf_qa_' + stage['model_key'], track='hf_qa')
        token_proof = tmp_path / 'tokens.json'
        token_proof.write_text(json.dumps({
            'exit_code': 0, 'code_revision': plan['code_revision'],
            'models': {stage['model_key']: {
                'requests_sha256': stage['requests_sha256'], 'request_count': stage['request_count'],
                'model_path': plan['models'][stage['model_key']]['path'], 'max_prompt_tokens': 1024}
                for stage in plan['stages']}}))
        plan['token_status'] = str(token_proof)
    return plan


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


def test_baseline_schema_keeps_fixed_counts_and_disallows_production_mix(tmp_path):
    plan = _plan(tmp_path, schema_version=2)
    assert queue.validate_plan(plan) is plan
    assert [stage['request_count'] for stage in plan['stages']] == [874, 874, 120, 120]
    assert queue.report_module_for_plan(plan) == 'eval.report_production_baseline'
    for index in range(4):
        changed = deepcopy(plan)
        changed['stages'][index]['request_count'] -= 1
        with pytest.raises(ValueError, match='874 synthetic and 120 real'):
            queue.validate_plan(changed)
    for version in (1, 3):
        changed = deepcopy(plan)
        changed['schema_version'] = version
        with pytest.raises(ValueError, match='four predeclared'):
            queue.validate_plan(changed)
    swapped = deepcopy(plan)
    swapped['stages'][0], swapped['stages'][1] = swapped['stages'][1], swapped['stages'][0]
    with pytest.raises(ValueError, match='four predeclared'):
        queue.validate_plan(swapped)
    unmatched = deepcopy(plan)
    unmatched['stages'][1]['envelope_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='identical frozen requests'):
        queue.validate_plan(unmatched)
    with pytest.raises(ValueError, match='unknown queue schema'):
        queue.report_module_for_plan({'schema_version': 6})


def test_hf_schema_requires_two_models_same_requests_and_tokenizer_proof(tmp_path):
    plan = _plan(tmp_path, schema_version=5)
    assert queue.validate_plan(plan) is plan
    assert queue.report_module_for_plan(plan) == 'eval.report_hf_qa'
    assert [(stage['track'], stage['model_key']) for stage in plan['stages']] == [
        ('hf_qa', 'gemma12b'), ('hf_qa', 'qwen27b')]
    changed = deepcopy(plan)
    changed['stages'].reverse()
    with pytest.raises(ValueError, match='predeclared'):
        queue.validate_plan(changed)
    changed = deepcopy(plan)
    changed['stages'][1]['track'] = 'definition_control'
    with pytest.raises(ValueError, match='predeclared'):
        queue.validate_plan(changed)
    for field, value in [('requests_sha256', '0' * 64), ('envelope_sha256', '0' * 64),
                         ('request_count', 2)]:
        changed = deepcopy(plan)
        changed['stages'][1][field] = value
        with pytest.raises(ValueError, match='identical frozen requests'):
            queue.validate_plan(changed)
    changed = deepcopy(plan)
    del changed['token_status']
    with pytest.raises(ValueError, match='actual tokenizer preflight'):
        queue.validate_plan(changed)


@pytest.mark.parametrize('field,value', [
    ('requests_sha256', '0' * 64), ('request_count', 2), ('model_path', 'other-model'),
    ('max_prompt_tokens', 8065), ('max_prompt_tokens', 0), ('max_prompt_tokens', True),
])
def test_hf_tokenizer_mismatch_blocks_all_gpu_work(tmp_path, monkeypatch, field, value):
    plan = _plan(tmp_path, schema_version=5)
    proof = json.loads(Path(plan['token_status']).read_text())
    proof['models']['gemma12b'][field] = value
    Path(plan['token_status']).write_text(json.dumps(proof))
    monkeypatch.setattr(queue.subprocess, 'Popen', lambda *args, **kwargs: pytest.fail('no GPU work before preflight'))
    assert queue.run_queue(plan) == 1
    state = json.loads(Path(plan['status_path']).read_text())
    assert 'tokenizer preflight differs' in state['error']['message']
    assert all(stage['status'] == 'PENDING' for stage in state['stages'])


@pytest.mark.parametrize('field,value', [('exit_code', 1), ('code_revision', 'different')])
def test_hf_failed_or_other_revision_token_proof_blocks_gpu_work(tmp_path, field, value):
    plan = _plan(tmp_path, schema_version=5)
    proof = json.loads(Path(plan['token_status']).read_text())
    proof[field] = value
    Path(plan['token_status']).write_text(json.dumps(proof))
    assert queue.run_queue(plan) == 1
    state = json.loads(Path(plan['status_path']).read_text())
    assert 'successful tokenizer preflight' in state['error']['message']
    assert all(stage['status'] == 'PENDING' for stage in state['stages'])


@pytest.mark.parametrize('schema_version', [1, 2, 5])
def test_request_envelope_is_sealed_before_runtime_work(tmp_path, schema_version):
    plan = _plan(tmp_path, schema_version=schema_version)
    stage = plan['stages'][0]
    assert len(queue.validate_requests(stage)['requests']) == stage['request_count']
    Path(stage['requests_file']).write_text('{}')
    with pytest.raises(ValueError, match='envelope changed'):
        queue.validate_requests(stage)


@pytest.mark.parametrize('schema_version', [1, 2, 5])
def test_setup_failure_records_each_stage_and_continues_in_declared_order(tmp_path, schema_version):
    plan = _plan(tmp_path, schema_version=schema_version)
    assert queue.run_queue(plan) == 1
    status = json.loads(Path(plan['status_path']).read_text())
    assert status['phase'] == 'FINISHED' and status['status'] == 'FAILED'
    assert [s['id'] for s in status['stages']] == [s['id'] for s in plan['stages']]
    assert all(s['status'] == 'FAILED' and s['exit_code'] == 1 for s in status['stages'])
    assert all(s['error']['message'] == 'model config is unavailable' for s in status['stages'])
    assert all('finished_at' in s for s in status['stages'])
    with pytest.raises(ValueError, match='duplicate launch'):
        queue.run_queue(plan)


@pytest.mark.parametrize('schema_version', [1, 2, 5])
def test_failed_test_proof_blocks_every_model_stage(tmp_path, schema_version):
    plan = _plan(tmp_path, schema_version=schema_version)
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


MEMORY_RACE = ('ValueError: Free memory on device cuda:0 (11.2/79.25 GiB) on startup '
               'is less than desired GPU memory utilization (0.45, 35.66 GiB). '
               'Decrease GPU memory utilization or reduce GPU memory used by other processes.')


def _retry_plan(tmp_path):
    import tarfile
    original = _plan(tmp_path, schema_version=5)
    original.update(source=str(tmp_path / 'inference'), log_dir=str(tmp_path), python='python',
                    model_python='model-python', hf_home=str(tmp_path / 'cache'))
    origin_path = tmp_path / 'original-plan.json'
    origin_path.write_bytes(queue.canonical(original))
    log = tmp_path / 'original-gemma.log'
    log.write_text(MEMORY_RACE)
    failed = {'id': original['stages'][0]['id'], 'request_count': 1, 'status': 'FAILED',
              'exit_code': 1, 'server_pid': 123, 'server_exit_code': 1,
              'server_log': str(log), 'model': 'gemma12b',
              'error': {'type': 'RuntimeError', 'message': 'owned model server exited during startup: 1'}}
    completed = {'id': original['stages'][1]['id'], 'request_count': 1, 'status': 'COMPLETE',
                 'exit_code': 0, 'benchmark_exit_code': 0, 'received_count': 1,
                 'missing_count': 0, 'error_count': 0, 'malformed_count': 0, 'model': 'qwen27b'}
    terminal = {'run_id': original['run_id'], 'code_revision': original['code_revision'],
                'plan_sha256': hashlib.sha256(queue.canonical(original)).hexdigest(),
                'status': 'FAILED', 'phase': 'FINISHED', 'exit_code': 1,
                'stages': [failed, completed]}
    Path(original['status_path']).write_bytes(queue.canonical(terminal))
    out = tmp_path / 'results' / completed['id']
    out.mkdir(parents=True)
    envelope = json.loads(Path(original['stages'][1]['requests_file']).read_text())
    (out / 'requests.jsonl').write_bytes(b''.join(queue.canonical(row) for row in envelope['requests']))
    (out / 'responses.jsonl').write_text('{}\n')
    (out / 'graded.json').write_text('{}\n')
    manifest = {'code_revision': original['code_revision'], 'track': 'hf_qa',
                'protocol': 'hf_qa_generation_v1', 'requested_model': 'qwen27b',
                'request_count': 1, 'received_count': 1, 'missing_count': 0, 'error_count': 0,
                'malformed_count': 0, 'status': 'COMPLETE',
                'request_corpus_sha256': original['stages'][1]['requests_sha256'],
                'frozen_request_file_sha256': original['stages'][1]['envelope_sha256'],
                'artifact_sha256': {name: queue.file_hash(out / name)
                                   for name in ('requests.jsonl', 'responses.jsonl', 'graded.json')}}
    manifest['seal_sha256'] = hashlib.sha256(queue.canonical(manifest)).hexdigest()
    (out / 'run_manifest.json').write_bytes(queue.canonical(manifest))
    (out / 'environment.json').write_bytes(queue.canonical({
        'code_revision': original['code_revision'], 'source_archive_sha256': original['archive_sha256'],
        'queue_plan_sha256': hashlib.sha256(queue.canonical(original)).hexdigest()}))
    orchestration_archive = tmp_path / 'orchestration.tar.gz'
    with tarfile.open(orchestration_archive, 'w:gz') as archive:
        archive.add(queue.__file__, arcname='eval/run_production_queue.py')
    proof = tmp_path / 'orchestration-unit.json'
    proof.write_bytes(queue.canonical({'code_revision': 'a' * 40, 'exit_code': 0}))
    plan = deepcopy(original)
    plan.update(run_id='retry-queue', run_root=str(tmp_path / 'retry'),
                status_path=str(tmp_path / 'retry-status.json'),
                retry_from={'plan_path': str(origin_path), 'plan_sha256': queue.file_hash(origin_path),
                            'status_path': original['status_path'],
                            'status_sha256': queue.file_hash(original['status_path'])},
                orchestrator={'code_revision': 'a' * 40,
                              'source': str(Path(queue.__file__).resolve().parent.parent),
                              'source_archive': str(orchestration_archive),
                              'archive_sha256': queue.file_hash(orchestration_archive),
                              'unit_status': str(proof)})
    return plan, original, terminal


def test_retry_preserves_original_completed_output_and_never_launches_qwen(tmp_path, monkeypatch):
    plan, original, terminal = _retry_plan(tmp_path)
    reused = queue.prepare_retry(plan)
    assert reused['reused_from'] == {
        **plan['retry_from'], 'run_id': original['run_id'], 'code_revision': original['code_revision'],
        'result_path': str(Path(original['run_root']) / 'results' / original['stages'][1]['id'])}
    monkeypatch.setattr(queue.subprocess, 'Popen', lambda *args, **kwargs: pytest.fail('no Qwen rerun'))
    # Gemma cannot start because the test intentionally has no model config; Qwen is still reused.
    assert queue.run_queue(plan) == 1
    status = json.loads(Path(plan['status_path']).read_text())
    assert status['stages'][0]['status'] == 'FAILED'
    assert status['stages'][1] == reused
    assert status['orchestrator_revision'] == 'a' * 40
    assert json.loads(Path(original['status_path']).read_text()) == terminal


@pytest.mark.parametrize('field', queue.RETRY_FROZEN_FIELDS)
def test_retry_rejects_every_changed_frozen_inference_input(tmp_path, field):
    plan, original, terminal = _retry_plan(tmp_path)
    plan[field] = None
    with pytest.raises((ValueError, TypeError, KeyError)):
        queue.validate_retry_origin(plan, original, terminal)


@pytest.mark.parametrize('change', ['origin_status', 'origin_plan', 'raw_qwen', 'qwen_environment',
                                   'gemma_output', 'different_failure', 'orchestration_archive',
                                   'orchestration_proof'])
def test_retry_fails_closed_before_gpu_work(tmp_path, monkeypatch, change):
    plan, original, terminal = _retry_plan(tmp_path)
    qwen = Path(original['run_root']) / 'results' / original['stages'][1]['id']
    if change == 'origin_status':
        Path(original['status_path']).write_text('{}')
    elif change == 'origin_plan':
        Path(plan['retry_from']['plan_path']).write_text('{}')
    elif change == 'raw_qwen':
        (qwen / 'responses.jsonl').write_text('tampered')
    elif change == 'qwen_environment':
        (qwen / 'environment.json').write_text('{}')
    elif change == 'gemma_output':
        (qwen.parent / original['stages'][0]['id']).mkdir()
    elif change == 'different_failure':
        Path(terminal['stages'][0]['server_log']).write_text('CUDA out of memory')
    elif change == 'orchestration_archive':
        Path(plan['orchestrator']['source_archive']).write_text('tampered')
    else:
        Path(plan['orchestrator']['unit_status']).write_text('{"exit_code": 1}')
    monkeypatch.setattr(queue.subprocess, 'Popen', lambda *args, **kwargs: pytest.fail('no GPU work'))
    assert queue.run_queue(plan) == 1
    status = json.loads(Path(plan['status_path']).read_text())
    assert all(stage['status'] == 'PENDING' for stage in status['stages'])


@pytest.mark.parametrize('original_change', ['qwen_incomplete', 'gemma_benchmark', 'gemma_other_error',
                                           'wrong_model', 'nonterminal', 'retry_chain'])
def test_retry_origin_only_accepts_exact_prebenchmark_failure(tmp_path, original_change):
    plan, original, terminal = _retry_plan(tmp_path)
    if original_change == 'qwen_incomplete':
        terminal['stages'][1]['missing_count'] = 1
    elif original_change == 'gemma_benchmark':
        terminal['stages'][0]['benchmark_exit_code'] = 1
    elif original_change == 'gemma_other_error':
        terminal['stages'][0]['error']['message'] = 'CUDA out of memory'
    elif original_change == 'wrong_model':
        terminal['stages'][1]['model'] = 'other-model'
    elif original_change == 'nonterminal':
        terminal['phase'] = 'MODEL_REQUESTS'
    else:
        original['retry_from'] = plan['retry_from']
        original['orchestrator'] = plan['orchestrator']
    with pytest.raises(ValueError):
        queue.validate_retry_origin(plan, original, terminal)


@pytest.mark.parametrize('failures,message,expected_starts', [
    (1, MEMORY_RACE, 2), (3, MEMORY_RACE, 3),
    (1, 'CUDA out of memory', 1), (1, 'Engine core initialization failed', 1),
])
def test_only_explicit_startup_memory_races_retry_owned_runtime(
        tmp_path, monkeypatch, failures, message, expected_starts):
    from io import BytesIO
    plan = _plan(tmp_path, schema_version=5)
    plan.update(log_dir=str(tmp_path), source=str(tmp_path))
    stage = plan['stages'][0]
    model = plan['models']['gemma12b']
    starts, stopped, deadlines, updates = [], [], [], []
    class Process:
        def __init__(self, command, **kwargs):
            self.pid = 1000 + len(starts)
            self.returncode = 1 if len(starts) < failures else None
            kwargs['stdout'].write(message.encode())
            kwargs['stdout'].flush()
            starts.append(self)
        def poll(self): return self.returncode
    def resources(*args, **kwargs):
        assert len(stopped) == len(starts), 'failed owned server stopped before reacquiring resources'
        deadlines.append(kwargs['deadline'])
        return 70000
    monkeypatch.setattr(queue.subprocess, 'Popen', Process)
    monkeypatch.setattr(queue, 'stop_owned', lambda process: stopped.append(process.pid))
    monkeypatch.setattr(queue, 'wait_for_resources', resources)
    monkeypatch.setattr(queue, 'urlopen', lambda *args, **kwargs:
                        BytesIO(json.dumps({'data': [{'id': model['served_name']}]}).encode()))
    current = {}
    args = (plan, model, stage, ['owned-server'], {}, current, lambda **v: updates.append(v))
    if failures == 1 and message == MEMORY_RACE:
        server, free, endpoint = queue.start_model_runtime(*args)
        assert server is starts[-1] and free == 70000
        assert current['startup_attempts'][-1]['status'] == 'READY'
    else:
        with pytest.raises(RuntimeError, match='exited during startup'):
            queue.start_model_runtime(*args)
        assert len(stopped) == expected_starts
        assert current['server_exit_code'] == 1
    assert len(starts) == expected_starts
    assert len(set(deadlines)) == 1, 'all resource retries share one bounded deadline'
    logs = [attempt['server_log'] for attempt in current['startup_attempts']]
    assert len(set(logs)) == expected_starts
    assert all(Path(path).read_text() == message for path in logs)


@pytest.mark.parametrize('schema_version', [1, 2, 5, 'retry'])
def test_successful_stages_release_runtime_before_starting_next(tmp_path, monkeypatch, schema_version):
    from io import BytesIO
    from types import SimpleNamespace
    is_retry = schema_version == 'retry'
    if is_retry:
        plan, original, terminal = _retry_plan(tmp_path)
        expected_reused = queue.prepare_retry(plan)
    else:
        plan = _plan(tmp_path, schema_version=schema_version)
        plan.update(source=str(tmp_path), log_dir=str(tmp_path), python='python',
                    model_python='model-python', hf_home=str(tmp_path / 'cache'))
    executed_stages = plan['stages'][:1] if is_retry else plan['stages']
    for model in plan['models'].values():
        Path(model['path']).mkdir()
        (Path(model['path']) / 'config.json').write_text('{}')
    events, live_servers, reports, benchmarks = [], [], [], []
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
                benchmarks.append(command)
                out = Path(command[command.index('--out-dir') + 1])
                out.mkdir(parents=True)
                stage = next(s for s in plan['stages'] if s['id'] == out.name)
                manifest = {'request_corpus_sha256': stage['requests_sha256'],
                    'request_count': stage['request_count'], 'code_revision': plan['code_revision'],
                    'track': stage['track'], 'requested_model': served['name'],
                    'received_count': stage['request_count'], 'malformed_count': 0, 'missing_count': 0, 'error_count': 0}
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
    def report(command, **kwargs):
        reports.append(command)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(queue.subprocess, 'run', report)
    monkeypatch.setattr(queue, 'stop_owned', stop)
    monkeypatch.setattr(queue, 'wait_for_resources', lambda *args, **kwargs: 70000)
    monkeypatch.setattr(queue, 'urlopen', lambda *args, **kwargs:
        BytesIO(json.dumps({'data': [{'id': served['name']}]}).encode()))
    assert queue.run_queue(plan) == 0
    assert not live_servers
    assert events == [(action, stage['model_key']) for stage in executed_stages
                      for action in ('start', 'benchmark', 'stop')]
    status = json.loads(Path(plan['status_path']).read_text())
    assert all(s['status'] == 'COMPLETE' and s['received_count'] == stage['request_count']
               for s, stage in zip(status['stages'], plan['stages']))
    expected_module = {1: 'eval.report_production_grounding', 2: 'eval.report_production_baseline',
                       3: 'eval.report_document_context', 4: 'eval.report_definition_control',
                       5: 'eval.report_hf_qa', 'retry': 'eval.report_hf_qa'}[schema_version]
    assert len(reports) == len(executed_stages) and all(command[2] == expected_module for command in reports)
    if is_retry:
        assert status['stages'][1] == expected_reused
        assert json.loads(Path(original['status_path']).read_text()) == terminal
        assert not (Path(plan['run_root']) / 'results' / plan['stages'][1]['id']).exists()
    for stage, command in zip(executed_stages, benchmarks):
        assert command[command.index('--track') + 1] == stage['track']
        assert command[command.index('--requests-file') + 1] == stage['requests_file']
        assert command[command.index('--max-tokens') + 1] == '128'
        assert command[command.index('--timeout') + 1] == '180'
        assert '--enable-thinking' not in command and '--omit-seed' not in command


@pytest.mark.parametrize('schema_version', [1, 2])
def test_collector_rejects_invalid_plan_before_remote_access(tmp_path, monkeypatch, schema_version):
    from eval import collect_production_queue as collector

    plan = _plan(tmp_path, schema_version=schema_version)
    plan['stages'] = []
    plan_path = tmp_path / 'plan.json'
    plan_path.write_bytes(queue.canonical(plan))

    def unexpected(*args, **kwargs):
        pytest.fail('invalid plan must be rejected before imports, network or publishing')

    monkeypatch.setattr(collector, 'import_module', unexpected)
    monkeypatch.setattr(collector.subprocess, 'check_output', unexpected)
    monkeypatch.setattr(collector.subprocess, 'run', unexpected)
    with pytest.raises(ValueError, match='four predeclared'):
        collector.collect({'repository': str(tmp_path), 'plan_path': str(plan_path)})


@pytest.mark.parametrize('schema_version', [1, 2, 3, 4])
def test_collector_dispatches_same_corpus_model_comparisons_and_scopes_commits(tmp_path, monkeypatch, schema_version):
    import shutil
    from types import SimpleNamespace
    from eval import collect_production_queue as collector

    plan = _plan(tmp_path, schema_version=schema_version)
    if schema_version in (3, 4):
        plan['stages'] = plan['stages'][:2]
        for stage in plan['stages']:
            stage['track'] = 'document_context' if schema_version == 3 else 'definition_control'
        token_proof = tmp_path / 'tokens.json'
        token_proof.write_text('{}')
        plan['token_status'] = str(token_proof)
    plan.update(run_root=str(tmp_path / 'remote'), log_path=str(tmp_path / 'queue.log'))
    plan_path = tmp_path / 'plan.json'
    plan_path.write_bytes(queue.canonical(plan))
    repo = tmp_path / 'repo'
    repo.mkdir()
    unrelated = repo / 'user-work.txt'
    unrelated.write_text('unrelated active work')
    terminal = {'run_id': plan['run_id'], 'code_revision': plan['code_revision'],
        'plan_sha256': hashlib.sha256(queue.canonical(plan)).hexdigest(),
        'status': 'COMPLETE', 'phase': 'FINISHED', 'exit_code': 0,
        'stages': [{'id': stage['id'], 'status': 'COMPLETE', 'received_count': stage['request_count'],
                    'malformed_count': 0, 'exit_code': 0} for stage in plan['stages']]}
    for stage in plan['stages']:
        out = Path(plan['run_root']) / 'results' / stage['id']
        out.mkdir(parents=True)
        manifest = {'request_corpus_sha256': stage['requests_sha256'],
            'request_count': stage['request_count'], 'code_revision': plan['code_revision'],
            'track': stage['track'], 'requested_model': plan['models'][stage['model_key']]['served_name']}
        (out / 'run_manifest.json').write_bytes(queue.canonical(manifest))
        (out / 'summary.json').write_bytes(queue.canonical({'stage': stage['id']}))
        (out / 'RESULTS.md').write_text('frozen report')
    imported, report_calls, commands = [], [], []

    def prepare(run_dir, *, compare=None):
        report_calls.append((Path(run_dir).name, None if compare is None else Path(compare).name))
        return {'stage': Path(run_dir).name}

    def module(name):
        imported.append(name)
        return SimpleNamespace(prepare_report=prepare, render_markdown=lambda summary: 'paired model report')

    def check_output(command, **kwargs):
        if command[0] == 'ssh':
            remote = command[-1]
            if remote.startswith('cat '):
                return json.dumps(terminal)
            if remote.startswith('tail '):
                return 'bounded completed log\n'
            if remote.startswith('python3 -c '):
                stage = next(stage for stage in plan['stages'] if stage['id'] in remote)
                out = Path(plan['run_root']) / 'results' / stage['id']
                return json.dumps([path.name for path in out.iterdir()])
        if command == ['git', 'branch', '--show-current']:
            return 'main\n'
        if command[:2] == ['git', 'rev-parse']:
            return 'revision\n'
        raise AssertionError(command)

    def run(command, **kwargs):
        commands.append(command)
        if command[0] == 'scp':
            source = command[-2].split(':', 1)[1]
            shutil.copyfile(source, command[-1])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(collector, 'import_module', module)
    monkeypatch.setattr(collector.subprocess, 'check_output', check_output)
    monkeypatch.setattr(collector.subprocess, 'run', run)
    config = {'repository': str(repo), 'plan_path': str(plan_path), 'host': 'one-server',
        'status_path': str(tmp_path / 'collector-status.json'), 'report_dir': 'reports/new-queue',
        'workspace': str(tmp_path), 'staging_id': 'owned-staging-id'}
    assert collector.collect(config) == 0
    expected_module = {1: 'eval.report_production_grounding', 2: 'eval.report_production_baseline',
                       3: 'eval.report_document_context', 4: 'eval.report_definition_control'}[schema_version]
    assert imported == [expected_module]
    assert report_calls == [(stage['id'], None) for stage in plan['stages']] + [
        (plan['stages'][i + 1]['id'], plan['stages'][i]['id'])
        for i in range(0, len(plan['stages']), 2)]
    report_root = repo / config['report_dir']
    overview = json.loads((report_root / 'summary.json').read_text())
    markdown = (report_root / 'RESULTS.md').read_text()
    if schema_version == 4:
        assert overview['schema_version'] == 4
        assert (report_root / 'token_preflight.json').exists()
        assert (report_root / 'documents_comparison.md').exists()
        assert 'six matched' in markdown
    elif schema_version == 3:
        assert overview['knowledge_conditions'] == ['none', 'full', 'retrieved', 'ktrf']
        assert overview['source_conditions'] == ['none', 'full', 'retrieved']
        assert (report_root / 'token_preflight.json').exists()
        assert (report_root / 'documents_comparison.md').exists()
        assert 'Full documents are preserved' in markdown
    elif schema_version == 2:
        assert overview['condition'] == 'B' and overview['comparison_condition'] == 'C'
        assert overview['production_inference_rerun'] is False
        assert overview['ktrf_guard_applied_to_baseline'] is False
        assert 'KTRF execution guard is not applied to baseline B' in markdown
        assert 'C GPU inference is not rerun' in markdown
        assert markdown.startswith('# Baseline grounding queue')
    else:
        assert 'condition' not in overview and 'production_inference_rerun' not in overview
        assert markdown.startswith('# Production grounding queue')
        assert 'actual production profiles' in markdown
    commits = [command for command in commands if command[:2] == ['git', 'commit']]
    assert len(commits) == len(plan['stages']) + 1 and all('--only' in command for command in commits)
    assert all(path.startswith(config['report_dir'] + '/') for command in commits
               for path in command[command.index('--') + 1:])
    assert unrelated.read_text() == 'unrelated active work'
    assert len([command for command in commands if command[:2] == ['git', 'fetch']]) == len(plan['stages']) + 1
    assert len([command for command in commands if command[:2] == ['git', 'push']]) == len(plan['stages']) + 1
