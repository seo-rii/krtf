"""Source ownership and evaluation-only support recovery contracts."""
from copy import deepcopy
import json

import pytest

from eval import support_recovery as suite
from tests.test_evidence_efficiency import FixtureTokenizer, provenance, source_record


def prepare(records=None, conditions=suite.CONDITIONS, population=suite.POPULATION):
    records = records or [source_record()]
    source = provenance(records)
    source['evaluation_population'] = population
    models = {'gemma12b': {'path': 'fixture', 'revision': 'unit'}}
    return suite.prepare_support_recovery(records=records, tokenizers={'gemma12b': FixtureTokenizer()},
        models=models, code_revision='f' * 40, source_provenance=source, conditions=conditions)


def row_for(prepared, condition):
    return next(r for r in prepared[0]['requests'] if r['condition'] == condition)


def response(row, eid='global:control-a', *, all_matching=True):
    entities = {v: k for k, v in row['reference_registry']['entities'].items()}
    selection = {'r': row['reference_registry']['request_ref'], 'e': entities[eid] if eid else None,
                 's': 'SUPPORT' if eid else 'UNRESOLVED', 'q': [], 'a': []}
    if eid:
        inventory = row['support_inventory']
        target_segments = [s for s in inventory['segments'] if s['contains_target']]
        claims = [a for a in inventory['attributes']
                  if a['value'] in row['applicability'][eid][a['attribute']]
                  and suite._owned_by_target(a, row, eid)] if all_matching else []
        selection['a'] = [a['attribute_alias'] for a in claims][:suite.MAX_SELECTED_ATTRIBUTES]
        selection['q'] = list(dict.fromkeys([s['segment_alias'] for s in target_segments]
                          + [a['segment_alias'] for a in claims]))[:suite.MAX_SELECTED_SEGMENTS]
    return {'selections': [selection]}


def kinds(grade):
    return {v['kind'] for v in grade['guard_violations']}


@pytest.fixture(scope='module')
def prepared():
    return prepare()


def test_eight_arms_preserve_actual_candidates_and_full_source(prepared):
    envelope, proof = prepared
    assert len(envelope['requests']) == proof['request_count'] == 8
    assert envelope['protocol']['execution_authority'] == 'none'
    fixed = ('text', 'pack', 'selection_binding', 'offered_cards', 'applicability', 'resolve_response')
    for row in envelope['requests']:
        assert all(row[k] == envelope['requests'][0][k] for k in fixed)
        assert row['text'] in row['user']
        assert 'SECRET_GOLD_NOT_VISIBLE' not in row['system'] + row['user']
        for card in row['offered_cards']:
            assert card['definition'] in row['user']
        grade = suite.grade_support_recovery_response(response(row), row)
        assert grade['accepted_correct_id']
        assert grade['production_base_guard_valid']
        assert grade['evaluation_only'] and grade['execution_authority'] == 'none'
        assert not grade['support_unknown_attributes']


def test_canonical_disk_roundtrip_is_exact(prepared):
    rows = json.loads(suite.canonical(prepared[0]))['requests']
    assert suite.validate_support_recovery_requests(rows) == rows


def test_inventory_and_visible_prompt_do_not_read_gold_or_diagnostic_labels(prepared):
    row = row_for(prepared, 'multispan_supported_shadow')
    changed = deepcopy(row)
    changed.update(expected_entity_id=None, positive_gold=False, stratum='forged-stratum',
                   gold={'label': 'NIL', 'entity_ref': None}, rationale='DO_NOT_READ_ME')
    assert suite.support_inventory(changed) == suite.support_inventory(row)
    assert suite._prompts(changed) == suite._prompts(row)
    assert suite.reference_registry(changed) == suite.reference_registry(row)


def test_confirmation_is_exact_baseline_plus_one_selected_method():
    conditions = (suite.BASELINE, 'multispan_supported_shadow')
    envelope, proof = prepare(conditions=conditions, population=suite.FRESH_POPULATION)
    assert tuple(proof['conditions']) == conditions
    assert envelope['protocol']['evaluation_population'] == suite.FRESH_POPULATION
    for invalid in ((suite.BASELINE,), ('multispan_all_production', 'multispan_supported_shadow'),
                    (suite.BASELINE, suite.BASELINE), (suite.BASELINE, 'bad')):
        with pytest.raises(ValueError):
            prepare(conditions=invalid)


def test_cross_paragraph_evidence_recovers_only_when_multispan_enabled():
    record = source_record(text='관할: 대한민국\n운용 단계: 현재 운영\n구분: 업무 절차, 범위: 내부 직원\n처리할 항목은 휘온이다.')
    prepared = prepare([record])
    baseline = row_for(prepared, suite.BASELINE)
    multi = row_for(prepared, 'multispan_all_production')
    assert not suite.grade_support_recovery_response(response(baseline), baseline)['accepted_correct_id']
    grade = suite.grade_support_recovery_response(response(multi), multi)
    assert grade['accepted_correct_id'] and grade['production_base_guard_valid']
    assert len(response(multi)['selections'][0]['q']) > 1


def test_missing_values_remain_unknown_instead_of_becoming_true():
    record = source_record(text='내부 직원은 휘온 승인절차에 신청 번호를 부여했다.')
    prepared = prepare([record])
    all_row = row_for(prepared, 'multispan_all_shadow')
    observed = row_for(prepared, 'multispan_observed_shadow')
    supported = row_for(prepared, 'multispan_supported_shadow')
    assert 'complete_applicability_claims_required' in kinds(suite.grade_support_recovery_response(response(all_row), all_row))
    for row in (observed, supported):
        grade = suite.grade_support_recovery_response(response(row), row)
        assert grade['accepted_correct_id']
        assert grade['support_present_attributes'] == ['scope']
        assert set(grade['support_unknown_attributes']) == {'jurisdiction', 'temporal_status', 'referent_kind'}


def test_observed_allows_unknown_but_supported_requires_positive_attribute():
    prepared = prepare([source_record(text='휘온 승인절차의 접수 번호를 수정했다.')])
    observed = row_for(prepared, 'multispan_observed_shadow')
    supported = row_for(prepared, 'multispan_supported_shadow')
    assert suite.grade_support_recovery_response(response(observed), observed)['accepted_correct_id']
    assert 'positive_applicability_support_required' in kinds(suite.grade_support_recovery_response(response(supported), supported))


@pytest.mark.parametrize('condition', suite.CONDITIONS)
def test_explicit_country_conflict_blocks_even_a_valid_actual_candidate(condition):
    prepared = prepare([source_record(text='독일의 휘온 승인절차를 내부 직원이 쓴다.', expected=None)])
    row = row_for(prepared, condition)
    grade = suite.grade_support_recovery_response(response(row), row)
    assert not grade['accepted_wrong_id']
    assert 'explicit_jurisdiction_conflict' in kinds(grade)


def test_other_entity_attribute_cannot_be_borrowed():
    record = source_record(text='휘온 승인절차의 접수 번호를 고쳤다.\n휘온 외부절차는 독일에서 폐지했으며 외부 고객이 쓴다.', collision=True)
    prepared = prepare([record])
    row = row_for(prepared, 'multispan_observed_shadow')
    payload = response(row)
    foreign = next(a for a in row['support_inventory']['attributes'] if a['value'] == '독일')
    payload['selections'][0]['a'].append(foreign['attribute_alias'])
    payload['selections'][0]['q'].append(foreign['segment_alias'])
    grade = suite.grade_support_recovery_response(payload, row)
    assert not grade['accepted_correct_id']
    assert 'attribute_owned_by_other_or_unresolved_occurrence' in kinds(grade)


def test_repeated_surface_earlier_attributes_do_not_authorize_later_occurrence():
    text = '대한민국의 현재 운영 중인 업무 절차 휘온은 내부 직원에게 적용한다.\n두 번째 휘온은 독립 관측소의 명령이다.'
    record = source_record(text=text, occurrence=1, expected=None)
    row = row_for(prepare([record]), 'multispan_observed_shadow')
    payload = response(row)
    first = next(s for s in row['support_inventory']['segments'] if not s['contains_target'])
    payload['selections'][0]['q'].append(first['segment_alias'])
    payload['selections'][0]['a'] = [a['attribute_alias'] for a in row['support_inventory']['attributes']]
    grade = suite.grade_support_recovery_response(payload, row)
    assert not grade['accepted_wrong_id']
    assert 'evidence_owned_by_other_or_unresolved_occurrence' in kinds(grade)


def test_context_resolved_collision_is_shadow_only():
    record = source_record(collision=True)
    prepared = prepare([record])
    production = row_for(prepared, 'multispan_supported_production')
    shadow = row_for(prepared, 'multispan_supported_shadow')
    gp = suite.grade_support_recovery_response(response(production), production)
    gs = suite.grade_support_recovery_response(response(shadow), shadow)
    assert production['resolver_status'] == 'AMBIGUOUS'
    assert not gp['accepted_correct_id'] and not gp['production_base_guard_valid']
    assert gs['accepted_correct_id'] and gs['shadow_accepted_correct_id']
    assert not gs['production_guard_accepted_correct_id']
    assert gs['execution_authority'] == 'none'


def test_truly_ambiguous_collision_remains_unresolved():
    record = source_record(text='휘온이라는 이름만 남아 어느 부서의 것인지 정할 수 없다.', collision=True, expected=None)
    row = row_for(prepare([record]), 'multispan_observed_shadow')
    grade = suite.grade_support_recovery_response(response(row), row)
    assert not grade['accepted_wrong_id']
    assert 'unresolved_candidate_collision' in kinds(grade)


@pytest.mark.parametrize('text', ['휘온은 예제 문자열이며 비밀번호다.', '휘온은 2008년에 폐지한 옛 제도다.'])
def test_nonmention_or_historical_identity_cannot_pass_observed(text):
    row = row_for(prepare([source_record(text=text, expected=None)]), 'multispan_observed_shadow')
    assert not suite.grade_support_recovery_response(response(row), row)['accepted_wrong_id']


def test_omitting_directly_negated_attribute_cannot_hide_contradiction():
    row = row_for(prepare([source_record(text='휘온은 대한민국이 아닌 독일의 업무이며 내부 직원에게 적용한다.', expected=None)]),
                  'multispan_observed_shadow')
    payload = response(row, all_matching=False)
    grade = suite.grade_support_recovery_response(payload, row)
    assert not grade['accepted_wrong_id']
    assert 'candidate_applicability_directly_negated' in kinds(grade)


@pytest.mark.parametrize('suffix, expected_identity', [('담당자', 'DISTINCT_FROM_CORE'), ('ICT', 'UNKNOWN')])
def test_actual_full_surface_role_and_unknown_identity_are_blocked(suffix, expected_identity):
    record = source_record(text='휘온' + suffix + '의 이름을 내부 직원 명부에서 확인했다.',
                           target='휘온' + suffix, expected=None)
    record['target_core_span']['end'] = record['target_core_span']['start'] + 2
    row = row_for(prepare([record]), 'multispan_observed_shadow')
    found = next(m for m in row['resolve_response']['mentions'] if m['span']['codepoint'] == row['target_core_span'])
    assert found['full_surface']['identity'] == expected_identity
    assert row['binding_span_origin'] == 'actual_resolver_occurrence'
    grade = suite.grade_support_recovery_response(response(row), row)
    assert not grade['accepted_wrong_id']
    assert 'full_surface_structural_identity_not_same' in kinds(grade)


def test_foreign_request_handles_and_client_offsets_are_rejected(prepared):
    row = row_for(prepared, 'multispan_all_shadow')
    other = row_for(prepared, 'multispan_all_production')
    assert not suite.grade_support_recovery_response(response(other), row)['wire_valid']
    for key in ('r', 'e'):
        payload = response(row)
        payload['selections'][0][key] = 'forged-reference'
        assert not suite.grade_support_recovery_response(payload, row)['guard_valid']
    for key in ('q', 'a'):
        payload = response(row)
        payload['selections'][0][key] = ['forged-reference']
        assert not suite.grade_support_recovery_response(payload, row)['guard_valid']
    payload = response(row)
    payload['selections'][0]['span'] = {'start': 0, 'end': 1}
    assert suite.support_recovery_response_error(payload, row) == 'exact_wire_selection_fields_required'


def test_other_document_evidence_cannot_be_replayed(prepared):
    own = row_for(prepared, 'multispan_all_shadow')
    foreign = row_for(prepare([source_record(case='foreign', text='내부 직원이 대한민국의 현재 운영 중인 업무 절차 휘온을 쓴다.')]),
                      'multispan_all_shadow')
    payload = response(own)
    borrowed = response(foreign)['selections'][0]
    payload['selections'][0].update(q=borrowed['q'], a=borrowed['a'])
    grade = suite.grade_support_recovery_response(payload, own)
    assert not grade['guard_valid']
    assert 'unknown_or_stale_evidence_reference' in kinds(grade)


@pytest.mark.parametrize('mutate', [
    lambda r: r['support_inventory']['attributes'][0].update(start=999),
    lambda r: r['selection_binding'].update(snapshot_id='forged'),
    lambda r: r['selection_binding'].update(mention_id='other-occurrence'),
    lambda r: r.update(execution_authority='production'),
    lambda r: r.update(evaluation_only=False),
    lambda r: r.update(binding_span_origin='requested_annotation_without_detection'),
    lambda r: r.update(execution_guard='unrestricted'),
    lambda r: r.update(source_reused=False),
    lambda r: r.update(source_origin_split='wrong'),
    lambda r: r.update(original_evaluation_split='wrong'),
    lambda r: r['offered_cards'][0].update(definition='truncated'),
])
def test_frozen_request_tampering_is_rejected(prepared, mutate):
    rows = deepcopy(prepared[0]['requests'])
    mutate(rows[0])
    with pytest.raises(ValueError):
        suite.validate_support_recovery_requests(rows)


@pytest.mark.parametrize('value', [None, [], 'bad', {'selections': []},
    {'selections': [{'r': 'r', 'e': None, 's': [], 'q': [], 'a': []}]},
    {'selections': [{'r': 'r', 'e': None, 's': 'UNRESOLVED', 'q': None, 'a': []}]}])
def test_malformed_responses_never_throw(prepared, value):
    row = row_for(prepared, suite.BASELINE)
    grade = suite.grade_support_recovery_response(value, row)
    assert grade['malformed'] and not grade['guard_valid']


def test_consistent_abstention_valid_across_all_conditions(prepared):
    for row in prepared[0]['requests']:
        payload = response(row, eid=None)
        assert suite.support_recovery_response_error(payload, row) is None
        grade = suite.grade_support_recovery_response(payload, row)
        assert grade['proposal_abstention'] and grade['over_abstention']
        assert grade['guard_valid']
