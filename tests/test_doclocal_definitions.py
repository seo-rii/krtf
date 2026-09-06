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


# ---------------------------------------------------------------------------
# the name is what the parenthesis defines, not everything before it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("preamble", [
    "", "이날 ", "정부는 ", "어제 서울에서 ", "관계 부처와 협의를 마친 ",
])
def test_words_before_the_name_do_not_decide_whether_it_defines(detector,
                                                                preamble):
    """The proportional gate measured the match against the whole capture, so
    `이날 한국전력공사(이하 한전)` kept the definition and `정부는 …` lost it.
    Three characters of unrelated preamble is not a fact about the name."""
    text = f'{preamble}한국전력공사(이하 "한전")가 발표했다. 한전은 이어 설명했다.'
    bindings = detector.extract(text)
    assert len(bindings) == 1, f"{preamble!r} lost the definition"
    assert bindings[0].alias_surface == "한전"
    assert bindings[0].long_form == "한국전력공사"
    assert bindings[0].entity_ids == ["E_KEPCO"]


def test_the_long_form_is_the_name_not_the_sentence_so_far(detector):
    text = '정부는 한국전력공사(이하 "한전")와 협의했다. 한전이 답했다.'
    assert detector.extract(text)[0].long_form == "한국전력공사"


def test_a_name_glued_to_the_previous_word_is_not_anchored(detector):
    """Right-anchoring alone is not enough: the match also has to begin a
    word, or the tail of any longer token would read as a name of its own.
    `대한한국전력공사` is one token, so nothing in it defines 한전."""
    assert detector.extract("대한한국전력공사(한전)가 있다. 한전은 답했다.") == []


# ---------------------------------------------------------------------------
# a bracket is not a definition by itself
# ---------------------------------------------------------------------------


def test_a_qualifier_in_brackets_is_not_a_definition(detector):
    """From the wild corpus: `서울특별시(사실상), 세종특별자치시(행정)` is a
    line about which capital is which, not two definitions. 사실상 is not an
    abbreviation of 서울특별시 and the document never uses it as a name."""
    text = "대한민국 - 한국전력공사(사실상), 한전(행정)"
    # neither bracket survives: 사실상 abbreviates nothing and the line
    # never uses it as a name, and 행정 is the same shape
    assert detector.extract(text) == []


def test_iha_says_outright_that_it_is_a_definition(detector):
    """`이하` needs no corroboration — declaring the alias is what it does."""
    text = "한국전력공사(이하 케이피)가 발표했다."
    bindings = detector.extract(text)
    assert [b.alias_surface for b in bindings] == ["케이피"]


def test_a_bare_bracket_is_kept_when_the_document_uses_the_name(detector):
    """코레일 is not an abbreviation of 한국철도공사, and it is still a real
    doc-local alias in a document that goes on to use it."""
    used = "한국전력공사(케이피) 설립준비단장을 위촉했다. 케이피 출범을 준비한다."
    assert [b.alias_surface for b in detector.extract(used)] == ["케이피"]

    unused = "한국전력공사(케이피), 한국수력원자력 등 103개 기관이 동참했다."
    assert detector.extract(unused) == []


def test_a_bare_bracket_is_kept_when_it_reads_as_an_abbreviation(detector):
    """한전 abbreviates 한국전력공사, so the bracket needs no other support."""
    text = "한국전력공사(한전)가 발표했다."
    assert [b.alias_surface for b in detector.extract(text)] == ["한전"]


def test_a_definition_supported_only_by_a_later_chunk_survives_chunking():
    """The recurrence rule reads the document, and a job is a document.

    `케이피` abbreviates nothing and carries no `이하`; it is a doc-local
    alias only because the text goes on to use it — six sentences later, in
    another chunk. Extracted per chunk, no chunk both defines and uses it and
    the definition disappears. The job extracts once from the whole text
    (INV-017), so the async path answers what the sync path answers.
    """
    from ktrf.jobs import ResolveJobManager
    from ktrf.resolver import resolve
    from ktrf.snapshot import compile_snapshot

    snap = compile_snapshot(load_glossary("examples/realorg_glossary.yaml"),
                            strict=False, run_conformance=False)
    text = ("한국전력공사(케이피)가 발표했다. " + "관련 회의가 이어졌다. " * 6
            + "케이피는 이어 설명했다.")

    assert [b.alias_surface for b in snap.doclocal.extract(text)] == ["케이피"]

    mgr = ResolveJobManager(
        max_chunk_bytes=len(text.encode("utf-8")) // 3 + 20)
    jid = mgr.submit(snap, text,
                     options={"return_all_mentions": True})["job_id"]
    job = mgr._get(jid)
    assert len(job.chunks) > 1
    # no single chunk can see both the definition and the use
    assert all(snap.doclocal.extract(text[a:b]) == []
               for a, b in job.chunks)
    mgr.process(jid)

    def doc_local(resp):
        return [m["surface"] for m in resp["mentions"]
                if "doc_local" in (m.get("generation_channels") or [])]

    chunked = doc_local(mgr.results(jid, page_size=500))
    sync = doc_local(resolve(snap, text, mode="commit",
                             options={"return_all_mentions": True}))
    assert chunked == sync == ["케이피"]
