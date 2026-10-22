"""Evaluation-only support recovery; production authorization is unchanged.

Literal source ownership is deliberately conservative and inspectable.  These
rules test a bounded hypothesis about missing evidence, not general entailment.
Every decision is a shadow observation and confers no execution authority.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import re

from eval import evidence_efficiency as efficiency
from eval.evidence_control import PROPOSAL_POLICY, _sha, evidence_inventory
from eval.hf_qa import canonical
from eval.prepare_followup import MAX_MODEL_LEN, _token_ids
from eval.review_business import SEMANTIC_CHECK, grade_business_response
from eval.routing_confirmation import ATTRIBUTES, RESERVED_OUTPUT_TOKENS, records_sha256
from ktrf.context import CharTokenCounter

EXPERIMENT = 'support_recovery'
POPULATION = 'REUSED_SEALED_SOURCE_DIAGNOSTIC'
FRESH_POPULATION = 'FRESH_AI_AUTHORED_CONFIRMATION'
CONDITIONS = ('paragraph_all_production', 'multispan_all_production',
              'multispan_observed_production', 'multispan_supported_production',
              'paragraph_all_shadow', 'multispan_all_shadow',
              'multispan_observed_shadow', 'multispan_supported_shadow')
BASELINE = CONDITIONS[0]
MAX_SELECTED_SEGMENTS = 8
MAX_SELECTED_ATTRIBUTES = 16
LIMITATIONS = [
    'All decisions are evaluation-only shadow observations with execution_authority=none; no action is executed.',
    'Production conditions retain the unchanged production occurrence guard; shadow conditions separately test source support without granting production authorization.',
    'Source facts and labels are AI authored and independently AI reviewed, not human gold or actual workplace records.',
    'Missing applicability values remain UNKNOWN and are never inferred to be true.',
    'Ownership uses known glossary spellings and a bounded nearest-mention discourse rule; it is not semantic entailment.',
    'All conditions retain complete source text and complete candidate definitions; only evidence policy and experimental judgment differ.',
    'Candidate retrieval and occurrence binding are produced by the actual resolver; gold is used only for scoring.',
    'Family clusters are statistical units; reused diagnostic sources are not an independent validation population.',
    'The paragraph baseline includes the new source-ownership and explicit-conflict checks; it is not numerically interchangeable with the preceding bundle-control baseline.',
]
POLICY = (
    '본 평가는 실행 없는 shadow 실험이며 어떤 출력도 실행 권한을 주지 않는다. '
    'selections 하나에 r=request_ref,e=entity_alias 또는 null,s=SUPPORT/CONTRADICT/UNRESOLVED, '
    'q=선택한 segment_alias 배열,a=선택한 attribute_alias 배열을 쓴다. '
    '제안하려면 요청한 발생 위치를 포함하는 근거와 같은 대상을 설명하는 근거만 선택한다. '
    '서로 다른 대상이나 다른 발생 위치의 속성을 빌리지 않는다. '
    '제공되지 않은 속성은 UNKNOWN이며 사전의 속성을 원문의 사실로 추정하지 않는다. '
    '명시적 모순, 문자열 예시, 다른 역할이나 파생 대상을 지칭하면 null로 둔다. '
    'null일 때 s=UNRESOLVED 또는 CONTRADICT,q=[],a=[]로 출력한다.'
)
COUNTRIES = ('대한민국', '한국', '북한', '독일', '프랑스', '영국', '미국', '일본', '중국',
             '핀란드', '덴마크', '노르웨이', '스웨덴', '칠레', '케냐', '아이슬란드', '캐나다',
             '호주', '뉴질랜드', '스페인', '포르투갈', '폴란드', '베트남', '태국', '인도',
             '싱가포르', '대만', '몽골', '브라질', '멕시코', '이탈리아', '네덜란드', '스위스')


def _conditions(conditions):
    chosen = tuple(CONDITIONS if conditions is None else conditions)
    if (len(chosen) != len(set(chosen)) or any(c not in CONDITIONS for c in chosen)
            or not (set(chosen) == set(CONDITIONS)
                    or len(chosen) == 2 and BASELINE in chosen)):
        raise ValueError('eight discovery conditions or baseline plus one selected condition required')
    return tuple(c for c in CONDITIONS if c in chosen)


def _request_ref(binding, condition):
    return 'sr-' + _sha({'protocol': 'support_recovery_v1', 'condition': condition, 'binding': binding})


def support_recovery_schema(row_or_condition):
    condition = row_or_condition['condition'] if isinstance(row_or_condition, dict) else row_or_condition
    if condition not in CONDITIONS:
        raise ValueError('unknown support recovery condition')
    nonempty = {'type': 'string', 'minLength': 1}
    properties = {'r': nonempty, 'e': {'anyOf': [nonempty, {'type': 'null'}]},
        's': {'type': 'string', 'enum': ['SUPPORT', 'CONTRADICT', 'UNRESOLVED']},
        'q': {'type': 'array', 'maxItems': MAX_SELECTED_SEGMENTS, 'items': nonempty},
        'a': {'type': 'array', 'maxItems': MAX_SELECTED_ATTRIBUTES, 'items': nonempty}}
    return {'type': 'object', 'properties': {'selections': {'type': 'array', 'minItems': 1, 'maxItems': 1,
        'items': {'type': 'object', 'properties': properties, 'required': list(properties),
                  'additionalProperties': False}}}, 'required': ['selections'], 'additionalProperties': False}


def _sentences(text):
    """Complete nonempty sentence units, retaining exact source coordinates."""
    result = []
    for line in re.finditer(r'[^\n]+', text):
        left = line.start()
        for part in re.finditer(r'.+?(?:[.!?](?=\s|$)|$)', line.group()):
            start, end = left + part.start(), left + part.end()
            while start < end and text[start].isspace():
                start += 1
            if start < end:
                result.append({'start': start, 'end': end, 'text': text[start:end]})
    return result


def _anchors(row):
    """Merge overlapping canonical/alias spellings into occurrence anchors."""
    matches = []
    for eid, aliases in row['source_aliases'].items():
        for alias in aliases:
            for match in re.finditer(re.escape(alias), row['text']):
                matches.append((match.start(), match.end(), eid))
    # The exact requested span is always an anchor, even if a variant spelling
    # was proposed by a channel rather than explicitly registered.
    full = row['target_full_span']
    matches.extend((full['start'], full['end'], eid) for eid in row['offered_entity_ids'])
    merged = []
    for start, end, eid in sorted(set(matches)):
        if merged and start < merged[-1]['end']:
            merged[-1]['end'] = max(end, merged[-1]['end'])
            merged[-1]['entity_ids'].add(eid)
        else:
            merged.append({'start': start, 'end': end, 'entity_ids': {eid}})
    return [{**anchor, 'entity_ids': sorted(anchor['entity_ids'])} for anchor in merged]


def _contains(segment, span):
    return segment['start'] <= span['start'] < span['end'] <= segment['end']


def support_inventory(row):
    """Source-only anchors; never inspect expected ID, labels or case strata.

    An unlabelled sentence may continue the nearest named occurrence at most
    four sentence units away. Ties and competing mentions remain unresolved.
    This permits ledger headers before a name, while a repeated spelling gets
    its own owner and cannot lend facts to the requested later occurrence.
    """
    if row['condition'].startswith('paragraph_'):
        paragraphs = evidence_inventory(row)['segments']
        units = [{k: s[k] for k in ('start', 'end', 'text')} for s in paragraphs]
    else:
        units = _sentences(row['text'])
    anchors = _anchors(row)
    # Locate anchors in sentence units even in paragraph mode. This keeps the
    # same discourse distances and exposes ambiguous ownership conservatively.
    sentences = _sentences(row['text'])
    anchor_indexes = [(a, next((i for i, s in enumerate(sentences) if _contains(s, a)), None)) for a in anchors]
    prefix = _sha({'request_ref': row['request_ref'], 'binding': row['selection_binding']})[:16]
    segments, attrs = [], []
    values = {name: sorted({v for facts in row['source_applicability'].values() for v in facts[name]})
              for name in ATTRIBUTES}
    for index, unit in enumerate(units):
        direct = [a for a in anchors if _contains(unit, a)]
        owners = direct
        if not owners:
            positions = [i for i, s in enumerate(sentences) if _contains(unit, s)]
            if positions:
                distances = [(min(abs(i - ai) for i in positions), a) for a, ai in anchor_indexes if ai is not None]
                nearest = min((d for d, _ in distances), default=99)
                owners = [a for d, a in distances if d == nearest] if nearest <= 4 else []
        segment = {**unit, 'segment_alias': prefix + ':q' + str(index), 'owners': deepcopy(owners),
                   'contains_target': _contains(unit, row['target_full_span']),
                   'ownership': 'explicit_mention' if direct else 'bounded_nearest_mention' if owners else 'UNKNOWN'}
        segments.append(segment)
        # Attribute ownership is evaluated on its own complete sentence, not an
        # entire paragraph which might contain a second, unrelated entity.
        for name in ATTRIBUTES:
            for value in values[name]:
                for match in re.finditer(re.escape(value), unit['text']):
                    start, end = unit['start'] + match.start(), unit['start'] + match.end()
                    sentence = next(s for s in sentences if s['start'] <= start < end <= s['end'])
                    own = [a for a in anchors if _contains(sentence, a)]
                    if not own:
                        si = sentences.index(sentence)
                        ds = [(abs(si - ai), a) for a, ai in anchor_indexes if ai is not None]
                        near = min((d for d, _ in ds), default=99)
                        own = [a for d, a in ds if d == near] if near <= 4 else []
                    attrs.append({'attribute_alias': prefix + ':a' + str(len(attrs)),
                        'segment_alias': segment['segment_alias'], 'attribute': name, 'value': value,
                        'start': start, 'end': end, 'owners': deepcopy(own)})
    return {'segments': segments, 'attributes': attrs, 'ownership_rule': 'nearest_named_occurrence_max_four_sentence_units_v1',
            'max_selected_segments': MAX_SELECTED_SEGMENTS, 'max_selected_attributes': MAX_SELECTED_ATTRIBUTES,
            'omissions': [], 'complete_source_preserved': True}


def reference_registry(row):
    prefix = _sha({'request_ref': row['request_ref'], 'binding': row['selection_binding']})[:16]
    return {'request_ref': prefix + ':r',
            'entities': {prefix + ':e' + str(i): eid for i, eid in enumerate(row['offered_entity_ids'])}}


def _visible(row):
    aliases = {v: k for k, v in row['reference_registry']['entities'].items()}
    inventory = row['support_inventory']
    def visible_owner(owner):
        return {'start': owner['start'], 'end': owner['end'],
                'entity_aliases': [aliases[eid] for eid in owner['entity_ids'] if eid in aliases]}
    return {'candidates': [{'entity_alias': aliases[c['entity_id']], 'canonical': c['canonical'],
                           'definition': c['definition'], 'applicability': row['applicability'][c['entity_id']]}
                          for c in row['offered_cards']],
        'segments': [{**{k: s[k] for k in ('segment_alias', 'text', 'contains_target', 'ownership')},
                      'owners': [visible_owner(o) for o in s['owners']]} for s in inventory['segments']],
        'attributes': [{**{k: a[k] for k in ('attribute_alias', 'segment_alias', 'attribute', 'value')},
                        'owners': [visible_owner(o) for o in a['owners']]} for a in inventory['attributes']],
        'ownership_rule': inventory['ownership_rule']}


def _prompts(row):
    mode = row['support_policy']
    requirement = {'all': '네 applicability 항목 모두를 원문에서 명시적으로 지지하는 속성 근거가 필요하다.',
        'observed': '원문에서 관측된 속성만 선택한다. 생략된 속성은 UNKNOWN으로 남기며 명시적 모순이 있으면 보류한다.',
        'supported': '원문에서 최소 한 개의 applicability 속성을 적극적으로 지지해야 한다. 미해결 충돌·부정·다른 역할·문자열 인용이면 보류한다.'}[mode]
    system = PROPOSAL_POLICY + '\n' + SEMANTIC_CHECK + '\n' + POLICY + '\n' + requirement
    fragment = json.dumps(_visible(row), ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    binding = {'request_ref': row['reference_registry']['request_ref'],
               **{k: row['selection_binding'][k] for k in ('surface', 'core_span', 'full_span')}}
    user = ('원문:\n' + row['text'] + '\n\n용어와 근거 목록:\n' + fragment
        + '\n\n요청 발생 위치:\n' + json.dumps(binding, ensure_ascii=False, sort_keys=True, separators=(',', ':')))
    return system, user, fragment


def prepare_support_recovery(*, records, tokenizers, models, code_revision, source_provenance, conditions=CONDITIONS):
    chosen = _conditions(conditions)
    population = source_provenance.get('evaluation_population')
    if population not in {POPULATION, FRESH_POPULATION}:
        raise ValueError('explicit diagnostic or fresh confirmation population required')
    proxy = {**deepcopy(source_provenance), 'evaluation_population': efficiency.POPULATION}
    envelope, _ = efficiency.prepare_evidence_efficiency(records=records, tokenizers=tokenizers, models=models,
        code_revision=code_revision, source_provenance=proxy)
    originals = {r['case_id']: r for r in records}
    bases = [r for r in envelope['requests'] if r['condition'] == 'evidence_compact']
    rows = []
    for index, base in enumerate(bases):
        original = originals[base['case_id']]
        source_aliases = {}
        for term in original.get('terms', []):
            eid = 'global:' + term['key']
            source_aliases[eid] = sorted(set([term['canonical']] + list(term.get('surfaces', []))))
        # _constraint_inventory already checks original metadata before this.
        source_applicability = deepcopy(original['entity_constraints'])
        group = []
        for condition in chosen:
            row = deepcopy(base)
            row.update(experiment=EXPERIMENT, condition=condition, selector='ktrf', selector_variant=condition,
                evaluation_population=population, source_reused=population == POPULATION,
                original_evaluation_split=base['evaluation_split'], source_origin_split=base['evaluation_split'],
                evidence_gate=True, evidence_required=True, evidence_transport='multispan_ids',
                execution_guard='production_occurrence_guard_plus_experimental_support' if condition.endswith('_production')
                                else 'evaluation_only_shadow_support',
                execution_authority='none', evaluation_only=True,
                authorization_mode=condition.rsplit('_', 1)[1],
                support_policy=condition.split('_')[1], source_aliases=deepcopy(source_aliases),
                source_applicability=deepcopy(source_applicability),
                request_ref=_request_ref(base['selection_binding'], condition))
            # Remove transport and routing artifacts belonging to the parent
            # experiment rather than silently carrying a second policy.
            for key in ('evidence_inventory', 'compact_projection', 'source_only_route', 'difficulty_gate'):
                row.pop(key, None)
            row['support_inventory'] = support_inventory(row)
            row['reference_registry'] = reference_registry(row)
            row['response_schema'] = support_recovery_schema(row)
            row['system'], row['user'], row['prompt_fragment'] = _prompts(row)
            row['estimated_input_tokens'] = CharTokenCounter().count(row['system'] + row['user'])
            group.append(row)
        rotation = index % len(chosen)
        rows.extend(group[rotation:] + group[:rotation])
    validate_support_recovery_requests(rows, chosen)
    proofs = {}
    for name, tokenizer in tokenizers.items():
        sizes = [len(_token_ids(tokenizer.apply_chat_template(
            [{'role': 'system', 'content': r['system']}, {'role': 'user', 'content': r['user']}],
            tokenize=True, add_generation_prompt=True, enable_thinking=False, return_dict=False))) for r in rows]
        if max(sizes) + RESERVED_OUTPUT_TOKENS > MAX_MODEL_LEN:
            raise ValueError('complete source and facts exceed context: ' + name)
        proofs[name] = {'request_count': len(rows), 'path': models[name]['path'],
            'max_prompt_tokens': max(sizes), 'max_input_tokens': max(sizes), 'sum_input_tokens': sum(sizes),
            'reserved_output_tokens': RESERVED_OUTPUT_TOKENS, 'overflow_count': 0, 'fits_context': True,
            'apply_chat_template': True, 'enable_thinking': False, 'source': deepcopy(models[name]),
            'by_condition': {c: {'request_count': len(records),
                'sum_input_tokens': sum(n for r, n in zip(rows, sizes) if r['condition'] == c)} for c in chosen}}
    envelope = {'protocol': {'kind': 'ktrf_extended_v1', 'phase': 'FINAL_FROZEN', 'experiment': EXPERIMENT,
        'conditions': list(chosen), 'repeat_count': 1, 'response_schema_scope': 'per_request',
        'reserved_output_tokens': RESERVED_OUTPUT_TOKENS, 'evaluation_population': population,
        'execution_authority': 'none', 'evaluation_only': True,
        'comparisons': [[BASELINE, c] for c in chosen if c != BASELINE], 'limitations': LIMITATIONS},
        'provenance': {'code_revision': code_revision, 'source': deepcopy(source_provenance)}, 'requests': rows}
    proof = {'file': EXPERIMENT + '.json', 'request_count': len(rows), 'question_count': len(records),
        'authored_documents': len(records), 'authored_families': len({r['family_id'] for r in records}),
        'conditions': list(chosen), 'models': proofs, 'repeat_count': 1, 'evaluation_population': population,
        'strata': dict(Counter(r['stratum'] for r in records)),
        'split_case_counts': dict(Counter(r['evaluation_split'] for r in records)),
        'source_records_sha256': records_sha256(records),
        'requests_sha256': hashlib.sha256(b''.join(canonical(r) for r in rows)).hexdigest(),
        'envelope_sha256': _sha(envelope), 'human_verified': False, 'source_gold_before_resolver': True,
        'independent_validation': False, 'no_deployment_risk_claim': True,
        'execution_authority': 'none', 'evaluation_only': True, 'limitations': LIMITATIONS}
    return envelope, proof


def support_recovery_response_error(response, row):
    if not isinstance(response, dict) or set(response) != {'selections'}:
        return 'selection_envelope_required'
    selections = response['selections']
    if not isinstance(selections, list) or len(selections) != 1 or not isinstance(selections[0], dict):
        return 'one_selection_required'
    selection = selections[0]
    if set(selection) != {'r', 'e', 's', 'q', 'a'}:
        return 'exact_wire_selection_fields_required'
    if not isinstance(selection['r'], str) or not selection['r']:
        return 'request_reference_required'
    if selection['e'] is not None and (not isinstance(selection['e'], str) or not selection['e'].strip()):
        return 'nonnull_entity_id_must_be_string'
    if not isinstance(selection['s'], str) or selection['s'] not in {'SUPPORT', 'CONTRADICT', 'UNRESOLVED'}:
        return 'assertion_assessment_required'
    for key, limit in (('q', MAX_SELECTED_SEGMENTS), ('a', MAX_SELECTED_ATTRIBUTES)):
        if (not isinstance(selection[key], list) or len(selection[key]) > limit
                or any(not isinstance(x, str) or not x for x in selection[key])):
            return 'source_reference_arrays_required'
    return None


def _owned_by_target(item, row, eid):
    target = row['target_full_span']
    owners = item['owners']
    return bool(len(owners) == 1 and owners[0]['start'] <= target['start'] < target['end'] <= owners[0]['end']
                and eid in owners[0]['entity_ids'])


def _source_vetoes(row, eid, segments):
    """Bounded explicit contradictions, scoped to target-owned sentences only."""
    owned = [s for s in support_inventory({**row, 'condition': 'multispan_observed_shadow'})['segments']
             if _owned_by_target(s, row, eid)]
    text = '\n'.join(s['text'] for s in owned)
    facts = row['applicability'][eid]
    violations = []
    # Omission of a negated claim by the model must not hide a contradiction.
    # Scan every target-owned source sentence, including unselected evidence.
    for name in ATTRIBUTES:
        for value in facts[name]:
            for match in re.finditer(re.escape(value), text):
                if re.match(r'[\s"\'”’]*(?:이|가|은|는|에)?\s*(?:아니|아닌)', text[match.end():match.end() + 24]):
                    violations.append({'kind': 'candidate_applicability_directly_negated', 'attribute': name})
    # Country lexemes are a fixed transparent list, rather than a semantic
    # inference from model confidence or a list derived from gold outcomes.
    countries = [c for c in COUNTRIES if c in text]
    allowed = facts['jurisdiction']
    if any(not any(c in value or value in c for value in allowed)
           and not re.search(r'별도|무관|적용하지|해당하지|제외', text[text.find(c) + len(c):][:65])
           for c in countries):
        violations.append({'kind': 'explicit_jurisdiction_conflict'})
    for name in ATTRIBUTES:
        for other in row['source_applicability'].values():
            for value in other[name]:
                if value in facts[name] or value not in text:
                    continue
                # An explicitly excluded rival is not positive evidence for
                # the rival. Retain the separate support of the requested name.
                tail = text[text.find(value) + len(value):][:55]
                if not re.search(r'아니|무관|별도|적용하지|해당하지|제외', tail):
                    violations.append({'kind': 'explicit_applicability_conflict', 'attribute': name})
    if (re.search(r'폐지|옛 |과거의|종료된|이름만 같|계승 관계.{0,5}없', text)
            and not any(re.search(r'폐지|옛|종료', v) for v in facts['temporal_status'])):
        violations.append({'kind': 'explicit_temporal_or_identity_conflict'})
    if re.search(r'비밀번호|예제 문자열|문자열 예시|실제.{0,12}지칭하지|소설|등장인물|공연 제목', text):
        violations.append({'kind': 'nonreferential_or_other_kind_context'})
    if re.search(r'이름.{0,5}같.{0,20}(?:뿐|별개)|독자적|독립.{0,12}(?:규칙|명령)|다른.{0,8}(?:대상|조직)|외부.{0,12}(?:장부|조선소|자료)|회사 업무가 아니', text):
        violations.append({'kind': 'explicit_separate_identity_context'})
    if re.search(r'어느.{0,20}(?:없|모르|못)|구별.{0,8}(?:없|못)|정할 수 없|구분할 수 없|복구할 수 없', text):
        violations.append({'kind': 'explicit_unresolved_identity_context'})
    found = next((m for m in row['resolve_response']['mentions']
                  if m['span']['codepoint'] == row['target_core_span']), None)
    # resolver._mention_response merges _surface_record directly into the
    # mention object. Absence means core=surface; UNKNOWN is never SAME_AS_CORE.
    identity = (found or {}).get('full_surface', {}).get('identity')
    if identity and identity != 'SAME_AS_CORE':
        violations.append({'kind': 'full_surface_structural_identity_not_same'})
    full = row['target_surface']
    if row['target_core_span'] != row['target_full_span'] or re.search(r'(?:담당자|기관장|위원장|노조|직원)$', full):
        violations.append({'kind': 'full_surface_role_or_composition'})
    return violations


def support_violations(selection, row, eid):
    """Resolve request-bound anchors and return explicit UNKNOWN attributes."""
    if eid is None:
        errors = ([] if selection['s'] in {'UNRESOLVED', 'CONTRADICT'} and not selection['q'] and not selection['a']
                  else [{'kind': 'abstention_assertion_inconsistent'}])
        return errors, [], list(ATTRIBUTES)
    errors = []
    if selection['s'] != 'SUPPORT':
        errors.append({'kind': 'positive_assertion_support_required'})
    inventory = row['support_inventory']
    segments = {s['segment_alias']: s for s in inventory['segments']}
    attrs = {a['attribute_alias']: a for a in inventory['attributes']}
    if len(set(selection['q'])) != len(selection['q']) or len(set(selection['a'])) != len(selection['a']):
        errors.append({'kind': 'duplicate_source_reference'})
    if any(q not in segments for q in selection['q']):
        errors.append({'kind': 'unknown_or_stale_evidence_reference'})
    if any(a not in attrs for a in selection['a']):
        errors.append({'kind': 'unknown_or_stale_attribute_reference'})
    chosen = [segments[q] for q in selection['q'] if q in segments]
    claims = [attrs[a] for a in selection['a'] if a in attrs]
    if not any(_contains(s, row['target_full_span']) for s in chosen):
        errors.append({'kind': 'evidence_does_not_contain_requested_occurrence'})
    if any(not _owned_by_target(s, row, eid) for s in chosen):
        errors.append({'kind': 'evidence_owned_by_other_or_unresolved_occurrence'})
    present = set()
    for claim in claims:
        name, value = claim['attribute'], claim['value']
        if claim['segment_alias'] not in selection['q']:
            errors.append({'kind': 'attribute_outside_selected_evidence'})
        if not _owned_by_target(claim, row, eid):
            errors.append({'kind': 'attribute_owned_by_other_or_unresolved_occurrence', 'attribute': name})
        if value not in row['applicability'][eid][name]:
            errors.append({'kind': 'entity_applicability_mismatch', 'attribute': name})
        elif _owned_by_target(claim, row, eid):
            present.add(name)
        right = claim['end']
        if row['text'][claim['start']:right] != value:
            errors.append({'kind': 'attribute_source_span_mismatch'})
        if re.match(r'[\s"\'”’]*(?:이|가|은|는|에)?\s*(?:아니|아닌)', row['text'][right:right + 24]):
            errors.append({'kind': 'claimed_value_directly_negated', 'attribute': name})
    missing = [name for name in ATTRIBUTES if name not in present]
    if row['support_policy'] == 'all' and missing:
        errors.append({'kind': 'complete_applicability_claims_required', 'missing': missing})
    if row['support_policy'] == 'supported' and not present:
        errors.append({'kind': 'positive_applicability_support_required'})
    if len(row['offered_entity_ids']) > 1:
        # A shared spelling alone cannot disambiguate. At least one claimed
        # source value must rule out every competing actual candidate.
        distinguishing = all(any(c['value'] not in row['applicability'][other][c['attribute']]
                                  for c in claims if _owned_by_target(c, row, eid))
                             for other in row['offered_entity_ids'] if other != eid)
        if not distinguishing:
            errors.append({'kind': 'unresolved_candidate_collision'})
    errors.extend(_source_vetoes(row, eid, chosen))
    return errors, [name for name in ATTRIBUTES if name in present], missing


def grade_support_recovery_response(response, row):
    error = support_recovery_response_error(response, row)
    selections = response.get('selections') if isinstance(response, dict) else None
    selection = selections[0] if isinstance(selections, list) and len(selections) == 1 and isinstance(selections[0], dict) else {}
    registry = row['reference_registry']
    alias = selection.get('e')
    selected = registry['entities'].get(alias) if isinstance(alias, str) else None
    nonnull = 'e' in selection and alias is not None
    raw_semantic = 'e' in selection and selected == row['expected_entity_id'] and not (nonnull and selected is None)
    wire_valid = error is None and selection['r'] == registry['request_ref']
    errors = [{'kind': error}] if error else []
    if not error and not wire_valid:
        errors.append({'kind': 'unknown_or_stale_request_reference'})
    if wire_valid and nonnull and selected is None:
        errors.append({'kind': 'unknown_or_stale_entity_reference'})
        wire_valid = False
    proposal_valid = wire_valid
    expanded = {'selections': [{**deepcopy(row['selection_binding']), 'entity_id': selected}]}
    base = grade_business_response(expanded, {**row, 'selector': 'ktrf'}) if proposal_valid else None
    base_valid = bool(base and base['guard_valid'])
    evidence_errors, present, unknown = (support_violations(selection, row, selected) if proposal_valid
                                          else ([], [], list(ATTRIBUTES)))
    evidence_valid = proposal_valid and not evidence_errors
    # Source identity is verified independently of production RESOLVED status.
    # The shadow path can test a context-disambiguated actual candidate but can
    # never grant execution authority or bypass source/binding integrity.
    identity_valid = bool(row.get('binding_span_origin') == 'actual_resolver_occurrence'
                          and row['selection_binding']['document_hash'] == row['document_sha256']
                          and row['selection_binding']['snapshot_id'] == row['pack']['snapshot']['snapshot_id'])
    shadow_valid = evidence_valid and (selected is None or identity_valid)
    chosen_valid = (base_valid and evidence_valid) if row['authorization_mode'] == 'production' else shadow_valid
    violations = errors + evidence_errors
    if row['authorization_mode'] == 'production' and base:
        violations += base['guard_violations']
    if nonnull and not identity_valid:
        violations.append({'kind': 'actual_occurrence_identity_required'})
    accepted = proposal_valid and chosen_valid
    return {'correct': raw_semantic and accepted, 'malformed': error is not None,
        'semantic_match': raw_semantic, 'raw_semantic_match': raw_semantic,
        'semantic_proposal_valid': proposal_valid, 'proposal_correct_id': proposal_valid and nonnull and raw_semantic,
        'proposal_wrong_id': proposal_valid and nonnull and not raw_semantic,
        'proposal_abstention': proposal_valid and not nonnull, 'wire_valid': wire_valid,
        'base_guard_valid': base_valid, 'production_base_guard_valid': base_valid,
        'production_guard_violations': deepcopy(base['guard_violations']) if base else [],
        'evidence_gate_valid': evidence_valid, 'evidence_gate_violations': evidence_errors,
        'guard_valid': accepted, 'guard_violations': violations,
        'positive_gold': row['positive_gold'], 'attempted_nonnull': nonnull,
        'accepted_correct_id': nonnull and raw_semantic and accepted,
        'accepted_wrong_id': nonnull and not raw_semantic and accepted,
        'rejected_correct_id': nonnull and raw_semantic and not accepted,
        'rejected_wrong_id': nonnull and not raw_semantic and not accepted,
        'correct_abstention': proposal_valid and not nonnull and not row['positive_gold'] and accepted,
        'over_abstention': proposal_valid and not nonnull and row['positive_gold'],
        'production_guard_accepted_correct_id': proposal_valid and nonnull and raw_semantic and base_valid,
        'production_guard_accepted_wrong_id': proposal_valid and nonnull and not raw_semantic and base_valid,
        'shadow_accepted_correct_id': proposal_valid and nonnull and raw_semantic and shadow_valid,
        'shadow_accepted_wrong_id': proposal_valid and nonnull and not raw_semantic and shadow_valid,
        'support_present_attributes': present, 'support_unknown_attributes': unknown,
        'authorization_mode': row['authorization_mode'], 'evaluation_only': True, 'execution_authority': 'none'}


def validate_support_recovery_requests(rows, conditions=None):
    if not isinstance(rows, list) or not rows:
        raise ValueError('nonempty support recovery requests required')
    chosen = _conditions(conditions if conditions is not None else {r.get('condition') for r in rows})
    groups = defaultdict(list)
    for row in rows:
        condition = row.get('condition')
        if (condition not in chosen or row.get('experiment') != EXPERIMENT
                or row.get('task') != 'structured_routing' or row.get('repeat_id') != 0
                or row.get('selector') != 'ktrf' or row.get('selector_variant') != condition
                or row.get('control') != 'matched' or row.get('wire_schema') != 'compact'
                or row.get('semantic_check') is not True or row.get('evidence_gate') is not True
                or row.get('evidence_required') is not True or row.get('execution_contract') != 'occurrence_v1'
                or row.get('execution_authority') != 'none' or row.get('evaluation_only') is not True
                or row.get('authorization_mode') != condition.rsplit('_', 1)[1]
                or row.get('execution_guard') != ('production_occurrence_guard_plus_experimental_support'
                    if condition.endswith('_production') else 'evaluation_only_shadow_support')
                or row.get('support_policy') != condition.split('_')[1]
                or row.get('response_schema') != support_recovery_schema(row)
                or row.get('reserved_output_tokens') != RESERVED_OUTPUT_TOKENS
                or row.get('evaluation_population') not in {POPULATION, FRESH_POPULATION}):
            raise ValueError('condition, shadow authority or support contract changed')
        if (row.get('source_reused') is not (row['evaluation_population'] == POPULATION)
                or row.get('source_origin_split') != row['evaluation_split']
                or row.get('original_evaluation_split') != row['evaluation_split']):
            raise ValueError('source population and original split identity changed')
        found = next((m for m in row['resolve_response']['mentions'] if m['span']['codepoint'] == row['target_core_span']), None)
        actual_ids = sorted({m['entity_id'] for m in found.get('prediction_set', {}).get('members', []) if m.get('entity_id')}) if found else []
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
                or row['offered_entity_ids'] != actual_ids
                or [c['entity_id'] for c in row['offered_cards']] != actual_ids
                or row['pipeline_trace']['candidate_entity_ids'] != actual_ids
                or row['facts_sha256'] != _sha(row['offered_cards'])
                or set(row['applicability']) != set(actual_ids)
                or not row.get('source_records_sha256')
                or row['request_ref'] != _request_ref(binding, condition)
                or row['reference_registry'] != reference_registry(row)
                or row['support_inventory'] != support_inventory(row)):
            raise ValueError('actual candidates, source anchors or immutable occurrence binding changed')
        if _prompts(row) != (row['system'], row['user'], row['prompt_fragment']):
            raise ValueError('prompt differs from complete source or candidate facts')
        if row['estimated_input_tokens'] != CharTokenCounter().count(row['system'] + row['user']):
            raise ValueError('prompt token estimate changed')
        groups[row['case_id']].append(row)
    fixed = ('text', 'document_sha256', 'family_id', 'document_id', 'parent_document_id', 'evaluation_split',
        'source_records_sha256', 'offered_entity_ids', 'offered_cards', 'applicability', 'source_aliases',
        'source_applicability', 'pack', 'selection_binding', 'resolve_response', 'pipeline_trace',
        'preparation_timing_ms', 'target_surface', 'target_core_span', 'target_full_span', 'gold', 'expected_entity_id')
    for group in groups.values():
        if len(group) != len(chosen) or {r['condition'] for r in group} != set(chosen):
            raise ValueError('complete paired support condition matrix required')
        if any(any(r.get(k) != group[0].get(k) for k in fixed) for r in group):
            raise ValueError('paired source or actual candidate facts changed')
    return rows


# Short aliases remain convenient for external diagnostic notebooks.
support_schema = support_recovery_schema
validate_support_requests = validate_support_recovery_requests
support_response_error = support_recovery_response_error
grade_support_response = grade_support_recovery_response
