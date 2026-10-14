"""Verify definition-format controls and report literal-normalized QA separately."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from eval.definition_control import CONDITIONS, PROTOCOL, grade_outputs, validate_requests
from eval.production_grounding import TASKS, production_response_error
from eval.report_production_grounding import _operational
from eval.report_synthetic_grounding import ARTIFACTS, _json_bytes


def prepare_report(run_dir, *, compare=None):
    root = Path(run_dir)
    manifest = json.loads((root/'run_manifest.json').read_text())
    unsealed = dict(manifest)
    seal = unsealed.pop('seal_sha256', None)
    if hashlib.sha256(_json_bytes(unsealed)).hexdigest() != seal:
        raise ValueError('invalid manifest seal')
    if (manifest.get('track') != 'definition_control' or manifest.get('protocol') != PROTOCOL['kind']
            or manifest.get('declared_protocol') != PROTOCOL):
        raise ValueError('definition control protocol mismatch')
    blobs = {name: (root/name).read_bytes() for name in ARTIFACTS}
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in blobs.items()}
    if manifest.get('artifact_sha256') != hashes or manifest.get('request_corpus_sha256') != hashes['requests.jsonl']:
        raise ValueError('sealed artifact hash mismatch')
    rows = [json.loads(line) for line in blobs['requests.jsonl'].splitlines() if line.strip()]
    records = [json.loads(line) for line in blobs['responses.jsonl'].splitlines() if line.strip()]
    validate_requests(rows, check_current_policy=False)
    by_document = defaultdict(list)
    known = {(row['case_id'], row['condition']): row for row in rows}
    for row in rows:
        by_document[row['document_id']].append(row)
    for group in by_document.values():
        if {(row['condition'], row['task']) for row in group} != {(c, t) for c in CONDITIONS for t in TASKS}:
            raise ValueError('incomplete condition/task matrix')
    seen = set()
    for record in records:
        key = record['case_id'], record['condition']
        if key not in known or key in seen:
            raise ValueError('unknown or duplicate response')
        seen.add(key)
        status = record.get('status')
        if status not in {'RECEIVED', 'MALFORMED', 'HTTP_ERROR', 'TRANSPORT_ERROR'}:
            raise ValueError('unknown response status')
        if ('response' in record) != (status in {'RECEIVED', 'MALFORMED'}):
            raise ValueError('response/status mismatch')
        if 'response' in record and not isinstance(record['response'], dict):
            raise ValueError('response must be a JSON object')
        if status == 'RECEIVED' and production_response_error(record['response'], known[key]) is not None:
            raise ValueError('received response violates schema')
        if (record.get('error') is not None) != (status in {'HTTP_ERROR', 'TRANSPORT_ERROR'}):
            raise ValueError('transport error/status mismatch')
    counts = {'request_count': len(rows), 'received_count': sum('response' in r for r in records),
              'error_count': sum(r.get('error') is not None for r in records),
              'malformed_count': sum(r['status'] == 'MALFORMED' for r in records)}
    counts['missing_count'] = len(rows) - counts['received_count']
    if any(manifest.get(k) != v for k, v in counts.items()):
        raise ValueError('manifest counts disagree')
    status = 'COMPLETE' if counts['missing_count'] == counts['error_count'] == 0 else 'INCOMPLETE'
    if manifest.get('status') != status:
        raise ValueError('manifest completion status disagrees')
    graded = grade_outputs(rows, [r for r in records if 'response' in r])
    graded['limitations'] = list(PROTOCOL['limitations'])
    if json.loads(blobs['graded.json'])['model_results'] != graded:
        raise ValueError('frozen regrading differs')
    summary = {'kind': 'sealed_definition_control_report', 'status': status,
               **{k: manifest.get(k) for k in ('track', 'protocol', 'declared_protocol', 'code_revision',
                    'requested_model', 'decoding', 'request_provenance', 'request_corpus_sha256')},
               'verified_manifest_seal_sha256': seal, 'verified_artifact_sha256': hashes,
               'counts': {**counts, 'documents': len(by_document)}, 'metrics': graded,
               'operational': {c: {t: _operational([r for r in rows if r['condition']==c and r['task']==t], records)
                                   for t in TASKS} for c in CONDITIONS},
               'limitations': list(PROTOCOL['limitations'])}
    summary['contrasts'] = _contrasts(graded['cases'])
    if compare is not None:
        baseline = prepare_report(compare)
        if any(summary[k] != baseline[k] for k in ('request_corpus_sha256', 'decoding', 'declared_protocol')):
            raise ValueError('model comparison requires identical input and decoding')
        summary['comparison'] = {'baseline_model': baseline['requested_model'],
                                  'baseline_metrics': baseline['metrics']}
    return summary


def _contrasts(cases):
    result = {}
    for old, new in (("prose_all", "cards_all"), ("cards_all", "cards_retrieved"),
                     ("cards_all", "ktrf_qa_cards"),
                     ("ktrf_execution_cards", "ktrf_contextual_execution_cards")):
        by_task = {}
        for task in TASKS:
            left = {c['case_id']: c for c in cases if c['condition']==old and c['task']==task}
            right = {c['case_id']: c for c in cases if c['condition']==new and c['task']==task}
            if set(left) != set(right):
                raise ValueError('paired controls differ in case identities')
            observed = sorted(k for k in left if not left[k]['missing'] and not right[k]['missing'])
            by_task[task] = {'planned': len(left), 'comparable': len(observed),
                **{metric: {'helpful_case_ids': [k for k in observed if not left[k][metric] and right[k][metric]],
                            'harmful_case_ids': [k for k in observed if left[k][metric] and not right[k][metric]]}
                   for metric in ('exact_match', 'semantic_match', 'operational_correct')}}
        result[old+'__to__'+new] = by_task
    return result


def render_markdown(summary):
    lines = ['# Definition format and contextual evidence controls', '',
             f"Status: **{summary['status']}**. Model: `{summary['requested_model']}`. "
             f"{summary['counts']['received_count']}/{summary['counts']['request_count']} responses.", '',
             'Exact output matching and conservative literal-normalized QA are distinct. '
             'UNASSESSED needs review; definition containment never earns automatic credit.', '',
             '| Condition | Task | Exact / planned | Normalized / planned | Unassessed | Positive null | Malformed | Missing |',
             '|---|---|---:|---:|---:|---:|---:|---:|']
    for condition, scores in summary['metrics']['by_condition'].items():
        for task, values in scores['by_task'].items():
            n=values['planned']
            lines.append(f"| {condition} | {task} | {values['exact_match']}/{n} | "
                         f"{values['semantic_match']}/{n} | {values['semantic_unassessed']} | "
                         f"{values['positive_null']} | {values['malformed']} | {values['missing']} |")
    lines += ['', '## Source collections', '',
              'Previously inspected contextual documents and fresh explicit-definition cases remain separate.', '',
              '| Condition | Collection | Task | Exact / planned | Normalized / planned |',
              '|---|---|---|---:|---:|']
    for condition,scores in summary['metrics']['by_condition'].items():
        for collection,tasks in scores['by_collection'].items():
            for task,values in tasks.items():
                lines.append(f"| {condition} | {collection} | {task} | {values['exact_match']}/{values['planned']} | "
                             f"{values['semantic_match']}/{values['planned']} |")
    lines += ['', '## Routing acceptance', '',
              'Neutral arms validate supplied-ID membership for proposals. Production arms use their execution guard.', '',
              '| Condition | Accepted correct ID | Accepted wrong ID | Positive candidate / targets |',
              '|---|---:|---:|---:|']
    for condition,scores in summary['metrics']['by_condition'].items():
        cases=[c for c in summary['metrics']['cases'] if c['condition']==condition and c['task']=='structured_routing']
        correct=sum(not c['missing'] and bool(c.get('nonnull')) and bool(c.get('operational_valid')) and c['exact_match'] for c in cases)
        wrong=sum(bool(c.get('accepted_wrong_id')) for c in cases)
        values=scores['by_task']['structured_routing']
        lines.append(f"| {condition} | {correct} | {wrong} | {values['candidate_recall']}/{values['positive_gold']} |")
    lines += ['', '## Paired changes', '',
              '| Contrast | Task | Metric | Comparable | Helped | Harmed |', '|---|---|---|---:|---:|---:|']
    for contrast,tasks in summary['contrasts'].items():
        for task,values in tasks.items():
            for metric in ('exact_match','semantic_match','operational_correct'):
                change=values[metric]
                lines.append(f"| {contrast} | {task} | {metric} | {values['comparable']} | "
                             f"{len(change['helpful_case_ids'])} | {len(change['harmful_case_ids'])} |")
    lines += ['', '## Definition availability', '',
              'Catalog/card exposure and full model-input exposure are separate; source text can itself contain a definition.', '',
              '| Condition | Task | Catalog definition / positive | Definition in model input / positive |',
              '|---|---|---:|---:|']
    for condition,scores in summary['metrics']['by_condition'].items():
        for task,values in scores['by_task'].items():
            lines.append(f"| {condition} | {task} | {values['catalog_definition_visible']}/{values['positive_gold']} | "
                         f"{values['definition_visible_in_model_input']}/{values['positive_gold']} |")
    lines += ['', '## Costs', '', '| Condition | Task | Prompt tokens | p95 latency ms |', '|---|---|---:|---:|']
    for condition,tasks in summary['operational'].items():
        for task,values in tasks.items():
            lines.append(f"| {condition} | {task} | {values['actual_usage']['prompt_tokens']['total']} | {values['latency_ms']['p95']} |")
    lines += ['', '## Limitations', '', *['- '+s for s in summary['limitations']], '']
    if 'comparison' in summary:
        lines += ['', f"Matched model comparison with `{summary['comparison']['baseline_model']}`; "
                      'model family and size both change.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--compare', type=Path)
    args = parser.parse_args()
    summary = prepare_report(args.run_dir, compare=args.compare)
    (args.run_dir/'summary.json').write_bytes(_json_bytes(summary))
    (args.run_dir/'RESULTS.md').write_text(render_markdown(summary))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
