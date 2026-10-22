from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from eval import prepare_support_recovery as wrapper
from eval.hf_qa import canonical


def summaries():
    result={}
    for model in ('gemma12b','qwen27b'):
        result[model]={'experiment':'support_recovery','status':'COMPLETE','code_revision':'f'*40,
            'counts':{'request_count':512,'error_count':0,'missing_count':0,'malformed_count':0},
            'by_variant':{c:{'accepted_wrong_id':0,'accepted_correct_id':7,
                'usage':{'total_tokens':1000+i},
                'usage_observed_responses':{k:64 for k in ('prompt_tokens','completion_tokens','total_tokens')}} for i,c in enumerate(wrapper.CONDITIONS)}}
    return result


def test_selection_uses_both_models_wrong_first_then_correct_then_cost():
    data=summaries()
    one,two,three=wrapper.CONDITIONS[1:4]
    for model in data.values():
        model['by_variant'][one].update(accepted_correct_id=30,accepted_wrong_id=1)
        model['by_variant'][two].update(accepted_correct_id=20)
        model['by_variant'][three].update(accepted_correct_id=20)
    selected,ranking=wrapper.select_condition(data)
    assert selected==two
    assert ranking[-1]['condition']==one
    # Equal recall and token cost is deterministic in predeclared condition order.
    for model in data.values():model['by_variant'][three]['usage']['total_tokens']=0
    assert wrapper.select_condition(data)[0]==three


@pytest.mark.parametrize('change',[
    lambda d:d.pop('qwen27b'),
    lambda d:d['gemma12b'].update(status='INCOMPLETE'),
    lambda d:d['gemma12b']['counts'].update(missing_count=1),
    lambda d:d['gemma12b']['counts'].update(malformed_count=1),
    lambda d:d['qwen27b']['by_variant'].pop(wrapper.CONDITIONS[-1]),
    lambda d:d['gemma12b']['by_variant'][wrapper.CONDITIONS[1]]['usage_observed_responses'].update(total_tokens=63),
])
def test_selection_rejects_incomplete_or_changed_discovery(change):
    data=summaries();change(data)
    with pytest.raises(ValueError):wrapper.select_condition(data)


def test_finalize_filters_existing_prompts_and_binds_selection(tmp_path,monkeypatch):
    cases=[]
    for i in range(96):
        for condition in wrapper.CONDITIONS:
            cases.append({'case_id':str(i),'condition':condition,'user':'sealed source '+str(i),
                          'system':'sealed method '+condition})
    source={'source_sha256':'a'*64,'review_sha256':'b'*64}
    envelope={'protocol':{'conditions':list(wrapper.CONDITIONS),'comparisons':[]},
              'provenance':{'source':source},'requests':cases}
    token_sizes={m:{json.dumps([r['case_id'],r['condition']],separators=(',',':')):100+i
                    for i,r in enumerate(cases)} for m in ('gemma12b','qwen27b')}
    proof={'request_count':768,'conditions':list(wrapper.CONDITIONS),
           'envelope_sha256':hashlib.sha256(canonical(envelope)).hexdigest(),
           'models':{m:{'request_count':768,'overflow_count':0,'path':'/model'} for m in token_sizes}}
    manifest={'code_revision':'f'*40,'source':source,'experiments':{'support_recovery':proof},
              'actual_token_sizes_sha256':hashlib.sha256(canonical(token_sizes)).hexdigest()}
    root=tmp_path/'candidate';root.mkdir()
    for name,value in [('support_recovery.json',envelope),('manifest.json',manifest),('actual_token_sizes.json',token_sizes)]:
        (root/name).write_bytes(canonical(value))
    monkeypatch.setattr(wrapper,'validate_requests',lambda rows,protocol:rows)
    result,selection=wrapper.finalize_confirmation(root,summaries(),discovery_run_id='discovery',out_dir=tmp_path/'selected',
        frozen_envelope_sha256=proof['envelope_sha256'],frozen_token_sizes_sha256=manifest['actual_token_sizes_sha256'])
    chosen=json.loads((tmp_path/'selected/support_recovery.json').read_text())
    assert len(chosen['requests'])==192
    for row in chosen['requests']:
        assert row in envelope['requests']
    assert chosen['protocol']['conditions']==[wrapper.BASELINE,selection['selected_condition']]
    assert selection['fresh_source_sha256']==source['source_sha256']
    assert selection['fresh_review_sha256']==source['review_sha256']
    assert selection['discovery_code_revision']=='f'*40
    assert not selection['selection_uses_confirmation_outputs'] and selection['selected_before_confirmation']
    assert result['total_planned_model_calls']==384
    assert all(v['request_count']==192 for v in result['experiments']['support_recovery']['models'].values())
    (root/'actual_token_sizes.json').write_bytes(b'{}')
    with pytest.raises(ValueError,match='token sizes'):
        wrapper.finalize_confirmation(root,summaries(),discovery_run_id='discovery',out_dir=tmp_path/'bad',
            frozen_envelope_sha256=proof['envelope_sha256'],frozen_token_sizes_sha256=manifest['actual_token_sizes_sha256'])


def test_real_sealed_discovery_and_fresh_matrices_are_frozen_before_selection(tmp_path,monkeypatch):
    from eval import evidence_efficiency_data as old, support_recovery_data as fresh
    from test_evidence_efficiency import FixtureTokenizer
    config={'models':{m:{'path':'unit-fixture','revision':'unit'} for m in ('gemma12b','qwen27b')}}
    for prefix,source,review in [('discovery',old.CASES_FILE,old.REVIEW_FILE),('confirmation',fresh.CASES_FILE,fresh.REVIEW_FILE)]:
        config[prefix+'_source_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
        config[prefix+'_review_sha256']=hashlib.sha256(review.read_bytes()).hexdigest()
    monkeypatch.setattr(wrapper,'load_tokenizers',lambda models:{m:FixtureTokenizer() for m in models})
    prepared=wrapper.prepare(config,tmp_path/'prepared',code_revision='f'*40)
    assert prepared['phases']['discovery']['experiments']['support_recovery']['request_count']==512
    assert prepared['phases']['confirmation_candidates']['experiments']['support_recovery']['request_count']==768
    assert prepared['phases']['confirmation_candidates']['source']['evaluation_population']=='FRESH_AI_AUTHORED_CONFIRMATION'
    assert prepared['phases']['confirmation_candidates']['total_planned_model_calls']==0
    manifest,selection=wrapper.finalize_confirmation(tmp_path/'prepared/confirmation_candidates',summaries(),
        discovery_run_id='discovery',out_dir=tmp_path/'selected',
        frozen_envelope_sha256=prepared['phases']['confirmation_candidates']['experiments']['support_recovery']['envelope_sha256'],
        frozen_token_sizes_sha256=prepared['phases']['confirmation_candidates']['actual_token_sizes_sha256'])
    assert manifest['experiments']['support_recovery']['request_count']==192
    envelope=json.loads((tmp_path/'selected/support_recovery.json').read_text())
    assert len({r['family_id'] for r in envelope['requests']})==12
    assert all(r['evaluation_only'] and r['execution_authority']=='none' for r in envelope['requests'])
    assert 'source_support_annotations' not in ''.join(r['system']+r['user'] for r in envelope['requests'])
