"""Reviewed source -> frozen five-arm envelope with conditional wire schemas."""
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json

import pytest

from eval import prepare_evidence_efficiency as wrapper
from eval.evidence_efficiency import (
    CONDITIONS, compact_projection, expand_compact_projection, evidence_efficiency_schema,
    _short_facts, _short_inventory,
)
from eval.evidence_efficiency_data import (
    CASES_FILE, REVIEW_FILE, SOURCE_SHA256, REVIEW_SHA256, load_evidence_efficiency_records,
)
from eval.hf_qa import canonical
from eval.run_extended_suite import load_request_file, schema_for
from test_evidence_efficiency import FixtureTokenizer


def config():
    return {'source_sha256': SOURCE_SHA256, 'review_sha256': REVIEW_SHA256,
        'models': {key: {'path': 'fixture:' + key} for key in ('gemma12b', 'qwen27b')}}


@pytest.fixture(scope='module')
def prepared(tmp_path_factory):
    output = tmp_path_factory.mktemp('efficiency-wrapper') / 'prepared'
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(wrapper, 'load_tokenizers',
                      lambda models: {key: FixtureTokenizer() for key in models})
        manifest = wrapper.prepare(config(), output, code_revision='f' * 40)
    return output, manifest


@pytest.mark.parametrize('field', ['source_sha256', 'review_sha256'])
def test_changed_seal_rejected_before_resolution_or_tokenizers(tmp_path, monkeypatch, field):
    selected = config()
    selected[field] = '0' * 64
    monkeypatch.setattr(wrapper, 'load_evidence_efficiency_records',
                        lambda: pytest.fail('changed source must fail before loader'))
    monkeypatch.setattr(wrapper, 'load_tokenizers',
                        lambda _: pytest.fail('changed source must fail before tokenizer or resolver'))
    with pytest.raises(ValueError, match='source gold or independent review changed'):
        wrapper.prepare(selected, tmp_path / 'absent', code_revision='f' * 40)
    assert not (tmp_path / 'absent').exists()


def test_immutable_revision_and_exact_model_pair_required(tmp_path):
    with pytest.raises(ValueError, match='immutable code revision'):
        wrapper.prepare(config(), tmp_path / 'moving', code_revision='main')
    selected = config()
    selected['models'].pop('gemma12b')
    with pytest.raises(ValueError, match='both frozen model tokenizers'):
        wrapper.prepare(selected, tmp_path / 'one-model', code_revision='f' * 40)


def test_frozen_review_covers_source_before_preparation(prepared):
    output, manifest = prepared
    assert hashlib.sha256(CASES_FILE.read_bytes()).hexdigest() == SOURCE_SHA256
    assert hashlib.sha256(REVIEW_FILE.read_bytes()).hexdigest() == REVIEW_SHA256
    review = json.loads(REVIEW_FILE.read_text())
    source = manifest['source']
    assert source['independent_ai_review']['reviewer'] == review['reviewer']
    assert source['independent_ai_review']['cases_reviewed'] == 64
    assert source['independent_ai_review']['resolved_before_resolver']
    assert not source['human_verified']
    assert source['evaluation_population'] == 'FRESH_AI_AUTHORED_CONFIRMATION'
    assert manifest['total_planned_model_calls'] == 640
    assert manifest['split_case_counts'] == {'development': 16, 'confirmation': 48}
    assert manifest['methods_selected_from_prior_results_source_sealed_before_new_inference']
    assert manifest['real_business_shadow_status'] == 'WAITING_FOR_INPUT'
    assert json.loads((output / 'manifest.json').read_text()) == manifest


def test_real_source_roundtrip_preserves_gold_candidates_and_definitions(prepared):
    output, manifest = prepared
    rows, protocol, provenance = load_request_file(output / 'evidence_efficiency.json')
    sources = {row['case_id']: row for row in load_evidence_efficiency_records()}
    assert len(rows) == 320
    grouped = defaultdict(list)
    for row in rows:
        grouped[row['case_id']].append(row)
        original = sources[row['case_id']]
        for key in ('text', 'document_sha256', 'target_core_span', 'target_full_span',
                    'target_surface', 'gold', 'expected_entity_id', 'family_id', 'evaluation_split'):
            assert row[key] == original[key]
        assert row['text'] in row['user']
        assert row['offered_entity_ids'] == row['pipeline_trace']['candidate_entity_ids']
        assert row['compact_projection'] == compact_projection(row)
        assert expand_compact_projection(row['compact_projection']) == (_short_facts(row), _short_inventory(row))
        for card in row['offered_cards']:
            assert card['definition'] in row['user']
    assert len(grouped) == 64
    assert all(len(group) == 5 and {r['condition'] for r in group} == set(CONDITIONS)
               for group in grouped.values())
    assert Counter(group[0]['evaluation_split'] for group in grouped.values()) == {
        'development': 16, 'confirmation': 48}
    families = {split: {r['family_id'] for r in rows if r['evaluation_split'] == split}
                for split in ('development', 'confirmation')}
    assert len(families['development']) == 2 and len(families['confirmation']) == 6
    assert families['development'].isdisjoint(families['confirmation'])
    assert provenance['source'] == manifest['source']
    proof = manifest['experiments']['evidence_efficiency']
    assert proof['request_count'] == 320 and proof['question_count'] == 64
    assert proof['envelope_sha256'] == hashlib.sha256((output / 'evidence_efficiency.json').read_bytes()).hexdigest()
    assert proof['requests_sha256'] == hashlib.sha256(b''.join(canonical(r) for r in rows)).hexdigest()


def test_conditional_schema_manifest_covers_each_request_separately(prepared):
    output, _ = prepared
    rows, protocol, _ = load_request_file(output / 'evidence_efficiency.json')
    schemas = schema_for(rows, protocol)
    assert len(schemas) == 320
    for row in rows:
        key = json.dumps([row['case_id'], row['condition']], ensure_ascii=False, separators=(',', ':'))
        assert schemas[key] == evidence_efficiency_schema(row)
    selected = [r for r in rows if r['condition'] == 'selective_compact']
    assert all(r['evidence_required'] == r['source_only_route']['evidence_required'] for r in selected)
    assert sum(not r['evidence_required'] for r in selected) + sum(r['evidence_required'] for r in selected) == 64
    # This records the actual gate distribution without forcing source cases into either route.
    assert all(r['difficulty_gate']['easy'] == (not r['evidence_required']) for r in selected)
