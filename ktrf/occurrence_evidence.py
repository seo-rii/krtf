"""Experimental source evidence for one occurrence of an ambiguous alias.

This module selects source passages and applies a small assertion/refutation
gate. It never chooses an entity, estimates a probability, or grants permission
to execute an entity ID. Registered candidates only supply retrieval vocabulary;
the caller must retain the resolver's structural and execution guards.

The rules are deliberately bounded lexical heuristics. They do not establish
entailment, resolve arbitrary anaphora, or provide an end-to-end risk guarantee.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ktrf.context_resolution import _paragraphs, _quotation_spans, _sentences


@dataclass(frozen=True)
class EvidenceSpan:
    start: int
    end: int
    quote: str
    reason: str


@dataclass(frozen=True)
class AssertionAssessment:
    allowed: bool
    abstain_reason: str | None = None
    support_spans: tuple[EvidenceSpan, ...] = ()
    status: str = "EXPERIMENTAL_HEURISTIC"


@dataclass(frozen=True)
class EvidenceSelection:
    rendered_query: str
    spans: tuple[EvidenceSpan, ...]
    gate_allowed: bool
    abstain_reason: str | None
    mode: str
    status: str = "EXPERIMENTAL_HEURISTIC"
    assertion: AssertionAssessment | None = None


_HEADING = re.compile(r"^(?:#{1,6}\s+|\[[^\]\n]{1,60}\]\s*$|\d+[.)]\s+)")
_ROLE_SUFFIX = re.compile(r"(?:팀장|실장|센터장|위원장|원장|회장|부장|국장|대표|책임자)")
_AMBIGUOUS = re.compile(
    r"어느\s*(?:쪽|팀|부서|대상|업무|조직)[^.!?。？！\n]{0,65}"
    r"(?:알\s*수\s*없|모르|확정되지|결정되지|판단할\s*수\s*없|구분할\s*수\s*없)"
    r"|(?:두|여러)\s*(?:후보|부서|대상|팀)\s*중[^.!?。？！\n]{0,50}"
    r"(?:근거가\s*없|결정되지|확정되지|알\s*수\s*없)"
    r"|(?:수신처|담당\s*부서|대상\s*조직)[^.!?。？！\n]{0,30}"
    r"(?:아직\s*)?(?:미정|불명|확정되지|결정되지)"
)
_CLAIM_SUBJECT = (
    r"(?:(?:그|이|위|앞의|해당|이번)\s*)"
    r"(?:설명|주장|정의|해석|진술|문구|문장|이름|명칭|용어|표현|낱말|대상|물체|상품)"
)
_CLAIM_DENIAL = re.compile(
    _CLAIM_SUBJECT + r"[^,;\n.!?。？！]{0,65}"
    r"(?:틀리|틀린|틀렸|잘못|거짓|허위|가짜|사실과\s*다르|"
    r"철회|폐기|취소|삭제해야|미등록|등록(?:돼|되어|된)?\s*있지\s*않|"
    r"등록되지|등록한\s*업무\s*대상이\s*아니|"
    r"(?:상표|상품명|작품\s*이름|영화\s*제목|문자열\s*예시|입력\s*견본))"
    r"|" + _CLAIM_SUBJECT + r"(?:은|는|이|가)?\s*(?:실제\s*)?"
    r"(?:조직|부서|업무|진술)[^,;\n.!?。？！]{0,35}(?:아니|않)"
)
_TARGET_DENIAL = re.compile(
    r"(?:보내|전달하|연결하|지칭하|가리키|뜻하|배정하|사용하)지\s*(?:않|말)"
    r"|(?:담당|수신처|부서|조직|업무\s*대상)(?:이|가|은|는)?\s*아니"
    r"|(?:후보|이름|명칭|문구|안내|안)(?:을|를|은|는|이|가)?"
    r"[^,;\n.!?。？！]{0,30}(?:폐기|철회|취소|삭제)"
    r"|(?:실제\s*)?(?:부서|조직|서비스)[^,;\n.!?。？！]{0,35}"
    r"(?:부여한\s*적(?:은|이)?\s*없|등록(?:돼|되어)?\s*있지\s*않)"
)
_OBJECT_BEFORE = re.compile(
    r"(?:독서등|조명|상품|제품|브랜드|단편\s*영화|영화|소설|작품|상표)\s*$"
)
_OBJECT_AFTER = re.compile(
    r"(?:의\s*)?(?:사진|포스터|상영|상품|제품|상표|영화|작품|제목)"
)
_REJECTED_EXAMPLE = re.compile(
    r"(?:틀린|가짜|허위|잘못된)\s*(?:예문|예시|정의|주장|문장)"
    r"|(?:이름|철자|명칭)[^,;\n.!?。？！]{0,20}(?:연습|훈련)"
    r"[^,;\n.!?。？！]{0,55}(?:폐기|취소|철회)"
)
_NONMENTION_DENIAL = re.compile(
    r"(?:(?:틀린|가짜|허위|잘못된)\s*)?"
    r"(?:예문|예시|정의|주장|문장|상표|상품명|작품\s*이름|영화\s*제목|"
    r"문자열\s*예시|입력\s*견본)(?:이|가)?\s*아니"
)
_WORDS = re.compile(r"[0-9A-Za-z가-힣]+")


def _valid_span(text: str, span) -> bool:
    return (isinstance(text, str) and isinstance(span, (tuple, list))
            and len(span) == 2 and all(type(value) is int for value in span)
            and 0 <= span[0] < span[1] <= len(text)
            and bool(text[span[0]:span[1]].strip()))


def _record(text: str, bounds: tuple[int, int], reason: str) -> EvidenceSpan:
    return EvidenceSpan(bounds[0], bounds[1], text[bounds[0]:bounds[1]], reason)


def _aliases(candidates: Sequence[Mapping]) -> set[str]:
    aliases = set()
    for candidate in candidates:
        for field in ("aliases", "surfaces"):
            values = candidate.get(field, ())
            if isinstance(values, (tuple, list)):
                aliases.update(value for value in values if isinstance(value, str) and value)
    return aliases


def _section(text: str, target: tuple[int, int], paragraphs):
    """Recognize explicit headings only; prose paragraphs are never headings."""
    start, end = 0, len(text)
    for bounds in paragraphs:
        paragraph = text[bounds[0]:bounds[1]].strip()
        if "\n" in paragraph or len(paragraph) > 80 or not _HEADING.match(paragraph):
            continue
        if bounds[0] <= target[0]:
            start = bounds[0]
        elif bounds[0] > target[0]:
            end = bounds[0]
            break
    return start, end


def _unquoted_occurrences(text: str, surface: str, bounds: tuple[int, int]):
    fragment = text[bounds[0]:bounds[1]]
    quotes, malformed = _quotation_spans(fragment)
    if malformed:
        # Ambiguous quoting must not broaden passage scope.
        return ()
    occurrences, cursor = [], 0
    while (found := fragment.find(surface, cursor)) >= 0:
        finish = found + len(surface)
        cursor = finish
        containing = [(opening, closing) for opening, closing in quotes
                      if opening < found and finish < closing]
        if containing and any(fragment[opening + 1:closing - 1].strip() != surface
                              for opening, closing in containing):
            continue
        occurrences.append((bounds[0] + found, bounds[0] + finish))
    return tuple(occurrences)


def _mask_registered_anchors(fragment: str, candidates: Sequence[Mapping]) -> str:
    """Candidate names containing denial words are vocabulary, not assertions."""
    anchors = set()
    for candidate in candidates:
        for field in ("canonical", "short_definition", "definition"):
            anchor = candidate.get(field)
            if isinstance(anchor, str) and len(anchor) >= 3:
                anchors.add(anchor)
    for anchor in sorted(anchors, key=lambda item: (-len(item), item)):
        fragment = fragment.replace(anchor, " " * len(anchor))
    return fragment


def _denial(fragment: str, candidates: Sequence[Mapping]) -> str | None:
    outside_anchors = _mask_registered_anchors(fragment, candidates)
    outside_anchors = _NONMENTION_DENIAL.sub(" ", outside_anchors)
    if _CLAIM_DENIAL.search(outside_anchors):
        return "SCOPED_RETRACTION_OR_UNREGISTERED"
    if _AMBIGUOUS.search(outside_anchors):
        return "EXPLICITLY_UNRESOLVED_TARGET"
    return None


def assess_assertion(text: str, target_span, candidates: Sequence[Mapping]
                     ) -> AssertionAssessment:
    """Gate a ranking proposal using explicit assertions about this occurrence.

    An allowed result means these lexical vetoes did not fire. It is not proof
    that a candidate is correct. Whole quoted claims, explicit retractions,
    unregistered objects, target negations and declared ambiguity cause abstention.
    Negated candidate names elsewhere do not veto an affirmed target request.
    """
    if not _valid_span(text, target_span):
        return AssertionAssessment(False, "INVALID_TARGET_SPAN")
    target = tuple(target_span)
    surface = text[target[0]:target[1]]
    aliases = _aliases(candidates)
    if aliases and surface not in aliases and not any(
            surface == candidate.get("canonical") for candidate in candidates):
        return AssertionAssessment(False, "TARGET_SURFACE_NOT_REGISTERED")
    paragraphs = _paragraphs(text)
    index = next((i for i, bounds in enumerate(paragraphs)
                  if bounds[0] <= target[0] and target[1] <= bounds[1]), None)
    if index is None:
        return AssertionAssessment(False, "NO_TARGET_PARAGRAPH")
    paragraph = paragraphs[index]
    raw = text[paragraph[0]:paragraph[1]]
    quote_spans, malformed = _quotation_spans(raw)
    evidence = (_record(text, paragraph, "TARGET_ASSERTION"),)
    if malformed:
        return AssertionAssessment(False, "UNCERTAIN_QUOTATION", evidence)
    for opening, closing in quote_spans:
        opening += paragraph[0]
        closing += paragraph[0]
        if opening < target[0] and target[1] < closing:
            if text[opening + 1:closing - 1].strip() != surface:
                return AssertionAssessment(False, "QUOTED_ASSERTION", evidence)
    if _ROLE_SUFFIX.match(text[target[1]:]):
        return AssertionAssessment(False, "DISTINCT_ROLE_SURFACE", evidence)
    sentence = next((bounds for bounds in _sentences(text, *paragraph)
                     if bounds[0] <= target[0] < bounds[1]), paragraph)
    statement = text[sentence[0]:sentence[1]]
    outside_anchors = _mask_registered_anchors(statement, candidates)
    outside_anchors = _NONMENTION_DENIAL.sub(" ", outside_anchors)
    if _TARGET_DENIAL.search(outside_anchors) or _REJECTED_EXAMPLE.search(outside_anchors):
        return AssertionAssessment(False, "NEGATED_OR_REJECTED_TARGET", evidence)
    # Registered identity predicates may themselves be denied. A denial of
    # "being an example" is different and is not included in this check.
    for candidate in candidates:
        for field in ("canonical", "definition", "short_definition"):
            anchor = candidate.get(field)
            if not isinstance(anchor, str) or not anchor:
                continue
            found = text.find(anchor, target[1], sentence[1])
            if found >= 0 and re.match(r"\s*(?:이|가)?\s*아니", text[found + len(anchor):sentence[1]]):
                return AssertionAssessment(False, "NEGATED_OR_REJECTED_TARGET", evidence)
    before = text[sentence[0]:target[0]].strip()
    after = text[target[1]:sentence[1]].lstrip()
    if _OBJECT_BEFORE.search(before) and _OBJECT_AFTER.match(after):
        return AssertionAssessment(False, "EXPLICIT_UNREGISTERED_OBJECT", evidence)
    reason = _denial(raw, candidates)
    if reason:
        return AssertionAssessment(False, reason, evidence)

    # Scope remote uncertainty/retraction only when no other unquoted target
    # occurrence can be its antecedent. Multi-target documents stay local.
    section = _section(text, target, paragraphs)
    occurrences = _unquoted_occurrences(text, surface, section)
    if len(occurrences) == 1:
        scope = [bounds for bounds in paragraphs
                 if section[0] <= bounds[0] < section[1] and bounds != paragraph]
    else:
        # An immediately following explicitly scoped denial may retract the
        # local assertion, but cannot cross another occurrence or section.
        scope = paragraphs[index + 1:index + 2]
        scope = [bounds for bounds in scope if bounds[0] < section[1]
                 and surface not in text[bounds[0]:bounds[1]]]
    for bounds in scope:
        reason = _denial(text[bounds[0]:bounds[1]], candidates)
        if reason:
            return AssertionAssessment(False, reason,
                                       evidence + (_record(text, bounds, "SCOPED_VETO"),))
    return AssertionAssessment(True, support_spans=evidence)


def _features(text: str) -> set[str]:
    # Character pairs retain Korean morphology without an external tokenizer.
    return {word[i:i + 2].lower() for word in _WORDS.findall(text)
            for i in range(len(word) - 1)}


def _retrieval_score(text: str, candidate_features: Sequence[set[str]]) -> float:
    features = _features(text)
    return max((2 * len(features & vocabulary) / (len(features) + len(vocabulary))
                for vocabulary in candidate_features if features or vocabulary), default=0.0)


def _safe_support(fragment: str, candidates: Sequence[Mapping]) -> bool:
    quotes, malformed = _quotation_spans(fragment)
    if malformed:
        return False
    names = _aliases(candidates) | {candidate.get("canonical") for candidate in candidates}
    if any(fragment[opening + 1:closing - 1].strip() not in names
           for opening, closing in quotes):
        return False
    outside_anchors = _mask_registered_anchors(fragment, candidates)
    outside_anchors = _NONMENTION_DENIAL.sub(" ", outside_anchors)
    return not (_TARGET_DENIAL.search(outside_anchors)
                or _REJECTED_EXAMPLE.search(outside_anchors)
                or _denial(fragment, candidates))


def select_evidence(text: str, core_span, candidates: Sequence[Mapping], *,
                    mode: str = "paragraph", max_chars: int = 1024
                    ) -> EvidenceSelection:
    """Select source paragraphs without using labels or choosing a candidate.

    ``paragraph`` is the ungated target-paragraph control. ``scoped`` adds up to
    two affirmatively presented passages ranked by maximum lexical overlap with
    *any* registered candidate, only for a single target occurrence in a section.
    Otherwise its passage scope stays at the current target paragraph. Complete
    passages, raw offsets, and original source order are preserved. The budget
    includes markers and paragraph separators; overflow abstains without clipping.
    """
    def refuse(reason: str, spans=()):
        return EvidenceSelection("", tuple(spans), False, reason, mode)

    if mode not in {"paragraph", "scoped"}:
        raise ValueError("mode must be paragraph or scoped")
    if type(max_chars) is not int or max_chars <= 0:
        return refuse("INVALID_CONTEXT_BUDGET")
    if not _valid_span(text, core_span):
        return refuse("INVALID_TARGET_SPAN")
    target = tuple(core_span)
    paragraphs = _paragraphs(text)
    paragraph = next((bounds for bounds in paragraphs
                      if bounds[0] <= target[0] and target[1] <= bounds[1]), None)
    if paragraph is None:
        return refuse("NO_TARGET_PARAGRAPH")
    selected = [_record(text, paragraph, "TARGET_PARAGRAPH")]
    assessment = assess_assertion(text, target, candidates)
    if mode == "scoped":
        surface = text[target[0]:target[1]]
        section = _section(text, target, paragraphs)
        if len(_unquoted_occurrences(text, surface, section)) == 1:
            vocabularies = []
            for candidate in candidates:
                profile = " ".join(str(candidate.get(field) or "") for field in
                                   ("canonical", "short_definition", "definition", "profile"))
                vocabularies.append(_features(profile))
            supporting = []
            for bounds in paragraphs:
                if bounds == paragraph or not section[0] <= bounds[0] < section[1]:
                    continue
                fragment = text[bounds[0]:bounds[1]]
                if not _safe_support(fragment, candidates):
                    continue
                score = _retrieval_score(fragment, vocabularies)
                if score > 0:
                    supporting.append((score, bounds))
            supporting.sort(key=lambda item: (-item[0], abs(item[1][0] - target[0]), item[1][0]))
            selected.extend(_record(text, bounds, "REGISTERED_VOCABULARY_SUPPORT")
                            for _, bounds in supporting[:2])
    selected.sort(key=lambda item: item.start)
    pieces = []
    for item in selected:
        if item.start <= target[0] and target[1] <= item.end:
            pieces.append(text[item.start:target[0]] + "[TARGET]"
                          + text[target[0]:target[1]] + "[/TARGET]" + text[target[1]:item.end])
        else:
            pieces.append(item.quote)
    rendered = "\n\n".join(pieces)
    if len(rendered) > max_chars:
        return refuse("CONTEXT_BUDGET_EXCEEDED", selected)
    allowed = mode == "paragraph" or assessment.allowed
    return EvidenceSelection(rendered, tuple(selected), allowed,
                             None if allowed else assessment.abstain_reason, mode,
                             assertion=assessment)
