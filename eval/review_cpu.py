"""CPU review audits: sealed historical reanalysis and actual candidate retrieval.

Outputs contain aggregates only. Historical scoring runs in its frozen source
version; experimental occurrence proposals never authorize production actions.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import tarfile
import time

from eval.context_ranking_challenge import _snapshot
from eval.context_ranking_corpus import _profile
from eval.occurrence_evidence_corpus import build_cases
from eval.run_context_ranking_challenge import FROZEN_RULES
from ktrf.occurrence_evidence import select_evidence
from ktrf.rerank import LexicalCrossEncoder, rerank_query
from ktrf.resolver import resolve

PROTOCOL = 'ktrf_review_cpu_v1'
VARIANTS = ('target_full', 'scoped_evidence', 'scoped_asserted')


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def paired_cluster_bootstrap(observations, *, unit='family', replicates=2000,
                             seed=20261020):
    """Paired micro-mean differences, resampling whole source clusters.

    Each observation has left/right numeric values and family/document keys.
    Multiple mentions/repeats in a family never become independent draws.
    """
    if unit not in {'family', 'document'} or replicates < 1:
        raise ValueError('positive replicate count and family/document unit required')
    clusters = defaultdict(list)
    for row in observations:
        if not isinstance(row.get(unit), str) or not row[unit]:
            raise ValueError('source cluster identity is required')
        values = row['left'], row['right']
        if any(type(v) not in (float, int, bool) or not math.isfinite(v) for v in values):
            raise ValueError('paired observations must be finite numeric values')
        clusters[row[unit]].append(float(row['right']) - float(row['left']))
    grouped = [(math.fsum(values), len(values)) for _, values in sorted(clusters.items())]
    count = sum(n for _, n in grouped)
    estimate = math.fsum(total for total, _ in grouped) / count if count else None
    if len(grouped) < 2:
        interval = None  # one cluster cannot substantiate a sampling interval
    else:
        rng = random.Random(seed)
        samples = []
        for _ in range(replicates):
            selected = [grouped[rng.randrange(len(grouped))] for _ in grouped]
            samples.append(math.fsum(total for total, _ in selected) /
                           sum(n for _, n in selected))
        samples.sort()
        interval = [samples[max(0, math.floor(.025 * replicates))],
                    samples[min(replicates - 1, math.ceil(.975 * replicates) - 1)]]
    return {'estimate_right_minus_left': estimate, 'percentile_interval_95': interval,
            'cluster_unit': unit, 'clusters': len(grouped), 'observations': count,
            'replicates': replicates, 'seed': seed,
            'interpretation': 'DESCRIPTIVE_PAIRED_CLUSTER_BOOTSTRAP_NOT_RISK_CERTIFICATION'}


def _paired_summary(pairs, *, replicates, seed):
    observations = [dict(family=left['family_id'],
                         document=left.get('parent_document_id') or left.get('document_id'),
                         left=int(lgrade['correct']), right=int(rgrade['correct']))
                    for left, right, lgrade, rgrade, _, _ in pairs]
    result = {'questions': len(pairs),
              'positive_questions': sum(bool(left['positive_gold']) for left, *_ in pairs),
              'left_correct': sum(int(lg['correct']) for _, _, lg, _, _, _ in pairs),
              'right_correct': sum(int(rg['correct']) for _, _, _, rg, _, _ in pairs),
              'helpful_flips': sum(not lg['correct'] and rg['correct'] for _, _, lg, rg, _, _ in pairs),
              'harmful_flips': sum(lg['correct'] and not rg['correct'] for _, _, lg, rg, _, _ in pairs),
              'bootstrap': {unit: paired_cluster_bootstrap(observations, unit=unit,
                              replicates=replicates, seed=seed) for unit in ('family', 'document')}}
    for side, index in [('left', 4), ('right', 5)]:
        records = [p[index] for p in pairs]
        for metric in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
            values = [r['usage'][metric] for r in records
                      if isinstance(r.get('usage'), dict) and type(r['usage'].get(metric)) is int]
            result[side + '_' + metric + '_sum'] = sum(values)
            result[side + '_' + metric + '_observed'] = len(values)
        latencies = [r['latency_ms'] for r in records if type(r.get('latency_ms')) in (int, float)]
        result[side + '_mean_latency_ms'] = math.fsum(latencies) / len(latencies) if latencies else None
    for metric in ('accepted_wrong_id', 'accepted_correct_id', 'over_abstention', 'correct_abstention'):
        if pairs and metric in pairs[0][2]:
            result['left_' + metric] = sum(int(p[2][metric]) for p in pairs)
            result['right_' + metric] = sum(int(p[3][metric]) for p in pairs)
    return result


def _verify_frozen_source(prior_dir, source):
    """Verify executable historical files against the original sealed archive."""
    base = Path(prior_dir).resolve().parent
    launch = json.loads((base / 'launch.json').read_text())
    archive = base / 'source.tar.gz'
    if hashlib.sha256(archive.read_bytes()).hexdigest() != launch['archive_sha256']:
        raise ValueError('historical source archive hash mismatch')
    source = Path(source).resolve()
    checked, source_files = 0, set()
    with tarfile.open(archive, 'r:gz') as bundle:
        for member in bundle.getmembers():
            path = Path(member.name)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('unsafe historical archive member')
            if not member.isfile():
                continue
            archived = bundle.extractfile(member).read()
            local = source / path
            if not local.is_file() or local.read_bytes() != archived:
                raise ValueError('frozen historical source differs from archive: ' + member.name)
            source_files.add(member.name)
            checked += 1
    if any(str(p.relative_to(source)) not in source_files for p in source.rglob('*.py')):
        raise ValueError('unexpected Python code in historical source')
    return {'archive_sha256': launch['archive_sha256'],
            'historical_code_revision': launch['code_revision'], 'verified_source_files': checked}


def _read_historical_runs(prior_dir, frozen_source_dir):
    source = Path(frozen_source_dir).resolve()
    proof = _verify_frozen_source(prior_dir, source)
    script = '''import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
from eval.report_extended_suite import read_run
result = []
for directory in sorted(pathlib.Path(sys.argv[2]).iterdir()):
    if not directory.is_dir() or not (directory / "run_manifest.json").is_file():
        continue
    manifest, rows, records, graded, counts = read_run(directory)
    if manifest["code_revision"] != sys.argv[3]:
        raise ValueError("historical stage code revision mismatch")
    result.append({"stage": directory.name, "rows": rows, "grades": graded["cases"],
        "records": [{k:r.get(k) for k in ("case_id","condition","latency_ms","usage")}
                    for r in records], "counts": counts,
        "manifest_sha256": __import__("hashlib").sha256((directory/"run_manifest.json").read_bytes()).hexdigest()})
print(json.dumps(result, ensure_ascii=False))
'''
    checked = subprocess.run([sys.executable, '-I', '-c', script, str(source),
                              str(Path(prior_dir).resolve()), proof['historical_code_revision']],
                             cwd=source, text=True, capture_output=True, check=False)
    if checked.returncode:
        # Exception types/diagnostic messages do not include raw requests.
        raise ValueError('historical frozen verifier failed: ' + checked.stderr[-1500:])
    return json.loads(checked.stdout), proof


def reanalyze_previous(prior_dir, *, frozen_source_dir=None, bootstrap_replicates=2000,
                       seed=20261020):
    prior_dir = Path(prior_dir).resolve()
    if frozen_source_dir is None:
        frozen_source_dir = prior_dir.parent / 'collector_source'
    runs, source_proof = _read_historical_runs(prior_dir, frozen_source_dir)
    output = {}
    for run in runs:
        rows = {(r['case_id'], r['condition']): r for r in run['rows']}
        grades = {(r['case_id'], r['condition']): r for r in run['grades']}
        records = {(r['case_id'], r['condition']): r for r in run['records']}
        if len(rows) != len(run['rows']) or set(rows) != set(grades) or set(rows) != set(records):
            raise ValueError('historical paired audit requires unique complete request keys')
        experiment = run['rows'][0]['experiment']
        if experiment == 'fresh_compact':
            contrasts = [('none', 'full'), ('none', 'compact'), ('full', 'compact')]
        elif experiment == 'source_pack_factorial':
            contrasts = [('full_' + pack, 'shrunken_' + pack) for pack in ('none', 'full', 'compact')]
            contrasts += [(source + '_none', source + '_' + pack)
                          for source in ('full', 'shrunken') for pack in ('full', 'compact')]
        elif experiment == 'safety_robustness':
            contrasts = [('pack_' + position + '_baseline', 'pack_' + position + '_semantic_check')
                         for position in ('first', 'last')]
            contrasts += [('pack_first_' + policy, 'pack_last_' + policy)
                          for policy in ('baseline', 'semantic_check')]
        else:
            raise ValueError('unexpected historical diagnostic experiment')
        paired = {}
        for left_condition, right_condition in contrasts:
            groups = defaultdict(list)
            for case_id in sorted({key[0] for key in rows}):
                lk, rk = (case_id, left_condition), (case_id, right_condition)
                if lk not in rows or rk not in rows:
                    raise ValueError('historical condition matrix is incomplete')
                left, right = rows[lk], rows[rk]
                if (left['family_id'] != right['family_id']
                        or left['evaluation_split'] != right['evaluation_split']
                        or left['positive_gold'] != right['positive_gold']):
                    raise ValueError('paired source identities disagree')
                pair = left, right, grades[lk], grades[rk], records[lk], records[rk]
                prefix = left['evaluation_split'] + '/'
                groups[prefix + 'all'].append(pair)
                injected = bool(left.get('pack_injected', left.get('injected')) or
                                right.get('pack_injected', right.get('injected')))
                identical = (left['system'], left['user']) == (right['system'], right['user'])
                if injected:
                    groups[prefix + 'pack_actually_injected'].append(pair)
                if identical:
                    groups[prefix + 'identical_prompts'].append(pair)
                if not injected and not identical:
                    groups[prefix + 'policy_or_source_changed_without_pack'].append(pair)
                if experiment == 'source_pack_factorial' and left_condition.startswith('full_') and right_condition.startswith('shrunken_'):
                    if not left['positive_gold']:
                        category = 'negative_question'
                    elif left['source_gold_visible'] and not right['source_gold_visible']:
                        category = 'positive_source_visibility_lost'
                    elif left['source_gold_visible'] and right['source_gold_visible']:
                        category = 'positive_source_visibility_kept'
                    else:
                        category = 'positive_source_not_visible_before'
                    groups[prefix + category].append(pair)
            paired[left_condition + '_to_' + right_condition] = {
                group: _paired_summary(pairs, replicates=bootstrap_replicates, seed=seed)
                for group, pairs in sorted(groups.items())}
        output[run['stage']] = {'status': 'REPARSED_AND_REGRADED_BY_ORIGINAL_FROZEN_SOURCE',
            'manifest_sha256': run['manifest_sha256'], 'counts': run['counts'],
            'exposure': 'POST_HOC_EXPOSED_DIAGNOSTIC_REANALYSIS', 'paired_subgroups': paired}
    return {'historical_source_proof': source_proof, 'runs': output,
            'subgroups_are_new_confirmatory_holdouts': False,
            'subgroup_selection': 'preexisting injection flags, exact prompt equality, and gold source visibility; never response correctness',
            'original_article_independence_verified': False}


def _bounds(value):
    return tuple(value['codepoint'][k] for k in ('start', 'end'))


def _semantic_span(mention):
    # full_span includes raw grammatical particles; gold surface spans do not.
    return _bounds(mention.get('full_surface', {}).get('span', mention['span']))


def _metrics(rows):
    positives = [r for r in rows if r['positive']]
    present = [r for r in positives if r['gold_in_candidates']]
    selected = [r for r in rows if r['proposal_selected']]
    return {'events': len(rows), 'positive_events': len(positives),
        'missed_mentions': sum(r['missed'] for r in rows),
        'core_boundary_mismatches': sum(r['core_boundary_wrong'] for r in rows),
        'full_surface_boundary_mismatches': sum(r['full_boundary_wrong'] for r in rows),
        'gold_in_unbudgeted_candidates': sum(r['gold_in_all_candidates'] for r in positives),
        'gold_in_budgeted_candidates': len(present),
        'candidate_recall': len(present) / len(positives) if positives else None,
        'conditional_ranking_correct': sum(r['top_entity_correct'] for r in present),
        'conditional_ranking_accuracy': sum(r['top_entity_correct'] for r in present) / len(present) if present else None,
        'conditional_exact_link_correct': sum(r['top_correct'] for r in present),
        'correct_proposals': sum(r['top_correct'] for r in selected),
        'wrong_proposals': sum(not r['top_correct'] for r in selected),
        'over_abstentions': sum(r['positive'] and not r['proposal_selected'] for r in rows),
        'correct_abstentions': sum(not r['positive'] and not r['proposal_selected'] for r in rows),
        'production_correct_commits': sum(r['production_correct'] for r in rows),
        'production_wrong_commits': sum(r['production_selected'] and not r['production_correct'] for r in rows),
        'production_over_abstentions': sum(r['positive'] and not r['production_selected'] for r in rows),
        'documents_with_wrong_proposal': len({r['document'] for r in selected if not r['top_correct']}),
        'documents_with_wrong_production_commit': len({r['document'] for r in rows
            if r['production_selected'] and not r['production_correct']}),
        'mean_candidate_count': math.fsum(r['candidate_count'] for r in rows) / len(rows) if rows else None,
        'candidate_budget_truncations': sum(r['candidate_truncated'] for r in rows),
        'resolver_pool_truncations': sum(r['pool_truncated'] for r in rows),
        'families': len({r['family'] for r in rows}), 'documents': len({r['document'] for r in rows})}


def evaluate_actual_candidates(cases, scorer=None, *, candidate_budget=8,
                               backend='lexical', max_pair_tokens=1024,
                               bootstrap_replicates=2000, seed=20261020):
    """Use only resolve() outputs: no fixed hypotheses or gold candidate insertion."""
    if type(candidate_budget) is not int or not 1 <= candidate_budget <= 8:
        raise ValueError('candidate budget must be between one and eight')
    if backend not in FROZEN_RULES:
        raise ValueError('backend must be lexical or nano with its frozen rule')
    scorer = scorer or LexicalCrossEncoder()
    snapshots, catalogs, documents, prepared = {}, {}, {}, []
    max_actual_tokens, pair_calls = 0, 0
    identity = []
    for case in cases:
        family = case['family_id']
        terms = case['catalog_terms']
        if family not in snapshots:
            snapshots[family] = _snapshot(terms, family)
            catalogs[family] = _digest(terms)
        elif _digest(terms) != catalogs[family]:
            raise ValueError('family catalog cannot change')
        # No gold labels, fixed hypotheses, or gold target span go to resolve.
        key = family, case['document_id']
        if key not in documents:
            start = time.perf_counter()
            response = resolve(snapshots[family], case['text'], mode='commit', options={
                'return_eval_trace': True, 'max_prediction_set': 500})
            documents[key] = response, case['text'], (time.perf_counter() - start) * 1000
        response, source, elapsed = documents[key]
        if source != case['text']:
            raise ValueError('source document identity changed')
        core, full = tuple(case['core_span']), tuple(case['full_surface_span'])
        matches = [m for m in response['mentions'] if _bounds(m['span']) == core]
        mention = next((m for m in matches if _semantic_span(m) == full), matches[0] if matches else None)
        overlaps = [m for m in response['mentions'] if _bounds(m['span'])[0] < core[1] and core[0] < _bounds(m['span'])[1]]
        ranked = mention.get('eval_trace', {}).get('ranked', []) if mention else []
        shortlist = ranked[:candidate_budget]
        if len({c['entity_id'] for c in shortlist}) != len(shortlist):
            raise ValueError('resolver candidate IDs must be unique')
        by_entity = {'global:' + t['key']: t for t in terms}
        candidates = []
        for candidate in shortlist:
            if candidate['entity_id'] not in by_entity:
                raise ValueError('actual candidate has no glossary profile')
            term = by_entity[candidate['entity_id']]
            candidates.append(dict(candidate, profile=_profile(term), canonical=term['canonical'],
                                   aliases=term['surfaces'], short_definition=term['short_definition']))
        variants = {}
        if mention and candidates:
            actual_core = _bounds(mention['span'])
            full_query = rerank_query(source, actual_core, 'target', radius=len(source))
            selection = select_evidence(source, actual_core, candidates, mode='scoped', max_chars=1024)
            for variant in VARIANTS:
                query = full_query if variant == 'target_full' else selection.rendered_query
                pairs = [(query, c['profile']) for c in candidates]
                if hasattr(scorer, 'tokenizer'):
                    from eval.run_context_ranking import _token_count
                    counts = [_token_count(scorer.tokenizer, pair) for pair in pairs]
                    if any(n > max_pair_tokens for n in counts):
                        raise ValueError('actual resolver pair exceeds frozen token limit before inference')
                    max_actual_tokens = max(max_actual_tokens, *counts)
                variants[variant] = (pairs, bool(selection.gate_allowed) if variant == 'scoped_asserted' else True)
        prepared.append((case, mention, overlaps, ranked, candidates, variants))
        identity.append([case['case_id'], case['document_sha256'],
                         [c['entity_id'] for c in candidates],
                         {v: _digest(pairs) for v, (pairs, _) in variants.items()}])
    # All source, candidates and exact inputs preflight before the first score.
    results = defaultdict(list)
    for case, mention, overlaps, ranked, candidates, variants in prepared:
        positive = case['semantic_label'] == 'LINK'
        gold = case.get('expected_entity_id') if positive else None
        full_matches = mention is not None and _semantic_span(mention) == tuple(case['full_surface_span'])
        production_id = (mention.get('resolved_entity') or {}).get('entity_id') if mention else None
        base = {'family': case['family_id'], 'document': case['document_id'],
            'positive': positive, 'cohort': case['cohort'], 'stratum': case.get('stratum', 'unspecified'),
            'missed': not mention and not overlaps,
            'core_boundary_wrong': not mention and bool(overlaps),
            'full_boundary_wrong': bool(mention) and not full_matches,
            'gold_in_all_candidates': bool(gold and any(c['entity_id'] == gold for c in ranked)),
            'gold_in_candidates': bool(gold and any(c['entity_id'] == gold for c in candidates)),
            'candidate_count': len(candidates), 'candidate_truncated': len(ranked) > candidate_budget,
            'pool_truncated': bool(mention and (mention.get('eval_trace', {}).get('pool', {}).get('truncated') or
                                                mention.get('eval_trace', {}).get('pool', {}).get('exact_overflow'))),
            'production_selected': bool(mention and mention.get('link_decision') == 'RESOLVED'),
            'production_correct': bool(positive and full_matches and production_id == gold),
            'top_correct': False, 'top_entity_correct': False, 'proposal_selected': False}
        for variant in VARIANTS:
            row = dict(base)
            if variant in variants:
                pairs, assertion_allowed = variants[variant]
                scores = scorer.score_pairs(pairs)
                if len(scores) != len(candidates) or any(type(s) not in (int, float) or not math.isfinite(s) for s in scores):
                    raise ValueError('one finite raw scalar score required for every actual candidate')
                pair_calls += len(scores)
                order = sorted(range(len(candidates)), key=lambda i: (-scores[i], candidates[i]['entity_id']))
                index = order[0]
                top = candidates[index]
                margin = scores[index] - scores[order[1]] if len(order) > 1 else None
                identity_value = mention.get('full_surface', {}).get('identity', 'SAME_AS_CORE')
                guard_allowed = (not top.get('commit_blocked') and identity_value == 'SAME_AS_CORE')
                rule = FROZEN_RULES[backend]
                row['top_entity_correct'] = bool(positive and top['entity_id'] == gold)
                row['top_correct'] = bool(row['top_entity_correct'] and full_matches)
                row['proposal_selected'] = bool(guard_allowed and not row['pool_truncated'] and
                    not row['candidate_truncated'] and assertion_allowed and scores[index] >= rule['minimum_score'] and
                    (margin is None or margin > 0 and margin >= rule['minimum_margin']))
            results[(case['cohort'], variant)].append(row)
    cohorts = {}
    for cohort in sorted({case['cohort'] for case in cases}):
        by_variant = {}
        for variant in VARIANTS:
            variant_rows = results[(cohort, variant)]
            by_variant[variant] = _metrics(variant_rows)
            by_variant[variant]['by_stratum'] = {
                stratum: _metrics([r for r in variant_rows if r['stratum'] == stratum])
                for stratum in sorted({r['stratum'] for r in variant_rows})}

        comparisons = {}
        for left, right in itertools.combinations(VARIANTS, 2):
            lrows, rrows = results[(cohort, left)], results[(cohort, right)]
            paired = [dict(family=l['family'], document=l['document'],
                           left=int(l['proposal_selected'] and l['top_correct']),
                           right=int(r['proposal_selected'] and r['top_correct'])) for l, r in zip(lrows, rrows)]
            comparisons[left + '_to_' + right] = {unit: paired_cluster_bootstrap(paired, unit=unit,
                replicates=bootstrap_replicates, seed=seed) for unit in ('family', 'document')}
        cohorts[cohort] = {'exposure': ('PREVIOUSLY_EVALUATED_AI_SYNTHETIC_EXPOSED_DIAGNOSTIC'
                                       if cohort in {'development', 'heldout'} else
                                       'AI_SOURCE_GOLD_REVIEWED_BEFORE_CURRENT_INFERENCE'),
                           'human_verified': False, 'by_variant': by_variant, 'paired_correct_proposals': comparisons}
    return {'cohorts': cohorts, 'backend': backend, 'reranker_id': scorer.reranker_id,
            'candidate_budget': candidate_budget, 'gold_forced_candidates': False,
            'resolver_calls': len(documents), 'target_events': len(prepared),
            'input_sha256': _digest(identity), 'measured_pair_calls': pair_calls,
            'tokenizer_checked': hasattr(scorer, 'tokenizer'),
            'maximum_pair_tokens': max_actual_tokens or None,
            'frozen_rules': FROZEN_RULES[backend], 'threshold_fitting_performed': False,
            'production_authorized': False, 'coverage_valid': False,
            'resolver_total_ms': math.fsum(value[2] for value in documents.values()),
            'full_span_contract': 'semantic nominal surface excludes grammatical particles; raw full_span is not compared to nominal gold',
            'fixture_sha256': sorted({c['fixture_sha256'] for c in cases if c.get('fixture_sha256')}),
            'catalog_scope': 'complete registered catalog for each family, not a global deployment glossary',
            'candidate_recall_scope': 'entity ID at exactly detected core; nominal full boundary reported separately',
            'ranking_scope': 'entity ranking conditional on gold in actual budgeted candidates; exact-link correctness additionally requires nominal full span',
            'selection_limit': 'previous corpus was authored around registered aliases and fixed candidate families; actual resolve integration does not create an independent general retrieval benchmark'}


def _assert_public_aggregates(value):
    forbidden = {'case_id', 'family_id', 'document_id', 'source_text', 'text', 'question',
                 'answer', 'expected_answers', 'raw_response', 'requests', 'records'}
    if isinstance(value, dict):
        if forbidden & set(value):
            raise ValueError('individual source or answer fields cannot enter public CPU proof')
        for item in value.values():
            _assert_public_aggregates(item)
    elif isinstance(value, list):
        for item in value:
            _assert_public_aggregates(item)


def run_cpu_audits(prior_dir, out_dir, scorer=None, *, frozen_source_dir=None,
                   bootstrap_replicates=2000, seed=20261020, backend='lexical'):
    history = reanalyze_previous(prior_dir, frozen_source_dir=frozen_source_dir,
                                bootstrap_replicates=bootstrap_replicates, seed=seed)
    cases = build_cases(cohort='development') + build_cases(cohort='heldout')
    actual = evaluate_actual_candidates(cases, scorer, backend=backend,
                                       bootstrap_replicates=bootstrap_replicates, seed=seed)
    proof = {'protocol': PROTOCOL, 'historical_reanalysis': history,
             'actual_candidate_occurrence': actual, 'new_llm_requests': 0,
             'production_authorized': False, 'coverage_valid': False}
    _assert_public_aggregates(proof)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'cpu_audits.json').write_text(json.dumps(proof, ensure_ascii=False, sort_keys=True,
                                                 indent=2) + '\n')
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prior-dir', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--frozen-source-dir', type=Path)
    parser.add_argument('--backend', choices=('lexical', 'nano'), default='lexical')
    parser.add_argument('--model-dir', type=Path)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--bootstrap-replicates', type=int, default=2000)
    args = parser.parse_args()
    scorer = None
    if args.backend == 'nano':
        if args.model_dir is None:
            parser.error('--model-dir is required for nano')
        from eval.run_context_ranking import StrictLocalScalarScorer
        scorer = StrictLocalScalarScorer(args.model_dir, 1024, args.device)
    proof = run_cpu_audits(args.prior_dir, args.out_dir, scorer,
        frozen_source_dir=args.frozen_source_dir, backend=args.backend,
        bootstrap_replicates=args.bootstrap_replicates)
    print(json.dumps({'protocol': proof['protocol'], 'output': 'cpu_audits.json', 'status': 'COMPLETE'}))


if __name__ == '__main__':
    main()
