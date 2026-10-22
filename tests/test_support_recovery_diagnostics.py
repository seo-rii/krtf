from copy import deepcopy

import pytest

from eval.support_recovery_diagnostics import analyze_rows
from eval.evidence_robustness import grade_evidence_robustness_response
from test_evidence_robustness import prepare, row_for, response
from test_evidence_efficiency import source_record


def diagnostic(record, *, answer=None):
    row = row_for(prepare([record]), 'bundle_control')
    grade = grade_evidence_robustness_response(answer or response(row), row)
    case = {'case_id': row['case_id'], 'condition': 'bundle_control', **grade}
    return analyze_rows([row], [case])


def test_oracle_ceiling_retains_existing_production_guard():
    d = diagnostic(source_record(collision=True))
    assert d['gold_in_actual_candidates'] == 1
    assert d['production_guard_oracle_correct_ceiling'] == 0
    assert d['four_attribute_gate_oracle_correct_ceiling'] == 0
    assert d['positive_primary_bottlenecks'] == {'production_occurrence_guard_blocked': 1}
    assert not d['operational_proposals_emitted']


def test_missing_attribute_is_a_validator_capacity_failure_not_model_failure():
    d = diagnostic(source_record(text='휘온은 내부 직원 업무 절차다.'))
    assert d['production_guard_oracle_correct_ceiling'] == 1
    assert d['four_attribute_gate_oracle_correct_ceiling'] == 0
    assert d['positive_primary_bottlenecks'] == {'no_complete_same_paragraph_four_attribute_bundle': 1}
    assert d['positive_attribute_literal_absence_in_target_paragraph']['jurisdiction'] == 1


def test_valid_oracle_identifies_model_null_below_ceiling():
    prepared = prepare([source_record()])
    row = row_for(prepared, 'bundle_control')
    answer = response(row, eid=None)
    d = diagnostic(source_record(), answer=answer)
    assert d['four_attribute_gate_oracle_correct_ceiling'] == 1
    assert d['additional_correct_approvals_possible_without_validator_changes'] == 1
    assert d['positive_primary_bottlenecks'] == {'model_or_wire_failure_below_validator_ceiling': 1}


def test_oracle_will_not_report_inconsistent_observed_approval():
    row = row_for(prepare([source_record(collision=True)]), 'bundle_control')
    with pytest.raises(ValueError, match='exceeds'):
        analyze_rows([row], [{'case_id': row['case_id'], 'condition': 'bundle_control',
                             'accepted_correct_id': True}])
