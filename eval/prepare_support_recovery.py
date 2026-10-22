"""Freeze discovery and all fresh candidate methods, then select without fresh outputs."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re

from .collect_hf_qa_queue import validate_public_json
from .evidence_efficiency_data import CASES_FILE as DISCOVERY_FILE, REVIEW_FILE as DISCOVERY_REVIEW, load_evidence_efficiency_records
from .hf_qa import canonical
from .prepare_followup import load_tokenizers, _token_ids
from .routing_confirmation import records_sha256, RESERVED_OUTPUT_TOKENS
from .support_recovery import CONDITIONS, prepare_support_recovery
from .run_extended_suite import validate_requests

BASELINE = 'paragraph_all_production'
SELECTION_RULE = 'minimum_wrong_then_maximum_correct_then_lower_token_cost_v1'


def _source(records, source_file, review_file, *, fresh):
    review = json.loads(review_file.read_text())
    digest = records_sha256(records)
    if (len(review['reviewed_case_ids']) != len(records)
            or set(review['reviewed_case_ids']) != {r['case_id'] for r in records}
            or review['reviewed_before_resolver'] is not True):
        raise ValueError('complete independent source-first AI review required')
    return {
        'kind': 'fresh_ai_authored_support_recovery' if fresh else 'reused_ai_authored_evidence_efficiency',
        'evaluation_population': 'FRESH_AI_AUTHORED_CONFIRMATION' if fresh else 'REUSED_SEALED_SOURCE_DIAGNOSTIC',
        'source_sha256': hashlib.sha256(source_file.read_bytes()).hexdigest(),
        'review_sha256': hashlib.sha256(review_file.read_bytes()).hexdigest(),
        'records_sha256': digest, 'source_gold_before_resolver': True,
        'human_verified': False, 'private_workplace_distribution_measured': False,
        'independent_validation': False, 'reused_source': not fresh,
        'independent_ai_review': {'reviewer': review['reviewer'], 'cases_reviewed': len(records),
            'resolved_before_resolver': True, 'records_sha256': digest},
    }


def prepare(config, out_dir, *, code_revision):
    if not re.fullmatch('[0-9a-f]{40}', code_revision):
        raise ValueError('immutable code revision required')
    if set(config['models']) != {'gemma12b', 'qwen27b'}:
        raise ValueError('both frozen checkpoints required')
    from .support_recovery_data import CASES_FILE, REVIEW_FILE, load_support_recovery_records
    # Both source artifacts are sealed and independently reviewed before ANY
    # resolver/tokenizer access, including the heldout corpus.
    discovery = load_evidence_efficiency_records()
    fresh = load_support_recovery_records()
    materials = [('discovery', discovery, DISCOVERY_FILE, DISCOVERY_REVIEW, False),
                 ('confirmation_candidates', fresh, CASES_FILE, REVIEW_FILE, True)]
    for phase, records, source_file, review_file, is_fresh in materials:
        prefix = 'confirmation' if is_fresh else 'discovery'
        for label, path in (('source', source_file), ('review', review_file)):
            if config.get(prefix + '_' + label + '_sha256') != hashlib.sha256(path.read_bytes()).hexdigest():
                raise ValueError('source or review changed after selection: ' + prefix)
        if len(records) != (96 if is_fresh else 64):
            raise ValueError('complete declared source population required')
    # Family and lexical exclusion is also independently audited by fresh loader.
    if {r['family_id'] for r in discovery} & {r['family_id'] for r in fresh}:
        raise ValueError('discovery and final confirmation families overlap')
    root = Path(out_dir)
    root.mkdir(parents=True, mode=0o700, exist_ok=False)
    tokenizers = load_tokenizers(config['models'])
    manifest = {'phase': 'ALL_METHODS_FROZEN_BEFORE_DISCOVERY', 'code_revision': code_revision,
                'methods': list(CONDITIONS), 'baseline_condition': BASELINE,
                'selection_rule': SELECTION_RULE, 'real_business_shadow_status': 'WAITING_FOR_INPUT',
                'phases': {}}
    for phase, records, source_file, review_file, is_fresh in materials:
        source = _source(records, source_file, review_file, fresh=is_fresh)
        envelope, proof = prepare_support_recovery(records=records, tokenizers=tokenizers,
            models=config['models'], code_revision=code_revision, source_provenance=source,
            conditions=CONDITIONS)
        rows = validate_requests(envelope['requests'], envelope['protocol'])
        if len(rows) != len(records) * 8:
            raise ValueError('full eight-method source matrix required')
        target = root / phase
        target.mkdir(mode=0o700)
        proof.update(file='support_recovery.json', request_count=len(rows),
            requests_sha256=hashlib.sha256(b''.join(canonical(r) for r in rows)).hexdigest(),
            envelope_sha256=hashlib.sha256(canonical(envelope)).hexdigest())
        sizes = {}
        for name, tokenizer in tokenizers.items():
            sizes[name] = {json.dumps([r['case_id'], r['condition']], separators=(',', ':')):
                len(_token_ids(tokenizer.apply_chat_template(
                    [{'role':'system','content':r['system']},{'role':'user','content':r['user']}],
                    tokenize=True,add_generation_prompt=True,enable_thinking=False,return_dict=False)))
                for r in rows}
        tokens = canonical(sizes)
        local_manifest = {'phase':'FINAL_FROZEN','code_revision':code_revision,'source':source,
            'experiments':{'support_recovery':proof},
            'total_planned_model_calls':0 if is_fresh else 1024,
            'precomputed_candidate_calls_not_all_scheduled':1536 if is_fresh else 0,
            'actual_token_sizes_sha256':hashlib.sha256(tokens).hexdigest(),
            'real_business_shadow_status':'WAITING_FOR_INPUT',
            'raw_request_envelopes_and_individual_answers_remain_private':True,
            'all_methods_frozen_before_discovery_outputs':True}
        validate_public_json(local_manifest)
        (target/'support_recovery.json').write_bytes(canonical(envelope))
        (target/'manifest.json').write_bytes(canonical(local_manifest))
        (target/'actual_token_sizes.json').write_bytes(tokens)
        manifest['phases'][phase] = local_manifest
    validate_public_json(manifest)
    (root/'manifest.json').write_bytes(canonical(manifest))
    return manifest


def select_condition(summaries):
    """One predeclared joint-model rule on discovery aggregates only."""
    if set(summaries) != {'gemma12b','qwen27b'}:
        raise ValueError('both discovery models required')
    for summary in summaries.values():
        if (summary.get('experiment') != 'support_recovery' or summary.get('status') != 'COMPLETE'
                or set(summary.get('by_variant',{})) != set(CONDITIONS)
                or summary.get('counts',{}).get('request_count') != 512):
            raise ValueError('complete eight-arm discovery aggregates required')
        if any(summary['counts'].get(k) != 0 for k in ('error_count','missing_count','malformed_count')):
            raise ValueError('discovery errors must be resolved before method selection')
        for values in summary['by_variant'].values():
            observed=values.get('usage_observed_responses',{})
            if any(observed.get(key)!=64 for key in ('prompt_tokens','completion_tokens','total_tokens')):
                raise ValueError('complete per-condition usage observations required for cost selection')
    ranked = []
    for index, condition in enumerate(CONDITIONS):
        if condition == BASELINE:
            continue
        values = [d['by_variant'][condition] for d in summaries.values()]
        wrong = sum(v['accepted_wrong_id'] for v in values)
        correct = sum(v['accepted_correct_id'] for v in values)
        tokens = sum(v['usage']['total_tokens'] for v in values)
        ranked.append({'condition':condition,'wrong_approvals':wrong,'correct_approvals':correct,
                       'total_tokens':tokens,'tie_break_order':index})
    ranked.sort(key=lambda v:(v['wrong_approvals'],-v['correct_approvals'],v['total_tokens'],v['tie_break_order']))
    return ranked[0]['condition'], ranked


def finalize_confirmation(candidates_dir, summaries, *, discovery_run_id, out_dir,
                          frozen_envelope_sha256, frozen_token_sizes_sha256):
    """Filter already frozen prompts; never resolve/rewrite fresh source after selection."""
    root=Path(candidates_dir)
    original=json.loads((root/'support_recovery.json').read_text())
    original_manifest=json.loads((root/'manifest.json').read_text())
    original_proof=original_manifest['experiments']['support_recovery']
    if (original_proof['envelope_sha256']!=frozen_envelope_sha256
            or hashlib.sha256(canonical(original)).hexdigest()!=frozen_envelope_sha256):
        raise ValueError('frozen fresh candidate envelope changed')
    sizes_raw=(root/'actual_token_sizes.json').read_bytes()
    if (original_manifest['actual_token_sizes_sha256']!=frozen_token_sizes_sha256
            or hashlib.sha256(sizes_raw).hexdigest()!=frozen_token_sizes_sha256):
        raise ValueError('actual token sizes changed after preparation')
    validate_requests(original['requests'],original['protocol'])
    selected,ranking=select_condition(summaries)
    revisions={d.get('code_revision') for d in summaries.values()}
    if len(revisions)!=1 or not re.fullmatch('[0-9a-f]{40}',next(iter(revisions)) or ''):
        raise ValueError('one frozen discovery code revision required')
    conditions=[BASELINE,selected]
    envelope=deepcopy(original)
    envelope['protocol']['conditions']=conditions
    envelope['protocol']['comparisons']=[[BASELINE,selected]]
    envelope['requests']=[r for r in envelope['requests'] if r['condition'] in conditions]
    validate_requests(envelope['requests'],envelope['protocol'])
    if len(envelope['requests'])!=192 or len({r['case_id'] for r in envelope['requests']})!=96:
        raise ValueError('96 fresh cases and two selected arms required')
    source=envelope['provenance']['source']
    selection={'kind':'ktrf_support_method_selection_v1','phase':'FINAL_FROZEN',
        'discovery_run_id':discovery_run_id,'discovery_code_revision':next(iter(revisions)),
        'baseline_condition':BASELINE,'selected_condition':selected,
        'fresh_source_sha256':source['source_sha256'],'fresh_review_sha256':source['review_sha256'],
        'selected_before_confirmation':True,'selection_uses_confirmation_outputs':False,
        'selection_rule':SELECTION_RULE,'ranking':ranking,'evaluation_only':True,'real_execution':False,
        'discovery_summary_sha256':{k:hashlib.sha256(canonical(v)).hexdigest() for k,v in summaries.items()},
        'all_fresh_method_envelope_sha256':frozen_envelope_sha256,
        'all_fresh_token_sizes_sha256':frozen_token_sizes_sha256}
    proof=deepcopy(original_proof)
    proof.update(request_count=192,conditions=conditions,
        requests_sha256=hashlib.sha256(b''.join(canonical(r) for r in envelope['requests'])).hexdigest(),
        envelope_sha256=hashlib.sha256(canonical(envelope)).hexdigest())
    all_sizes=json.loads(sizes_raw)
    for model, values in proof['models'].items():
        counts=[all_sizes[model][json.dumps([r['case_id'],r['condition']],separators=(',',':'))]
                for r in envelope['requests']]
        values.update(request_count=192,max_prompt_tokens=max(counts),max_input_tokens=max(counts),
                      sum_input_tokens=sum(counts),reserved_output_tokens=RESERVED_OUTPUT_TOKENS,
                      by_condition={c:{'request_count':96,'sum_input_tokens':sum(n for r,n in zip(envelope['requests'],counts) if r['condition']==c)} for c in conditions})
    manifest={**original_manifest,'experiments':{'support_recovery':proof},
        'total_planned_model_calls':384,'selected_conditions':conditions,
        'selected_from_precomputed_prompts':True,'selection':selection,
        'all_methods_frozen_before_discovery_outputs':True}
    for obj in (selection,manifest):validate_public_json(obj)
    target=Path(out_dir);target.mkdir(mode=0o700,parents=True,exist_ok=False)
    (target/'support_recovery.json').write_bytes(canonical(envelope))
    (target/'manifest.json').write_bytes(canonical(manifest))
    (target/'selection.json').write_bytes(canonical(selection))
    return manifest,selection


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--code-revision',required=True);a=p.parse_args();os.umask(0o077)
    result=prepare(json.loads(a.config.read_text()),a.out_dir,code_revision=a.code_revision)
    print(json.dumps({'phase':result['phase'],'discovery_calls':1024,'final_confirmation_calls':384}))


if __name__=='__main__':main()
