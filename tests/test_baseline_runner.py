"""No-resolver controls retain sealed transport and response contracts."""
import hashlib
import json

import pytest

from eval import run_product_llm as runner


def test_baseline_requires_frozen_input_before_network(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, '_request_json', lambda *a, **kw: pytest.fail('no HTTP before validation'))
    with pytest.raises(ValueError, match='require a frozen'):
        runner.run_benchmark(endpoint='http://localhost/v1', model='served', out_dir=tmp_path / 'run',
                             code_revision='test-code', track='baseline_real')
    assert not (tmp_path / 'run').exists()


def test_baseline_runner_sends_only_prompts_and_grades_complete_response(tmp_path, monkeypatch):
    from eval import production_baseline as baseline
    rows = [{'case_id': 'case:' + task, 'condition': 'plain_glossary', 'task': task,
             'target_surface': 'ABC', 'system': 'schema policy', 'user': 'plain glossary facts',
             'gold': {'private_test_marker': 'must not reach model'}}
            for task in ('document_qa', 'structured_routing')]
    protocol = {'kind': 'production_baseline_real_v1', 'limitations': ['test protocol']}
    provenance = {'reference': 'sealed-production-reference'}
    frozen = tmp_path / 'requests.json'
    frozen.write_text('{}')
    monkeypatch.setattr(baseline, 'load_baseline_request_file',
                        lambda path, *, track: (rows, protocol, provenance))
    observed = []
    def grader(requests, outputs):
        observed.extend(outputs)
        return {'missing_outputs': len(requests) - len(outputs)}
    monkeypatch.setattr(baseline, 'grade_baseline_outputs', grader)
    complete = {'selections': [{'surface': 'ABC', 'entity_id': 'unapproved-id'}],
                'answer': 'must remain present and be rejected, not projected away'}
    replies = iter([{'answer': None}, complete])
    sent = []
    def request(url, *, payload=None, timeout):
        if url.endswith('/models'):
            return {'data': [{'id': 'served'}]}
        sent.append(payload)
        return {'choices': [{'message': {'content': json.dumps(next(replies))}, 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 3, 'total_tokens': 13}}
    monkeypatch.setattr(runner, '_request_json', request)
    out = tmp_path / 'run'
    manifest = runner.run_benchmark(endpoint='http://localhost/v1', model='served', out_dir=out,
        code_revision='test-code', track='baseline_real', requests_file=frozen)
    assert manifest['malformed_count'] == 1 and manifest['received_count'] == 2
    assert manifest['request_provenance'] == provenance
    assert manifest['frozen_request_file_sha256'] == hashlib.sha256(frozen.read_bytes()).hexdigest()
    assert observed[1]['response'] == complete and observed[1]['status'] == 'MALFORMED'
    assert all(payload['messages'] == [{'role': 'system', 'content': row['system']},
                                      {'role': 'user', 'content': row['user']}]
               for payload, row in zip(sent, rows))
    graded = json.loads((out / 'graded.json').read_text())
    assert graded['local_checks']['ktrf_resolver_used'] is False
    assert graded['local_checks']['ktrf_guard_used'] is False
    assert graded['model_results']['limitations'] == ['test protocol']
