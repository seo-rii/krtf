"""Lossless compact facts, source-only routing and immutable wire references."""
from copy import deepcopy
import hashlib
import json

import pytest

from eval import evidence_efficiency as suite
from eval.evidence_control import _prompts as previous_prompts


class FixtureTokenizer:
    def apply_chat_template(self, messages, **kwargs):
        assert kwargs == {'tokenize': True, 'add_generation_prompt': True,
                          'enable_thinking': False, 'return_dict': False}
        return [1] * (sum(len(m['content']) for m in messages) // 3 + 1)


def source_record(*, case='one', text=None, target='휘온', occurrence=0,
                  expected='global:control-a', collision=False, split='confirmation'):
    text = text or '휘온의 관할은 대한민국이며 현재 운영 중인 업무 절차로서 내부 직원에게 적용한다.'
    start = [i for i in range(len(text)) if text.startswith(target, i)][occurrence]
    attrs = {'jurisdiction': ['대한민국'], 'temporal_status': ['현재 운영'],
             'referent_kind': ['업무 절차'], 'scope': ['내부 직원']}
    terms = [{'key': 'control-a', 'canonical': '휘온 승인절차', 'surfaces': ['휘온'],
              'short_definition': '대한민국에서 현재 운영 중인 업무 절차로 내부 직원에게 적용한다. 외부 고객에게 적용하지 않으며 실행 권한을 뜻하지 않는다.'}]
    constraints = {'global:control-a': attrs}
    if collision:
        terms.append({'key': 'control-b', 'canonical': '휘온 외부절차', 'surfaces': ['휘온'],
                      'short_definition': '독일에서 폐지된 업무 절차로 외부 고객에게 적용했다.'})
        constraints['global:control-b'] = {**attrs, 'jurisdiction': ['독일'],
                                         'temporal_status': ['폐지'], 'scope': ['외부 고객']}
    return {'case_id': case, 'family_id': 'fixture-family', 'document_id': 'doc:' + case,
        'parent_document_id': 'parent:' + case, 'document_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'text': text, 'target_surface': target, 'target_core_span': {'start': start, 'end': start + len(target)},
        'target_full_span': {'start': start, 'end': start + len(target)}, 'stratum': 'fixture',
        'gold': {'label': 'LINK' if expected else 'NIL', 'entity_ref': expected},
        'expected_entity_id': expected, 'qa': {'requires_terminology': True},
        'rationale': 'SECRET_GOLD_NOT_VISIBLE', 'evaluation_split': split,
        'annotation_origin': 'AI_AUTHORED', 'human_verified': False,
        'source_provenance': {'kind': 'synthetic_unit_fixture'}, 'terms': terms,
        'entity_constraints': constraints}


def provenance(records):
    digest = suite.records_sha256(records)
    return {'source_gold_before_resolver': True, 'human_verified': False,
        'records_sha256': digest, 'evaluation_population': suite.POPULATION,
        'independent_ai_review': {'reviewer': 'fixture-reviewer', 'cases_reviewed': len(records),
                                'resolved_before_resolver': True, 'records_sha256': digest}}


def prepare(records=None, tokenizer=None):
    records = [source_record()] if records is None else records
    models = {name: {'path': 'unit-fixture', 'revision': 'unit'} for name in ('gemma12b', 'qwen27b')}
    return suite.prepare_evidence_efficiency(records=records, models=models,
        tokenizers={name: tokenizer or FixtureTokenizer() for name in models}, code_revision='f' * 40,
        source_provenance=provenance(records))


@pytest.fixture(scope='module')
def prepared():
    return prepare()


def row_for(prepared, condition):
    return next(r for r in prepared[0]['requests'] if r['condition'] == condition)


def response(row, eid='global:control-a'):
    short = suite._short_wire(row)
    registry = row['reference_registry']
    reverse = lambda key: {v: k for k, v in registry[key].items()}
    selection = ({'r': registry['request_ref'], 'e': reverse('entities').get(eid, eid) if eid else None}
                 if short else {'request_ref': row['request_ref'], 'entity_id': eid})
    if row['evidence_required']:
        evidence = row['evidence_inventory']['segments'][0] if eid else None
        attrs = [next(a for a in row['evidence_inventory']['attributes']
                      if a['attribute'] == name and a['value'] in row['applicability'][eid][name])
                 for name in suite.ATTRIBUTES] if eid else []
        assessment = 'SUPPORT' if eid else 'UNRESOLVED'
        if short:
            selection.update(s=assessment, q=reverse('segments')[evidence['evidence_id']] if evidence else None,
                             a=[reverse('attributes')[a['attribute_id']] for a in attrs])
        else:
            selection['assertion'] = {'assessment': assessment,
                'evidence_id': evidence['evidence_id'] if evidence else None,
                'attribute_ids': [a['attribute_id'] for a in attrs]}
    return {'selections': [selection]}


def test_five_arms_preserve_candidates_source_definitions_and_common_guard(prepared):
    envelope, proof = prepared
    rows = envelope['requests']
    assert len(rows) == proof['request_count'] == 5
    assert proof['split_case_counts'] == {'confirmation': 1}
    assert proof['evaluation_population'] == suite.POPULATION
    for row in rows:
        assert row['offered_cards'] == rows[0]['offered_cards']
        assert row['pack'] == rows[0]['pack']
        assert row['reserved_output_tokens'] == 768
        assert row['text'] in row['user']
        for card in row['offered_cards']:
            assert card['definition'] in row['user']
        assert 'SECRET_GOLD_NOT_VISIBLE' not in row['system'] + row['user']
        assert suite.evidence_efficiency_response_error(response(row), row) is None
        grade = suite.grade_evidence_efficiency_response(response(row), row)
        assert grade['proposal_correct_id'] and grade['accepted_correct_id']
        assert grade['base_guard_valid'] and grade['evidence_gate_valid']


def test_long_arm_reuses_previous_exact_prompt_and_schema(prepared):
    row = row_for(prepared, 'evidence_long')
    proxy = {**row, 'condition': 'ktrf_evidence_ids'}
    assert previous_prompts(proxy) == (row['system'], row['user'], row['prompt_fragment'])
    assert len(row['request_ref']) > 64
    assert row['response_schema'] == suite.evidence_control_schema('ktrf_evidence_ids')


def test_canonical_envelope_disk_roundtrip_revalidates_every_prompt(prepared):
    loaded = json.loads(suite.canonical(prepared[0]))
    assert suite.validate_evidence_efficiency_requests(loaded['requests']) == loaded['requests']


def test_short_handles_and_field_names_expand_to_identical_literal_assertion(prepared):
    for condition in ('evidence_short', 'evidence_compact'):
        row = row_for(prepared, condition)
        expanded, violations = suite._expand_response(response(row), row)
        assert violations == []
        assert expanded['selections'][0]['entity_id'] == 'global:control-a'
        assert all(len(x) < 20 for x in row['reference_registry']['attributes'])
        from eval.evidence_control import _expand_evidence
        literal, errors = _expand_evidence(expanded['selections'][0], row)
        assert not errors
        assert literal['assertion']['evidence']['text'] in row['text']
        assert {a['attribute'] for a in literal['assertion']['attributes']} == set(suite.ATTRIBUTES)


def test_compact_projection_round_trip_and_exception_preservation(prepared):
    row = row_for(prepared, 'evidence_compact')
    facts, inventory = suite.expand_compact_projection(row['compact_projection'])
    assert facts == suite._short_facts(row)
    assert inventory == suite._short_inventory(row)
    assert '외부 고객에게 적용하지 않으며 실행 권한을 뜻하지 않는다.' in facts[0]['definition']
    assert len(row['user']) < len(row_for(prepared, 'evidence_short')['user'])


def test_selective_easy_schema_omits_experimental_evidence_but_uses_same_guard(prepared):
    row = row_for(prepared, 'selective_compact')
    assert row['difficulty_gate']['easy']
    assert not row['evidence_required'] and not row['evidence_gate']
    assert set(response(row)['selections'][0]) == {'r', 'e'}
    assert suite.grade_evidence_efficiency_response(response(row), row)['base_guard_valid']


def test_annotation_full_span_stays_nominal_while_actual_guard_binding_keeps_particle(prepared):
    for row in prepared[0]['requests']:
        assert row['target_full_span'] == {'start': 0, 'end': 2}
        assert row['selection_binding']['full_span'] == {'start': 0, 'end': 3}
        assert row['binding_span_origin'] == 'actual_resolver_occurrence'
        assert row['text'][0:3] == '휘온의'


def test_no_gold_candidate_is_inserted_when_actual_detection_misses():
    record = source_record(text='미등록은 대한민국의 현재 운영 업무 절차로 내부 직원에게 적용한다.', target='미등록')
    for row in prepare([record])[0]['requests']:
        assert row['offered_entity_ids'] == []
        assert not row['pipeline_trace']['gold_in_candidates']
        assert row['binding_span_origin'] == 'requested_annotation_without_detection'
        grade = suite.grade_evidence_efficiency_response(response(row, None), row)
        assert not grade['accepted_correct_id']


def test_nil_abstention_and_unknown_entity_attempt_are_distinct():
    record = source_record(text='휘온은 독일의 과거 동명 산이다.', expected=None)
    for row in prepare([record])[0]['requests']:
        grade = suite.grade_evidence_efficiency_response(response(row, None), row)
        assert grade['correct_abstention'] and not grade['attempted_nonnull']
        if suite._short_wire(row):
            answer = response(row, None)
            answer['selections'][0]['e'] = 'unknown-request:e0'
            grade = suite.grade_evidence_efficiency_response(answer, row)
            assert grade['attempted_nonnull'] and not grade['raw_semantic_match']
            assert not grade['correct_abstention'] and not grade['guard_valid']


@pytest.mark.parametrize('text,occurrence,collision,reason', [
    ('휘온은 독일의 현재 운영 업무 절차로 내부 직원에게 적용한다.', 0, False,
     'no_unique_explicit_four_attribute_support'),
    ('휘온은 대한민국이 아니라 독일의 현재 운영 업무 절차로 내부 직원에게 적용한다.', 0, False,
     'quotation_negation_or_context_conflict_cue'),
    ('"휘온은 대한민국의 현재 운영 업무 절차로 내부 직원에게 적용한다"고 인용했다.', 0, False,
     'quotation_negation_or_context_conflict_cue'),
    ('휘온은 대한민국의 현재 운영 업무 절차로 내부 직원에게 적용한다. 휘온은 다른 산이다.', 1, False,
     'repeated_or_unmatched_surface'),
    ('휘온은 대한민국의 현재 운영 업무 절차로 내부 직원에게 적용한다.', 0, True,
     'candidate_count_not_one'),
])
def test_context_conflicts_and_ambiguity_always_take_checked_path(text, occurrence, collision, reason):
    row = row_for(prepare([source_record(text=text, occurrence=occurrence, collision=collision)]), 'selective_compact')
    assert not row['difficulty_gate']['easy'] and row['evidence_required']
    assert reason in row['difficulty_gate']['reasons']
    assert set(suite.evidence_efficiency_schema(row)['properties']['selections']['items']['required']) == {'r', 'e', 's', 'q', 'a'}


def test_country_conflict_can_be_resolved_yet_never_called_easy():
    row = row_for(prepare([source_record(text='휘온은 독일의 현재 운영 업무 절차로 내부 직원에게 적용한다.', expected=None)]), 'selective_compact')
    assert row['resolver_status'] == 'RESOLVED'
    assert row['evidence_required']


def test_route_and_registry_need_no_gold_or_output_fields(prepared):
    row = row_for(prepared, 'evidence_compact')
    keys = ('text', 'target_surface', 'target_full_span', 'offered_entity_ids',
            'resolver_status', 'evidence_inventory', 'applicability')
    source_only = {k: deepcopy(row[k]) for k in keys}
    assert suite.source_only_route(source_only) == row['source_only_route']
    source_only.update(gold={'label': 'NIL'}, expected_entity_id=None,
                       rationale='force hard', model_response={'entity_id': None})
    assert suite.source_only_route(source_only) == row['source_only_route']


def test_ambiguous_candidates_exposed_but_guard_never_promotes():
    for row in prepare([source_record(collision=True)])[0]['requests']:
        assert set(row['offered_entity_ids']) == {'global:control-a', 'global:control-b'}
        grade = suite.grade_evidence_efficiency_response(response(row), row)
        assert grade['proposal_correct_id'] and grade['rejected_correct_id']
        assert not grade['accepted_correct_id'] and not grade['base_guard_valid']


@pytest.mark.parametrize('mutation,kind', [
    (lambda s: s.update(r='stale'), 'unknown_or_stale_request_reference'),
    (lambda s: s.update(e='stale'), 'unknown_or_stale_entity_reference'),
    (lambda s: s.update(q='stale'), 'unknown_or_stale_evidence_reference'),
    (lambda s: s['a'].__setitem__(0, 'stale'), 'unknown_or_stale_attribute_reference'),
    (lambda s: s['a'].__setitem__(1, s['a'][0]), 'duplicate_attribute_reference'),
    (lambda s: s.update(document_hash='spoof'), 'exact_wire_selection_fields_required'),
])
def test_short_stale_unknown_duplicate_or_client_binding_fails_closed(prepared, mutation, kind):
    row = row_for(prepared, 'evidence_compact')
    answer = response(row)
    mutation(answer['selections'][0])
    grade = suite.grade_evidence_efficiency_response(answer, row)
    assert not grade['guard_valid'] and not grade['accepted_correct_id']
    assert kind in {v['kind'] for v in grade['guard_violations']}


def test_cross_request_short_evidence_and_entity_handles_rejected(prepared):
    row = row_for(prepared, 'evidence_compact')
    other = row_for(prepared, 'evidence_short')
    for key, field in (('attributes', 'a'), ('segments', 'q'), ('entities', 'e')):
        answer = response(row)
        value = next(iter(other['reference_registry'][key]))
        answer['selections'][0][field] = [value] if field == 'a' else value
        assert not suite.grade_evidence_efficiency_response(answer, row)['guard_valid']


@pytest.mark.parametrize('value', [None, [], {'selections': []}, {'selections': [{}]},
    {'selections': [{'r': 'x', 'e': None, 's': [], 'q': None, 'a': []}]}])
def test_malformed_response_does_not_raise(prepared, value):
    row = row_for(prepared, 'evidence_compact')
    assert not suite.grade_evidence_efficiency_response(value, row)['guard_valid']


@pytest.mark.parametrize('mutate', [
    lambda rows: rows[0]['offered_entity_ids'].append('global:oracle'),
    lambda rows: rows[0]['compact_projection']['candidates'][0].__setitem__(2, 'truncated'),
    lambda rows: rows[0]['reference_registry']['entities'].update(stale='global:control-a'),
    lambda rows: rows[0]['difficulty_gate'].update(easy=False),
    lambda rows: rows[0].update(evidence_required=not rows[0]['evidence_required']),
    lambda rows: rows[0].update(execution_guard='relaxed'),
    lambda rows: rows[0].update(user=rows[0]['user'] + ' changed'),
])
def test_frozen_fact_gate_prompt_and_binding_mutations_rejected(prepared, mutate):
    rows = deepcopy(prepared[0]['requests'])
    mutate(rows)
    with pytest.raises(ValueError):
        suite.validate_evidence_efficiency_requests(rows)


def test_unreviewed_or_exposed_population_rejected_before_any_resolver(monkeypatch):
    monkeypatch.setattr(suite, 'business_snapshot', lambda *a, **kw: pytest.fail('resolver accessed before review'))
    record = source_record()
    p = provenance([record])
    p['evaluation_population'] = 'EXPOSED_DIAGNOSTIC'
    with pytest.raises(ValueError, match='fresh presealed'):
        suite.prepare_evidence_efficiency(records=[record], models={'m': {}}, tokenizers={'m': FixtureTokenizer()},
            code_revision='f' * 40, source_provenance=p)
    p = provenance([record]); p['independent_ai_review']['resolved_before_resolver'] = False
    with pytest.raises(ValueError, match='independent AI review'):
        suite.prepare_evidence_efficiency(records=[record], models={'m': {}}, tokenizers={'m': FixtureTokenizer()},
            code_revision='f' * 40, source_provenance=p)


def test_complete_source_overflow_fails_without_truncation():
    class TooLarge(FixtureTokenizer):
        def apply_chat_template(self, *args, **kwargs):
            return [1] * (8192 - 768 + 1)
    with pytest.raises(ValueError, match='complete source'):
        prepare(tokenizer=TooLarge())
