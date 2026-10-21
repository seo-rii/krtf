"""Source-only evidence bundles preserve every existing execution check."""
from copy import deepcopy
import json

import pytest

from eval import evidence_robustness as suite
from eval.evidence_efficiency_data import load_evidence_efficiency_records
from test_evidence_efficiency import FixtureTokenizer, provenance, source_record


def prepare(records=None, tokenizer=None):
    records = [source_record()] if records is None else records
    source = provenance(records)
    source['evaluation_population'] = suite.POPULATION
    models = {name: {'path': 'unit-fixture', 'revision': 'unit'} for name in ('gemma12b', 'qwen27b')}
    return suite.prepare_evidence_robustness(records=records, models=models,
        tokenizers={name: tokenizer or FixtureTokenizer() for name in models},
        code_revision='f' * 40, source_provenance=source)


@pytest.fixture(scope='module')
def prepared():
    return prepare()


def row_for(prepared, condition):
    return next(r for r in prepared[0]['requests'] if r['condition'] == condition)


def response(row, eid='global:control-a'):
    registry = row['reference_registry']
    alias = next((a for a, entity in registry['entities'].items() if entity == eid), eid)
    selection = {'r': registry['request_ref'], 'e': alias if eid else None,
                 's': 'SUPPORT' if eid else 'UNRESOLVED'}
    bundles = row['bundle_inventory']['bundles']
    bundle_alias = next((a for a, bundle in bundles.items() if bundle['entity_alias'] == alias), None)
    bundle = bundles.get(bundle_alias)
    if suite._bundle_wire(row):
        selection['b'] = bundle_alias if eid else None
    else:
        selection.update(q=bundle['segment_alias'] if eid and bundle else None,
                         a=bundle['attribute_aliases'][:] if eid and bundle else [])
    return {'selections': [selection]}


def normalized(value):
    """Compare semantics across independently bound request handles."""
    if isinstance(value, dict):
        return {normalized(k): normalized(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalized(v) for v in value]
    if isinstance(value, str) and ':' in value and value.split(':', 1)[0].isalnum():
        prefix, suffix = value.split(':', 1)
        if len(prefix) == 12 and all(c in '0123456789abcdef' for c in prefix):
            return suffix
    return value


def test_six_arms_reuse_sources_and_identical_candidate_guard_facts(prepared):
    envelope, proof = prepared
    assert len(envelope['requests']) == proof['request_count'] == 6
    assert proof['evaluation_population'] == suite.POPULATION
    assert proof['source_reused'] and not proof['independent_validation']
    assert envelope['provenance']['source']['evaluation_population'] == suite.POPULATION
    assert 'not a new independent holdout' in ' '.join(proof['limitations'])
    for row in envelope['requests']:
        assert row['source_origin_split'] == row['evaluation_split'] == 'confirmation'
        assert row['evidence_required'] and row['evidence_gate']
        assert row['text'] in row['user']
        assert row['pack'] == envelope['requests'][0]['pack']
        assert row['execution_guard'] == 'common_production_occurrence_v1'
        assert row['offered_cards'] == envelope['requests'][0]['offered_cards']
        assert all(card['definition'] in row['user'] for card in row['offered_cards'])
        assert 'SECRET_GOLD_NOT_VISIBLE' not in row['system'] + row['user']
        assert suite.evidence_robustness_response_error(response(row), row) is None
        grade = suite.grade_evidence_robustness_response(response(row), row)
        assert grade['accepted_correct_id'] and grade['base_guard_valid'] and grade['evidence_gate_valid']


def test_format_pairs_receive_same_full_tables_and_use_identical_gate(prepared):
    for perturbation in ('control', 'reordered', 'distractors'):
        compact = row_for(prepared, 'compact_' + perturbation)
        bundle = row_for(prepared, 'bundle_' + perturbation)
        assert normalized(compact['compact_projection']) == normalized(bundle['compact_projection'])
        compact_grade = suite.grade_evidence_robustness_response(response(compact), compact)
        bundle_grade = suite.grade_evidence_robustness_response(response(bundle), bundle)
        assert compact_grade == bundle_grade
        properties = bundle['response_schema']['properties']['selections']['items']['properties']
        assert set(properties) == {'r', 'e', 's', 'b'}
        assert set(response(compact)['selections'][0]) == {'r', 'e', 's', 'q', 'a'}


def test_reorder_reverses_visible_rows_without_reversing_identity_maps(prepared):
    for wire in ('compact', 'bundle'):
        control, reordered = (row_for(prepared, wire + '_' + p) for p in ('control', 'reordered'))
        before, after = map(lambda r: normalized(r['compact_projection']), (control, reordered))
        for key in ('candidates', 'segments', 'attributes', 'bundles'):
            assert after[key] == before[key][::-1]
        # Each arm has independent request-bound cryptographic IDs, while the
        # alias-to-source-position mapping retains its canonical order.
        assert normalized(control['reference_registry']['entities']) == normalized(reordered['reference_registry']['entities'])
        for key in ('segments', 'attributes'):
            assert normalized(list(control['reference_registry'][key])) == normalized(list(reordered['reference_registry'][key]))
            def literal_entries(row):
                return [{k: v for k, v in entry.items() if k not in {'evidence_id', 'attribute_id'}}
                        for entry in row['evidence_inventory'][key]]
            assert literal_entries(control) == literal_entries(reordered)
        assert control['text'] == reordered['text']


def test_distractors_cannot_become_evidence_or_change_document_binding(prepared):
    row = row_for(prepared, 'bundle_distractors')
    assert len(row['distractors']) == 2
    assert row['selection_binding'] == row_for(prepared, 'compact_control')['selection_binding']
    for excerpt in row['distractors']:
        assert excerpt['authority'] == 'none' and excerpt['target_document'] is False
        assert excerpt['text'] not in row['text']
        assert all(excerpt['text'] not in s['text'] for s in row['evidence_inventory']['segments'])
    forged = response(row)
    forged['selections'][0]['b'] = row['distractors'][0]['excerpt_id']
    grade = suite.grade_evidence_robustness_response(forged, row)
    assert not grade['guard_valid']
    assert 'unknown_or_stale_bundle_reference' in {v['kind'] for v in grade['guard_violations']}


def test_bundle_expands_exact_same_four_literal_claims_as_compact(prepared):
    row = row_for(prepared, 'bundle_control')
    expanded, errors = suite._expand_bundle_response(response(row), row)
    assert not errors
    restored, errors = suite.efficiency._expand_response(expanded, {**row, 'condition': 'evidence_compact'})
    assert not errors
    from eval.evidence_control import _expand_evidence
    literal, errors = _expand_evidence(restored['selections'][0], {**row, 'evidence_transport': 'ids'})
    assert not errors
    assert {a['attribute'] for a in literal['assertion']['attributes']} == set(suite.ATTRIBUTES)
    assert literal['assertion']['evidence']['text'] in row['text']


@pytest.mark.parametrize('condition', suite.CONDITIONS)
def test_direct_negation_is_still_rejected_not_prefiltered_as_truth(condition):
    record = source_record(text='휘온은 대한민국이 아니라 독일의 현재 운영 업무 절차로 내부 직원에게 적용한다.', expected=None)
    row = row_for(prepare([record]), condition)
    assert row['bundle_inventory']['bundles']  # Literal eligibility is not entailment.
    grade = suite.grade_evidence_robustness_response(response(row), row)
    assert grade['proposal_wrong_id'] and grade['base_guard_valid']
    assert not grade['evidence_gate_valid'] and not grade['accepted_wrong_id']


@pytest.mark.parametrize('condition', suite.CONDITIONS)
def test_ambiguous_candidate_proposals_do_not_gain_execution_authority(condition):
    row = row_for(prepare([source_record(collision=True)]), condition)
    grade = suite.grade_evidence_robustness_response(response(row), row)
    assert grade['proposal_correct_id'] and grade['rejected_correct_id']
    assert grade['evidence_gate_valid'] and not grade['base_guard_valid']


def test_bounded_bundle_cartesian_products_disclose_all_omissions():
    record = source_record(text='휘온은 대한민국 대한민국 대한민국의 현재 운영 현재 운영 현재 운영 '
                           '업무 절차 업무 절차 업무 절차로 내부 직원 내부 직원 내부 직원에게 적용한다.')
    prepared = prepare([record])
    row = row_for(prepared, 'bundle_control')
    inventory = row['bundle_inventory']
    assert len(inventory['bundles']) == suite.MAX_BUNDLES_PER_ENTITY_SEGMENT == 8
    assert inventory['combinations'] == [{'entity_alias': next(iter(row['reference_registry']['entities'])),
        'segment_alias': next(iter(row['reference_registry']['segments'])),
        'total_combinations': 81, 'emitted_combinations': 8, 'omitted_combinations': 73}]
    assert inventory['omitted_combinations'] == 73
    assert all(n == 73 for n in prepared[1]['bundle_omitted_combinations_per_condition'].values())


def test_bundle_enumeration_and_noise_use_no_gold_outcomes(prepared):
    row = row_for(prepared, 'bundle_control')
    fields = ('offered_entity_ids', 'applicability', 'evidence_inventory', 'reference_registry', 'target_surface')
    minimal = {k: deepcopy(row[k]) for k in fields}
    assert suite.bundle_inventory(minimal) == row['bundle_inventory']
    expected_noise = suite._distractors(minimal)
    minimal.update(gold={'label': 'NIL'}, expected_entity_id=None, model_response={'e': 'different'})
    assert suite.bundle_inventory(minimal) == row['bundle_inventory']
    assert suite._distractors(minimal) == expected_noise


@pytest.mark.parametrize('condition', suite.CONDITIONS)
def test_no_explicit_attributes_means_no_bundle_and_no_silent_claims(condition):
    row = row_for(prepare([source_record(text='휘온을 확인했다.')]), condition)
    assert row['bundle_inventory']['bundles'] == {}
    grade = suite.grade_evidence_robustness_response(response(row), row)
    assert grade['proposal_correct_id'] and not grade['evidence_gate_valid']
    assert not grade['accepted_correct_id']
    abstention = suite.grade_evidence_robustness_response(response(row, None), row)
    assert abstention['proposal_abstention'] and abstention['over_abstention']


def test_cross_request_bundle_entity_and_request_handles_fail_closed(prepared):
    row = row_for(prepared, 'bundle_control')
    other = row_for(prepared, 'bundle_reordered')
    for key, stale in [('r', other['reference_registry']['request_ref']),
                       ('e', next(iter(other['reference_registry']['entities']))),
                       ('b', next(iter(other['bundle_inventory']['bundles'])))]:
        answer = response(row)
        answer['selections'][0][key] = stale
        grade = suite.grade_evidence_robustness_response(answer, row)
        assert not grade['guard_valid'] and not grade['accepted_correct_id']


def test_bundle_cannot_be_borrowed_for_another_entity():
    record = source_record(collision=True)
    # Both actual candidates have matching literal values. Bundle identity must
    # reject a borrow even when value-only checks would be identical.
    record['entity_constraints']['global:control-b'] = deepcopy(record['entity_constraints']['global:control-a'])
    row = row_for(prepare([record]), 'bundle_control')
    answer = response(row)
    other_alias = next(a for a, e in row['reference_registry']['entities'].items() if e == 'global:control-b')
    answer['selections'][0]['b'] = next(a for a, b in row['bundle_inventory']['bundles'].items()
                                       if b['entity_alias'] == other_alias)
    grade = suite.grade_evidence_robustness_response(answer, row)
    assert not grade['guard_valid']
    assert 'bundle_for_different_entity' in {v['kind'] for v in grade['guard_violations']}


def test_many_bundle_ids_roundtrip_and_two_candidate_reordering_preserve_identity():
    record = source_record(collision=True,
        text='휘온은 대한민국 대한민국 대한민국의 현재 운영 현재 운영 현재 운영 '
             '업무 절차 업무 절차 업무 절차로 내부 직원 내부 직원 내부 직원에게 적용한다.')
    record['entity_constraints']['global:control-b'] = deepcopy(record['entity_constraints']['global:control-a'])
    prepared = prepare([record])
    loaded = json.loads(suite.canonical(prepared[0]))
    suite.validate_evidence_robustness_requests(loaded['requests'])
    control, reordered = (row_for(prepared, 'bundle_' + p) for p in ('control', 'reordered'))
    assert len(control['bundle_inventory']['bundles']) == 16
    assert len(control['compact_projection']['candidates']) == 2
    assert normalized(control['compact_projection']['candidates']) == normalized(reordered['compact_projection']['candidates'][::-1])
    assert normalized(control['compact_projection']['bundles']) == normalized(reordered['compact_projection']['bundles'][::-1])


def test_forged_entity_with_bundle_still_counts_a_rejected_wrong_attempt(prepared):
    row = row_for(prepared, 'bundle_control')
    answer = response(row)
    answer['selections'][0]['e'] = 'forged:entity'
    grade = suite.grade_evidence_robustness_response(answer, row)
    assert grade['attempted_nonnull'] and grade['rejected_wrong_id']
    assert not grade['guard_valid'] and not grade['correct_abstention']


@pytest.mark.parametrize('value', [None, [], {'selections': []}, {'selections': [{}]},
    {'selections': [{'r': 'x', 'e': None, 's': [], 'b': None}]},
    {'selections': [{'r': 'x', 'e': None, 's': 'UNRESOLVED', 'b': []}]}])
def test_malformed_bundle_wire_does_not_raise(prepared, value):
    row = row_for(prepared, 'bundle_control')
    grade = suite.grade_evidence_robustness_response(value, row)
    assert grade['malformed'] and not grade['guard_valid']


@pytest.mark.parametrize('mutate', [
    lambda r: r['bundle_inventory']['bundles'].clear(),
    lambda r: r['bundle_inventory'].update(omitted_combinations=100),
    lambda r: r['compact_projection']['candidates'][0].__setitem__(2, 'truncated'),
    lambda r: r['compact_projection']['attributes'].reverse(),
    lambda r: r['reference_registry']['entities'].update(forged='global:control-a'),
    lambda r: r.update(source_reused=False),
    lambda r: r.update(source_origin_split='development'),
    lambda r: r.update(evaluation_population='FRESH_AI_AUTHORED_CONFIRMATION'),
    lambda r: r.update(execution_guard='relaxed'),
    lambda r: r.update(user=r['user'] + ' changed'),
])
def test_frozen_bundle_fact_order_binding_and_prompt_mutations_fail(prepared, mutate):
    rows = deepcopy(prepared[0]['requests'])
    row = next(r for r in rows if r['condition'] == 'bundle_control')
    mutate(row)
    with pytest.raises(ValueError):
        suite.validate_evidence_robustness_requests(rows)


def test_distractor_artifact_tampering_fails_even_when_target_document_unchanged(prepared):
    rows = deepcopy(prepared[0]['requests'])
    row = next(r for r in rows if r['condition'] == 'bundle_distractors')
    row['distractors'][0]['authority'] = 'approved'
    with pytest.raises(ValueError, match='unrelated excerpts'):
        suite.validate_evidence_robustness_requests(rows)


def test_actual_sealed_source_subset_and_json_roundtrip_preserve_occurrences():
    records = load_evidence_efficiency_records()[:8]
    envelope, proof = prepare(records)
    loaded = json.loads(suite.canonical(envelope))
    assert suite.validate_evidence_robustness_requests(loaded['requests']) == loaded['requests']
    assert len(loaded['requests']) == proof['request_count'] == 48
    sources = {r['case_id']: r for r in records}
    for row in loaded['requests']:
        source = sources[row['case_id']]
        assert row['gold'] == source['gold'] and row['text'] == source['text']
        assert row['source_origin_split'] == source['evaluation_split']
        assert row['offered_entity_ids'] == row['pipeline_trace']['candidate_entity_ids']


def test_population_seal_rejected_before_resolver_access(monkeypatch):
    monkeypatch.setattr(suite.efficiency, 'prepare_evidence_efficiency',
                        lambda **kwargs: pytest.fail('resolver cannot run for mislabeled population'))
    record = source_record()
    with pytest.raises(ValueError, match='reused-source diagnostic'):
        suite.prepare_evidence_robustness(records=[record], models={'m': {}},
            tokenizers={'m': FixtureTokenizer()}, code_revision='f' * 40,
            source_provenance=provenance([record]))


def test_complete_source_overflow_fails_without_truncation():
    class TooLarge(FixtureTokenizer):
        def apply_chat_template(self, *args, **kwargs):
            return [1] * (8192 - 768 + 1)
    with pytest.raises(ValueError, match='complete source'):
        prepare(tokenizer=TooLarge())
