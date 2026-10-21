"""Candidate-matched proposals and identical literal evidence verification."""
from copy import deepcopy
import hashlib

import pytest

from eval import evidence_control as suite
from eval.routing_confirmation_data import load_routing_confirmation_records


class FixtureTokenizer:
    def apply_chat_template(self, messages, **kwargs):
        assert kwargs == {'tokenize': True, 'add_generation_prompt': True,
                          'enable_thinking': False, 'return_dict': False}
        return [1] * (sum(len(m['content']) for m in messages) // 3 + 1)


def source_record(*, case='one', text=None, target='휘온', occurrence=0, expected='global:control-a', collision=False):
    text = text or '휘온의 관할은 대한민국이며 현재 운영 중인 업무 절차로서 내부 직원에게 적용한다. 요청은 취소되지 않았다.'
    start = [i for i in range(len(text)) if text.startswith(target, i)][occurrence]
    digest = hashlib.sha256(text.encode()).hexdigest()
    attrs = {'jurisdiction': ['대한민국'], 'temporal_status': ['현재 운영'],
             'referent_kind': ['업무 절차'], 'scope': ['내부 직원']}
    terms = [{'key': 'control-a', 'canonical': '휘온 승인절차', 'surfaces': ['휘온'],
              'short_definition': '대한민국에서 현재 운영 중인 업무 절차로 내부 직원에게 적용한다.'}]
    constraints = {'global:control-a': attrs}
    if collision:
        terms.append({'key': 'control-b', 'canonical': '휘온 외부절차', 'surfaces': ['휘온'],
                      'short_definition': '독일에서 폐지된 업무 절차로 외부 고객에게 적용했다.'})
        constraints['global:control-b'] = {**attrs, 'jurisdiction': ['독일'],
                                         'temporal_status': ['폐지'], 'scope': ['외부 고객']}
    return {'case_id': case, 'family_id': 'fixture-family', 'document_id': 'doc:' + case,
        'parent_document_id': 'parent:' + case, 'document_sha256': digest,
        'text': text, 'target_surface': target, 'target_core_span': {'start': start, 'end': start + len(target)},
        'target_full_span': {'start': start, 'end': start + len(target)}, 'stratum': 'positive',
        'gold': {'label': 'LINK' if expected else 'NIL', 'entity_ref': expected},
        'expected_entity_id': expected, 'qa': {'requires_terminology': True},
        'rationale': 'SECRET_GOLD_NOT_VISIBLE', 'evaluation_split': 'development',
        'annotation_origin': 'AI_AUTHORED', 'human_verified': False,
        'source_provenance': {'kind': 'synthetic_unit_fixture'}, 'terms': terms,
        'entity_constraints': constraints}


def provenance(records):
    digest = suite.records_sha256(records)
    return {'source_gold_before_resolver': True, 'human_verified': False,
        'records_sha256': digest, 'evaluation_population': suite.POPULATION, 'selected_split': 'development',
        'independent_ai_review': {'reviewer': 'fixture-reviewer', 'cases_reviewed': len(records),
                                'resolved_before_resolver': True, 'records_sha256': digest}}


def prepare(records=None, tokenizer=None):
    records = [source_record()] if records is None else records
    models = {name: {'path': 'unit-fixture', 'revision': 'unit'} for name in ('gemma12b', 'qwen27b')}
    return suite.prepare_evidence_control(records=records, models=models,
        tokenizers={name: tokenizer or FixtureTokenizer() for name in models}, code_revision='f' * 40,
        source_provenance=provenance(records))


@pytest.fixture(scope='module')
def prepared():
    return prepare()


def row_for(prepared, condition):
    return next(r for r in prepared[0]['requests'] if r['condition'] == condition)


def response(row, eid='global:control-a'):
    selection = {'request_ref': row['request_ref'], 'entity_id': eid}
    if row['evidence_gate']:
        evidence = row['evidence_inventory']['segments'][0] if eid is not None else None
        attrs = [next(a for a in row['evidence_inventory']['attributes']
                      if a['attribute'] == name and a['value'] in row['applicability'][eid][name])
                 for name in suite.ATTRIBUTES] if eid is not None else []
        if row['evidence_transport'] == 'ids':
            selection['assertion'] = {'assessment': 'SUPPORT' if eid is not None else 'UNRESOLVED',
                'evidence_id': evidence['evidence_id'] if evidence else None,
                'attribute_ids': [a['attribute_id'] for a in attrs]}
        else:
            selection['assertion'] = {'assessment': 'SUPPORT' if eid is not None else 'UNRESOLVED',
                'evidence': {k: evidence[k] for k in ('text', 'start', 'end')} if evidence else None,
                'attributes': [{k: a[k] for k in ('attribute', 'value', 'start', 'end')} for a in attrs]}
    return {'selections': [selection]}


def test_four_arms_match_candidates_and_approve_valid_exact_occurrence(prepared):
    envelope, proof = prepared
    rows = envelope['requests']
    assert len(rows) == proof['request_count'] == 4
    assert proof['evaluation_population'] == 'EXPOSED_DIAGNOSTIC'
    assert all(r['offered_cards'] == rows[0]['offered_cards'] for r in rows)
    assert all(r['pack'] == rows[0]['pack'] for r in rows)
    assert all(r['reserved_output_tokens'] == 768 for r in rows)
    for row in rows:
        assert row['text'] in row['user']
        assert 'SECRET_GOLD_NOT_VISIBLE' not in row['system'] + row['user']
        assert suite.evidence_control_response_error(response(row), row) is None
        grade = suite.grade_evidence_control_response(response(row), row)
        assert grade['proposal_correct_id'] and grade['accepted_correct_id']
        assert grade['base_guard_valid'] and grade['evidence_gate_valid']


def test_ambiguous_candidates_visible_to_all_but_no_arm_authorizes():
    result = prepare([source_record(collision=True)])
    for row in result[0]['requests']:
        assert set(row['offered_entity_ids']) == {'global:control-a', 'global:control-b'}
        assert row['pipeline_trace']['gold_in_candidates']
        assert row['resolver_status'] == 'AMBIGUOUS'
        grade = suite.grade_evidence_control_response(response(row), row)
        assert grade['proposal_correct_id'] and grade['semantic_proposal_valid']
        assert grade['rejected_correct_id'] and not grade['accepted_correct_id']
        assert not grade['base_guard_valid']


def test_no_oracle_candidate_inserted_when_detection_misses():
    record = source_record(target='미등록', text='미등록은 대한민국의 현재 운영 업무 절차로 내부 직원에게 적용된다.')
    for row in prepare([record])[0]['requests']:
        assert row['offered_entity_ids'] == []
        assert row['evidence_inventory']['attributes'] == []
        if row['evidence_gate']:
            continue
        grade = suite.grade_evidence_control_response(response(row), row)
        assert grade['raw_semantic_match'] and not grade['semantic_proposal_valid']
        assert not grade['proposal_correct_id'] and not grade['accepted_correct_id']


def test_id_and_offset_expand_to_same_literal_assertion(prepared):
    ids = row_for(prepared, 'ktrf_evidence_ids')
    offsets = row_for(prepared, 'ktrf_evidence_offsets')
    expanded, violations = suite._expand_evidence(response(ids)['selections'][0], ids)
    assert not violations
    assert expanded['assertion'] == response(offsets)['selections'][0]['assertion']
    # The source payloads match; references differ because each is request-bound.
    strip_refs = lambda inv: [{k: v for k, v in x.items() if not k.endswith('_id')}
                             for x in inv['segments'] + inv['attributes']]
    assert strip_refs(ids['evidence_inventory']) == strip_refs(offsets['evidence_inventory'])
    assert 'start' not in suite._visible_inventory(ids)['attributes'][0]


def test_wrong_model_offsets_rejected_but_server_ids_succeed(prepared):
    offsets = row_for(prepared, 'ktrf_evidence_offsets')
    answer = response(offsets)
    answer['selections'][0]['assertion']['evidence']['end'] -= 1
    grade = suite.grade_evidence_control_response(answer, offsets)
    assert grade['proposal_correct_id'] and grade['base_guard_valid']
    assert not grade['evidence_gate_valid'] and not grade['accepted_correct_id']
    ids = row_for(prepared, 'ktrf_evidence_ids')
    assert suite.grade_evidence_control_response(response(ids), ids)['accepted_correct_id']


@pytest.mark.parametrize('mutation,kind', [
    (lambda s: s.update(request_ref='stale'), 'unknown_or_stale_request_reference'),
    (lambda s: s.update(document_hash='spoof'), 'exact_wire_selection_fields_required'),
    (lambda s: s['assertion'].update(evidence_id='other-request'), 'unknown_or_stale_evidence_reference'),
    (lambda s: s['assertion']['attribute_ids'].__setitem__(0, 'stale'), 'unknown_or_stale_attribute_reference'),
    (lambda s: s['assertion']['attribute_ids'].__setitem__(1, s['assertion']['attribute_ids'][0]), 'duplicate_attribute_reference'),
])
def test_invalid_or_duplicate_bindings_fail_closed(prepared, mutation, kind):
    row = row_for(prepared, 'ktrf_evidence_ids')
    answer = response(row)
    mutation(answer['selections'][0])
    grade = suite.grade_evidence_control_response(answer, row)
    assert not grade['guard_valid'] and not grade['accepted_correct_id']
    assert kind in {v['kind'] for v in grade['guard_violations']}


def test_cross_request_evidence_reference_rejected(prepared):
    row = row_for(prepared, 'ktrf_evidence_ids')
    other = row_for(prepared, 'ktrf_evidence_offsets')
    answer = response(row)
    answer['selections'][0]['assertion']['evidence_id'] = other['evidence_inventory']['segments'][0]['evidence_id']
    assert not suite.grade_evidence_control_response(answer, row)['evidence_gate_valid']


def test_quoted_attribute_direct_negation_veto_is_identical():
    result = prepare([source_record(text='휘온은 대한민국이 아니라 독일의 현재 운영 업무 절차이며 내부 직원 대상이다.')])
    for condition in ('ktrf_evidence_ids', 'ktrf_evidence_offsets'):
        row = row_for(result, condition)
        grade = suite.grade_evidence_control_response(response(row), row)
        assert grade['base_guard_valid']
        assert not grade['evidence_gate_valid']
        assert 'claimed_value_directly_negated' in {v['kind'] for v in grade['evidence_gate_violations']}


def test_repeated_surface_window_cannot_borrow_other_occurrence_attributes():
    text = '휘온은 대한민국의 현재 운영 업무 절차이며 내부 직원 대상이다. 휘온은 외국 소설 속 동명 산이다.'
    result = prepare([source_record(text=text, occurrence=1, expected=None)])
    row = row_for(result, 'ktrf_evidence_ids')
    evidence = row['evidence_inventory']['segments'][0]
    assert evidence['text'] == '휘온은 외국 소설 속 동명 산이다.'
    assert evidence['start'] == text.rindex('휘온')
    assert row['evidence_inventory']['attributes'] == []
    assert not any(row['evidence_inventory']['candidate_attribute_availability']['global:control-a'].values())
    other = deepcopy(row)
    other['request_ref'] = 'other-request'
    other['target_full_span'] = {'start': 0, 'end': 2}
    other_inventory = suite.evidence_inventory(other)
    answer = response(row, None)
    answer['selections'][0].update(entity_id='global:control-a', assertion={'assessment': 'SUPPORT',
        'evidence_id': other_inventory['segments'][0]['evidence_id'], 'attribute_ids': []})
    assert not suite.grade_evidence_control_response(answer, row)['guard_valid']


def test_same_sentence_duplicate_has_no_safe_catalog_quote():
    text = '휘온과 휘온은 서로 다르며 대한민국의 현재 운영 업무 절차는 내부 직원 대상이다.'
    row = row_for(prepare([source_record(text=text, occurrence=1)]), 'ktrf_evidence_ids')
    assert row['evidence_inventory']['segments'] == []
    assert row['evidence_inventory']['attributes'] == []


def test_newline_window_cannot_borrow_attribute_from_prior_paragraph():
    text = '대한민국의 현재 운영 업무 절차이며 내부 직원 대상이다.\n휘온이라는 외국 소설 속 산을 인용했다.'
    row = row_for(prepare([source_record(text=text, expected=None)]), 'ktrf_evidence_ids')
    assert row['evidence_inventory']['segments'][0]['start'] == text.index('\n') + 1
    assert row['evidence_inventory']['attributes'] == []


def test_inventory_ignores_gold_and_rationale(prepared):
    row = row_for(prepared, 'ktrf_evidence_ids')
    source_only = {k: deepcopy(row[k]) for k in ('text', 'target_full_span', 'target_surface', 'request_ref', 'applicability')}
    assert suite.evidence_inventory(source_only) == row['evidence_inventory']


@pytest.mark.parametrize('mutate', [
    lambda rows: rows[0]['offered_entity_ids'].append('global:oracle'),
    lambda rows: rows[0]['evidence_inventory']['segments'][0].update(start=1),
    lambda rows: rows[0].update(execution_guard='plain_lexical'),
    lambda rows: rows[0].update(evaluation_population='INDEPENDENT_HOLDOUT'),
    lambda rows: rows[0].update(request_ref='stale'),
    lambda rows: rows[0].update(user=rows[0]['user'] + ' changed'),
])
def test_frozen_matrix_mutations_rejected(prepared, mutate):
    rows = deepcopy(prepared[0]['requests'])
    mutate(rows)
    with pytest.raises(ValueError):
        suite.validate_evidence_control_requests(rows)


def test_confirmation_split_rejected_before_resolver():
    record = source_record()
    record['evaluation_split'] = 'confirmation'
    with pytest.raises(ValueError, match='exposed development'):
        prepare([record])


def test_complete_source_overflow_fails_without_truncation():
    class TooLarge(FixtureTokenizer):
        def apply_chat_template(self, *args, **kwargs):
            return [1] * (8192 - 768 + 1)
    with pytest.raises(ValueError, match='complete source'):
        prepare(tokenizer=TooLarge())


def test_predeclared_development_matrix_64_cases_8_families():
    records = load_routing_confirmation_records(split='development')
    envelope, proof = prepare(records)
    assert len(records) == 64 and proof['authored_families'] == 8
    assert len(envelope['requests']) == 256
    assert proof['split_case_counts'] == {'development': 64}
    for row in envelope['requests']:
        assert row['offered_entity_ids'] == row['pipeline_trace']['candidate_entity_ids']
        assert row['text'] in row['user']
        for card in row['offered_cards']:
            assert card['definition'] in row['user']
