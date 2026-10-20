"""Frozen wrapper and non-executing shadow replay against the reviewed source."""
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json

import pytest

from eval import prepare_routing_confirmation as wrapper
from eval.collect_hf_qa_queue import validate_public_json
from eval.hf_qa import canonical
from eval.routing_confirmation import CONDITIONS, records_sha256
from eval.routing_confirmation_data import (
    CASES_FILE, REVIEW_FILE, SOURCE_SHA256, REVIEW_SHA256, load_routing_confirmation_records,
)
from eval.run_extended_suite import load_request_file
from eval.shadow_routing import load_shadow_documents, prepare_shadow


class FixtureTokenizer:
    def apply_chat_template(self, messages, **kwargs):
        assert kwargs == {'tokenize': True, 'add_generation_prompt': True,
                          'enable_thinking': False, 'return_dict': False}
        return [1] * (sum(len(message['content']) for message in messages) // 4 + 1)


def config():
    return {'source_sha256': SOURCE_SHA256, 'review_sha256': REVIEW_SHA256,
        'models': {name: {'path': 'unit-fixture:' + name, 'revision': 'unit-fixture'}
                   for name in ('gemma12b', 'qwen27b')}}


@pytest.fixture(scope='module')
def prepared(tmp_path_factory):
    parent = tmp_path_factory.mktemp('routing-wrapper')
    output = parent / 'prepared'
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(wrapper, 'load_tokenizers', lambda models: {
            key: FixtureTokenizer() for key in models})
        manifest = wrapper.prepare(config(), output, code_revision='f' * 40)
    return output, manifest


@pytest.mark.parametrize('field', ['source_sha256', 'review_sha256'])
def test_source_and_review_hash_mismatch_fail_before_loader_or_tokenizer(tmp_path, monkeypatch, field):
    selected = config()
    selected[field] = '0' * 64
    monkeypatch.setattr(wrapper, 'load_routing_confirmation_records',
                        lambda: pytest.fail('source loader reached before identity check'))
    monkeypatch.setattr(wrapper, 'load_tokenizers',
                        lambda models: pytest.fail('tokenizer/resolver preparation reached'))
    output = tmp_path / 'should-not-exist'
    with pytest.raises(ValueError, match='source gold or independent review changed'):
        wrapper.prepare(selected, output, code_revision='f' * 40)
    assert not output.exists()


def test_immutable_revision_and_both_models_required(tmp_path):
    with pytest.raises(ValueError, match='immutable code revision'):
        wrapper.prepare(config(), tmp_path / 'revision', code_revision='main')
    missing = config()
    missing['models'].pop('gemma12b')
    with pytest.raises(ValueError, match='both frozen model tokenizers'):
        wrapper.prepare(missing, tmp_path / 'one-model', code_revision='f' * 40)


def test_real_source_review_seals_before_resolution(prepared):
    output, manifest = prepared
    assert hashlib.sha256(CASES_FILE.read_bytes()).hexdigest() == SOURCE_SHA256
    assert hashlib.sha256(REVIEW_FILE.read_bytes()).hexdigest() == REVIEW_SHA256
    records = load_routing_confirmation_records()
    review = json.loads(REVIEW_FILE.read_text())
    source = manifest['source']
    assert source['source_sha256'] == SOURCE_SHA256
    assert source['review_sha256'] == REVIEW_SHA256
    assert source['records_sha256'] == records_sha256(records)
    assert source['source_gold_before_resolver'] is True
    assert source['human_verified'] is False
    assert source['private_workplace_distribution_measured'] is False
    assert source['independent_ai_review']['resolved_before_resolver'] is True
    assert source['independent_ai_review']['reviewer'] == review['reviewer']
    assert source['independent_ai_review']['cases_reviewed'] == len(records) == 192
    assert source['independent_ai_review']['records_sha256'] == records_sha256(records)
    assert set(review['reviewed_case_ids']) == {record['case_id'] for record in records}
    assert manifest['phase'] == 'FINAL_FROZEN'
    assert manifest['total_planned_model_calls'] == 2304
    assert manifest['real_business_shadow_status'] == 'WAITING_FOR_INPUT'
    assert manifest['raw_request_envelopes_and_individual_answers_remain_private'] is True
    assert manifest['fictional_source_gold_is_versioned'] is True
    validate_public_json(manifest)
    assert json.loads((output / 'manifest.json').read_text()) == manifest


def test_all_192_cases_keep_immutable_source_and_six_paired_conditions(prepared):
    output, manifest = prepared
    rows, protocol, provenance = load_request_file(output / 'routing_confirmation.json')
    source_records = {record['case_id']: record for record in load_routing_confirmation_records()}
    assert len(rows) == 1152
    assert protocol['conditions'] == list(CONDITIONS)
    assert protocol['reserved_output_tokens'] == 768
    assert provenance['source'] == manifest['source']
    grouped = defaultdict(list)
    for row in rows:
        grouped[row['case_id']].append(row)
        original = source_records[row['case_id']]
        for field in ('text', 'document_sha256', 'target_core_span', 'target_full_span',
                      'target_surface', 'gold', 'expected_entity_id', 'family_id', 'evaluation_split'):
            assert row[field] == original[field]
        assert row['text'] in row['user']
        assert row['reserved_output_tokens'] == 768
        assert row['source_records_sha256'] == manifest['source']['records_sha256']
    assert len(grouped) == 192
    for group in grouped.values():
        assert len(group) == 6
        assert {row['condition'] for row in group} == set(CONDITIONS)
        assert len({canonical(row['selection_binding']) for row in group}) == 1
        assert len({canonical(row['pipeline_trace']) for row in group}) == 1
    assert Counter(group[0]['evaluation_split'] for group in grouped.values()) == {
        'development': 64, 'confirmation': 128}
    splits = defaultdict(set)
    for group in grouped.values():
        splits[group[0]['evaluation_split']].add(group[0]['family_id'])
    assert len(splits['development']) == 8
    assert len(splits['confirmation']) == 16
    assert splits['development'].isdisjoint(splits['confirmation'])
    proof = manifest['experiments']['routing_confirmation']
    assert proof['request_count'] == 1152
    assert proof['question_count'] == 192
    assert proof['requests_sha256'] == hashlib.sha256(b''.join(canonical(row) for row in rows)).hexdigest()
    assert proof['envelope_sha256'] == hashlib.sha256((output / 'routing_confirmation.json').read_bytes()).hexdigest()
    for model in proof['models'].values():
        assert model['request_count'] == 1152
        assert model['reserved_output_tokens'] == 768
        assert model['overflow_count'] == 0
        assert model['max_prompt_tokens'] + model['reserved_output_tokens'] <= 8192


def test_shadow_exports_complete_glossary_sources_and_separate_family_components(prepared):
    output, manifest = prepared
    raw = [json.loads(line) for line in (output / 'synthetic_shadow.jsonl').read_text().splitlines()]
    records = {record['document_id']: record for record in load_routing_confirmation_records()}
    assert len(raw) == len({row['document_id'] for row in raw}) == 192
    for row in raw:
        assert set(row) == {'document_id', 'family_id', 'text', 'source_origin', 'source_revision', 'partition'}
        assert row['source_origin'] == 'AI_AUTHORED'
        assert row['source_revision'] == SOURCE_SHA256
        assert row['text'] == records[row['document_id']]['text']
        assert row['partition'] == records[row['document_id']]['evaluation_split']
    glossary = json.loads((output / 'synthetic_glossary.json').read_text())
    assert len(glossary['entities']) == 48
    expected_ids = {'global:' + term['key'] for record in records.values() for term in record['terms']}
    assert {entity['entity_id'] for entity in glossary['entities']} == expected_ids
    documents, digest = load_shadow_documents(output / 'synthetic_shadow.jsonl')
    assert digest == hashlib.sha256((output / 'synthetic_shadow.jsonl').read_bytes()).hexdigest()
    components = defaultdict(list)
    for row in documents:
        components[row['source_component_id']].append(row)
    assert len(components) == 24
    assert all(len(group) == 8 and len({row['partition'] for row in group}) == 1
               for group in components.values())
    assert Counter(row['partition'] for row in documents) == {'development': 64, 'confirmation': 128}
    assert manifest['real_business_shadow_status'] == 'WAITING_FOR_INPUT'


def test_prepared_sources_replay_without_actions_or_automated_gold(prepared, tmp_path):
    output, _ = prepared
    shadow = tmp_path / 'shadow-replay'
    manifest = prepare_shadow(output / 'synthetic_shadow.jsonl', output / 'synthetic_glossary.json',
                              shadow, replay=True, repeats=1)
    assert manifest['status'] == 'SHADOW_REPLAY_COMPLETE'
    assert manifest['document_count'] == 192
    assert manifest['source_component_count'] == 24
    assert manifest['partition_counts'] == {'development': 64, 'confirmation': 128}
    assert manifest['source_origin_counts'] == {'AI_AUTHORED': 192}
    assert manifest['real_business_pilot_status'] == 'NOT_ACTUAL_BUSINESS_INPUT'
    assert manifest['execution_enabled'] is False
    assert manifest['actions_performed'] == 0
    assert manifest['actual_business_data_verified'] is False
    assert manifest['semantic_accuracy'] is None
    assert manifest['resolver_calls'] == 384
    requests = [json.loads(line) for line in (shadow / 'shadow_requests.jsonl').read_text().splitlines()]
    proposals = [json.loads(line) for line in (shadow / 'shadow_proposals.jsonl').read_text().splitlines()]
    assert len(requests) == len(proposals) == 192
    assert all(row['purpose'] == 'SHADOW_PROPOSAL_ONLY' and not row['execution_enabled'] for row in requests)
    assert all(not row['execution_enabled'] and not row['action_performed']
               and row['semantic_correctness'] is None for row in proposals)
    blind = json.loads((shadow / 'blind_annotation.json').read_text())
    assert blind['annotation_status'] == 'UNANNOTATED'
    assert blind['resolver_output_visible'] is False
    assert blind['human_verified'] is False
    assert len(blind['documents']) == 192
    assert all(row['annotations'] == [] and row['annotation_status'] == 'UNANNOTATED'
               for row in blind['documents'])
    summary = json.loads((shadow / 'summary.json').read_text())
    validate_public_json(summary)
    assert summary['status'] == 'SHADOW_REPLAY_COMPLETE'
    assert summary['actions_performed'] == 0
    assert summary['latency']['network_included'] is False
    assert summary['latency']['llm_included'] is False
    assert summary['latency']['repeat_call_ms']['observations'] == 192


def test_cross_family_partition_leak_is_rejected_on_export_import(prepared, tmp_path):
    output, _ = prepared
    rows = [json.loads(line) for line in (output / 'synthetic_shadow.jsonl').read_text().splitlines()]
    corrupted = deepcopy(rows)
    development = next(row for row in corrupted if row['partition'] == 'development')
    confirmation = next(row for row in corrupted if row['partition'] == 'confirmation')
    confirmation['event_id'] = 'linked-source-event'
    development['event_id'] = 'linked-source-event'
    path = tmp_path / 'cross-partition.jsonl'
    path.write_bytes(b''.join(canonical(row) for row in corrupted))
    with pytest.raises(ValueError, match='source component crosses'):
        load_shadow_documents(path)
