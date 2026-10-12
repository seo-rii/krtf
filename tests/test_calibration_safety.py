"""Safety invariants from the October review; no output-induced commitment."""
import dataclasses
import math

import pytest

from ktrf.calibration import (InsufficientCalibrationData, TrainingExample,
                              TunedCalibrator, fit_calibrator, partition_examples,
                              derive_training_examples)
from ktrf.candidates import Candidate, CandidatePool
from ktrf.glossary import load_glossary
from ktrf.offsets import OffsetMap
from ktrf.resolver import MentionNode, _mention_response, resolve
from ktrf.snapshot import compile_snapshot
from ktrf.artifacts import finetune
from ktrf.corrections import CorrectionStore


@pytest.fixture
def snap():
    return compile_snapshot(load_glossary('examples/demo_glossary.yaml'))


@pytest.mark.parametrize('mode', ['commit', 'aggressive'])
@pytest.mark.parametrize('channel', ['exact', 'jamo', 'dense', 'abbrev'])
@pytest.mark.parametrize('fitted', [False, True])
def test_output_budget_does_not_change_decision(snap, mode, channel, fitted):
    if fitted:
        snap = dataclasses.replace(snap, calibrator=TunedCalibrator(
            1, 0, .05, {'exact|multi': 1, 'fuzzy|multi': 1, 'dense|multi': 1},
            1, 1, {}, 500))
    pool = CandidatePool(snap.policy.candidate_budget)
    for eid, p in [('A', .8), ('B', .79)]:
        pool.add(Candidate(eid, None, None, generation_channels={channel},
                           is_exact=channel == 'exact', calibrated_probability=p))
    node = MentionNode((0, 2), 'AP', pool, sources={channel})
    results = [_mention_response(node, 0, snap, OffsetMap('AP'), 'AP', mode, n)
               for n in [1, 2, 10]]
    assert {m['link_decision'] for m in results} == {'AMBIGUOUS'}
    assert results[0]['prediction_set']['total_member_count'] == 2
    assert results[0]['prediction_set']['truncated']
    assert not results[0]['prediction_set']['coverage_valid']
    assert results[0]['prediction_set']['decision_margin'] == pytest.approx(.01)


def test_outside_prediction_set_still_competes(snap):
    snap = dataclasses.replace(snap, policy=dataclasses.replace(
        snap.policy, prediction_set_min_p=.795))
    pool = CandidatePool(snap.policy.candidate_budget)
    for eid, p in [('A', .8), ('B', .79)]:
        pool.add(Candidate(eid, None, None, generation_channels={'exact'},
                           is_exact=True, calibrated_probability=p))
    node = MentionNode((0, 2), 'AP', pool)
    m = _mention_response(node, 0, snap, OffsetMap('AP'), 'AP', 'commit', 10)
    assert len(m['prediction_set']['members']) == 1
    assert m['link_decision'] == 'AMBIGUOUS'


def test_parity_labels_cannot_force_reuse():
    rows = [TrainingExample(.9 if y else .4, 'exact|multi', y, event_id=f'e{i}')
            for i in range(10) for y in [1, 0]]
    fit, calibration = partition_examples(rows)
    assert not {e.event_id for e in fit} & {e.event_id for e in calibration}
    cal = fit_calibrator(rows, n_min=1)
    assert not set(cal.partition_manifest['fit_event_ids']) & set(
        cal.partition_manifest['calibration_event_ids'])
    assert cal.group_counts['exact|multi'] == 5
    assert not cal.coverage_valid


def test_shared_sources_join_transitively():
    rows = [TrainingExample(.5, 'exact|multi', 1, event_id='a', document_id='doc'),
            TrainingExample(.6, 'exact|multi', 0, event_id='b', document_id='doc', request_id='r'),
            TrainingExample(.7, 'exact|multi', 1, event_id='c', request_id='r'),
            TrainingExample(.8, 'exact|multi', 0, event_id='d')]
    fit, cal = partition_examples(rows)
    assert {'a', 'b', 'c'} <= {e.event_id for e in fit} or {'a', 'b', 'c'} <= {e.event_id for e in cal}
    assert partition_examples(list(reversed(rows)))[0][0].event_id in {e.event_id for e in fit}


@pytest.mark.parametrize('rows', [
    [TrainingExample(.5, 'exact|multi', i % 2) for i in range(20)],
    [TrainingExample(.5, 'exact|multi', i % 2, event_id='same') for i in range(20)],
    [TrainingExample(.5, 'exact|multi', 1, event_id=f'e{i}') for i in range(20)],
])
def test_insufficient_data_refuses_fit(rows):
    with pytest.raises(InsufficientCalibrationData):
        fit_calibrator(rows)


def test_internal_quantile_uses_identical_unrounded_transform():
    cal = TunedCalibrator(1, 0, .05, {'exact|single': 1 - 1 / (1 + math.exp(-1))},
                          1, 1, {'exact|single': 100}, 1)
    p = cal.calibrate_marginal(1)
    assert p == 1 / (1 + math.exp(-1))
    assert p != round(p, 3)
    assert cal.in_prediction_set(p, 'exact|single') == (True, False)
    assert cal.calibrate_marginal(-1000) == 0
    assert cal.calibrate_marginal(1000) == 1


def test_weights_do_not_manufacture_calibration_samples():
    rows = [TrainingExample(.9 if y else .4, 'exact|multi', y, event_id=f'e{i}')
            for i in range(20) for y in [1, 0]]
    cal = fit_calibrator(rows * 5, n_min=1)
    assert cal.group_counts['exact|multi'] == 10


def test_heuristic_never_advertises_coverage(snap):
    m = next(m for m in resolve(snap, 'AP 확인')['mentions'] if m['surface'] == 'AP')
    ps = m['prediction_set']
    assert ps['calibration_status'] == 'HEURISTIC'
    assert ps['set_confidence'] is None
    assert ps['target_set_confidence'] == .95
    assert not ps['coverage_valid']
    assert ps['coverage_scope'] == 'candidate_conditional'


def test_insufficient_finetune_reports_status_and_keeps_snapshot(snap):
    from ktrf.errors import KtrfApiError
    with pytest.raises(KtrfApiError) as exc:
        finetune(snap, CorrectionStore())
    assert exc.value.details['calibration_status'] == 'INSUFFICIENT_DATA'
    assert snap.calibrator is None


def test_only_accepted_corrections_extract_training():
    assert derive_training_examples({'status': 'SUBMITTED'}) == []


def test_audit_metadata_cannot_certify_correlated_mentions():
    rows = [TrainingExample(.9 if y else .4, 'exact|multi', y,
                            event_id=f'doc{i}-mention{j}', document_id=f'doc{i}',
                            sample_source='random_audit')
            for i in range(40) for j in range(2) for y in [1, 0]]
    cal = fit_calibrator(rows)
    assert cal.sample_source == 'random_audit'
    assert not cal.partition_manifest['independent_calibration_units']
    assert not cal.coverage_valid


def test_explanation_uses_full_decision_margin_with_one_displayed_candidate(snap):
    from ktrf.explain import _blocking_reason
    mention = {'link_decision': 'AMBIGUOUS', 'mention_decision': 'TERM',
               'prediction_set': {'decision_margin': .01, 'total_member_count': 2,
                                  'truncated': True, 'members': [
                                      {'kind': 'ENTITY', 'entity_id': 'A',
                                       'calibrated_probability': .8}]}}
    reason = _blocking_reason(mention, snap.policy)
    assert reason['reason'] == 'insufficient_margin'
    assert reason['margin'] == .01
