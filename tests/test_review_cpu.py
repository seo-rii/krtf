"""Review CPU audits preserve source clusters, actual retrieval and old seals."""
from copy import deepcopy
import hashlib
import json
import tarfile

import pytest

from eval import review_cpu as audit


class ScalarScorer:
    reranker_id = 'test-scalar'

    def __init__(self):
        self.pairs = []

    def score_pairs(self, pairs):
        self.pairs.extend(pairs)
        return [8.0 if '먼저' in profile else 1.0 for _, profile in pairs]


def _terms():
    return [dict(key='first', canonical='먼저 기관', surfaces=['나래'], short_definition='첫 조직'),
            dict(key='second', canonical='나중 기관', surfaces=['나래'], short_definition='둘째 조직')]


def _case(*, name='doc', gold='global:first', text='나래는 업무를 진행했다.'):
    return {'case_id': name + '::target', 'document_id': name, 'family_id': 'family',
            'cohort': 'development', 'text': text, 'catalog_terms': _terms(),
            'document_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'core_span': [0, 2], 'full_surface_span': [0, 2],
            'semantic_label': 'LINK' if gold else 'NIL', 'expected_entity_id': gold}


def _mention(*, core=(0, 2), ids=('global:first', 'global:second')):
    return {'span': {'codepoint': {'start': core[0], 'end': core[1]}},
            # This token extent includes a particle; nominal extent does not.
            'full_span': {'codepoint': {'start': core[0], 'end': core[1] + 1}},
            'link_decision': 'AMBIGUOUS', 'eval_trace': {'pool': {},
                'ranked': [dict(entity_id=eid, commit_blocked=None) for eid in ids]}}


def test_bootstrap_resamples_complete_correlated_families_not_mentions():
    rows = [dict(family='one', document='one-' + str(i), left=0, right=1) for i in range(100)]
    rows.append(dict(family='two', document='two', left=1, right=0))
    result = audit.paired_cluster_bootstrap(rows, replicates=500, seed=9)
    assert result['clusters'] == 2 and result['observations'] == 101
    assert result['estimate_right_minus_left'] == pytest.approx(99 / 101)
    assert result['percentile_interval_95'] == [-1, 1]
    assert audit.paired_cluster_bootstrap(list(reversed(rows)), replicates=500, seed=9) == result
    # A single family is not enough to report an inferential interval.
    assert audit.paired_cluster_bootstrap(rows[:-1])['percentile_interval_95'] is None


def test_actual_retrieval_missing_gold_is_never_filled_from_catalog(monkeypatch):
    calls = []
    monkeypatch.setattr(audit, '_snapshot', lambda terms, family: object())
    def resolver(snapshot, text, **kwargs):
        calls.append((text, kwargs))
        return {'mentions': [_mention(ids=('global:second',))]}
    monkeypatch.setattr(audit, 'resolve', resolver)
    scorer = ScalarScorer()
    result = audit.evaluate_actual_candidates([_case()], scorer, bootstrap_replicates=10)
    assert len(calls) == result['resolver_calls'] == 1
    assert 'core_span' not in calls[0][1] and 'gold' not in calls[0][1]
    assert scorer.pairs and all('나중 기관' in profile for _, profile in scorer.pairs)
    assert all('먼저 기관' not in profile for _, profile in scorer.pairs)
    for values in result['cohorts']['development']['by_variant'].values():
        assert values['candidate_recall'] == 0
        assert values['gold_in_unbudgeted_candidates'] == 0
        assert values['conditional_ranking_accuracy'] is None
        assert values['mean_candidate_count'] == 1
    assert not result['gold_forced_candidates'] and not result['production_authorized']


def test_undetected_and_wrong_core_boundaries_do_not_get_gold_seeded_pairs(monkeypatch):
    monkeypatch.setattr(audit, '_snapshot', lambda terms, family: object())
    monkeypatch.setattr(audit, 'resolve', lambda snapshot, text, **kwargs: {
        'mentions': [] if text.startswith('나래') else [_mention(core=(0, 3))]})
    missing = _case()
    wrong = _case(name='wrong', text='나다래는 업무를 진행했다.')
    scorer = ScalarScorer()
    result = audit.evaluate_actual_candidates([missing, wrong], scorer, bootstrap_replicates=10)
    assert scorer.pairs == []
    for values in result['cohorts']['development']['by_variant'].values():
        assert values['missed_mentions'] == values['core_boundary_mismatches'] == 1
        assert values['mean_candidate_count'] == 0
        assert values['over_abstentions'] == 2


def test_two_targets_share_single_resolve_call_and_gold_cannot_change_inputs(monkeypatch):
    calls = []
    monkeypatch.setattr(audit, '_snapshot', lambda terms, family: object())
    def resolver(snapshot, text, **kwargs):
        calls.append(text)
        return {'mentions': [_mention()]}
    monkeypatch.setattr(audit, 'resolve', resolver)
    first = _case()
    second = dict(first, case_id='doc::other-target', expected_entity_id='global:second')
    scorer = ScalarScorer()
    original = audit.evaluate_actual_candidates([first, second], scorer, bootstrap_replicates=10)
    assert original['resolver_calls'] == 1 and original['target_events'] == 2
    changed = deepcopy(first)
    changed['expected_entity_id'], changed['semantic_label'] = None, 'NIL'
    revised = audit.evaluate_actual_candidates([changed, second], ScalarScorer(), bootstrap_replicates=10)
    assert revised['input_sha256'] == original['input_sha256']
    # Raw token span includes 조사; semantic full span correctly remains two chars.
    assert original['cohorts']['development']['by_variant']['target_full']['full_surface_boundary_mismatches'] == 0


def test_all_variants_share_actual_budget_and_do_not_use_case_fixed_candidates(monkeypatch):
    monkeypatch.setattr(audit, '_snapshot', lambda terms, family: object())
    monkeypatch.setattr(audit, 'resolve', lambda *args, **kwargs: {'mentions': [_mention()]})
    case = _case()
    case['candidates'] = [dict(entity_id='FAKE_GOLD', profile='FAKE_PROFILE')]
    scorer = ScalarScorer()
    result = audit.evaluate_actual_candidates([case], scorer, candidate_budget=1,
                                              bootstrap_replicates=10)
    assert len(scorer.pairs) == 3
    assert all('먼저 기관' in profile and 'FAKE_PROFILE' not in profile for _, profile in scorer.pairs)
    for metrics in result['cohorts']['development']['by_variant'].values():
        assert metrics['mean_candidate_count'] == 1
        assert metrics['candidate_budget_truncations'] == 1
        assert metrics['correct_proposals'] == 0  # truncation cannot create authority


def test_pair_overflow_in_later_case_preflights_before_any_score(monkeypatch):
    monkeypatch.setattr(audit, '_snapshot', lambda terms, family: object())
    monkeypatch.setattr(audit, 'resolve', lambda *args, **kwargs: {'mentions': [_mention()]})
    scorer = ScalarScorer()
    def tokenize(query, profile, **kwargs):
        return {'input_ids': [1] * (2000 if '긴문서' in query else 10)}
    scorer.tokenizer = tokenize
    with pytest.raises(ValueError, match='before inference'):
        audit.evaluate_actual_candidates([_case(), _case(name='later', text='나래 긴문서')],
                                         scorer, bootstrap_replicates=10)
    assert scorer.pairs == []


def test_actual_resolver_runs_with_complete_registered_family_catalog():
    result = audit.evaluate_actual_candidates([_case()], bootstrap_replicates=10)
    assert result['resolver_calls'] == 1
    assert result['cohorts']['development']['by_variant']['target_full']['candidate_recall'] == 1
    assert result['cohorts']['development']['by_variant']['target_full']['mean_candidate_count'] == 2
    audit._assert_public_aggregates(result)


def _historical_run(experiment='fresh_compact'):
    rows, grades, records = [], [], []
    conditions = ['none', 'full', 'compact']
    for name, injected in [('injected', True), ('identical', False)]:
        for condition in conditions:
            identity = name + (' pack' if injected and condition != 'none' else '')
            rows.append(dict(case_id=name, condition=condition, experiment=experiment,
                family_id=name, parent_document_id=name, positive_gold=True,
                evaluation_split='fresh_context_holdout', pack_injected=injected and condition != 'none',
                system='policy', user=identity, source_gold_visible=True))
            grades.append(dict(case_id=name, condition=condition, correct=condition != 'none'))
            records.append(dict(case_id=name, condition=condition, latency_ms=1,
                                usage={'prompt_tokens': 10, 'completion_tokens': 1, 'total_tokens': 11}))
    return dict(stage='fresh_compact_test', rows=rows, grades=grades, records=records,
                manifest_sha256='f' * 64, counts={'request_count': 6})


def test_reanalysis_reports_injected_and_identical_prompts_even_when_outputs_differ(monkeypatch, tmp_path):
    monkeypatch.setattr(audit, '_read_historical_runs', lambda *args: ([_historical_run()], {}))
    result = audit.reanalyze_previous(tmp_path, bootstrap_replicates=20)
    groups = result['runs']['fresh_compact_test']['paired_subgroups']['none_to_full']
    assert groups['fresh_context_holdout/pack_actually_injected']['questions'] == 1
    assert groups['fresh_context_holdout/identical_prompts']['questions'] == 1
    assert groups['fresh_context_holdout/identical_prompts']['helpful_flips'] == 1
    assert not result['subgroups_are_new_confirmatory_holdouts']
    audit._assert_public_aggregates(result)


def test_reanalysis_separates_source_visibility_lost_and_kept(monkeypatch, tmp_path):
    run = _historical_run('source_pack_factorial')
    rows, grades, records = [], [], []
    for name in ('lost', 'kept'):
        for source in ('full', 'shrunken'):
            for pack in ('none', 'full', 'compact'):
                condition = source + '_' + pack
                rows.append(dict(case_id=name, condition=condition, experiment='source_pack_factorial',
                    family_id=name, parent_document_id=name, positive_gold=True,
                    evaluation_split='adaptive_reused', pack_injected=pack != 'none',
                    system='policy', user=source + pack,
                    source_gold_visible=(source == 'full' or name == 'kept')))
                grades.append(dict(case_id=name, condition=condition, correct=source == 'full'))
                records.append(dict(case_id=name, condition=condition, latency_ms=1, usage={}))
    run.update(rows=rows, grades=grades, records=records)
    monkeypatch.setattr(audit, '_read_historical_runs', lambda *args: ([run], {}))
    result = audit.reanalyze_previous(tmp_path, bootstrap_replicates=20)
    groups = result['runs']['fresh_compact_test']['paired_subgroups']['full_none_to_shrunken_none']
    assert groups['adaptive_reused/positive_source_visibility_lost']['questions'] == 1
    assert groups['adaptive_reused/positive_source_visibility_kept']['questions'] == 1


def test_historical_source_archive_and_executable_bytes_are_verified(tmp_path):
    collected = tmp_path / 'collected'
    source = tmp_path / 'collector_source'
    collected.mkdir()
    source.mkdir()
    (source / 'original.py').write_text('VERSION = 1\n')
    archive = tmp_path / 'source.tar.gz'
    with tarfile.open(archive, 'w:gz') as bundle:
        bundle.add(source / 'original.py', arcname='original.py')
    (tmp_path / 'launch.json').write_text(json.dumps(dict(code_revision='original-revision',
        archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())))
    assert audit._verify_frozen_source(collected, source)['verified_source_files'] == 1
    (source / 'original.py').write_text('VERSION = 2\n')
    with pytest.raises(ValueError, match='differs from archive'):
        audit._verify_frozen_source(collected, source)


def test_public_proof_rejects_individual_identifiers_and_source():
    with pytest.raises(ValueError, match='cannot enter public'):
        audit._assert_public_aggregates({'aggregate': {'document_id': 'private'}})
