"""Source-only reference completion changes transport, never authority."""
from copy import deepcopy
import json

import pytest

from eval import evidence_closure as suite
from eval import support_recovery as support
from tests.test_evidence_efficiency import FixtureTokenizer, provenance, source_record


def prepare(records=None, tokenizer=None, population=suite.POPULATION):
    records = [source_record()] if records is None else records
    source = {**provenance(records), 'evaluation_population': population}
    models = {'gemma12b': {'path': 'fixture', 'revision': 'unit'}}
    return suite.prepare_evidence_closure(records=records, models=models,
        tokenizers={'gemma12b': tokenizer or FixtureTokenizer()}, code_revision='f' * 40,
        source_provenance=source)


def row_for(prepared, condition):
    return next(r for r in prepared[0]['requests'] if r['condition'] == condition)


def response(row, eid='global:control-a', *, manual=True):
    entities = {v: k for k, v in row['reference_registry']['entities'].items()}
    selection = {'r': row['reference_registry']['request_ref'], 'e': entities[eid] if eid else None}
    if row['discriminated_abstention'] and not eid:
        return {'selections': [selection]}
    selection['s'] = 'SUPPORT' if eid else 'UNRESOLVED'
    if row['condition'] == 'closure_bundle':
        bundles = [(b, details) for b, details in row['bundle_inventory']['bundles'].items()
                   if details['entity_alias'] == selection['e']]
        selection['b'] = max(bundles, key=lambda pair: len(pair[1]['attribute_aliases']))[0]
    else:
        attrs = [a for a in row['support_inventory']['attributes']
                 if eid and a['value'] in row['applicability'][eid][a['attribute']]
                 and support._owned_by_target(a, row, eid)]
        selection['a'] = [a['attribute_alias'] for a in attrs][:support.MAX_SELECTED_ATTRIBUTES]
        selection['q'] = list(dict.fromkeys(
            [s['segment_alias'] for s in row['support_inventory']['segments'] if s['contains_target']]
            + [a['segment_alias'] for a in attrs])) if manual and eid else []
    return {'selections': [selection]}


def kinds(grade):
    return {v['kind'] for v in grade['guard_violations']}


@pytest.fixture(scope='module')
def prepared():
    return prepare()


def test_five_arms_keep_actual_source_candidates_and_no_authority(prepared):
    envelope, proof = prepared
    rows = envelope['requests']
    assert len(rows) == proof['request_count'] == 5
    assert proof['evaluation_population'] == suite.POPULATION
    assert envelope['protocol']['execution_authority'] == 'none'
    assert proof['bundle_omitted_combinations_per_condition'] == dict.fromkeys(suite.CONDITIONS, 0)
    fixed = ('text', 'pack', 'selection_binding', 'offered_cards', 'applicability', 'resolve_response')
    for row in rows:
        assert all(row[k] == rows[0][k] for k in fixed)
        assert row['text'] in row['user']
        assert 'SECRET_GOLD_NOT_VISIBLE' not in row['system'] + row['user']
        for card in row['offered_cards']:
            assert card['definition'] in row['user']
        assert suite.evidence_closure_response_error(response(row), row) is None
        grade = suite.grade_evidence_closure_response(response(row), row)
        assert grade['accepted_correct_id'] and grade['shadow_accepted_correct_id']
        assert grade['execution_authority'] == 'none' and grade['evaluation_only']
        assert grade['closed_validation_valid']


def test_canonical_disk_roundtrip_revalidates_every_reference(prepared):
    loaded = json.loads(suite.canonical(prepared[0]))
    assert suite.validate_evidence_closure_requests(loaded['requests']) == loaded['requests']


def test_visible_facts_and_bundle_inventory_never_consult_gold(prepared):
    row = row_for(prepared, 'closure_bundle')
    changed = deepcopy(row)
    changed.update(expected_entity_id=None, positive_gold=False, stratum='forged',
                   gold={'label': 'NIL', 'entity_ref': None}, rationale='DO_NOT_READ_ME')
    assert support.support_inventory(changed) == support.support_inventory(row)
    assert suite.bundle_inventory(changed) == suite.bundle_inventory(row)
    assert suite._prompts(changed) == suite._prompts(row)
    assert suite._request_ref(changed['selection_binding'], changed['condition']) == row['request_ref']


def test_catalog_is_semantically_equal_across_all_wire_arms(prepared):
    def normalized(row):
        segments = {s['segment_alias']: (s['start'], s['end']) for s in row['support_inventory']['segments']}
        attrs = {a['attribute_alias']: (a['attribute'], a['value'], a['start'], a['end'])
                 for a in row['support_inventory']['attributes']}
        return [(row['reference_registry']['entities'][b['entity_alias']],
                 [segments[q] for q in b['segment_aliases']], [attrs[a] for a in b['attribute_aliases']])
                for b in row['bundle_inventory']['bundles'].values()]
    assert all(normalized(r) == normalized(prepared[0]['requests'][0]) for r in prepared[0]['requests'])


def test_target_and_selected_attribute_parent_are_added_without_new_claims():
    record = source_record(text='대한민국 관할의 기록이다.\n내부 직원에게 적용한다.\n처리할 항목은 휘온이다.')
    data = prepare([record])
    manual = row_for(data, 'manual_null')
    closure = row_for(data, 'closure_null')
    raw = response(closure, manual=False)
    before = deepcopy(raw)
    grade = suite.grade_evidence_closure_response(raw, closure)
    assert not grade['raw_validation_valid'] and grade['closed_validation_valid']
    assert grade['accepted_correct_id']
    assert grade['server_added_segment_count'] == 3
    assert grade['reference_closure']['target_segment_count'] == 1
    assert grade['reference_closure']['attribute_parent_segment_count'] == 2
    canonical = grade['canonical_response']['selections'][0]
    assert canonical['a'] == before['selections'][0]['a']
    assert canonical['r'] == before['selections'][0]['r']
    assert canonical['e'] == before['selections'][0]['e']
    assert canonical['s'] == before['selections'][0]['s']
    assert raw == before
    assert not suite.grade_evidence_closure_response(response(manual, manual=False), manual)['guard_valid']


def test_closure_does_not_create_missing_positive_attribute_claim(prepared):
    row = row_for(prepared, 'closure_null')
    payload = response(row, manual=False)
    payload['selections'][0]['a'] = []
    grade = suite.grade_evidence_closure_response(payload, row)
    assert not grade['guard_valid']
    assert 'positive_applicability_support_required' in kinds(grade)
    assert grade['canonical_response']['selections'][0]['a'] == []
    assert set(grade['support_unknown_attributes']) == set(suite.ATTRIBUTES)


@pytest.mark.parametrize('condition', ('manual_null', 'closure_null', 'closure_bundle'))
def test_discriminated_abstention_is_exact_two_field_branch(prepared, condition):
    row = row_for(prepared, condition)
    payload = response(row, None)
    assert suite.evidence_closure_response_error(payload, row) is None
    grade = suite.grade_evidence_closure_response(payload, row)
    assert grade['guard_valid'] and grade['proposal_abstention'] and grade['over_abstention']
    assert grade['canonical_response']['selections'][0]['s'] == 'UNRESOLVED'
    for key, value in (('s', 'UNRESOLVED'), ('q', []), ('a', []), ('b', None)):
        bad = deepcopy(payload)
        bad['selections'][0][key] = value
        assert suite.evidence_closure_response_error(bad, row) == 'discriminated_abstention_fields_required'
        bad_grade = suite.grade_evidence_closure_response(bad, row)
        assert not bad_grade['guard_valid'] and bad_grade['null_wire_error']
        assert not bad_grade['proposal_abstention'] and not bad_grade['over_abstention']


@pytest.mark.parametrize('condition', ('manual_null', 'closure_null', 'closure_bundle'))
def test_nonnull_discriminated_branch_requires_support(prepared, condition):
    row = row_for(prepared, condition)
    payload = response(row)
    payload['selections'][0]['s'] = 'UNRESOLVED'
    assert suite.evidence_closure_response_error(payload, row) == 'positive_assertion_support_required'
    grade = suite.grade_evidence_closure_response(payload, row)
    assert not grade['guard_valid'] and not grade['null_wire_error']
    assert not grade['proposal_correct_id'] and grade['rejected_correct_id']


def test_legacy_closure_preserves_inconsistent_abstention_instead_of_normalizing(prepared):
    row = row_for(prepared, 'closure_legacy')
    payload = response(row, None)
    payload['selections'][0]['s'] = 'SUPPORT'
    payload['selections'][0]['a'] = [row['support_inventory']['attributes'][0]['attribute_alias']]
    closed, metadata = suite.closure_for_support_response(payload, row)
    assert closed == payload and not metadata['applied']
    grade = suite.grade_evidence_closure_response(payload, row)
    assert 'abstention_assertion_inconsistent' in kinds(grade)
    assert grade['null_wire_error']


@pytest.mark.parametrize('field', ('r', 'e', 'q', 'a'))
def test_unknown_or_foreign_references_fail_closed_without_repair(prepared, field):
    row = row_for(prepared, 'closure_null')
    payload = response(row, manual=False)
    payload['selections'][0][field] = ['stale-reference'] if field in {'q', 'a'} else 'stale-reference'
    before = deepcopy(payload)
    closed, metadata = suite.closure_for_support_response(payload, row)
    assert closed == payload == before
    assert metadata['blocked_reason'] and not metadata['server_added_segments']
    assert not suite.grade_evidence_closure_response(payload, row)['guard_valid']


def test_wrong_other_occurrence_evidence_is_never_removed():
    text = ('대한민국의 현재 운영 중인 업무 절차 휘온은 내부 직원에게 적용한다.\n'
            '두 번째 휘온은 외부 고객의 별개 기록이다.')
    row = row_for(prepare([source_record(text=text, occurrence=1, expected=None)]), 'closure_null')
    payload = response(row, manual=False)
    first = row['support_inventory']['segments'][0]
    payload['selections'][0]['q'] = [first['segment_alias']]
    closed, metadata = suite.closure_for_support_response(payload, row)
    assert closed == payload
    assert metadata['blocked_reason'] == 'evidence_owned_by_other_or_unresolved_occurrence'
    grade = suite.grade_evidence_closure_response(payload, row)
    assert not grade['accepted_wrong_id']
    assert first['segment_alias'] in grade['canonical_response']['selections'][0]['q']


def test_other_entity_attribute_cannot_supply_parent_evidence():
    text = '휘온 승인절차의 이름을 적었다.\n휘온 외부절차는 독일에서 폐지했으며 외부 고객이 쓴다.'
    row = row_for(prepare([source_record(text=text, collision=True)]), 'closure_null')
    payload = response(row, manual=False)
    foreign = next(a for a in row['support_inventory']['attributes'] if a['value'] == '독일')
    payload['selections'][0]['a'] = [foreign['attribute_alias']]
    closed, metadata = suite.closure_for_support_response(payload, row)
    assert closed == payload and not metadata['applied']
    assert metadata['blocked_reason'] == 'attribute_owned_by_other_or_unresolved_occurrence'
    assert not suite.grade_evidence_closure_response(payload, row)['guard_valid']


def test_copied_request_and_bundle_handles_fail_in_another_arm(prepared):
    row = row_for(prepared, 'closure_bundle')
    other = row_for(prepared, 'closure_null')
    copied = response(row)
    assert not suite.grade_evidence_closure_response(copied, other)['guard_valid']
    copied['selections'][0]['b'] = 'foreign-bundle'
    assert 'unknown_or_stale_bundle_reference' in kinds(suite.grade_evidence_closure_response(copied, row))


def test_bundle_entity_binding_is_checked_even_when_alias_exists():
    row = row_for(prepare([source_record(collision=True)]), 'closure_bundle')
    payload = response(row)
    payload['selections'][0]['e'] = next(alias for alias, eid in row['reference_registry']['entities'].items()
                                        if eid == 'global:control-b')
    grade = suite.grade_evidence_closure_response(payload, row)
    assert not grade['guard_valid'] and not grade['accepted_wrong_id']
    assert 'bundle_entity_or_binding_mismatch' in kinds(grade)


def test_bundle_binding_digest_cannot_be_replaced(prepared):
    row = deepcopy(row_for(prepared, 'closure_bundle'))
    payload = response(row)
    row['bundle_inventory']['bundles'][payload['selections'][0]['b']]['binding_sha256'] = '0' * 64
    assert 'bundle_entity_or_binding_mismatch' in kinds(suite.grade_evidence_closure_response(payload, row))


def test_foreign_bundle_is_rejected_without_counting_a_valid_proposal(prepared):
    row = row_for(prepared, 'closure_bundle')
    payload = response(row)
    payload['selections'][0]['b'] = 'foreign-bundle'
    grade = suite.grade_evidence_closure_response(payload, row)
    assert grade['attempted_nonnull'] and grade['raw_semantic_match']
    assert grade['rejected_correct_id'] and not grade['rejected_wrong_id']
    assert not grade['wire_valid'] and not grade['semantic_proposal_valid']
    assert not grade['proposal_correct_id'] and not grade['proposal_wrong_id']
    assert not grade['proposal_abstention'] and not grade['bundle_expanded']
    assert not grade['accepted_correct_id'] and not grade['accepted_wrong_id']
    assert not grade['shadow_accepted_correct_id'] and not grade['shadow_accepted_wrong_id']
    assert not grade['production_guard_accepted_correct_id'] and not grade['production_guard_accepted_wrong_id']
    assert not grade['raw_validation_valid'] and not grade['closed_validation_valid']
    assert not grade['null_wire_error']


@pytest.mark.parametrize('field,value', [('r', []), ('e', []), ('s', []), ('q', {}), ('a', [None])])
@pytest.mark.parametrize('condition', ('manual_legacy', 'closure_legacy', 'manual_null', 'closure_null'))
def test_malformed_reference_wire_is_rejected_without_exceptions(prepared, condition, field, value):
    row = row_for(prepared, condition)
    payload = response(row)
    payload['selections'][0][field] = value
    grade = suite.grade_evidence_closure_response(payload, row)
    assert grade['malformed'] and not grade['wire_valid']
    assert not grade['guard_valid'] and not grade['accepted_correct_id'] and not grade['accepted_wrong_id']
    assert not grade['proposal_correct_id'] and not grade['proposal_wrong_id']
    assert not grade['null_wire_error']


def test_bundles_do_not_preapprove_directly_negated_source_values():
    record = source_record(text='휘온은 대한민국이 아닌 독일의 업무 절차이며 내부 직원이 쓴다.', expected=None)
    row = row_for(prepare([record]), 'closure_bundle')
    assert any(a['value'] == '대한민국' for a in row['support_inventory']['attributes'])
    assert row['bundle_inventory']['bundles']
    grade = suite.grade_evidence_closure_response(response(row), row)
    assert not grade['accepted_wrong_id']
    assert 'candidate_applicability_directly_negated' in kinds(grade)


def test_shared_alias_can_recover_only_as_shadow_with_source_support():
    row = row_for(prepare([source_record(collision=True)]), 'closure_null')
    grade = suite.grade_evidence_closure_response(response(row, manual=False), row)
    assert row['resolver_status'] == 'AMBIGUOUS'
    assert grade['accepted_correct_id'] and grade['shadow_accepted_correct_id']
    assert not grade['production_guard_accepted_correct_id']
    assert grade['authorization_mode'] == 'shadow' and grade['execution_authority'] == 'none'


def test_closure_helper_accepts_sealed_support_rows_for_diagnostic_replay():
    record = source_record(text='대한민국의 현재 운영 중인 업무 절차이다.\n내부 직원의 휘온을 처리한다.')
    parent, _ = support.prepare_support_recovery(records=[record], tokenizers={'gemma12b': FixtureTokenizer()},
        models={'gemma12b': {'path': 'fixture', 'revision': 'unit'}}, code_revision='f' * 40,
        source_provenance={**provenance([record]), 'evaluation_population': support.POPULATION},
        conditions=(support.BASELINE, 'multispan_supported_shadow'))
    row = next(r for r in parent['requests'] if r['condition'] == 'multispan_supported_shadow')
    alias = next(alias for alias, eid in row['reference_registry']['entities'].items() if eid == 'global:control-a')
    payload = {'selections': [{'r': row['reference_registry']['request_ref'], 'e': alias, 's': 'SUPPORT', 'q': [],
                             'a': [a['attribute_alias'] for a in row['support_inventory']['attributes']]}]}
    closed, metadata = suite.closure_for_support_response(payload, row)
    assert not support.grade_support_recovery_response(payload, row)['guard_valid']
    assert support.grade_support_recovery_response(closed, row)['guard_valid']
    assert metadata['added_segment_count'] == 2


def test_missing_attributes_stay_unknown_in_bundles():
    row = row_for(prepare([source_record(text='내부 직원이 휘온 승인절차에 접수 번호를 부여했다.')]), 'closure_bundle')
    grade = suite.grade_evidence_closure_response(response(row), row)
    assert grade['accepted_correct_id'] and grade['support_present_attributes'] == ['scope']
    assert set(grade['support_unknown_attributes']) == {'jurisdiction', 'temporal_status', 'referent_kind'}


def test_bundle_enumeration_is_bounded_and_reports_omissions(prepared):
    row = deepcopy(row_for(prepared, 'closure_bundle'))
    attr = row['support_inventory']['attributes'][0]
    row['support_inventory']['attributes'] = [{**deepcopy(attr), 'attribute_alias': 'many-a' + str(i)} for i in range(20)]
    inventory = suite.bundle_inventory(row)
    assert len(inventory['bundles']) == suite.MAX_BUNDLES_PER_ENTITY
    assert inventory['omitted_combinations'] == 5
    assert inventory['combinations'][0]['invalid_source_or_reference_limit_combinations'] == 1


def test_long_band_is_preserved_for_stratified_reporting():
    record = source_record()
    record['document_length_band'] = 'long'
    rows = prepare([record], population=suite.FRESH_POPULATION)[0]['requests']
    assert all(r['document_length_band'] == 'long' and not r['source_reused'] for r in rows)


def test_source_strata_are_preserved_without_becoming_prompt_claims():
    record = source_record()
    strata = {'candidate_referent_kind': 'stratum-kind-only',
              'candidate_country': 'stratum-country-only', 'target_side': 'stratum-side-only'}
    record.update(strata)
    rows = prepare([record])[0]['requests']
    for row in rows:
        assert all(row[field] == value for field, value in strata.items())
        assert all(value not in row['system'] + row['user'] for value in strata.values())
    rows[0]['target_side'] = 'different-stratum'
    with pytest.raises(ValueError, match='paired'):
        suite.validate_evidence_closure_requests(rows)


@pytest.mark.parametrize('mutation', ('authority', 'candidate', 'binding', 'inventory', 'catalog', 'prompt', 'schema', 'matrix'))
def test_sealed_request_tampering_is_rejected(prepared, mutation):
    rows = deepcopy(prepared[0]['requests'])
    row = rows[0]
    if mutation == 'authority':
        row['execution_authority'] = 'production'
    elif mutation == 'candidate':
        row['offered_entity_ids'] = []
    elif mutation == 'binding':
        row['selection_binding']['document_hash'] = '0' * 64
    elif mutation == 'inventory':
        row['support_inventory']['segments'][0]['text'] = 'forged'
    elif mutation == 'catalog':
        row['bundle_inventory']['bundles'].clear()
    elif mutation == 'prompt':
        row['user'] += 'forged'
    elif mutation == 'schema':
        row['response_schema']['additionalProperties'] = True
    else:
        rows.pop()
    with pytest.raises(ValueError):
        suite.validate_evidence_closure_requests(rows)


def test_tokenizer_overflow_is_rejected_without_clipping():
    class OverflowTokenizer:
        def apply_chat_template(self, *args, **kwargs):
            return [1] * suite.MAX_MODEL_LEN
    with pytest.raises(ValueError, match='exceed'):
        prepare(tokenizer=OverflowTokenizer())
