"""Frozen, source-first final confirmation data; no resolver-derived labels."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path

import pytest

from eval import support_recovery_data as data


def artifact():
    return json.loads(data.CASES_FILE.read_text())


def test_final_confirmation_families_are_source_first_and_independent():
    rows = data.load_support_recovery_records(require_review=False)
    assert len(rows) == 96
    assert {r['evaluation_split'] for r in rows} == {'confirmation'}
    assert len({r['family_id'] for r in rows}) == 12
    assert Counter(r['gold']['label'] for r in rows) == {
        'LINK':48, 'NIL':24, 'NON_MENTION':6, 'COMPOSITIONAL':6, 'AMBIGUOUS':12,
    }
    assert Counter(r['scenario_style'] for r in rows) == {
        'incident_investigation':32, 'procurement_email':32, 'handover_chat':32,
    }
    for field in ('case_id','document_id','event_id','parent_document_id','document_sha256'):
        assert len({r[field] for r in rows}) == 96
    assert all(r['annotation_origin'] == 'AI_AUTHORED' and not r['human_verified'] for r in rows)
    assert all(r['source_provenance']['authored_before_resolver'] for r in rows)
    assert all(r['source_provenance']['authored_before_generation'] for r in rows)
    assert data.load_support_recovery_records('development', require_review=False) == []


def test_positive_grounding_distinguishes_cross_paragraph_omission_and_conflict():
    rows = data.load_support_recovery_records(require_review=False)
    for fid in data.ALL_FAMILIES:
        group = [r for r in rows if r['family_id']==fid]
        assert len(group) == 8
        assert sum(r['expected_entity_id'] is not None for r in group)==4
        shared=set(group[0]['terms'][0]['surfaces']) & set(group[0]['terms'][1]['surfaces'])
        assert len(shared)==1
        assert sum(r['target_surface'] in shared for r in group)==2
        assert all('applicability' not in t for t in group[0]['terms'])
        cross=next(r for r in group if r['evidence_design']=='CROSS_PARAGRAPH_ATTRIBUTES')
        units=cross['source_support_annotations']['support_units']
        assert len(units)==4 and '\n\n' in cross['text']
        target_start=cross['target_full_span']['start']
        assert all(u['span']['start']>target_start for u in units)
        assert len({cross['text'][:u['span']['start']].count('\n\n') for u in units})>=2
        implicit=next(r for r in group if r['evidence_design']=='IMPLICIT_ATTRIBUTE_POSITIVE')
        annotations=implicit['source_support_annotations']
        assert {'jurisdiction','temporal_status'} <= set(annotations['allowed_missing_attributes'])
        assert annotations['contradictions']==[]
        attrs=implicit['entity_constraints'][implicit['expected_entity_id']]
        assert all(value not in implicit['text'] for attr in ('jurisdiction','temporal_status') for value in attrs[attr])
        rival=next(r for r in group if r['stratum']=='neighbor_attribution_nil')
        assert rival['expected_entity_id'] is None
        assert len(rival['source_support_annotations']['support_units'])==4
        assert {u['entity_id'] for u in rival['source_support_annotations']['support_units']}=={'global:'+fid+'-b'}
        assert rival['source_support_annotations']['contradictions'][0]['attribute']=='scope'
    rows[0]['entity_constraints'].clear()
    assert rows[1]['entity_constraints']


def test_codepoint_spans_preserve_core_and_full_referents():
    for row in data.load_support_recovery_records(require_review=False):
        core,full=row['target_core_span'],row['target_full_span']
        assert row['text'][full['start']:full['end']]==row['target_surface']
        assert full['start']<=core['start']<core['end']<=full['end']
        if row['gold']['label']=='COMPOSITIONAL':
            assert full['end']>core['end'] and row['target_surface'].endswith('담당자')
        for unit in row['source_support_annotations']['support_units']:
            span=unit['span']
            assert row['text'][span['start']:span['end']]==unit['value']


def test_prior_source_family_and_lexical_exclusion_is_byte_auditable():
    proof=json.loads(data.EXCLUSION_FILE.read_text())
    assert proof['source_sha256']==data.SOURCE_SHA256
    assert proof['new_name_string_overlap_count']==0 and proof['collisions']==[]
    names=set(proof['new_lexical_names']); assert len(names)==60
    root=data.CASES_FILE.parents[3]
    prior=proof['tracked_json_yaml_source_files']
    assert len(prior)>=20
    assert {'eval/fixtures/evidence_efficiency/source_gold.json','eval/fixtures/routing_confirmation/source_gold.json'} <= {r['path']for r in prior}
    for row in prior:
        raw=(root/row['path']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==row['sha256']
        assert not any(name in raw.decode()for name in names)


@pytest.mark.parametrize('field',['event_id','document_id','parent_document_id'])
def test_duplicate_event_and_document_provenance_is_rejected(field):
    source=artifact();source['families'][1]['cases'][0][field]=source['families'][0]['cases'][0][field]
    with pytest.raises(ValueError,match='identities'):
        data.validate_source_artifact(source)


@pytest.mark.parametrize('mutation',['text','span','entity','split','omission','attribute_ownership','attribute_span','contradiction','family_reuse'])
def test_substantive_source_mutations_are_rejected(mutation):
    source=artifact();row=source['families'][0]['cases'][0]
    if mutation=='text':row['text']+='changed'
    elif mutation=='span':row['target_full_span']['start']+=1
    elif mutation=='entity':
        row['expected_entity_id']='global:sr26-family-02-a';row['gold']['entity_ref']=row['expected_entity_id']
    elif mutation=='split':source['families'][0]['evaluation_split']='development'
    elif mutation=='omission':row['source_support_annotations']['allowed_missing_attributes']=['jurisdiction']
    elif mutation=='attribute_ownership':row['source_support_annotations']['support_units'][0]['entity_id']='global:sr26-family-01-b'
    elif mutation=='attribute_span':row['source_support_annotations']['support_units'][0]['span']['start']+=1
    elif mutation=='contradiction':source['families'][0]['cases'][4]['source_support_annotations']['contradictions']=[]
    else:source['reuse_policy']='METHOD_SELECTION'
    with pytest.raises(ValueError):data.validate_source_artifact(source)


def test_source_bytes_and_independent_review_are_sealed(tmp_path):
    assert data.file_sha256(data.CASES_FILE)==data.SOURCE_SHA256
    assert data.file_sha256(data.EXCLUSION_FILE)==data.EXCLUSION_SHA256
    changed=tmp_path/'changed.json';changed.write_bytes(data.CASES_FILE.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='source/gold seal'):
        data.load_support_recovery_records(path=changed,require_review=False)
    with pytest.raises(ValueError,match='review is required'):
        data.load_support_recovery_records(review_path=tmp_path/'missing-review.json')
    with pytest.raises(ValueError,match='split'):
        data.load_support_recovery_records('test')
    if data.REVIEW_SHA256 is not None:
        rows=data.load_support_recovery_records()
        assert len(rows)==96
        assert all(r['source_provenance']['independent_ai_reviewed']for r in rows)


def sealed_test_review(tmp_path,monkeypatch,**updates):
    source=artifact()
    review=dict(schema_version=1,status='APPROVED',source_sha256=data.SOURCE_SHA256,
                reviewer='independent-test-reviewer',reviewed_case_ids=sorted(r['case_id']for f in source['families']for r in f['cases']),
                reviewed_before_resolver=True,reviewed_before_generation=True,human_verified=False,unresolved_disagreements=0)
    review.update(updates);path=tmp_path/'review.json';path.write_text(json.dumps(review))
    monkeypatch.setattr(data,'REVIEW_SHA256',data.file_sha256(path));return path


@pytest.mark.parametrize('mutation',['author','case_coverage','after_resolver','after_generation','human','disagreement'])
def test_resealed_review_still_requires_complete_independent_preinference_contract(tmp_path,monkeypatch,mutation):
    changes={'author':{'reviewer':artifact()['authored_by']},'case_coverage':{'reviewed_case_ids':[]},
             'after_resolver':{'reviewed_before_resolver':False},'after_generation':{'reviewed_before_generation':False},
             'human':{'human_verified':True},'disagreement':{'unresolved_disagreements':1}}[mutation]
    path=sealed_test_review(tmp_path,monkeypatch,**changes)
    with pytest.raises(ValueError,match='complete pre-inference'):
        data.load_support_recovery_records(review_path=path)


def test_reviewed_loader_contains_no_resolver_or_model_imports(tmp_path,monkeypatch):
    path=sealed_test_review(tmp_path,monkeypatch)
    assert len(data.load_support_recovery_records(review_path=path))==96
    parsed=ast.parse(Path(data.__file__).read_text())
    for node in ast.walk(parsed):
        if isinstance(node,ast.Import):
            assert all(n.name.split('.')[0]not in {'ktrf','eval','torch','transformers'}for n in node.names)
        if isinstance(node,ast.ImportFrom):
            assert node.module.split('.')[0]not in {'ktrf','eval','torch','transformers'}
