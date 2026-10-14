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
    return {'schema_version': schema_version, 'stages': stages, 'port': 18104,
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
        queue.report_module_for_plan({'schema_version': 5})


@pytest.mark.parametrize('schema_version', [1, 2])
def test_request_envelope_is_sealed_before_runtime_work(tmp_path, schema_version):
    plan = _plan(tmp_path, schema_version=schema_version)
    stage = plan['stages'][0]
    assert len(queue.validate_requests(stage)['requests']) == stage['request_count']
    Path(stage['requests_file']).write_text('{}')
    with pytest.raises(ValueError, match='envelope changed'):
        queue.validate_requests(stage)


@pytest.mark.parametrize('schema_version', [1, 2])
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


@pytest.mark.parametrize('schema_version', [1, 2])
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


@pytest.mark.parametrize('schema_version', [1, 2])
def test_successful_stages_release_runtime_before_starting_next(tmp_path, monkeypatch, schema_version):
    from io import BytesIO
    from types import SimpleNamespace
    plan = _plan(tmp_path, schema_version=schema_version)
    plan.update(source=str(tmp_path), log_dir=str(tmp_path), python='python',
                model_python='model-python', hf_home=str(tmp_path / 'cache'))
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
    monkeypatch.setattr(queue, 'wait_for_resources', lambda *args: 70000)
    monkeypatch.setattr(queue, 'urlopen', lambda *args, **kwargs:
        BytesIO(json.dumps({'data': [{'id': served['name']}]}).encode()))
    assert queue.run_queue(plan) == 0
    assert not live_servers
    assert events == [(action, model) for model in ('gemma12b', 'qwen27b', 'gemma12b', 'qwen27b')
                      for action in ('start', 'benchmark', 'stop')]
    status = json.loads(Path(plan['status_path']).read_text())
    assert all(s['status'] == 'COMPLETE' and s['received_count'] == stage['request_count']
               for s, stage in zip(status['stages'], plan['stages']))
    expected_module = {1: 'eval.report_production_grounding', 2: 'eval.report_production_baseline',
                       3: 'eval.report_document_context', 4: 'eval.report_definition_control'}[schema_version]
    assert len(reports) == 4 and all(command[2] == expected_module for command in reports)
    for stage, command in zip(plan['stages'], benchmarks):
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
