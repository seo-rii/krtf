"""Whole-document queues preserve context capacity and earlier experiment ownership."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from eval import prepare_document_context as prepare
from eval import run_production_queue as queue


def _plan(tmp_path):
    rows = [{'system': 'fixed policy', 'user': 'complete document', 'case_id': 'case'}]
    envelope = tmp_path / 'requests.json'
    envelope.write_bytes(queue.canonical({'requests': rows}))
    source = tmp_path / 'source.tar'
    source.write_bytes(b'source')
    unit = tmp_path / 'unit.json'
    unit.write_text(json.dumps({'code_revision': 'revision', 'exit_code': 0}))
    return {'schema_version': 3, 'run_id': 'document-test', 'run_root': str(tmp_path),
        'source_archive': str(source), 'archive_sha256': queue.file_hash(source),
        'code_revision': 'revision', 'unit_status': str(unit),
        'status_path': str(tmp_path / 'status.json'), 'token_status': str(tmp_path / 'tokens.json'),
        'port': 18104, 'models': {name: {'path': str(tmp_path / name), 'gpu_memory_utilization': .5}
                               for name in ('gemma12b', 'qwen27b')},
        'stages': [{'id': 'documents_' + name, 'track': 'document_context', 'model_key': name,
                    'requests_file': str(envelope), 'request_count': len(rows),
                    'envelope_sha256': queue.file_hash(envelope),
                    'requests_sha256': hashlib.sha256(b''.join(queue.canonical(r) for r in rows)).hexdigest()}
                   for name in ('gemma12b', 'qwen27b')]}


def test_document_plan_requires_two_identical_corpus_models_and_token_proof(tmp_path):
    plan = _plan(tmp_path)
    assert queue.validate_plan(plan) is plan
    assert queue.report_module_for_plan(plan) == 'eval.report_document_context'
    for mutation in ('order', 'inputs', 'token_proof'):
        changed = deepcopy(plan)
        if mutation == 'order':
            changed['stages'].reverse()
        elif mutation == 'inputs':
            changed['stages'][1]['requests_sha256'] = 'f' * 64
        else:
            del changed['token_status']
        with pytest.raises(ValueError):
            queue.validate_plan(changed)


@pytest.mark.parametrize('length,exit_code', [(8064, 0), (8065, 1)])
def test_real_template_preflight_rejects_overflow_without_truncation(tmp_path, monkeypatch, length, exit_code):
    plan = _plan(tmp_path)
    calls = []
    class Tokenizer:
        def apply_chat_template(self, messages, **kwargs):
            calls.append((messages, kwargs))
            return [1] * length if kwargs.get("return_dict") is False else {"input_ids": [1] * length, "attention_mask": [1] * length}
    monkeypatch.setitem(sys.modules, 'transformers', SimpleNamespace(
        AutoTokenizer=SimpleNamespace(from_pretrained=lambda path, **kw: Tokenizer())))
    result = prepare.check_tokens(plan)
    assert result['exit_code'] == exit_code
    assert all(model['max_prompt_tokens'] == length for model in result['models'].values())
    assert all(call[0][1]['content'] == 'complete document' for call in calls)
    assert all(call[1] == {'tokenize': True, 'add_generation_prompt': True, 'enable_thinking': False, 'return_dict': False}
               for call in calls)
    if exit_code:
        monkeypatch.setattr(queue, 'wait_for_resources', lambda *a: pytest.fail('no GPU on overflow'))
        assert queue.run_queue(plan) == 1
        state = json.loads(Path(plan['status_path']).read_text())
        assert 'tokenizer preflight' in state['error']['message']
        assert all(stage['status'] == 'PENDING' for stage in state['stages'])


def test_queue_waits_until_entire_predecessor_finishes_without_touching_it(tmp_path, monkeypatch):
    path = tmp_path / 'earlier.json'
    status = {'run_id': 'prior', 'code_revision': 'old', 'phase': 'MODEL_REQUESTS', 'exit_code': None}
    path.write_text(json.dumps(status))
    predecessor = {'run_id': 'prior', 'code_revision': 'old', 'status_path': str(path)}
    updates, sleeps = [], []
    def sleep(seconds):
        sleeps.append(seconds)
        path.write_text(json.dumps({**status, 'phase': 'FINISHED', 'status': 'COMPLETE', 'exit_code': 0}))
    monkeypatch.setattr(queue.time, 'sleep', sleep)
    queue.wait_for_predecessors({'predecessors': [predecessor]}, lambda **v: updates.append(v))
    assert sleeps == [60] and updates[0]['phase'] == 'WAITING_FOR_PREDECESSOR'
    with pytest.raises(ValueError, match='identity'):
        queue.wait_for_predecessors({'predecessors': [{**predecessor, 'run_id': 'replacement'}]}, lambda **v: None)


def test_frozen_document_track_sends_only_prompts_and_regrades_sealed_run(tmp_path, monkeypatch):
    from eval import document_context as engine, run_product_llm as runner
    from eval.report_document_context import prepare_report
    family = json.loads(engine.FIXTURE.read_text().splitlines()[0])
    family['documents'] = family['documents'][:1]
    fixture = tmp_path / 'family.jsonl'
    fixture.write_text(json.dumps(family, ensure_ascii=False) + '\n')
    envelope = engine.build_document_context_envelope(fixture)
    requests_file = tmp_path / 'frozen.json'
    requests_file.write_bytes(queue.canonical(envelope))
    sent = []
    def request_json(url, *, payload=None, timeout):
        if url.endswith('/models'):
            return {'data': [{'id': 'served'}]}
        row = envelope['requests'][len(sent)]
        sent.append(payload)
        assert payload['messages'] == [{'role': 'system', 'content': row['system']},
                                       {'role': 'user', 'content': row['user']}]
        assert set(payload) == {'model', 'messages', 'temperature', 'seed', 'max_tokens', 'chat_template_kwargs'}
        response = ({'answer': None} if row['task'] == 'document_qa' else
                    {'selections': [{'surface': row['target_surface'], 'entity_id': None}]})
        if len(sent) == 1:
            response['unexpected'] = True
        return {'model': 'served', 'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(response)}}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 4, 'total_tokens': 14}}
    monkeypatch.setattr(runner, '_request_json', request_json)
    out = tmp_path / 'run'
    manifest = runner.run_benchmark(endpoint='http://localhost:18104/v1', model='served',
        out_dir=out, code_revision='frozen-revision', track='document_context', requests_file=requests_file)
    assert len(sent) == manifest['received_count'] == 24
    assert manifest['malformed_count'] == 1 and manifest['missing_count'] == 0
    report = prepare_report(out)
    assert report['counts']['conditions'] == 12 and report['counts']['documents'] == 1
    assert report['counts']['malformed_count'] == 1
    with pytest.raises(ValueError, match='frozen'):
        runner.run_benchmark(endpoint='http://localhost/v1', model='served', out_dir=tmp_path/'invalid',
                             code_revision='revision', track='document_context')


@pytest.mark.parametrize('value', [{'input_ids': [1, 2], 'attention_mask': [1, 1]}, [[1, 2]], []])
def test_token_preflight_rejects_mapping_or_batched_token_shapes(tmp_path, monkeypatch, value):
    plan = _plan(tmp_path)
    tokenizer = SimpleNamespace(apply_chat_template=lambda *args, **kwargs: value)
    monkeypatch.setitem(sys.modules, 'transformers', SimpleNamespace(
        AutoTokenizer=SimpleNamespace(from_pretrained=lambda *args, **kwargs: tokenizer)))
    with pytest.raises(ValueError, match='flat list of token IDs'):
        prepare.check_tokens(plan)
    assert not Path(plan['token_status']).exists()
