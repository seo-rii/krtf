"""In-document definitions of unregistered names (VARIANTS_PLAN M6).

REQ-LOC-001/002 were pinned only by tests asserting the detector does *not*
overwrite global bindings — properties a module that does nothing satisfies
perfectly, and over the 114,605-sentence corpus it very nearly did nothing:
2,346 definition patterns matched and six bindings came out, three of them
wrong. These tests pin the other half, that it finds something, and the shape
of what it refuses.
"""

import pytest

from ktrf.doclocal import (
    DocLocalDetector,
    NewTermDefinition,
    _PAT_IHA,
    align_definition,
)
from ktrf.glossary import load_glossary
from ktrf.matcher import ExactIndex
from ktrf.registry.proposals import (
    TermAdmissionPolicy,
    TermProposalStore,
    decide_admission,
    validate_term_proposal,
)


@pytest.fixture(scope="module")
def glossary():
    return load_glossary({
        "glossary_id": "t", "version": "1", "schema_version": "3",
        "entities": [
            {"entity_id": "E_KEPCO", "canonical": "한국전력공사",
             "description": "전력 공기업"},
        ],
        "alias_families": [
            {"family_id": "F_KEPCO", "representative": "한국전력공사",
             "normalization_profile": "korean_org_name"},
        ],
        "alias_bindings": [
            {"alias_id": "A_KEPCO", "family_id": "F_KEPCO",
             "entity_id": "E_KEPCO", "surface": "한국전력공사"},
            {"alias_id": "A_HJ", "family_id": "F_KEPCO",
             "entity_id": "E_KEPCO", "surface": "한전"},
        ],
    })


@pytest.fixture(scope="module")
def detector(glossary):
    return DocLocalDetector(ExactIndex(glossary))


# ---------------------------------------------------------------------------
# the 이하 bug: three fifths of that pattern's wild fires were a cut word
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", [
    "게토의 박해와 살인을 용이하게 만들었다",
    "2004년 노무현은 위기를 맞이하였다",
    "행동을 같이하여 대응했다",
])
def test_iha_inside_a_word_is_not_a_definition(text):
    """`용이하게` is one word. Splitting it yields a name ending at `용`."""
    assert not _PAT_IHA.findall(text)


@pytest.mark.parametrize("text", [
    "한국과학기술연구원, 이하 KIST",
    "한국과학기술연구원 이하 연구원",
])
def test_iha_still_reads_a_real_definition(text):
    assert _PAT_IHA.findall(text)


# ---------------------------------------------------------------------------
# what makes a pair an abbreviation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("long_form,short,canonical", [
    ("국가공무원노동조합", "국공노", "국가공무원노동조합"),
    ("추가경정예산", "추경", "추가경정예산"),
    ("Portland Pattern Repository", "PPR", "Portland Pattern Repository"),
    # reversed: the long form sits inside the parens
    ("학생부", "학교생활기록부", "학교생활기록부"),
])
def test_an_abbreviation_aligns_in_either_direction(long_form, short, canonical):
    """Subsequence alignment is script-agnostic and direction-agnostic."""
    found = align_definition(long_form, short)
    assert found is not None
    assert found.canonical == canonical
    assert found.surface == min((long_form, short), key=len)


@pytest.mark.parametrize("long_form,short", [
    ("서원초등학교", "초등학교"),   # the head noun, not an abbreviation
    ("대물변제", "변제"),
    ("선물옵션", "선물"),
    ("자동차손해보험사", "보험사"),
])
def test_a_contiguous_substring_does_not_abbreviate(long_form, short):
    """An abbreviation skips. A truncation is just the name cut off."""
    assert align_definition(long_form, short) is None


def test_the_alignment_says_where_the_name_starts():
    """`X(Y)` captures the clause before the paren; the name starts later."""
    found = align_definition("탈당하여 후보 단일화 추진 협의회", "후단협")
    assert found is not None
    assert found.canonical == "후보 단일화 추진 협의회"


def test_an_alignment_that_sprawls_past_the_name_is_refused():
    """`미국` does not abbreviate a sentence that merely contains 미 and 국."""
    assert align_definition(
        "미사일에 대한 국제사회와 트럼프대통령과 트럼프행정부", "미국") is None


def test_a_bare_type_terminal_is_never_proposed():
    """`위원회` aligns and abbreviates nothing — it names everything."""
    assert align_definition("미세먼지특별대책위원회", "위원회") is None


def test_a_single_character_alias_is_not_evidence():
    assert align_definition("한국전력공사", "한") is None


# ---------------------------------------------------------------------------
# detector-level: aliases and proposals are disjoint
# ---------------------------------------------------------------------------


def test_a_registered_long_form_stays_an_alias_not_a_proposal(detector):
    """`한국전력공사(한전공)` names an entity we hold — that is a binding."""
    text = "한국전력공사(한전공)은 발표했다"
    assert detector.extract(text)
    assert detector.extract_new_terms(text) == []


def test_an_unregistered_definition_is_reported_instead_of_dropped(detector):
    """This is the case the module existed for and never once reached."""
    text = "국가공무원노동조합(국공노)이 성명을 냈다"
    assert detector.extract(text) == []          # no entity to bind to
    found = detector.extract_new_terms(text)
    assert [(f.surface, f.canonical) for f in found] == \
        [("국공노", "국가공무원노동조합")]
    assert found[0].pattern == "paren"
    lo, hi = found[0].definition_span
    assert text[lo:hi].startswith("국가공무원노동조합(")


def test_the_detector_writes_to_no_glossary(detector, glossary):
    """INV-009: finding a new term must not touch the compiled glossary."""
    before = [(b.surface, b.entity_id) for b in glossary.alias_bindings]
    detector.extract_new_terms("국가공무원노동조합(국공노)이 성명을 냈다")
    assert [(b.surface, b.entity_id) for b in glossary.alias_bindings] == before
    assert not hasattr(NewTermDefinition, "register")


# ---------------------------------------------------------------------------
# the approval bridge
# ---------------------------------------------------------------------------


def test_a_definition_supplies_the_canonical_but_never_the_meaning(detector):
    """The document says what it is called. It does not say what it is."""
    found = detector.extract_new_terms("국가공무원노동조합(국공노)이 성명을 냈다")[0]
    with pytest.raises(ValueError, match="short_definition"):
        found.to_proposal(short_definition="   ", entry_id="doc-1")
    kwargs = found.to_proposal(short_definition="공무원 노동조합",
                               entry_id="doc-1")
    assert kwargs["canonical"] == "국가공무원노동조합"  # from the text
    assert kwargs["origin"] == "document_definition"
    assert kwargs["evidence_refs"][0].definition_pattern is True


def test_a_mined_definition_does_not_auto_activate(detector, glossary):
    """`document_definition` is an explicit origin, so scope decides."""
    found = detector.extract_new_terms("국가공무원노동조합(국공노)이 성명을 냈다")[0]
    kwargs = found.to_proposal(short_definition="공무원 노동조합",
                               entry_id="doc-1")
    assert kwargs["requested_scope"] == "project"

    class _Snap:
        pass
    snap = _Snap()
    snap.glossary = glossary
    store = TermProposalStore()
    proposal = store.submit(**kwargs)
    report = validate_term_proposal(proposal, snap)
    assert report["ok"], report["reasons"]
    state, _reason = decide_admission(proposal, TermAdmissionPolicy())
    assert state == "VALIDATED"

    # and the scope the detector refuses to pick for the caller would have
    # activated it without anyone saying yes
    session = store.submit(**{**kwargs, "requested_scope": "session"})
    assert decide_admission(session, TermAdmissionPolicy())[0] == "ACTIVE"


def test_a_definition_of_something_already_bound_is_refused(detector, glossary):
    """A proposal may not quietly re-point a surface the glossary owns."""
    class _Snap:
        pass
    snap = _Snap()
    snap.glossary = glossary
    store = TermProposalStore()
    proposal = store.submit(surface="한전", canonical="한국전력",
                            short_definition="전력 공기업",
                            requested_scope="project",
                            origin="document_definition",
                            evidence_refs=(),)
    report = validate_term_proposal(proposal, snap)
    assert not report["ok"]
    assert not report["checks"]["no_alias_collision"]


# ---------------------------------------------------------------------------
# the reversed branch: SHORT(LONG)
# ---------------------------------------------------------------------------


def test_a_latin_acronym_may_define_by_convention(detector):
    """`KIST(한국과학기술연구원)` — the alignment is a romanization we can
    not compute, so the convention is the evidence."""
    bindings = detector.extract("KEP(한국전력공사)이 밝혔다")
    assert [(b.alias_surface, b.entity_ids) for b in bindings] == \
        [("KEP", ["E_KEPCO"])]


def test_a_hangul_short_form_must_show_its_work(detector):
    """`한전공(한국전력공사)` aligns; a bare Hangul token does not."""
    assert [b.alias_surface for b in detector.extract("한전공(한국전력공사)")] \
        == ["한전공"]


@pytest.mark.parametrize("text,alias", [
    ("노선영(한국전력공사)가 선발됐다", "노선영"),        # 선수(소속팀)
    ("현대캐피탈(한국전력공사)이 2001.", "현대캐피탈"),   # 자회사(모기업)
])
def test_korean_apposition_is_not_a_definition(detector, text, alias):
    """Longer is not evidence. Each of these bound a surface to an entity it
    does not name, and handed it a scoring boost."""
    assert not any(b.alias_surface == alias for b in detector.extract(text))


# ---------------------------------------------------------------------------
# the press-release shape, found by a held-out corpus
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("long_form,short,canonical", [
    ("한국콘텐츠진흥원 원장 조현래", "한콘진", "한국콘텐츠진흥원"),
    ("코리아스타트업포럼 의장 박재욱", "코스포", "코리아스타트업포럼"),
])
def test_a_title_and_a_name_may_follow_the_name(long_form, short, canonical):
    """Korean press writing introduces a body as `기관명(직책 이름, 이하 약칭)`.
    A corpus that strips the parentheses leaves the title and person in front
    of the marker; the name still ends where its 어절 does."""
    found = align_definition(long_form, short)
    assert found is not None
    assert found.canonical == canonical


def test_an_alignment_spread_over_words_still_refuses_a_trailing_phrase():
    """The narrowing is only for an alignment inside one 어절. Scattered
    across several words with more words after it is a sentence, not a name."""
    assert align_definition(
        "미사일에 대한 국제사회와 트럼프대통령과 트럼프행정부", "미국") is None
    assert align_definition("혈구는 호흡 색소 검사", "혈색소") is None
