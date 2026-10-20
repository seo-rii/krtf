"""Exact occurrence binding and literal evidence checks before fresh GPU runs."""
from copy import deepcopy
import hashlib
import json

import pytest

from eval import routing_confirmation as suite


class FixtureTokenizer:
    def apply_chat_template(self, messages, **kwargs):
        assert kwargs == {'tokenize': True, 'add_generation_prompt': True,
                          'enable_thinking': False, 'return_dict': False}
        return [1] * (sum(len(m['content']) for m in messages) // 3 + 1)


def source_record(*, case='one', text=None, target='휘온', occurrence=0, expected='global:confirm-a'):
    text = text or '휘온의 관할은 대한민국이며 현재 운영 중인 업무 절차로서 내부 직원에게 적용한다. 요청은 취소되지 않았다.'
    start = [i for i in range(len(text)) if text.startswith(target, i)][occurrence]
    digest = hashlib.sha256(text.encode()).hexdigest()
    return {'case_id': case, 'family_id': 'fixture-family', 'document_id': 'doc:' + case,
        'parent_document_id': 'parent:' + case, 'document_sha256': digest,
        'text': text, 'target_surface': target, 'target_core_span': {'start': start, 'end': start + len(target)},
        'target_full_span': {'start': start, 'end': start + len(target)}, 'stratum': 'positive',
        'gold': {'label': 'LINK' if expected else 'NIL', 'entity_ref': expected},
        'expected_entity_id': expected, 'qa': {'requires_terminology': True},
        'rationale': 'SECRET_GOLD_RATIONALE_NEVER_PROMPT',
        'evaluation_split': 'fresh_authored', 'annotation_origin': 'AI_AUTHORED',
        'human_verified': False, 'source_provenance': {'kind': 'synthetic_unit_fixture'},
        'terms': [{'key': 'confirm-a', 'canonical': '휘온 승인절차', 'surfaces': ['휘온'],
            'short_definition': '대한민국에서 현재 운영 중인 업무 절차로 내부 직원에게 적용한다.',
            'applicability': {'ignored_production_metadata': True}}],
        'entity_constraints': {'global:confirm-a': {'jurisdiction': ['대한민국'],
            'temporal_status': ['현재 운영'], 'referent_kind': ['업무 절차'], 'scope': ['내부 직원']}}}


def provenance(records):
    digest = suite.records_sha256(records)
    return {'source_gold_before_resolver': True, 'human_verified': False,
        'records_sha256': digest, 'independent_ai_review': {'reviewer': 'unit-fixture-reviewer',
            'cases_reviewed': len(records), 'resolved_before_resolver': True, 'records_sha256': digest}}


def prepare(records=None, tokenizer=None):
    records = [source_record()] if records is None else records
    models = {k: {'path': 'unit-fixture', 'revision': 'unit'} for k in ('gemma12b', 'qwen27b')}
    return suite.prepare_routing_confirmation(records=records, source_provenance=provenance(records),
        models=models, tokenizers={k: tokenizer or FixtureTokenizer() for k in models},
        code_revision='f' * 40)


@pytest.fixture(scope='module')
def prepared():
    return prepare()


def row_for(prepared, condition):
    return next(r for r in prepared[0]['requests'] if r['condition'] == condition)


def response(row, eid='global:confirm-a'):
    selection = ({'request_ref': row['request_ref']} if row['wire_schema'] == 'compact'
                 else deepcopy(row['selection_binding']))
    selection['entity_id'] = eid
    if row['evidence_gate']:
        if eid is None:
            assertion = {'assessment': 'UNRESOLVED', 'evidence': None, 'attributes': []}
        else:
            text = row['text']
            attributes = []
            for key, values in row['applicability'][eid].items():
                value = values[0]
                start = text.index(value)
                attributes.append({'attribute': key, 'value': value, 'start': start, 'end': start + len(value)})
            assertion = {'assessment': 'SUPPORT', 'evidence': {'text': text, 'start': 0, 'end': len(text)},
                         'attributes': attributes}
        selection['assertion'] = assertion
    return {'selections': [selection]}


def test_complete_conditions_real_candidates_and_input_proof(prepared):
    envelope, proof = prepared
    assert len(envelope['requests']) == proof['request_count'] == 6
    assert proof['authored_families'] == 1
    assert envelope['protocol']['response_schema_scope'] == 'per_request'
    assert {r['condition'] for r in envelope['requests']} == set(suite.CONDITIONS)
    assert all(r['pipeline_trace']['gold_in_candidates'] for r in envelope['requests'])
    assert all(r['reserved_output_tokens'] == 768 for r in envelope['requests'])
    assert all(p['overflow_count'] == 0 for p in proof['models'].values())
    for row in envelope['requests']:
        assert row['text'] in row['user']
        assert 'SECRET_GOLD_RATIONALE_NEVER_PROMPT' not in row['user'] + row['system']
        assert row['source_records_sha256'] == provenance([source_record()])['records_sha256']
        assert suite.confirmation_response_error(response(row), row) is None
        assert suite.grade_confirmation_response(response(row), row)['accepted_correct_id']


def test_only_protocol_changes_between_full_and_compact(prepared):
    for selector in suite.SELECTORS:
        full = row_for(prepared, selector + '_full')
        compact = row_for(prepared, selector + '_compact')
        assert full['prompt_fragment'] == compact['prompt_fragment']
        assert full['selection_binding'] == compact['selection_binding']
        assert full['pack'] == compact['pack']
        assert full['pipeline_trace'] == compact['pipeline_trace']
    checked = row_for(prepared, 'ktrf_check_full')
    evidence = row_for(prepared, 'ktrf_evidence_full')
    assert checked['prompt_fragment'] == evidence['prompt_fragment']
    assert checked['offered_cards'] == evidence['offered_cards']


@pytest.mark.parametrize('mutation,reason', [
    (lambda s: s.update(request_ref='unknown-handle'), 'unknown_or_stale_request_reference'),
    (lambda s: s.update(snapshot_id='invented'), 'exact_wire_selection_fields_required'),
    (lambda s: s.update(document_hash='invented'), 'exact_wire_selection_fields_required'),
    (lambda s: s.update(mention_id='another'), 'exact_wire_selection_fields_required'),
    (lambda s: s.update(entity_id={'entity_id': 'global:confirm-a'}), 'nonnull_entity_id_must_be_string'),
])
def test_compact_rejects_stale_or_untrusted_binding_fields(prepared, mutation, reason):
    row = row_for(prepared, 'ktrf_check_compact')
    answer = response(row)
    mutation(answer['selections'][0])
    result = suite.grade_confirmation_response(answer, row)
    assert not result['guard_valid'] and not result['accepted_correct_id']
    assert reason in {v['kind'] for v in result['guard_violations']}


def test_compact_handle_bound_to_condition_document_snapshot_and_occurrence(prepared):
    row = row_for(prepared, 'ktrf_check_compact')
    answer = response(row)
    answer['selections'][0]['request_ref'] = row_for(prepared, 'ktrf_evidence_compact')['request_ref']
    assert not suite.grade_confirmation_response(answer, row)['wire_valid']
    for field, value in [('snapshot_id', 'new'), ('document_hash', 'new'), ('mention_id', 'other')]:
        changed = deepcopy(row['selection_binding'])
        changed[field] = value
        assert suite._request_ref(changed, row['condition']) != row['request_ref']
    assert suite.grade_confirmation_response(response(row, None), row)['over_abstention']
    abstain = response(row, None)
    abstain['selections'][0]['request_ref'] = 'stale'
    assert not suite.grade_confirmation_response(abstain, row)['guard_valid']


def test_full_wrong_occurrence_keeps_raw_semantics_separate(prepared):
    row = row_for(prepared, 'ktrf_check_full')
    answer = response(row)
    answer['selections'][0]['mention_id'] = 'unresolved-another-occurrence'
    grade = suite.grade_confirmation_response(answer, row)
    assert grade['raw_semantic_match'] and grade['rejected_correct_id']
    assert not grade['accepted_correct_id']
    answer = response(row)
    answer['answer'] = 'must not disappear during projection'
    assert suite.confirmation_response_error(answer, row) == 'selection_envelope_required'
    assert not suite.grade_confirmation_response(answer, row)['guard_valid']


def test_missing_gold_candidate_cannot_be_inserted_or_authorized():
    record = source_record(text='누락표기의 관할은 대한민국이며 현재 운영 중인 업무 절차로서 내부 직원에게 적용한다.',
                           target='누락표기')
    result = prepare([record])
    row = row_for(result, 'ktrf_check_compact')
    assert row['expected_entity_id'] not in row['pipeline_trace']['candidate_entity_ids']
    assert row['expected_entity_id'] not in row['offered_entity_ids']
    grade = suite.grade_confirmation_response(response(row), row)
    assert grade['raw_semantic_match'] and not grade['base_guard_valid']
    assert not grade['accepted_correct_id']


@pytest.mark.parametrize('mutation,reason', [
    (lambda a: a['evidence'].update(text='fabricated evidence'), 'source_quote_mismatch'),
    (lambda a: a['evidence'].update(start=3), 'evidence_does_not_contain_requested_occurrence'),
    (lambda a: a['attributes'][0].update(value='미국'), 'entity_applicability_mismatch'),
    (lambda a: a['attributes'][0].update(start=0, end=4), 'attribute_source_span_mismatch'),
    (lambda a: a.update(attributes=[]), 'complete_applicability_claims_required'),
    (lambda a: a.update(assessment='CONTRADICT'), 'positive_assertion_support_required'),
])
def test_evidence_gate_needs_verified_literal_source_and_applicability(prepared, mutation, reason):
    row = row_for(prepared, 'ktrf_evidence_compact')
    answer = response(row)
    mutation(answer['selections'][0]['assertion'])
    grade = suite.grade_confirmation_response(answer, row)
    assert grade['base_guard_valid'] and not grade['evidence_gate_valid']
    assert grade['raw_semantic_match'] and grade['rejected_correct_id']
    assert reason in {v['kind'] for v in grade['evidence_gate_violations']}


def test_benign_negation_and_positive_quotation_are_not_blanket_vetoes():
    for text in [
        '휘온의 관할은 대한민국이며 현재 운영 중인 업무 절차로서 내부 직원에게 적용한다. 요청은 취소되지 않았다.',
        '담당자는 “휘온은 대한민국에서 현재 운영 중인 업무 절차이며 내부 직원에게 적용된다”고 정확하게 설명했다.',
    ]:
        row = row_for(prepare([source_record(text=text)]), 'ktrf_evidence_full')
        assert suite.grade_confirmation_response(response(row), row)['accepted_correct_id']


def test_directly_negated_claim_is_blocked_without_hiding_raw_semantics():
    text = '휘온의 관할은 대한민국이 아니다. 현재 운영 중인 업무 절차이며 내부 직원에게 적용한다.'
    row = row_for(prepare([source_record(text=text, expected=None)]), 'ktrf_evidence_compact')
    grade = suite.grade_confirmation_response(response(row), row)
    assert grade['base_guard_valid'] and grade['rejected_wrong_id']
    assert {'kind': 'claimed_value_directly_negated', 'attribute': 'jurisdiction'} in grade['evidence_gate_violations']


def test_evidence_cannot_borrow_another_occurrence_or_paragraph():
    text = ('휘온의 관할은 대한민국이며 현재 운영 중인 업무 절차로서 내부 직원에게 적용한다.\n'
            '외부 고객의 휘온은 별개 이름이다.')
    record = source_record(text=text, occurrence=1, expected=None)
    row = row_for(prepare([record]), 'ktrf_evidence_compact')
    answer = response(row)
    grade = suite.grade_confirmation_response(answer, row)
    kinds = {v['kind'] for v in grade['evidence_gate_violations']}
    assert not grade['guard_valid']
    assert 'evidence_crosses_target_paragraph' in kinds
    assert 'evidence_has_other_surface_occurrence' in kinds


def test_long_source_fails_instead_of_clipping():
    class OversizedTokenizer(FixtureTokenizer):
        def apply_chat_template(self, messages, **kwargs):
            return [1] * 8192
    with pytest.raises(ValueError, match='complete source and facts exceed'):
        prepare(tokenizer=OversizedTokenizer())


def test_source_review_must_be_valid_before_any_resolver_access(monkeypatch):
    records = [source_record()]
    seal = provenance(records)
    records[0]['rationale'] = 'changed after review'
    monkeypatch.setattr(suite, 'business_snapshot', lambda *a: pytest.fail('resolver accessed'))
    with pytest.raises(ValueError, match='seal before resolver'):
        suite.prepare_routing_confirmation(records=records, source_provenance=seal,
            tokenizers={'unit': FixtureTokenizer()}, models={'unit': {'path': 'unit'}},
            code_revision='f' * 40)


def test_reordering_records_does_not_change_prompt_order_or_content():
    records = [source_record(case=str(i), text=f'{i}번 기록: 휘온의 관할은 대한민국이며 현재 운영 중인 업무 절차로서 내부 직원에게 적용한다.')
               for i in range(7)]
    first, second = prepare(records)[0]['requests'], prepare(list(reversed(records)))[0]['requests']
    projection = lambda rows: [(r['case_id'], r['condition'], r['system'], r['user']) for r in rows]
    assert projection(first) == projection(second)
    assert [r['condition'] for r in first[::6]][:6] == list(suite.CONDITIONS)


@pytest.mark.parametrize('mutation', [
    lambda r: r.update(user=r['user'] + '\nchanged'),
    lambda r: r.update(request_ref='stale'),
    lambda r: r.update(wire_schema='full' if r['wire_schema'] == 'compact' else 'compact'),
    lambda r: r.update(response_schema={'type': 'object'}),
    lambda r: r['applicability'].update({'global:invented': {}}),
    lambda r: r['pipeline_trace'].update(candidate_entity_ids=['invented']),
    lambda r: r['selection_binding'].update(snapshot_id='changed'),
])
def test_frozen_request_tampering_is_rejected(prepared, mutation):
    rows = deepcopy(prepared[0]['requests'])
    mutation(rows[0])
    with pytest.raises(ValueError):
        suite.validate_confirmation_requests(rows)


def test_grading_is_exactly_reproducible_without_clock_fields(prepared):
    row = row_for(prepared, 'ktrf_evidence_compact')
    assert suite.grade_confirmation_response(response(row), row) == suite.grade_confirmation_response(response(row), row)
    assert not any('time' in k or 'elapsed' in k for k in suite.grade_confirmation_response(response(row), row))


@pytest.mark.parametrize('bad_assertion', [
    None, [], {'assessment': [], 'evidence': None, 'attributes': []},
    {'assessment': 'SUPPORT', 'evidence': {'text': 'x', 'start': True, 'end': 2}, 'attributes': []},
    {'assessment': 'SUPPORT', 'evidence': None, 'attributes': [{'attribute': [], 'value': 'x', 'start': 0, 'end': 1}]},
])
def test_malicious_assertion_shapes_return_errors_instead_of_raising(prepared, bad_assertion):
    row = row_for(prepared, 'ktrf_evidence_compact')
    answer = response(row)
    answer['selections'][0]['assertion'] = bad_assertion
    assert suite.confirmation_response_error(answer, row)
    assert not suite.grade_confirmation_response(answer, row)['guard_valid']


def test_runtime_transmits_per_row_schemas_and_report_regrades_raw_output(prepared, tmp_path, monkeypatch):
    from eval import run_extended_suite as runner
    from eval import report_extended_suite as reporter
    from eval.hf_qa import canonical
    envelope = prepared[0]
    by_prompt = {(r['system'], r['user']): r for r in envelope['requests']}
    calls = []

    def fake_request(endpoint, *, payload=None, timeout):
        if endpoint.endswith('/models'):
            return {'data': [{'id': 'fixture-model'}]}
        row = by_prompt[tuple(m['content'] for m in payload['messages'])]
        assert payload['max_tokens'] == 768
        assert payload['response_format']['json_schema']['strict'] is True
        assert payload['response_format']['json_schema']['schema'] == suite.confirmation_schema(row)
        answer = response(row)
        if row['condition'] == 'ktrf_check_compact':
            answer['selections'][0]['request_ref'] = 'stale'
        if row['condition'] == 'ktrf_evidence_compact':
            answer['selections'][0]['assertion']['evidence']['text'] = 'made up evidence'
        calls.append(row['condition'])
        return {'choices': [{'message': {'content': json.dumps(answer, ensure_ascii=False)}, 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150}}

    monkeypatch.setattr(runner, '_request_json', fake_request)
    requests = tmp_path / 'requests.json'
    requests.write_bytes(canonical(envelope))
    out = tmp_path / 'run'
    manifest = runner.run_benchmark(requests_file=requests, endpoint='http://127.0.0.1:18115/v1',
        model='fixture-model', out_dir=out, code_revision='f' * 40)
    assert calls == [r['condition'] for r in envelope['requests']]
    assert manifest['status'] == 'COMPLETE'
    assert manifest['decoding']['max_tokens'] == 768
    assert manifest['answer_schema'] == {r['condition']: suite.confirmation_schema(r) for r in envelope['requests']}
    verified, rows, records, graded, counts = reporter.read_run(out)
    assert verified == manifest
    assert counts['malformed_count'] == counts['error_count'] == counts['missing_count'] == 0
    assert all(r['execution_validation_ms'] >= 0 for r in records)
    assert graded == runner.grade_outputs(rows, records, envelope['protocol'])
    by_condition = {case['condition']: case for case in graded['cases']}
    assert by_condition['ktrf_check_compact']['semantic_match']
    assert not by_condition['ktrf_check_compact']['wire_valid']
    assert by_condition['ktrf_evidence_compact']['base_guard_valid']
    assert not by_condition['ktrf_evidence_compact']['evidence_gate_valid']
    summary = reporter.prepare_report(out)
    assert summary['by_variant']['plain_check_full']['accepted_correct_id'] == 1
    assert summary['by_variant']['ktrf_evidence_compact']['accepted_correct_id'] == 0
    assert summary['pipeline_diagnostics']['fresh_authored']['positive_gold_in_candidates'] == 1
    assert summary['preparation_timing_ms']['snapshot_compile']['observations'] == 1
    assert summary['preparation_timing_ms']['first_prepare']['observations'] == 1
    # Re-sealing a changed manifest is insufficient to alter the condition schema contract.
    manifest['answer_schema']['ktrf_check_compact'] = suite.confirmation_schema('ktrf_check_full')
    manifest.pop('seal_sha256')
    manifest['seal_sha256'] = hashlib.sha256(canonical(manifest)).hexdigest()
    (out / 'run_manifest.json').write_bytes(canonical(manifest))
    with pytest.raises(ValueError, match='manifest disagree'):
        reporter.read_run(out)
