"""Experimental, opt-in lexical evidence for exact alias collisions.

This is a deliberately small definition recognizer, not a semantic model or a
calibrated confidence estimator. It accepts a full registered canonical name or
definition only when an explicit identity statement ties it to the target.
Ordinary contextual similarity, pronoun references, adjacent bare definitions,
examples, and unrelated name occurrences do not authorize a choice. The resolver
must still enforce every structural guard. Denial checks are lexical and bounded
to the target paragraph and the following paragraph, not a semantic guarantee.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ContextResolutionEvidence:
    chosen_entity_id: str | None = None
    support_span: tuple[int, int] | None = None
    support_quote: str | None = None
    anchor_span: tuple[int, int] | None = None
    evidence_type: str | None = None
    abstention_reason: str | None = None
    status: str = "EXPERIMENTAL_HEURISTIC"
    scope: str | None = None


_PARAGRAPH_BREAK = re.compile(r"\n[ \t\r]*\n+")
_SENTENCE_END = re.compile(r"[.!?。？！](?=\s|$)")
_COPULA = re.compile(r"(?:이다|다|입니다|임)[.。]*$")
_DIRECT_PREFIX = re.compile(r"(?:은|는|란|이란)(?:\s+바로)?\s*$")
_DIRECT_NAME_SUFFIX = re.compile(r"\)(?:이다|다|입니다|임)?[.。]*$")
_BENIGN_LOCATIVE_PREFIX = re.compile(r"(?:이\s*(?:업무\s*)?문서에서|이번\s*요청에서)\s*$")
# Sentence-level vetoes inspect the assertion outside registered anchors.
# Operational warnings in other sentences are not identity contradictions.
_UNSUPPORTED_CONTEXT = re.compile(
    r"아니|않|없|못|제외|무관|미등록|등록되지|비언급|보통명사|"
    r"문자열|입력 견본|입력견본|상표|상품명|행사명|비유|"
    r"개인|책임자|직함|센터장|팀장|실장|원장|노조|"
    r"만약|가정|예시|예문|추정|불확실|미확인|모르|[?？]|"
    r"틀리|틀린|틀렸|거짓|허위|오해|반례|오인"
)
_CLAIM_SUBJECT = (
    r"(?:(?:그|이|위|앞의|해당)\s*)?"
    r"(?:설명|주장|정의|해석|진술|문구|문장|이름|명칭|용어|표현|낱말|단어|대상)"
)
_SCOPED_IDENTITY_CONTRADICTION = re.compile(
    # A denial belongs to the same clause as its identity/claim subject. An
    # affirmative declaration followed by a comma and a denial of an example
    # is not itself denied (e.g. "이 설명은 명칭 선언이며, 예시가 아니다").
    _CLAIM_SUBJECT + r"[^,;\n.!?。？！]{0,40}"
    r"(?:틀리|틀린|틀렸|거짓|허위|오해|오류|아니|않|없|못|미등록|등록되지|"
    r"예시|예문|상품명|행사명|상표|보통명사|입력\s*견본|비유|추정|불확실|미확인)"
    r"|" + _CLAIM_SUBJECT + r"(?:을|를|은|는)?\s*(?:정정|철회|번복)"
    r"|(?:여기서는|이번에|이\s*(?:업무\s*)?문서에서|"
    r"전체\s*표현|표현\s*전체|(?:그|이)\s*(?:이름|명칭|용어|표현|낱말|대상|물체))"
    r"[^,;\n.!?。？！]{0,60}(?:개인|책임자|직함|센터장|팀장|실장|원장|노조|"
    r"미등록|등록되지|입력\s*견본|무관|상품명|행사명|상표|비유)"
    r"|(?:입력\s*견본|시험\s*문자열|문자열\s*견본|비언급|보통명사)"
    r"|(?:주장|설명|정의|해석|진술|문구)[^,;\n.!?。？！]{0,40}사실과\s*다르"
)
_QUOTES = frozenset('"\'“”‘’「」『』')


def _normalize_with_offsets(text: str) -> tuple[str, list[int]]:
    """Normalize spacing/compatibility forms while retaining raw offsets.

    Spaces remain significant: this does not manufacture an anchor by removing
    Korean word boundaries or punctuation. Quote wrappers are ignored so a
    directly asserted quoted name can still be recognized.
    """
    chars: list[str] = []
    offsets: list[int] = []
    for offset, char in enumerate(text):
        for folded in unicodedata.normalize("NFKC", char):
            if folded in _QUOTES:
                continue
            if folded.isspace():
                if not chars or chars[-1] == " ":
                    continue
                folded = " "
            chars.append(folded)
            offsets.append(offset)
    while chars and chars[-1] == " ":
        chars.pop()
        offsets.pop()
    return "".join(chars), offsets


def _normalize(text: str) -> str:
    return _normalize_with_offsets(text)[0]


def _paragraphs(text: str) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    start = 0
    for match in _PARAGRAPH_BREAK.finditer(text):
        if text[start:match.start()].strip():
            result.append((start, match.start()))
        start = match.end()
    if text[start:].strip():
        result.append((start, len(text)))
    return result


def _sentences(text: str, start: int, end: int) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    cursor = start
    for match in _SENTENCE_END.finditer(text, start, end):
        if text[cursor:match.end()].strip():
            result.append((cursor, match.end()))
        cursor = match.end()
    if text[cursor:end].strip():
        result.append((cursor, end))
    return result


def _anchor_occurrences(text: str, start: int, end: int, anchor: str):
    normalized, offsets = _normalize_with_offsets(text[start:end])
    cursor = 0
    while True:
        found = normalized.find(anchor, cursor)
        if found < 0:
            return
        finish = found + len(anchor)
        cursor = finish
        # A full anchor inside a longer lexical item is insufficient evidence.
        if found and normalized[found - 1].isalnum():
            continue
        raw_start = start + offsets[found]
        raw_end = start + offsets[finish - 1] + 1
        yield raw_start, raw_end


def _quotation_spans(text: str) -> tuple[list[tuple[int, int]], bool]:
    """Find paired quote wrappers; malformed quoting is not assertion evidence."""
    pairs = {'"': '"', "'": "'", '“': '”', '‘': '’',
             '「': '」', '『': '』'}
    stack: list[tuple[str, int]] = []
    spans: list[tuple[int, int]] = []
    for offset, char in enumerate(text):
        if char not in _QUOTES:
            continue
        if stack and char == stack[-1][0]:
            _, opening = stack.pop()
            spans.append((opening, offset + 1))
        elif char in pairs:
            stack.append((pairs[char], offset))
        else:
            return spans, True
    return spans, bool(stack)


def _identity_relation(text: str, target: tuple[int, int],
                       anchor: tuple[int, int], sentences: list[tuple[int, int]]
                       ) -> str | None:
    """Require a target-subject assertion in the same sentence.

    A closed set of benign document/request locatives may precede the subject.

    Pronouns and bare adjacent definitions have no verified antecedent. Quoted
    target names or registered names remain valid when their identity assertion
    is outside the quotation; quoted assertions themselves are insufficient.
    """
    bounds = next((bounds for bounds in sentences
                   if bounds[0] <= target[0] < bounds[1]), None)
    if (bounds is None or not bounds[0] <= anchor[0] < bounds[1]
            or anchor[0] < target[1]):
        return None
    # Subject must begin the assertion after an optional benign locative.
    # Arbitrary introductory text can turn an embedded statement into a
    # citation, example, or false claim.
    prefix = _normalize(text[bounds[0]:target[0]])
    if prefix and not _BENIGN_LOCATIVE_PREFIX.fullmatch(prefix):
        return None
    raw_sentence = text[bounds[0]:bounds[1]]
    quote_spans, malformed = _quotation_spans(raw_sentence)
    if malformed:
        return None
    for opening, closing in quote_spans:
        quote_start, quote_end = bounds[0] + opening, bounds[0] + closing
        for item in (target, anchor):
            if quote_start < item[0] and item[1] < quote_end:
                body = text[quote_start + 1:quote_end - 1]
                if _normalize(body) != _normalize(text[item[0]:item[1]]):
                    return None
    between = _normalize(text[target[1]:anchor[0]])
    suffix = _normalize(text[anchor[1]:bounds[1]])
    if _DIRECT_PREFIX.fullmatch(between) and _COPULA.fullmatch(suffix):
        return "DIRECT_REGISTERED_DEFINITION"
    if between == "(" and _DIRECT_NAME_SUFFIX.fullmatch(suffix):
        # A bare or copular parenthetical name is a direct identity annotation.
        # Trailing clauses may instead contrast or reject the named entity.
        return "DIRECT_REGISTERED_NAME"
    return None


def assess_context(text: str, span: tuple[int, int], surface: str,
                   candidates: Sequence[Mapping], policy: Mapping | None = None
                   ) -> ContextResolutionEvidence:
    """Return bounded lexical evidence, or an explicit reason to abstain.

    ``policy`` accepts ``enabled`` (default false) and ``max_context_chars``
    (default 4096). ``allow_document_scope`` is ignored: distant or implicit
    references never authorize this experimental rule. A candidate has
    ``entity_id``, ``canonical`` and ``definition`` (``short_definition`` also
    accepted). Example sentences are intentionally unused.

    Callers must keep this experimental heuristic separate from fitted
    calibration and preserve their exact-match and full-surface identity guards.
    """
    def abstain(reason: str, scope: str | None = None):
        return ContextResolutionEvidence(abstention_reason=reason, scope=scope)

    policy = policy or {}
    if not policy.get("enabled", False):
        return abstain("DISABLED")
    if (not isinstance(span, (tuple, list)) or len(span) != 2
            or not all(isinstance(value, int) for value in span)
            or not 0 <= span[0] < span[1] <= len(text)
            or text[span[0]:span[1]] != surface):
        return abstain("INVALID_TARGET_SPAN")
    target = (span[0], span[1])
    records = {str(record.get("entity_id")): record for record in candidates
               if record.get("entity_id")}
    if len(records) < 2:
        return abstain("NO_EXACT_COLLISION")
    max_chars = policy.get("max_context_chars", 4096)
    if not isinstance(max_chars, int) or max_chars <= 0:
        return abstain("INVALID_CONTEXT_BUDGET")
    paragraphs = _paragraphs(text)
    paragraph_index = next((i for i, bounds in enumerate(paragraphs)
                            if bounds[0] <= target[0] < bounds[1]), None)
    if paragraph_index is None:
        return abstain("NO_TARGET_PARAGRAPH")
    first = paragraphs[paragraph_index]
    last = paragraphs[min(paragraph_index + 1, len(paragraphs) - 1)]
    scopes = [(first[0], last[1], "adjacent_paragraph")]

    anchors: dict[str, list[tuple[str, str]]] = {}
    for entity_id, record in records.items():
        collected = []
        for kind, field, minimum in (("canonical", "canonical", 6),
                                     ("definition", "definition", 12)):
            value = record.get(field)
            if field == "definition" and not value:
                value = record.get("short_definition")
            normalized = _normalize(value) if isinstance(value, str) else ""
            if sum(char.isalnum() for char in normalized) >= minimum:
                collected.append((kind, normalized))
        anchors[entity_id] = collected
    if not any(anchors.values()):
        return abstain("NO_MEANINGFUL_REGISTERED_ANCHOR")

    last_reason = "NO_EXPLICIT_REGISTERED_DEFINITION"
    for start, end, scope in scopes:
        if end - start > max_chars:
            last_reason = "CONTEXT_BUDGET_EXCEEDED"
            continue
        context = text[start:end]
        if context.count(surface) != 1:
            return abstain("REPEATED_TARGET_IN_CONTEXT", scope)
        sentences = []
        for paragraph_start, paragraph_end in paragraphs:
            if start <= paragraph_start and paragraph_end <= end:
                sentences.extend(_sentences(text, paragraph_start, paragraph_end))
        target_sentence = next(bounds for bounds in sentences
                               if bounds[0] <= target[0] < bounds[1])
        assertion = list(text[target_sentence[0]:target_sentence[1]])
        # Registered definitions can themselves contain words such as
        # "정정", "없", or job titles. They are evidence, not a negation of it.
        for entity_anchors in anchors.values():
            for _, anchor in entity_anchors:
                for anchor_start, anchor_end in _anchor_occurrences(
                        text, *target_sentence, anchor):
                    a = anchor_start - target_sentence[0]
                    b = anchor_end - target_sentence[0]
                    assertion[a:b] = " " * (b - a)
        if (_UNSUPPORTED_CONTEXT.search(_normalize("".join(assertion)))
                or _SCOPED_IDENTITY_CONTRADICTION.search(_normalize(context))):
            return abstain("UNSUPPORTED_OR_NEGATED_CONTEXT", scope)
        seen_entities: set[str] = set()
        supports: list[tuple[str, str, tuple[int, int], str]] = []
        for entity_id, entity_anchors in anchors.items():
            for kind, anchor in entity_anchors:
                for anchor_span in _anchor_occurrences(text, start, end, anchor):
                    seen_entities.add(entity_id)
                    relation = _identity_relation(text, target, anchor_span,
                                                  sentences)
                    if relation:
                        supports.append((entity_id, kind, anchor_span, relation))
        if len(seen_entities) > 1:
            return abstain("COMPETING_REGISTERED_ANCHORS", scope)
        if supports:
            entity_id, kind, anchor_span, relation = min(
                supports, key=lambda item: (item[2][0], item[2][1], item[1]))
            support_span = next(bounds for bounds in sentences
                                if bounds[0] <= anchor_span[0] < bounds[1])
            support_start, support_end = support_span
            while support_start < support_end and text[support_start].isspace():
                support_start += 1
            while support_end > support_start and text[support_end - 1].isspace():
                support_end -= 1
            support_span = (support_start, support_end)
            quote = text[support_start:support_end]
            return ContextResolutionEvidence(
                chosen_entity_id=entity_id, support_span=support_span,
                anchor_span=anchor_span,
                support_quote=quote, evidence_type=f"{relation}:{kind}",
                scope=scope)
    return abstain(last_reason)
