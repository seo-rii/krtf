"""Source gold, matched-fact controls and raw occurrence execution regressions."""
from copy import deepcopy
import hashlib
import json

import pytest

from eval import review_business as suite
from eval.collect_hf_qa_queue import validate_public_json
from ktrf.registry.simple_schema import compile_simple_terms


class FixtureTokenizer:
    def apply_chat_template(self, messages, **kwargs):
        assert kwargs == {'tokenize': True, 'add_generation_prompt': True,
                          'enable_thinking': False, 'return_dict': False}
        return [1] * (sum(len(m['content']) for m in messages) // 3 + 1)


@pytest.fixture(scope='module')
def natural_fixture():
    authored = suite.load_business_records()
    terms = [t for r in authored[::4] for t in r['terms']]
    glossary = compile_simple_terms({'terms': terms}, scope='global', glossary_id='fixture-public')
    rows = []
    for source in authored[:32]:
        row = deepcopy(source)
        row.update(case_id='natural:' + row['case_id'], family_id='natural:' + row['document_sha256'],
            evaluation_split='natural_public', annotation_origin='AI_ANNOTATED_PUBLIC_SOURCE',
            glossary_data=glossary,
            source_provenance={'kind': 'synthetic_unit_fixture', 'human_verified': False})
        rows.append(row)
    return rows


@pytest.fixture(scope='module')
def prepared(natural_fixture):
    # This unit fixture has its own explicit source seal, never the public gold seal.
    original = suite.REVIEWED_NATURAL_GOLD_SHA256
    suite.REVIEWED_NATURAL_GOLD_SHA256 = suite._sha([
        {k: r[k] for k in suite.NATURAL_GOLD_FIELDS} for r in natural_fixture])
    models = {k: {'path': 'unit-fixture', 'revision': 'unit-fixture'}
              for k in ('gemma12b', 'qwen27b')}
    try:
        return suite.prepare_review_business(natural_cases=natural_fixture,
            tokenizers={k: FixtureTokenizer() for k in models}, models=models, code_revision='f' * 40)
    finally:
        suite.REVIEWED_NATURAL_GOLD_SHA256 = original


def test_authored_gold_is_source_first_balanced_and_independently_reviewed():
    records = suite.load_business_records()
    assert len(records) == 64
    assert len({r['family_id'] for r in records}) == 16
    assert sum(r['expected_entity_id'] is not None for r in records) == 32
    assert sum(r['qa']['requires_terminology'] for r in records) == 32
    assert sum(r['stratum'] == 'unregistered_typo' for r in records) == 4
    assert all(not r['human_verified'] and r['rationale'] for r in records)
    assert hashlib.sha256(suite.CASES_FILE.read_bytes()).hexdigest() == suite.REVIEWED_CASE_FILE_SHA256
    for r in records:
        s = r['target_full_span']
        assert r['text'][s['start']:s['end']] == r['target_surface']
        if r['qa']['requires_terminology'] and r['expected_entity_id']:
            # The glossary fact was not accidentally copied into the source.
            assert all(a not in r['text'] for a in r['qa']['answers'])


def test_fixture_seal_must_precede_resolver_access(monkeypatch):
    monkeypatch.setattr(suite, 'REVIEWED_CASE_FILE_SHA256', '0' * 64)
    monkeypatch.setattr(suite, 'prepare_llm_context', lambda *a, **kw: pytest.fail('resolver reached'))
    with pytest.raises(ValueError, match='independent review'):
        suite.prepare_review_business(natural_cases=[], tokenizers={'gemma12b': None, 'qwen27b': None},
                                      models={'gemma12b': {}, 'qwen27b': {}}, code_revision='f' * 40)


def test_768_requests_hold_source_gold_schema_and_matched_facts_fixed(prepared):
    envelope, proof, records = prepared
    rows = envelope['requests']
    assert len(rows) == proof['request_count'] == 768
    assert proof['split_case_counts'] == {'authored_business': 64, 'natural_public': 32}
    assert proof['authored_families'] == 16
    assert len(records) == 64
    validate_public_json(proof)
    for model in proof['models'].values():
        assert model['path'] == 'unit-fixture'
        assert model['max_prompt_tokens'] + 384 <= 8192
        assert model['overflow_count'] == 0 and model['apply_chat_template']
        assert model['enable_thinking'] is False
    assert all(r['response_schema'] == suite.ROUTING_SCHEMA for r in rows)
    assert all(r['execution_contract'] == 'occurrence_v1' for r in rows)
    for case_id in {r['case_id'] for r in rows}:
        group = [r for r in rows if r['case_id'] == case_id]
        assert len(group) == 8
        assert len({r['document_sha256'] for r in group}) == 1
        assert len({suite._sha(r['selection_binding']) for r in group}) == 1
        assert len({r['facts_sha256'] for r in group if r['control'] == 'matched'}) == 1
        assert all(r['text'] in r['user'] for r in group)
    starts = [rows[i]['condition'] for i in range(0, len(rows), 8)]
    assert starts[:8] == list(suite.CONDITIONS)
    review = envelope['provenance']['source']['independent_ai_review']
    assert review['cases_reviewed'] == 96 and review['resolved_before_resolver']
    good = next(r for r in rows if r['case_id'] == 'rev-glass:1'
                and r['condition'] == 'matched_ktrf_base')
    assert '<resolved_terms authority="actual_resolver_occurrences_only">' in good['prompt_fragment']
    assert 'global:rev-glass' in good['offered_entity_ids']
    unresolved = next(r for r in rows if r['case_id'] == 'rev-calendar:2'
                      and r['condition'] == 'matched_ktrf_base')
    assert not unresolved['pack']['resolved_terms']
    assert '<resolved_terms' not in unresolved['prompt_fragment']


@pytest.mark.parametrize('mutation', [
    lambda r: r.update(user=r['user'] + '\nchanged'),
    lambda r: r.update(system=r['system'] + '\nchanged'),
    lambda r: r.update(document_sha256='0' * 64),
    lambda r: r.update(execution_contract='legacy_surface_v1'),
    lambda r: r.update(gold={'label': 'NIL', 'entity_ref': None}),
    lambda r: r['selection_binding'].update(mention_id='another-occurrence'),
    lambda r: r.update(response_schema={'type': 'object'}),
    lambda r: r['offered_cards'].append({'entity_id': 'invented'}),
])
def test_source_or_condition_tampering_is_rejected(prepared, mutation):
    rows = deepcopy(prepared[0]['requests'])
    mutation(rows[0])
    with pytest.raises((ValueError, KeyError)):
        suite.validate_business_requests(rows)


def _response(row, entity_id):
    return {'selections': [{**deepcopy(row['selection_binding']), 'entity_id': entity_id}]}


def test_strict_guard_consumes_complete_output_and_preserves_raw_semantics(prepared):
    rows = prepared[0]['requests']
    row = next(r for r in rows if r['condition'] == 'pipeline_ktrf_base'
               and r['case_id'] == 'rev-glass:1')
    good = _response(row, row['expected_entity_id'])
    grade = suite.grade_business_response(good, row)
    assert grade['accepted_correct_id'] and grade['semantic_match']
    good['selections'][0]['mention_id'] = 'unresolved-other-occurrence'
    grade = suite.grade_business_response(good, row)
    assert grade['semantic_match'] and grade['rejected_correct_id']
    assert not grade['accepted_correct_id']
    bad = _response(row, row['expected_entity_id'])
    bad['answer'] = 'mixed QA response must not be projected'
    assert suite.business_response_error(bad, row)
    assert not suite.grade_business_response(bad, row)['guard_valid']


def test_plain_baseline_uses_own_offered_ids_and_exact_occurrence(prepared):
    row = next(r for r in prepared[0]['requests'] if r['condition'] == 'pipeline_plain_base'
               and r['case_id'] == 'rev-glass:1')
    assert suite.grade_business_response(_response(row, row['expected_entity_id']), row)['accepted_correct_id']
    assert not suite.grade_business_response(_response(row, 'global:invented'), row)['guard_valid']
    wrong = _response(row, row['expected_entity_id'])
    wrong['selections'][0]['document_hash'] = '0' * 64
    assert not suite.grade_business_response(wrong, row)['guard_valid']
    abstain = suite.grade_business_response(_response(row, None), row)
    assert abstain['over_abstention'] and abstain['guard_valid']


def test_wrong_meaning_is_not_equated_with_guard_failure(prepared):
    row = next(r for r in prepared[0]['requests'] if r['condition'] == 'pipeline_plain_base'
               and r['case_id'] == 'rev-glass:3')
    wrong = _response(row, row['offered_entity_ids'][0])
    grade = suite.grade_business_response(wrong, row)
    assert grade['accepted_wrong_id'] and not grade['semantic_match']
    abstain = suite.grade_business_response(_response(row, None), row)
    assert abstain['correct_abstention'] and abstain['correct']


def test_multioccurrence_binding_selects_requested_final_position(prepared):
    row = next(r for r in prepared[0]['requests'] if r['case_id'] == 'rev-glass:4'
               and r['condition'] == 'pipeline_ktrf_base')
    assert row['target_span'][0] == row['text'].rfind(row['target_surface'])
    assert row['selection_binding']['core_span']['start'] == row['target_span'][0]
    first = next(c for c in row['pack']['resolved_terms'] for c in c['mentions']
                 if c['core_span']['start'] == row['text'].index(row['target_surface']))
    borrowed = _response(row, 'global:rev-glass')
    borrowed['selections'][0].update({k: first[k] for k in ('mention_id', 'core_span', 'full_span')})
    # A valid occurrence elsewhere must not authorize the requested occurrence.
    assert not suite.grade_business_response(borrowed, row)['correct']
    # The core guard is pack-bound; the benchmark must also enforce requested binding.
    assert not suite.grade_business_response(borrowed, row)['accepted_wrong_id']


def test_public_annotations_require_reviewed_source_seal(natural_fixture):
    with pytest.raises(ValueError, match='pre-resolver review'):
        suite.load_natural_records(natural_fixture)


def test_shared_runtime_keeps_raw_semantics_separate_from_approved_actions(prepared):
    from eval.run_extended_suite import grade_outputs, schema_for, validate_requests
    envelope = prepared[0]
    rows, protocol = envelope['requests'], envelope['protocol']
    validate_requests(rows, protocol)
    assert schema_for(rows, protocol) == suite.ROUTING_SCHEMA
    correct = next(r for r in rows if r['case_id'] == 'rev-glass:1'
                   and r['condition'] == 'pipeline_ktrf_base')
    wrong = next(r for r in rows if r['case_id'] == 'rev-glass:3'
                 and r['condition'] == 'pipeline_plain_base')
    outputs = [{'case_id': r['case_id'], 'condition': r['condition'], 'status': 'RECEIVED',
                'response': _response(r, eid)}
               for r, eid in [(correct, correct['expected_entity_id']),
                              (wrong, wrong['offered_entity_ids'][0])]]
    result = grade_outputs(rows, outputs, protocol)
    assert result['missing_outputs'] == 766
    assert result['by_variant']['pipeline_ktrf_base']['accepted_correct_id'] == 1
    assert result['by_variant']['pipeline_plain_base']['accepted_wrong_id'] == 1
    assert result['by_evaluation_split']['authored_business']['questions'] == 64
    assert result['by_evaluation_split']['natural_public']['questions'] == 32
