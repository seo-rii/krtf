"""Post-hoc CPU replay of source-reference closure and null-only transport.

These deterministic projections diagnose headroom in previously inspected AI
cases. They are not new model calls, prospective results or execution approval.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path

from .hf_qa import canonical
from .report_extended_suite import read_run
from .support_recovery import grade_support_recovery_response, support_recovery_response_error

VARIANTS = ('original', 'server_closure', 'null_projection', 'closure_and_null')


def replay_response(response, row, *, closure=False, null_projection=False):
    from .evidence_closure import closure_for_support_response
    changed=deepcopy(response)
    metadata={'server_added_segments':[], 'null_projected':False}
    # This is explicitly a hypothetical format projection, NOT accepting a
    # malformed original reply as an operational instruction.
    if support_recovery_response_error(changed,row) is None:
        selection=changed['selections'][0]
        if null_projection and selection['e'] is None:
            metadata['null_projected']=bool(selection['s']!='UNRESOLVED' or selection['q'] or selection['a'])
            changed={'selections':[{'r':selection['r'],'e':None,'s':'UNRESOLVED','q':[],'a':[]}]}
        if closure:
            changed,extra=closure_for_support_response(changed,row)
            metadata.update(extra)
    return grade_support_recovery_response(changed,row),metadata


def analyze_frozen_run(path):
    manifest,rows,responses,graded,counts=read_run(path)
    if manifest['experiment']!='support_recovery' or manifest['status']!='COMPLETE':
        raise ValueError('complete sealed support-recovery run required')
    selected=[r for r in rows if r['condition']=='multispan_supported_shadow']
    indexed={(r['case_id'],r['condition']):r for r in responses}
    output={};transitions={};breakdowns={}
    for name in VARIANTS:
        metrics=Counter();strata=defaultdict(Counter);changed_cases=0
        for row in selected:
            recorded=indexed[(row['case_id'],row['condition'])]
            if recorded['status']!='RECEIVED':raise ValueError('complete parsed original responses required')
            original=grade_support_recovery_response(recorded['response'],row)
            now,extra=replay_response(recorded['response'],row,closure=name in {'server_closure','closure_and_null'},
                                     null_projection=name in {'null_projection','closure_and_null'})
            for field in ('accepted_correct_id','accepted_wrong_id','correct_abstention','over_abstention',
                          'proposal_correct_id','proposal_wrong_id','proposal_abstention','wire_valid'):
                metrics[field]+=bool(now[field]);strata[row['stratum']][field]+=bool(now[field])
            metrics['server_added_segments']+=len(extra.get('server_added_segments',[]))
            metrics['null_projected_cases']+=bool(extra.get('null_projected'))
            changed_cases+=original!=now
            if name!='original':
                metrics['recovered_correct_id']+=bool(now['accepted_correct_id'] and not original['accepted_correct_id'])
                metrics['new_wrong_id']+=bool(now['accepted_wrong_id'] and not original['accepted_wrong_id'])
                metrics['lost_correct_id']+=bool(original['accepted_correct_id'] and not now['accepted_correct_id'])
        output[name]=dict(metrics)|{'case_count':len(selected),'positive_cases':sum(r['expected_entity_id'] is not None for r in selected)}
        transitions[name]={'cases_with_changed_grade':changed_cases}
        breakdowns[name]={s:dict(v) for s,v in sorted(strata.items())}
    return {'model':manifest['requested_model'],'code_revision':manifest['code_revision'],
        'replay_source_files_sha256':{name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
            for name in ('evidence_closure_diagnostics.py','evidence_closure.py','support_recovery.py')},
        'source_manifest_sha256':hashlib.sha256((Path(path)/'run_manifest.json').read_bytes()).hexdigest(),
        'frozen_request_file_sha256':manifest['frozen_request_file_sha256'],'sealed_regrade_counts':counts,
        'evaluation_population':'EXPOSED_POSTHOC_CPU_DIAGNOSTIC','new_inference_calls':0,
        'evaluation_only':True,'execution_authority':'none','independent_validation':False,
        'by_variant':output,'transitions':transitions,'by_stratum':breakdowns,
        'limitations':['Source documents and model responses have already been inspected; this replay is adaptive diagnostic only.',
            'Null projection removes assertion fields only for an existing null entity proposal; it never supplies a non-null entity.',
            'Server closure adds the requested occurrence and selected attribute parent segments without adding attributes or changing the selected entity.',
            'All ownership, source contradiction, structural and request checks remain; prospective generation may differ.']}


def render_markdown(results):
    lines=['# 근거 연결·기권 형식 CPU 재분석','',
        '기존96문서의 봉인된 원시 응답을 검증한 후, 같은 응답에 결정적 변환을 적용한 사후 진단이다.',
        '새 생성 결과나 운영 승인이 아니며, 아래 회복 수가 새 실험에서 재현된다고 가정하지 않는다.','',
        '| 모델 | 변환 | 정상 shadow 판정 | 잘못된 shadow 판정 | 정상 기권 | 추가 연결 회복 |',
        '|---|---|---:|---:|---:|---:|']
    for model,result in results.items():
        for name,v in result['by_variant'].items():
            lines.append(f"| {model} | {name} | {v['accepted_correct_id']}/{v['positive_cases']} | {v['accepted_wrong_id']} | {v['correct_abstention']} | {v.get('recovered_correct_id',0)} |")
    lines+=['','원시 응답과 기존 성적은 변경하지 않는다. 비어 있지 않은 잘못된 근거 참조를 삭제해',
        '오류를 숨기거나, 사전 속성을 원문 근거로 추가하거나, 잘못된 entity를 교체하지 않는다.','']
    return '\n'.join(lines)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gemma-run',type=Path,required=True);p.add_argument('--qwen-run',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
    results={m:analyze_frozen_run(path) for m,path in [('gemma12b',a.gemma_run),('qwen27b',a.qwen_run)]}
    from .collect_hf_qa_queue import validate_public_json
    validate_public_json(results);a.out_dir.mkdir(parents=True,exist_ok=False)
    (a.out_dir/'summary.json').write_bytes(canonical(results));(a.out_dir/'ANALYSIS.md').write_text(render_markdown(results))
    print(json.dumps({m:v['by_variant'] for m,v in results.items()},ensure_ascii=False))

if __name__=='__main__':main()
