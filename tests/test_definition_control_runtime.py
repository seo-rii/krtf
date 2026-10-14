"""Frozen new controls run real task schemas and fail closed on altered reports."""
from copy import deepcopy
import json

import pytest

from eval import definition_control as controls, report_definition_control as report
from eval import run_product_llm as runner
from eval.run_production_queue import report_module_for_plan


@pytest.fixture()
def envelope(tmp_path):
    family = json.loads(controls.FIXTURE.read_text().splitlines()[0])
    family['documents'] = family['documents'][:1]
    path = tmp_path/'world.jsonl'
    path.write_text(json.dumps(family, ensure_ascii=False)+'\n')
    return controls.build_envelope(path)


def frozen_run(tmp_path, envelope, monkeypatch):
    path = tmp_path/'requests.json'
    path.write_bytes(runner._json_bytes(envelope))
    observed = []
    def request(url, *, payload=None, timeout):
        if url.endswith('/models'):
            return {'data': [{'id': 'served'}]}
        row = envelope['requests'][len(observed)]
        observed.append(payload)
        assert payload['messages'] == [{'role':'system','content':row['system']},
                                        {'role':'user','content':row['user']}]
        response = ({'answer': row['expected_answer']+'이다.'} if row['task']=='document_qa' else
                    {'selections':[{'surface':row['target_surface'],'entity_id':row['expected_entity_id']}]})
        return {'model':'served','choices':[{'message':{'content':json.dumps(response)},'finish_reason':'stop'}],
                'usage':{'prompt_tokens':50,'completion_tokens':10,'total_tokens':60}}
    monkeypatch.setattr(runner,'_request_json',request)
    out = tmp_path/'run'
    manifest = runner.run_benchmark(endpoint='http://localhost:18104/v1',model='served',out_dir=out,
        code_revision='frozen-revision',track='definition_control',requests_file=path)
    assert len(observed) == manifest['received_count'] == 12
    assert manifest['malformed_count'] == manifest['missing_count'] == 0
    return out


def test_runner_separates_qa_definition_format_and_routing_guard(tmp_path,envelope,monkeypatch):
    out = frozen_run(tmp_path,envelope,monkeypatch)
    summary = report.prepare_report(out)
    assert summary['counts']['request_count'] == 12
    for condition, scores in summary['metrics']['by_condition'].items():
        qa = scores['by_task']['document_qa']
        assert qa['exact_match'] == 0 and qa['semantic_match'] == 1
        assert qa['semantic_status']['MATCH'] == 1
    assert report_module_for_plan({'schema_version':4}) == 'eval.report_definition_control'
    assert 'UNASSESSED' in report.render_markdown(summary)
    with pytest.raises(ValueError,match='frozen'):
        runner.run_benchmark(endpoint='http://localhost/v1',model='served',out_dir=tmp_path/'invalid',
                             code_revision='x',track='definition_control')


def test_report_rejects_corrupted_artifacts_and_counts(tmp_path,envelope,monkeypatch):
    out = frozen_run(tmp_path,envelope,monkeypatch)
    before = (out/'responses.jsonl').read_bytes()
    (out/'responses.jsonl').write_bytes(before+b'\n')
    with pytest.raises(ValueError,match='hash'):
        report.prepare_report(out)
    (out/'responses.jsonl').write_bytes(before)
    manifest = json.loads((out/'run_manifest.json').read_text())
    manifest['received_count'] -= 1
    manifest.pop('seal_sha256')
    import hashlib
    manifest['seal_sha256'] = hashlib.sha256(runner._json_bytes(manifest)).hexdigest()
    (out/'run_manifest.json').write_bytes(runner._json_bytes(manifest))
    with pytest.raises(ValueError,match='counts'):
        report.prepare_report(out)


def test_model_comparison_requires_same_inputs_decoding(tmp_path,envelope,monkeypatch):
    out = frozen_run(tmp_path,envelope,monkeypatch)
    second = tmp_path/'second'
    import shutil,hashlib
    shutil.copytree(out,second)
    manifest = json.loads((second/'run_manifest.json').read_text())
    manifest['decoding']['max_tokens'] = 129
    manifest.pop('seal_sha256')
    manifest['seal_sha256'] = hashlib.sha256(runner._json_bytes(manifest)).hexdigest()
    (second/'run_manifest.json').write_bytes(runner._json_bytes(manifest))
    with pytest.raises(ValueError,match='identical'):
        report.prepare_report(second,compare=out)


def test_preparation_keeps_original_and_new_documents_identified(tmp_path):
    from eval.prepare_definition_control import freeze
    manifest = freeze(tmp_path/'prepared','frozen-revision')
    assert manifest['corpora']['documents']['document_count'] == 64
    assert manifest['corpora']['documents']['request_count'] == 768
    envelope = json.loads((tmp_path/'prepared'/'documents.json').read_text())
    split=envelope['provenance']['source_collection_split']
    assert list(split.values()).count('original_context') == list(split.values()).count('fresh_definition') == 32
    assert all(row['collection']==split[row['document_id']] for row in envelope['requests'])
    assert len(envelope['provenance']['source_fixture_sha256']) == 2


def test_source_definition_availability_is_not_hidden_by_empty_candidate_pack(tmp_path,envelope):
    family=json.loads(controls.FIXTURE.read_text().splitlines()[0])
    document=family['documents'][0]
    definition=document['expected_answer']
    document['text']=document['target_surface']+'를 검토한다.\n\n'+definition+'이다.'
    document['decisive_evidence']=[]
    family['documents']=[document]
    fixture=tmp_path/'visible-source.jsonl'
    fixture.write_text(json.dumps(family,ensure_ascii=False)+'\n')
    rows=controls.build_envelope(fixture)['requests']
    row=next(r for r in rows if r['condition']=='ktrf_execution_cards' and r['task']=='structured_routing')
    assert row['catalog_definition_visible'] is False
    assert row['definition_visible_in_model_input'] is True
    changed=deepcopy(row)
    changed['definition_visible_in_model_input']=False
    with pytest.raises(ValueError,match='definition visibility'):
        controls.validate_requests([changed])
