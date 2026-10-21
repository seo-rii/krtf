"""Prospective source-matched evidence transport and selective checking experiment.

The source-only router is a conservative experimental cost heuristic. Literal
evidence consistency and the production occurrence guard are distinct checks;
neither is a general semantic entailment or deployment-risk guarantee.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import re
import time
from xml.sax.saxutils import escape, quoteattr

from eval.evidence_control import (
    PROPOSAL_POLICY, _prompts as _long_prompts,
    _sha, _visible_inventory, evidence_control_response_error,
    evidence_control_schema, evidence_inventory, grade_evidence_control_response,
)
from eval.prepare_followup import MAX_MODEL_LEN, _token_ids
from eval.review_business import SEMANTIC_CHECK, _prepare_record, business_snapshot
from eval.routing_confirmation import (
    ATTRIBUTES, RESERVED_OUTPUT_TOKENS, _constraint_inventory,
    _evidence_violations, _validate_records, records_sha256,
)
from ktrf.context import CharTokenCounter
from eval.hf_qa import canonical

EXPERIMENT = 'evidence_efficiency'
CONDITIONS = ('plain_matched', 'evidence_long', 'evidence_short',
              'evidence_compact', 'selective_compact')
POPULATION = 'FRESH_AI_AUTHORED_CONFIRMATION'
SHORT_POLICY = (
    '출력 selections 하나의 r은 request_ref, e는 entity_alias 또는 null이다. '
    '서버가 이 요청에 고정한 entity ID와 발생 위치를 복원한다. '
    '다른 요청의 별칭이나 근거를 사용하지 않는다.'
)
SHORT_EVIDENCE_POLICY = (
    '추가 근거 일치 검사: s는 SUPPORT, CONTRADICT, UNRESOLVED 중 하나다. '
    'e를 제안하려면 SUPPORT로 판단하고 요청한 발생 위치를 포함하는 q=segment_alias와 '
    '선택한 entity의 applicability 네 항목을 명시적으로 지지하는 a=attribute_alias 배열을 '
    '선택한다. 서버가 인용과 문자 위치를 복원한다. 직접 부정된 값이나 다른 대상의 '
    '속성을 선택하지 않는다. 근거가 부족하면 e=null,s=UNRESOLVED 또는 CONTRADICT,q=null,a=[]다.'
)
LIMITATIONS = [
    'Fresh source documents and glossary facts are AI authored and AI reviewed, not human gold or actual workplace records.',
    'All arms receive identical actual resolver candidates, complete source text, full candidate definitions and applicability facts.',
    'The long-ID arm retains the preceding evidence-control instruction and fact representation; short transport changes identifiers and response field names.',
    'Compact input is a reversible projection of the same complete facts and evidence catalog; no source, definitions, exceptions or applicability facts are clipped.',
    'Selective routing uses only source text, requested occurrence, actual candidate metadata and resolver observations before model inference; it does not inspect gold or model agreement.',
    'Easy selective cases omit the experimental evidence check but still use the identical unchanged production occurrence execution guard.',
    'Evidence checks enforce source literals, occurrence identity and narrow direct-negation vetoes, not semantic entailment or a deployment-risk guarantee.',
    'Fresh confirmation family clusters are the statistical units; the development split is reported separately and method selection must not reuse confirmation outcomes.',
]


def _request_ref(binding, condition):
    return 'ee-' + _sha({'protocol': 'evidence_efficiency_v1', 'condition': condition, 'binding': binding})


def _short_wire(row):
    return row['condition'] in {'evidence_short', 'evidence_compact', 'selective_compact'}


def evidence_efficiency_schema(row_or_condition):
    row = row_or_condition if isinstance(row_or_condition, dict) else {'condition': row_or_condition}
    condition = row['condition']
    if condition not in CONDITIONS:
        raise ValueError('unknown evidence efficiency condition')
    required = row.get('evidence_required', condition != 'plain_matched')
    if not _short_wire(row):
        return evidence_control_schema('ktrf_evidence_ids' if required else 'plain_matched')
    nonempty = {'type': 'string', 'minLength': 1}
    nullable = {'anyOf': [nonempty, {'type': 'null'}]}
    properties = {'r': nonempty, 'e': nullable}
    if required:
        properties.update(s={'type': 'string', 'enum': ['SUPPORT', 'CONTRADICT', 'UNRESOLVED']},
                          q=nullable, a={'type': 'array', 'maxItems': len(ATTRIBUTES), 'items': nonempty})
    return {'type': 'object', 'properties': {'selections': {'type': 'array',
        'minItems': 1, 'maxItems': 1, 'items': {'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False}}},
        'required': ['selections'], 'additionalProperties': False}


def reference_registry(row):
    """Request-bound short handles. Full binding is always restored server-side."""
    prefix = _sha({'request_ref': row['request_ref'], 'binding': row['selection_binding']})[:12]
    inventory = row['evidence_inventory']
    return {'request_ref': prefix + ':r',
        'entities': {prefix + ':e' + str(i): eid for i, eid in enumerate(row['offered_entity_ids'])},
        'segments': {prefix + ':q' + str(i): e['evidence_id'] for i, e in enumerate(inventory['segments'])},
        'attributes': {prefix + ':a' + str(i): a['attribute_id'] for i, a in enumerate(inventory['attributes'])}}


def _short_inventory(row):
    registry = row['reference_registry']
    entities = {v: k for k, v in registry['entities'].items()}
    segments = {v: k for k, v in registry['segments'].items()}
    attributes = {v: k for k, v in registry['attributes'].items()}
    inventory = _visible_inventory(row)
    return {'segments': [{'segment_alias': segments[e['evidence_id']], 'text': e['text']}
                         for e in inventory['segments']],
        'attributes': [{'attribute_alias': attributes[a['attribute_id']],
            'segment_alias': segments[a['evidence_id']], 'attribute': a['attribute'], 'value': a['value']}
                       for a in inventory['attributes']],
        'candidate_attribute_availability': {entities[eid]: facts for eid, facts in
                                              inventory['candidate_attribute_availability'].items()}}


def _short_facts(row):
    entities = {v: k for k, v in row['reference_registry']['entities'].items()}
    return [{'entity_alias': entities[c['entity_id']], 'canonical': c['canonical'],
             'definition': c['definition'], 'applicability': deepcopy(row['applicability'][c['entity_id']])}
            for c in row['offered_cards']]


def compact_projection(row):
    """Deduplicate keys and repeated segment text with a reversible table format."""
    inventory = _short_inventory(row)
    entities = {v: k for k, v in row['reference_registry']['entities'].items()}
    return {'attribute_order': list(ATTRIBUTES),
        'candidate_columns': ['entity_alias', 'canonical', 'definition', 'applicability'],
        'candidates': [[entities[c['entity_id']], c['canonical'], c['definition'],
                        [deepcopy(row['applicability'][c['entity_id']][name]) for name in ATTRIBUTES]]
                       for c in row['offered_cards']],
        'segment_columns': ['segment_alias', 'text'],
        'segments': [[s['segment_alias'], s['text']] for s in inventory['segments']],
        'attribute_columns': ['attribute_alias', 'segment_alias', 'attribute_index', 'value'],
        'attributes': [[a['attribute_alias'], a['segment_alias'], ATTRIBUTES.index(a['attribute']), a['value']]
                       for a in inventory['attributes']],
        'candidate_attribute_availability': {eid: [facts[name] for name in ATTRIBUTES]
                                            for eid, facts in inventory['candidate_attribute_availability'].items()}}


def expand_compact_projection(projection):
    """Canonical lossless reconstruction used to validate the frozen prompts."""
    if (projection.get('attribute_order') != list(ATTRIBUTES)
            or projection.get('candidate_columns') != ['entity_alias', 'canonical', 'definition', 'applicability']
            or projection.get('segment_columns') != ['segment_alias', 'text']
            or projection.get('attribute_columns') != ['attribute_alias', 'segment_alias', 'attribute_index', 'value']):
        raise ValueError('compact fact schema changed')
    facts = [{'entity_alias': alias, 'canonical': name, 'definition': definition,
              'applicability': dict(zip(ATTRIBUTES, values))}
             for alias, name, definition, values in projection['candidates']]
    inventory = {'segments': [{'segment_alias': alias, 'text': text} for alias, text in projection['segments']],
        'attributes': [{'attribute_alias': alias, 'segment_alias': segment,
                        'attribute': ATTRIBUTES[index], 'value': value}
                       for alias, segment, index, value in projection['attributes']],
        'candidate_attribute_availability': {eid: dict(zip(ATTRIBUTES, values))
                                            for eid, values in projection['candidate_attribute_availability'].items()}}
    return facts, inventory


def source_only_route(row):
    """Choose cost path without gold, case strata, rationale or model output."""
    reasons = []
    ids = row['offered_entity_ids']
    if row['resolver_status'] != 'RESOLVED':
        reasons.append('resolver_not_resolved')
    if len(ids) != 1:
        reasons.append('candidate_count_not_one')
    occurrences = list(re.finditer(re.escape(row['target_surface']), row['text']))
    if len(occurrences) != 1 or occurrences[0].start() != row['target_full_span']['start']:
        reasons.append('repeated_or_unmatched_surface')
    inventory = row['evidence_inventory']
    if len(inventory['segments']) != 1:
        reasons.append('no_unique_target_evidence')
    quote = inventory['segments'][0]['text'] if len(inventory['segments']) == 1 else ''
    # These broad indicators deliberately send even benign negation/quotation
    # to the checked path. They never block or approve an entity themselves.
    if re.search(r'''["'“”‘’「」『』]|인용|소설|가상|동명|예전|과거|폐지|직책|기관장|아니|아닌|않|제외|불가''', quote):
        reasons.append('quotation_negation_or_context_conflict_cue')
    supported = []
    for eid in ids:
        attrs = []
        for name in ATTRIBUTES:
            candidates = [a for a in inventory['attributes']
                          if a['attribute'] == name and a['value'] in row['applicability'][eid][name]]
            if len(candidates) != 1:
                break
            attrs.append(candidates[0])
        if len(attrs) == len(ATTRIBUTES) and inventory['segments']:
            segment = inventory['segments'][0]
            selection = {'entity_id': eid, 'assertion': {'assessment': 'SUPPORT',
                'evidence': {k: segment[k] for k in ('text', 'start', 'end')},
                'attributes': [{k: a[k] for k in ('attribute', 'value', 'start', 'end')} for a in attrs]}}
            if not _evidence_violations(selection, row):
                supported.append(eid)
    if len(supported) != 1 or len(ids) != 1:
        reasons.append('no_unique_explicit_four_attribute_support')
    # A second candidate's conflicting value in the same quote is a routing
    # reason even when the first candidate has all four literal values.
    if len(supported) == 1:
        own = row['applicability'][supported[0]]
        if any(value in quote and value not in own[name]
               for facts in row['applicability'].values() for name in ATTRIBUTES for value in facts[name]):
            reasons.append('competing_applicability_values')
    return {'path': 'evidence_compact' if reasons else 'plain_compact',
            'evidence_required': bool(reasons),
            'reasons': reasons or ['unique_occurrence_explicit_uncontested_applicability']}


def _prompts(row):
    if not _short_wire(row):
        proxy = {**row, 'condition': 'ktrf_evidence_ids' if row['evidence_required'] else 'plain_matched'}
        return _long_prompts(proxy)
    system = PROPOSAL_POLICY + '\n' + SEMANTIC_CHECK + '\n' + SHORT_POLICY
    # The full definitions and all applicability facts remain present in every
    # arm. Compactness concerns representation, not semantic summarization.
    if row['condition'] == 'evidence_short':
        # Preserve the long arm's XML facts and separate applicability/catalog
        # layout. Only request/entity/evidence handles and wire instructions
        # change here; table representation is isolated in the next arm.
        entities = {v: k for k, v in row['reference_registry']['entities'].items()}
        lines = ['<candidate_facts authority="semantic_reference_only">']
        for card in row['offered_cards']:
            lines.append('<entity entity_id=' + quoteattr(entities[card['entity_id']]) + ' canonical='
                         + quoteattr(card['canonical']) + '>' + escape(card['definition']) + '</entity>')
        fragment = '\n'.join(lines + ['</candidate_facts>'])
        fragment += '\nentity applicability:\n' + json.dumps(
            {entities[eid]: facts for eid, facts in row['applicability'].items()}, ensure_ascii=False, sort_keys=True)
    else:
        projection = deepcopy(row['compact_projection'])
        if not row['evidence_required']:
            # The router may omit the experimental catalog for easy cases; the
            # complete source and all entity reference facts are still present.
            for key in ('segments', 'attributes', 'candidate_attribute_availability'):
                projection.pop(key)
        fragment = 'reference_tables:\n' + json.dumps(projection, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    entities = {v: k for k, v in row['reference_registry']['entities'].items()}
    resolved = row['pipeline_trace']['resolved_entity_id']
    observation = {'status': row['resolver_status'], 'resolved_entity_id': entities.get(resolved),
                   'execution_authority': 'production_occurrence_guard_only'}
    fragment += '\nresolver observation:\n' + json.dumps(observation, ensure_ascii=False, sort_keys=True,
        **({} if row['condition'] == 'evidence_short' else {'separators': (',', ':')}))
    if row['condition'] == 'evidence_short' and row['evidence_required']:
        registry = row['reference_registry']
        segment_aliases = {v: k for k, v in registry['segments'].items()}
        attribute_aliases = {v: k for k, v in registry['attributes'].items()}
        visible = _visible_inventory(row)
        visible['segments'] = [{**s, 'evidence_id': segment_aliases[s['evidence_id']]} for s in visible['segments']]
        visible['attributes'] = [{**a, 'attribute_id': attribute_aliases[a['attribute_id']],
                                  'evidence_id': segment_aliases[a['evidence_id']]} for a in visible['attributes']]
        visible['candidate_attribute_availability'] = {entities[eid]: facts
            for eid, facts in visible['candidate_attribute_availability'].items()}
        fragment += '\nevidence_catalog:\n' + json.dumps(visible, ensure_ascii=False, sort_keys=True)
    if row['evidence_required']:
        system += '\n' + SHORT_EVIDENCE_POLICY
    binding = {'request_ref': row['reference_registry']['request_ref'], **{k: deepcopy(row['selection_binding'][k])
                                                                          for k in ('surface', 'core_span', 'full_span')}}
    user = ('원문:\n' + row['text'] + '\n\n제공된 용어 정보:\n' + fragment
        + '\n\n요청한 발생 위치의 request_binding:\n' + json.dumps(binding, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        + '\n해당 발생 위치의 전체 표현이 제공된 entity 자체를 지칭하는 경우에만 별칭을 제안한다.')
    return system, user, fragment


def prepare_evidence_efficiency(*, records, tokenizers, models, code_revision, source_provenance):
    if not code_revision or not tokenizers or set(tokenizers) != set(models):
        raise ValueError('frozen code and matching actual model tokenizers required')
    _validate_records(records, source_provenance)
    if (source_provenance.get('evaluation_population') != POPULATION
            or any(r['evaluation_split'] not in {'development', 'confirmation'} for r in records)):
        raise ValueError('fresh presealed development and confirmation sources required')
    snapshots, rows = {}, []
    for index, original in enumerate(sorted(records, key=lambda r: (r['document_sha256'], r['case_id']))):
        record = deepcopy(original)
        for term in record.get('terms', []):
            term.pop('applicability', None)
        record.setdefault('qa', {'requires_terminology': True})
        key = _sha({'family_id': record['family_id'], 'terms': record.get('terms'), 'glossary': record.get('glossary_data')})
        compile_ms = 0.0
        if key not in snapshots:
            started = time.perf_counter()
            snapshots[key] = business_snapshot(record)
            compile_ms = (time.perf_counter() - started) * 1000
        snapshot = snapshots[key]
        started = time.perf_counter()
        base = next(r for r in _prepare_record(record, snapshot) if r['condition'] == 'pipeline_ktrf_check')
        first_ms = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        warm = next(r for r in _prepare_record(record, snapshot) if r['condition'] == 'pipeline_ktrf_check')
        warm_ms = (time.perf_counter() - started) * 1000
        if any(base[k] != warm[k] for k in ('selection_binding', 'pipeline_trace', 'pack', 'resolve_response')):
            raise ValueError('warm preparation changed actual candidate identity')
        cards = []
        for eid in base['pipeline_trace']['candidate_entity_ids']:
            entity = snapshot.glossary.entity(eid)
            cards.append({'entity_id': eid, 'canonical': entity.canonical,
                          'definition': (entity.grounding or {}).get('short_definition') or entity.description or ''})
        group = []
        for condition in CONDITIONS:
            row = deepcopy(base)
            detected = any(m['span']['codepoint'] == row['target_core_span'] for m in row['resolve_response']['mentions'])
            row.update(experiment=EXPERIMENT, condition=condition, control='matched',
                selector='plain' if condition == 'plain_matched' else 'ktrf', selector_variant=condition,
                wire_schema='compact', evaluation_population=POPULATION,
                evidence_transport='ids', execution_guard='common_production_occurrence_v1',
                offered_cards=deepcopy(cards), offered_entity_ids=[c['entity_id'] for c in cards],
                facts_sha256=_sha(cards), applicability=_constraint_inventory(record, [c['entity_id'] for c in cards]),
                request_ref=_request_ref(base['selection_binding'], condition),
                source_records_sha256=source_provenance['records_sha256'], reserved_output_tokens=RESERVED_OUTPUT_TOKENS,
                binding_span_origin='actual_resolver_occurrence' if detected else 'requested_annotation_without_detection',
                preparation_timing_ms={'snapshot_compile': compile_ms, 'first_prepare': first_ms, 'warm_prepare': warm_ms})
            row['evidence_inventory'] = evidence_inventory(row)
            row['reference_registry'] = reference_registry(row)
            row['compact_projection'] = compact_projection(row)
            row['source_only_route'] = source_only_route(row)
            row['difficulty_gate'] = {'easy': not row['source_only_route']['evidence_required'],
                                      'reasons': list(row['source_only_route']['reasons'])}
            row['evidence_required'] = condition != 'plain_matched' and (condition != 'selective_compact'
                                                        or row['source_only_route']['evidence_required'])
            row['evidence_gate'] = row['evidence_required']
            row['response_schema'] = evidence_efficiency_schema(row)
            row['system'], row['user'], row['prompt_fragment'] = _prompts(row)
            row['estimated_input_tokens'] = CharTokenCounter().count(row['system'] + row['user'])
            group.append(row)
        rotation = index % len(CONDITIONS)
        rows.extend(group[rotation:] + group[:rotation])
    validate_evidence_efficiency_requests(rows)
    proofs = {}
    for name, tokenizer in tokenizers.items():
        sizes = [len(_token_ids(tokenizer.apply_chat_template(
            [{'role': 'system', 'content': row['system']}, {'role': 'user', 'content': row['user']}],
            tokenize=True, add_generation_prompt=True, enable_thinking=False, return_dict=False))) for row in rows]
        if max(sizes) + RESERVED_OUTPUT_TOKENS > MAX_MODEL_LEN:
            raise ValueError('complete source and facts exceed model context: ' + name)
        proofs[name] = {'request_count': len(rows), 'path': models[name]['path'],
            'max_prompt_tokens': max(sizes), 'max_input_tokens': max(sizes), 'sum_input_tokens': sum(sizes),
            'reserved_output_tokens': RESERVED_OUTPUT_TOKENS, 'overflow_count': 0, 'fits_context': True,
            'apply_chat_template': True, 'enable_thinking': False, 'source': deepcopy(models[name]),
            'by_condition': {c: {'request_count': len(records),
                'sum_input_tokens': sum(n for r, n in zip(rows, sizes) if r['condition'] == c)} for c in CONDITIONS}}
    envelope = {'protocol': {'kind': 'ktrf_extended_v1', 'phase': 'FINAL_FROZEN', 'experiment': EXPERIMENT,
        'conditions': list(CONDITIONS), 'repeat_count': 1, 'response_schema_scope': 'per_request',
        'reserved_output_tokens': RESERVED_OUTPUT_TOKENS, 'evaluation_population': POPULATION,
        'comparisons': [['plain_matched', 'evidence_long'], ['evidence_long', 'evidence_short'],
            ['evidence_short', 'evidence_compact'], ['evidence_compact', 'selective_compact']],
        'limitations': LIMITATIONS},
        'provenance': {'code_revision': code_revision, 'source': deepcopy(source_provenance)}, 'requests': rows}
    proof = {'file': EXPERIMENT + '.json', 'request_count': len(rows), 'question_count': len(records),
        'authored_documents': len(records), 'authored_families': len({r['family_id'] for r in records}),
        'conditions': list(CONDITIONS), 'models': proofs, 'repeat_count': 1, 'evaluation_population': POPULATION,
        'strata': dict(Counter(r['stratum'] for r in records)),
        'split_case_counts': dict(Counter(r['evaluation_split'] for r in records)),
        'selective_route_counts': dict(Counter(r['source_only_route']['path'] for r in rows if r['condition'] == 'selective_compact')),
        'selective_route_reasons': dict(Counter(reason for r in rows if r['condition'] == 'selective_compact'
                                               for reason in r['source_only_route']['reasons'])),
        'source_records_sha256': records_sha256(records),
        'requests_sha256': hashlib.sha256(b''.join(canonical(r) for r in rows)).hexdigest(),
        'envelope_sha256': _sha(envelope), 'human_verified': False,
        'source_gold_before_resolver': True, 'independent_validation': False,
        'no_deployment_risk_claim': True, 'limitations': LIMITATIONS}
    return envelope, proof


def _expand_response(response, row):
    """Restore request-bound entity and evidence handles without trusting offsets."""
    if not _short_wire(row):
        return deepcopy(response), []
    selection = response['selections'][0]
    registry = row['reference_registry']
    violations = []
    if selection['r'] != registry['request_ref']:
        violations.append({'kind': 'unknown_or_stale_request_reference'})
    alias = selection['e']
    if alias is not None and alias not in registry['entities']:
        violations.append({'kind': 'unknown_or_stale_entity_reference'})
    expanded = {'request_ref': row['request_ref'] if selection['r'] == registry['request_ref'] else selection['r'],
                'entity_id': registry['entities'].get(alias) if alias is not None else None}
    if row['evidence_required']:
        q, attrs = selection['q'], selection['a']
        if q is not None and q not in registry['segments']:
            violations.append({'kind': 'unknown_or_stale_evidence_reference'})
        if any(a not in registry['attributes'] for a in attrs):
            violations.append({'kind': 'unknown_or_stale_attribute_reference'})
        expanded['assertion'] = {'assessment': selection['s'],
            'evidence_id': registry['segments'].get(q) if q is not None else None,
            'attribute_ids': [registry['attributes'].get(a, a) for a in attrs]}
    return {'selections': [expanded]}, violations


def evidence_efficiency_response_error(response, row):
    if not _short_wire(row):
        proxy = {**row, 'condition': 'ktrf_evidence_ids' if row['evidence_required'] else 'plain_matched'}
        return evidence_control_response_error(response, proxy)
    if not isinstance(response, dict) or set(response) != {'selections'}:
        return 'selection_envelope_required'
    selections = response['selections']
    if not isinstance(selections, list) or len(selections) != 1 or not isinstance(selections[0], dict):
        return 'one_selection_required'
    selection = selections[0]
    expected = set(evidence_efficiency_schema(row)['properties']['selections']['items']['required'])
    if set(selection) != expected:
        return 'exact_wire_selection_fields_required'
    if not isinstance(selection['r'], str) or not selection['r']:
        return 'request_reference_required'
    if selection['e'] is not None and (not isinstance(selection['e'], str) or not selection['e'].strip()):
        return 'nonnull_entity_id_must_be_string'
    if row['evidence_required']:
        if not isinstance(selection['s'], str) or selection['s'] not in {'SUPPORT', 'CONTRADICT', 'UNRESOLVED'}:
            return 'assertion_assessment_required'
        if selection['q'] is not None and (not isinstance(selection['q'], str) or not selection['q']):
            return 'evidence_reference_required'
        if (not isinstance(selection['a'], list) or len(selection['a']) > len(ATTRIBUTES)
                or any(not isinstance(a, str) or not a for a in selection['a'])):
            return 'attribute_references_required'
    return None


def grade_evidence_efficiency_response(response, row):
    error = evidence_efficiency_response_error(response, row)
    proxy = {**row, 'condition': 'ktrf_evidence_ids' if row['evidence_required'] else 'plain_matched'}
    if error:
        grade = grade_evidence_control_response({}, proxy)
        grade['guard_violations'] = [{'kind': error}]
        return grade
    expanded, violations = _expand_response(response, row)
    grade = grade_evidence_control_response(expanded, proxy)
    if violations:
        had_correct = grade['proposal_correct_id']
        had_wrong = grade['proposal_wrong_id']
        unknown_entity = any(v['kind'] == 'unknown_or_stale_entity_reference' for v in violations)
        grade.update(correct=False, semantic_proposal_valid=False, wire_valid=False,
            proposal_correct_id=False, proposal_wrong_id=False, proposal_abstention=False,
            base_guard_valid=False, evidence_gate_valid=False, guard_valid=False,
            accepted_correct_id=False, accepted_wrong_id=False, correct_abstention=False,
            over_abstention=False, rejected_correct_id=had_correct, rejected_wrong_id=had_wrong,
            guard_violations=grade['guard_violations'] + violations)
        if unknown_entity:
            grade.update(semantic_match=False, raw_semantic_match=False, attempted_nonnull=True,
                         rejected_wrong_id=True)
    return grade


def validate_evidence_efficiency_requests(rows):
    if not isinstance(rows, list) or not rows or len(rows) % len(CONDITIONS):
        raise ValueError('complete five-condition matrix required')
    groups = defaultdict(list)
    for row in rows:
        condition = row.get('condition')
        expected_gate = condition != 'plain_matched' and (condition != 'selective_compact'
                                       or row.get('source_only_route', {}).get('evidence_required'))
        if (condition not in CONDITIONS or row.get('experiment') != EXPERIMENT
                or row.get('task') != 'structured_routing' or row.get('repeat_id') != 0
                or row.get('control') != 'matched' or row.get('selector_variant') != condition
                or row.get('selector') != ('plain' if condition == 'plain_matched' else 'ktrf')
                or row.get('wire_schema') != 'compact' or row.get('semantic_check') is not True
                or row.get('execution_contract') != 'occurrence_v1'
                or row.get('execution_guard') != 'common_production_occurrence_v1'
                or row.get('evidence_required') is not expected_gate or row.get('evidence_gate') is not expected_gate
                or row.get('evidence_transport') != 'ids'
                or row.get('response_schema') != evidence_efficiency_schema(row)
                or row.get('reserved_output_tokens') != RESERVED_OUTPUT_TOKENS):
            raise ValueError('condition, evidence, schema or common guard changed')
        if (row.get('evaluation_population') != POPULATION
                or row.get('evaluation_split') not in {'development', 'confirmation'}
                or row.get('human_verified') is not False or row.get('independent_validation') is not False
                or row.get('source_text') != row.get('text')
                or row.get('document_sha256') != hashlib.sha256(row['text'].encode()).hexdigest()
                or row['pack']['document_hash'] != row['document_sha256']
                or row['selection_binding'].get('document_hash') != row['document_sha256']
                or row['selection_binding'].get('snapshot_id') != row['pack']['snapshot']['snapshot_id']
                or row['selection_binding'].get('surface') != row['target_surface']
                or row['selection_binding'].get('core_span') != row['target_core_span']):
            raise ValueError('source population or occurrence identity changed')
        found = next((m for m in row['resolve_response']['mentions'] if m['span']['codepoint'] == row['target_core_span']), None)
        expected_span = found.get('full_span', found['span'])['codepoint'] if found else row['target_full_span']
        expected_mention = found['mention_id'] if found else 'requested-target'
        expected_origin = 'actual_resolver_occurrence' if found else 'requested_annotation_without_detection'
        if (row['selection_binding'].get('full_span') != expected_span
                or row['selection_binding'].get('mention_id') != expected_mention
                or row.get('binding_span_origin') != expected_origin):
            raise ValueError('actual resolver authorization binding changed')
        actual = sorted({m['entity_id'] for m in found.get('prediction_set', {}).get('members', []) if m.get('entity_id')}) if found else []
        if (row['offered_entity_ids'] != actual or [c['entity_id'] for c in row['offered_cards']] != actual
                or row['pipeline_trace']['candidate_entity_ids'] != actual
                or row['facts_sha256'] != _sha(row['offered_cards']) or set(row['applicability']) != set(actual)
                or not row.get('source_records_sha256')
                or row['request_ref'] != _request_ref(row['selection_binding'], condition)
                or row['evidence_inventory'] != evidence_inventory(row)
                or row['reference_registry'] != reference_registry(row)
                or row['compact_projection'] != compact_projection(row)
                or expand_compact_projection(row['compact_projection']) != (_short_facts(row), _short_inventory(row))
                or row['source_only_route'] != source_only_route(row)
                or row['difficulty_gate'] != {'easy': not row['source_only_route']['evidence_required'],
                                               'reasons': list(row['source_only_route']['reasons'])}):
            raise ValueError('candidate facts, lossless projection, source-only routing or immutable references changed')
        if (_prompts(row) != (row['system'], row['user'], row['prompt_fragment'])
                or row['estimated_input_tokens'] != CharTokenCounter().count(row['system'] + row['user'])):
            raise ValueError('prompt differs from complete frozen source facts')
        groups[row['case_id']].append(row)
    fixed = ('family_id', 'document_id', 'parent_document_id', 'evaluation_split', 'document_sha256',
        'text', 'target_surface', 'target_span', 'target_core_span', 'target_full_span', 'gold',
        'expected_entity_id', 'selection_binding', 'pack', 'resolve_response', 'pipeline_trace',
        'source_records_sha256', 'preparation_timing_ms', 'offered_cards', 'offered_entity_ids', 'applicability',
        'source_only_route', 'difficulty_gate', 'binding_span_origin')
    for group in groups.values():
        if len(group) != len(CONDITIONS) or {r['condition'] for r in group} != set(CONDITIONS):
            raise ValueError('complete paired source matrix required')
        if any(any(row.get(k) != group[0].get(k) for k in fixed) for row in group):
            raise ValueError('paired conditions changed source or actual candidate facts')
    return rows
