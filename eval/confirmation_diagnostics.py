"""Reproduce posthoc routing attrition and conservative literal-offset diagnosis.

The original sealed runs and grades remain unchanged. Position repair is a
source-only counterfactual, never a new prospective result or execution grant.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from eval.collect_hf_qa_queue import validate_public_json
from eval.hf_qa import canonical
from eval.report_extended_suite import read_run
from eval.routing_confirmation import (
    ATTRIBUTES, CONDITIONS, MAX_EVIDENCE_CHARS,
    grade_confirmation_response,
)

STATUS = 'POSTHOC_DIAGNOSTIC'
METRICS = ('accepted_correct_id', 'accepted_wrong_id', 'rejected_correct_id',
           'rejected_wrong_id', 'correct_abstention', 'over_abstention')


def literal_positions(text, value):
    """Include overlapping matches so uniqueness cannot conceal a second match."""
    if not isinstance(value, str) or not value:
        return []
    result, start = [], 0
    while True:
        index = text.find(value, start)
        if index == -1:
            return result
        result.append(index)
        start = index + 1


def repair_literal_positions(response, *, text, target_full_span, target_surface):
    """Repair only positions from unique literals, without accepting gold inputs.

    The quote must be globally unique, in the requested target paragraph, and
    contain only that occurrence of the target surface. Each attribute value
    must occur exactly once inside that quote. Failure returns no edited output.
    The original wire, entity, assertion, literal values and all other checks
    are preserved and must still pass the original grader afterwards.
    """
    result = deepcopy(response)
    selections = result.get('selections') if isinstance(result, dict) else None
    if not isinstance(selections, list) or len(selections) != 1 or not isinstance(selections[0], dict):
        return None, 'selection_shape'
    selection = selections[0]
    if selection.get('entity_id') is None:
        return None, 'null_selection'
    assertion = selection.get('assertion')
    evidence = assertion.get('evidence') if isinstance(assertion, dict) else None
    if not isinstance(evidence, dict) or not isinstance(evidence.get('text'), str):
        return None, 'missing_quote'
    quote = evidence['text']
    if not 1 <= len(quote) <= MAX_EVIDENCE_CHARS:
        return None, 'quote_length'
    positions = literal_positions(text, quote)
    if len(positions) != 1:
        return None, 'quote_missing' if not positions else 'quote_not_unique'
    start, end = positions[0], positions[0] + len(quote)
    full = target_full_span
    if not (isinstance(full, dict) and set(full) == {'start', 'end'}
            and all(type(v) is int for v in full.values())
            and 0 <= full['start'] < full['end'] <= len(text)
            and text[full['start']:full['end']] == target_surface):
        return None, 'invalid_requested_occurrence'
    if not start <= full['start'] < full['end'] <= end:
        return None, 'quote_excludes_requested_occurrence'
    paragraph_start = text.rfind('\n', 0, full['start']) + 1
    paragraph_end = text.find('\n', full['end'])
    paragraph_end = len(text) if paragraph_end == -1 else paragraph_end
    if start < paragraph_start or end > paragraph_end:
        return None, 'quote_crosses_target_paragraph'
    if [start + offset for offset in literal_positions(quote, target_surface)] != [full['start']]:
        return None, 'quote_has_other_surface_occurrence'
    claims = assertion.get('attributes')
    if (not isinstance(claims, list) or len(claims) != len(ATTRIBUTES)
            or any(not isinstance(claim, dict) for claim in claims)
            or {claim.get('attribute') for claim in claims} != set(ATTRIBUTES)):
        return None, 'incomplete_attribute_claims'
    for claim in claims:
        matches = literal_positions(quote, claim.get('value'))
        if len(matches) != 1:
            return None, 'attribute_missing' if not matches else 'attribute_not_unique'
        claim['start'] = start + matches[0]
        claim['end'] = claim['start'] + len(claim['value'])
    evidence.update(start=start, end=end)
    return result, 'positions_reconstructed'


def _totals(grades):
    return {metric: sum(bool(grade[metric]) for grade in grades) for metric in METRICS}


def _evidence(rows, keyed):
    observations, outcomes, residual = Counter(), Counter(), Counter()
    original, repaired = [], []
    for row in rows:
        record = keyed.get((row['case_id'], row['condition']))
        if not record or record['status'] != 'RECEIVED':
            observations['not_received'] += 1
            continue
        response = record['response']
        grade = grade_confirmation_response(response, row)
        original.append(grade)
        selection = response['selections'][0]
        if selection['entity_id'] is None:
            continue
        observations['nonnull_proposals'] += 1
        observations['original_base_guard_valid'] += grade['base_guard_valid']
        evidence = selection['assertion']['evidence']
        if evidence is not None:
            observations['quote_present'] += 1
            quote, text = evidence['text'], row['text']
            positions = literal_positions(text, quote)
            observations['quote_verbatim_anywhere'] += bool(positions)
            observations['quote_unique_in_source'] += len(positions) == 1
            observations['original_quote_offsets_exact'] += (
                evidence['end'] <= len(text) and text[evidence['start']:evidence['end']] == quote)
            if len(positions) == 1:
                start, end = positions[0], positions[0] + len(quote)
                full = row['target_full_span']
                observations['unique_quote_contains_target'] += start <= full['start'] < full['end'] <= end
        # Only this four-field source projection enters the reconstruction.
        changed, outcome = repair_literal_positions(response, text=row['text'],
            target_full_span=row['target_full_span'], target_surface=row['target_surface'])
        outcomes[outcome] += 1
        if changed is None:
            continue
        observations['positions_reconstructed'] += 1
        diagnostic = grade_confirmation_response(changed, row)
        repaired.append(diagnostic)
        for violation in diagnostic['guard_violations']:
            residual[violation['kind']] += 1
    return {'scope': STATUS, 'planned_calls': len(rows),
        'observations': {key: observations[key] for key in (
            'not_received', 'nonnull_proposals', 'original_base_guard_valid', 'quote_present',
            'quote_verbatim_anywhere', 'quote_unique_in_source', 'original_quote_offsets_exact',
            'unique_quote_contains_target', 'positions_reconstructed')},
        'reconstruction_outcomes': dict(sorted(outcomes.items())),
        'original_scores_unchanged': _totals(original),
        'posthoc_reconstructed_nonnull_only': _totals(repaired),
        'remaining_original_guard_violations': dict(sorted(residual.items()))}


def _pipeline(rows, keyed):
    stages, missing_status, rejected_status, reasons, attrition = (Counter() for _ in range(5))
    for row in rows:
        if not row['positive_gold']:
            continue
        stages['positive_targets'] += 1
        trace, gold = row['pipeline_trace'], row['expected_entity_id']
        detected = trace['exact_core_detected']
        retrieved = gold in trace['candidate_entity_ids']
        offered = gold in row['offered_entity_ids']
        stages['exact_core_detected'] += detected
        stages['gold_retrieved'] += detected and retrieved
        stages['gold_offered'] += offered
        if not offered:
            missing_status[row['resolver_status']] += 1
        record = keyed.get((row['case_id'], row['condition']))
        grade = (grade_confirmation_response(record['response'], row)
                 if record and record['status'] == 'RECEIVED' else None)
        selected = record['response']['selections'][0]['entity_id'] if grade else None
        correct_proposal = grade is not None and selected == gold
        stages['model_correct_id'] += correct_proposal
        stages['model_correct_id_among_offered'] += offered and correct_proposal
        stages['approved_correct_id'] += bool(grade and grade['accepted_correct_id'])
        if correct_proposal and not grade['guard_valid']:
            rejected_status[row['resolver_status']] += 1
            reasons.update(v['kind'] for v in grade['guard_violations'])
        if not detected:
            loss = 'not_detected'
        elif not retrieved:
            loss = 'gold_not_retrieved'
        elif not offered:
            loss = 'retrieved_gold_not_offered'
        elif grade is None:
            loss = 'offered_no_valid_response'
        elif selected is None:
            loss = 'offered_model_abstained'
        elif not correct_proposal:
            loss = 'offered_model_wrong_id'
        elif not grade['guard_valid']:
            loss = 'offered_correct_id_rejected'
        else:
            loss = 'approved_correct_id'
        attrition[loss] += 1
    return {'stages': {key: stages[key] for key in ('positive_targets', 'exact_core_detected',
        'gold_retrieved', 'gold_offered', 'model_correct_id', 'model_correct_id_among_offered',
        'approved_correct_id')}, 'exclusive_first_loss': dict(sorted(attrition.items())),
        'not_offered_resolver_status': dict(sorted(missing_status.items())),
        'correct_proposal_rejected_resolver_status': dict(sorted(rejected_status.items())),
        'correct_proposal_rejected_reasons': dict(sorted(reasons.items()))}


def _guard_control(rows, keyed):
    """Hold recorded responses and offered facts fixed; change only the guard."""
    counters = {selector: [] for selector in ('plain', 'ktrf')}
    for row in rows:
        record = keyed.get((row['case_id'], row['condition']))
        if not record or record['status'] != 'RECEIVED':
            continue
        for selector in counters:
            alternative = {**row, 'selector': selector}
            counters[selector].append(grade_confirmation_response(record['response'], alternative))
    return {selector + '_guard': _totals(grades) for selector, grades in counters.items()}


def analyze_run(run_dir):
    manifest, rows, records, _, counts = read_run(run_dir)
    if manifest['status'] != 'COMPLETE' or manifest['experiment'] != 'routing_confirmation':
        raise ValueError('completed sealed routing confirmation run required')
    keyed = {(record['case_id'], record['condition']): record for record in records}
    scopes = {'all': rows}
    scopes.update({split: [row for row in rows if row['evaluation_split'] == split]
                   for split in sorted({row['evaluation_split'] for row in rows})})
    result = {'status': STATUS, 'original_run_status': manifest['status'],
        'requested_model': manifest['requested_model'], 'counts': counts,
        'original_code_revision': manifest['code_revision'],
        'verified_manifest_seal_sha256': manifest['seal_sha256'],
        'verified_artifact_sha256': manifest['artifact_sha256'], 'by_scope': {}}
    for scope, subset in scopes.items():
        by_condition = {condition: [row for row in subset if row['condition'] == condition]
                        for condition in CONDITIONS}
        unique = by_condition['ktrf_check_compact']
        result['by_scope'][scope] = {
            'documents': len(unique), 'families': len({row['family_id'] for row in unique}),
            'pipeline': {condition: _pipeline(group, keyed) for condition, group in by_condition.items()},
            'evidence': {condition: _evidence(group, keyed) for condition, group in by_condition.items()
                         if condition.startswith('ktrf_evidence_')},
            'fixed_response_guard_control': {condition: _guard_control(group, keyed)
                for condition, group in by_condition.items() if not condition.startswith('ktrf_evidence_')}}
    return result


def render_markdown(summary):
    lines = ['# Routing confirmation CPU diagnosis', '',
        '**POSTHOC_DIAGNOSTIC — original scores are unchanged.** Both completed runs were verified with',
        '`read_run`: manifest/artifact digests, frozen requests, raw-output reparsing, and sealed regrading.',
        'This reuses the exposed 192 AI-authored documents; it adds no independent validation sample.', '',
        '## Literal evidence positions', '',
        'The following table uses the 128-case confirmation split. `Non-null` is a model proposal;',
        '`reconstructed` requires a globally unique verbatim quote in the target paragraph, exactly',
        'the requested surface occurrence, and a unique occurrence of every claimed attribute value',
        'inside that quote. Only numeric positions change. Missing or ambiguous matches reject the repair.',
        'Gold labels are read only after source-only reconstruction for outcome counting.', '',
        '| Model / evidence wire | Non-null | Unique quote | Original offsets exact | Quote contains target | Reconstructed | Posthoc correct / wrong approvals |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for model, result in summary['runs'].items():
        for condition, metrics in result['by_scope']['confirmation']['evidence'].items():
            observed, post = metrics['observations'], metrics['posthoc_reconstructed_nonnull_only']
            lines.append(f"| {model} / {condition.removeprefix('ktrf_evidence_')} | {observed['nonnull_proposals']} | "
                f"{observed['quote_unique_in_source']} | {observed['original_quote_offsets_exact']} | "
                f"{observed['unique_quote_contains_target']} | {observed['positions_reconstructed']} | "
                f"{post['accepted_correct_id']} / {post['accepted_wrong_id']} |")
    lines += ['', 'The original occurrence guard, request reference, chosen ID, literal values, assessment,',
        'applicability check and direct-negation check are still applied. A source-position repair does',
        'not establish semantic entailment. Repaired outcomes cannot replace the prospective scores',
        'and do not authorize execution. Detailed rejection counts are in `summary.json`.', '',
        '## Where positive links are lost', '',
        'Each row contains the same 64 positive targets of the confirmation split. “Offered” concerns',
        'the actual rendered fact inventory; it is not synonymous with the resolver candidate set.', '',
        '| Model / condition | Detected | Gold retrieved | Gold offered | Correct model ID | Approved correct ID |',
        '|---|---:|---:|---:|---:|---:|']
    for model, result in summary['runs'].items():
        for condition in ('plain_check_compact', 'ktrf_check_compact'):
            counts = result['by_scope']['confirmation']['pipeline'][condition]['stages']
            lines.append(f"| {model} / {condition} | {counts['exact_core_detected']} | {counts['gold_retrieved']} | "
                f"{counts['gold_offered']} | {counts['model_correct_id']} | {counts['approved_correct_id']} |")
    lines += ['', 'The KTRF automation pack renders only resolver-resolved terms. A term may also be',
        'visible because another occurrence was resolved; the requested ambiguous occurrence still',
        'fails its own execution guard. Thus merely exposing a correct entity somewhere in the pack',
        'does not grant authority for the target occurrence.', '',
        '## Guard-policy confounding', '',
        'The next table keeps each compact response and its original offered facts fixed, then applies',
        'either the plain membership/binding check or the KTRF occurrence guard. It is a CPU counterfactual:',
        'models did not generate again under the alternative rule, and candidate inventories still differ.', '',
        '| Model / original prompt | Plain guard correct / wrong | KTRF guard correct / wrong |',
        '|---|---:|---:|']
    for model, result in summary['runs'].items():
        for condition in ('plain_check_compact', 'ktrf_check_compact'):
            control = result['by_scope']['confirmation']['fixed_response_guard_control'][condition]
            plain, ktrf = control['plain_guard'], control['ktrf_guard']
            lines.append(f"| {model} / {condition} | {plain['accepted_correct_id']} / {plain['accepted_wrong_id']} | "
                f"{ktrf['accepted_correct_id']} / {ktrf['accepted_wrong_id']} |")
    lines += ['', 'A new bounded experiment should hold candidates and execution authorization fixed, have',
        'the model select immutable server-generated evidence IDs, and report candidate ranking separately',
        'from executable approvals. The consumed confirmation cases are now diagnostic material.',
        'Independent deployment-risk claims still require a new audit population.', '',
        '## Reproduction', '', 'Use the private collected run directories from the original experiment:', '',
        '```bash', 'python -m eval.confirmation_diagnostics \\',
        '  --gemma-run /private/collected/routing_confirmation_gemma12b \\',
        '  --qwen-run /private/collected/routing_confirmation_qwen27b \\',
        '  --out-dir /new/aggregate-report', '```', '',
        '`summary.json` contains aggregate counts, source seals, and the diagnostic implementation digest.',
        'No source document text, per-case responses, private paths, or new LLM calls are published.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gemma-run', required=True, type=Path)
    parser.add_argument('--qwen-run', required=True, type=Path)
    parser.add_argument('--out-dir', required=True, type=Path)
    args = parser.parse_args()
    summary = {'schema_version': 1, 'status': STATUS, 'human_verified': False,
        'new_model_calls': 0, 'independent_validation': False, 'original_scores_modified': False,
        'diagnostic_implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'runs': {name: analyze_run(path) for name, path in
                 (('gemma12b', args.gemma_run), ('qwen27b', args.qwen_run))}}
    validate_public_json(summary)
    args.out_dir.mkdir(parents=True, exist_ok=False)
    (args.out_dir / 'summary.json').write_bytes(canonical(summary))
    (args.out_dir / 'ANALYSIS.md').write_text(render_markdown(summary))
    print(json.dumps({'status': STATUS, 'models': list(summary['runs']), 'new_model_calls': 0}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
