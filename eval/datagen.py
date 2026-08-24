"""Deterministic evaluation data generation (spec §37, §42 slices).

Generates labeled examples from a glossary: Level A catalog variants
(particles/chains/suffix/prefix/spacing/punct/width/case), Level B
recovery cases (jamo typo, keyboard mode, derived abbreviation, doc-local)
and §37.8 negatives. No randomness — everything derives from the glossary
and the catalogs, mirroring §14.8's philosophy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ktrf.glossary import Glossary
from ktrf.hangul import (
    CHOSEONG,
    compose_syllable,
    decompose_syllable,
    hangul_to_keys,
    is_syllable,
)
from ktrf.morphology import PARTICLES, _constraint_ok
from ktrf.normalization import normalize_alias


@dataclass
class GoldMention:
    span: tuple[int, int]  # codepoint half-open core span
    entity_id: str
    surface: str


@dataclass
class EvalExample:
    text: str
    slice: str
    level: str  # "A" | "B"
    gold: list[GoldMention] = field(default_factory=list)
    forbidden_entities: list[str] = field(default_factory=list)
    expect_no_mention: bool = False


def _gold(text: str, start: int, surface: str, entity_id: str) -> GoldMention:
    assert text[start:start + len(surface)] == surface
    return GoldMention((start, start + len(surface)), entity_id, surface)


_SINGLE_PARTICLES = ["은", "는", "이", "가", "을", "를", "도", "만", "에서",
                     "으로", "로", "까지", "부터", "조차", "마저", "처럼", "보다"]
_CHAINS = ["에서도", "까지는", "만이라도", "으로부터", "에서의"]


def _fullwidth(s: str) -> str:
    return "".join(chr(ord(c) + 0xFEE0) if 0x21 <= ord(c) <= 0x7E else c
                   for c in s)


def _derived_abbreviation(canonical: str) -> str | None:
    """과학기술정보통신부 -> 과기정통부 (even-index syllables + last)."""
    if not all(is_syllable(c) for c in canonical) or len(canonical) < 6:
        return None
    body = canonical[:-1]
    abbr = body[0::2] + canonical[-1]
    return abbr if 2 < len(abbr) < len(canonical) else None


def _jamo_typos(surface: str) -> list[str]:
    """Single-jamo typos on ≥3-syllable Hangul surfaces (§37.5)."""
    if len(surface) < 3 or not all(is_syllable(c) for c in surface):
        return []
    out = []
    # drop the final jongseong of the last syllable that has one
    for i in range(len(surface) - 1, -1, -1):
        cho, jung, jong = decompose_syllable(surface[i])
        if jong:
            out.append(surface[:i] + compose_syllable(cho, jung, "") + surface[i + 1:])
            break
    # substitute the first choseong with the next catalog consonant
    cho, jung, jong = decompose_syllable(surface[0])
    alt = CHOSEONG[(CHOSEONG.index(cho) + 1) % len(CHOSEONG)]
    out.append(compose_syllable(alt, jung, jong) + surface[1:])
    return out


def generate(glossary: Glossary) -> list[EvalExample]:
    examples: list[EvalExample] = []

    def add(text, slice_, level, gold=(), forbidden=(), none=False):
        examples.append(EvalExample(text, slice_, level, list(gold),
                                    list(forbidden), none))

    registered_keys = {
        normalize_alias(b.surface, glossary.binding_profile(b))
        for b in glossary.alias_bindings
    }

    for b in glossary.alias_bindings:
        s = b.surface
        eid = b.entity_id
        prof = glossary.binding_profile(b)
        last = s[-1]
        hangul_core = is_syllable(last)

        # ---- Level A ----
        t = f"{s} 관련 회의를 진행했다."
        add(t, "exact_base", "A", [_gold(t, 0, s, eid)])

        if b.boundary_policy.right == "particle_or_token_boundary":
            for p in _SINGLE_PARTICLES:
                if _constraint_ok(PARTICLES[p], last) is False:
                    continue
                t = f"{s}{p} 검토 대상이다."
                add(t, "particle_single", "A", [_gold(t, 0, s, eid)])
            for chain in _CHAINS:
                first = chain[:2] if chain[:2] in PARTICLES else chain[:1]
                if _constraint_ok(PARTICLES.get(first, "ANY"), last) is False:
                    continue
                t = f"{s}{chain} 공유되었다."
                add(t, "particle_chain", "A", [_gold(t, 0, s, eid)])

        if hangul_core:
            for sfx in ["본부", "담당자"]:
                t = f"{s}{sfx} 앞으로 전달했다."
                add(t, "suffix_residual", "A", [_gold(t, 0, s, eid)])
            t = f"{s}서울본부에서도 확인했다."
            add(t, "suffix_particle_chain", "A", [_gold(t, 0, s, eid)])

        if b.boundary_policy.left == "hangul_token_boundary":
            t = f"구 {s} 조직 개편안이다."
            add(t, "prefix_modifier", "A", [_gold(t, 2, s, eid)])
            t = f"전{s} 명의의 문서다."
            add(t, "prefix_modifier", "A", [_gold(t, 1, s, eid)])

        if prof.spacing_mode == "tolerant" and len(s) >= 2:
            mid = len(s) // 2
            v = s[:mid] + " " + s[mid:]
            t = f"{v} 명의로 계약했다."
            add(t, "spacing_variant", "A",
                [GoldMention((0, len(v)), eid, v)])

        if 2 <= len(s) <= 4:
            for p in prof.ignore_punctuation:
                v = p.join(s)
                t = f"{v} 항목을 점검했다."
                add(t, "punct_variant", "A", [GoldMention((0, len(v)), eid, v)])

        if any(c.isascii() and c.isalnum() for c in s):
            v = _fullwidth(s)
            t = f"{v} 장비 상태 보고."
            add(t, "width_variant", "A", [GoldMention((0, len(s)), eid, v)])
        if prof.case_fold == "ascii" and s.lower() != s:
            v = s.lower()
            t = f"{v} 확인 부탁드립니다."
            add(t, "case_variant", "A", [GoldMention((0, len(v)), eid, v)])

        if prof.latin_morph and last.isascii() and last.isalpha():
            t = f"{s}s 교체 작업 예정."
            add(t, "latin_morph_tail", "A", [_gold(t, 0, s, eid)])

        # ---- Level B ----
        key = normalize_alias(s, prof)
        for typo in _jamo_typos(s):
            t = f"{typo} 쪽에 문의했다."
            add(t, "jamo_typo_1", "B", [GoldMention((0, len(typo)), eid, typo)])
        if hangul_core and len(s) >= 2:
            keys = hangul_to_keys(s)
            if keys.isascii() and keys.isalpha():
                t = f"{keys} 담당자 확인 요청."
                add(t, "keyboard_mode", "B",
                    [GoldMention((0, len(keys)), eid, keys)])

        # ---- negatives (§37.8) ----
        if hangul_core and 2 <= len(s) <= 3:
            t = f"대{s}선 주가가 올랐다."
            add(t, "negative_embedded_hangul", "A", forbidden=[eid])
        if s.isascii() and s.isalpha() and len(s) <= 3:
            t = f"C{s}EX 절감 방안 논의."
            add(t, "negative_inside_latin_run", "A", forbidden=[eid])

    # ---- entity-level Level B: derived abbreviation (UE-derived, §42) ----
    for e in glossary.entities:
        abbr = _derived_abbreviation(e.canonical)
        if abbr and normalize_alias(
            abbr, glossary.normalization_profiles["korean_org_name"]
        ) not in registered_keys:
            t = f"{abbr}에서 발표했다."
            add(t, "ue_derived_abbreviation", "B",
                [GoldMention((0, len(abbr)), e.entity_id, abbr)])

    # ---- doc-local (§18) ----
    for e in glossary.entities:
        c = e.canonical
        if all(is_syllable(ch) for ch in c) and len(c) >= 4:
            short = c[0] + c[-1]
            t = f"{c}(이하 {short})가 주관한다. {short} 측 답변을 기다린다."
            pos = t.index(short, t.index(")"))
            add(t, "doc_local", "B",
                [GoldMention((pos, pos + len(short)), e.entity_id, short)])

    # ---- multi-mention (§37.7) ----
    surfaces: dict[str, str] = {}
    for b in glossary.alias_bindings:
        surfaces.setdefault(b.surface, b.entity_id)
    if {"한전KDN", "AP", "QMS"} <= set(surfaces):
        t = "한전KDN은 AP 장애 내용을 QMS에 등록했다."
        add(t, "multi_mention", "A", [
            _gold(t, 0, "한전KDN", surfaces["한전KDN"]),
            _gold(t, 7, "AP", surfaces["AP"]),
            _gold(t, 17, "QMS", surfaces["QMS"]),
        ])

    # ---- pure negative sentences ----
    for t in ["오늘 날씨가 맑고 회의는 없었다.",
              "점심 메뉴로 국밥을 먹었다.",
              "보고서 제출 기한은 다음 주 금요일이다."]:
        add(t, "negative_plain", "A", none=True)

    return examples
