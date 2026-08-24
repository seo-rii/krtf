"""Level B channel tests: fuzzy (§17), doc-local (§18), abbreviation (§21.7).

REQ-FUZ-001 (min-cost single application), REQ-FUZ-002 (short alias off),
REQ-LOC-001/002 (poisoning/promotion bans).
"""

import pytest

from ktrf.abbrev import AbbrevAligner
from ktrf.doclocal import DocLocalDetector
from ktrf.fuzzy import (
    COST_ADJACENT_KEY,
    COST_CV_SUBST,
    FuzzyIndex,
    weighted_edit_distance,
    _subst_cost,
)
from ktrf.glossary import load_glossary
from ktrf.hangul import hangul_to_keys, keys_to_hangul, to_jamo_seq
from ktrf.matcher import ExactIndex


@pytest.fixture(scope="module")
def glossary():
    return load_glossary({
        "glossary_id": "t", "version": "1", "schema_version": "3",
        "entities": [
            {"entity_id": "E_KEPCO", "canonical": "한국전력공사",
             "description": "전력 공기업"},
            {"entity_id": "E_MSIT", "canonical": "과학기술정보통신부"},
            {"entity_id": "E_QMS", "canonical": "Quality Management System"},
            {"entity_id": "E_KIST", "canonical": "한국과학기술연구원"},
            {"entity_id": "E_AP", "canonical": "Access Point"},
        ],
        "alias_families": [
            {"family_id": "F_KEPCO", "representative": "한국전력",
             "normalization_profile": "korean_org_name"},
            {"family_id": "F_MSIT", "representative": "과학기술정보통신부",
             "normalization_profile": "korean_org_name"},
            {"family_id": "F_QMS", "representative": "QMS",
             "normalization_profile": "latin_acronym"},
            {"family_id": "F_KIST_KO", "representative": "한국과학기술연구원",
             "normalization_profile": "korean_org_name"},
            {"family_id": "F_AP", "representative": "AP",
             "normalization_profile": "latin_acronym"},
        ],
        "alias_bindings": [
            {"alias_id": "A_KEPCO", "family_id": "F_KEPCO",
             "entity_id": "E_KEPCO", "surface": "한국전력"},
            {"alias_id": "A_MSIT", "family_id": "F_MSIT",
             "entity_id": "E_MSIT", "surface": "과학기술정보통신부"},
            {"alias_id": "A_QMS", "family_id": "F_QMS",
             "entity_id": "E_QMS", "surface": "QMS",
             "boundary_policy": {"left": "latin_token_boundary"}},
            {"alias_id": "A_KIST_KO", "family_id": "F_KIST_KO",
             "entity_id": "E_KIST", "surface": "한국과학기술연구원"},
            {"alias_id": "A_AP", "family_id": "F_AP",
             "entity_id": "E_AP", "surface": "AP",
             "boundary_policy": {"left": "latin_token_boundary"}},
        ],
    })


@pytest.fixture(scope="module")
def fuzzy(glossary):
    return FuzzyIndex(glossary)


def test_min_cost_single_application():
    # REQ-FUZ-001: adjacent-key choseong substitution charges 0.20, not 0.20+0.70
    a, b = "ㅁ", "ㄴ"  # a/s keys are adjacent, both consonants
    assert _subst_cost(a, b) == COST_ADJACENT_KEY
    # consonants on distant keys fall back to the generic 초성 substitution cost
    assert _subst_cost("ㅂ", "ㅊ") == COST_CV_SUBST  # q vs c: not adjacent


def test_missing_jongseong_recovered(fuzzy):
    # 종성 누락: 한국전려 -> 한국전력 (final ㄱ dropped)
    cands = fuzzy.query_jamo("한국전려", (0, 4))
    assert any(c.binding.alias_id == "A_KEPCO" and c.cost <= 0.3 for c in cands)


def test_short_alias_fuzzy_disabled(fuzzy):
    # REQ-FUZ-002: 2-char Latin alias (QMS is 3) - use AP (2 chars): no jamo fuzzy
    cands = fuzzy.query_jamo("AB", (0, 2))
    assert not any(c.binding.alias_id == "A_AP" for c in cands)


def test_keyboard_english_mode(fuzzy):
    keys = hangul_to_keys("한국전력")
    assert keys == "gksrnrwjsfur"
    cands = fuzzy.query_keyboard(keys, (0, len(keys)))
    assert any(c.binding.alias_id == "A_KEPCO" for c in cands)
    assert all(c.channel == "keyboard" for c in cands)


def test_keyboard_hangul_mode(fuzzy):
    # typing "qms" with IME on composes 븐
    token = keys_to_hangul("qms")
    cands = fuzzy.query_keyboard(token, (0, len(token)))
    assert any(c.binding.alias_id == "A_QMS" for c in cands)


def test_weighted_distance_symmetry_zero():
    j = to_jamo_seq("한국전력")
    assert weighted_edit_distance(j, j) == 0.0


# ---------------------------------------------------------------------------
# doc-local (§18)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def detector(glossary):
    return DocLocalDetector(ExactIndex(glossary))


def test_doclocal_paren_definition(detector):
    text = "한국과학기술연구원(KIST)은 발표했다. KIST 연구진은 이어서…"
    bindings = detector.extract(text)
    assert any(b.alias_surface == "KIST" and "E_KIST" in b.entity_ids
               for b in bindings)
    occs = detector.find_occurrences(text, bindings)
    # the defining occurrence is skipped; later mention found
    assert len([o for o in occs if o.surface == "KIST"]) == 1
    assert text[occs[0].span[0]:occs[0].span[1]] == "KIST"


def test_doclocal_iha_definition(detector):
    text = "한국과학기술연구원, 이하 연구원. 연구원 측 설명이다."
    bindings = detector.extract(text)
    assert any(b.alias_surface == "연구원" for b in bindings)


def test_doclocal_no_global_overwrite(detector, glossary):
    # §18.3: 한국전력(이하 AP) must NOT remove the global AP binding.
    # Detector only creates additive local bindings; global glossary untouched.
    text = "한국전력(이하 AP) 발표. AP 점검 결과."
    bindings = detector.extract(text)
    assert any(b.alias_surface == "AP" and b.entity_ids == ["E_KEPCO"]
               for b in bindings)
    assert any(b.surface == "AP" for b in glossary.alias_bindings)  # untouched


def test_doclocal_unknown_long_form_ignored(detector):
    bindings = detector.extract("어떤무명단체(WXYZ)가 있다")
    assert not bindings


# ---------------------------------------------------------------------------
# abbreviation alignment (§21.7)
# ---------------------------------------------------------------------------


def test_abbrev_hangul_subsequence(glossary):
    al = AbbrevAligner(glossary)
    cands = al.align_token("과기정통부", (0, 5))
    assert cands and cands[0].entity_id == "E_MSIT"


def test_abbrev_rejects_non_subsequence(glossary):
    al = AbbrevAligner(glossary)
    assert not [c for c in al.align_token("행정안전", (0, 4))
                if c.entity_id == "E_MSIT"]


def test_abbrev_latin_initials(glossary):
    al = AbbrevAligner(glossary)
    cands = al.align_token("QMS", (0, 3))
    assert any(c.entity_id == "E_QMS" for c in cands)
