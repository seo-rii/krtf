"""Evaluation-only source reference closure and discriminated abstention wires.

Closure supplies references, never claims: only the requested target sentence
and the parents of already selected attribute anchors may be added.  The
existing supported-shadow ownership, contradiction and occurrence checks stay
unchanged.  Bundles are another reversible transport of those same anchors.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json

from eval import support_recovery as support
from eval.evidence_control import PROPOSAL_POLICY, _sha
from eval.hf_qa import canonical
from eval.prepare_followup import MAX_MODEL_LEN, _token_ids
from eval.review_business import SEMANTIC_CHECK
from eval.routing_confirmation import ATTRIBUTES, RESERVED_OUTPUT_TOKENS, records_sha256
from ktrf.context import CharTokenCounter

EXPERIMENT = 'evidence_closure'
POPULATION = support.POPULATION
FRESH_POPULATION = support.FRESH_POPULATION
CONDITIONS = ('manual_legacy', 'closure_legacy', 'manual_null', 'closure_null', 'closure_bundle')
BASELINE = CONDITIONS[0]
MAX_BUNDLES_PER_ENTITY = 16
SOURCE_STRATA_FIELDS = ('candidate_referent_kind', 'candidate_country', 'target_side')
LIMITATIONS = [
    'All decisions are evaluation-only shadow observations with execution_authority=none; no action is executed.',
    'The supported-shadow source ownership, positive-support, explicit-conflict and occurrence checks are unchanged across all five arms.',
    'Server closure adds only the exact requested target sentence and parents of model-selected attribute anchors; it never supplies an entity, assessment or attribute claim.',
    'Unknown, stale, duplicate or other-occurrence references are not repaired, and original selected evidence is never removed to conceal contradictions.',
    'A discriminated null wire accepts only request reference and e=null; link branches require SUPPORT and still undergo the complete unchanged gate.',
    'Source-only bundles enumerate individual compatible owned attributes and a bounded combined set, not semantic entailment or authorization.',
    'Every arm receives the same full document, complete definitions, ownership inventory and bundle catalog; policies and response transport are the manipulated factors.',
    'Missing applicability values remain UNKNOWN; the server does not infer missing facts or create new support.',
    'Sources and annotations are AI authored and independently AI reviewed, not human gold or actual workplace records.',
    'Document and family provenance is retained; model calls and paired conditions are not independent documents.',
]
COMMON_POLICY = (
    '본 평가는 실행 없는 shadow 실험이며 출력은 실행 권한을 주지 않는다. '
    '제안하려면 원문에서 요청한 발생 위치의 대상에 대한 applicability 속성 하나 이상을 '
    '적극적으로 확인한다. 생략된 속성은 UNKNOWN이며 추정하여 채우지 않는다. '
    '다른 발생 위치나 다른 대상의 속성을 빌리지 않는다. 명시적 모순, 인용된 문자열, '
    '역할·파생 대상, 구별 불가능한 후보이면 기권한다. '
    'bundles는 source-owned 참조의 묶음일 뿐 정답이나 사전 승인이 아니다.'
)
LEGACY_POLICY = (
    'selections 하나에 r=request_ref,e=entity_alias 또는 null,s=SUPPORT/CONTRADICT/UNRESOLVED,'
    'q=segment_alias 배열,a=attribute_alias 배열을 쓴다. '
    'e=null이면 s=UNRESOLVED 또는 CONTRADICT,q=[],a=[]이어야 한다.'
)
NULL_POLICY = (
    '기권 응답은 selections:[{r:request_ref,e:null}]로 두 필드만 쓴다. '
    '기권 응답에는 s,q,a,b를 쓰지 않는다. '
    '연결 제안에는 r,e,s=SUPPORT,q=segment_alias 배열,a=attribute_alias 배열을 모두 쓴다.'
)
CLOSURE_POLICY = (
    '서버가 요청 발생 위치를 포함하는 문장과 선택한 a의 부모 문장을 근거 q에 추가한다. '
    '서버는 선택하지 않은 속성·대상·판정을 추가하지 않는다. 기존 q는 삭제하지 않으며 '
    '잘못된 참조나 다른 대상의 근거는 복구하지 않는다.'
)
MANUAL_POLICY = (
    'q에 요청 발생 위치를 포함하는 문장과 선택한 모든 a의 부모 문장을 직접 포함한다.'
)
BUNDLE_POLICY = (
    '기권은 selections:[{r:request_ref,e:null}]로 두 필드만 쓴다. '
    '연결은 r,e,s=SUPPORT,b=bundle_alias 네 필드만 쓴다. '
    'b는 같은 entity_alias와 요청 발생 위치에 묶인 근거·속성 참조를 복원한다. '
    '속성이 직접 부정됐거나 다른 명시적 모순이 있으면 선택하지 않는다.'
)


def _request_ref(binding, condition):
    return 'ec-' + _sha({'protocol': 'evidence_closure_v1', 'condition': condition, 'binding': binding})


def _null_wire(row):
    return row['condition'] in {'manual_null', 'closure_null', 'closure_bundle'}


def evidence_closure_schema(row_or_condition):
    row = row_or_condition if isinstance(row_or_condition, dict) else {'condition': row_or_condition}
    if row['condition'] not in CONDITIONS:
        raise ValueError('unknown evidence closure condition')
    nonempty = {'type': 'string', 'minLength': 1}
    if not _null_wire(row):
        return support.support_recovery_schema('multispan_supported_shadow')
    null = {'type': 'object', 'properties': {'r': nonempty, 'e': {'type': 'null'}},
            'required': ['r', 'e'], 'additionalProperties': False}
    properties = {'r': nonempty, 'e': nonempty, 's': {'type': 'string', 'const': 'SUPPORT'}}
    if row['condition'] == 'closure_bundle':
        properties['b'] = nonempty
    else:
        properties['q'] = {'type': 'array', 'maxItems': support.MAX_SELECTED_SEGMENTS, 'items': nonempty}
        properties['a'] = {'type': 'array', 'maxItems': support.MAX_SELECTED_ATTRIBUTES, 'items': nonempty}
    linked = {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}
    return {'type': 'object', 'properties': {'selections': {'type': 'array', 'minItems': 1, 'maxItems': 1,
            'items': {'anyOf': [null, linked]}}}, 'required': ['selections'], 'additionalProperties': False}


def bundle_inventory(row):
    """Bounded source-only, occurrence-owned bundles; no gold or model output.

    Directly negated attributes remain in the catalog. The gate, not catalog
    construction, rejects their use. Enumeration omissions are explicit.
    """
    inverse = {eid: alias for alias, eid in row['reference_registry']['entities'].items()}
    prefix = row['reference_registry']['request_ref'].removesuffix(':r')
    inventory = row['support_inventory']
    bundles, counts = {}, []
    for eid in row['offered_entity_ids']:
        targets = [s for s in inventory['segments']
                   if s['contains_target'] and support._owned_by_target(s, row, eid)]
        compatible = [a for a in inventory['attributes']
                      if a['value'] in row['applicability'][eid][a['attribute']]
                      and support._owned_by_target(a, row, eid)]
        combinations = [[a] for a in compatible]
        if len(compatible) > 1:
            combinations.append(compatible)
        emitted = []
        skipped_limit = 0
        for claims in combinations:
            segments = list(dict.fromkeys([s['segment_alias'] for s in targets]
                            + [a['segment_alias'] for a in claims]))
            if (not targets or len(claims) > support.MAX_SELECTED_ATTRIBUTES
                    or len(segments) > support.MAX_SELECTED_SEGMENTS):
                skipped_limit += 1
                continue
            emitted.append((claims, segments))
        # Preserve the combined bundle when it fits rather than letting the
        # first sixteen individual anchors make it disappear silently.
        if len(emitted) > MAX_BUNDLES_PER_ENTITY:
            emitted = emitted[:MAX_BUNDLES_PER_ENTITY - 1] + emitted[-1:]
        for claims, segments in emitted:
            alias = prefix + ':b' + str(len(bundles))
            bundles[alias] = {'entity_alias': inverse[eid], 'segment_aliases': segments,
                'attribute_aliases': [a['attribute_alias'] for a in claims],
                'binding_sha256': _sha({'request_ref': row['request_ref'], 'entity_id': eid,
                                       'selection_binding': row['selection_binding']})}
        counts.append({'entity_alias': inverse[eid], 'total_combinations': len(combinations),
            'emitted_combinations': len(emitted), 'omitted_combinations': len(combinations) - len(emitted),
            'invalid_source_or_reference_limit_combinations': skipped_limit})
    return {'max_per_entity': MAX_BUNDLES_PER_ENTITY, 'bundles': bundles, 'combinations': counts,
            'omitted_combinations': sum(c['omitted_combinations'] for c in counts)}


def _visible(row):
    facts = support._visible(row)
    facts['bundles'] = deepcopy(row['bundle_inventory'])
    return facts


def _prompts(row):
    wire = BUNDLE_POLICY if row['condition'] == 'closure_bundle' else NULL_POLICY if _null_wire(row) else LEGACY_POLICY
    closure = CLOSURE_POLICY if row['condition'].startswith('closure_') else MANUAL_POLICY
    system = PROPOSAL_POLICY + '\n' + SEMANTIC_CHECK + '\n' + COMMON_POLICY + '\n' + wire + '\n' + closure
    fragment = json.dumps(_visible(row), ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    binding = {'request_ref': row['reference_registry']['request_ref'],
               **{k: deepcopy(row['selection_binding'][k]) for k in ('surface', 'core_span', 'full_span')}}
    user = ('원문:\n' + row['text'] + '\n\n용어와 근거 목록:\n' + fragment
            + '\n\n요청 발생 위치:\n' + json.dumps(binding, ensure_ascii=False, sort_keys=True, separators=(',', ':')))
    return system, user, fragment


def prepare_evidence_closure(*, records, tokenizers, models, code_revision, source_provenance):
    population = source_provenance.get('evaluation_population')
    if population not in {POPULATION, FRESH_POPULATION}:
        raise ValueError('explicit diagnostic or fresh confirmation population required')
    parent, _ = support.prepare_support_recovery(records=records, tokenizers=tokenizers, models=models,
        code_revision=code_revision, source_provenance=source_provenance,
        conditions=(support.BASELINE, 'multispan_supported_shadow'))
    bases = [r for r in parent['requests'] if r['condition'] == 'multispan_supported_shadow']
    originals = {r['case_id']: r for r in records}
    rows = []
    for index, base in enumerate(sorted(bases, key=lambda r: (r['document_sha256'], r['case_id']))):
        group = []
        for condition in CONDITIONS:
            row = deepcopy(base)
            row.update(experiment=EXPERIMENT, condition=condition, selector_variant=condition,
                request_ref=_request_ref(base['selection_binding'], condition),
                evidence_transport='support_bundle' if condition == 'closure_bundle' else 'multispan_ids',
                reference_closure=condition.startswith('closure_'),
                discriminated_abstention=_null_wire({'condition': condition}),
                document_length_band=originals[base['case_id']].get('document_length_band', 'short'))
            for field in SOURCE_STRATA_FIELDS:
                if field in originals[base['case_id']]:
                    row[field] = deepcopy(originals[base['case_id']][field])
            row['support_inventory'] = support.support_inventory(row)
            row['reference_registry'] = support.reference_registry(row)
            row['bundle_inventory'] = bundle_inventory(row)
            row['response_schema'] = evidence_closure_schema(row)
            row['system'], row['user'], row['prompt_fragment'] = _prompts(row)
            row['estimated_input_tokens'] = CharTokenCounter().count(row['system'] + row['user'])
            group.append(row)
        rotation = index % len(CONDITIONS)
        rows.extend(group[rotation:] + group[:rotation])
    validate_evidence_closure_requests(rows)
    proofs = {}
    for name, tokenizer in tokenizers.items():
        sizes = [len(_token_ids(tokenizer.apply_chat_template(
            [{'role': 'system', 'content': r['system']}, {'role': 'user', 'content': r['user']}],
            tokenize=True, add_generation_prompt=True, enable_thinking=False, return_dict=False))) for r in rows]
        if max(sizes) + RESERVED_OUTPUT_TOKENS > MAX_MODEL_LEN:
            raise ValueError('complete source and facts exceed model context: ' + name)
        proofs[name] = {'request_count': len(rows), 'path': models[name]['path'],
            'max_prompt_tokens': max(sizes), 'max_input_tokens': max(sizes), 'sum_input_tokens': sum(sizes),
            'reserved_output_tokens': RESERVED_OUTPUT_TOKENS, 'overflow_count': 0, 'fits_context': True,
            'apply_chat_template': True, 'enable_thinking': False, 'source': deepcopy(models[name]),
            'by_condition': {c: {'request_count': len(records),
                'sum_input_tokens': sum(n for r, n in zip(rows, sizes) if r['condition'] == c)} for c in CONDITIONS}}
    comparisons = [[BASELINE, 'closure_legacy'], [BASELINE, 'manual_null'], ['manual_null', 'closure_null'],
                   ['closure_legacy', 'closure_null'], ['closure_null', 'closure_bundle']]
    envelope = {'protocol': {'kind': 'ktrf_extended_v1', 'phase': 'FINAL_FROZEN', 'experiment': EXPERIMENT,
        'conditions': list(CONDITIONS), 'repeat_count': 1, 'response_schema_scope': 'per_request',
        'reserved_output_tokens': RESERVED_OUTPUT_TOKENS, 'evaluation_population': population,
        'execution_authority': 'none', 'evaluation_only': True, 'comparisons': comparisons, 'limitations': LIMITATIONS},
        'provenance': {'code_revision': code_revision, 'source': deepcopy(source_provenance)}, 'requests': rows}
    proof = {'file': EXPERIMENT + '.json', 'request_count': len(rows), 'question_count': len(records),
        'authored_documents': len(records), 'authored_families': len({r['family_id'] for r in records}),
        'conditions': list(CONDITIONS), 'models': proofs, 'repeat_count': 1, 'evaluation_population': population,
        'strata': dict(Counter(r['stratum'] for r in records)),
        'split_case_counts': dict(Counter(r['evaluation_split'] for r in records)),
        'source_records_sha256': records_sha256(records),
        'requests_sha256': hashlib.sha256(b''.join(canonical(r) for r in rows)).hexdigest(),
        'envelope_sha256': _sha(envelope), 'human_verified': False,
        'source_reused': population == POPULATION, 'source_gold_before_resolver': True,
        'independent_validation': False, 'no_deployment_risk_claim': True,
        'execution_authority': 'none', 'evaluation_only': True,
        'bundle_omitted_combinations_per_condition': {c: sum(r['bundle_inventory']['omitted_combinations']
            for r in rows if r['condition'] == c) for c in CONDITIONS}, 'limitations': LIMITATIONS}
    return envelope, proof


def evidence_closure_response_error(response, row):
    if not _null_wire(row):
        return support.support_recovery_response_error(response, row)
    if not isinstance(response, dict) or set(response) != {'selections'}:
        return 'selection_envelope_required'
    selections = response['selections']
    if not isinstance(selections, list) or len(selections) != 1 or not isinstance(selections[0], dict):
        return 'one_selection_required'
    selection = selections[0]
    if not isinstance(selection.get('r'), str) or not selection['r']:
        return 'request_reference_required'
    if 'e' not in selection:
        return 'entity_reference_required'
    if selection['e'] is None:
        return None if set(selection) == {'r', 'e'} else 'discriminated_abstention_fields_required'
    if not isinstance(selection['e'], str) or not selection['e'].strip():
        return 'nonnull_entity_id_must_be_string'
    if row['condition'] == 'closure_bundle':
        if set(selection) != {'r', 'e', 's', 'b'}:
            return 'exact_bundle_selection_fields_required'
        if not isinstance(selection['b'], str) or not selection['b']:
            return 'bundle_reference_required'
    else:
        if set(selection) != {'r', 'e', 's', 'q', 'a'}:
            return 'exact_wire_selection_fields_required'
        error = support.support_recovery_response_error(response, row)
        if error:
            return error
    if selection.get('s') != 'SUPPORT':
        return 'positive_assertion_support_required'
    return None


def closure_for_support_response(response, row):
    """Add source references to a valid old/new legacy response, never claims.

    This helper also supports frozen support-recovery rows for CPU replay.
    Replays are diagnostics, not new model outputs or prospective estimates.
    Invalid selections are returned unchanged and remain rejected by the gate.
    """
    result = deepcopy(response)
    metadata = {'applied': False, 'added_segment_count': 0, 'target_segment_count': 0,
                'attribute_parent_segment_count': 0, 'added_segment_aliases': [],
                'server_added_segments': [], 'blocked_reason': None}
    error = support.support_recovery_response_error(response, row)
    if error:
        metadata['blocked_reason'] = error
        return result, metadata
    selection = result['selections'][0]
    registry = row['reference_registry']
    if selection['r'] != registry['request_ref']:
        metadata['blocked_reason'] = 'unknown_or_stale_request_reference'
        return result, metadata
    if selection['e'] is None:
        # Do not normalize inconsistent old abstentions. The null-wire
        # experiment is a separate manipulation from reference completion.
        return result, metadata
    eid = registry['entities'].get(selection['e'])
    if eid is None:
        metadata['blocked_reason'] = 'unknown_or_stale_entity_reference'
        return result, metadata
    inventory = row['support_inventory']
    segments = {s['segment_alias']: s for s in inventory['segments']}
    attrs = {a['attribute_alias']: a for a in inventory['attributes']}
    if len(selection['q']) != len(set(selection['q'])) or len(selection['a']) != len(set(selection['a'])):
        metadata['blocked_reason'] = 'duplicate_source_reference'
    elif any(q not in segments for q in selection['q']):
        metadata['blocked_reason'] = 'unknown_or_stale_evidence_reference'
    elif any(a not in attrs for a in selection['a']):
        metadata['blocked_reason'] = 'unknown_or_stale_attribute_reference'
    elif any(not support._owned_by_target(segments[q], row, eid) for q in selection['q']):
        metadata['blocked_reason'] = 'evidence_owned_by_other_or_unresolved_occurrence'
    elif any(not support._owned_by_target(attrs[a], row, eid) for a in selection['a']):
        metadata['blocked_reason'] = 'attribute_owned_by_other_or_unresolved_occurrence'
    if metadata['blocked_reason']:
        return result, metadata
    targets = [s['segment_alias'] for s in inventory['segments']
               if s['contains_target'] and support._owned_by_target(s, row, eid)]
    parents = [attrs[a]['segment_alias'] for a in selection['a']]
    additions = [q for q in dict.fromkeys(targets + parents) if q not in selection['q']]
    if len(selection['q']) + len(additions) > support.MAX_SELECTED_SEGMENTS:
        metadata['blocked_reason'] = 'closure_segment_budget_exceeded'
        return result, metadata
    selection['q'].extend(additions)
    metadata.update(applied=bool(additions), added_segment_count=len(additions),
        target_segment_count=sum(q in targets for q in additions),
        attribute_parent_segment_count=sum(q in parents and q not in targets for q in additions),
        added_segment_aliases=additions, server_added_segments=deepcopy(additions))
    return result, metadata


def _canonical_response(response, row):
    error = evidence_closure_response_error(response, row)
    if error:
        return deepcopy(response), error
    selection = deepcopy(response['selections'][0])
    if _null_wire(row) and selection['e'] is None:
        selection.update(s='UNRESOLVED', q=[], a=[])
    elif row['condition'] == 'closure_bundle':
        bundle = row['bundle_inventory']['bundles'].get(selection.pop('b'))
        if bundle is None:
            selection.update(q=[], a=[])
            return {'selections': [selection]}, 'unknown_or_stale_bundle_reference'
        eid = row['reference_registry']['entities'].get(selection['e'])
        digest = _sha({'request_ref': row['request_ref'], 'entity_id': eid,
                       'selection_binding': row['selection_binding']})
        if bundle['entity_alias'] != selection['e'] or bundle['binding_sha256'] != digest:
            selection.update(q=[], a=[])
            return {'selections': [selection]}, 'bundle_entity_or_binding_mismatch'
        selection.update(q=deepcopy(bundle['segment_aliases']), a=deepcopy(bundle['attribute_aliases']))
    return {'selections': [selection]}, None


def grade_evidence_closure_response(response, row):
    wire_error = evidence_closure_response_error(response, row)
    converted, error = _canonical_response(response, row)
    raw = support.grade_support_recovery_response(converted, row)
    closed, closure = (closure_for_support_response(converted, row) if row['reference_closure'] and not error
                       else (deepcopy(converted), {'applied': False, 'added_segment_count': 0,
                           'target_segment_count': 0, 'attribute_parent_segment_count': 0,
                           'added_segment_aliases': [], 'server_added_segments': [], 'blocked_reason': error}))
    grade = support.grade_support_recovery_response(closed, row)
    if error:
        # A wire error or foreign bundle can never disappear through canonical
        # projection. Keep attempted/raw/rejected observations, but do not
        # count an invalid projection as a valid proposal or approval.
        grade.update(correct=False, malformed=wire_error is not None,
                     wire_valid=False, semantic_proposal_valid=False, guard_valid=False, evidence_gate_valid=False,
                     proposal_correct_id=False, proposal_wrong_id=False, proposal_abstention=False,
                     accepted_correct_id=False, accepted_wrong_id=False, correct_abstention=False,
                     over_abstention=False,
                     shadow_accepted_correct_id=False, shadow_accepted_wrong_id=False,
                     production_guard_accepted_correct_id=False, production_guard_accepted_wrong_id=False)
        grade['rejected_correct_id'] = bool(grade['attempted_nonnull'] and grade['raw_semantic_match'])
        grade['rejected_wrong_id'] = bool(grade['attempted_nonnull'] and not grade['raw_semantic_match'])
        grade['guard_violations'] = [{'kind': error}] + grade['guard_violations']
        grade['evidence_gate_violations'] = [{'kind': error}] + grade['evidence_gate_violations']
    selections = response.get('selections') if isinstance(response, dict) else None
    selection = (selections[0] if isinstance(selections, list) and len(selections) == 1
                 and isinstance(selections[0], dict) else {})
    attempted_null = 'e' in selection and selection['e'] is None
    null_wire_error = attempted_null and (wire_error is not None or any(
        v['kind'] == 'abstention_assertion_inconsistent' for v in grade['guard_violations']))
    grade.update(reference_closure=closure, server_added_segment_count=closure['added_segment_count'],
        server_added_segments=deepcopy(closure['server_added_segments']),
        raw_validation_valid=raw['guard_valid'] and not error,
        closed_validation_valid=grade['guard_valid'],
        null_wire_error=null_wire_error,
        raw_guard_valid=raw['guard_valid'] and not error,
        raw_evidence_gate_valid=raw['evidence_gate_valid'] and not error,
        raw_guard_violations=deepcopy(raw['guard_violations']),
        raw_accepted_correct_id=raw['accepted_correct_id'] and not error,
        raw_accepted_wrong_id=raw['accepted_wrong_id'] and not error,
        canonical_response=closed, discriminated_abstention=row['discriminated_abstention'],
        bundle_expanded=row['condition'] == 'closure_bundle' and not error
            and response['selections'][0]['e'] is not None)
    return grade


def validate_evidence_closure_requests(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError('nonempty evidence closure requests required')
    groups = defaultdict(list)
    for row in rows:
        condition = row.get('condition')
        if (condition not in CONDITIONS or row.get('experiment') != EXPERIMENT
                or row.get('task') != 'structured_routing' or row.get('repeat_id') != 0
                or row.get('selector') != 'ktrf' or row.get('selector_variant') != condition
                or row.get('control') != 'matched' or row.get('wire_schema') != 'compact'
                or row.get('semantic_check') is not True or row.get('evidence_gate') is not True
                or row.get('evidence_required') is not True or row.get('execution_contract') != 'occurrence_v1'
                or row.get('execution_authority') != 'none' or row.get('evaluation_only') is not True
                or row.get('authorization_mode') != 'shadow' or row.get('support_policy') != 'supported'
                or row.get('execution_guard') != 'evaluation_only_shadow_support'
                or row.get('reference_closure') is not condition.startswith('closure_')
                or row.get('discriminated_abstention') is not _null_wire(row)
                or row.get('evidence_transport') != ('support_bundle' if condition == 'closure_bundle' else 'multispan_ids')
                or row.get('response_schema') != evidence_closure_schema(row)
                or row.get('document_length_band') not in {'short', 'long'}
                or any(field in row and (not isinstance(row[field], str) or not row[field].strip())
                       for field in SOURCE_STRATA_FIELDS)
                or row.get('reserved_output_tokens') != RESERVED_OUTPUT_TOKENS
                or row.get('evaluation_population') not in {POPULATION, FRESH_POPULATION}):
            raise ValueError('condition, shadow authority or source support contract changed')
        if (row.get('source_reused') is not (row['evaluation_population'] == POPULATION)
                or row.get('source_origin_split') != row['evaluation_split']
                or row.get('original_evaluation_split') != row['evaluation_split']):
            raise ValueError('source population or original split changed')
        found = next((m for m in row['resolve_response']['mentions']
                      if m['span']['codepoint'] == row['target_core_span']), None)
        ids = sorted({m['entity_id'] for m in found.get('prediction_set', {}).get('members', [])
                      if m.get('entity_id')}) if found else []
        binding = row['selection_binding']
        if (row.get('human_verified') is not False or row.get('independent_validation') is not False
                or row['source_text'] != row['text']
                or row['document_sha256'] != hashlib.sha256(row['text'].encode()).hexdigest()
                or binding['document_hash'] != row['document_sha256']
                or row['pack']['document_hash'] != row['document_sha256']
                or binding['snapshot_id'] != row['pack']['snapshot']['snapshot_id']
                or binding['surface'] != row['target_surface'] or binding['core_span'] != row['target_core_span']
                or binding['mention_id'] != (found['mention_id'] if found else 'requested-target')
                or binding['full_span'] != (found.get('full_span', found['span'])['codepoint'] if found else row['target_full_span'])
                or row.get('binding_span_origin') != ('actual_resolver_occurrence' if found else 'requested_annotation_without_detection')
                or row['offered_entity_ids'] != ids or [c['entity_id'] for c in row['offered_cards']] != ids
                or row['pipeline_trace']['candidate_entity_ids'] != ids
                or row['facts_sha256'] != _sha(row['offered_cards'])
                or set(row['applicability']) != set(ids) or not row.get('source_records_sha256')
                or row['request_ref'] != _request_ref(binding, condition)
                or row['reference_registry'] != support.reference_registry(row)
                or row['support_inventory'] != support.support_inventory(row)
                or row['bundle_inventory'] != bundle_inventory(row)):
            raise ValueError('actual candidates, owned source anchors or occurrence binding changed')
        if _prompts(row) != (row['system'], row['user'], row['prompt_fragment']):
            raise ValueError('prompt differs from complete source and facts')
        if row['estimated_input_tokens'] != CharTokenCounter().count(row['system'] + row['user']):
            raise ValueError('prompt token estimate changed')
        groups[row['case_id']].append(row)
    fixed = ('text', 'document_sha256', 'family_id', 'document_id', 'parent_document_id', 'evaluation_split',
        'source_records_sha256', 'offered_entity_ids', 'offered_cards', 'applicability', 'source_aliases',
        'source_applicability', 'pack', 'selection_binding', 'resolve_response', 'pipeline_trace',
        'preparation_timing_ms', 'target_surface', 'target_core_span', 'target_full_span', 'gold', 'expected_entity_id',
        'document_length_band', *SOURCE_STRATA_FIELDS)
    for group in groups.values():
        if len(group) != len(CONDITIONS) or {r['condition'] for r in group} != set(CONDITIONS):
            raise ValueError('complete paired closure condition matrix required')
        if any(any(r.get(k) != group[0].get(k) for k in fixed) for r in group):
            raise ValueError('paired source or actual candidate facts changed')
    return rows
