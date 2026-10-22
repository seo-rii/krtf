"""Gold-assisted CPU ceilings on sealed, previously exposed support experiments.

Oracle selections here diagnose validator capacity only. No oracle response,
label or reconstructed source evidence is used as an operational proposal.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .evidence_robustness import grade_evidence_robustness_response
from .hf_qa import canonical
from .report_extended_suite import read_run
from .review_business import grade_business_response
from .routing_confirmation import ATTRIBUTES


def _candidate_response(row, entity_id, bundle_alias=None):
    registry = row['reference_registry']
    alias = next((a for a, eid in registry['entities'].items() if eid == entity_id), None)
    return {'selections': [{'r': registry['request_ref'], 'e': alias,
                            's': 'SUPPORT' if alias else 'UNRESOLVED', 'b': bundle_alias}]}


def analyze_rows(rows, cases):
    """Count mutually exclusive positive bottlenecks, keeping gold diagnostic."""
    rows = [row for row in rows if row['condition'] == 'bundle_control']
    indexed = {c['case_id']: c for c in cases if c['condition'] == 'bundle_control'}
    if not rows or len(indexed) != len(rows) or len({r['case_id'] for r in rows}) != len(rows):
        raise ValueError('complete unique paired source and graded cases required')
    stages, by_stratum, by_family = Counter(), defaultdict(Counter), defaultdict(Counter)
    positive = retrieved = base_eligible = bundle_eligible = approved = 0
    negative_literal_eligible = 0
    missing_attributes = Counter()
    omitted = 0
    for row in rows:
        gold = row['expected_entity_id']
        aliases = row['reference_registry']['entities']
        bundles = row['bundle_inventory']['bundles']
        omitted += row['bundle_inventory']['omitted_combinations']
        if gold is None:
            # A synthetic SUPPORT proposal deliberately tests whether any
            # offered wrong candidate could pass; it is never model accuracy.
            negative_literal_eligible += any(
                grade_evidence_robustness_response(_candidate_response(row, eid, bid), row)['accepted_wrong_id']
                for bid, bundle in bundles.items()
                for alias, eid in aliases.items() if alias == bundle['entity_alias'])
            continue
        positive += 1
        found = row['pipeline_trace']['exact_core_detected']
        in_candidates = gold in row['offered_entity_ids']
        retrieved += in_candidates
        selection = {**deepcopy(row['selection_binding']), 'entity_id': gold}
        base = grade_business_response({'selections': [selection]}, row)
        production_allowed = bool(in_candidates and base['guard_valid'])
        base_eligible += production_allowed
        eligible_bundles = [bid for bid, bundle in bundles.items()
                            if aliases[bundle['entity_alias']] == gold]
        matching = [grade_evidence_robustness_response(_candidate_response(row, gold, bid), row)
                    for bid in eligible_bundles]
        eligible = any(g['accepted_correct_id'] for g in matching)
        bundle_eligible += eligible
        for name in ATTRIBUTES:
            if not any(a['attribute'] == name and a['value'] in row['applicability'].get(gold, {}).get(name, [])
                       for a in row['evidence_inventory']['attributes']):
                missing_attributes[name] += 1
        observed = indexed[row['case_id']]['accepted_correct_id']
        approved += observed
        if observed and not eligible:
            raise ValueError('observed approval exceeds enumerated unchanged-validator ceiling')
        if not found:
            reason = 'target_not_detected'
        elif not in_candidates:
            reason = 'gold_not_retrieved'
        elif not production_allowed:
            reason = 'production_occurrence_guard_blocked'
        elif not eligible_bundles:
            reason = 'no_complete_same_paragraph_four_attribute_bundle'
        elif not eligible:
            reason = 'literal_evidence_gate_blocked'
        elif not observed:
            reason = 'model_or_wire_failure_below_validator_ceiling'
        else:
            reason = 'approved'
        stages[reason] += 1
        by_stratum[row['stratum']][reason] += 1
        by_family[row['family_id']][reason] += 1
    return {
        'source_cases': len(rows), 'positive_cases': positive, 'negative_cases': len(rows) - positive,
        'gold_in_actual_candidates': retrieved, 'production_guard_oracle_correct_ceiling': base_eligible,
        'four_attribute_gate_oracle_correct_ceiling': bundle_eligible,
        'observed_correct_approvals': approved,
        'additional_correct_approvals_possible_without_validator_changes': bundle_eligible - approved,
        'positive_primary_bottlenecks': dict(stages),
        'positive_attribute_literal_absence_in_target_paragraph': dict(missing_attributes),
        'negative_cases_with_any_oracle_wrong_bundle_approval': negative_literal_eligible,
        'bundle_combinations_omitted': omitted,
        'ceiling_complete_for_enumerated_inventory': omitted == 0,
        'by_stratum': {k: dict(v) for k, v in sorted(by_stratum.items())},
        'by_family': {k: dict(v) for k, v in sorted(by_family.items())},
        'evaluation_population': 'EXPOSED_GOLD_ASSISTED_CPU_DIAGNOSTIC',
        'independent_validation': False, 'operational_proposals_emitted': False,
        'interpretation': ('Gold-assisted capacity of the existing candidate inventory and unchanged validator; '
                           'not evidence that gold-derived choices can be made by a model or used for execution.'),
    }


def analyze_frozen_run(run_dir):
    manifest, rows, _, graded, counts = read_run(run_dir)
    if manifest['experiment'] != 'evidence_robustness' or manifest['status'] != 'COMPLETE':
        raise ValueError('complete sealed robustness run required')
    result = analyze_rows(rows, graded['cases'])
    result.update(model=manifest['requested_model'], code_revision=manifest['code_revision'],
                  frozen_request_file_sha256=manifest['frozen_request_file_sha256'],
                  source_manifest_sha256=hashlib.sha256((Path(run_dir) / 'run_manifest.json').read_bytes()).hexdigest(),
                  sealed_regrade_counts=counts)
    return result


def render_markdown(results):
    lines = ['# 승인 상한과 보류 원인: CPU 진단', '',
             '이미 공개된 합성 자료의 봉인된 원시 응답을 재채점한 뒤 정답 ID와 근거를 넣어 검증기 상한을 계산했다.',
             '정답을 아는 oracle 진단이며 모델 성능·새 독립 검증·운영 승인으로 사용하지 않는다.', '',
             '| 모델 | 정상 사례 | 정답 후보 회수 | 기존 승인 검증 상한 | 네 속성 검사 포함 상한 | 실제 정상 승인 |',
             '|---|---:|---:|---:|---:|---:|']
    for name, d in results.items():
        lines.append(f"| {name} | {d['positive_cases']} | {d['gold_in_actual_candidates']} | "
                     f"{d['production_guard_oracle_correct_ceiling']} | {d['four_attribute_gate_oracle_correct_ceiling']} | {d['observed_correct_approvals']} |")
    for name, d in results.items():
        lines += ['', f'모델 `{name}`의 정상 사례별 첫 차단 원인:', '', '```json',
                  json.dumps(d['positive_primary_bottlenecks'], ensure_ascii=False, indent=2), '```']
    lines += ['', '후속 비교에서는 여러 문장·문단의 근거 결합, 누락 속성과 직접 모순의 분리,',
              '문맥으로 구분되는 모호 후보를 각각 다룬다. 기존 운영 승인과 실험용 shadow 결과는 분리한다.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gemma-run', type=Path, required=True)
    parser.add_argument('--qwen-run', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    results = {name: analyze_frozen_run(path) for name, path in
               (('gemma12b', args.gemma_run), ('qwen27b', args.qwen_run))}
    from .collect_hf_qa_queue import validate_public_json
    validate_public_json(results)
    args.out_dir.mkdir(parents=True, exist_ok=False)
    (args.out_dir / 'summary.json').write_bytes(canonical(results))
    (args.out_dir / 'ANALYSIS.md').write_text(render_markdown(results))
    print(json.dumps({name: {k: d[k] for k in ('production_guard_oracle_correct_ceiling',
          'four_attribute_gate_oracle_correct_ceiling', 'observed_correct_approvals')} for name, d in results.items()}))


if __name__ == '__main__':
    main()
