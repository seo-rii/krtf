from copy import deepcopy
import hashlib,json
from pathlib import Path
import pytest
from eval import prepare_evidence_closure as wrapper


def source_config():
    from eval import evidence_closure_data as source
    return {'models':{m:{'path':'fixture','revision':'unit'} for m in ('gemma12b','qwen27b')},
        'source_sha256':hashlib.sha256(source.CASES_FILE.read_bytes()).hexdigest(),
        'review_sha256':hashlib.sha256(source.REVIEW_FILE.read_bytes()).hexdigest()}


@pytest.mark.parametrize('mutation',[
    lambda c:c.update(source_sha256='0'*64),lambda c:c.update(review_sha256='0'*64),
    lambda c:c['models'].pop('qwen27b'),
])
def test_prepare_rejects_changed_seals_or_model_pairs(tmp_path,mutation):
    cfg=source_config();mutation(cfg)
    with pytest.raises(ValueError):wrapper.prepare(cfg,tmp_path/'out',code_revision='f'*40)


def test_prepare_fresh_complete_matrix_and_no_annotation_prompt_leak(tmp_path,monkeypatch):
    from test_evidence_efficiency import FixtureTokenizer
    cfg=source_config()
    monkeypatch.setattr(wrapper,'load_tokenizers',lambda models:{m:FixtureTokenizer() for m in models})
    result=wrapper.prepare(cfg,tmp_path/'out',code_revision='f'*40)
    assert result['total_planned_model_calls']==960
    assert result['document_length_band_case_counts']=={'long':48,'short':48}
    assert result['experiments']['evidence_closure']['request_count']==480
    envelope=json.loads((tmp_path/'out/evidence_closure.json').read_text())
    assert len({r['family_id'] for r in envelope['requests']})==12
    for row in envelope['requests']:
        assert row['text'] in row['user']
        assert 'source_support_annotations' not in row['system']+row['user']
        assert row['evaluation_only'] and row['execution_authority']=='none'
