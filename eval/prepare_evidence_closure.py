"""Seal source-first balanced/long documents and a five-arm closure benchmark."""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import hashlib
import json
import os
from pathlib import Path
import re

from .collect_hf_qa_queue import validate_public_json
from .hf_qa import canonical
from .prepare_followup import load_tokenizers
from .routing_confirmation import records_sha256
from .run_extended_suite import validate_requests


def prepare(config,out_dir,*,code_revision):
    from .evidence_closure_data import CASES_FILE,REVIEW_FILE,load_evidence_closure_records
    from .evidence_closure import CONDITIONS,prepare_evidence_closure
    if not re.fullmatch('[0-9a-f]{40}',code_revision):raise ValueError('immutable code revision required')
    if set(config['models'])!={'gemma12b','qwen27b'}:raise ValueError('both frozen checkpoint tokenizers required')
    source_hash=hashlib.sha256(CASES_FILE.read_bytes()).hexdigest()
    review_hash=hashlib.sha256(REVIEW_FILE.read_bytes()).hexdigest()
    if config.get('source_sha256')!=source_hash or config.get('review_sha256')!=review_hash:
        raise ValueError('source or independent review changed after selection')
    records=load_evidence_closure_records()
    if len(records)!=96 or len({r['family_id'] for r in records})!=12 or len({r['case_id'] for r in records})!=96:
        raise ValueError('complete96document12family corpus required')
    if Counter(r['document_length_band'] for r in records)!={'short':48,'long':48}:
        raise ValueError('balanced short and long source groups required')
    if any(r['evaluation_split']!='confirmation' for r in records):raise ValueError('all sources final confirmation only')
    review=json.loads(REVIEW_FILE.read_text())
    if (set(review['reviewed_case_ids'])!={r['case_id'] for r in records}
            or len(review['reviewed_case_ids'])!=96 or review['reviewed_before_resolver'] is not True):
        raise ValueError('all source cases require independent source-first review')
    digest=records_sha256(records)
    source={'kind':'fresh_ai_authored_evidence_closure','evaluation_population':'FRESH_AI_AUTHORED_CONFIRMATION',
        'source_sha256':source_hash,'review_sha256':review_hash,'records_sha256':digest,
        'source_gold_before_resolver':True,'human_verified':False,'private_workplace_distribution_measured':False,
        'independent_validation':False,'reused_source':False,
        'independent_ai_review':{'reviewer':review['reviewer'],'cases_reviewed':96,'resolved_before_resolver':True,'records_sha256':digest}}
    envelope,proof=prepare_evidence_closure(records=records,tokenizers=load_tokenizers(config['models']),
        models=config['models'],code_revision=code_revision,source_provenance=source)
    rows=validate_requests(envelope['requests'],envelope['protocol']);groups=defaultdict(list)
    originals={r['case_id']:r for r in records}
    for row in rows:
        original=originals[row['case_id']]
        if any(row.get(k)!=original[k] for k in ('text','document_sha256','gold','expected_entity_id','family_id','target_core_span','target_full_span','document_length_band')):
            raise ValueError('source or gold changed across conditions')
        groups[row['case_id']].append(row)
    if len(rows)!=480 or set(groups)!=set(originals) or any({r['condition'] for r in group}!=set(CONDITIONS) or len(group)!=5 for group in groups.values()):
        raise ValueError('complete96sourcefivecondition matrix required')
    proof.update(file='evidence_closure.json',request_count=480,
        requests_sha256=hashlib.sha256(b''.join(canonical(r) for r in rows)).hexdigest(),
        envelope_sha256=hashlib.sha256(canonical(envelope)).hexdigest())
    manifest={'phase':'FINAL_FROZEN','code_revision':code_revision,'source':source,
        'experiments':{'evidence_closure':proof},'total_planned_model_calls':960,
        'document_length_band_case_counts':dict(Counter(r['document_length_band'] for r in records)),
        'raw_request_envelopes_and_individual_answers_remain_private':True,
        'real_business_shadow_status':'WAITING_FOR_INPUT','evaluation_only':True,'execution_authority':'none'}
    validate_public_json(manifest);root=Path(out_dir);root.mkdir(parents=True,mode=0o700,exist_ok=False)
    (root/'evidence_closure.json').write_bytes(canonical(envelope));(root/'manifest.json').write_bytes(canonical(manifest))
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--code-revision',required=True)
    a=p.parse_args();os.umask(0o077);result=prepare(json.loads(a.config.read_text()),a.out_dir,code_revision=a.code_revision)
    print(json.dumps({'phase':result['phase'],'total_planned_model_calls':960}))

if __name__=='__main__':main()
