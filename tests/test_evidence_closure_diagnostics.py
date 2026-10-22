from copy import deepcopy
import pytest
from eval.evidence_closure_diagnostics import replay_response
from tests.test_support_recovery import prepare,row_for,response


def fixture():
    return row_for(prepare(),'multispan_supported_shadow')


def test_target_and_attribute_parent_closure_changes_only_references():
    row=fixture();answer=response(row);answer['selections'][0]['q']=[]
    original,_=replay_response(answer,row)
    result,meta=replay_response(answer,row,closure=True)
    assert not original['accepted_correct_id']
    assert result['accepted_correct_id'] and not result['accepted_wrong_id']
    assert meta['server_added_segments']
    assert answer['selections'][0]['q']==[]


def test_null_projection_is_explicit_posthoc_and_never_makes_nonnull():
    row=fixture();answer=response(row,eid=None)
    answer['selections'][0]['q']=[row['support_inventory']['segments'][0]['segment_alias']]
    result,meta=replay_response(answer,row,null_projection=True)
    assert result['proposal_abstention'] and not result['accepted_correct_id']
    assert meta['null_projected']


def test_forged_request_is_never_restored():
    row=fixture();answer=response(row);answer['selections'][0]['r']='foreign-request'
    for closure in (False,True):
        result,_=replay_response(answer,row,closure=closure)
        assert not result['wire_valid'] and not result['accepted_correct_id']


def test_foreign_reference_is_retained_and_rejected():
    row=fixture();answer=response(row);answer['selections'][0]['q'].append('foreign-evidence')
    result,_=replay_response(answer,row,closure=True)
    assert not result['accepted_correct_id']
    assert any(v['kind']=='unknown_or_stale_evidence_reference' for v in result['guard_violations'])
