"""Posthoc reconstruction must not infer gold, occurrence or execution authority."""
from copy import deepcopy
import inspect

import pytest

from eval import confirmation_diagnostics as diagnosis
from eval.routing_confirmation import grade_confirmation_response
from test_routing_confirmation import prepare, response, row_for, source_record


@pytest.fixture(scope='module')
def row():
    return row_for(prepare(), 'ktrf_evidence_compact')


def damaged(row):
    result = response(row)
    assertion = result['selections'][0]['assertion']
    assertion['evidence'].update(start=1, end=2)
    for claim in assertion['attributes']:
        claim.update(start=1, end=2)
    return result


def reconstruct(result, row):
    return diagnosis.repair_literal_positions(result, text=row['text'],
        target_full_span=row['target_full_span'], target_surface=row['target_surface'])


def test_repair_is_source_only_and_preserves_original_payload(row):
    original = damaged(row)
    before = deepcopy(original)
    repaired, reason = reconstruct(original, row)
    assert reason == 'positions_reconstructed'
    assert original == before
    assert repaired == response(row)
    assert not grade_confirmation_response(original, row)['accepted_correct_id']
    assert grade_confirmation_response(repaired, row)['accepted_correct_id']
    assert set(inspect.signature(diagnosis.repair_literal_positions).parameters) == {
        'response', 'text', 'target_full_span', 'target_surface'}


def test_overlapping_matches_are_not_unique():
    assert diagnosis.literal_positions('aaaa', 'aa') == [0, 1, 2]
    assert diagnosis.literal_positions('aaaa', '') == []


def test_repeated_quote_rejected_even_when_model_offsets_point_to_target(row):
    changed = deepcopy(row)
    quote = row['text']
    changed['text'] += '\n' + quote
    original = response(row)
    assert reconstruct(original, changed) == (None, 'quote_not_unique')


def test_quote_of_other_occurrence_rejected(row):
    changed = deepcopy(row)
    changed['text'] += '\n휘온은 다른 사건에 등장했다.'
    start = changed['text'].rindex('휘온')
    changed['target_full_span'] = {'start': start, 'end': start + len('휘온')}
    assert reconstruct(damaged(row), changed) == (None, 'quote_excludes_requested_occurrence')


def test_unique_quote_with_multiple_target_mentions_rejected(row):
    changed = deepcopy(row)
    changed['text'] += ' 휘온은 반복 표기다.'
    original = damaged(row)
    original['selections'][0]['assertion']['evidence']['text'] = changed['text']
    assert reconstruct(original, changed) == (None, 'quote_has_other_surface_occurrence')


def test_cross_paragraph_quote_rejected(row):
    changed = deepcopy(row)
    changed['text'] += '\n무관한 문단이다.'
    original = damaged(row)
    original['selections'][0]['assertion']['evidence']['text'] = changed['text']
    assert reconstruct(original, changed) == (None, 'quote_crosses_target_paragraph')


@pytest.mark.parametrize(('value', 'reason'), [('없는속성', 'attribute_missing'),
                                               ('휘온', 'attribute_not_unique')])
def test_missing_or_ambiguous_attribute_rejects_atomic_repair(row, value, reason):
    changed = deepcopy(row)
    # A repeated attribute must not be a second target occurrence: use a different literal.
    if reason == 'attribute_not_unique':
        value = '대한민국'
        changed['text'] += ' 관할 대한민국을 재확인했다.'
    original = damaged(row)
    original['selections'][0]['assertion']['evidence']['text'] = changed['text']
    original['selections'][0]['assertion']['attributes'][0]['value'] = value
    before = deepcopy(original)
    assert reconstruct(original, changed) == (None, reason)
    assert original == before


def test_stale_reference_remains_rejected_after_position_repair(row):
    original = damaged(row)
    original['selections'][0]['request_ref'] = 'stale-ref'
    repaired, reason = reconstruct(original, row)
    assert reason == 'positions_reconstructed'
    grade = grade_confirmation_response(repaired, row)
    assert not grade['guard_valid']
    assert {'kind': 'unknown_or_stale_request_reference'} in grade['guard_violations']


def test_entity_and_assessment_cannot_be_repaired(row):
    original = damaged(row)
    original['selections'][0]['entity_id'] = 'global:other'
    original['selections'][0]['assertion']['assessment'] = 'CONTRADICT'
    repaired, reason = reconstruct(original, row)
    assert reason == 'positions_reconstructed'
    assert repaired['selections'][0]['entity_id'] == 'global:other'
    grade = grade_confirmation_response(repaired, row)
    assert not grade['guard_valid']
    assert {'kind': 'positive_assertion_support_required'} in grade['evidence_gate_violations']


def test_literal_direct_negation_still_rejected():
    data = source_record(text='휘온의 관할은 대한민국이 아니며 현재 운영 중인 업무 절차로 내부 직원에게 적용한다.')
    row = row_for(prepare([data]), 'ktrf_evidence_compact')
    repaired, reason = reconstruct(damaged(row), row)
    assert reason == 'positions_reconstructed'
    grade = grade_confirmation_response(repaired, row)
    assert not grade['evidence_gate_valid']
    assert {'kind': 'claimed_value_directly_negated', 'attribute': 'jurisdiction'} in grade['evidence_gate_violations']


def test_all_four_attributes_remain_required(row):
    original = damaged(row)
    original['selections'][0]['assertion']['attributes'].pop()
    assert reconstruct(original, row) == (None, 'incomplete_attribute_claims')


def test_read_run_is_mandatory_and_failure_propagates(monkeypatch, tmp_path):
    calls = []
    def invalid(path):
        calls.append(path)
        raise ValueError('invalid extended manifest seal')
    monkeypatch.setattr(diagnosis, 'read_run', invalid)
    with pytest.raises(ValueError, match='invalid extended manifest seal'):
        diagnosis.analyze_run(tmp_path)
    assert calls == [tmp_path]


def test_pipeline_distinguishes_retrieved_from_offered_and_guard(row):
    hidden = deepcopy(row)
    hidden.update(case_id='hidden', resolver_status='AMBIGUOUS', offered_entity_ids=[])
    rejected = deepcopy(row)
    rejected.update(case_id='rejected', resolver_status='AMBIGUOUS')
    original = response(rejected)
    original['selections'][0]['request_ref'] = 'wrong'
    accepted = deepcopy(row)
    accepted['case_id'] = 'accepted'
    records = [
        {'case_id': hidden['case_id'], 'condition': hidden['condition'], 'status': 'RECEIVED',
         'response': response(hidden, eid=None)},
        {'case_id': rejected['case_id'], 'condition': rejected['condition'], 'status': 'RECEIVED',
         'response': original},
        {'case_id': accepted['case_id'], 'condition': accepted['condition'], 'status': 'RECEIVED',
         'response': response(accepted)},
    ]
    result = diagnosis._pipeline([hidden, rejected, accepted],
        {(r['case_id'], r['condition']): r for r in records})
    assert result['stages']['gold_retrieved'] == 3
    assert result['stages']['gold_offered'] == 2
    assert result['stages']['model_correct_id'] == 2
    assert result['stages']['approved_correct_id'] == 1
    assert result['exclusive_first_loss'] == {'retrieved_gold_not_offered': 1,
        'offered_correct_id_rejected': 1, 'approved_correct_id': 1}
    assert result['not_offered_resolver_status'] == {'AMBIGUOUS': 1}


def test_evidence_report_keeps_original_scores_and_reconstructs_copy(row):
    original = damaged(row)
    record = {'case_id': row['case_id'], 'condition': row['condition'], 'status': 'RECEIVED',
              'response': original}
    before = deepcopy(record)
    result = diagnosis._evidence([row], {(row['case_id'], row['condition']): record})
    assert result['original_scores_unchanged']['accepted_correct_id'] == 0
    assert result['posthoc_reconstructed_nonnull_only']['accepted_correct_id'] == 1
    assert result['scope'] == diagnosis.STATUS
    assert record == before
