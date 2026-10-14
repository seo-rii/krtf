"""Opt-in definition evidence cannot override structural or budget safety."""
from dataclasses import replace

import pytest

from ktrf.context import ContextPolicy, prepare_llm_context, validate_llm_grounding
from ktrf.fusion import FEATURE_NAMES, FusionModel
from ktrf.glossary import load_glossary
from ktrf.registry.simple_schema import compile_simple_terms
from ktrf.resolver import resolve
from ktrf.snapshot import RuntimePolicy, compile_snapshot


def snapshot(enabled=False, **kwargs):
    terms = {'terms': [
        {'key': 'billing', 'canonical': '청구 관리팀', 'surfaces': ['공통'],
         'short_definition': '월별 청구 오류를 검토하는 조직'},
        {'key': 'entry', 'canonical': '방문 승인팀', 'surfaces': ['공통'],
         'short_definition': '방문자의 출입을 사전에 승인하는 조직'}]}
    glossary = load_glossary(compile_simple_terms(terms, scope='global', glossary_id='context-test'))
    return compile_snapshot(glossary, policy=RuntimePolicy(contextual_exact_resolution=enabled, **kwargs),
                            run_conformance=False)


def mention(response):
    return next(m for m in response['mentions'] if m['surface'] == '공통')


def test_default_stays_ambiguous_and_enabled_self_definition_is_executable():
    text = '공통은 월별 청구 오류를 검토하는 조직이다.'
    off, on = snapshot(), snapshot(True)
    assert off.snapshot_id != on.snapshot_id
    assert mention(resolve(off, text))['link_decision'] == 'AMBIGUOUS'
    result = mention(resolve(on, text))
    assert result['link_decision'] == 'RESOLVED'
    assert result['resolved_entity']['entity_id'] == 'global:billing'
    assert result['resolved_entity']['decision_basis'] == 'EXPERIMENTAL_CONTEXT_DEFINITION'
    proof = result['contextual_resolution']
    a, b = proof['support_span']
    assert text[a:b] == proof['support_quote']
    assert result['prediction_set']['calibration_status'] == 'HEURISTIC'
    assert result['prediction_set']['coverage_valid'] is False
    prepared = prepare_llm_context(on, text, query='공통', context_policy=ContextPolicy(profile='automation'))
    assert prepared.should_inject
    guard = validate_llm_grounding({'selections': [{'surface': '공통', 'entity_id': 'global:billing'}]},
                                   prepared.context_pack, purpose='execution')
    assert guard['valid']
    assert prepared.context_pack['resolved_terms'][0]['resolution']['contextual_evidence']['support_quote']


def test_output_budget_order_and_fast_mode_preserve_decisions():
    snap = snapshot(True)
    text = '공통은 월별 청구 오류를 검토하는 조직이다.'
    results = [mention(resolve(snap, text, options={'max_prediction_set': cap})) for cap in (1, 2, 8)]
    assert {m['resolved_entity']['entity_id'] for m in results} == {'global:billing'}
    assert results[0]['prediction_set']['truncated']
    assert mention(resolve(snap, text, mode='fast'))['link_decision'] == 'AMBIGUOUS'
    ambiguous = [mention(resolve(snap, '공통을 다음 주에 적용한다.', options={'max_prediction_set': cap}))
                 for cap in (1, 2)]
    assert all(m['link_decision'] == 'AMBIGUOUS' for m in ambiguous)


@pytest.mark.parametrize('text', [
    '공통은 월별 청구 오류를 검토하는 조직이 아니다.',
    '공통은 새 행사 이름이다. 청구 관리팀도 행사에 참석한다.',
    '공통팀장은 월별 청구 오류를 검토하는 조직을 이끄는 사람이다.',
    '공통은 방문 승인팀 또는 청구 관리팀을 가리킨다.',
    '공통을 확인한다.\n\n다른 주제다.\n\n청구 관리팀은 월별 청구 오류를 검토하는 조직이다.',
])
def test_nonmention_role_negation_competition_and_unrelated_context_cannot_promote(text):
    m = mention(resolve(snapshot(True), text))
    assert m['link_decision'] != 'RESOLVED'


def test_new_evidence_is_not_used_with_unfitted_feature_schema():
    snap = replace(snapshot(True), fusion=FusionModel([0.] * len(FEATURE_NAMES), 0.))
    m = mention(resolve(snap, '공통은 월별 청구 오류를 검토하는 조직이다.',
                        options={'return_trace': True}))
    assert 'contextual_resolution' not in m
    assert m['link_decision'] != 'RESOLVED'


def test_policy_flag_must_be_explicit_boolean():
    with pytest.raises(ValueError, match='boolean'):
        RuntimePolicy(contextual_exact_resolution=1)


@pytest.mark.parametrize('text', [
    '공통에 요청을 보낸다. 다른 업무를 맡은 조직도 있다. 이는 월별 청구 오류를 검토하는 조직이다.',
    '문구는 다음과 같다: “공통은 월별 청구 오류를 검토하는 조직이다.”',
    '틀린 주장: 공통은 월별 청구 오류를 검토하는 조직이다.',
    '공통은 월별 청구 오류를 검토하는 조직이다. 그 설명은 틀렸다.',
])
def test_quoted_disputed_and_unbound_definitions_cannot_authorize_execution(text):
    snap = snapshot(True)
    assert mention(resolve(snap, text))['link_decision'] != 'RESOLVED'
    pack = prepare_llm_context(snap, text, query='공통', context_policy=ContextPolicy(profile='automation')).context_pack
    assert not validate_llm_grounding({'selections':[{'surface':'공통','entity_id':'global:billing'}]},
                                      pack, purpose='execution')['valid']


def test_actual_fitted_calibrator_retains_its_original_decision_without_new_feature():
    from ktrf.calibration import TunedCalibrator
    calibrated = TunedCalibrator(1., 0., .05, {'exact|multi':1.}, 1., 1., {'exact|multi':30}, 20)
    snap = replace(snapshot(True), calibrator=calibrated)
    result = resolve(snap,'공통은 월별 청구 오류를 검토하는 조직이다.', options={'return_trace':True})
    assert result['trace']['contextual_exact_skipped'] == 'unsupported_learned_artifact'
    assert 'contextual_resolution' not in mention(result)


@pytest.mark.parametrize('blocker',['non_exact','weak_boundary','blocked','truncated','exact_overflow'])
def test_context_evidence_cannot_rehabilitate_invalid_or_incomplete_candidate_pool(blocker,monkeypatch):
    from ktrf.candidates import Candidate, CandidateBudget, CandidatePool
    from ktrf.resolver import MentionNode, _contextual_exact
    import ktrf.context_resolution as evidence
    pool = CandidatePool(CandidateBudget())
    for eid in ('global:billing','global:entry'):
        pool.add(Candidate(eid,None,None,is_exact=True,generation_channels={'exact'},
                           channel_scores={'exact':1.},provenance={'boundary':'PASS'}))
    if blocker == 'non_exact':
        pool.add(Candidate('foreign',None,None,is_exact=False))
    elif blocker == 'weak_boundary':
        pool.exact['global:billing'].provenance['boundary'] = 'SOFT'
    elif blocker == 'blocked':
        pool.exact['global:billing'].commit_blocked = 'guard_block'
    elif blocker == 'truncated':
        pool.stats.non_exact_truncated = 1
    else:
        pool.exact_overflow = True
    monkeypatch.setattr(evidence,'assess_context',lambda *args,**kw: pytest.fail('blocked node must not request promotion'))
    node = MentionNode((0,2),'공통',pool)
    trace = {}
    _contextual_exact({(0,2):node},snapshot(True),'공통은 월별 청구 오류를 검토하는 조직이다.',{},'commit',trace)
    assert node.contextual_evidence is None
    assert trace['contextual_exact_supported'] == 0


def test_fresh_authored_corpus_preserves_negative_guards_and_authorizes_supported_declarations():
    import json
    from pathlib import Path
    fixture=Path(__file__).resolve().parents[1]/'eval/fixtures/context_definitions/families.jsonl'
    accepted=0
    for line in fixture.read_text().splitlines():
        family=json.loads(line)
        glossary=load_glossary(compile_simple_terms({'terms':family['terms']},scope='global',glossary_id=family['family_id']))
        snap=compile_snapshot(glossary,policy=RuntimePolicy(contextual_exact_resolution=True),run_conformance=False)
        for document in family['documents']:
            prepared=prepare_llm_context(snap,document['text'],query=document['target_surface'],
                                         context_policy=ContextPolicy(profile='automation'))
            expected=document['gold']['entity_ref']
            proposed={'selections':[{'surface':document['target_surface'],'entity_id':expected}]}
            if expected is not None and validate_llm_grounding(proposed,prepared.context_pack,purpose='execution')['valid']:
                accepted+=1
            if expected is None:
                for entity in glossary.entities:
                    response={'selections':[{'surface':document['target_surface'],'entity_id':entity.entity_id}]}
                    assert not validate_llm_grounding(response,prepared.context_pack,purpose='execution')['valid']
    assert accepted==15  # One valid short canonical intentionally remains outside this evidence rule.


def test_default_snapshot_identity_preserves_pre_feature_policy_hash():
    import dataclasses
    from ktrf.snapshot import _hash
    snap=snapshot()
    original_policy=dataclasses.asdict(snap.policy)
    original_policy.pop('contextual_exact_resolution')
    assert snap.manifest['policy_hash']==_hash(original_policy)
    assert snap.manifest['resolver_semantics_version']=='safety-2-path-union-1'
    assert 'context_definition_semantics_version' not in snap.manifest
    enabled=snapshot(True)
    assert enabled.manifest['context_definition_semantics_version']=='context-definition-2'
